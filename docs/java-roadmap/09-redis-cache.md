> [← 总纲](./00-outline.md) | [上一章：数据库与持久层](./08-database-orm.md) | [下一章：消息队列](./10-message-queue.md)

# 09 Redis 与缓存：数据结构、缓存三大问题、一致性、分布式锁

---

## 1. 本章地图

第 08 章把「我的订单」优化到了毫秒级，但商品详情页这种**读多写少、所有人都在看同一份数据**的场景，每次都查 MySQL 仍然是浪费；秒杀时成千上万的请求更新同一行库存，行锁排队会直接把数据库拖垮。Redis 就是放在应用与数据库之间的「高速层」。

```
① Controller → ② OrderBizComponent / ProductBizComponent
                     │
       ┌─────────────┼───────────────────────────┐
       ▼             ▼                           ▼
 ProductCacheService  StockPreDeductService   Redisson 锁（防重复下单）   ← 本章
 （旁路缓存）          （Lua 预扣库存）
       │             │                           │
       ▼             ▼                           ▼
              Redis（单机 / 哨兵 / Cluster）
       │ 未命中 / 落库
       ▼
 ProductDao / OrderCreateUnit → MySQL（第 08 章）
```

| 问题 | 小节 |
|---|---|
| Redis 为什么快？单线程为什么够用？ | 3.2 |
| 五种数据结构底层是什么？各用在哪？ | 3.3 / 4.1 |
| 数据过期了怎么删？内存满了删谁？ | 4.2 |
| 宕机了数据还在吗？ | 4.3 |
| 主从、哨兵、Cluster 有什么区别？ | 4.4 |
| Java 里怎么用？序列化有什么坑？ | 3.4 |
| 缓存和数据库怎么保持一致？ | 4.5 |
| 穿透、击穿、雪崩怎么防？ | 4.6 |
| 分布式锁怎么写才对？ | 4.8 |
| mini-mall：商品缓存、预扣库存、防重复下单、改价一致性 | 5 |

---

## 2. 前端类比

### 2.1 为什么需要缓存

前端你已经天天在用缓存，只是没叫它这个名字：

| 前端缓存 | 位置 | 失效方式 | 对应的服务端概念 |
|---|---|---|---|
| HTTP 强缓存 `Cache-Control: max-age` | 浏览器 | 到期失效 | TTL 过期 |
| 协商缓存 `ETag / 304` | 浏览器 ↔ 服务器 | 每次询问是否变化 | 版本号校验 |
| `localStorage` | 单个浏览器 | 手动删除 | 本地缓存（Caffeine），**只属于一个进程** |
| SWR / React Query `stale-while-revalidate` | 内存 | 先返回旧值、后台刷新 | **逻辑过期**（4.6.2） |
| CDN | 边缘节点 | 主动刷新 / TTL | 多级缓存的最外层 |

服务端缓存和前端缓存的根本区别：

| 维度 | 前端缓存 | Redis |
|---|---|---|
| 共享范围 | 一个用户自己 | **所有实例、所有用户共享** |
| 一致性要求 | 旧一点无所谓，刷新就好 | 价格、库存错了就是资损 |
| 并发 | 单线程、无竞争 | 成千上万请求同时读写同一个 key |
| 故障影响 | 一个用户页面不对 | 缓存挂了，流量全部打到 DB → 雪崩 |

### 2.2 Redis 本身的类比

| 前端 | Redis |
|---|---|
| 一个巨大的全局 `Map<string, any>` | Redis 的 key-value 空间 |
| `Map` / `Set` / `Array` | Hash / Set / List |
| 带分数的排行榜 `arr.sort((a,b)=>b.score-a.score)` | ZSet（有序集合） |
| Node 事件循环：单线程 + epoll | Redis：单线程执行命令 + IO 多路复用 |
| 不会被打断的同步代码块 | Lua 脚本：整段原子执行 |

---

## 3. 核心概念

### 3.1 快速上手

```bash
SET product:1 '{"id":1,"name":"键盘","price":"199.00"}' EX 1800   # 设置并 30 分钟过期
GET product:1
TTL product:1                      # 剩余秒数
SET lock:order:1001 abc NX EX 10   # 不存在才设置（分布式锁基础）
INCR stat:pv                       # 原子自增
HSET user:1001 name alice phone 138xxxx
ZADD rank:sales 520 product:1 300 product:2
ZREVRANGE rank:sales 0 9 WITHSCORES   # 销量 Top10
```

**key 命名规范**：`业务:对象:id`，用冒号分层（客户端工具会按冒号展示成树）。如 `mall:product:detail:1`。一律设置 TTL，除非你能说清它为什么必须永久存在。

### 3.2 Redis 为什么快

| 原因 | 说明 |
|---|---|
| 纯内存 | 内存访问约 100ns，SSD 随机读约 100µs，差 1000 倍 |
| 高效数据结构 | SDS、listpack、skiplist、哈希表渐进式 rehash 等，针对场景精心设计（4.1） |
| 单线程执行命令 | 无锁、无线程切换；瓶颈在内存和网络，不在 CPU |
| IO 多路复用 | 一个线程用 epoll 同时监听上万连接 |

**单线程 + IO 多路复用，和 Node 事件循环是同一个模型**：

```
         Node.js                                 Redis（6.0 之前）
  ┌─────────────────────┐               ┌──────────────────────────┐
  │ libuv epoll 等待事件  │               │ ae 事件库 epoll 等待事件 │
  │       ▼               │               │       ▼                  │
  │ 主线程执行 JS 回调     │               │ 主线程：读请求 → 解析命令 │
  │（长任务会卡住全部请求）│               │ → 执行 → 写回响应         │
  └─────────────────────┘               │（慢命令会卡住全部请求）  │
                                          └──────────────────────────┘
```

推论和 Node 一样：**任何慢命令都会阻塞所有客户端**。`KEYS *`、对百万元素的集合 `SMEMBERS`/`HGETALL`、`DEL` 一个超大 key，都相当于在 Node 主线程里跑了一个 10 秒的同步循环。

**Redis 6.0 多线程 IO**：网络读写和协议解析交给多个 IO 线程，**命令执行仍是单线程**，所以原子性不变。类比 Node 把文件 IO 交给 libuv 线程池，但 JS 依旧单线程。

```
IO 线程1 ┐ 读 socket、解析协议
IO 线程2 ┼──▶ 主线程串行执行命令 ──▶ IO 线程们并行写回响应
IO 线程3 ┘
```

> Redis 也并非严格单线程：持久化 fork 子进程，`UNLINK`、`FLUSHALL ASYNC` 的惰性释放有后台线程（bio）。

### 3.3 五大数据结构与业务场景

| 类型 | 类比 | 典型命令 | 业务场景 |
|---|---|---|---|
| String | `Map<string, string>` | `SET/GET/INCR/SETNX` | 对象缓存（JSON）、计数器、分布式锁、库存数 |
| Hash | 嵌套对象 `{field: value}` | `HSET/HGET/HINCRBY` | 对象部分字段更新（购物车：`cart:uid` → `productId: 数量`） |
| List | 数组（两端操作） | `LPUSH/RPOP/LRANGE` | 最新消息列表、简单队列（不推荐作可靠 MQ） |
| Set | `Set` | `SADD/SISMEMBER/SINTER` | 去重、共同关注、抽奖、「已下单用户集合」 |
| ZSet | 按 score 排序的 Set | `ZADD/ZRANGE/ZINCRBY` | 排行榜、延迟队列（score 为时间戳）、滑动窗口限流 |

扩展类型：

| 类型 | 原理 | 场景 |
|---|---|---|
| Bitmap | 基于 String 的位数组 | 签到（`user:sign:1001:202611` 第 n 位表示第 n 天）、活跃用户统计，1 亿用户约 12MB |
| HyperLogLog | 概率算法，固定 12KB，误差约 0.81% | UV 统计（只要基数、不要明细） |
| GEO | 基于 ZSet，经纬度编码为 GeoHash 作 score | 附近的门店 |
| Stream | 类 Kafka 的日志结构，支持消费组、ACK | 轻量消息队列；正经业务仍用 RocketMQ（第 10 章） |

### 3.4 Java 客户端

#### 3.4.1 客户端选型

| 客户端 | 特点 | 定位 |
|---|---|---|
| Jedis | 同步阻塞，连接非线程安全，需要连接池 | 老牌、简单 |
| Lettuce | 基于 Netty 异步非阻塞，一个连接可被多线程共享 | **Spring Boot 默认** |
| Redisson | 在 Redis 上实现分布式锁、限流器、布隆过滤器、分布式集合等 | 用于「分布式工具」，通常与 Lettuce 并存 |

#### 3.4.2 Spring Data Redis：RedisTemplate 与 StringRedisTemplate

```ts
// Node：ioredis
await redis.set('mall:product:detail:1', JSON.stringify(product), 'EX', 1800);
const cached = await redis.get('mall:product:detail:1');
const product = cached ? JSON.parse(cached) : null;
```

```java
// Java：StringRedisTemplate + 显式 JSON 序列化（推荐）
stringRedisTemplate.opsForValue().set("mall:product:detail:1",
        objectMapper.writeValueAsString(product), Duration.ofMinutes(30));
String cached = stringRedisTemplate.opsForValue().get("mall:product:detail:1");
ProductPO product = cached == null ? null : objectMapper.readValue(cached, ProductPO.class);
```

**序列化配置坑**：`RedisTemplate<Object, Object>` 默认用 `JdkSerializationRedisSerializer`，存进去的 key 长这样：

```
"\xac\xed\x00\x05t\x00\x15mall:product:detail:1"
```

后果：redis-cli 里查不到、其他语言读不了、类改了包名就反序列化失败、体积大。

| 方案 | 说明 |
|---|---|
| **`StringRedisTemplate` + 手动 JSON**（mini-mall 采用） | key、value 都是字符串，最透明；类型由调用方 `readValue` 指定 |
| `RedisTemplate<String, T>` + `GenericJackson2JsonRedisSerializer` | 自动 JSON，但会在 JSON 里写入 `@class` 类名，跨服务、重构时易出问题 |
| `Jackson2JsonRedisSerializer<T>` 指定类型 | 一个 Template 只服务一个类型 |

若一定要自定义 `RedisTemplate`：

```java
package com.example.mall.config;

/**
 * Redis 配置：key 用字符串序列化，value 用 JSON 序列化。
 */
@Configuration
public class RedisConfig {

    /**
     * 自定义 RedisTemplate，替换默认的 JDK 序列化。
     *
     * @param factory Spring Boot 自动配置的 Lettuce 连接工厂
     * @return key 为 String、value 为 JSON 的 RedisTemplate
     */
    @Bean
    public RedisTemplate<String, ProductPO> productRedisTemplate(RedisConnectionFactory factory) {
        RedisTemplate<String, ProductPO> template = new RedisTemplate<>();
        template.setConnectionFactory(factory);
        // key 与 hash field 使用纯字符串
        template.setKeySerializer(RedisSerializer.string());
        template.setHashKeySerializer(RedisSerializer.string());
        // value 指定具体类型的 JSON 序列化，不在数据中写类名
        Jackson2JsonRedisSerializer<ProductPO> valueSerializer =
                new Jackson2JsonRedisSerializer<>(buildObjectMapper(), ProductPO.class);
        template.setValueSerializer(valueSerializer);
        template.setHashValueSerializer(valueSerializer);
        template.afterPropertiesSet();
        return template;
    }

    /**
     * 构建支持 Java 8 时间类型的 ObjectMapper。
     *
     * @return 配置好的 ObjectMapper
     */
    private ObjectMapper buildObjectMapper() {
        ObjectMapper mapper = new ObjectMapper();
        // 注册 JavaTimeModule，否则 LocalDateTime 序列化报错
        mapper.registerModule(new JavaTimeModule());
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        return mapper;
    }
}
```

另两个常见坑：

- **LocalDateTime 序列化报错**：ObjectMapper 要注册 `JavaTimeModule`（Spring 注入的 ObjectMapper 已注册，自己 `new` 的没有）；
- **BigDecimal 精度**：JSON 中写成字符串更安全（前端 JS 解析大数也会丢精度，你应该深有体会）。

配置：

```yaml
spring:
  data:
    redis:
      host: 127.0.0.1
      port: 6379
      password: ${REDIS_PASSWORD}
      timeout: 1000ms          # 命令超时，缓存就该快速失败
      lettuce:
        pool:                  # 需引入 commons-pool2 才生效
          max-active: 32
          max-idle: 16
          min-idle: 4
```

---

## 4. 原理深挖

### 4.1 底层编码

Redis 对外是 5 种类型，对内每种类型有多种编码，**小数据用紧凑编码省内存，大数据切换为高效查找的编码**。`OBJECT ENCODING key` 可查看。

| 类型 | 小数据编码 | 大数据编码 | 切换阈值（7.x 默认） |
|---|---|---|---|
| String | `int`（整数）/ `embstr`（≤44 字节） | `raw` | 长度 > 44 字节 |
| List | `listpack` | `quicklist` | 元素数 > 128 或单元素 > 64 字节 |
| Hash | `listpack` | `hashtable` | 字段数 > 128 或值 > 64 字节 |
| Set | `intset`（全整数）/ `listpack`（7.2+） | `hashtable` | 元素数 > 512（intset）/ 128（listpack） |
| ZSet | `listpack` | `skiplist` + `hashtable` | 元素数 > 128 或成员 > 64 字节 |

> 7.0 之前小数据编码是 `ziplist`。ziplist 每个节点记录「前一节点长度」，插入可能引发**连锁更新**；listpack 改为每个节点只记录自身长度，彻底消除该问题。

#### 4.1.1 SDS（简单动态字符串）

```
struct sdshdr8 {
    uint8_t len;     // 已用长度 → STRLEN 是 O(1)
    uint8_t alloc;   // 已分配容量 → 追加时预分配，减少 realloc
    char flags;      // 类型：sdshdr5/8/16/32/64，按长度选最小头部
    char buf[];      // 内容，结尾仍保留 '\0' 以兼容 C 函数
};
```

| 对比 C 字符串 | SDS |
|---|---|
| 求长度 O(n) | O(1) |
| `\0` 结尾，不能存二进制 | 按 len 判断结尾，**二进制安全**（可存图片、序列化数据） |
| 拼接可能缓冲区溢出 | 自动扩容；< 1MB 时翻倍预分配，≥ 1MB 每次多给 1MB |

类比 JS 的 `ArrayBuffer` 带 `byteLength`，而不是靠终止符。

#### 4.1.2 listpack 与 quicklist

```
listpack（一块连续内存）：
┌──────────┬───────────┬──────────────────────┬──────────────────────┬─────┬──────┐
│ 总字节数 │ 元素个数  │ entry1(编码|数据|长度)│ entry2(编码|数据|长度)│ ... │ 0xFF │
└──────────┴───────────┴──────────────────────┴──────────────────────┴─────┴──────┘
  连续内存 → CPU 缓存友好、无指针开销；但查找 O(n)、插入要 memmove，所以只用于小数据

quicklist（List 的大数据编码）= 双向链表，每个节点是一个 listpack：
  [listpack] ⇄ [listpack] ⇄ [listpack] ⇄ ...
  兼顾：链表两端 O(1) 增删 + 节点内紧凑存储；中间节点还可 LZF 压缩
```

#### 4.1.3 skiplist（跳表）

ZSet 需要同时支持：按 member 查 score（O(1)）、按 score 范围查询和排名（O(log n)）。所以大 ZSet 是**哈希表 + 跳表**两个结构。

```
level 3:  head ───────────────────────────────▶ 50 ─────────────────────▶ NULL
level 2:  head ──────────▶ 20 ────────────────▶ 50 ──────────▶ 80 ──────▶ NULL
level 1:  head ──▶ 10 ──▶ 20 ──▶ 30 ──▶ 40 ──▶ 50 ──▶ 60 ──▶ 80 ──▶ 90 ▶ NULL
                                                                     (底层双向，支持逆序)
查找 60：从最高层走，下一个大于目标就下降一层 → 平均 O(log n)
每个节点的层数随机：每升一层概率 1/4，最高 32 层
```

为什么用跳表而不是红黑树 / B+ 树？

| 维度 | 跳表 | 红黑树 | B+ 树 |
|---|---|---|---|
| 范围查询 | 找到起点后沿底层链表走 | 需要中序遍历 | 好，但为磁盘页设计 |
| 实现复杂度 | 简单（作者原话：易实现、易调试） | 旋转、染色复杂 | 复杂 |
| 内存 | 平均每节点 1.33 个指针，可调 | 每节点 2 指针 + 颜色 | 内存场景无优势 |
| 排名 `ZRANK` | 每层指针记录跨度 span，累加即排名 | 需额外维护子树大小 | — |

#### 4.1.4 哈希表与渐进式 rehash

Redis 的全局 key 空间和 Hash 大数据编码都是哈希表（链地址法）。扩容时不是一次性搬完（那会阻塞所有请求），而是**两张表并存，每次读写顺带迁移一个桶**，定时任务也会分批迁移。思路就是前端的「时间切片」（React Fiber 把大任务拆小，避免卡主线程）。

### 4.2 过期策略与内存淘汰

**过期删除**：Redis 把带 TTL 的 key 记在 expires 字典里，用两种策略配合：

| 策略 | 方式 | 优缺点 |
|---|---|---|
| 惰性删除 | 访问 key 时检查是否过期，过期则删 | 省 CPU；但不访问的过期 key 一直占内存 |
| 定期删除 | 每秒 10 次（hz=10）随机抽样 20 个带 TTL 的 key，删过期的；过期比例 > 25% 就继续抽，且有时间上限 | 折中 |

两者都漏掉的 key，靠内存淘汰兜底。

**内存淘汰**（`maxmemory-policy`，达到 `maxmemory` 时触发）：

| 策略 | 范围 | 算法 |
|---|---|---|
| noeviction（默认） | — | 不淘汰，写命令报错 |
| allkeys-lru | 所有 key | 最近最少使用 |
| allkeys-lfu（4.0+） | 所有 key | 最少使用频率 |
| allkeys-random | 所有 key | 随机 |
| volatile-lru / lfu / random | 只淘汰带 TTL 的 | 同上 |
| volatile-ttl | 只淘汰带 TTL 的 | 剩余 TTL 最短的先删 |

选择：纯缓存实例用 `allkeys-lru` 或 `allkeys-lfu`；**缓存与分布式锁、库存等「不能丢」的数据混用时用 `volatile-*`**，并确保后者不设 TTL 或分实例部署。

实现细节：Redis 的 LRU 是**近似 LRU**——不维护全局链表（太耗内存），而是每个对象记 24 位访问时钟，淘汰时随机抽 `maxmemory-samples`（默认 5）个，删最久未访问的。LFU 复用这 24 位：16 位时间 + 8 位对数计数器（随时间衰减），解决 LRU「偶尔被扫一次的冷数据被误认为热数据」的问题。

### 4.3 持久化

| 方式 | 原理 | 优点 | 缺点 |
|---|---|---|---|
| RDB | 定时 fork 子进程，把内存快照写成二进制文件 | 文件小、恢复快 | 两次快照间的数据会丢；fork 大实例时有停顿 |
| AOF | 每条写命令追加到日志 | 最多丢 1 秒（`appendfsync everysec`） | 文件大、恢复慢；需要 AOF 重写压缩 |
| 混合持久化（4.0+，`aof-use-rdb-preamble yes`） | AOF 重写时，前半段写 RDB 快照，后半段追加增量命令 | 兼顾恢复速度与数据安全 | 推荐默认使用 |

**fork + 写时复制（COW）**：fork 出的子进程与父进程共享内存页，父进程修改某页时才复制该页。因此：

- fork 本身要复制页表，10GB 实例可能停顿百毫秒 → 单实例内存建议 ≤ 10GB；
- 快照期间写入量大会复制大量页，内存可能接近翻倍 → 预留内存；
- 关闭 Linux 透明大页（THP），否则一次 COW 复制 2MB 而不是 4KB。

7.0 起 AOF 变为 Multi-Part AOF（base + incr 多文件 + manifest），重写不再需要在内存里缓存重写期间的增量。

> 定位提醒：**Redis 持久化不等于可靠存储**。即使 `appendfsync always`，主从异步复制、故障切换也可能丢数据。订单、余额必须以 MySQL 为准。

### 4.4 主从、哨兵、Cluster

```
主从复制                  哨兵 Sentinel                       Cluster
┌──────┐                  ┌────┐ ┌────┐ ┌────┐               ┌─────────┐ ┌─────────┐ ┌─────────┐
│Master│──▶ Replica       │ S1 │ │ S2 │ │ S3 │ 监控+选主      │ M1      │ │ M2      │ │ M3      │
└──────┘──▶ Replica       └─┬──┘ └─┬──┘ └─┬──┘               │0-5460   │ │5461-    │ │10923-   │
读写分离，手动故障转移      ▼      ▼      ▼                   │         │ │10922    │ │16383    │
                           Master + Replicas                   └──┬──────┘ └──┬──────┘ └──┬──────┘
                           自动故障转移，容量仍是单机            ▼ R1         ▼ R2         ▼ R3
                                                                数据分片 + 每片自带主从
```

**主从复制流程**：

1. 首次：从库发 `PSYNC`，主库 `bgsave` 生成 RDB 发给从库（全量），期间新写命令存入复制缓冲区再补发；
2. 之后：主库把写命令异步传播给从库；
3. 断线重连：若从库的 offset 仍在主库的 `repl_backlog`（环形缓冲区）范围内，只补增量；否则重新全量。**backlog 要调大**（默认 1MB 太小）。

**哨兵**：多个哨兵节点监控主库；一个哨兵认为主库不通为「主观下线」，超过 quorum 个认为不通为「客观下线」；哨兵间用 Raft 类似算法选出 leader，由它挑选一个从库（优先级 → 复制 offset 最大 → runid 最小）提升为主，并通知客户端。

**Cluster 哈希槽**：

```
slot = CRC16(key) % 16384
mall:product:detail:1  → slot 9821 → 节点 M2
```

- 16384 个槽分配给各主节点，扩容就是迁移槽；
- 客户端访问错节点会收到 `MOVED`（槽已迁移）或 `ASK`（迁移中）重定向，智能客户端会缓存槽映射；
- **多 key 操作（MGET、Lua 脚本、事务）要求所有 key 在同一个槽**，否则报 `CROSSSLOT`。解法是 **hash tag**：`{product:1}:stock` 与 `{product:1}:buyers` 只用 `{}` 内部分计算槽，必然同槽；
- 为什么是 16384 而不是 65536？节点间心跳包携带槽位图，16384 位 = 2KB，65536 位 = 8KB；集群节点数官方建议不超过 1000，16384 槽足够。

| 方案 | 高可用 | 容量扩展 | 复杂度 |
|---|---|---|---|
| 主从 | 手动 | 否 | 低 |
| 哨兵 | 自动 | 否 | 中 |
| Cluster | 自动 | 是 | 高（多 key 限制） |

**分布式环境的根本限制**：Redis 复制是异步的，主库写成功、还没同步给从库就宕机，切换后新主库没有这条数据。这直接影响分布式锁的安全性（4.8.4）。

### 4.5 缓存模式与一致性

#### 4.5.1 四种缓存模式

| 模式 | 读 | 写 | 谁维护缓存 | 场景 |
|---|---|---|---|---|
| **Cache Aside（旁路缓存）** | 先读缓存，未命中读 DB 并回填 | 先写 DB，再**删**缓存 | 应用 | 最常用，mini-mall 采用 |
| Read Through | 应用只读缓存，未命中由缓存层自己加载 DB | — | 缓存组件 | Caffeine `LoadingCache`、Spring Cache |
| Write Through | — | 应用写缓存，缓存层同步写 DB | 缓存组件 | 少见 |
| Write Behind（Write Back） | — | 只写缓存，异步批量刷 DB | 缓存组件 | 点赞数、浏览量等可容忍丢失的计数；CPU 缓存、OS page cache 也是这个模式 |

```
Cache Aside 读：
  请求 ──▶ GET cache ──命中──▶ 返回
              │ 未命中
              ▼
           查 DB ──▶ SET cache（带 TTL）──▶ 返回

Cache Aside 写：
  请求 ──▶ UPDATE DB ──▶ DEL cache
```

#### 4.5.2 为什么是「更新数据库 + 删除缓存」，而不是更新缓存

**为什么删而不更新**：

1. 并发写时，更新缓存的顺序可能和更新 DB 的顺序不一致：A 写 DB=1、B 写 DB=2、B 写缓存=2、A 写缓存=1 → 缓存永久是旧值；
2. 缓存值可能是多表计算的结果，每次写都重算是浪费，而很多写之后根本没人读；
3. 删除是幂等的，失败重试也安全。

**为什么先更新 DB 再删缓存，而不是先删缓存**：

```
先删缓存，再更新 DB（有问题）：
 写线程 A                      读线程 B
 DEL cache
                               GET cache → 未命中
                               查 DB → 读到旧值
 UPDATE DB 新值
                               SET cache = 旧值   ← 缓存是旧值，直到 TTL 过期
（读 DB 远快于写 DB，这个窗口很容易出现）

先更新 DB，再删缓存（推荐）：
 读线程 B                      写线程 A
 GET cache → 未命中（恰好过期）
 查 DB → 读到旧值
                               UPDATE DB 新值
                               DEL cache
 SET cache = 旧值   ← 仍有问题，但要求「B 读 DB 后、回填前，A 完成了整个写 DB + 删缓存」
（写 DB 通常慢于读 DB，概率很低；且需要恰好缓存失效）
```

剩下的两类风险和对策：

| 风险 | 对策 |
|---|---|
| 上面的极小概率并发 | 缓存设置 TTL 兜底；或延迟双删 |
| 删缓存失败（Redis 抖动） | 重试：发 MQ 消息异步重试删除；或订阅 binlog |
| 读从库导致回填旧值 | 回填缓存时读主库，或延迟双删的延迟 > 主从延迟 |

#### 4.5.3 延迟双删

```
1. DEL cache
2. UPDATE DB
3. 延迟 N 毫秒（N > 一次「读 DB + 回填缓存」的耗时，以及主从延迟）
4. DEL cache        ← 把并发读回填的旧值再删掉
```

延迟删除不能 `Thread.sleep` 阻塞请求线程，应投递延迟消息或交给调度线程池。缺点：N 是经验值，无法严格保证；它是**降低概率**，不是消除。

#### 4.5.4 订阅 binlog 删缓存（Canal）

```
应用 ──UPDATE──▶ MySQL ──binlog──▶ Canal（伪装成从库）──▶ RocketMQ ──▶ 缓存删除消费者 ──DEL──▶ Redis
                                                                         失败重试，最终成功
```

| 优点 | 缺点 |
|---|---|
| 业务代码只管写 DB，完全解耦 | 多一套组件，运维成本 |
| 所有写入口（包括手工改库、脚本）都能触发 | 有秒级延迟 |
| MQ 天然支持重试 | 需要把表/行映射到缓存 key |

#### 4.5.5 一致性取舍

缓存 + 数据库**做不到强一致**（除非加分布式锁把读写串行化，那缓存就失去了意义）。工程上的目标是**最终一致 + 可控的不一致窗口**：

| 数据类型 | 策略 |
|---|---|
| 商品名称、描述 | Cache Aside + TTL，秒级不一致可接受 |
| 商品价格 | Cache Aside + 删除失败重试；**下单时以 DB 价格为准**（缓存只用于展示） |
| 库存 | 展示用缓存近似值；扣减以 Redis 原子预扣 + DB 条件更新为准 |
| 余额 | 不缓存，直接查主库 |

### 4.6 缓存穿透、击穿、雪崩

| 问题 | 现象 | 原因 |
|---|---|---|
| 穿透 | 查询**不存在**的数据，每次都打到 DB | 恶意请求 `id=-1`、爬虫遍历 |
| 击穿 | 一个**热点 key** 过期瞬间，大量请求同时打到 DB | 热点 + 过期 |
| 雪崩 | **大量 key 同时过期**或 Redis 宕机，DB 被压垮 | TTL 相同、缓存层故障 |

#### 4.6.1 穿透：空值缓存 / 布隆过滤器

| 方案 | 做法 | 优缺点 |
|---|---|---|
| 参数校验 | id ≤ 0 直接拒绝 | 最便宜，第一道防线 |
| 空值缓存 | DB 查不到时缓存一个特殊值（如 `""`），TTL 短（1～5 分钟） | 简单；恶意请求大量随机 id 时会塞满缓存 |
| 布隆过滤器 | 所有存在的 id 预先放入过滤器，不在其中直接返回 | 内存极小；有误判（说存在可能不存在，说不存在一定不存在）；不支持删除 |

```
布隆过滤器：m 位数组 + k 个哈希函数
添加 id=1：h1(1)=3, h2(1)=7, h3(1)=12 → 置 1
查询 id=9：h1(9)=3, h2(9)=5 ... 只要有一位是 0 → 一定不存在

位数组： 0 0 0 1 0 0 0 1 0 0 0 0 1 0 0 ...
               ▲           ▲         ▲
```

Redisson 提供 `RBloomFilter`：

```java
RBloomFilter<Long> filter = redissonClient.getBloomFilter("mall:product:bloom");
filter.tryInit(10_000_000L, 0.01);   // 预计 1000 万元素、1% 误判率，约占 12MB
filter.add(productId);               // 新增商品时同步加入
boolean mayExist = filter.contains(productId);
```

#### 4.6.2 击穿：互斥锁 / 逻辑过期

| 方案 | 做法 | 一致性 | 可用性 |
|---|---|---|---|
| 互斥锁 | 未命中时只让一个线程查 DB 回填，其他线程等待后重读缓存 | 好 | 等待期间请求变慢 |
| 逻辑过期 | 缓存不设物理 TTL，value 内带 `expireAt`；读到过期数据**先返回旧值**，异步由一个线程刷新 | 短暂旧数据 | 好，永不阻塞 |
| 热点永不过期 + 主动刷新 | 定时任务刷新热点 | — | — |

逻辑过期正是前端 SWR 的 `stale-while-revalidate`：

```ts
// SWR：先给旧数据，后台重新验证
const { data } = useSWR('/api/product/1', fetcher, { revalidateOnFocus: true });
```

```java
/**
 * 逻辑过期缓存的值包装：数据本身 + 逻辑过期时间。
 *
 * @param data     缓存的商品数据
 * @param expireAt 逻辑过期时间戳（毫秒），超过后需要异步刷新，但仍可返回
 */
public record LogicalExpireValue(ProductPO data, long expireAt) {

    /**
     * 判断是否已逻辑过期。
     *
     * @return true 已过期，需触发异步刷新
     */
    public boolean isExpired() {
        return System.currentTimeMillis() > expireAt;
    }
}
```

读取流程：命中且未过期 → 返回；命中但已过期 → `tryLock` 成功则提交异步刷新任务，**无论是否抢到锁都返回旧值**；未命中（逻辑过期方案需要预热） → 回源。

#### 4.6.3 雪崩：随机 TTL / 多级缓存 / 高可用

| 原因 | 对策 |
|---|---|
| 大量 key 同时过期（如凌晨批量预热） | TTL = 基础值 + 随机值（如 30 分钟 ± 5 分钟） |
| Redis 宕机 | 哨兵/Cluster 高可用；本地缓存兜底（多级缓存）；Sentinel 限流熔断降级保护 DB |
| 冷启动 | 发布前预热热点数据 |

### 4.7 大 key、热 key 与多级缓存

#### 4.7.1 大 key

标准（经验值）：String > 10KB，集合元素 > 5000 或总大小 > 10MB。

| 危害 | 说明 |
|---|---|
| 阻塞 | 读写/删除大 key 耗时长，单线程下所有请求排队 |
| 网络 | 一次 `GET` 1MB，1000 QPS 就是 1GB/s，打满网卡 |
| 集群倾斜 | 某个分片内存远高于其他 |
| 迁移/过期 | 槽迁移、过期删除时卡顿 |

发现：`redis-cli --bigkeys`、`--memkeys`、`MEMORY USAGE key`、离线分析 RDB（如 redis-rdb-tools）。

处理：拆分（`cart:1001` 按 hash 拆成 `cart:1001:0..9`）、只取需要的字段（`HMGET` 而非 `HGETALL`）、压缩、删除用 `UNLINK`（后台线程释放）或 `HSCAN` + `HDEL` 分批删。

#### 4.7.2 热 key

秒杀商品详情被每秒 10 万次访问，即使 Redis 能扛，**所有请求都打到同一个分片**，Cluster 扩容也无济于事。

| 方案 | 说明 |
|---|---|
| 本地缓存 | 应用内 Caffeine 缓存热点，命中后不访问 Redis（最有效） |
| 热 key 打散 | 写多份 `product:1:copy0..9`，读时随机选一份 |
| 读写分离 | 热 key 的读走从节点 |
| 发现 | `redis-cli --hotkeys`（需 LFU 策略）、客户端埋点统计、京东 hotkey 等中间件实时探测 |

#### 4.7.3 多级缓存：Caffeine + Redis

```
请求 ──▶ L1 Caffeine（进程内，纳秒级，容量小，各实例各一份）
            │ 未命中
            ▼
         L2 Redis（网络，亚毫秒级，所有实例共享）
            │ 未命中
            ▼
         MySQL
```

```java
/**
 * L1 本地缓存：最多 1 万个商品，写入后 30 秒过期。
 * key 为商品 ID，value 为商品实体。
 */
private final Cache<Long, ProductPO> localCache = Caffeine.newBuilder()
        .maximumSize(10_000)
        .expireAfterWrite(Duration.ofSeconds(30))   // L1 TTL 必须很短：无法跨实例主动失效
        .recordStats()
        .build();
```

**难点是 L1 一致性**：改价后删了 Redis，但每个实例的 Caffeine 里还是旧值。方案：L1 TTL 设很短（秒级）、通过 Redis Pub/Sub 或 MQ 广播失效消息让所有实例删除本地缓存。Caffeine 用 W-TinyLFU 算法，命中率高于纯 LRU，Spring Boot 默认本地缓存实现就是它。

### 4.8 分布式锁

**为什么需要**：`synchronized`/`ReentrantLock`（第 04 章）只在一个 JVM 内有效。mini-mall 部署了 3 个实例，同一用户的两次点击可能落到不同实例上。

#### 4.8.1 演进：从 SETNX 到 Redisson

```
版本 1：SETNX lock 1  → 业务 → DEL lock
  问题：业务执行中进程崩溃，锁永远不释放 → 死锁

版本 2：SETNX + EXPIRE 两条命令
  问题：两条命令之间崩溃，仍死锁（非原子）

版本 3：SET lock 1 NX EX 10（一条命令，原子）
  问题 A：业务执行了 15 秒，锁 10 秒时已过期，B 拿到锁；A 执行完 DEL 把 B 的锁删了
  问题 B：业务超过 TTL，锁失效，互斥被破坏

版本 4：SET lock {uuid} NX EX 10，释放时 Lua 脚本「值是自己的才删」
  解决问题 A；问题 B 仍在（TTL 设多长都不对）

版本 5：Redisson —— 唯一值 + Lua + 看门狗自动续期 + 可重入 + 等待通知
  解决问题 B；剩下的是 Redis 主从异步复制导致的锁丢失 → RedLock 的争议
```

版本 4 的释放脚本：

```lua
-- KEYS[1] 锁 key，ARGV[1] 加锁时写入的唯一值
-- 先比较再删除必须在一个原子操作里，否则比较后、删除前锁可能过期并被别人拿到
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
```

#### 4.8.2 Redisson 原理

**加锁**：用 Hash 结构实现可重入，field 是 `客户端 UUID:线程 ID`，value 是重入次数：

```lua
-- KEYS[1] 锁名；ARGV[1] 过期毫秒；ARGV[2] uuid:threadId
if (redis.call('exists', KEYS[1]) == 0) or (redis.call('hexists', KEYS[1], ARGV[2]) == 1) then
    redis.call('hincrby', KEYS[1], ARGV[2], 1)      -- 首次加锁或重入，计数 +1
    redis.call('pexpire', KEYS[1], ARGV[1])
    return nil                                       -- nil 表示加锁成功
end
return redis.call('pttl', KEYS[1])                   -- 返回剩余 TTL，告诉调用方要等多久
```

**看门狗（Watchdog）**：调用 `lock()` / `tryLock(waitTime, unit)` 且**不指定 leaseTime** 时，默认 TTL 30 秒，后台每 10 秒（TTL 的 1/3）检查持有者仍在则续期到 30 秒；进程崩溃则停止续期，最多 30 秒后自动释放。**一旦显式指定 leaseTime，看门狗就不生效**。

**等待**：未拿到锁的线程订阅 `redisson_lock__channel:{锁名}`，释放时 `PUBLISH` 通知，而不是空转轮询。

```
线程 A lock() ──▶ Lua 加锁成功（TTL 30s）──▶ 启动看门狗：每 10s pexpire 30s
线程 B lock() ──▶ Lua 返回 pttl ──▶ 订阅 channel，阻塞等待
线程 A unlock() ──▶ Lua 计数 -1，为 0 则 DEL + PUBLISH ──▶ 取消看门狗
线程 B 被唤醒 ──▶ 重试加锁
```

#### 4.8.3 Redisson 用法

```java
RLock lock = redissonClient.getLock("mall:lock:order:create:" + userId);
// tryLock(等待时间, 单位)：最多等 0 秒，拿不到立即失败；不指定 leaseTime → 启用看门狗
if (!lock.tryLock(0, TimeUnit.SECONDS)) {
    throw new BizException(ErrorCode.REPEAT_SUBMIT);
}
try {
    // 业务
} finally {
    // 只释放自己持有的锁；否则可能抛 IllegalMonitorStateException
    if (lock.isHeldByCurrentThread()) {
        lock.unlock();
    }
}
```

#### 4.8.4 RedLock 的争议

**问题**：主库加锁成功，还没复制到从库就宕机，哨兵把从库提升为主，新主库上没有这把锁 → 另一个客户端也能加锁成功。

**RedLock（Redis 作者 antirez 提出）**：部署 N（如 5）个**完全独立**的 Redis 主节点，客户端依次向所有节点加锁，在锁有效期内拿到多数（≥ 3）才算成功。

**Martin Kleppmann 的反驳**（《How to do distributed locking》）：

1. **进程暂停**：客户端拿到锁后发生长 GC（STW）或网络延迟，锁过期被别人拿到，暂停恢复后它仍以为自己持有锁 → 任何基于租约的锁都有此问题；
2. **依赖时钟**：RedLock 假设各节点时钟漂移有界，时钟跳变会让锁提前过期；
3. 正确做法是 **fencing token**：锁服务每次发一个单调递增的令牌，存储层拒绝比已见过的令牌更小的写入。Redis 锁无法提供这个。

antirez 的回应是：可以通过检查耗时来缓解，时钟问题可通过运维保证。

**工程结论**：

| 场景 | 选择 |
|---|---|
| 「效率型」锁：防重复计算、防重复提交，偶尔失效只是多做一次 | Redisson 单实例/主从锁即可 |
| 「正确性型」锁：失效会造成资损 | 不要只依赖 Redis 锁：**数据库层必须有兜底**（唯一索引、条件更新、乐观锁），或使用 ZooKeeper/etcd 等 CP 系统 + fencing token |
| RedLock | 部署成本高（5 个独立实例）、争议大，Redisson 已将其标为废弃，**实际很少使用** |

mini-mall 的防重复下单就是「Redisson 锁拦截绝大部分 + `uk_order_no` 唯一索引 / 幂等 token 兜底」。

### 4.9 Lua 脚本与原子操作

Redis 执行 Lua 脚本期间不会执行其他命令，整段脚本是原子的。类比：一段同步 JS 代码在事件循环中不会被其他回调打断。

| 方式 | 原子性 | 回滚 | 场景 |
|---|---|---|---|
| 单条命令（`INCR`、`SET NX`） | 原子 | — | 首选 |
| `MULTI/EXEC` 事务 | 批量执行不被插队 | **不回滚**，中间某条失败其余照常执行；不能根据中间结果做分支 | 少用 |
| Lua 脚本 | 原子 | 不回滚（已执行的写不会撤销） | 「判断 + 修改」组合操作 |
| Pipeline | **不原子**，只是批量发送减少 RTT | — | 批量读写提速 |

注意事项：

- 脚本要短：执行期间阻塞整个 Redis，超过 `busy-reply-threshold`（默认 5 秒）后其他客户端会收到 BUSY 错误；
- 所有 key 通过 `KEYS` 传入，Cluster 下须在同一个槽（用 hash tag）；
- 用 `EVALSHA` 避免每次传输脚本（Spring 的 `DefaultRedisScript` 会自动处理）；
- 7.0 引入 Function（`FUNCTION LOAD`），把脚本作为服务端持久化的函数库。

### 4.10 限流

| 算法 | 原理 | 优点 | 缺点 |
|---|---|---|---|
| 固定窗口 | `INCR key` + 窗口长度 TTL，超阈值拒绝 | 最简单 | 临界突刺：59 秒 100 次 + 61 秒 100 次 → 2 秒内 200 次 |
| 滑动窗口 | ZSet 存每次请求的时间戳，`ZREMRANGEBYSCORE` 删窗口外的，`ZCARD` 计数 | 精确 | 每个请求一个成员，内存随 QPS 增长 |
| 漏桶 | 请求入桶，以恒定速率流出 | 输出平滑 | 无法应对合理突发 |
| 令牌桶 | 以恒定速率放令牌，请求取令牌，桶有上限 | 允许一定突发，又限制平均速率 | 实现稍复杂 |

前端类比：固定窗口 ≈ 按秒计数，令牌桶 ≈ `throttle` 加了「攒次数」的能力。

**滑动窗口 Lua**：

```lua
-- KEYS[1] 限流 key；ARGV[1] 当前毫秒时间；ARGV[2] 窗口毫秒；ARGV[3] 上限；ARGV[4] 本次请求唯一 ID
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, tonumber(ARGV[1]) - tonumber(ARGV[2]))  -- 移除窗口外的请求
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then
    return 0                                                                        -- 超限
end
redis.call('ZADD', KEYS[1], ARGV[1], ARGV[4])
redis.call('PEXPIRE', KEYS[1], ARGV[2])
return 1
```

**令牌桶**直接用 Redisson：

```java
RRateLimiter limiter = redissonClient.getRateLimiter("mall:limit:order:create");
// 全局每秒产生 1000 个令牌（RateType.OVERALL 表示所有实例共享）
limiter.trySetRate(RateType.OVERALL, 1000, Duration.ofSeconds(1));
if (!limiter.tryAcquire()) {
    throw new BizException(ErrorCode.TOO_MANY_REQUESTS);
}
```

> 网关层的整体限流通常交给 Sentinel / Spring Cloud Gateway（第 11 章），业务层 Redis 限流用于「单用户每分钟最多下 10 单」这类细粒度规则。

### 4.11 Spring Cache 注解

Spring Cache 是一层抽象（Read Through 风格），用注解声明缓存，背后可以是 Redis / Caffeine。

| 注解 | 作用 |
|---|---|
| `@EnableCaching` | 开启 |
| `@Cacheable(cacheNames="product", key="#id")` | 先查缓存，未命中执行方法并缓存返回值 |
| `@CachePut` | 总是执行方法，并用返回值更新缓存 |
| `@CacheEvict(cacheNames="product", key="#id")` | 删除缓存 |
| `@Caching` | 组合多个 |

```java
/**
 * 查询商品详情，结果缓存到 product::{id}。
 *
 * @param id 商品 ID
 * @return 商品，不存在返回 null（unless 条件下不缓存）
 */
@Cacheable(cacheNames = "product", key = "#id", unless = "#result == null")
public ProductPO getProduct(Long id) {
    return productDao.getById(id);
}
```

| 优点 | 局限 |
|---|---|
| 零侵入、代码简洁 | 基于 AOP 代理：**同类内部调用不生效**（与 `@Transactional` 同理，第 06 章） |
| 可切换实现 | 默认不防击穿（`sync = true` 只在单 JVM 内互斥） |
| — | TTL 只能按 cacheName 配置，不方便随机 TTL；空值缓存、逻辑过期都要自定义 |

结论：后台管理、配置类数据用 Spring Cache；**核心高并发链路（商品详情）手写缓存服务**，掌控每个细节。

---

## 5. mini-mall 实战

本章为 mini-mall 新增的组件（第四层能力单元，放在 `com.example.mall.cache` 包；锁和限流的 key 常量统一放 `RedisKeys`）：

| 组件 | 层级 | 职责 |
|---|---|---|
| `RedisKeys` | ⑤ 工具 | 集中定义 key 前缀与构造方法 |
| `ProductCacheService` | ④ 能力单元 | 商品详情旁路缓存：读、删、空值、随机 TTL、互斥回源 |
| `StockPreDeductService` | ④ 能力单元 | Redis + Lua 预扣/回补库存 |
| `ProductPriceUnit` | ③ 功能单元 | 改价：更新 DB + 删除缓存 + 失败补偿 |
| `OrderBizComponent`（已有） | ② 编排层 | 下单流程中加入 Redisson 锁、预扣库存 |

### 5.1 Key 定义

```java
package com.example.mall.cache;

/**
 * Redis key 统一定义，避免字符串散落各处。
 */
public final class RedisKeys {

    /** 商品详情缓存前缀，完整 key：mall:product:detail:{productId} */
    private static final String PRODUCT_DETAIL = "mall:product:detail:";

    /** 商品回源互斥锁前缀，完整 key：mall:lock:product:load:{productId} */
    private static final String PRODUCT_LOAD_LOCK = "mall:lock:product:load:";

    /** 下单防重锁前缀，完整 key：mall:lock:order:create:{userId} */
    private static final String ORDER_CREATE_LOCK = "mall:lock:order:create:";

    private RedisKeys() {
    }

    /**
     * 构造商品详情缓存 key。
     *
     * @param productId 商品 ID
     * @return 缓存 key
     */
    public static String productDetail(Long productId) {
        return PRODUCT_DETAIL + productId;
    }

    /**
     * 构造商品回源锁 key。
     *
     * @param productId 商品 ID
     * @return 锁 key
     */
    public static String productLoadLock(Long productId) {
        return PRODUCT_LOAD_LOCK + productId;
    }

    /**
     * 构造库存 key，使用 {stock} 作为 hash tag，使一次下单涉及的多个商品库存落在同一槽，
     * 以便在一个 Lua 脚本中原子扣减。
     * 代价：所有库存 key 集中在一个分片；库存 key 体量很小，可接受。
     *
     * @param productId 商品 ID
     * @return 库存 key，形如 mall:{stock}:1
     */
    public static String stock(Long productId) {
        return "mall:{stock}:" + productId;
    }

    /**
     * 构造下单防重锁 key。
     *
     * @param userId 用户 ID
     * @return 锁 key
     */
    public static String orderCreateLock(Long userId) {
        return ORDER_CREATE_LOCK + userId;
    }

    /**
     * 单商品扣库存分布式锁 key（04 章并发扣库存示例使用）：mall:lock:stock:{productId}
     *
     * @param productId 商品 ID
     * @return 锁 key
     */
    public static String stockLock(Long productId) {
        return "mall:lock:stock:" + productId;
    }
}
```

> hash tag 前后的差异：`mall:stock:1` 与 `mall:stock:2` 可能在不同槽，`mall:{stock}:1` 与 `mall:{stock}:2` 必定同槽。

### 5.2 商品详情旁路缓存 ProductCacheService

```
ProductCacheService.getProduct(productId)
  │
  ├─ 1. productId 非法 → 返回 null（穿透第一道防线）
  ├─ 2. GET mall:product:detail:{id}
  │      ├─ 命中且为空值标记 "" → 返回 null（空值缓存，防穿透）
  │      └─ 命中 JSON → 反序列化返回
  ├─ 3. 未命中 → Redisson tryLock(回源锁, 等待 200ms)（防击穿）
  │      ├─ 抢到锁：双重检查缓存 → 查 DB → 回填（存在：30min±5min 随机 TTL；不存在：空值 2min）
  │      └─ 没抢到：短暂等待后再读一次缓存；仍无则直接查 DB（降级，不让请求失败）
  └─ 返回
```

```java
package com.example.mall.cache;

/**
 * 商品详情旁路缓存（Cache Aside）：负责商品缓存的读取、回源与删除，不包含业务判断。
 * 防护：空值缓存防穿透、回源互斥锁防击穿、随机 TTL 防雪崩。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ProductCacheService {

    /** 空值标记：表示「已确认数据库中不存在」 */
    private static final String NULL_VALUE = "";

    /** 正常数据基础 TTL：30 分钟 */
    private static final long BASE_TTL_SECONDS = 30 * 60;

    /** 随机 TTL 上限：5 分钟，打散过期时间 */
    private static final long RANDOM_TTL_SECONDS = 5 * 60;

    /** 空值 TTL：2 分钟，既防穿透又能较快感知新上架商品 */
    private static final long NULL_TTL_SECONDS = 2 * 60;

    private final StringRedisTemplate stringRedisTemplate;
    private final RedissonClient redissonClient;
    private final ObjectMapper objectMapper;
    private final ProductDao productDao;

    /**
     * 查询商品详情：先查缓存，未命中则互斥回源数据库并回填。
     *
     * @param productId 商品 ID
     * @return 商品实体；不存在返回 null
     */
    public ProductPO getProduct(Long productId) {
        // 1. 非法参数直接拦截
        if (productId == null || productId <= 0) {
            return null;
        }
        // 2. 读缓存
        String key = RedisKeys.productDetail(productId);
        CacheHit hit = readCache(key);
        if (hit.found()) {
            return hit.product();
        }
        // 3. 未命中，互斥回源
        return loadWithMutex(productId, key);
    }

    /**
     * 删除商品缓存（数据变更后调用）。
     *
     * @param productId 商品 ID
     * @return true 删除了已存在的 key；false key 不存在
     */
    public boolean evict(Long productId) {
        return Boolean.TRUE.equals(stringRedisTemplate.delete(RedisKeys.productDetail(productId)));
    }

    /**
     * 读取缓存并解析。
     *
     * @param key 缓存 key
     * @return 命中结果：found=false 表示未命中；found=true 且 product=null 表示命中空值
     */
    private CacheHit readCache(String key) {
        String json = stringRedisTemplate.opsForValue().get(key);
        if (json == null) {
            return CacheHit.MISS;
        }
        if (NULL_VALUE.equals(json)) {
            return new CacheHit(true, null);
        }
        return new CacheHit(true, fromJson(json));
    }

    /**
     * 加互斥锁回源数据库，保证同一商品同一时刻只有一个请求查库。
     *
     * @param productId 商品 ID
     * @param key       缓存 key
     * @return 商品实体，不存在返回 null
     */
    private ProductPO loadWithMutex(Long productId, String key) {
        RLock lock = redissonClient.getLock(RedisKeys.productLoadLock(productId));
        boolean locked = false;
        try {
            // 最多等 200ms：拿到锁的线程通常几十毫秒内完成回填
            locked = lock.tryLock(200, TimeUnit.MILLISECONDS);
            if (locked) {
                // 双重检查：等锁期间可能已被其他线程回填
                CacheHit hit = readCache(key);
                return hit.found() ? hit.product() : loadFromDbAndFill(productId, key);
            }
            // 没拿到锁：再读一次缓存，仍未命中则降级直接查库（宁可多查一次也不让请求失败）
            CacheHit hit = readCache(key);
            return hit.found() ? hit.product() : productDao.getById(productId);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return productDao.getById(productId);
        } finally {
            if (locked && lock.isHeldByCurrentThread()) {
                lock.unlock();
            }
        }
    }

    /**
     * 查询数据库并回填缓存：存在则随机 TTL，不存在则缓存空值。
     *
     * @param productId 商品 ID
     * @param key       缓存 key
     * @return 商品实体，不存在返回 null
     */
    private ProductPO loadFromDbAndFill(Long productId, String key) {
        ProductPO product = productDao.getById(productId);
        if (product == null) {
            stringRedisTemplate.opsForValue().set(key, NULL_VALUE, Duration.ofSeconds(NULL_TTL_SECONDS));
            return null;
        }
        stringRedisTemplate.opsForValue().set(key, toJson(product), Duration.ofSeconds(randomTtlSeconds()));
        return product;
    }

    /**
     * 计算随机 TTL：基础值 + [0, 随机上限)，避免大量 key 同时过期。
     *
     * @return TTL 秒数
     */
    private long randomTtlSeconds() {
        return BASE_TTL_SECONDS + ThreadLocalRandom.current().nextLong(RANDOM_TTL_SECONDS);
    }

    /**
     * 商品序列化为 JSON。
     *
     * @param product 商品实体
     * @return JSON 字符串
     */
    private String toJson(ProductPO product) {
        try {
            return objectMapper.writeValueAsString(product);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("商品序列化失败, id=" + product.getId(), e);
        }
    }

    /**
     * JSON 反序列化为商品；数据损坏时返回 null 并记录日志（调用方会视为缓存命中空值，下次 TTL 后自愈）。
     *
     * @param json 缓存中的 JSON
     * @return 商品实体
     */
    private ProductPO fromJson(String json) {
        try {
            return objectMapper.readValue(json, ProductPO.class);
        } catch (JsonProcessingException e) {
            log.error("商品缓存反序列化失败, json={}", json, e);
            return null;
        }
    }

    /**
     * 缓存读取结果。
     *
     * @param found   是否命中（含空值命中）
     * @param product 商品实体；命中空值时为 null
     */
    private record CacheHit(boolean found, ProductPO product) {
        /** 未命中常量 */
        static final CacheHit MISS = new CacheHit(false, null);
    }
}
```

设计说明：

- 为什么用 `CacheHit` 而不是直接返回 null？因为要区分「未命中」与「命中空值」，这是空值缓存正确工作的前提；
- 没抢到锁时降级查库而不是返回失败：商品详情是读接口，**可用性优先**；若 DB 压力是主要矛盾，可改为返回「系统繁忙」；
- 若热点商品还需更快，在 `getProduct` 前面套一层 Caffeine（4.7.3），并订阅改价广播清除本地缓存。

### 5.3 Redis + Lua 预扣库存 StockPreDeductService

秒杀/大促时，下单链路变成：

```
OrderBizComponent.createOrder
  │
  ├─ 1. Redisson 锁：同一用户同时只能有一个下单请求（5.4）
  ├─ 2. StockPreDeductService.preDeduct(按商品 ID 的数量 Map)   ← Redis 原子预扣，不足直接返回
  │       └─ 失败 → 返回「库存不足」，请求根本不碰数据库
  ├─ 3. OrderCreateUnit.create(...)  @Transactional：写订单 + 明细 + DB 条件扣库存（第 08 章 6.5）
  │       └─ 失败（异常）→ StockPreDeductService.restore(...) 回补 Redis
  └─ 4. 返回订单号
```

Redis 是**挡在前面的流量闸门**：99% 的请求在 Redis 判断库存不足后就返回了；DB 的条件更新仍保留，作为**最终正确性**的保证。

Lua 脚本（`resources/lua/stock_pre_deduct.lua`）：

```lua
-- 多商品原子预扣：要么全部扣减，要么都不扣
-- KEYS[i]：第 i 个商品的库存 key（同一 hash tag，保证同槽）
-- ARGV[i]：第 i 个商品的扣减数量
-- 返回：1 成功；0 某商品库存不足；-1 某商品库存未预热

-- 第一遍：只检查，不修改（Lua 不会回滚，所以必须先全部校验）
for i = 1, #KEYS do
    local stock = redis.call('GET', KEYS[i])
    if not stock then
        return -1
    end
    if tonumber(stock) < tonumber(ARGV[i]) then
        return 0
    end
end
-- 第二遍：全部通过后再扣减
for i = 1, #KEYS do
    redis.call('DECRBY', KEYS[i], ARGV[i])
end
return 1
```

```java
package com.example.mall.cache;

/**
 * Redis 预扣库存能力单元：用 Lua 原子地检查并扣减多个商品的 Redis 库存。
 * Redis 库存只是流量闸门，最终以数据库条件更新为准。
 */
@Component
@RequiredArgsConstructor
public class StockPreDeductService {

    /** 预扣脚本：返回 1 成功，0 库存不足，-1 未预热 */
    private static final DefaultRedisScript<Long> PRE_DEDUCT_SCRIPT =
            new DefaultRedisScript<>(loadScript("lua/stock_pre_deduct.lua"), Long.class);

    private final StringRedisTemplate stringRedisTemplate;

    /**
     * 预扣结果。
     */
    @Getter
    @RequiredArgsConstructor
    public enum PreDeductResult {
        /** 全部扣减成功 */
        SUCCESS(1L),
        /** 至少一个商品库存不足，未做任何扣减 */
        NOT_ENOUGH(0L),
        /** 至少一个商品库存未预热到 Redis，需要回源或拒绝 */
        NOT_WARMED(-1L);

        /** Lua 脚本返回码 */
        private final long code;

        /**
         * 按脚本返回码解析枚举。
         *
         * @param code 返回码
         * @return 对应枚举，未知码视为库存不足（安全侧）
         */
        public static PreDeductResult of(Long code) {
            for (PreDeductResult r : values()) {
                if (code != null && r.code == code) {
                    return r;
                }
            }
            return NOT_ENOUGH;
        }
    }

    /**
     * 商品上架或活动开始前，把数据库库存预热到 Redis。
     *
     * @param productId 商品 ID
     * @param stock     数据库当前库存
     */
    public void warmUp(Long productId, int stock) {
        stringRedisTemplate.opsForValue().set(RedisKeys.stock(productId), String.valueOf(stock));
    }

    /**
     * 原子预扣多个商品的库存。
     *
     * @param quantityByProductId key 为商品 ID，value 为扣减数量
     * @return 预扣结果
     */
    public PreDeductResult preDeduct(Map<Long, Integer> quantityByProductId) {
        // KEYS 与 ARGV 必须一一对应，所以先固定遍历顺序
        List<Long> productIds = new ArrayList<>(quantityByProductId.keySet());
        List<String> keys = productIds.stream().map(RedisKeys::stock).toList();
        String[] args = productIds.stream()
                .map(id -> String.valueOf(quantityByProductId.get(id)))
                .toArray(String[]::new);
        Long code = stringRedisTemplate.execute(PRE_DEDUCT_SCRIPT, keys, (Object[]) args);
        return PreDeductResult.of(code);
    }

    /**
     * 回补 Redis 库存（DB 下单失败或订单取消时调用）。
     *
     * @param quantityByProductId key 为商品 ID，value 为回补数量
     */
    public void restore(Map<Long, Integer> quantityByProductId) {
        // 单条 INCRBY 本身原子，多个商品之间无需整体原子，失败可重试
        quantityByProductId.forEach((productId, quantity) ->
                stringRedisTemplate.opsForValue().increment(RedisKeys.stock(productId), quantity));
    }

    /**
     * 从 classpath 读取 Lua 脚本内容。
     *
     * @param path classpath 下的脚本路径
     * @return 脚本文本
     */
    private static String loadScript(String path) {
        try (InputStream in = new ClassPathResource(path).getInputStream()) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new IllegalStateException("加载 Lua 脚本失败: " + path, e);
        }
    }
}
```

> `execute(script, keys, args...)` 的 args 是 `Object...` 可变参数，这里传 `String[]` 并强转只是为了展开数组，元素都是字符串（`StringRedisTemplate` 的序列化器只接受 String），并非用 Object 充当数据结构。

**Redis 与 DB 库存不一致怎么办？**

| 情况 | 结果 | 处理 |
|---|---|---|
| Redis 扣成功，DB 下单失败 | Redis 少了 | 应用内 `restore`；进程崩溃来不及回补 → 定时对账：Redis 库存 = DB 库存 − 处理中的预扣 |
| 订单超时取消 | DB 回补后 | 同时 `restore` Redis（第 10 章延迟消息消费者里调用） |
| Redis 宕机丢数据 | 预热数据丢失 | 返回 `NOT_WARMED`，编排层降级为直接走 DB 条件更新（限流保护） |

原则：**Redis 只能少卖，不能多卖**——Redis 偏少最多导致少卖几件，靠对账修复；多卖由 DB 的 `stock >= ?` 兜底杜绝。

### 5.4 Redisson 锁防止用户重复下单

前端会做按钮防抖、提交中禁用，但**服务端永远不能信任前端**：网络重试、用户多开页面、脚本刷单都会绕过。

```java
package com.example.mall.biz;

/**
 * 订单编排层（节选）：下单流程编排。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class OrderBizComponent {

    private final RedissonClient redissonClient;
    private final StockPreDeductService stockPreDeductService;
    private final OrderCreateUnit orderCreateUnit;

    /**
     * 创建订单：防重锁 → Redis 预扣 → 事务落库 → 失败回补。
     *
     * @param userId 当前登录用户 ID
     * @param dto    下单入参
     * @return 订单号
     */
    public String createOrder(Long userId, CreateOrderDTO dto) {
        RLock lock = redissonClient.getLock(RedisKeys.orderCreateLock(userId));
        // 1. 同一用户同时只允许一个下单请求；拿不到锁立即失败，不排队
        if (!lock.tryLock()) {
            throw new BizException(ErrorCode.REPEAT_SUBMIT);
        }
        try {
            // 2~3. 锁包住整个事务方法：事务提交后才释放锁
            return preDeductAndCreate(userId, dto);
        } finally {
            if (lock.isHeldByCurrentThread()) {
                lock.unlock();
            }
        }
    }

    /**
     * 预扣 Redis 库存后落库；落库失败回补 Redis。
     *
     * @param userId 用户 ID
     * @param dto    下单入参
     * @return 订单号
     */
    private String preDeductAndCreate(Long userId, CreateOrderDTO dto) {
        Map<Long, Integer> quantityByProductId = dto.quantityByProductId();
        // 2. Redis 预扣：不足直接返回，不访问数据库
        PreDeductResult result = stockPreDeductService.preDeduct(quantityByProductId);
        if (result != PreDeductResult.SUCCESS) {
            throw new BizException(ErrorCode.STOCK_NOT_ENOUGH);
        }
        try {
            // 3. 事务落库（OrderCreateUnit 内 @Transactional，含 DB 条件扣库存）
            return orderCreateUnit.createOrder(userId, dto.getItems()).getOrderNo();
        } catch (RuntimeException e) {
            // 4. 落库失败，回补 Redis 预扣，再抛出原异常
            stockPreDeductService.restore(quantityByProductId);
            throw e;
        }
    }
}
```

> `CreateOrderDTO.quantityByProductId()` 返回 `Map<Long, Integer>`（key 商品 ID，value 数量），由 DTO 内的明细列表聚合（同一商品多行时求和）。`ErrorCode.REPEAT_SUBMIT`、`STOCK_NOT_ENOUGH` 是本章新增的错误码。

几个关键决策：

| 决策 | 理由 |
|---|---|
| 锁粒度是 userId，不是全局 | 全局锁会让所有用户串行下单 |
| `tryLock()` 不等待 | 重复提交就该立即拒绝，而不是排队后再下一单 |
| 不指定 leaseTime | 启用看门狗，下单慢（DB 抖动）时锁不会提前过期 |
| **锁在事务外面** | 若在 `@Transactional` 方法内部加解锁，解锁时事务尚未提交，下一个请求进来看不到刚写的订单 |
| 锁只防并发，不防「先后两次」 | 用户下完一单 2 秒后又点一次，锁已释放 → 这是「幂等」问题，靠前端提交时带幂等 token（下单页加载时由服务端下发，`SET token NX` 消费一次）解决，第 10 章详述 |

### 5.5 更新商品价格的缓存一致性

改价写的是 `t_product` 一张表 + 一个缓存，但删缓存失败需要补偿，所以封装为第三层功能单元：

```
ProductAdminController.updatePrice
  │
  ▼
ProductPriceUnit.updatePrice(productId, newPrice)
  ├─ 1. ProductDao.updatePrice（事务内）
  ├─ 2. 事务提交后 → ProductCacheService.evict(productId)
  │        └─ 失败 → 发送「删除缓存」消息到 MQ，消费者重试删除（第 10 章）
  └─ 3. 延迟 1 秒再删一次（延迟双删，消除并发读回填的旧值；可选）

兜底：缓存 TTL 30 分钟；下单时 OrderCreateUnit 读取 DB 价格，不使用缓存价格
```

```java
package com.example.mall.domain;

/**
 * 商品改价功能单元：更新数据库价格，并在事务提交后删除缓存，删除失败时异步补偿。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ProductPriceUnit {

    /** 延迟双删的延迟时间：大于一次「读 DB + 回填缓存」耗时与主从延迟 */
    private static final long DELAY_EVICT_MILLIS = 1000;

    private final ProductDao productDao;
    private final ProductCacheService productCacheService;
    private final CacheEvictRetryProducer cacheEvictRetryProducer;
    private final ScheduledExecutorService cacheEvictScheduler;

    /**
     * 修改商品价格。
     *
     * @param productId 商品 ID
     * @param newPrice  新价格（元，2 位小数）
     * @return true 修改成功；false 商品不存在
     */
    @Transactional(rollbackFor = Exception.class)
    public boolean updatePrice(Long productId, BigDecimal newPrice) {
        // 1. 更新数据库
        if (!productDao.updatePrice(productId, newPrice)) {
            return false;
        }
        // 2. 注册事务同步：提交后再删缓存，避免「删了缓存、事务回滚」或「删早了被旧值回填」
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                evictWithRetry(productId);
                scheduleDelayedEvict(productId);
            }
        });
        return true;
    }

    /**
     * 删除缓存；Redis 异常时投递 MQ 消息由消费者重试。
     *
     * @param productId 商品 ID
     */
    private void evictWithRetry(Long productId) {
        try {
            productCacheService.evict(productId);
        } catch (RuntimeException e) {
            log.warn("删除商品缓存失败，转 MQ 重试, productId={}", productId, e);
            cacheEvictRetryProducer.sendProductEvict(productId);
        }
    }

    /**
     * 延迟双删：延迟一段时间后再删一次，清除并发读请求回填的旧值。
     *
     * @param productId 商品 ID
     */
    private void scheduleDelayedEvict(Long productId) {
        // ponytail: 进程重启会丢失未执行的延迟任务，可靠性要求高时改用 MQ 延迟消息
        cacheEvictScheduler.schedule(() -> evictWithRetry(productId),
                DELAY_EVICT_MILLIS, TimeUnit.MILLISECONDS);
    }
}
```

> `CacheEvictRetryProducer` 是第 10 章实现的 MQ 生产者；`cacheEvictScheduler` 是在配置类中声明的单线程 `ScheduledExecutorService` Bean（第 04 章线程池规范：命名线程、有界）。若引入了 Canal（4.5.4），以上删缓存代码都可以去掉，由 binlog 消费者统一处理——这是规模变大后的演进方向。

**为什么在 `afterCommit` 里删缓存？**

```
在事务内删缓存（错误）：
  事务 A：UPDATE price=99（未提交）→ DEL cache
  读请求：GET 未命中 → 查 DB，读到旧价格 199（A 未提交，MVCC 看不到）→ 回填 199
  事务 A：COMMIT          ← 缓存是旧价格 199，直到 TTL 过期

afterCommit 删缓存（正确）：
  事务 A：UPDATE price=99 → COMMIT → DEL cache
  之后的读请求一定从 DB 读到 99
```

---

## 6. 常见坑

| 坑 | 后果 | 正确做法 |
|---|---|---|
| 默认 JDK 序列化 | key/value 乱码、跨语言不可读、类变更反序列化失败 | `StringRedisTemplate` + JSON |
| `KEYS *` 查 key | 阻塞 Redis 数秒，全站超时 | `SCAN` 游标迭代；生产 `rename-command KEYS ""` |
| key 不设 TTL | 内存只增不减 | 一律设 TTL，并加随机值 |
| 先删缓存再写库 | 并发读回填旧值 | 先写库再删缓存 + 重试 |
| 缓存里存可变对象引用（Caffeine） | 调用方修改了返回的对象，缓存被污染 | 返回副本或使用不可变对象（`record`） |
| 锁的 value 固定写 "1" | 误删别人的锁 | 唯一值 + Lua 比较删除 |
| `tryLock(wait, lease, unit)` 指定了 leaseTime | 看门狗失效，业务没执行完锁就过期 | 不传 leaseTime，或确保 leaseTime 远大于业务耗时 |
| `unlock` 未放 finally | 异常时锁不释放（直到过期） | finally 中释放，并判断 `isHeldByCurrentThread` |
| 锁内调用 `@Transactional` 方法，锁在事务提交前释放 | 释放锁后、事务提交前，另一个请求读到旧数据 | **锁包事务**：加锁 → 调用事务方法（提交）→ 解锁 |
| Lua 里操作不同槽的 key | Cluster 下报 CROSSSLOT | hash tag `{...}` |
| 把 Redis 当可靠存储 | 宕机/切换丢数据 | 关键数据以 DB 为准，Redis 可重建 |
| 缓存空值没区分「没查」与「查了为空」 | 穿透或误判 | 用特殊标记值（如 `""`）表示「确认不存在」 |
| 大 key 用 `DEL` | 阻塞 | `UNLINK` |
| `BigDecimal` 存 JSON 变成 double | 精度丢失 | Jackson 配置 `WRITE_BIGDECIMAL_AS_PLAIN`，或存字符串 |

---

## 7. 高级视角

### 7.1 缓存设计清单

上线一个缓存前，逐项回答：

| 问题 | 示例回答（商品详情） |
|---|---|
| 缓存什么、粒度多大 | 单个商品基础信息，约 1KB |
| 命中率预期 | > 95%，监控 `keyspace_hits / (hits + misses)` |
| TTL 与过期策略 | 30min ± 5min |
| 一致性要求与不一致窗口 | 秒级；价格以 DB 为准 |
| 更新方式 | Cache Aside，afterCommit 删除 + MQ 重试 |
| 穿透/击穿/雪崩 | 空值 / 互斥锁 / 随机 TTL |
| 容量估算 | 100 万商品 × 1KB ≈ 1GB |
| Redis 不可用时 | 降级查 DB + 限流；不能让缓存故障变成全站故障 |
| 是否需要本地缓存 | 热点商品需要 |

### 7.2 Redis 运维与监控指标

| 指标 | 关注点 |
|---|---|
| `used_memory` / `maxmemory` | 超过 80% 告警 |
| `evicted_keys` | 持续增长说明容量不足 |
| `instantaneous_ops_per_sec` | 单实例经验上限约 10 万 QPS |
| `connected_clients` | 突增可能是连接泄漏 |
| `SLOWLOG GET` | 慢命令，阈值 `slowlog-log-slower-than` 默认 10ms |
| `latency doctor` | 延迟诊断（fork、AOF fsync、大 key 删除等） |
| 命中率 | 骤降往往是 key 规则改动或大面积过期 |

### 7.3 一致性的更高阶方案

| 方案 | 思路 | 代价 |
|---|---|---|
| 读写锁（Redisson `RReadWriteLock`） | 写时加写锁阻塞读回填 | 性能下降，失去缓存意义的一部分 |
| 版本号缓存 | 缓存值带 DB 的 `version`，回填时 Lua 比较「新版本 > 缓存版本」才写入 | 需要表有 version（`t_product` 正好有） |
| binlog 驱动 | Canal 统一删缓存 | 组件运维 |

`t_product.version` 在这里再次发挥作用：回填时用 Lua 判断 `if 新值.version > 缓存值.version then SET`，就能杜绝「旧值覆盖新值」的竞态——这和 React 里用请求序号丢弃过期响应（避免竞态条件）是同一个思路。

### 7.4 高级工程师的缓存观

- **缓存是性能优化，不是数据源**：任何时候 Redis 被清空，系统都必须能正确运行（变慢可以）；
- **先问要不要缓存**：数据库能扛住就不加；每加一层缓存就多一个一致性问题；
- **把不一致窗口说清楚**：评审时回答「最坏情况下用户会看到多久的旧数据，造成什么后果」；
- **锁的兜底在数据库**：Redis 锁提高效率，唯一索引和条件更新保证正确；
- **热点与容量提前规划**：大促前压测、预热、扩容，而不是故障后救火。

---

## 8. 小练习

1. 用 `OBJECT ENCODING` 观察：给一个 Hash 写 10 个字段和 200 个字段、给 ZSet 写一个 100 字节的 member，编码分别是什么？调整 `hash-max-listpack-entries` 后再观察。
2. 用 `RedisTemplate` 默认配置存一个对象，在 redis-cli 里查看 key；再换成 `StringRedisTemplate` + JSON，对比差异。
3. 实现 `ProductCacheService` 并压测：用 JMeter/wrk 对一个刚过期的商品发起 1000 并发，统计查库次数（去掉互斥锁 vs 加上互斥锁）。
4. 用两个线程模拟 4.5.2 中「先删缓存再更新 DB」的竞态，在关键位置用 `CountDownLatch` 控制执行顺序，复现缓存旧值；再改为 `afterCommit` 删除验证修复。
5. 写一个 JUnit 测试：100 个线程同时对库存 10 的商品调用 `StockPreDeductService.preDeduct`，断言恰好 10 次成功、Redis 库存最终为 0。
6. 手写版本 4 的分布式锁（`SET NX EX` + Lua 释放），故意让业务耗时超过 TTL，观察锁被另一个线程获取的现象；再换成 Redisson 不指定 leaseTime，验证看门狗续期。
7. 用 ZSet + Lua 实现「单用户每分钟最多下 10 单」的滑动窗口限流，并写测试验证第 11 次被拒绝、一分钟后恢复。
