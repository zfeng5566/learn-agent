# 第 10 章 消息队列：RocketMQ / Kafka、可靠投递、幂等与延迟消息

> [← 总纲](./00-outline.md) | [上一章：Redis 与缓存](./09-redis-cache.md) | [下一章：微服务与分布式](./11-microservices.md)

---

## 1. 本章地图

```
                 ┌──────────── 订单服务进程 ────────────┐
 下单请求 ──────▶│ Controller → Biz → OrderCreateUnit   │
                 │                    │ 写 MySQL          │
                 │                    ▼                   │
                 │            OrderEventProducer ─────────┼──▶ RocketMQ Broker
                 └───────────────────────────────────────┘        │
                                                                   │ 本章重点
              ┌──────────────────────┬─────────────────────────────┤
              ▼                      ▼                             ▼
      通知消费者(短信/站内信)   积分消费者(加积分)      延迟消息 30 分钟后 → 超时取消消费者
```

本章回答四个问题：

| 问题 | 对应小节 |
|---|---|
| 为什么要引入 MQ，它和前端的 EventEmitter 有什么本质区别 | 2、3 |
| RocketMQ / Kafka 内部怎么存消息、怎么保证不丢 | 4 |
| 消息会丢、会重、会乱序、会堆积，怎么办 | 3.5 ~ 3.10、6 |
| 在 mini-mall 中如何落地：下单事件、30 分钟自动取消、消费幂等、事务消息 | 5 |

在总纲全景图中，MQ 属于「进程外的中间件」：它是订单服务与其他业务之间的**异步、持久化的通信管道**。

---

## 2. 前端类比

### 2.1 你已经会的「发布订阅」

```ts
// TS：浏览器/Node 里的 EventEmitter
import { EventEmitter } from 'events';

const bus = new EventEmitter();

// 订阅：积分模块、通知模块各自监听
bus.on('order:created', (e: { orderNo: string; userId: number }) => addPoints(e));
bus.on('order:created', (e) => sendSms(e));

// 发布：下单成功后广播
bus.emit('order:created', { orderNo: 'M202611260001', userId: 1001 });
```

```java
// Java：用 RocketMQ 完成同样的事情（简化版，完整代码见第 5 节）
/**
 * 下单成功后发布订单创建事件。
 *
 * @param event 订单创建事件，包含订单号、用户 ID、金额
 */
public void publishOrderCreated(OrderCreatedEvent event) {
    // destination 格式为 "topic:tag"，tag 用于消费端二次过滤
    rocketMQTemplate.syncSend("mall_order_topic:ORDER_CREATED", event);
}
```

形式上几乎一样：**发布者不知道有谁订阅，订阅者不知道谁发布**。但本质差异巨大：

| 维度 | EventEmitter / postMessage | 消息队列（RocketMQ/Kafka） |
|---|---|---|
| 通信范围 | 同一进程（或同源窗口/Worker） | **跨进程、跨机器、跨机房** |
| 消息存储 | 内存，不保存；没订阅者就丢 | **持久化到磁盘**，订阅者晚上线也能收到 |
| 进程崩溃 | 一切消失 | 消息还在 Broker，重启后继续消费 |
| 投递语义 | 同步调用，调完就完 | **至少一次（At Least Once）**：可能重复 |
| 失败处理 | 回调抛异常就结束 | 自动重试 N 次 → 进入死信队列 |
| 顺序 | 天然有序 | 默认**不保证**全局顺序 |
| 消费速度 | 同步执行 | 消费者按自己能力拉取，可**削峰**、可**堆积** |
| 多副本 | 无 | 订阅组之间各收一份；组内多实例**分摊** |

> 一句话：**EventEmitter 是函数调用的语法糖；MQ 是一个分布式、持久化的「邮局」**。邮局会弄丢信（概率低）、会投递两次、会晚到——你写的代码必须容忍这些。

### 2.2 为什么需要 MQ：解耦、异步、削峰

```
【无 MQ：同步串行】                          【有 MQ：异步解耦】
下单 ─▶ 写库 20ms                            下单 ─▶ 写库 20ms ─▶ 发消息 5ms ─▶ 返回（25ms）
     ─▶ 调积分服务 80ms                                              │
     ─▶ 调短信服务 200ms                          ┌─────────────────┼────────────┐
     ─▶ 调推荐服务 50ms                           ▼                 ▼            ▼
     ─▶ 返回（350ms，任一失败则下单失败）       积分服务         短信服务     推荐服务
                                               （各自消费，失败各自重试，互不影响）
```

| 价值 | 说明 | 前端里的影子 |
|---|---|---|
| **解耦** | 新增「下单后给推荐系统打点」只需新增一个消费组，订单服务零改动 | 组件间用事件总线代替 props 层层透传 |
| **异步** | 非核心链路（通知、积分）不阻塞主流程，接口 RT 降低 | `requestIdleCallback`、上报日志用 `sendBeacon` |
| **削峰** | 秒杀瞬间 10 万 QPS 写入 MQ，下游按 2000 QPS 匀速消费 | 输入框防抖、请求队列限并发 |

代价也必须说清：

- **系统复杂度上升**：多了一个必须高可用的中间件。
- **一致性变成最终一致**：下单成功那一刻，积分可能还没加上。
- **需要处理丢失、重复、乱序、堆积**——这是本章的重心。

> 判断标准：**下游失败时，主流程是否必须一起失败？** 必须一起失败（如扣库存）→ 同步调用；可以稍后补偿（如加积分、发短信）→ MQ。

---

## 3. 核心概念

### 3.1 核心模型

```
Producer ──send──▶ ┌──────────────── Broker ────────────────┐ ──pull──▶ Consumer Group A（积分）
                   │ Topic: mall_order_topic                 │              ├─ 实例 A1 ← Queue0,1
                   │   ├─ Queue 0  [m1][m4][m7]...           │              └─ 实例 A2 ← Queue2,3
                   │   ├─ Queue 1  [m2][m5]...               │
                   │   ├─ Queue 2  [m3][m6]...               │ ──pull──▶ Consumer Group B（通知）
                   │   └─ Queue 3  ...                       │              └─ 实例 B1 ← Queue0~3
                   └─────────────────────────────────────────┘
```

| 概念 | 含义 | 类比 |
|---|---|---|
| **Producer** | 消息发送方 | `bus.emit` 的调用方 |
| **Broker** | 存储与转发消息的服务器 | 邮局 |
| **Topic** | 消息的逻辑分类，如 `mall_order_topic` | 事件名 `order:*` |
| **Tag**（RocketMQ） | Topic 下的二级分类，如 `ORDER_CREATED` | 事件名的后缀 |
| **Queue / Partition** | Topic 的物理分片，**并行度与顺序性的最小单位** | — |
| **Consumer Group** | 一组逻辑相同的消费者实例，**组内分摊、组间广播** | 一个 `bus.on` 订阅（但可横向扩容多个实例） |
| **Offset** | 消费者在某个 Queue 上读到的位置 | 游标 / 书签 |
| **Message Key** | 业务唯一键（如订单号），用于查询和去重 | — |

### 3.2 集群消费 vs 广播消费

| 模式 | 行为 | 典型场景 |
|---|---|---|
| **集群消费 CLUSTERING**（默认） | 同一组内，一条消息只被**一个**实例消费 | 99% 的业务：加积分、发短信 |
| **广播消费 BROADCASTING** | 同一组内，每个实例**都**消费一次 | 刷新每台机器的本地缓存 |

> 关键认知：**「一条消息被几个服务处理」由消费组数量决定；「一个服务内谁处理」由消费模式决定。**
> 积分服务部署 3 个实例、同属 `mall-points-cg` → 每条消息只加一次积分；通知服务另一个组 `mall-notify-cg` → 也收到一份。

### 3.3 推模式 vs 拉模式

| 模式 | 原理 | 优缺点 |
|---|---|---|
| Push | Broker 主动推给消费者 | 实时；但消费者处理不过来会被压垮 |
| Pull | 消费者主动拉 | 消费者自控节奏；但轮询有延迟和空转 |
| **长轮询**（RocketMQ/Kafka 实际做法） | 消费者拉取，Broker 无消息时**挂起请求**最多 N 秒，有消息立刻返回 | 兼顾实时性和流控 |

RocketMQ 的 `DefaultMQPushConsumer` 名字叫 Push，**底层其实是长轮询 Pull**，只是 SDK 帮你封装成了回调。这和前端的 SSE / 长轮询 `fetch` 是一个思路。

### 3.4 发送方式

| 方式 | API | 可靠性 | 场景 |
|---|---|---|---|
| 同步发送 | `syncSend` | 高：拿到 Broker 确认才返回 | **业务消息默认用它** |
| 异步发送 | `asyncSend` + 回调 | 高（需在回调里处理失败） | RT 敏感、量大 |
| 单向发送 | `sendOneWay` | 低：不等确认 | 日志采集，可丢 |

```ts
// TS 对照：同步发送 ≈ await fetch；异步发送 ≈ fetch().then().catch()；单向 ≈ navigator.sendBeacon
await api.post('/mq', msg);                                  // 同步
api.post('/mq', msg).then(onOk).catch(onErr);                // 异步
navigator.sendBeacon('/log', JSON.stringify(msg));           // 单向，不关心结果
```

### 3.5 消息可靠性：三段都要守住

```
  ① 生产端                     ② Broker 存储                     ③ 消费端
Producer ──网络──▶ Broker 内存 ──刷盘──▶ 磁盘 ──复制──▶ Slave      Consumer 处理 ──▶ ACK
   丢点：网络失败、             丢点：异步刷盘时宕机、              丢点：先 ACK 后处理、
        发完不检查结果                单副本磁盘损坏                     吞掉异常
```

| 环节 | 措施 | 配置/做法 |
|---|---|---|
| 生产端 | 同步发送 + 检查 `SendStatus` + 失败重试；仍失败则落库补偿 | `retryTimesWhenSendFailed=2`；本地消息表或事务消息 |
| Broker | 同步刷盘 + 同步复制（或多副本） | `flushDiskType=SYNC_FLUSH`、`brokerRole=SYNC_MASTER`；Kafka `acks=all` + `min.insync.replicas=2` |
| 消费端 | **业务处理成功后才 ACK**；失败抛异常让 MQ 重试 | Listener 里不要 catch 吞掉异常 |

> 金融级才全开同步刷盘（吞吐下降明显）；一般业务用「异步刷盘 + 同步复制」——单机宕机靠从节点兜底，性价比最高。

### 3.6 重复消费与幂等

**MQ 只保证「至少一次」，重复是必然的**。重复来源：

1. 生产端：发送超时但实际已写入，SDK 重试 → Broker 里有两条。
2. 消费端：处理完成但 ACK 前进程崩溃 / 网络断开 → 重新投递。
3. Rebalance：消费者扩缩容，Queue 重新分配，未提交 offset 的消息被新实例再消费一次。

幂等方案对比：

| 方案 | 做法 | 优点 | 缺点 | 适用 |
|---|---|---|---|---|
| 业务唯一键 + 唯一索引 | 积分流水表 `uk(order_no, biz_type)` | 最可靠，和业务同事务 | 每个业务都要设计 | **首选** |
| 通用去重表 | `t_mq_consume_record` 唯一键 `(consumer_group, msg_key)` | 通用 | 多一次写库 | 没有天然唯一键时 |
| 状态机 | `UPDATE ... SET status=2 WHERE status=0` | 零额外存储 | 只适合有状态流转的场景 | 订单取消、支付回调 |
| Redis `SETNX` | `SET key 1 NX EX 86400` | 快 | 与业务库非原子：Redis 写成功但业务失败 → 消息被误判为已消费 | 非核心、可容忍极少丢失 |

### 3.7 顺序消息

场景：同一订单的「创建 → 支付 → 发货」消息，消费端必须按序处理。

```
全局有序：Topic 只有 1 个 Queue → 吞吐极低，几乎不用
分区有序：按 orderNo 哈希选 Queue，同一订单的消息落同一个 Queue，Queue 内 FIFO

 orderNo=A ─hash─▶ Queue1: [A创建][A支付][A发货]   ← 单线程按序消费
 orderNo=B ─hash─▶ Queue3: [B创建][B支付]
```

三个条件缺一不可：

1. **发送端**：同一业务键发到同一 Queue（`syncSendOrderly(dest, msg, hashKey)`），且必须**同步单线程**发送；
2. **Broker**：Queue 内本身 FIFO；
3. **消费端**：`ConsumeMode.ORDERLY`，对 Queue 加锁、单线程消费；失败时**原地重试、阻塞后续消息**（不会跳过）。

> 代价：一条消息卡住会阻塞整个 Queue。很多场景可以用**状态机**替代顺序消息：消费端判断「当前状态是否允许这一步」，乱序到达的消息要么丢弃要么稍后重试。

### 3.8 延迟消息

| 版本 | 能力 | 实现 |
|---|---|---|
| RocketMQ 4.x | 18 个固定级别：`1s 5s 10s 30s 1m 2m 3m 4m 5m 6m 7m 8m 9m 10m 20m 30m 1h 2h` | 消息先写入 `SCHEDULE_TOPIC_XXXX` 的对应级别队列，定时线程到点后转投原 Topic |
| RocketMQ 5.x | **任意精度延迟**（默认最长 24 小时，可配置） | 基于**时间轮（TimerWheel）+ TimerLog** 的定时消息 |
| Kafka | 原生不支持 | 自己实现：分级延迟 Topic、或借助外部调度 |
| RabbitMQ | TTL + 死信交换机，或延迟插件 | — |

mini-mall 的 30 分钟取消：4.x 正好用级别 16（30m），5.x 直接指定 1800 秒。

### 3.9 事务消息：半消息 + 回查

问题：**写库和发消息是两个系统，无法放在一个本地事务里**。

```
先写库再发消息：库提交成功，发消息前进程挂了 → 消息丢失（订单有了，积分永远不加）
先发消息再写库：消息发出，写库失败回滚     → 消息多余（订单没了，积分却加了）
```

RocketMQ 事务消息流程：

```
Producer                               Broker                         本地 DB
   │ ① 发送半消息（Half，消费者不可见）   │                               │
   │────────────────────────────────────▶│ 存入 RMQ_SYS_TRANS_HALF_TOPIC │
   │◀──────────── ② 半消息写入成功 ──────│                               │
   │ ③ 执行本地事务 executeLocalTransaction ─────────────────────────────▶│ 写订单
   │ ④ 根据结果提交 COMMIT / ROLLBACK     │                               │
   │────────────────────────────────────▶│ COMMIT → 转投真实 Topic，消费者可见
   │                                      │ ROLLBACK → 丢弃
   │                                      │
   │   若 ④ 丢失（进程崩溃/返回 UNKNOWN）  │
   │◀──── ⑤ 定时回查 checkLocalTransaction│（默认 60s 一次，最多 15 次）
   │ ⑥ 查库：订单存在 → COMMIT，不存在 → ROLLBACK
```

核心思想：**把「发消息」拆成「预发送 + 确认」，用回查把不确定状态收敛为确定状态**。回查的前提是：本地事务结果必须**可查**（比如按订单号查订单是否存在）。

### 3.10 消息堆积与死信队列

**堆积**：生产速度 > 消费速度，`消费延迟 = Broker 最大 offset - 消费组已提交 offset`。

排查与处理顺序：

| 步骤 | 动作 |
|---|---|
| 1. 定位 | 控制台看哪个消费组、哪个 Queue 堆积；是全部 Queue 还是个别 Queue（个别 → 某实例卡死或顺序消息阻塞） |
| 2. 看消费端 | `jstack` / Arthas 看消费线程卡在哪：慢 SQL、下游超时、死锁 |
| 3. 临时扩容 | 增加消费实例（**实例数 ≤ Queue 数才有效**，多出来的实例空闲）；调大 `consumeThreadMax` |
| 4. 紧急转移 | Queue 数不够时：写一个临时消费者把消息原样转发到一个 Queue 更多的新 Topic，再用大量实例消费新 Topic |
| 5. 降级 | 非核心消息可以跳过（重置 offset），事后用对账补偿 |
| 6. 根治 | 批量消费、异步化下游调用、优化 SQL |

**死信队列（DLQ）**：并发消费模式下一条消息重试 16 次（默认，间隔 10s → 2h 递增）仍失败，进入 `%DLQ%{consumerGroup}`。死信不会自动消费，需要：

1. 对 DLQ 配置**告警**；
2. 人工排查原因，修复后在控制台重新投递，或写专门的消费者处理。

### 3.11 三款 MQ 选型对比

| 维度 | RocketMQ | Kafka | RabbitMQ |
|---|---|---|---|
| 语言 | Java | Scala/Java | Erlang |
| 定位 | **业务消息**（电商、金融交易） | **日志、大数据流**、事件流 | 传统企业集成、复杂路由 |
| 单机吞吐 | 10 万级 | **百万级** | 万级 |
| 延迟 | ms 级 | ms 级（批量换吞吐） | **微秒级** |
| 事务消息 | ✅ 半消息 + 回查 | ✅（Exactly Once 语义，面向流处理，**不是**本地事务与消息的一致性） | ❌（只有 confirm） |
| 延迟消息 | ✅ 4.x 级别 / 5.x 任意 | ❌ | 插件 / 死信 |
| 消息过滤 | Tag / SQL92 | 无（消费端过滤） | Exchange 路由很强 |
| 死信/重试 | ✅ 自带 | 需自己实现 | ✅ |
| 消息查询 | ✅ 按 Key / MsgId | 弱 | 弱 |
| Topic 数量多时 | 稳定（CommitLog 统一存储） | 性能下降（每分区一组文件，随机 IO 增多） | — |
| 生态 | 阿里系、国内业务 | Flink/Spark/ELK 大数据生态 | 多语言客户端 |

选型建议：

- **业务系统（订单、支付、库存）→ RocketMQ**：事务消息、延迟消息、重试死信开箱即用。
- **日志采集、埋点、CDC（Canal/Debezium）、流计算 → Kafka**。
- 很多公司两者并存：业务用 RocketMQ，数据管道用 Kafka。

---

## 4. 原理深挖

### 4.1 RocketMQ 架构

```
                   ┌──────────── NameServer 集群（无状态，彼此不通信）────────────┐
                   │   NS1          NS2          NS3                               │
                   └───▲─────────────▲────────────▲───────────────────────────────┘
          ② 拉取路由    │             │ ① Broker 每 30s 心跳注册 Topic 路由
     ┌─────────────────┘             │
     │                ┌──────────────┴─────────────┐
 Producer ──③ 发送──▶ │ Broker-a Master ──复制──▶ Broker-a Slave │
 Consumer ◀──④ 拉取── │ Broker-b Master ──复制──▶ Broker-b Slave │
                      └────────────────────────────┘
```

| 组件 | 职责 | 设计取舍 |
|---|---|---|
| **NameServer** | 路由注册中心：Topic 在哪些 Broker、哪些 Queue | 刻意做成**无状态、互不通信**，比 ZooKeeper 简单；代价是路由最终一致（客户端 30s 拉一次，Broker 宕机后最多 2 分钟被剔除，期间靠客户端重试和故障规避） |
| **Broker** | 存储、投递消息 | 主从架构；5.x 支持 Controller 模式自动主从切换（DLedger/Raft） |
| **Proxy**（5.x） | 无状态接入层，支持 gRPC | 计算存储分离，适合云原生 |

### 4.2 存储模型：CommitLog + ConsumeQueue + IndexFile

```
所有 Topic 的消息顺序追加写入同一个 CommitLog（单文件 1GB，顺序写）
CommitLog: [T1-m1][T2-m1][T1-m2][T3-m1][T1-m3] ...
              ▲              ▲              ▲
              │ 物理偏移      │              │
ConsumeQueue（每个 Topic 每个 Queue 一个，存「索引」，每条定长 20 字节）
  T1/Queue0: [commitLogOffset(8B) | size(4B) | tagHashCode(8B)] [..] [..]
IndexFile：按 Message Key / 时间建立哈希索引，支持「按订单号查消息」
```

为什么这么设计：

| 设计 | 目的 |
|---|---|
| 所有 Topic **共享一个 CommitLog** | 写入永远是**顺序写**，磁盘吞吐接近内存；Topic 再多也不会退化成随机写（这是相对 Kafka 的优势） |
| ConsumeQueue 只存定长索引 | 体积小，几乎全在 PageCache 中；消费时先读索引再按偏移读 CommitLog |
| 存 tag 的 hashCode | Broker 端按 Tag 过滤，不必读消息体 |
| `mmap` + PageCache | 写入只写到内存映射区，由 OS 刷盘；读取命中 PageCache |
| 读 CommitLog 是随机读 | 代价：消费冷数据（大量堆积后回溯）会产生随机 IO，需要 SSD |

### 4.3 刷盘与主从复制

| 配置 | 行为 | 宕机丢失风险 | 性能 |
|---|---|---|---|
| `ASYNC_FLUSH` | 写 PageCache 即返回，后台线程定时刷盘 | 机器断电丢最近几百 ms 数据（进程崩溃不丢，PageCache 还在） | 高 |
| `SYNC_FLUSH` | 刷盘（GroupCommit 批量 fsync）后才返回 | 不丢 | 降低明显 |
| `ASYNC_MASTER` | 主写成功即返回，异步复制到从 | 主磁盘损坏丢未复制部分 | 高 |
| `SYNC_MASTER` | 至少一个从复制成功才返回 | 不丢 | 中 |

常见生产配置：`ASYNC_FLUSH + SYNC_MASTER`——数据同时存在两台机器的内存中，两台同时断电的概率远低于单台。

### 4.4 消费进度与重试的实现

- 集群模式下，消费进度（offset）存在 **Broker**（`consumerOffset.json`），客户端每 5s 上报一次。广播模式存在**消费者本地**。
- 并发消费时，一批消息里有一条失败，RocketMQ 不会卡住 Queue，而是把失败消息**发回 Broker** 的 `%RETRY%{group}` Topic（本质是延迟消息，级别从 3 开始递增），成功后 offset 才能前移。
- offset 提交的是「**本批次中最小的未完成消息的位置**」。所以实例崩溃会导致已处理的消息被重新消费 → 再次强调幂等。

### 4.5 Kafka 架构

```
               ┌────────── Kafka Cluster（3.x 起用 KRaft 取代 ZooKeeper）──────────┐
               │ Topic: order-events，3 个 Partition，副本因子 3                     │
               │                                                                    │
               │  Broker1             Broker2             Broker3                   │
               │  P0 (Leader)         P0 (Follower)       P0 (Follower)             │
               │  P1 (Follower)       P1 (Leader)         P1 (Follower)             │
               │  P2 (Follower)       P2 (Follower)       P2 (Leader)               │
               └────────────────────────────────────────────────────────────────────┘
  Producer 只写 Leader；Follower 从 Leader 拉取复制；Consumer 默认从 Leader 读
```

| 概念 | 说明 |
|---|---|
| **Partition** | 等价于 RocketMQ 的 Queue，**每个 Partition 是一组独立的日志段文件**（.log + .index + .timeindex） |
| **Replica / Leader / Follower** | 每个 Partition 多副本，Leader 负责读写 |
| **ISR**（In-Sync Replicas） | 与 Leader 保持同步的副本集合；落后超过 `replica.lag.time.max.ms`（默认 30s）被踢出 |
| **HW**（High Watermark） | ISR 中所有副本都已复制到的位置，**消费者只能读到 HW 之前的消息** |
| **LEO**（Log End Offset） | 每个副本自己写到的位置 |
| **offset** | 消费组的进度，提交到内部 Topic `__consumer_offsets` |
| **acks** | `0` 不等确认；`1` Leader 写入即确认；`all` ISR 全部写入才确认 |

Kafka 不丢消息的标准配置：

```properties
# 生产者：所有 ISR 副本确认、开启幂等（单分区内去重，防止重试产生重复）
acks=all
enable.idempotence=true
retries=2147483647
# Topic / Broker：至少 2 个副本同步才允许写入；不允许非 ISR 副本当选 Leader
min.insync.replicas=2
unclean.leader.election.enable=false
# 消费者：关闭自动提交，处理成功后手动提交
enable.auto.commit=false
```

Kafka 为什么快：

| 手段 | 说明 |
|---|---|
| 顺序写 + PageCache | 与 RocketMQ 相同 |
| **零拷贝 sendfile** | 消费时数据从 PageCache 直接到网卡，不经过用户态（RocketMQ 用 mmap，少一次拷贝但不如 sendfile 彻底） |
| 批量 + 压缩 | Producer 攒批（`linger.ms`、`batch.size`）+ lz4/zstd 压缩 |
| 分区并行 | 吞吐随 Partition 线性扩展（直到文件数过多） |

### 4.6 RocketMQ vs Kafka 存储设计取舍

```
Kafka：每个 Partition 独立文件              RocketMQ：所有消息一个 CommitLog
 P0.log ▓▓▓▓                                CommitLog ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
 P1.log ▓▓▓                                 ConsumeQueue 只存索引
 P2.log ▓▓▓▓▓
 ...（分区多了 → 多文件并发写 → 退化为随机写）
```

- Kafka：单分区读写极致，适合「少 Topic、大流量」的数据管道。
- RocketMQ：牺牲一点读性能（多一次索引跳转），换来「**海量 Topic、业务功能丰富**」。这就是为什么业务系统偏好 RocketMQ。

### 4.7 RocketMQ 5.x 的变化

| 变化 | 说明 |
|---|---|
| 任意延迟消息 | TimerWheel 实现，不再受 18 级限制 |
| Proxy + gRPC 客户端 | 新客户端 `rocketmq-client-java`，`SimpleConsumer` 支持按消息粒度 ACK（不再按 Queue 分配） |
| POP 消费 | 消费者不绑定 Queue，解决「实例数 > Queue 数时空闲」与 Rebalance 抖动问题 |
| Controller 自动切主 | 主从切换不再需要人工 |

> 本章 Spring 示例使用 `rocketmq-spring-boot-starter`（基于 4.x Remoting 客户端），可以连接 5.x Broker，并通过 `syncSendDelayTimeSeconds` 使用任意延迟。

---

## 5. mini-mall 实战

### 5.1 本章新增内容一览

| 类型 | 名称 | 层级 | 说明 |
|---|---|---|---|
| 常量 | `MqConstants` | common | Topic、Tag、消费组常量 |
| 消息体 | `OrderCreatedEvent` | model/event | 订单创建事件 |
| 消息体 | `OrderTimeoutCheckEvent` | model/event | 订单超时检查事件（延迟消息） |
| 生产者 | `OrderEventProducer` | ④ 能力单元 `mq/producer` | 封装发送逻辑 |
| 事务监听 | `OrderTxMessageListener` | ④ `mq/producer` | 执行本地事务 + 回查 |
| 消费者 | `OrderCreatedPointsConsumer`、`OrderCreatedNotifyConsumer`、`OrderTimeoutCancelConsumer` | ① 接口层 `mq/consumer` | 与 Controller 同级：只解析消息、调用下层 |
| 功能单元 | `OrderCancelUnit` | ③ domain | 取消订单 + 回补库存（事务） |
| 功能单元 | `PointsGrantUnit` | ③ domain | 写积分流水 + 加积分（事务） |
| 能力单元 | `MqConsumeRecordDao` | ④ dao | 通用消费去重表 |
| 表 | `t_mq_consume_record`、`t_points_log` | — | 去重表、积分流水表 |

> 消费者在五层架构中属于**接口层**：它和 Controller、XXL-Job 一样都是「触发入口」，不写业务逻辑。

### 5.2 依赖与配置

```xml
<!-- pom.xml：rocketmq-spring-boot-starter 2.3.x 支持 Spring Boot 3 -->
<dependency>
    <groupId>org.apache.rocketmq</groupId>
    <artifactId>rocketmq-spring-boot-starter</artifactId>
    <version>2.3.1</version>
</dependency>
```

```yaml
# application.yml
rocketmq:
  name-server: 127.0.0.1:9876
  producer:
    group: mall-order-producer-group
    send-message-timeout: 3000          # 发送超时 3s
    retry-times-when-send-failed: 2     # 同步发送失败重试 2 次（会换 Broker）
    retry-times-when-send-async-failed: 2
    max-message-size: 4194304           # 4MB，消息体不要放大对象
```

### 5.3 常量与消息体

```java
package com.example.mall.common;

/**
 * 消息队列相关常量：Topic、Tag、消费组。
 * 命名约定：topic 以 mall_ 开头，消费组以 -cg 结尾，便于在控制台检索。
 */
public final class MqConstants {

    private MqConstants() {
    }

    /** 订单领域 Topic，所有订单事件共用，按 Tag 区分事件类型 */
    public static final String TOPIC_ORDER = "mall_order_topic";

    /** Tag：订单已创建 */
    public static final String TAG_ORDER_CREATED = "ORDER_CREATED";

    /** Tag：订单超时检查（延迟消息） */
    public static final String TAG_ORDER_TIMEOUT_CHECK = "ORDER_TIMEOUT_CHECK";

    /** 消费组：积分服务 */
    public static final String CG_POINTS = "mall-points-cg";

    /** 消费组：通知服务 */
    public static final String CG_NOTIFY = "mall-notify-cg";

    /** 消费组：订单超时取消 */
    public static final String CG_ORDER_TIMEOUT = "mall-order-timeout-cg";

    /** 未支付订单自动取消的等待时长（秒）：30 分钟 */
    public static final long ORDER_PAY_TIMEOUT_SECONDS = 30 * 60L;
}
```

```java
package com.example.mall.model.event;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 订单创建事件。消息体只放「消费方需要的最小字段」，不放整个 OrderPO：
 * 消费方需要更多信息时按 orderNo 回查，避免消息体与表结构强耦合。
 *
 * @param orderNo     订单号，全局唯一，同时作为消息 Key 用于查询与幂等
 * @param userId      下单用户 ID
 * @param totalAmount 订单总金额
 * @param createTime  下单时间
 */
public record OrderCreatedEvent(String orderNo, Long userId, BigDecimal totalAmount, LocalDateTime createTime) {
}
```

```java
package com.example.mall.model.event;

/**
 * 订单超时检查事件，作为延迟消息在下单 30 分钟后投递。
 *
 * @param orderNo 待检查的订单号
 */
public record OrderTimeoutCheckEvent(String orderNo) {
}
```

TS 对照——消息体就是一个「跨进程的类型契约」：

```ts
// 前端：事件载荷类型
interface OrderCreatedEvent {
  orderNo: string;
  userId: number;
  totalAmount: string;   // 金额在 JSON 里建议用字符串，避免精度丢失
  createTime: string;
}
```

> ⚠️ 消息体是**跨服务、跨版本**的契约：只能**新增字段**，不能改名或删除字段——消费者可能还是老版本。Jackson 反序列化需配置 `FAIL_ON_UNKNOWN_PROPERTIES=false`（Spring Boot 默认已关闭）。

### 5.4 表结构

```sql
-- t_mq_consume_record：通用消费去重表，(consumer_group, msg_key) 唯一保证同一消费组对同一业务消息只处理一次
CREATE TABLE t_mq_consume_record (
    id             BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    consumer_group VARCHAR(64)  NOT NULL COMMENT '消费组',
    msg_key        VARCHAR(64)  NOT NULL COMMENT '业务消息 Key，如订单号',
    create_time    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次消费时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_group_key (consumer_group, msg_key)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = 'MQ 消费去重记录';

-- t_points_log：积分流水表，(order_no, biz_type) 唯一即为积分业务的天然幂等键
CREATE TABLE t_points_log (
    id          BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
    user_id     BIGINT      NOT NULL COMMENT '用户 ID',
    order_no    VARCHAR(32) NOT NULL COMMENT '关联订单号',
    biz_type    TINYINT     NOT NULL COMMENT '业务类型：1 下单赠送 2 取消扣回',
    points      INT         NOT NULL COMMENT '积分变动值，可为负',
    create_time DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_order_biz (order_no, biz_type),
    KEY idx_user_id (user_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '积分流水';
```

> 去重表需要定期清理（如保留 30 天），由 XXL-Job 归档删除（见第 11 章）。

### 5.5 生产者：OrderEventProducer

```java
package com.example.mall.mq.producer;

import com.example.mall.common.MqConstants;
import com.example.mall.model.dto.CreateOrderDTO;
import com.example.mall.model.event.OrderCreatedEvent;
import com.example.mall.model.event.OrderTimeoutCheckEvent;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.rocketmq.client.producer.LocalTransactionState;
import org.apache.rocketmq.client.producer.SendResult;
import org.apache.rocketmq.client.producer.SendStatus;
import org.apache.rocketmq.client.producer.TransactionSendResult;
import org.apache.rocketmq.common.message.MessageConst;
import org.apache.rocketmq.spring.core.RocketMQTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

/**
 * 订单事件生产者（能力单元）：封装订单相关消息的发送细节，上层只关心「发什么事件」。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class OrderEventProducer {

    private final RocketMQTemplate rocketMQTemplate;

    /**
     * 以事务消息方式发送订单创建事件，并在本地事务中完成下单。
     * 半消息发送成功后，框架回调 {@link OrderTxMessageListener#executeLocalTransaction} 执行下单。
     *
     * @param event 订单创建事件（orderNo 需提前生成）
     * @param dto   下单入参，透传给本地事务执行器
     * @return true 表示本地事务已提交（订单写入成功，消息将对消费者可见）
     */
    public boolean sendOrderCreatedInTx(OrderCreatedEvent event, CreateOrderDTO dto) {
        // KEYS 设为订单号：控制台可按订单号查消息，消费端也用它做幂等
        Message<OrderCreatedEvent> message = MessageBuilder.withPayload(event)
                .setHeader(MessageConst.PROPERTY_KEYS, event.orderNo())
                .build();
        String destination = MqConstants.TOPIC_ORDER + ":" + MqConstants.TAG_ORDER_CREATED;
        // 第三个参数是框架定义的 Object 类型「本地事务参数」，这里固定传 CreateOrderDTO
        TransactionSendResult result = rocketMQTemplate.sendMessageInTransaction(destination, message, dto);
        log.info("事务消息发送完成, orderNo={}, sendStatus={}, localState={}",
                event.orderNo(), result.getSendStatus(), result.getLocalTransactionState());
        return result.getLocalTransactionState() == LocalTransactionState.COMMIT_MESSAGE;
    }

    /**
     * 发送订单超时检查的延迟消息。
     * RocketMQ 5.x Broker 支持任意秒级延迟；若 Broker 为 4.x，需改用延迟级别（30 分钟 = level 16）。
     *
     * @param orderNo 订单号
     * @return true 表示 Broker 已确认接收
     */
    public boolean sendOrderTimeoutCheck(String orderNo) {
        String destination = MqConstants.TOPIC_ORDER + ":" + MqConstants.TAG_ORDER_TIMEOUT_CHECK;
        Message<OrderTimeoutCheckEvent> message = MessageBuilder.withPayload(new OrderTimeoutCheckEvent(orderNo))
                .setHeader(MessageConst.PROPERTY_KEYS, orderNo)
                .build();
        // 同步发送 + 检查状态：只有 SEND_OK 才算真正落盘（取决于 Broker 刷盘/复制配置）
        SendResult result = rocketMQTemplate.syncSendDelayTimeSeconds(
                destination, message, MqConstants.ORDER_PAY_TIMEOUT_SECONDS);
        boolean ok = result.getSendStatus() == SendStatus.SEND_OK;
        if (!ok) {
            log.warn("超时检查消息发送状态异常, orderNo={}, status={}", orderNo, result.getSendStatus());
        }
        return ok;
    }
}
```

4.x Broker 的写法对照：

```java
// 4.x：只能选 18 个级别之一，第 4 个参数 delayLevel=16 表示 30 分钟
rocketMQTemplate.syncSend(destination, message, 3000, 16);
```

### 5.6 事务消息监听器：保证「下单成功则消息必达」

```java
package com.example.mall.mq.producer;

import com.example.mall.dao.OrderDao;
import com.example.mall.domain.OrderCreateUnit;
import com.example.mall.model.dto.CreateOrderDTO;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.rocketmq.common.message.MessageConst;
import org.apache.rocketmq.spring.annotation.RocketMQTransactionListener;
import org.apache.rocketmq.spring.core.RocketMQLocalTransactionListener;
import org.apache.rocketmq.spring.core.RocketMQLocalTransactionState;
import org.apache.rocketmq.spring.support.RocketMQHeaders;
import org.springframework.messaging.Message;

/**
 * 订单事务消息监听器：
 * 1) 半消息写入成功后执行本地事务（下单）；
 * 2) Broker 未收到确认时回查订单是否存在，以收敛最终状态。
 * 注意：rocketmq-spring 中一个 RocketMQTemplate 只能绑定一个事务监听器，多种事务消息需自定义多个 Template。
 */
@Slf4j
@RequiredArgsConstructor
@RocketMQTransactionListener
public class OrderTxMessageListener implements RocketMQLocalTransactionListener {

    private final OrderCreateUnit orderCreateUnit;
    private final OrderDao orderDao;

    /**
     * 执行本地事务：写订单、明细、扣库存（OrderCreateUnit 内部带 @Transactional）。
     *
     * @param msg 半消息
     * @param arg 发送时传入的本地事务参数，约定为 CreateOrderDTO
     * @return COMMIT 让消息对消费者可见；ROLLBACK 丢弃半消息；UNKNOWN 交给回查
     */
    @Override
    public RocketMQLocalTransactionState executeLocalTransaction(Message msg, Object arg) {
        String orderNo = getOrderNo(msg);
        try {
            // 本地事务成功提交后才返回 COMMIT
            orderCreateUnit.create(orderNo, (CreateOrderDTO) arg);
            return RocketMQLocalTransactionState.COMMIT;
        } catch (Exception e) {
            // 业务异常（库存不足等）事务已回滚，消息必须丢弃
            log.warn("本地事务失败，回滚半消息, orderNo={}", orderNo, e);
            return RocketMQLocalTransactionState.ROLLBACK;
        }
    }

    /**
     * 事务回查：进程在提交确认前崩溃、或确认请求丢失时，Broker 定时调用。
     * 判断依据必须是「可查询的持久化事实」——订单是否已落库。
     *
     * @param msg 半消息
     * @return 订单存在 → COMMIT；不存在 → ROLLBACK
     */
    @Override
    public RocketMQLocalTransactionState checkLocalTransaction(Message msg) {
        String orderNo = getOrderNo(msg);
        boolean exists = orderDao.existsByOrderNo(orderNo);
        log.info("事务回查, orderNo={}, exists={}", orderNo, exists);
        return exists ? RocketMQLocalTransactionState.COMMIT : RocketMQLocalTransactionState.ROLLBACK;
    }

    /**
     * 从消息头中取出订单号（发送时写在 KEYS 中）。
     *
     * @param msg Spring Message
     * @return 订单号
     */
    private String getOrderNo(Message msg) {
        // rocketmq-spring 会把原生属性加上 "rocketmq_" 前缀放入 header
        Object keys = msg.getHeaders().get(RocketMQHeaders.PREFIX + MessageConst.PROPERTY_KEYS);
        return String.valueOf(keys);
    }
}
```

> 回查时的一个边界：「本地事务还在执行中（慢 SQL），回查已经到来」——此时查不到订单会被误判 ROLLBACK。解决：回查发现不存在时，若消息产生时间未超过阈值（如 5 分钟）则返回 `UNKNOWN` 等下次回查。生产代码建议加上这一判断。

### 5.7 编排层：下单流程

```java
package com.example.mall.biz;

/**
 * 订单编排组件（片段）：下单流程编排。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class OrderBizComponent {

    private final OrderEventProducer orderEventProducer;
    private final OrderDao orderDao;
    private final OrderConverter orderConverter;
    private final OrderNoGenerator orderNoGenerator;

    /**
     * 创建订单：事务消息保证「订单落库」与「订单创建事件」同时成功或同时失败，
     * 随后发送 30 分钟超时检查的延迟消息。
     *
     * @param dto 下单入参
     * @return 订单视图
     */
    public OrderVO createOrder(CreateOrderDTO dto) {
        // 1. 先生成订单号：事务消息与回查都依赖它
        String orderNo = orderNoGenerator.next();
        OrderCreatedEvent event = orderConverter.toCreatedEvent(orderNo, dto);
        // 2. 事务消息：半消息 → 本地事务下单 → 提交
        boolean committed = orderEventProducer.sendOrderCreatedInTx(event, dto);
        if (!committed) {
            throw new BizException(ErrorCode.ORDER_CREATE_FAILED);
        }
        // 3. 发送超时检查延迟消息；失败不影响下单结果，由定时任务扫描超时订单兜底
        sendTimeoutCheckQuietly(orderNo);
        // 4. 查询并返回
        return orderConverter.toVO(orderDao.getByOrderNo(orderNo));
    }

    /**
     * 发送超时检查消息，吞掉异常只打日志：下单已成功，不能因为非核心步骤让用户看到失败。
     *
     * @param orderNo 订单号
     */
    private void sendTimeoutCheckQuietly(String orderNo) {
        try {
            orderEventProducer.sendOrderTimeoutCheck(orderNo);
        } catch (Exception e) {
            // 兜底：依赖 XXL-Job 每 5 分钟扫描 create_time < now-30min 且 status=0 的订单
            log.error("超时检查消息发送失败，等待定时任务兜底, orderNo={}", orderNo, e);
        }
    }
}
```

完整链路：

```
OrderController.create
  → OrderBizComponent.createOrder
      → OrderNoGenerator.next                         生成订单号（07 章的 OrderNoUtil.generate 升级为可注入组件，11 章换成雪花 ID）
      → OrderEventProducer.sendOrderCreatedInTx       ① 发半消息
          → [Broker 存入 HALF Topic]
          → OrderTxMessageListener.executeLocalTransaction
              → OrderCreateUnit.create  @Transactional  写 t_order / t_order_item / 扣 t_product.stock
              ├─ 成功 → COMMIT → 消息对 points-cg / notify-cg 可见
              └─ 异常 → ROLLBACK → 半消息丢弃 → Biz 抛 BizException
      → OrderEventProducer.sendOrderTimeoutCheck      ② 延迟 1800s
          └─ 失败 → 只记日志，定时任务兜底
      → OrderDao.getByOrderNo → OrderConverter.toVO   ③ 返回
```

### 5.8 消费者：积分（业务唯一键幂等）

```java
package com.example.mall.mq.consumer;

import com.example.mall.common.MqConstants;
import com.example.mall.domain.PointsGrantUnit;
import com.example.mall.model.event.OrderCreatedEvent;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.rocketmq.spring.annotation.RocketMQMessageListener;
import org.apache.rocketmq.spring.core.RocketMQListener;
import org.springframework.stereotype.Component;

/**
 * 订单创建 → 赠送积分 消费者（接口层）：只做日志和调用，不写业务。
 * 抛出异常即视为消费失败，RocketMQ 会按退避策略重试，16 次后进入死信队列。
 */
@Slf4j
@Component
@RequiredArgsConstructor
@RocketMQMessageListener(
        topic = MqConstants.TOPIC_ORDER,
        selectorExpression = MqConstants.TAG_ORDER_CREATED,   // 只订阅 ORDER_CREATED，Broker 端按 Tag 过滤
        consumerGroup = MqConstants.CG_POINTS)
public class OrderCreatedPointsConsumer implements RocketMQListener<OrderCreatedEvent> {

    private final PointsGrantUnit pointsGrantUnit;

    /**
     * 处理订单创建事件，按订单金额赠送积分。
     *
     * @param event 订单创建事件
     */
    @Override
    public void onMessage(OrderCreatedEvent event) {
        log.info("收到订单创建事件(积分), orderNo={}", event.orderNo());
        pointsGrantUnit.grantForOrder(event);
    }
}
```

```java
package com.example.mall.domain;

/**
 * 积分发放功能单元：写积分流水 + 增加用户积分，两张表在同一事务中。
 * 幂等依赖 t_points_log 的唯一键 uk_order_biz(order_no, biz_type)。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class PointsGrantUnit {

    /** 积分业务类型：下单赠送 */
    private static final int BIZ_TYPE_ORDER_GRANT = 1;

    private final PointsLogDao pointsLogDao;
    private final UserPointsDao userPointsDao;

    /**
     * 为订单发放积分（幂等）：每消费 1 元赠送 1 积分，向下取整。
     *
     * @param event 订单创建事件
     */
    @Transactional(rollbackFor = Exception.class)
    public void grantForOrder(OrderCreatedEvent event) {
        int points = event.totalAmount().intValue();
        // 1. 先插流水：唯一键冲突说明已处理过，直接返回（重复消息被吸收）
        boolean inserted = pointsLogDao.insertIgnoreDuplicate(
                event.userId(), event.orderNo(), BIZ_TYPE_ORDER_GRANT, points);
        if (!inserted) {
            log.info("积分已发放，忽略重复消息, orderNo={}", event.orderNo());
            return;
        }
        // 2. 再加积分：与流水同事务，任一失败整体回滚，消息重试时可重新处理
        userPointsDao.increase(event.userId(), points);
    }
}
```

```java
/**
 * 插入积分流水，唯一键冲突时返回 false 而不是抛异常。
 *
 * @param userId  用户 ID
 * @param orderNo 订单号
 * @param bizType 业务类型
 * @param points  积分值
 * @return true 插入成功；false 已存在
 */
public boolean insertIgnoreDuplicate(Long userId, String orderNo, int bizType, int points) {
    PointsLogPO po = new PointsLogPO();
    po.setUserId(userId);
    po.setOrderNo(orderNo);
    po.setBizType(bizType);
    po.setPoints(points);
    try {
        return pointsLogMapper.insert(po) == 1;
    } catch (DuplicateKeyException e) {
        // Spring 把 MySQL 1062 错误翻译为 DuplicateKeyException
        return false;
    }
}
```

> 为什么「先插流水、再加积分」且放在同一事务：如果先加积分再插流水，重复消息并发到达时两个线程都会先加积分。**用唯一索引把并发冲突交给数据库裁决**，是最简单可靠的幂等手段。
> ⚠️ 唯一键冲突在 InnoDB 中会使当前事务**持有该记录的锁**直到事务结束，但不影响正确性。

### 5.9 消费者：通知（通用去重表）

短信没有天然的业务表可加唯一键，用通用去重表：

```java
/**
 * 订单创建 → 发送下单通知 消费者。
 */
@Slf4j
@Component
@RequiredArgsConstructor
@RocketMQMessageListener(
        topic = MqConstants.TOPIC_ORDER,
        selectorExpression = MqConstants.TAG_ORDER_CREATED,
        consumerGroup = MqConstants.CG_NOTIFY)
public class OrderCreatedNotifyConsumer implements RocketMQListener<OrderCreatedEvent> {

    private final MqConsumeRecordDao mqConsumeRecordDao;
    private final SmsClient smsClient;

    /**
     * 发送下单成功短信，按 (消费组, 订单号) 去重。
     *
     * @param event 订单创建事件
     */
    @Override
    public void onMessage(OrderCreatedEvent event) {
        // 1. 抢占去重记录：抢不到说明已处理
        if (!mqConsumeRecordDao.tryInsert(MqConstants.CG_NOTIFY, event.orderNo())) {
            log.info("通知已发送，忽略重复消息, orderNo={}", event.orderNo());
            return;
        }
        try {
            // 2. 调用三方短信
            smsClient.sendOrderCreated(event.userId(), event.orderNo());
        } catch (Exception e) {
            // 3. 失败时删除去重记录，让 MQ 重试能再次进入
            mqConsumeRecordDao.delete(MqConstants.CG_NOTIFY, event.orderNo());
            throw e;
        }
    }
}
```

这里有一个**无法在本地事务内解决**的窗口：短信已发出、删除/提交前进程崩溃 → 用户可能收到两条短信。对外部副作用，完全的 Exactly Once 做不到，只能**缩小窗口**，或依赖下游接口自身的幂等（传 requestId 给短信平台）。这是分布式系统的基本事实。

去重的三种写法对照：

```
               ┌──────────── 去重记录与业务在同一个库同一事务 ────────────┐
 积分（5.8）   │ INSERT 流水(唯一键) + UPDATE 积分 → 原子，最可靠           │
               └──────────────────────────────────────────────────────────┘
 通知（5.9）     INSERT 去重表 → 调外部接口 → 失败则 DELETE  → 有极小窗口
 Redis SETNX     SET k NX EX → 业务 → 失败则 DEL            → 窗口更大（Redis 与 DB 非原子）
```

### 5.10 消费者：30 分钟未支付自动取消（状态机幂等）

```java
/**
 * 订单超时检查消费者：延迟消息到达时，若订单仍为待支付则取消并回补库存。
 */
@Slf4j
@Component
@RequiredArgsConstructor
@RocketMQMessageListener(
        topic = MqConstants.TOPIC_ORDER,
        selectorExpression = MqConstants.TAG_ORDER_TIMEOUT_CHECK,
        consumerGroup = MqConstants.CG_ORDER_TIMEOUT)
public class OrderTimeoutCancelConsumer implements RocketMQListener<OrderTimeoutCheckEvent> {

    private final OrderCancelUnit orderCancelUnit;

    /**
     * 处理超时检查事件。
     *
     * @param event 超时检查事件
     */
    @Override
    public void onMessage(OrderTimeoutCheckEvent event) {
        boolean cancelled = orderCancelUnit.cancelIfUnpaid(event.orderNo());
        log.info("订单超时检查完成, orderNo={}, cancelled={}", event.orderNo(), cancelled);
    }
}
```

```java
package com.example.mall.domain;

/**
 * 订单取消功能单元：修改订单状态 + 回补库存，跨 t_order / t_order_item / t_product 三张表，必须同事务。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class OrderCancelUnit {

    private final OrderDao orderDao;
    private final OrderItemDao orderItemDao;
    private final ProductDao productDao;

    /**
     * 仅当订单处于 CREATED(0) 时取消并回补库存；已支付/已取消的订单不做任何事（幂等）。
     *
     * @param orderNo 订单号
     * @return true 本次调用完成了取消；false 订单状态不允许取消或订单不存在
     */
    @Transactional(rollbackFor = Exception.class)
    public boolean cancelIfUnpaid(String orderNo) {
        OrderPO order = orderDao.getByOrderNo(orderNo);
        if (order == null) {
            return false;
        }
        // 1. 状态机 CAS：UPDATE t_order SET status=2 WHERE order_no=? AND status=0
        //    影响行数为 0 说明已被支付或已被取消，这正是重复消息/并发支付的「裁决点」
        int rows = orderDao.updateStatus(orderNo, OrderStatusEnum.CREATED, OrderStatusEnum.CANCELLED);
        if (rows == 0) {
            return false;
        }
        // 2. 状态更新成功才回补库存：保证库存只回补一次
        List<OrderItemPO> items = orderItemDao.listByOrderId(order.getId());
        for (OrderItemPO item : items) {
            productDao.restoreStock(item.getProductId(), item.getQuantity());
        }
        return true;
    }
}
```

```java
/**
 * 条件更新订单状态（状态机 CAS）。
 *
 * @param orderNo 订单号
 * @param from    期望的当前状态
 * @param to      目标状态
 * @return 影响行数：1 成功，0 当前状态不是 from
 */
public int updateStatus(String orderNo, OrderStatusEnum from, OrderStatusEnum to) {
    return orderMapper.update(null, Wrappers.<OrderPO>lambdaUpdate()
            .set(OrderPO::getStatus, to.getCode())
            .eq(OrderPO::getOrderNo, orderNo)
            .eq(OrderPO::getStatus, from.getCode()));
}
```

**并发场景推演：用户在第 29 分 59 秒支付，同时超时消息到达**

```
支付回调线程                                   超时取消线程
UPDATE status=1 WHERE no=X AND status=0       UPDATE status=2 WHERE no=X AND status=0
          └────── InnoDB 行锁串行化：只有一个能把 status 从 0 改掉 ──────┘
支付先到：rows=1，订单已支付                    rows=0 → 不取消、不回补库存 ✅
取消先到：rows=0 → 支付失败，走退款流程        rows=1，取消 + 回补库存 ✅
```

> 状态机天然幂等：**同一条消息消费 100 次，只有第一次能让 `status=0 → 2` 成立**。这比去重表更轻，是订单类场景的首选。

### 5.11 顺序消息示例（订单状态变更同步给数据仓库）

```java
/**
 * 按订单号哈希发送顺序消息：同一订单的状态变更进入同一个 Queue。
 *
 * @param orderNo 订单号，作为 hashKey
 * @param status  变更后的状态
 */
public void sendStatusChangedOrderly(String orderNo, OrderStatusEnum status) {
    String destination = MqConstants.TOPIC_ORDER + ":ORDER_STATUS_CHANGED";
    OrderStatusChangedEvent event = new OrderStatusChangedEvent(orderNo, status.getCode());
    rocketMQTemplate.syncSendOrderly(destination, event, orderNo);
}
```

```java
@RocketMQMessageListener(
        topic = MqConstants.TOPIC_ORDER,
        selectorExpression = "ORDER_STATUS_CHANGED",
        consumerGroup = "mall-dw-sync-cg",
        consumeMode = ConsumeMode.ORDERLY)   // 顺序消费：每个 Queue 同时只有一个线程处理
public class OrderStatusSyncConsumer implements RocketMQListener<OrderStatusChangedEvent> {
    // ... 失败抛异常时会在本 Queue 原地重试，阻塞后续消息，务必设置监控
}
```

---

## 6. 常见坑

| # | 坑 | 后果 | 正确做法 |
|---|---|---|---|
| 1 | 在 `@Transactional` 方法**内部**发普通消息 | 消息已发出，事务回滚 → 消费者查不到订单；或消费者比事务提交还快 → 查不到数据 | 用事务消息、本地消息表，或 `TransactionSynchronization.afterCommit` 中发送 |
| 2 | Listener 里 `catch (Exception e) { log.error(...) }` | 异常被吞，框架认为消费成功，消息丢失 | 处理失败必须抛出异常 |
| 3 | 认为「MQ 不会重复」 | 积分加两次、短信发两次 | 所有消费者都按幂等设计 |
| 4 | 用 Redis SETNX 做核心业务幂等 | Redis 标记成功但业务失败 → 消息被误跳过 | 核心业务用 DB 唯一键 / 状态机 |
| 5 | 不同业务共用一个消费组 | 组内订阅关系不一致，消息被「分错」实例而丢失 | **一个消费组 = 一套订阅关系**，组名不复用 |
| 6 | 消费实例数 > Queue 数还继续扩容 | 多余实例空闲，堆积不缓解 | 先扩 Queue 数；或用 5.x POP 消费 |
| 7 | 消息体放整个大对象（含图片 base64） | 超 4MB 发送失败；存储与网络开销大 | 只放 ID + 必要字段，消费方回查 |
| 8 | 延迟消息当成精确定时器 | 4.x 只能选级别；Broker 繁忙时会延后 | 延迟消息 + 状态校验 + 定时扫描兜底 |
| 9 | 消费者中做耗时远程调用且未设超时 | 消费线程全部卡住 → 堆积 | 下游调用必须设超时；必要时拆成两段消息 |
| 10 | 消费端修改消息体字段名 | 老版本生产者的消息反序列化失败，全部进死信 | 消息体只增不改，双方灰度兼容 |
| 11 | 顺序消息消费失败一直重试 | 整个 Queue 阻塞 | 设置 `maxReconsumeTimes`，超限记录并跳过，人工处理 |
| 12 | 把 Kafka 自动提交 offset 当成「处理成功才提交」 | 处理中崩溃 → 消息丢失 | `enable.auto.commit=false`，处理后手动提交 |

---

## 7. 高级视角

### 7.1 「发消息」的三种一致性方案

| 方案 | 原理 | 依赖 | 优点 | 缺点 |
|---|---|---|---|---|
| **RocketMQ 事务消息** | 半消息 + 本地事务 + 回查 | 仅 RocketMQ | 不需要额外表 | 绑定 RocketMQ；一个 Template 一个监听器；回查逻辑要能查 |
| **本地消息表** | 业务与「待发消息」写同一个库同一事务，异步投递 + 定时重扫 | 任何 MQ | 通用、可审计、可人工重发 | 多一张表、多一个投递任务 |
| **CDC（Canal/Debezium 订阅 binlog）** | 业务只写库，由 binlog 生成事件 | Canal + Kafka | 业务零侵入 | 架构重；事件语义是「表变更」不是「业务事件」 |

第 11 章微服务场景将用**本地消息表**实现，对比两种方案的取舍。

### 7.2 消息语义

| 语义 | 含义 | 实现 |
|---|---|---|
| At Most Once | 最多一次，可能丢 | 先 ACK 后处理 / 单向发送 |
| **At Least Once** | 至少一次，可能重 | 处理后 ACK + 重试（业务主流） |
| Exactly Once | 恰好一次 | 端到端几乎做不到；工程上 = **At Least Once + 消费幂等** |

> Kafka 的 Exactly Once 指「Kafka 读 → 处理 → 写回 Kafka」这一闭环内的事务，**一旦涉及外部数据库或接口就不成立**。

### 7.3 MQ 的设计原则

1. **消息是事实，不是命令**：`OrderCreated`（发生了什么）优于 `AddPoints`（让你做什么）。前者生产者不依赖消费者，后者又耦合回去了。
2. **Topic 按领域划分，Tag 按事件类型划分**：`mall_order_topic` + `ORDER_CREATED / ORDER_PAID / ORDER_CANCELLED`。
3. **消息体自包含但最小化**：包含消费者大概率用到的字段，避免所有消费者都回查造成「回查风暴」。
4. **消费者对乱序有韧性**：用状态机/版本号判断「这条消息是否过时」，而不是一律依赖顺序消息。
5. **可观测**：每条消息带 traceId（放在 UserProperty），消费日志打印 msgId + key，死信必告警，消费延迟设阈值告警。

### 7.4 容量与参数心算

- Queue 数 = 预期最大消费实例数 × 1~2，建议 8/16。Kafka Partition 同理，但单集群总分区数要控制。
- 消费 TPS ≈ 实例数 × 消费线程数 × (1000 / 单条耗时 ms)。例：4 实例 × 20 线程 × (1000/50) = 1600 TPS。
- 重试间隔默认递增到 2 小时，**总重试窗口约 4 小时 46 分**：下游故障 5 小时以上必然产生死信，预案要覆盖。

### 7.5 何时不该用 MQ

- 调用方必须立刻拿到结果（扣库存是否成功）→ 同步 RPC。
- 只是同进程内的模块解耦 → Spring `ApplicationEvent` 即可（`@TransactionalEventListener(phase = AFTER_COMMIT)` 还能保证事务提交后触发），不必引入中间件。
- 数据量小、实时性要求低 → 定时任务扫表可能更简单。

---

## 8. 小练习

1. **对比实验**：用 docker-compose（见第 12 章）起一个 RocketMQ，分别用两个不同消费组和同一消费组的两个实例订阅 `mall_order_topic`，观察「组间广播、组内分摊」。
2. **重复消费复现**：在 `OrderCreatedPointsConsumer.onMessage` 末尾故意 `throw new RuntimeException()`，观察重试次数与间隔；再验证 `t_points_log` 唯一键能否挡住重复加积分。
3. **事务回查**：在 `executeLocalTransaction` 中 `return UNKNOWN`，观察约 1 分钟后 `checkLocalTransaction` 被调用；实现「本地事务执行中」的 `UNKNOWN` 判断（提示：消息头里有 `BORN_TIMESTAMP`）。
4. **并发裁决**：写一个单测，用两个线程同时对同一 `CREATED` 订单执行「支付」与 `cancelIfUnpaid`，断言最终只有一个成功、库存只回补一次。
5. **兜底任务**：实现超时订单扫描（`status=0 AND create_time < NOW() - INTERVAL 30 MINUTE`，分页、按 id 游标），复用 `OrderCancelUnit.cancelIfUnpaid`，思考它与延迟消息同时执行时为何不会出问题。
6. **思考题**：如果积分服务宕机 6 小时，会发生什么？恢复后如何把死信重新处理？画出你的处理流程。
