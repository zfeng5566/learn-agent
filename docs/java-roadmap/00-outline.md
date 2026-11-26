# 前端转 Java 服务端：技术栈总纲

> 读者：有扎实前端经验（JS/TS、React/Vue、Node 基础）的工程师
> 目标：从「能看懂 Java 代码」到「能独立设计、开发、排查线上问题的高级 Java 工程师」
> 选型基线：Java 21 LTS（兼顾 Java 8 存量项目）· Spring Boot 3 · MyBatis-Plus · MySQL 8 · Redis · RocketMQ（兼讲 Kafka）· Spring Cloud Alibaba · XXL-Job

---

## 1. 先建立全景图：一个请求在 Java 后端里走了哪些路

前端视角下，你熟悉的是「浏览器发出请求 → 拿到 JSON → 渲染」。服务端要回答的是：**这个 JSON 是怎么来的？**

```
浏览器 / App
   │  HTTPS
   ▼
Nginx / SLB（负载均衡、HTTPS 卸载、静态资源）               ← 你熟悉：前端部署也经过这里
   │
   ▼
API 网关 Spring Cloud Gateway（鉴权、限流、路由）           ← 类比：BFF / 前端请求拦截器
   │
   ▼
┌──────────────── 订单服务（一个 Spring Boot 进程，跑在 JVM 上）────────────────┐
│ Filter 过滤器链（编码、跨域、TraceId）                    ← 类比：Koa 洋葱中间件 │
│   ▼                                                                             │
│ Interceptor 拦截器（登录态、权限）                                              │
│   ▼                                                                             │
│ ① 接口层 Controller：解析参数、校验、调用编排层          ← 类比：Express 路由   │
│   ▼                                                                             │
│ ② 编排层 Component：按业务流程组合能力                    ← 类比：页面容器组件  │
│   ▼                                                                             │
│ ③ 功能单元：聚合多表的完整功能，带事务                    ← 类比：自定义 hooks  │
│   ▼                                                                             │
│ ④ 能力单元：DAO（MyBatis-Plus）、三方接口调用 Client     ← 类比：api/ 请求层    │
│   ▼                                                                             │
│ ⑤ 工具层：转换、校验、工具函数                            ← 类比：utils/        │
└──────┬─────────────┬───────────────┬──────────────────┬──────────────────────┘
       ▼             ▼               ▼                  ▼
     MySQL         Redis         RocketMQ          其他微服务（OpenFeign 调用）
   （持久化）     （缓存/锁）    （异步/解耦）        （注册发现：Nacos）

旁路：日志(ELK) · 监控(Prometheus+Grafana) · 链路追踪(SkyWalking) · 定时任务(XXL-Job)
底座：Docker 镜像 → K8s 部署 → CI/CD 流水线
```

**理解这张图就理解了本系列的组织方式**：01-05 章讲「JVM 进程本身」（语言、运行时、工程化），06-07 章讲「进程内的框架」（Spring），08-10 章讲「进程外的中间件」，11-12 章讲「多个进程如何协作与上线」，13 章讲「如何设计整个系统」。

---

## 2. 学习路线（建议 4 个阶段，约 4～6 个月）

| 阶段 | 章节 | 时长 | 阶段目标（检验标准） |
|---|---|---|---|
| **一、语言与运行时** | 01 语言基础 · 02 集合与 API · 03 JVM · 04 并发 | 4～6 周 | 能写出无明显坏味道的 Java 代码；能讲清 HashMap、GC、线程池原理 |
| **二、工程与框架** | 05 工程化 · 06 Spring 核心 · 07 Spring Boot Web | 3～4 周 | 能从零搭一个分层清晰的 Spring Boot 项目，写出 CRUD + 校验 + 统一异常 + 单测 |
| **三、中间件** | 08 数据库 · 09 Redis · 10 消息队列 | 4～6 周 | 能设计索引、写出合格 SQL；能正确使用缓存与 MQ 并处理一致性、幂等问题 |
| **四、分布式与架构** | 11 微服务 · 12 运维可观测 · 13 高级工程师 | 4～6 周 | 能拆分服务、处理分布式事务；能独立排查线上故障；能完成一道系统设计题 |

> 建议：每章读完后，**在贯穿项目里把对应部分亲手写一遍**。看懂 ≠ 会写，会写 ≠ 能排查。

---

## 3. 前端 → Java 概念映射总表

> 这张表是你的「翻译词典」。类比只帮你建立第一印象，**每一项的差异点才是重点**，各章会展开。

### 3.1 语言层

| 前端（JS/TS） | Java | 关键差异 | 章节 |
|---|---|---|---|
| `let` / `const` | 局部变量 / `final` | Java 有 `var`（Java 10+）但仍是静态类型，类型推断只在编译期 | 01 |
| `number` | `int` / `long` / `double` / `BigDecimal` | Java 区分整数/浮点/精度；**金额必须用 BigDecimal** | 01 |
| `string` | `String` | 不可变；比较内容用 `equals`，`==` 比较的是引用 | 01 |
| `null` / `undefined` | `null` | 只有 null；NPE 是头号异常 | 01 |
| `a?.b ?? c` | `Optional.ofNullable(a).map(..).orElse(c)` | Optional 只建议作返回值，不作字段/参数 | 01 |
| TS `interface`（结构化类型） | `interface`（名义类型） | Java 必须显式 `implements`，「长得像」不算 | 01 |
| TS `type` 联合类型 `'A' \| 'B'` | `enum` | Java 枚举是完整的类，可有字段和方法 | 01 |
| TS 泛型 `<T>` | 泛型 `<T>` | 都在编译期检查；Java 运行时**类型擦除**，不能 `new T()` | 01 |
| `class` / `extends` | `class` / `extends` | 单继承 + 多接口；有访问修饰符 public/protected/默认/private | 01 |
| 纯数据对象 `{a:1}` | `record` / POJO + Lombok | Java 没有对象字面量，数据要先定义类 | 01 |
| `arr.map().filter().reduce()` | `list.stream().map().filter().reduce()` | Stream 惰性求值、只能消费一次 | 01/02 |
| 箭头函数 | Lambda `x -> x * 2` | Lambda 只能实现**函数式接口**；捕获的变量须 effectively final | 01 |
| `try/catch` | `try/catch/finally` + `throws` | Java 有受检异常，编译器强制处理 | 01 |
| `Array` | `ArrayList` / 数组 `int[]` | 数组定长；日常用 `List` | 02 |
| `Map` / 对象 | `HashMap` / `LinkedHashMap` / `TreeMap` | 按「是否有序、是否线程安全」选实现 | 02 |
| `Set` | `HashSet` / `TreeSet` | 依赖 `equals` + `hashCode` 判重 | 02 |
| `Date` / dayjs | `java.time`（`LocalDateTime` 等） | 别用老的 `Date` / `SimpleDateFormat`（线程不安全） | 02 |
| `JSON.stringify/parse` | Jackson `ObjectMapper` | 需映射到具体类 | 02/07 |

### 3.2 运行时与并发

| 前端 | Java | 关键差异 | 章节 |
|---|---|---|---|
| V8 引擎 | JVM（HotSpot） | 先编译成字节码 `.class`，再由 JVM 解释 + JIT | 03 |
| V8 堆 / 新生代老生代 GC | JVM 堆 / 分代 GC（G1、ZGC） | 服务端进程常驻数月，GC 调优是必修课 | 03 |
| Chrome DevTools Memory | jmap / MAT / Arthas | 线上排查靠命令行工具 | 03 |
| 单线程 + 事件循环 | 多线程（线程池） | **共享内存 + 多线程 = 线程安全问题**，前端几乎没有 | 04 |
| `Promise` | `CompletableFuture` | 类似链式；但回调可能在别的线程执行 | 04 |
| `Promise.all` | `CompletableFuture.allOf` | — | 04 |
| `async/await` | 虚拟线程（Java 21）/ 同步阻塞写法 | Java 传统写法就是同步阻塞，靠多线程并发 | 04 |
| Web Worker | `Thread` / `ExecutorService` | Worker 不共享内存，Java 线程共享 | 04 |
| — | `synchronized` / `Lock` / `volatile` / CAS | 前端无对应概念，必须从零学 | 04 |

### 3.3 工程化

| 前端 | Java | 关键差异 | 章节 |
|---|---|---|---|
| npm / pnpm | Maven / Gradle | Maven 用 XML 声明，约定优于配置 | 05 |
| `package.json` | `pom.xml` | 有 groupId:artifactId:version 坐标 | 05 |
| `node_modules` | `~/.m2/repository` | 本地全局仓库，所有项目共享 | 05 |
| `package-lock.json` | 无锁文件；靠 `dependencyManagement` / BOM 锁版本 | 依赖冲突按「最短路径优先」裁决 | 05 |
| monorepo（pnpm workspace） | Maven 多模块（parent + modules） | — | 05 |
| `npm run build` | `mvn clean package` → 产出 `.jar` | 一个 fat jar 就能 `java -jar` 运行 | 05 |
| Jest / Vitest | JUnit 5 + Mockito + AssertJ | — | 05 |
| console.log | SLF4J + Logback | 分级别、按文件滚动、带 TraceId | 05 |
| ESLint / Prettier | Checkstyle / Spotless / 阿里 P3C | — | 05 |
| `.env` | `application.yml` + `application-{profile}.yml` | 配置中心（Nacos）可动态刷新 | 07/11 |

### 3.4 框架与架构

| 前端 | Java | 关键差异 | 章节 |
|---|---|---|---|
| NestJS / Angular DI | Spring IoC 容器 | Spring 是这套思想的鼻祖 | 06 |
| `@Injectable()` | `@Component` / `@Service` | — | 06 |
| 装饰器 / 高阶函数包装 | AOP（动态代理） | 事务、日志、权限都靠它 | 06 |
| — | `@Transactional` 声明式事务 | 有大量「失效」坑 | 06 |
| Express / Koa / NestJS | Spring MVC（Spring Boot Web） | — | 07 |
| `app.get('/x', handler)` | `@GetMapping("/x")` | — | 07 |
| 中间件 | Filter（Servlet 级）/ Interceptor（Spring 级） | 两层，执行时机不同 | 07 |
| zod / yup 校验 | Bean Validation（`@NotNull`、`@Valid`） | — | 07 |
| TS 类型：请求/响应/表单 | DTO / VO / PO(Entity) | 按层分对象，不混用 | 07 |
| Prisma / TypeORM | MyBatis-Plus / JPA | 国内主流 MyBatis-Plus | 08 |
| localStorage / HTTP 缓存 | Redis | 分布式共享、有过期、需考虑一致性 | 09 |
| EventEmitter / 发布订阅 | RocketMQ / Kafka | 跨进程、持久化、要处理丢失与重复 | 10 |
| 微前端 | 微服务 | 拆分维度：业务边界 | 11 |
| BFF | API 网关 | — | 11 |
| `setInterval` | XXL-Job 分布式定时任务 | 多实例下只跑一次 | 11 |
| Sentry / 前端监控 | Prometheus + Grafana + SkyWalking + ELK | — | 12 |

---

## 4. 贯穿项目：mini-mall 简易电商订单系统

所有章节的示例都围绕这个项目，**领域模型、表结构、命名在各章保持一致**。

### 4.1 基本约定

- 项目名：`mini-mall`；根包名：`com.example.mall`
- 技术：Java 21、Spring Boot 3.x、MyBatis-Plus、MySQL 8、Redis、RocketMQ
- 分层包结构（单体阶段）：

```
com.example.mall
├── controller        ① 接口层：OrderController
├── biz               ② 编排层：OrderBizComponent
├── domain            ③ 功能单元：OrderCreateUnit（下单：写订单+明细+扣库存，带事务）
├── dao               ④ 能力单元：OrderDao / ProductDao（封装 Mapper）
│   └── mapper           MyBatis-Plus Mapper 接口
├── client            ④ 三方/远程调用：PayClient
├── convert           ⑤ 转换器：OrderConverter（DTO ↔ PO ↔ VO）
├── util              ⑤ 工具
├── model
│   ├── dto           入参：CreateOrderDTO
│   ├── vo            出参：OrderVO
│   ├── po            表实体：OrderPO、OrderItemPO、ProductPO、UserPO
│   └── enums         OrderStatusEnum
└── common            统一返回 Result<T>、全局异常 BizException、错误码 ErrorCode
```

### 4.2 领域模型与表

| 表 | 关键字段 | 说明 |
|---|---|---|
| `t_user` | id, username, phone, create_time, update_time | 用户 |
| `t_product` | id, name, price `DECIMAL(10,2)`, stock `INT`, version, create_time, update_time | 商品（version 用于乐观锁） |
| `t_order` | id, order_no `VARCHAR(32)` 唯一, user_id, total_amount `DECIMAL(10,2)`, status `TINYINT`, create_time, update_time | 订单 |
| `t_order_item` | id, order_id, product_id, product_name, price, quantity, create_time | 订单明细 |

订单状态枚举 `OrderStatusEnum`：

| code | 枚举 | 含义 |
|---|---|---|
| 0 | CREATED | 待支付 |
| 1 | PAID | 已支付 |
| 2 | CANCELLED | 已取消（超时或主动） |
| 3 | SHIPPED | 已发货 |
| 4 | COMPLETED | 已完成 |

统一返回：`Result<T> { int code; String message; T data; }`

**全书统一命名约定**（各章示例以此为准）：

| 类别 | 约定 |
|---|---|
| 错误码 `ErrorCode` | 号段：0 成功；1xxxx 通用/参数/鉴权；2xxxx 商品；3xxxx 订单；9xxxx 系统/远程。完整清单见 07 章 |
| 入参 | `CreateOrderDTO { List<OrderItemDTO> items }`，用户 ID 不放入参，由登录拦截器写入 `UserContext` |
| 订单状态更新 | `OrderDao.updateStatus(..., from, to)`：条件更新（`WHERE status = from`），状态机防并发 |
| 库存 | `ProductDao.deductStock / deductStockWithVersion / restoreStock`，扣减按商品 ID 升序防死锁 |
| 表字段补充 | 08 章为 `t_user`、`t_product` 增加 `deleted` 逻辑删除列；`t_order` 建 `idx_user_create_time`、`idx_status_create_time` |
| Redis key | 统一由 09 章 `RedisKeys` 生成，前缀 `mall:` |

### 4.3 每章为项目添加的能力

| 章 | 在 mini-mall 中做什么 |
|---|---|
| 01 | 定义 `OrderStatusEnum`、`OrderPO` 等领域类；用 Stream 计算订单总额 |
| 02 | 用集合做订单分组统计（按用户、按状态）；分析 HashMap 存订单的注意点 |
| 03 | 复现「一次性加载百万订单导致 OOM」并用工具定位 |
| 04 | 订单详情页并行查询用户/商品/物流（CompletableFuture）；自定义线程池做订单导出；并发扣库存的线程安全问题 |
| 05 | 用 Maven 搭建项目骨架、配置日志、给下单逻辑写单测 |
| 06 | 用 IoC 组装 Service；用 AOP 记录接口耗时；下单事务与「事务失效」演示 |
| 07 | 实现「创建订单 / 查询订单」接口：参数校验、统一返回、全局异常、登录拦截器、五层落位 |
| 08 | 建表 DDL、索引设计、MyBatis-Plus 实现 DAO、乐观锁扣库存、分页查询与慢 SQL 优化 |
| 09 | 商品详情缓存（旁路缓存）；Redis + Lua 预扣库存；Redisson 防重复下单 |
| 10 | 下单成功发消息（通知、积分）；延迟消息实现「30 分钟未支付自动取消」；消费幂等 |
| 11 | 拆分为 user / product / order 服务 + 网关；OpenFeign 调用；Seata 或本地消息表保证下单一致性；XXL-Job 对账 |
| 12 | Dockerfile、K8s 部署、接入 Prometheus 监控与日志；一次线上 CPU 飙高排查演练 |
| 13 | 秒杀系统设计；整体架构复盘；面试题汇总 |

---

## 5. 各章统一结构

每一章按如下顺序组织，阅读时可以按需跳读：

1. **本章地图**：本章解决什么问题、在全景图中的位置
2. **前端类比**：用你熟悉的概念建立第一印象
3. **核心概念**：是什么、怎么用（附 TS ↔ Java 对照代码）
4. **原理深挖**：为什么这样设计、底层怎么实现
5. **mini-mall 实战**：在贯穿项目中落地
6. **常见坑**：新手和转岗者最容易犯的错误
7. **高级视角**：高级工程师需要额外掌握的东西
8. **小练习**：动手验证

> 面试题统一汇总在 [13 章](./13-senior-engineer.md)。

---

## 6. 章节目录

| # | 文档 | 一句话 |
|---|---|---|
| 01 | [Java 语言基础](./01-java-basics.md) | 用 TS 的眼睛看 Java：类型、类、泛型、Lambda、异常 |
| 02 | [集合框架与常用 API](./02-collections-and-api.md) | List/Map/Set 选型与原理，时间、IO、JSON |
| 03 | [JVM 原理](./03-jvm.md) | 内存区域、类加载、GC、调优与故障排查 |
| 04 | [并发编程](./04-concurrency.md) | 从事件循环到多线程：线程池、锁、JMM、CompletableFuture、虚拟线程 |
| 05 | [工程化](./05-engineering.md) | Maven、多模块、日志、Lombok、单元测试 |
| 06 | [Spring 核心](./06-spring-core.md) | IoC、Bean 生命周期、AOP、事务 |
| 07 | [Spring Boot 与 Web 开发](./07-spring-boot-web.md) | 自动配置、接口开发全套、五层分层架构 |
| 08 | [数据库与持久层](./08-database-orm.md) | MySQL 索引/事务/锁 + MyBatis-Plus |
| 09 | [Redis 与缓存](./09-redis-cache.md) | 数据结构、缓存三大问题、一致性、分布式锁 |
| 10 | [消息队列](./10-message-queue.md) | RocketMQ/Kafka、可靠投递、幂等、延迟消息 |
| 11 | [微服务与分布式](./11-microservices.md) | Spring Cloud Alibaba、分布式事务、分布式 ID、定时任务 |
| 12 | [部署、监控与线上排查](./12-devops-observability.md) | Docker、K8s、CI/CD、日志监控、故障排查 SOP |
| 13 | [高级工程师之路](./13-senior-engineer.md) | 设计模式、DDD、系统设计、性能调优、面试题汇总 |

---

## 7. 从「会写」到「高级」：能力模型

| 级别 | 关键能力 |
|---|---|
| 初级 | 能按规范写 CRUD；会用 Spring Boot、MyBatis-Plus；能看懂异常堆栈 |
| 中级 | 能独立负责模块；懂索引与事务、会用缓存和 MQ 并处理常见问题；能写单测 |
| 高级 | 能做技术方案（接口、表、组件、链路四要素）；能处理并发、一致性、性能问题；能独立排查线上故障；懂 JVM 与框架原理 |
| 资深/架构 | 能做系统拆分与演进规划；对稳定性、成本、效率有全局判断；能带团队落地规范 |

> 前端转岗的优势：对接口契约、用户体验、工程化有天然敏感度。
> 需要刻意补的短板：**多线程思维、数据一致性思维、「线上永远会出事」的防御思维**。
