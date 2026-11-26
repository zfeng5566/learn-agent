# 13 高级工程师之路：设计模式、架构、系统设计与面试题汇总

> [← 总纲](./00-outline.md) | [上一章：部署、监控与线上排查](./12-devops-observability.md)

---

## 本章地图

前 12 章解决的是「**会用**」：语言、JVM、并发、Spring、MySQL、Redis、MQ、微服务、上线排查。本章解决的是「**会设计、能扛事**」：

```
                        ┌─────────────────────────────────────┐
  第一部分 能力篇        │  思维：前端思维 → 服务端思维          │  §1
                        │  代码：设计模式 · SOLID · 五层架构    │  §2 §3
                        │  建模：DDD 入门                       │  §4
                        │  方案：技术方案四要素 + 完整示例       │  §5
                        │  系统：设计方法论 · 三板斧 · 设计题    │  §6 §7
                        │  质量：性能调优 · Code Review          │  §8 §9
                        │  成长：误区 · 学习建议 · 书单          │  §10
                        └─────────────────────────────────────┘
                        ┌─────────────────────────────────────┐
  第二部分 面试题汇总    │  12 类 · 约 130 题 · 难度 ★/★★/★★★    │  §11
                        └─────────────────────────────────────┘
```

| 级别 | 写代码时在想什么 |
|---|---|
| 中级 | 功能能不能跑通、SQL 对不对 |
| 高级 | 并发下会不会错、失败了怎么办、量涨 10 倍扛不扛得住、半年后谁来改、出事了怎么查 |

---

# 第一部分 能力篇

## 1. 从前端思维到服务端思维

### 1.1 四个根本差异

| 维度 | 前端（浏览器） | 服务端（JVM 集群） | 带来的问题 |
|---|---|---|---|
| 运行实例 | 每个用户一个独立页面实例 | 一份代码 N 个实例，服务所有用户 | 内存状态不能共享，必须无状态 |
| 并发模型 | 单线程事件循环 | 多线程共享内存，同一时刻上百请求 | 线程安全、竞态、死锁 |
| 数据归属 | 数据是后端给的「副本」，刷新即恢复 | 数据库就是「真相之源」，写错不可逆 | 一致性、事务、幂等 |
| 失败代价 | 一个用户白屏，刷新重试 | 全站故障、资损、数据错乱 | 防御式编程、降级、可观测 |

### 1.2 无状态与多实例

前端里把数据放 `useState`、全局 store 天经地义；服务端里把数据放在 JVM 内存（静态 Map、单例字段）几乎都是 bug。

```
              ┌──► 实例 A（内存 Map：用户1 的验证码）
  SLB 轮询 ───┼──► 实例 B（内存 Map：空）   ← 用户1 第二次请求打到这里：验证码不存在
              └──► 实例 C（内存 Map：空）
```

```ts
// 前端：模块级变量缓存，单页面内没问题
const codeCache = new Map<string, string>();
export function saveCode(phone: string, code: string) {
  codeCache.set(phone, code);
}
```

```java
/**
 * 验证码存储组件：状态外置到 Redis，任意实例都能读到，保证服务无状态。
 */
@Component
@RequiredArgsConstructor
public class SmsCodeStore {

    private static final String KEY_PREFIX = "mall:sms:code:";
    private final StringRedisTemplate redisTemplate;

    /**
     * 保存验证码。
     *
     * @param phone 手机号
     * @param code  验证码
     */
    public void save(String phone, String code) {
        // 5 分钟过期，避免永久占用内存
        redisTemplate.opsForValue().set(KEY_PREFIX + phone, code, Duration.ofMinutes(5));
    }

    /**
     * 读取验证码。
     *
     * @param phone 手机号
     * @return 验证码，不存在或已过期返回 null
     */
    public String get(String phone) {
        return redisTemplate.opsForValue().get(KEY_PREFIX + phone);
    }
}
```

**无状态检查清单**：会话 → Redis/JWT；本地缓存 → 能接受短暂不一致才用（Caffeine + 短 TTL）；定时任务 → XXL-Job 保证只跑一次；本地锁 `synchronized` → 多实例下失效，换分布式锁；上传文件 → 对象存储而非本地磁盘。

### 1.3 并发与一致性

前端「先读后写」没有问题，服务端「先读后写」就是经典竞态：

```
时间 →   线程 A                     线程 B
         读 stock = 1
                                    读 stock = 1
         判断 1 > 0，写 stock = 0
                                    判断 1 > 0，写 stock = 0   ← 超卖：卖出 2 件
```

三种解法，从轻到重：

| 方案 | 写法 | 适用 |
|---|---|---|
| 数据库原子条件更新 | `UPDATE t_product SET stock = stock - #{n} WHERE id = #{id} AND stock >= #{n}` | 首选，简单可靠 |
| 乐观锁 | `... SET stock = ?, version = version + 1 WHERE id = ? AND version = ?` | 冲突少、需要复杂计算 |
| 分布式锁 | Redisson `RLock` 包住「读-算-写」 | 跨多资源、无法用一条 SQL 表达 |

### 1.4 防御式编程：不信任任何输入

前端的校验是**体验**，后端的校验是**安全**——前端校验可以被 curl 绕过。

| 防线 | 做法 |
|---|---|
| 入参 | `@Valid` + Bean Validation；数量、金额要校验上下界；分页 `pageSize` 设上限 |
| 权限 | 越权校验：查订单必须带 `user_id = 当前用户`，不能只按 `order_no` 查 |
| 外部调用 | 必设超时（连接 + 读）、有限重试、熔断；把返回值当不可信数据判空 |
| 重复请求 | 接口幂等（token / 唯一键 / 状态机） |
| 数据量 | 禁止无条件全表查询；批量操作分批 |
| 金额 | 只用 `BigDecimal`，用 `compareTo` 比较 |

### 1.5 「线上一定会出事」

墨菲定律在服务端是日常：网络会抖、依赖会挂、磁盘会满、消息会重复、时钟会漂移、上游会突然 10 倍流量。高级工程师写每段代码时都要回答：

```
这一步失败了会怎样？ ──► 是否可重试？重试是否幂等？
                    ──► 是否需要补偿？谁来补偿（定时任务对账）？
                    ──► 用户看到什么？（降级文案、兜底数据）
                    ──► 我怎么知道它失败了？（日志 + 监控 + 告警）
                    ──► 我怎么快速止血？（开关、限流、回滚）
```

---

## 2. 设计模式在 Java/Spring 中的落地

> 原则：模式是为了**隔离变化**，不是为了炫技。两个分支的 if-else 不需要策略模式。

### 2.0 总览

| 模式 | Spring/JDK 中的典型落地 | 前端对应物 |
|---|---|---|
| 单例 | Spring Bean 默认 singleton | ES Module 导出的实例、Pinia store |
| 工厂 | `BeanFactory`、`FactoryBean` | `createApp()`、`React.createElement` |
| 策略 | `Map<String, Strategy>` 注入 | 对象映射表 `{ alipay: fn, wechat: fn }` |
| 模板方法 | `JdbcTemplate`、`AbstractApplicationContext.refresh()` | React 类组件生命周期 |
| 责任链 | Servlet `Filter` 链、Spring Security | Koa/Express 中间件、axios 拦截器 |
| 观察者 | `ApplicationEvent` + `@EventListener` | `EventEmitter`、`addEventListener` |
| 代理 | AOP（JDK 动态代理 / CGLIB） | ES6 `Proxy`、Vue 3 响应式 |
| 适配器 | `HandlerAdapter`、三方 SDK 封装 | 接口数据适配层 `adaptUser(raw)` |
| 建造者 | Lombok `@Builder`、`WebClient.builder()` | 链式配置 `yup.string().min(1).max(10)` |

### 2.1 单例

```ts
// 前端：ES Module 天然单例
export const http = axios.create({ baseURL: '/api' });
```

```java
/**
 * 饿汉式单例（非 Spring 环境下的写法），类加载时初始化，JVM 保证线程安全。
 */
public final class IdGenerator {

    private static final IdGenerator INSTANCE = new IdGenerator();

    private IdGenerator() {
    }

    /**
     * 获取单例实例。
     *
     * @return 全局唯一的 IdGenerator
     */
    public static IdGenerator getInstance() {
        return INSTANCE;
    }
}
```

**Spring 里的要点**：你几乎不用手写单例，`@Component` 默认就是单例。但随之而来的是：**单例 Bean 被所有线程共享，不能有可变的成员字段**（例如把当前用户 ID 存在 Service 字段里）。需要线程级状态时用方法局部变量或 `ThreadLocal`（用完必须 `remove()`，否则线程池复用导致串号）。

### 2.2 工厂

```java
/**
 * 订单号工厂：集中封装订单号生成规则，调用方不关心具体格式。
 */
@Component
public class OrderNoFactory {

    /**
     * 生成订单号：yyyyMMddHHmmss + 6 位随机数，总长 20 位，满足 order_no VARCHAR(32)。
     *
     * @return 新订单号
     */
    public String create() {
        String time = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMddHHmmss"));
        // ThreadLocalRandom 在多线程下无竞争，比 new Random() 更合适
        int random = ThreadLocalRandom.current().nextInt(100_000, 1_000_000);
        return time + random;
    }
}
```

> 生产中订单号通常用雪花算法（见 11 章），这里只演示「创建逻辑收敛到一处」。Spring 的 `FactoryBean` 用于创建复杂对象（如 MyBatis 的 `SqlSessionFactoryBean`），名字以 `&` 前缀可取到工厂本身。

### 2.3 策略 + Spring 注入 Map：消除 if-else

**场景**：mini-mall 支持支付宝、微信、余额三种支付方式，后续还会加。

```ts
// 前端：对象映射表消除 switch
const payHandlers: Record<string, (orderNo: string) => Promise<string>> = {
  alipay: (no) => payByAlipay(no),
  wechat: (no) => payByWechat(no),
};
export const pay = (channel: string, no: string) => payHandlers[channel](no);
```

```java
/**
 * 支付策略接口：每种支付渠道一个实现。
 */
public interface PayStrategy {

    /**
     * 发起支付。
     *
     * @param orderNo 订单号
     * @param amount  支付金额
     * @return 支付流水号
     */
    String pay(String orderNo, BigDecimal amount);
}

/**
 * 支付宝支付策略。bean 名 "alipay" 即策略 key。
 */
@Component("alipay")
@RequiredArgsConstructor
public class AlipayStrategy implements PayStrategy {

    private final PayClient payClient;

    /**
     * 调用支付宝渠道发起支付。
     *
     * @param orderNo 订单号
     * @param amount  支付金额
     * @return 支付流水号
     */
    @Override
    public String pay(String orderNo, BigDecimal amount) {
        return payClient.alipay(orderNo, amount);
    }
}

/**
 * 支付路由组件：根据渠道选择策略，新增渠道只需新增一个实现类，本类无需修改（开闭原则）。
 */
@Component
@RequiredArgsConstructor
public class PayRouter {

    /**
     * 所有 PayStrategy 实现。
     * key：Spring bean 名（即 @Component("alipay") 中的值）；value：对应的策略实例。
     * Spring 会自动把容器中所有 PayStrategy 类型的 bean 注入到这个 Map。
     */
    private final Map<String, PayStrategy> strategyMap;

    /**
     * 按渠道发起支付。
     *
     * @param channel 支付渠道，取值为策略 bean 名：alipay / wechat / balance
     * @param orderNo 订单号
     * @param amount  支付金额
     * @return 支付流水号
     */
    public String pay(String channel, String orderNo, BigDecimal amount) {
        PayStrategy strategy = strategyMap.get(channel);
        // 未知渠道直接抛业务异常，不做默认兜底，避免把钱付到错误渠道
        if (strategy == null) {
            throw new BizException(ErrorCode.PARAM_ERROR, "不支持的支付渠道: " + channel);
        }
        return strategy.pay(orderNo, amount);
    }
}
```

> 变体：如果不想让 bean 名耦合业务编码，可以在接口上加 `String channel()` 方法，启动时 `List<PayStrategy>` 转成 `Map<String, PayStrategy>`（key 为 `channel()` 返回值）。

### 2.4 模板方法

**JdbcTemplate** 把「获取连接 → 创建语句 → 执行 → 处理异常 → 释放连接」固定下来，只把「SQL + 结果映射」留给你——就是模板方法（配合回调）。

```ts
// 前端：React 类组件，框架定义骨架，你填钩子
class OrderPage extends React.Component {
  componentDidMount() { /* 子类填充 */ }
  render() { return <div />; }
}
```

```java
/**
 * 订单导出模板：固定「查询 → 转换 → 写文件 → 记录日志」骨架，子类只实现差异步骤。
 *
 * @param <T> 导出的行数据类型
 */
public abstract class AbstractOrderExporter<T> {

    /**
     * 导出主流程（final 防止子类篡改骨架）。
     *
     * @param userId 用户 ID
     * @return 生成的文件路径
     */
    public final String export(Long userId) {
        // 1. 查询数据：由子类决定查哪些订单
        List<T> rows = query(userId);
        // 2. 写文件：通用逻辑，所有导出共享
        String path = writeCsv(rows);
        // 3. 钩子：子类可选覆盖
        afterExport(path);
        return path;
    }

    /**
     * 查询待导出数据。
     *
     * @param userId 用户 ID
     * @return 行数据列表
     */
    protected abstract List<T> query(Long userId);

    /**
     * 把一行数据转成 CSV 文本行。
     *
     * @param row 行数据
     * @return CSV 行
     */
    protected abstract String toCsvLine(T row);

    /**
     * 导出完成后的钩子，默认空实现。
     *
     * @param path 文件路径
     */
    protected void afterExport(String path) {
    }

    /**
     * 通用写文件逻辑。
     *
     * @param rows 行数据
     * @return 文件路径
     */
    private String writeCsv(List<T> rows) {
        Path file = Path.of("/tmp", "export-" + System.currentTimeMillis() + ".csv");
        List<String> lines = rows.stream().map(this::toCsvLine).toList();
        try {
            Files.write(file, lines);
        } catch (IOException e) {
            throw new UncheckedIOException("导出写文件失败", e);
        }
        return file.toString();
    }
}
```

### 2.5 责任链

```ts
// 前端：Koa 洋葱模型
app.use(async (ctx, next) => {
  const start = Date.now();
  await next();
  console.log(`${ctx.path} ${Date.now() - start}ms`);
});
```

```java
/**
 * TraceId 过滤器：Servlet Filter 链中的一环，为每个请求生成链路 ID 写入 MDC。
 */
@Component
@Order(1)
public class TraceIdFilter extends OncePerRequestFilter {

    /**
     * 过滤逻辑：前置写入 TraceId，调用下一环，后置清理。
     *
     * @param request  请求
     * @param response 响应
     * @param chain    过滤器链，调用 doFilter 即「next()」
     */
    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String traceId = Optional.ofNullable(request.getHeader("X-Trace-Id"))
                .orElse(UUID.randomUUID().toString().replace("-", ""));
        MDC.put("traceId", traceId);
        try {
            // 相当于 await next()
            chain.doFilter(request, response);
        } finally {
            // 线程池复用线程，必须清理，否则下一个请求串号
            MDC.remove("traceId");
        }
    }
}
```

业务里的责任链：下单前校验「用户状态 → 商品上架 → 库存 → 限购 → 风控」，每个校验器实现同一接口，`List<OrderChecker>` 注入后按 `@Order` 顺序遍历执行，新增校验只加类。

### 2.6 观察者：ApplicationEvent

```ts
// 前端：EventEmitter
emitter.on('order:paid', (orderNo) => sendSms(orderNo));
emitter.emit('order:paid', 'NO123');
```

```java
/**
 * 订单支付成功事件。
 *
 * @param orderNo 订单号
 * @param userId  用户 ID
 */
public record OrderPaidEvent(String orderNo, Long userId) {
}

/**
 * 发布方：支付成功后发布事件，不关心谁在监听。
 */
@Component
@RequiredArgsConstructor
public class OrderPayBizComponent {

    private final ApplicationEventPublisher publisher;

    /**
     * 支付成功后的处理。
     *
     * @param orderNo 订单号
     * @param userId  用户 ID
     */
    @Transactional(rollbackFor = Exception.class)
    public void onPaid(String orderNo, Long userId) {
        // ... 更新订单状态为 PAID(1)
        publisher.publishEvent(new OrderPaidEvent(orderNo, userId));
    }
}

/**
 * 监听方：积分发放。
 */
@Component
@Slf4j
public class PointsListener {

    /**
     * 事务提交后再执行，避免订单回滚了积分却发了。
     *
     * @param event 支付成功事件
     */
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(OrderPaidEvent event) {
        log.info("发放积分, orderNo={}", event.orderNo());
    }
}
```

| 进程内事件 ApplicationEvent | 跨进程消息 RocketMQ |
|---|---|
| 同 JVM，默认同步执行 | 跨服务，异步 |
| 进程挂了事件就丢 | 持久化，可重试 |
| 适合：模块解耦、非关键旁路逻辑 | 适合：关键业务、跨服务通知 |

### 2.7 代理：AOP

```ts
// 前端：Proxy 拦截属性访问（Vue 3 响应式原理）
const proxied = new Proxy(target, {
  get(t, key) { console.log('get', key); return Reflect.get(t, key); },
});
```

```java
/**
 * 接口耗时切面：代理所有 Controller 方法，记录耗时。
 */
@Aspect
@Component
@Slf4j
public class CostLogAspect {

    /**
     * 环绕通知。
     *
     * @param pjp 连接点，proceed() 调用被代理的原方法
     * @return 原方法返回值
     * @throws Throwable 原方法抛出的异常原样抛出
     */
    @Around("execution(* com.example.mall.controller..*(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        long start = System.currentTimeMillis();
        try {
            return pjp.proceed();
        } finally {
            log.info("{} cost={}ms", pjp.getSignature().toShortString(),
                    System.currentTimeMillis() - start);
        }
    }
}
```

> 这里返回 `Object` 是 AOP 框架 API 的约束（被代理方法返回值类型不定），不属于「用 Object 充当数据结构」。
> 代理的经典坑：**同类内部 `this.method()` 调用不经过代理**，所以 `@Transactional`、`@Async`、`@Cacheable` 都会失效。

### 2.8 适配器

**场景**：物流查询要对接顺丰、中通两家，返回结构完全不同，业务层只想看到统一的 `LogisticsVO`。

```ts
// 前端：接口适配层
const adaptTrace = (raw: SfResp): Trace => ({ status: raw.st, time: raw.ts });
```

```java
/**
 * 物流查询统一接口（目标接口）。
 */
public interface LogisticsAdapter {

    /**
     * 查询物流轨迹。
     *
     * @param waybillNo 运单号
     * @return 统一结构的物流信息
     */
    LogisticsVO query(String waybillNo);
}

/**
 * 顺丰适配器：把顺丰 SDK 的返回结构转换为统一结构。
 */
@Component("sf")
@RequiredArgsConstructor
public class SfLogisticsAdapter implements LogisticsAdapter {

    private final SfClient sfClient;

    /**
     * 调用顺丰接口并适配。
     *
     * @param waybillNo 运单号
     * @return 统一结构的物流信息
     */
    @Override
    public LogisticsVO query(String waybillNo) {
        SfTraceResp resp = sfClient.queryTrace(waybillNo);
        // 字段名、状态码映射到统一模型
        return new LogisticsVO(waybillNo, resp.getRouteStatus(), resp.getAcceptTime());
    }
}
```

Spring MVC 的 `HandlerAdapter` 也是同理：Controller 可以是注解方法、`HttpRequestHandler` 等多种形态，`DispatcherServlet` 通过适配器统一调用。

### 2.9 建造者

```ts
// 前端：链式构建
const schema = yup.object({ name: yup.string().required().max(20) });
```

```java
/**
 * 订单查询条件，字段多且大多可选，用建造者构造。
 *
 * @param userId    用户 ID，必填
 * @param status    订单状态码，见 OrderStatusEnum，可选
 * @param beginTime 创建时间起，可选
 * @param endTime   创建时间止，可选
 */
@Builder
public record OrderQuery(Long userId, Integer status, LocalDateTime beginTime, LocalDateTime endTime) {
}

// 使用：可读性远好于 4 个参数的构造器
OrderQuery query = OrderQuery.builder()
        .userId(1001L)
        .status(OrderStatusEnum.CREATED.getCode())
        .build();
```

---

## 3. SOLID 原则与五层分层架构

### 3.1 SOLID 速查

| 原则 | 一句话 | Java 后端里的样子 | 前端对应 |
|---|---|---|---|
| **S** 单一职责 | 一个类只有一个变化原因 | Controller 不写业务，DAO 不写校验 | 一个组件一个职责，拆 hooks |
| **O** 开闭 | 对扩展开放，对修改关闭 | 新增支付渠道 = 新增策略类 | 插件化、render props |
| **L** 里氏替换 | 子类能无缝替换父类 | 子类不抛父类没声明的异常、不收紧入参 | 组件 props 兼容 |
| **I** 接口隔离 | 不强迫依赖用不到的方法 | 拆「读接口」和「写接口」 | props 不传一大坨 |
| **D** 依赖倒置 | 依赖抽象而非实现 | 构造器注入接口；Spring IoC | 依赖注入、Context |

### 3.2 五层架构

```
  ┌───────────────────────────────────────────────────────────┐
  │ ① 接口层  Controller / XXL-Job Handler / MQ Listener       │ 接收触发、解析入参、基础校验、翻译返回
  ├───────────────────────────────────────────────────────────┤
  │ ② 编排层  OrderBizComponent                                │ 按业务流程组合能力：顺序、分支、失败策略
  ├───────────────────────────────────────────────────────────┤
  │ ③ 功能单元层  OrderCreateUnit / OrderCancelUnit            │ 聚合多表的完整功能 + 事务，稳定契约
  ├───────────────────────────────────────────────────────────┤
  │ ④ 能力单元层  OrderDao / ProductDao / PayClient            │ 单表读写、单个三方接口
  ├───────────────────────────────────────────────────────────┤
  │ ⑤ 工具层  OrderConverter / 校验器 / 工具函数                │ 最小粒度、无业务状态
  └───────────────────────────────────────────────────────────┘
         依赖方向：自上而下单向 ↓     下层不感知上层

    越往下：越稳定、越通用、越少修改、越容易复用
    越往上：越贴近业务、越常变化
```

**核心规则**：

1. **依赖单向**：DAO 不能调 BizComponent；功能单元不能调 Controller。同层之间尽量不互调（编排层互调会形成网状依赖）。
2. **事务放在功能单元**：同时写 2 张及以上表的操作，封装为功能单元的一个方法并加 `@Transactional`。编排层不开大事务（避免把 RPC、MQ 包进事务）。
3. **业务变更优先只改编排层**：例如「下单后要额外发优惠券」——只在编排层追加一步，功能单元和 DAO 不动。
4. **同一个功能单元服务多个入口**：单条下单接口、批量导入下单、MQ 补单，都复用 `OrderCreateUnit`，各自在编排层组织流程。

| 层 | 允许做 | 禁止做 |
|---|---|---|
| ① 接口层 | `@Valid` 校验、取登录用户、调编排层、包装 `Result<T>` | 写业务分支、直接调 DAO |
| ② 编排层 | 调多个功能单元/能力单元、决定失败是忽略还是中断、发 MQ | 写 SQL、开包含 RPC 的大事务 |
| ③ 功能单元 | 多表写 + 事务、一致性保证 | 调 HTTP 三方接口（放事务里拖长事务） |
| ④ 能力单元 | 单表 CRUD、单个三方接口封装（超时/重试） | 跨表业务逻辑 |
| ⑤ 工具层 | 纯函数式转换、校验 | 依赖 Spring Bean 去查库 |

```ts
// 前端对照：同样的分层思想
// pages/OrderPage.tsx      ① 只管渲染与交互触发
// hooks/useCreateOrder.ts  ② 编排：校验 → 调接口 → 刷新列表 → toast
// services/order.ts        ④ 单个接口封装
// utils/format.ts          ⑤ 纯函数
```

---

## 4. DDD 入门

### 4.1 为什么会有 DDD

CRUD 式开发的问题：业务规则散落在各个 Service 里，`OrderPO` 只有 getter/setter（贫血模型），「订单什么状态下能取消」这种规则被复制到 5 个地方。DDD 的思路是：**让领域对象自己守护业务规则**。

### 4.2 核心概念

| 概念 | 定义 | mini-mall 示例 | 前端类比 |
|---|---|---|---|
| 实体 Entity | 有唯一标识，属性可变，按 ID 判等 | `Order`（按 orderNo 判等） | 带 id 的 store 记录 |
| 值对象 Value Object | 无标识，不可变，按值判等 | `Money(amount, currency)`、`Address` | 不可变对象 / `Object.freeze` |
| 聚合根 Aggregate Root | 一组强一致对象的入口，外部只能通过它修改内部 | `Order` 是聚合根，`OrderItem` 只能经由 `Order` 修改 | 父组件统一管理子状态 |
| 领域服务 Domain Service | 不属于任何单个实体的业务逻辑 | 跨订单与库存的「下单定价」 | 跨 store 的 action |
| 仓储 Repository | 聚合的持久化抽象 | `OrderRepository.save(order)` | 数据层 service |
| 领域事件 | 领域内发生的重要事实 | `OrderPaidEvent` | 自定义事件 |
| 限界上下文 Bounded Context | 模型的语义边界，同一个词在不同上下文含义不同 | 「商品」在商品上下文有详情图文，在订单上下文只是快照（名称+价格） | 微前端子应用边界 |

### 4.3 充血模型示例

```java
/**
 * 金额值对象：不可变，按值判等，封装金额运算规则。
 *
 * @param amount 金额，保留 2 位小数
 */
public record Money(BigDecimal amount) {

    /**
     * 构造时校验：金额不能为负。
     *
     * @param amount 金额
     */
    public Money {
        if (amount == null || amount.compareTo(BigDecimal.ZERO) < 0) {
            throw new IllegalArgumentException("金额不能为空或负数");
        }
        amount = amount.setScale(2, RoundingMode.HALF_UP);
    }

    /**
     * 金额相加，返回新对象（值对象不可变）。
     *
     * @param other 另一个金额
     * @return 相加后的新金额
     */
    public Money add(Money other) {
        return new Money(this.amount.add(other.amount));
    }
}

/**
 * 订单聚合根：状态流转规则内聚在实体内部，而不是散落在 Service。
 */
@Getter
public class Order {

    private final String orderNo;
    private OrderStatusEnum status;

    /**
     * 创建新订单，初始状态为待支付。
     *
     * @param orderNo 订单号
     */
    public Order(String orderNo) {
        this.orderNo = orderNo;
        this.status = OrderStatusEnum.CREATED;
    }

    /**
     * 取消订单：只有待支付状态可以取消。
     *
     * @throws BizException 状态不允许取消时抛出
     */
    public void cancel() {
        // 业务规则只写在这里一处
        if (status != OrderStatusEnum.CREATED) {
            throw new BizException(ErrorCode.ORDER_STATUS_ILLEGAL, "当前状态不可取消: " + status);
        }
        this.status = OrderStatusEnum.CANCELLED;
    }
}
```

### 4.4 什么时候不该用 DDD

| 适合 | 不适合 |
|---|---|
| 业务规则复杂、长期演进（交易、结算、风控） | 简单 CRUD、后台管理、报表 |
| 团队对业务有共同语言，有领域专家 | 团队小、交付周期短、原型验证 |
| 需要拆微服务，要找服务边界 | 数据驱动型系统（ETL、数据同步） |

> 务实做法：**不必全套 DDD**。借用「限界上下文」划服务边界、「聚合根」守护一致性、「值对象」封装金额/地址，就已拿到 80% 收益。五层架构里的功能单元层，正好可以承载聚合的读写。

---

## 5. 如何写技术方案

### 5.1 为什么要写

技术方案是「**写代码之前的代码**」：评审时改一行文档的成本，是上线后改一行代码成本的百分之一。高级工程师和中级工程师最大的可见差距，往往就在方案质量上。

### 5.2 四要素

```
             ┌──────────────┐
             │ ① 接口设计     │  新增/变更/删除哪些接口；入参出参字段、类型、含义、必填、默认值
             ├──────────────┤
             │ ② 数据库设计   │  DDL；ALTER 合并；中文注释；线上兼容
             ├──────────────┤
             │ ③ 组件设计     │  各层组件职责边界、依赖关系、哪些复用哪些不复用
             ├──────────────┤
             │ ④ 执行流程链路 │  文字版流程图：Controller → 校验 → 编排 → 功能单元 → DAO/三方
             └──────────────┘
   存量改造额外三项：改造范围（动什么、不动什么） · 改造前后对比 · 影响面分析
```

**① 接口设计要点**：每个接口写清楚 URL、方法、变更类型（新增/修改/删除）、归属模块；字段表包含「字段名 / 类型 / 必填 / 默认值 / 含义」，枚举字段列全部取值。

**② 数据库设计要点**：

```sql
-- 反例：同一张表多条 ALTER，每条都会触发一次表重建/元数据锁
ALTER TABLE t_order ADD COLUMN pay_time DATETIME;
ALTER TABLE t_order ADD INDEX idx_pay_time (pay_time);

-- 正例：合并为一条，注明表名与目的；新字段允许 NULL 或带默认值，保证旧 INSERT 不报错
-- t_order：新增支付时间字段 + 按支付时间统计的索引
ALTER TABLE t_order
    ADD COLUMN pay_time DATETIME NULL COMMENT '支付时间' AFTER status,
    ADD INDEX idx_pay_time (pay_time);
```

| 线上兼容规则 | 原因 |
|---|---|
| 新增字段必须 `NULL` 或 `DEFAULT` | 老代码的 INSERT 不带该字段 |
| 不删字段、不改字段名，先「废弃」后清理 | 灰度期间新老版本共存 |
| 不缩短字段长度、不改类型 | 已有数据可能截断 |
| 大表 DDL 走 Online DDL / gh-ost / pt-osc | 避免锁表 |
| 先发 DDL，再发代码 | 代码依赖新字段 |

**③ 组件设计要点**：按「接口层 / 编排层 / 功能单元 / 能力单元（DAO、三方 Client）/ 工具与转换」逐类列出，每个组件写职责、依赖谁、**明确不做什么**。

**④ 执行流程链路要点**：一个接口一张文字版流程图，体现层级、分支条件、数据流转、失败策略。

### 5.3 完整示例：mini-mall「订单超时自动取消」技术方案

#### 5.3.1 背景与目标

- **背景**：用户下单后长时间不支付，库存被占用。当前无自动取消，运营每天手工处理。
- **目标**：下单 30 分钟未支付的订单自动取消并回补库存；取消结果通知用户。
- **非目标**：本期不做「支付后取消（退款）」；不做可配置超时时长（固定 30 分钟）。
- **方案选型**：

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| 定时任务扫表 | 简单、可靠 | 有延迟（扫描间隔）、扫表压力 | 作为**兜底** |
| RocketMQ 延迟消息 | 准时、无扫表压力 | 消息可能丢/重复，需要幂等 | **主链路** |
| Redis 过期监听 | 简单 | 过期事件不可靠，不保证送达 | 不采用 |

最终：**延迟消息为主 + XXL-Job 扫表兜底 + 取消操作幂等**。

#### 5.3.2 接口设计

| 接口 | 类型 | 变更 | 归属 |
|---|---|---|---|
| `POST /api/orders` 创建订单 | HTTP | **修改**：下单成功后发送延迟消息，出参不变 | order 模块 |
| `ORDER_TIMEOUT_TOPIC` 消费者 | MQ | **新增** | order 模块 |
| `orderTimeoutCancelJob` | XXL-Job | **新增**，每 5 分钟执行 | order 模块 |
| `POST /api/orders/{orderNo}/cancel` 用户主动取消 | HTTP | **修改**：内部改为复用新的取消功能单元，出入参不变 | order 模块 |

**延迟消息体 `OrderTimeoutMessage`**：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| orderNo | String | 是 | 订单号 |
| userId | Long | 是 | 用户 ID |
| createTime | LocalDateTime | 是 | 下单时间，用于消费时二次判断是否已超时 |

**XXL-Job 参数**：

| 参数 | 类型 | 必填 | 默认值 | 含义 |
|---|---|---|---|---|
| batchSize | Integer | 否 | 200 | 单批扫描条数 |
| timeoutMinutes | Integer | 否 | 30 | 超时阈值（分钟），便于应急调整 |

**功能单元出参 `CancelResultEnum`**：

| 取值 | 含义 |
|---|---|
| SUCCESS | 本次成功取消 |
| ALREADY_CANCELLED | 已是取消状态（幂等命中） |
| STATUS_NOT_ALLOW | 订单已支付/发货，不可取消 |
| NOT_FOUND | 订单不存在 |

#### 5.3.3 数据库设计

```sql
-- t_order：新增取消原因、取消时间字段，用于区分超时取消与主动取消
-- 线上兼容：新字段均可为 NULL / 有默认值，存量 INSERT 不受影响
-- 超时扫描所需的 idx_status_create_time (status, create_time) 已在 08 章建表时创建，无需重复添加
ALTER TABLE t_order
    ADD COLUMN cancel_reason TINYINT NULL COMMENT '取消原因：1-超时未支付 2-用户主动取消' AFTER status,
    ADD COLUMN cancel_time DATETIME NULL COMMENT '取消时间' AFTER cancel_reason;
```

> 取消使用条件更新 `UPDATE t_order SET status = 2, ... WHERE order_no = ? AND status = 0`，依赖状态机天然幂等，无需额外幂等表。回补库存使用 `UPDATE t_product SET stock = stock + ? WHERE id = ?`。

#### 5.3.4 组件设计

| 层 | 组件 | 职责 | 不做什么 |
|---|---|---|---|
| ① 接口层 | `OrderTimeoutListener` | 消费延迟消息，反序列化后调用编排层 | 不写业务判断 |
| ① 接口层 | `OrderTimeoutCancelJob` | 解析 Job 参数，调用编排层 | 不直接查库 |
| ② 编排层 | `OrderCancelBizComponent` | 编排：取消 → 成功后发通知；批量入口逐条调用并汇总 | 不写 SQL，不开事务 |
| ③ 功能单元 | `OrderCancelUnit` | **事务内**：条件更新订单状态 + 回补全部明细的库存 | 不发 MQ、不调三方 |
| ④ 能力单元 | `OrderDao` / `OrderItemDao` / `ProductDao` | 单表读写 | 不做跨表逻辑 |
| ④ 能力单元 | `OrderMqProducer` | 发送延迟消息、取消通知消息 | 不关心业务含义 |
| ⑤ 工具层 | `OrderStatusEnum`、`CancelReasonEnum` | 状态与原因编码 | — |

**复用关系**：用户主动取消、延迟消息、XXL-Job 兜底三个入口复用同一个 `OrderCancelUnit`，只是 `cancelReason` 不同。

#### 5.3.5 执行流程链路

**链路 A：下单（存量改造）**

```
OrderController.create
  → @Valid 校验 CreateOrderDTO
  → OrderBizComponent.create
      → OrderCreateUnit.create（事务：写 t_order + t_order_item + 扣 t_product 库存）
      → [新增] OrderMqProducer.sendTimeoutMessage（延迟 30 分钟，事务提交后发送）
          └─ 发送失败：仅记录 ERROR 日志，不影响下单结果（由 XXL-Job 兜底）
  → 返回 Result<OrderVO>
```

**链路 B：延迟消息取消（新增）**

```
OrderTimeoutListener.onMessage(OrderTimeoutMessage)
  → OrderCancelBizComponent.cancelOne(orderNo, TIMEOUT)
      → OrderCancelUnit.cancel(orderNo, TIMEOUT)   【事务】
          → OrderDao.getByOrderNo ──► 不存在：返回 NOT_FOUND
          → status == CANCELLED ──► 返回 ALREADY_CANCELLED（重复消息幂等）
          → status != CREATED ──► 返回 STATUS_NOT_ALLOW（已支付）
          → OrderDao.updateStatusIfMatch(CREATED → CANCELLED)
              └─ 影响行数 = 0（并发被支付抢先）：返回 STATUS_NOT_ALLOW
          → OrderItemDao.listByOrderId → ProductDao.restoreStock（逐条回补）
          → 返回 SUCCESS
      → 结果 == SUCCESS ──► OrderMqProducer.sendCancelNotify（失败只记日志）
  → 消费异常 ──► 抛出，RocketMQ 自动重试（最多 16 次后进死信队列 + 告警）
```

**链路 C：XXL-Job 兜底（新增）**

```
OrderTimeoutCancelJob.execute(batchSize, timeoutMinutes)
  → OrderCancelBizComponent.cancelTimeoutBatch
      → 循环：OrderDao.listTimeout(status = 0 AND create_time < now - 30min, id > lastId, LIMIT batchSize)
          → 逐条 cancelOne(orderNo, TIMEOUT)（单条失败捕获并计数，不中断整批）
      → 无数据时退出循环
  → 返回 ReturnT（成功数 / 失败数写入 Job 日志）
```

#### 5.3.6 核心代码

```java
/**
 * 订单状态枚举。
 */
@Getter
@AllArgsConstructor
public enum OrderStatusEnum {
    /** 待支付 */
    CREATED(0, "待支付"),
    /** 已支付 */
    PAID(1, "已支付"),
    /** 已取消（超时或主动） */
    CANCELLED(2, "已取消"),
    /** 已发货 */
    SHIPPED(3, "已发货"),
    /** 已完成 */
    COMPLETED(4, "已完成");

    /** 数据库存储编码，对应 t_order.status */
    private final int code;
    /** 中文描述 */
    private final String desc;
}

/**
 * 订单取消原因枚举。
 */
@Getter
@AllArgsConstructor
public enum CancelReasonEnum {
    /** 超时未支付 */
    TIMEOUT(1),
    /** 用户主动取消 */
    USER(2);

    /** 数据库存储编码，对应 t_order.cancel_reason */
    private final int code;
}

/**
 * 取消结果枚举。
 */
public enum CancelResultEnum {
    /** 本次成功取消 */
    SUCCESS,
    /** 已是取消状态，幂等命中 */
    ALREADY_CANCELLED,
    /** 当前状态不允许取消 */
    STATUS_NOT_ALLOW,
    /** 订单不存在 */
    NOT_FOUND
}

/**
 * 订单取消功能单元：在一个事务内完成「订单状态变更 + 库存回补」两张表的写操作。
 */
@Component
@RequiredArgsConstructor
public class OrderCancelUnit {

    private final OrderDao orderDao;
    private final OrderItemDao orderItemDao;
    private final ProductDao productDao;

    /**
     * 取消订单（幂等）。
     *
     * @param orderNo 订单号
     * @param reason  取消原因
     * @return 取消结果
     */
    @Transactional(rollbackFor = Exception.class)
    public CancelResultEnum cancel(String orderNo, CancelReasonEnum reason) {
        OrderPO order = orderDao.getByOrderNo(orderNo);
        CancelResultEnum precheck = precheck(order);
        if (precheck != null) {
            return precheck;
        }
        // 条件更新：WHERE status = 0，防止与支付并发时覆盖已支付状态
        int rows = orderDao.updateStatusIfMatch(orderNo, OrderStatusEnum.CREATED,
                OrderStatusEnum.CANCELLED, reason);
        if (rows == 0) {
            return CancelResultEnum.STATUS_NOT_ALLOW;
        }
        // 回补库存：明细逐条加回
        orderItemDao.listByOrderId(order.getId())
                .forEach(item -> productDao.restoreStock(item.getProductId(), item.getQuantity()));
        return CancelResultEnum.SUCCESS;
    }

    /**
     * 取消前的状态预检查。
     *
     * @param order 订单，可能为 null
     * @return 需要提前返回的结果；返回 null 表示可以继续取消
     */
    private CancelResultEnum precheck(OrderPO order) {
        if (order == null) {
            return CancelResultEnum.NOT_FOUND;
        }
        if (order.getStatus() == OrderStatusEnum.CANCELLED.getCode()) {
            return CancelResultEnum.ALREADY_CANCELLED;
        }
        if (order.getStatus() != OrderStatusEnum.CREATED.getCode()) {
            return CancelResultEnum.STATUS_NOT_ALLOW;
        }
        return null;
    }
}

/**
 * 订单取消编排组件：组合取消功能单元与通知能力，提供单条、批量两个入口。
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class OrderCancelBizComponent {

    private final OrderCancelUnit orderCancelUnit;
    private final OrderDao orderDao;
    private final OrderMqProducer orderMqProducer;

    /**
     * 取消单个订单，成功后发送通知。
     *
     * @param orderNo 订单号
     * @param reason  取消原因
     * @return 取消结果
     */
    public CancelResultEnum cancelOne(String orderNo, CancelReasonEnum reason) {
        CancelResultEnum result = orderCancelUnit.cancel(orderNo, reason);
        if (result == CancelResultEnum.SUCCESS) {
            notifyQuietly(orderNo);
        }
        return result;
    }

    /**
     * 批量取消超时订单（XXL-Job 兜底入口），按主键游标分页，避免深分页。
     *
     * @param batchSize      单批条数
     * @param timeoutMinutes 超时阈值（分钟）
     * @return 成功取消的数量
     */
    public int cancelTimeoutBatch(int batchSize, int timeoutMinutes) {
        LocalDateTime deadline = LocalDateTime.now().minusMinutes(timeoutMinutes);
        long lastId = 0L;
        int success = 0;
        List<OrderPO> batch;
        do {
            batch = orderDao.listTimeout(deadline, lastId, batchSize);
            for (OrderPO order : batch) {
                success += cancelSafely(order.getOrderNo()) ? 1 : 0;
                lastId = order.getId();
            }
        } while (batch.size() == batchSize);
        return success;
    }

    /**
     * 单条取消并吞掉异常，保证批量任务中一条失败不影响整批。
     *
     * @param orderNo 订单号
     * @return 是否成功取消
     */
    private boolean cancelSafely(String orderNo) {
        try {
            return cancelOne(orderNo, CancelReasonEnum.TIMEOUT) == CancelResultEnum.SUCCESS;
        } catch (Exception e) {
            log.error("超时取消失败, orderNo={}", orderNo, e);
            return false;
        }
    }

    /**
     * 发送取消通知，失败只记日志（通知非关键路径，不影响取消结果）。
     *
     * @param orderNo 订单号
     */
    private void notifyQuietly(String orderNo) {
        try {
            orderMqProducer.sendCancelNotify(orderNo);
        } catch (Exception e) {
            log.warn("取消通知发送失败, orderNo={}", orderNo, e);
        }
    }
}
```

#### 5.3.7 存量改造说明

| 项 | 内容 |
|---|---|
| **改造范围** | ① `OrderBizComponent.create` 末尾追加发送延迟消息；② 用户主动取消接口内部改为调用 `OrderCancelUnit`；③ `t_order` 加 2 字段 1 索引 |
| **明确不动** | `OrderCreateUnit`（下单事务）、`OrderController` 出入参、支付回调链路、订单查询接口 |
| **前后对比** | 旧：未支付订单永久保持 CREATED，库存一直占用，主动取消逻辑写在 Controller 调用的 Service 里且不回补库存 → 新：30 分钟自动取消并回补库存；主动取消也回补库存（修复存量 bug） |
| **业务原因** | 释放被占库存、减少运营人工 |
| **影响面** | Controller：出参不变，前端无需修改；内部接口 `/api/inner/order/*`：不受影响；支付回调：与取消存在并发，靠 `WHERE status = 0` 条件更新互斥——支付回调同样必须用条件更新 `WHERE status = 0`，若支付回调发现订单已取消，走自动退款流程（已有）；报表：`status = 2` 的订单量会上升，需提前告知运营 |
| **上线顺序** | DDL → 发布消费者与 Job（Job 先停用）→ 发布下单改造 → 观察 1 天后启用 Job |
| **回滚方案** | 关闭发送延迟消息的配置开关；停用 Job；新增字段保留不影响 |

---

## 6. 系统设计方法论

### 6.1 六步法

```
① 需求澄清 → ② 容量估算 → ③ 架构草图 → ④ 存储设计 → ⑤ 瓶颈分析 → ⑥ 演进路线
```

| 步骤 | 要回答的问题 | 常见失分 |
|---|---|---|
| ① 需求澄清 | 核心功能是什么？非功能需求：QPS、延迟、可用性、一致性要求？哪些不做？ | 不问就开始画图 |
| ② 容量估算 | DAU、峰值 QPS、读写比、数据量/年、带宽 | 没有数字，后面选型全凭感觉 |
| ③ 架构草图 | 接入层、服务层、存储层、中间件，主链路先通 | 一上来就画 20 个微服务 |
| ④ 存储设计 | 表结构、索引、分库分表键、缓存结构、冷热分离 | 分片键选错导致热点 |
| ⑤ 瓶颈分析 | 单点、热点、慢依赖、一致性风险，各自的解法 | 只讲 happy path |
| ⑥ 演进路线 | 当前规模的最简方案 → 10 倍规模怎么改 | 过度设计 |

### 6.2 容量估算速算表

| 常用数字 | 值 |
|---|---|
| 一天秒数 | ≈ 86400 ≈ 10^5 |
| 峰值系数 | 平均 QPS × 2～10（秒杀可达 100 倍） |
| 单 MySQL 实例 | 读 ~1 万 QPS，写 ~几千 TPS（视硬件与 SQL） |
| 单 Redis 实例 | ~10 万 QPS |
| 单 RocketMQ Broker | ~10 万 TPS |
| 单 Tomcat 实例 | ~几百到几千 QPS（取决于业务耗时） |
| 内存访问 / SSD 随机读 / 同机房 RTT | 100ns / 100μs / 0.5ms |

**例**：DAU 1000 万，人均下单 0.1 次 → 日订单 100 万 → 平均写 QPS ≈ 100万 / 10^5 = 10，峰值 ×10 = 100。单库绰绰有余。订单表每年 3.65 亿行，单表 2000 万行左右开始考虑分表 → 需要分库分表或归档。

### 6.3 高并发三板斧

```
          ┌──────────── 缓存：让请求少走路 ─────────────┐
          │ 浏览器缓存 → CDN → Nginx → 本地缓存 → Redis   │ 读多写少
          └────────────────────────────────────────────┘
          ┌──────────── 异步：让请求不排队 ─────────────┐
          │ MQ 削峰填谷、非核心逻辑异步化、批量合并写     │ 写多、耗时长
          └────────────────────────────────────────────┘
          ┌──────────── 拆分：让压力被分摊 ─────────────┐
          │ 服务拆分、读写分离、分库分表、动静分离、单元化 │ 单点扛不住
          └────────────────────────────────────────────┘
```

| 板斧 | 带来的新问题 | 对应解法 |
|---|---|---|
| 缓存 | 一致性、穿透/击穿/雪崩、热 key、大 key | 旁路缓存+删缓存、布隆过滤器、互斥锁、随机 TTL、本地缓存 |
| 异步 | 消息丢失、重复、乱序、延迟、最终一致 | 可靠投递、幂等消费、顺序消息、对账 |
| 拆分 | 分布式事务、跨库查询、全局 ID、运维复杂度 | 本地消息表/Seata、ES 宽表、雪花 ID、服务治理 |

> 前端类比：缓存 ≈ HTTP 缓存 + SWR；异步 ≈ `requestIdleCallback` 把非关键任务挪走；拆分 ≈ 代码分割 + 微前端。

---

## 7. 实战设计题

### 7.1 mini-mall 秒杀系统

**需求澄清**：100 件 iPhone 1 元秒杀，预计 100 万人同时抢；每人限购 1 件；不能超卖；下单后 15 分钟内支付。

**核心矛盾**：100 万请求 vs 100 件库存 → **99.99% 的请求要在离数据库最远的地方被拦掉**。

#### 漏斗架构

```
  100 万用户
     │  ① 前端：按钮倒计时置灰、点击后防抖禁用、答题/验证码打散峰值、静态页上 CDN
     ▼  ~30 万请求
  ┌──────────────────────┐
  │ Nginx / 网关           │ ② 网关限流（Sentinel/令牌桶，按接口 + 按用户 ID）、黑名单、秒杀 URL 动态化
  └──────────┬───────────┘
     ▼  ~5 万请求
  ┌──────────────────────┐
  │ 秒杀服务（独立部署）    │ ③ 本地内存标记「已售罄」直接返回；校验活动时间、用户限购
  │                        │ ④ Redis + Lua 原子预扣库存 + 记录已购用户
  └──────────┬───────────┘
     ▼  ~100 个成功请求 → 发 MQ，立即返回「排队中」
  ┌──────────────────────┐
  │ RocketMQ              │ ⑤ 异步削峰，消费者按数据库能力匀速消费
  └──────────┬───────────┘
     ▼
  ┌──────────────────────┐
  │ 订单消费者             │ ⑥ 创建订单（OrderCreateUnit 复用）+ 数据库乐观扣减兜底
  └──────────┬───────────┘
     ▼
   MySQL：UPDATE t_product SET stock = stock - 1 WHERE id = ? AND stock >= 1
     ▲
  前端轮询 / WebSocket 查询下单结果
```

#### 完整流程

```
用户点击「抢购」
  → 前端：按钮禁用，请求带 activityId + 动态 token
  → 网关：令牌桶限流（超限直接返回「活动火爆」）
  → SeckillController.seckill
      → 校验：活动时间、token、登录态
      → 本地售罄标记 == true ──► 返回「已抢完」（不访问 Redis）
      → Redis Lua 原子执行：
          ├─ SISMEMBER 已购用户集合 ──► 已买过：返回 -2「限购」
          ├─ GET 库存 <= 0 ──► 返回 -1「已抢完」，置本地售罄标记
          └─ DECR 库存 + SADD 用户 ──► 返回 1
      → 结果 == 1 ──► 发送 MQ 消息 SeckillOrderMessage(userId, productId, requestId)
          └─ 发送失败 ──► Lua 回补库存 + 移除用户，返回「请重试」
      → 返回「排队中」，带 requestId
  → 订单消费者 SeckillOrderListener
      → 幂等：按 requestId 去重（t_order 唯一索引 / Redis SETNX）
      → OrderCreateUnit.create（事务：写订单 + 明细 + 条件扣数据库库存）
          └─ 数据库库存不足（rows=0）──► 记录异常并回补 Redis（理论上不应发生）
      → 发送 15 分钟延迟消息（复用 §5.3 超时取消链路，取消时回补 Redis + DB 库存）
      → 写入结果 Redis key（requestId → orderNo）
  → 前端轮询 GET /seckill/result?requestId= 拿到 orderNo 跳转支付
```

#### Redis 预扣库存 Lua 与调用

```java
/**
 * 秒杀库存组件：基于 Redis Lua 原子完成「限购校验 + 扣库存 + 记录用户」。
 */
@Component
@RequiredArgsConstructor
public class SeckillStockComponent {

    /**
     * KEYS[1]：库存 key；KEYS[2]：已购用户集合 key；ARGV[1]：用户 ID。
     * 返回：1 成功；-1 库存不足；-2 已购买过。
     */
    private static final String DEDUCT_LUA = """
            if redis.call('SISMEMBER', KEYS[2], ARGV[1]) == 1 then
                return -2
            end
            local stock = tonumber(redis.call('GET', KEYS[1]) or '0')
            if stock <= 0 then
                return -1
            end
            redis.call('DECR', KEYS[1])
            redis.call('SADD', KEYS[2], ARGV[1])
            return 1
            """;

    private static final DefaultRedisScript<Long> SCRIPT = new DefaultRedisScript<>(DEDUCT_LUA, Long.class);

    private final StringRedisTemplate redisTemplate;

    /**
     * 本地售罄标记。key：商品 ID；value：是否已售罄。各实例独立，只用于挡流量，不作为正确性依据。
     */
    private final Map<Long, Boolean> soldOutFlags = new ConcurrentHashMap<>();

    /**
     * 预扣库存。
     *
     * @param productId 商品 ID
     * @param userId    用户 ID
     * @return 1 成功；-1 库存不足；-2 已购买过
     */
    public long tryDeduct(Long productId, Long userId) {
        // 本地标记命中直接返回，避免售罄后还有海量请求打 Redis
        if (Boolean.TRUE.equals(soldOutFlags.get(productId))) {
            return -1L;
        }
        List<String> keys = List.of("seckill:stock:" + productId, "seckill:users:" + productId);
        Long result = redisTemplate.execute(SCRIPT, keys, String.valueOf(userId));
        long code = result == null ? -1L : result;
        if (code == -1L) {
            soldOutFlags.put(productId, Boolean.TRUE);
        }
        return code;
    }
}
```

#### 关键问题清单

| 问题 | 解法 |
|---|---|
| 超卖 | Redis Lua 原子扣减 + 数据库 `stock >= 1` 条件更新双保险 |
| 少卖（Redis 扣了但订单没建成） | MQ 发送失败回补；消费失败重试；超时未支付取消回补；定时对账 Redis 与 DB 库存 |
| 重复下单 | Lua 中 SET 限购 + 消费端 requestId 幂等 + 订单表 `(user_id, activity_id)` 唯一索引 |
| 热点 key | 库存 key 分片（拆成 N 个子库存 key 随机扣）、本地缓存活动信息 |
| 刷子/脚本 | 验证码、URL 动态化、风控黑名单、按用户限流 |
| 影响主站 | 秒杀服务独立部署、独立 Redis、独立 MQ Topic，故障隔离 |
| Redis 宕机 | 主从 + 哨兵；最坏情况活动降级关闭，不能退化为直接打 DB |

### 7.2 短链系统

**需求**：长链 → 6～8 位短码；跳转 QPS 高（读写比 100:1）；短码不可被轻易遍历；可设置过期。

```
生成：POST /short  { longUrl }
  → 查重（可选：longUrl 的 hash 索引）
  → 发号器取 ID（号段模式：DB 一次取 1000 个号放内存）
  → ID 转 62 进制（[0-9a-zA-Z]，7 位可表示 62^7 ≈ 3.5 万亿）
  → 写 t_short_url(code, long_url, expire_time) + 写 Redis
  → 返回 https://s.cn/{code}

跳转：GET /{code}
  → 布隆过滤器判断不存在 ──► 404（防穿透）
  → Redis 查 longUrl ──► 未命中查 DB 回填
  → 302 跳转（需统计点击用 302；301 会被浏览器缓存，后端拿不到统计）
  → 异步发 MQ 记录访问日志（UV/PV 统计）
```

| 设计点 | 选择与理由 |
|---|---|
| 短码生成 | 自增 ID + 62 进制（无冲突）；为防遍历可对 ID 做可逆混淆（如乘法逆元/Feistel） |
| Hash 方案 | MurmurHash 取前 N 位，有冲突需重试，适合「同一长链返回同一短码」 |
| 301 vs 302 | 302 便于统计与改指向；301 减少服务端压力 |
| 存储 | MySQL 按 code 主键；数据量大按 code 分表；Redis 缓存热点 |

### 7.3 Feed 流 / 消息通知（简版）

| 模式 | 写扩散（推） | 读扩散（拉） | 推拉结合 |
|---|---|---|---|
| 做法 | 发布时写入所有粉丝收件箱 | 读时聚合所有关注人发件箱 | 普通用户推，大 V 拉 |
| 优点 | 读快 | 写快、存储省 | 兼顾 |
| 缺点 | 大 V 千万粉丝写放大 | 关注多时读慢 | 实现复杂 |

```
发布动态
  → 写 t_post（发件箱）
  → 发 MQ：PostPublishedMessage
  → 消费者：作者粉丝数 < 阈值 ──► 分批写粉丝收件箱 Redis ZSet（score=时间戳，只保留最近 1000 条）
                         ≥ 阈值 ──► 不推，读时拉取

刷 Feed
  → 读自己的收件箱 ZSet（ZREVRANGEBYSCORE，游标分页：上次最小 score）
  → 合并关注的大 V 发件箱最近动态
  → 按时间归并排序 → 批量查动态详情（缓存）
```

**消息通知（站内信）** 同理：系统公告用读扩散（一条公告 + 用户已读游标），个人通知用写扩散（按用户分表）；未读数用 Redis 计数，进入页面清零。

> 前端类比：分页一律用游标（`lastId`/`lastScore`），而不是 `page=N`——和无限滚动列表的思路一致，避免数据新增导致重复/漏条。

---

## 8. 性能调优方法论

### 8.1 四步闭环

```
  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
  │ ① 定位   │ ─► │ ② 度量   │ ─► │ ③ 优化   │ ─► │ ④ 验证   │ ──┐
  └─────────┘    └─────────┘    └─────────┘    └─────────┘   │
       ▲                                                      │
       └──────────────── 未达标，回到定位 ◄───────────────────┘

  ① 定位：监控大盘 + 链路追踪（SkyWalking）找到最慢的一段，而不是凭感觉
  ② 度量：建立基线：P99 延迟、QPS、CPU、GC 次数、慢 SQL 数
  ③ 优化：一次只改一个变量
  ④ 验证：压测（JMeter/wrk）对比基线；灰度观察
```

> 前端类比：和 Lighthouse / Performance 面板的思路完全一致——先录制，找最长的那段，再动手。

### 8.2 五个层次（从便宜到昂贵）

| 层次 | 常见问题 | 排查工具 | 典型手段 |
|---|---|---|---|
| ① SQL | 全表扫描、索引失效、深分页、N+1 查询 | 慢查询日志、`EXPLAIN` | 加/改联合索引、覆盖索引、游标分页、批量查询代替循环查 |
| ② 缓存 | 重复查询、热点数据打 DB | Redis 命中率监控 | 旁路缓存、本地二级缓存、预热 |
| ③ JVM | Full GC 频繁、内存泄漏、大对象 | `jstat`、GC 日志、MAT、Arthas | 调整堆与 Region、修复泄漏、避免一次加载大量数据 |
| ④ 线程池 | 核心数不合理、队列堆积、线程阻塞 | `jstack`、线程池监控指标 | 区分 CPU/IO 密集设参数、隔离线程池、异步并行（CompletableFuture） |
| ⑤ 架构 | 单点瓶颈、同步链路过长 | 链路追踪、容量评估 | 异步化（MQ）、读写分离、分库分表、服务拆分 |

**N+1 查询示例**（最常见的接口慢原因）：

```java
/**
 * 批量组装订单 VO：先批量查明细再内存分组，避免循环内逐条查库（N+1）。
 *
 * @param orders 订单列表
 * @return 订单 VO 列表
 */
public List<OrderVO> assemble(List<OrderPO> orders) {
    List<Long> orderIds = orders.stream().map(OrderPO::getId).toList();
    // 一次查询全部明细：SELECT ... WHERE order_id IN (...)
    // key：订单 ID；value：该订单的明细列表
    Map<Long, List<OrderItemPO>> itemsByOrderId = orderItemDao.listByOrderIds(orderIds).stream()
            .collect(Collectors.groupingBy(OrderItemPO::getOrderId));
    return orders.stream()
            .map(o -> orderConverter.toVO(o, itemsByOrderId.getOrDefault(o.getId(), List.of())))
            .toList();
}
```

---

## 9. 代码质量与 Code Review 清单（Java 后端版）

| 类别 | 检查项 |
|---|---|
| **正确性** | 边界：空集合、null、0、负数、超长字符串；金额用 `BigDecimal` 且 `compareTo` 比较；`Integer` 用 `equals` 比较（-128～127 缓存坑） |
| **并发** | 单例 Bean 无可变成员字段；先查后改有无竞态；`ThreadLocal` 是否 `remove`；`SimpleDateFormat` 等非线程安全类 |
| **事务** | 多表写是否在同一事务；`rollbackFor = Exception.class`；同类自调用失效；事务内是否有 RPC/MQ/大循环（长事务） |
| **数据库** | 新 SQL 是否走索引（附 EXPLAIN）；有无全表/无 LIMIT 查询；批量操作分批；DDL 线上兼容 |
| **缓存** | 有无 TTL；更新数据后删缓存；穿透/击穿防护；key 命名规范、无大 key |
| **MQ** | 消费幂等；消费失败是否抛出触发重试；消息体是否兼容（新增字段不破坏老消费者） |
| **外部调用** | 超时设置；重试是否幂等；熔断降级；返回值判空 |
| **安全** | 越权（数据归属校验）；SQL 注入（MyBatis 禁用 `${}` 拼接用户输入）；敏感信息日志脱敏；接口限流 |
| **异常与日志** | 不吞异常（`catch` 后至少 log）；日志带业务主键与 traceId；`log.error("...", e)` 打印堆栈；不在循环里打大量 INFO |
| **设计** | 分层是否越级调用；方法是否单一职责、超过一屏要拆；重复代码是否抽取；有无过度设计 |
| **可运维** | 新功能有开关；有监控指标/告警；有回滚方案 |
| **注释与测试** | 方法有功能注释；复杂逻辑有设计说明；核心逻辑有单测 |

> Review 心法：先看**方案与边界**（会不会出事），再看**实现**（对不对），最后看**风格**（好不好）。风格问题交给 Checkstyle/Spotless 自动化。

---

## 10. 前端转 Java：常见误区、学习建议与书单

### 10.1 常见误区

| 误区 | 正解 |
|---|---|
| 「Java 就是啰嗦的 TS」 | 真正的难点不在语法，在**多线程、事务、一致性**，这些前端没有 |
| 用 `==` 比较字符串/包装类 | `equals`；`Integer` 缓存只覆盖 -128～127 |
| 到处 `Map<String, Object>` 传数据，像写 JS 对象 | 定义 DTO/VO/record，类型就是文档 |
| 在单例 Service 里存请求状态 | 单例被所有线程共享，状态放局部变量 |
| `@Transactional` 加上就以为生效 | 理解代理机制：自调用、非 public、异常被吞、checked 异常默认不回滚 |
| 本地 `synchronized` 解决并发 | 多实例部署下无效，需 DB 条件更新或分布式锁 |
| 只测 happy path | 服务端的价值在异常分支：超时、重复、并发、部分失败 |
| 过早上微服务 | 单体 + 清晰分层足以支撑大多数业务，拆分要有理由 |
| 只会 CRUD 不看原理 | 面试与排障都考原理：HashMap、线程池、GC、索引、MVCC |

### 10.2 学习建议

1. **以 mini-mall 为主线**：每学一章就在项目里落地一次，最后能完整讲清从下单到超时取消、到秒杀的全链路。
2. **先广后深**：第一轮按总纲把 01-12 章过一遍能写代码；第二轮带着面试题回头深挖原理。
3. **刻意练习三种思维**：每写一个接口，问自己「并发下会怎样、失败了会怎样、量大了会怎样」。
4. **读源码有顺序**：`HashMap` → `ConcurrentHashMap` → `ThreadPoolExecutor` → `AQS` → Spring `refresh()` → `@Transactional` 代理链 → MyBatis 执行流程。
5. **会排查才算会**：练熟 `jstack`、`jstat`、Arthas、`EXPLAIN`、慢查询日志、Redis `SLOWLOG`。
6. **发挥前端优势**：接口契约设计、BFF/网关、全栈联调、可观测性，是你天然比纯后端更有感觉的地方。

### 10.3 推荐书单与资源

| 方向 | 书 / 资源 | 读法 |
|---|---|---|
| 语言 | 《Java 核心技术 卷 I》 | 当字典查，挑并发前的章节通读 |
| 语言 | 《Effective Java》（第 3 版） | 高级工程师必读，90 条逐条对照自己的代码 |
| JVM | 《深入理解 Java 虚拟机》（周志明，第 3 版） | 内存区域、GC、类加载三部分精读 |
| 并发 | 《Java 并发编程实战》 | 前 5 章 + 线程池章节精读 |
| 并发 | 《Java 并发编程的艺术》 | 结合 AQS、ConcurrentHashMap 源码读 |
| Spring | Spring 官方文档 + 《Spring 揭秘》 | IoC、AOP、事务章节 |
| 数据库 | 《高性能 MySQL》（第 4 版） | 索引、查询优化、复制 |
| 数据库 | 《MySQL 是怎样运行的》 | 最适合入门 InnoDB 原理 |
| 缓存 | 《Redis 设计与实现》 | 数据结构与持久化、复制、集群 |
| 架构 | 《凤凰架构》（周志明，开源在线） | 分布式、服务治理全景 |
| 架构 | 《数据密集型应用系统设计》（DDIA） | 一致性、复制、分区的底层思维 |
| 设计 | 《重构》《领域驱动设计精粹》 | 代码坏味道与 DDD 入门 |
| 规范 | 《阿里巴巴 Java 开发手册》 | 日常编码规范直接对照 |
| 工具 | Arthas 官方文档 | 线上排查必备 |

---

# 第二部分 面试题汇总

## 11. 高频面试题（140 题）

> 难度：★ 基础必会 · ★★ 中级常考 · ★★★ 高级深挖。「前端类比」仅帮助记忆，答题时以 Java 原理为准。

| 分类 | 题号 | 分类 | 题号 |
|---|---|---|---|
| [11.1 Java 基础](#111-java-基础) | 1–12 | [11.7 MyBatis](#117-mybatis) | 77–82 |
| [11.2 集合](#112-集合) | 13–22 | [11.8 Redis](#118-redis) | 83–96 |
| [11.3 JVM](#113-jvm) | 23–34 | [11.9 消息队列](#119-消息队列) | 97–106 |
| [11.4 并发](#114-并发) | 35–50 | [11.10 微服务/分布式](#1110-微服务分布式) | 107–120 |
| [11.5 Spring/Spring Boot](#115-springspring-boot) | 51–64 | [11.11 系统设计](#1111-系统设计) | 121–126 |
| [11.6 MySQL](#116-mysql) | 65–76 | [11.12 场景题](#1112-场景题) | 127–140 |

### 11.1 Java 基础

**1. `==` 和 `equals` 的区别？** ★
- `==` 比较基本类型的值、引用类型的地址；`equals` 默认同 `==`，`String`、包装类等重写为比较内容。
- 重写 `equals` 必须同时重写 `hashCode`，否则放进 HashMap/HashSet 行为错误。
- 前端类比：`==` 像 JS 对象的 `===`（比引用），`equals` 像 lodash `isEqual`。

**2. 为什么重写 equals 必须重写 hashCode？** ★
- 约定：`equals` 相等的对象 `hashCode` 必须相等。
- HashMap 先按 hashCode 定位桶，再用 equals 比较；不重写会导致「相等的对象」落到不同桶，查不到、去重失败。

**3. String 为什么不可变？String、StringBuilder、StringBuffer 区别？** ★
- `String` 内部 `final byte[]`（Java 9+）且无修改方法；好处：线程安全、可缓存 hash、常量池复用、作 Map key 安全。
- `StringBuilder` 可变、非线程安全、性能好；`StringBuffer` 方法加 `synchronized`，线程安全但慢。
- 循环拼接用 `StringBuilder`；前端类比：JS 字符串同样不可变。

**4. `Integer a = 127, b = 127; a == b` 结果？换成 128 呢？** ★
- 127 为 `true`，128 为 `false`：自动装箱调用 `Integer.valueOf`，缓存 -128～127。
- 结论：包装类一律用 `equals` 比较；注意拆箱时 null 会 NPE。

**5. 接口和抽象类的区别？** ★
- 抽象类：单继承，可有构造器、成员变量、普通方法，表达「是什么」。
- 接口：多实现，Java 8+ 可有 `default`/`static` 方法，Java 9+ 可有 `private` 方法，无实例状态，表达「能做什么」。
- 前端类比：Java 接口是名义类型，必须显式 `implements`，不像 TS 结构化类型「长得像就行」。

**6. 受检异常和非受检异常？异常处理的最佳实践？** ★★
- 受检异常（`IOException`）编译器强制处理；非受检（`RuntimeException` 子类）不强制。
- 业务异常通常继承 `RuntimeException`（如 `BizException`），由全局异常处理器统一转成 `Result<T>`。
- 最佳实践：不吞异常；`finally`/try-with-resources 释放资源；不用异常做流程控制；保留原始 cause。

**7. 泛型擦除是什么？带来哪些限制？** ★★
- 编译后泛型信息被擦除为上界（默认 `Object`），运行时 `List<String>` 和 `List<Integer>` 是同一个 Class。
- 限制：不能 `new T()`、不能 `instanceof List<String>`、不能创建泛型数组、基本类型不能作泛型参数。
- 运行时取泛型需借助 `TypeReference`（Jackson）等技巧。前端类比：TS 类型编译后完全消失。

**8. `? extends T` 和 `? super T` 区别（PECS）？** ★★
- Producer Extends：只读取用 `extends`，可以读出 T，不能写入。
- Consumer Super：只写入用 `super`，可以写入 T，读出只能当 Object。
- 例：`Collections.copy(List<? super T> dest, List<? extends T> src)`。

**9. 反射是什么？优缺点与应用？** ★★
- 运行时获取类信息并操作字段、方法、构造器（`Class.forName`、`getDeclaredMethod`、`invoke`）。
- 应用：Spring IoC、AOP、MyBatis 映射、Jackson 序列化、注解处理。
- 缺点：性能较差（可缓存 Method）、破坏封装、编译期无检查。

**10. Java 是值传递还是引用传递？** ★
- 只有值传递：基本类型传值副本，引用类型传「引用的副本」。
- 方法内改对象字段会影响外部，但让形参指向新对象不影响外部。与 JS 完全一致。

**11. `record`、`sealed`、模式匹配、虚拟线程等 Java 新特性了解哪些？** ★★
- `record`（16）：不可变数据类，自动生成构造器/访问器/equals/hashCode/toString，适合 DTO。
- `sealed`（17）：限制子类范围，配合 `switch` 模式匹配（21）实现穷举检查。
- 虚拟线程（21）：轻量线程，阻塞 IO 不占平台线程，适合高并发 IO 场景。
- 前端类比：`sealed` + 模式匹配 ≈ TS 可辨识联合 + `never` 穷举检查。

**12. 深拷贝与浅拷贝？如何实现深拷贝？** ★
- 浅拷贝只复制引用，嵌套对象共享；深拷贝递归复制。
- 方式：手写拷贝构造器、序列化/反序列化（JSON）、MapStruct 转换；`clone()` 默认是浅拷贝且设计不佳，不推荐。
- 前端类比：`{...obj}` 是浅拷贝，`structuredClone` 是深拷贝。

### 11.2 集合

**13. HashMap 的底层原理（JDK 8）？** ★★
- 数组 + 链表 + 红黑树；`hash = h ^ (h >>> 16)` 扰动，`index = (n - 1) & hash`。
- 链表长度 ≥ 8 且数组长度 ≥ 64 时树化，≤ 6 退化为链表；数组 < 64 时优先扩容。
- 默认容量 16、负载因子 0.75，`size > 容量 × 0.75` 扩容为 2 倍。
- 前端类比：JS `Map` 是 V8 内部哈希表，但保持插入顺序——对应的是 `LinkedHashMap`。

**14. HashMap 容量为什么是 2 的幂？扩容时怎么迁移？** ★★★
- 2 的幂下 `(n-1) & hash` 等价于取模但更快，且分布均匀。
- 扩容时每个节点只需看 `hash & oldCap`：为 0 留在原位，否则移到「原位 + oldCap」，链表拆成高低两条，保持顺序。

**15. HashMap 为什么线程不安全？** ★★
- JDK 7 头插法并发扩容可能形成环形链表导致死循环；JDK 8 改尾插但仍有数据覆盖、size 不准问题。
- 并发场景用 `ConcurrentHashMap`，不要用 `Collections.synchronizedMap` 或 `Hashtable`（全表锁）。

**16. ConcurrentHashMap 的实现原理（JDK 7 vs 8）？** ★★★
- JDK 7：Segment 分段锁（继承 ReentrantLock），默认 16 段并发度。
- JDK 8：取消 Segment，`Node 数组 + 链表/红黑树`；桶为空时 CAS 插入，非空时 `synchronized` 锁桶头节点，锁粒度到桶。
- 扩容支持多线程协助迁移（`ForwardingNode` 标记）；`size` 用 `baseCount + CounterCell` 分散计数（类似 LongAdder）。
- key 和 value 都不允许 null（避免并发下 `get` 返回 null 的二义性）。

**17. ArrayList 和 LinkedList 区别？** ★
- ArrayList 动态数组，随机访问 O(1)，扩容 1.5 倍，尾部插入快；LinkedList 双向链表，随机访问 O(n)。
- 实际几乎总用 ArrayList（CPU 缓存友好）；LinkedList 中间插入也要先遍历定位。

**18. ArrayList 扩容机制？** ★
- 无参构造初始为空数组，首次 add 扩到 10；之后 `newCapacity = old + (old >> 1)`，`Arrays.copyOf` 复制。
- 已知大小时指定初始容量，避免反复扩容。

**19. fail-fast 与 fail-safe？** ★★
- fail-fast：遍历时结构被修改抛 `ConcurrentModificationException`（`modCount` 校验），如 ArrayList、HashMap。
- fail-safe：遍历副本或弱一致迭代器，如 `CopyOnWriteArrayList`、`ConcurrentHashMap`。
- 遍历中删除元素用 `Iterator.remove()` 或 `removeIf`。前端类比：`forEach` 中 splice 数组会跳元素。

**20. HashSet 如何保证不重复？TreeMap 如何排序？** ★
- HashSet 底层是 HashMap，元素作 key，依赖 `hashCode + equals`。
- TreeMap 基于红黑树，按 `Comparable` 或传入的 `Comparator` 排序，操作 O(log n)。

**21. LinkedHashMap 如何实现 LRU？** ★★
- 构造参数 `accessOrder = true` 按访问顺序维护双向链表，重写 `removeEldestEntry` 在 size 超限时返回 true。
- 前端类比：JS 中用 `Map` 删除再 set 实现 LRU 是同一思路。

**22. CopyOnWriteArrayList 适用什么场景？** ★★
- 写时复制整个数组并加锁，读无锁；适合读多写极少（监听器列表、配置白名单）。
- 缺点：写开销大、内存翻倍、读到的是弱一致快照。

### 11.3 JVM

**23. JVM 运行时内存区域有哪些？** ★
- 线程私有：程序计数器、虚拟机栈（栈帧：局部变量表、操作数栈）、本地方法栈。
- 线程共享：堆（对象实例）、方法区（Java 8 起由元空间 Metaspace 实现，使用本地内存）。
- 前端类比：V8 也有栈和堆，但 JS 单线程只有一个调用栈。

**24. 对象创建过程与内存布局？** ★★
- 创建：类加载检查 → 分配内存（指针碰撞/空闲列表，TLAB 线程本地分配）→ 零值初始化 → 设置对象头 → 执行构造器。
- 布局：对象头（Mark Word：hash、锁状态、GC 年龄；类型指针）+ 实例数据 + 对齐填充（8 字节对齐）。

**25. 如何判断对象可回收？GC Roots 有哪些？** ★★
- 可达性分析（不用引用计数，因为解决不了循环引用）。
- GC Roots：栈中局部变量引用、静态变量、常量、JNI 引用、活跃线程、`synchronized` 持有的对象。
- 前端类比：V8 同样是标记可达性，闭包持有引用导致的泄漏思路相同。

**26. 强、软、弱、虚四种引用？** ★★
- 强引用：不回收；软引用：内存不足时回收（缓存）；弱引用：下次 GC 即回收（`WeakHashMap`、ThreadLocalMap 的 key）；虚引用：只用于回收通知。
- 前端类比：弱引用 ≈ `WeakMap` / `WeakRef`。

**27. 垃圾回收算法有哪些？** ★
- 标记-清除（有碎片）、标记-复制（无碎片但浪费空间，用于新生代）、标记-整理（老年代）。
- 分代收集：新生代 Eden:S0:S1 = 8:1:1，对象熬过一定次数（默认 15）晋升老年代。

**28. 常见垃圾收集器？G1 原理？** ★★★
- Serial、Parallel（吞吐优先，JDK 8 默认）、CMS（已移除）、G1（JDK 9+ 默认）、ZGC（低延迟，亚毫秒停顿）。
- G1：堆划分为等大 Region，逻辑分代；维护每个 Region 的回收价值，按 `-XX:MaxGCPauseMillis` 目标优先回收垃圾最多的 Region（Garbage First）。
- 流程：初始标记（STW）→ 并发标记 → 最终标记（STW，SATB）→ 筛选回收（STW，复制存活对象）。
- 大对象放 Humongous Region；跨 Region 引用靠 Remembered Set + 卡表。

**29. 什么情况触发 Full GC？如何排查频繁 Full GC？** ★★★
- 触发：老年代空间不足、元空间不足、`System.gc()`、晋升失败/担保失败、G1 并发标记跟不上分配速度。
- 排查：`jstat -gcutil pid 1000` 看各区变化 → GC 日志 → `jmap -dump` 导出堆 → MAT 看大对象与引用链。
- 常见原因：一次查大量数据进内存、本地缓存无上限、内存泄漏（静态集合、ThreadLocal 未清理）。

**30. 类加载过程？** ★★
- 加载 → 验证 → 准备（静态变量赋零值）→ 解析（符号引用转直接引用）→ 初始化（执行 `<clinit>`，静态赋值和静态块）。
- 初始化时机：new、访问静态字段/方法、反射、子类初始化触发父类、main 类。

**31. 双亲委派模型？为什么要打破？** ★★★
- 类加载器先委托父加载器（Bootstrap → Platform → Application），父加载不了才自己加载。
- 好处：防止核心类被篡改（自定义 `java.lang.String` 无效）、避免重复加载。
- 打破场景：SPI（JDBC 用线程上下文类加载器）、Tomcat 隔离不同 Web 应用、热部署、OSGi。
- 前端类比：有点像 node_modules 向上逐级查找，但方向相反（先问父）。

**32. OOM 有哪几种？分别怎么处理？** ★★
- `Java heap space`：堆不足/泄漏；`Metaspace`：动态生成类过多；`unable to create native thread`：线程过多；`Direct buffer memory`：Netty 等直接内存；`StackOverflowError`：递归过深（不是 OOM 但常一起问）。
- 生产必配 `-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=`，事后用 MAT 分析。

**33. 常用 JVM 参数与调优思路？** ★★
- `-Xms -Xmx` 设相等避免扩缩；`-XX:+UseG1GC -XX:MaxGCPauseMillis=200`；`-Xss`；`-XX:MaxMetaspaceSize`；GC 日志 `-Xlog:gc*`。
- 容器内用 `-XX:MaxRAMPercentage=75` 让 JVM 感知容器内存。
- 思路：先确认是代码问题还是参数问题，大多数问题靠改代码而不是调参。

**34. JIT 编译是什么？逃逸分析？** ★★★
- 热点代码由 C1/C2 编译为本地机器码（分层编译），比解释执行快很多。
- 逃逸分析：对象不逃出方法时，可栈上分配/标量替换、锁消除。
- 前端类比：V8 的 TurboFan 同样是对热点函数做优化编译。

### 11.4 并发

**35. 进程与线程？Java 线程有哪些状态？** ★
- 线程是 CPU 调度单位，同进程线程共享堆。
- 状态：NEW、RUNNABLE、BLOCKED（等 synchronized 锁）、WAITING、TIMED_WAITING、TERMINATED。
- 前端类比：浏览器每个标签页是进程，Web Worker 是线程但不共享内存。

**36. 创建线程的方式？为什么推荐线程池？** ★
- 继承 Thread、实现 Runnable/Callable、线程池、`CompletableFuture`、虚拟线程 `Thread.ofVirtual()`。
- 线程池复用线程降低创建开销、控制并发数、统一管理与监控。

**37. 线程池七大参数与执行流程？** ★★
- `corePoolSize`、`maximumPoolSize`、`keepAliveTime`、`unit`、`workQueue`、`threadFactory`、`handler`。
- 流程：线程数 < core 新建线程 → 否则入队 → 队列满且 < max 新建非核心线程 → 再满触发拒绝策略。
- 注意：是「先入队再扩到 max」，不是先扩到 max。

**38. 线程池拒绝策略？为什么不用 Executors 创建？** ★★
- Abort（抛异常，默认）、CallerRuns（调用方线程执行，天然降速）、Discard、DiscardOldest。
- `newFixedThreadPool`/`newSingleThreadExecutor` 队列无界可能 OOM；`newCachedThreadPool` 线程数无上限。
- 用 `ThreadPoolExecutor` 显式构造，有界队列 + 命名线程工厂 + 监控。

**39. 线程池参数如何设置？** ★★★
- CPU 密集：≈ CPU 核数 + 1；IO 密集：≈ 核数 × (1 + 等待时间/计算时间)。
- 公式只是起点，最终靠压测与监控（活跃线程数、队列长度、拒绝次数）调整；建议参数做成动态配置（Nacos）。
- 不同业务用不同线程池隔离，避免一个慢依赖拖垮全部。

**40. synchronized 原理与锁升级？** ★★★
- 字节码：同步块 `monitorenter/monitorexit`，同步方法 `ACC_SYNCHRONIZED`；底层是对象头 Mark Word + Monitor（ObjectMonitor）。
- 锁升级：无锁 → 偏向锁 → 轻量级锁（CAS 自旋）→ 重量级锁（Monitor，线程阻塞），不可降级（一般情况）。
- JDK 15 起偏向锁默认禁用、18 起废弃（撤销成本高，现代应用收益低）。
- 可重入、非公平；JDK 6 后做了锁消除、锁粗化、自适应自旋。

**41. volatile 的作用与原理？** ★★★
- 保证可见性（写后立即刷主存，读从主存读）与有序性（禁止指令重排），**不保证原子性**（`i++` 仍不安全）。
- 原理：内存屏障（JMM 层面），x86 上通过 `lock` 前缀指令实现缓存一致性。
- 典型应用：状态标志位、DCL 单例中修饰 instance（防止半初始化对象被看到）。

**42. JMM 与 happens-before？** ★★★
- JMM 定义线程与主内存交互规则，解决可见性、原子性、有序性。
- happens-before 规则：程序顺序、锁（unlock 先于后续 lock）、volatile 写先于读、线程 start/join、传递性。
- 前端没有对应概念：JS 单线程不存在可见性问题。

**43. synchronized 与 ReentrantLock 区别？** ★★
- synchronized：JVM 实现、自动释放、非公平、不可中断。
- ReentrantLock：基于 AQS、需 `finally` 手动 `unlock`、支持公平锁、`tryLock` 超时、可中断、多个 `Condition`。
- 简单场景用 synchronized；需要超时/公平/多条件时用 ReentrantLock。

**44. AQS 原理？** ★★★
- `volatile int state` + CLH 变体双向等待队列；获取失败的线程入队并 `LockSupport.park`。
- 独占模式（ReentrantLock：state 表示重入次数）与共享模式（Semaphore、CountDownLatch）。
- 子类只需实现 `tryAcquire/tryRelease` 等模板方法——模板方法模式。

**45. CAS 是什么？ABA 问题怎么解决？** ★★
- Compare And Swap：比较内存值与期望值，相等才更新，CPU 原子指令（`cmpxchg`）。
- 问题：ABA、自旋开销、只能保证单变量。
- ABA 用版本号：`AtomicStampedReference`；数据库乐观锁的 version 字段是同一思想。

**46. ThreadLocal 原理与内存泄漏？** ★★★
- 每个 Thread 持有 `ThreadLocalMap`，key 为 ThreadLocal 弱引用，value 强引用。
- key 被回收后 value 仍被线程引用，线程池中线程长期存活 → 泄漏，且会读到上一个请求的数据（串号）。
- 必须在 `finally` 中 `remove()`；跨线程传递用 `InheritableThreadLocal`/TTL（TransmittableThreadLocal）。

**47. CountDownLatch、CyclicBarrier、Semaphore 区别？** ★★
- CountDownLatch：一个/多个线程等其他 N 个完成，一次性。
- CyclicBarrier：N 个线程互相等待到齐再一起走，可重用。
- Semaphore：控制同时访问的线程数（限流）。
- 前端类比：CountDownLatch ≈ `Promise.all`；Semaphore ≈ `p-limit` 并发控制。

**48. CompletableFuture 常用方法与注意点？** ★★
- `supplyAsync`、`thenApply`（同 Promise.then 映射）、`thenCompose`（扁平化）、`thenCombine`、`allOf`、`exceptionally`。
- 注意：不传线程池默认用 `ForkJoinPool.commonPool()`，IO 任务必须传自定义线程池；`allOf` 后要 `join` 取结果；设置超时 `orTimeout`。
- 前端类比：几乎一一对应 Promise，但回调在别的线程执行。

**49. 死锁条件与排查？** ★★
- 四条件：互斥、请求与保持、不可剥夺、循环等待。破坏其一即可：固定加锁顺序、`tryLock` 超时。
- 排查：`jstack pid` 末尾会直接输出 `Found one Java-level deadlock`；Arthas `thread -b`。

**50. 虚拟线程是什么？适用场景与注意事项？** ★★★
- Java 21 正式特性，由 JVM 调度的用户态线程，挂载在少量平台线程（carrier）上，阻塞时自动卸载。
- 适合大量阻塞 IO 的场景（每请求一线程模型），可创建百万级；不适合 CPU 密集。
- 注意：不要池化虚拟线程；`synchronized` 内阻塞会 pin 住载体线程（JDK 24 已改善）；ThreadLocal 慎用。
- 前端类比：让同步阻塞写法获得近似 async/await 的伸缩性。

### 11.5 Spring/Spring Boot

**51. 什么是 IoC 和 DI？有什么好处？** ★
- IoC：对象创建与依赖关系交给容器管理；DI 是其实现方式（构造器注入推荐、Setter、字段注入）。
- 好处：解耦、便于测试（注入 Mock）、统一管理生命周期。
- 前端类比：NestJS/Angular 的依赖注入，Vue 的 `provide/inject`。

**52. Spring Bean 的生命周期？** ★★★
- 实例化（构造器）→ 属性填充（依赖注入）→ Aware 回调（BeanNameAware 等）→ `BeanPostProcessor#before` → `@PostConstruct` → `InitializingBean#afterPropertiesSet` → init-method → `BeanPostProcessor#after`（**AOP 代理在此生成**）→ 使用 → `@PreDestroy` → `DisposableBean#destroy`。
- 前端类比：类似组件 constructor → mounted → unmounted，但多了扩展点。

**53. Spring 如何解决循环依赖？三级缓存？** ★★★
- 一级 `singletonObjects`（成品）、二级 `earlySingletonObjects`（半成品）、三级 `singletonFactories`（创建早期引用的工厂）。
- A 实例化后放入三级缓存 → 注入 B → B 注入 A 时从三级缓存拿到 A 的早期引用（若需 AOP 则此时提前生成代理）→ B 完成 → A 完成。
- 为什么三级：为了在有 AOP 时也能延迟且保证注入的是同一个代理对象。
- 无法解决：构造器注入的循环依赖、prototype Bean。Spring Boot 2.6+ 默认禁止循环依赖，应从设计上消除。

**54. Bean 的作用域？单例 Bean 线程安全吗？** ★★
- singleton（默认）、prototype、request、session、application。
- 单例 Bean 本身不保证线程安全；无状态（只依赖其他 Bean，无可变字段）则安全。

**55. AOP 原理？JDK 动态代理与 CGLIB 区别？** ★★
- 运行时为目标 Bean 生成代理对象，在调用前后织入切面逻辑。
- JDK 代理：基于接口，`Proxy + InvocationHandler`；CGLIB：生成子类，不能代理 final 类/方法。
- Spring Boot 2.x 起默认 `proxyTargetClass = true` 使用 CGLIB。前端类比：ES6 Proxy / 装饰器。

**56. @Transactional 失效的场景？** ★★★
- 同类内部方法调用（绕过代理）；方法非 public；`final`/`static` 方法。
- 异常被 catch 吞掉；抛出受检异常而未配置 `rollbackFor`（默认只回滚 RuntimeException 和 Error）。
- 类未被 Spring 管理；数据库引擎不支持事务（MyISAM）；多线程中执行（事务绑定在 ThreadLocal）。
- 传播行为配置为 `NOT_SUPPORTED`/`NEVER` 等。

**57. 事务传播行为？** ★★
- `REQUIRED`（默认，有则加入无则新建）、`REQUIRES_NEW`（挂起外部，新建独立事务）、`NESTED`（保存点，可部分回滚）、`SUPPORTS`、`NOT_SUPPORTED`、`MANDATORY`、`NEVER`。
- 典型：记录操作日志用 `REQUIRES_NEW`，主事务回滚日志仍保留。

**58. Spring Boot 自动配置原理？** ★★★
- `@SpringBootApplication` = `@SpringBootConfiguration` + `@ComponentScan` + `@EnableAutoConfiguration`。
- `@EnableAutoConfiguration` 通过 `AutoConfigurationImportSelector` 读取 `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`（Boot 2.7 前为 `spring.factories`）。
- 每个配置类用 `@ConditionalOnClass`、`@ConditionalOnMissingBean`、`@ConditionalOnProperty` 按条件生效，用户自定义 Bean 优先。
- 前端类比：像 Vite 插件按依赖自动启用的「约定优于配置」。

**59. 如何自定义一个 Spring Boot Starter？** ★★
- 建 `xxx-spring-boot-starter` 模块：`@ConfigurationProperties` 属性类 + `@AutoConfiguration` 配置类（带条件注解）+ 在 `AutoConfiguration.imports` 中注册。
- 使用方引入依赖、在 yml 配置即可生效。

**60. Spring 中用到了哪些设计模式？** ★★
- 工厂（BeanFactory）、单例（Bean）、代理（AOP）、模板方法（JdbcTemplate、RestTemplate）、观察者（ApplicationEvent）、适配器（HandlerAdapter）、责任链（Filter、拦截器）、策略（Resource 加载）。

**61. Spring MVC 请求处理流程？** ★★
- `DispatcherServlet` → `HandlerMapping` 找 Handler 与拦截器链 → `HandlerAdapter` 调用 Controller（参数解析、`@Valid` 校验）→ 返回值经 `HttpMessageConverter` 转 JSON → 异常交给 `@RestControllerAdvice`。

**62. Filter 与 Interceptor 的区别？** ★★
- Filter：Servlet 规范，在 DispatcherServlet 之前，作用于所有请求（含静态资源），适合编码、跨域、TraceId。
- Interceptor：Spring MVC，在 Handler 前后，可拿到 Handler 信息与 Spring Bean，适合登录、权限。
- 前端类比：Filter ≈ Nginx/网关层，Interceptor ≈ 路由守卫。

**63. BeanFactory 与 ApplicationContext、FactoryBean 的区别？** ★★
- BeanFactory：最基础容器，懒加载；ApplicationContext：继承它，增加事件、国际化、资源加载，启动时预实例化单例。
- FactoryBean：一种特殊 Bean，用于创建复杂对象，`getBean("&name")` 取工厂本身。

**64. Spring 容器启动流程（refresh）？** ★★★
- `prepareRefresh` → `obtainFreshBeanFactory` → `prepareBeanFactory` → `invokeBeanFactoryPostProcessors`（解析配置类、扫描注册 BeanDefinition）→ `registerBeanPostProcessors` → 初始化事件广播器 → `onRefresh`（Boot 在此启动内嵌 Tomcat）→ `finishBeanFactoryInitialization`（实例化非懒加载单例）→ `finishRefresh`（发布 ContextRefreshedEvent）。

### 11.6 MySQL

**65. InnoDB 索引为什么用 B+ 树？** ★★
- 非叶子节点只存键，扇出大，3～4 层可存千万级数据，IO 次数少。
- 叶子节点双向链表，范围查询和排序高效。
- 对比：Hash 不支持范围；二叉/红黑树太高；B 树非叶子存数据导致扇出小。

**66. 聚簇索引、二级索引、回表、覆盖索引？** ★★
- 聚簇索引：主键索引，叶子存整行数据；二级索引叶子存主键值。
- 回表：通过二级索引拿到主键再回聚簇索引查整行。
- 覆盖索引：查询列都在索引中，无需回表（EXPLAIN 显示 `Using index`）。

**67. 最左前缀原则与索引下推？** ★★
- 联合索引 `(a,b,c)` 按 a→b→c 排序，查询需从最左列连续匹配；范围查询后的列无法用于定位。
- 索引下推（ICP，5.6+）：在存储引擎层用索引中的列提前过滤，减少回表（`Using index condition`）。

**68. 索引失效的常见场景？** ★★★
- 违反最左前缀；对索引列使用函数/计算（`DATE(create_time)`）；隐式类型转换（varchar 列传数字）。
- `LIKE '%xx'` 左模糊；`OR` 连接非索引列；`!=`、`NOT IN` 可能不走；字符集不一致的关联。
- 优化器判断全表更快（区分度低、回表太多）。
- 排查一律看 `EXPLAIN`：type（至少 range）、key、rows、Extra。

**69. 事务的 ACID 分别靠什么保证？** ★★
- 原子性：undo log；持久性：redo log；隔离性：锁 + MVCC；一致性：前三者共同保证 + 业务约束。

**70. 四种隔离级别与并发问题？** ★★
- 读未提交（脏读）、读已提交（不可重复读）、可重复读（MySQL 默认，InnoDB 通过 MVCC + 间隙锁基本避免幻读）、串行化。

**71. MVCC 原理？** ★★★
- 每行有隐藏列 `trx_id`（最后修改事务 ID）和 `roll_pointer`（指向 undo log 版本链）。
- ReadView 记录：活跃事务列表 `m_ids`、最小活跃 ID、下一个分配 ID、创建者 ID；沿版本链找到第一个对当前 ReadView 可见的版本。
- RC 每次 SELECT 生成新 ReadView；RR 只在第一次 SELECT 生成，所以可重复读。
- 只作用于快照读；`SELECT ... FOR UPDATE`、UPDATE 是当前读，靠锁。

**72. redo log、undo log、binlog 区别？两阶段提交？** ★★★
- redo：InnoDB 物理日志，记录「某页改了什么」，崩溃恢复，保证持久性（WAL 先写日志）。
- undo：逻辑日志，记录反向操作，用于回滚和 MVCC。
- binlog：Server 层逻辑日志，用于主从复制、数据恢复，追加写。
- 两阶段提交：redo prepare → 写 binlog → redo commit，保证两份日志一致；崩溃时按 binlog 是否完整决定提交或回滚。

**73. InnoDB 有哪些锁？什么是间隙锁、临键锁？** ★★★
- 行锁：记录锁、间隙锁（锁区间防插入）、临键锁（记录 + 前面的间隙，RR 下默认加锁单位）；表锁：意向锁、MDL。
- 锁是加在索引上的，**无索引的更新会锁全表**。
- 唯一索引等值命中退化为记录锁。

**74. 如何排查和优化慢 SQL？** ★★
- 开启慢查询日志 → `EXPLAIN` 分析 → 看是否全表、是否回表多、是否 filesort/temporary。
- 手段：加合适联合索引、覆盖索引、改写 SQL、避免 `SELECT *`、拆分大查询、深分页改游标。

**75. 深分页 `LIMIT 1000000, 10` 为什么慢？怎么优化？** ★★
- 需扫描并丢弃前 100 万行（且大量回表）。
- 优化：游标分页 `WHERE id > lastId LIMIT 10`；或延迟关联 `子查询先查主键再 JOIN`。
- 前端类比：无限滚动用游标而不是页码。

**76. 什么时候分库分表？分片键怎么选？带来什么问题？** ★★★
- 单表超 2000 万行或单库 QPS/容量到瓶颈时考虑，先尝试归档、读写分离。
- 分片键选查询最频繁、分布均匀的字段（订单按 user_id，买家查询走分片；卖家查询用异构索引表/ES）。
- 问题：跨库 JOIN、分布式事务、全局 ID、分页排序、扩容迁移。工具：ShardingSphere。

### 11.7 MyBatis

**77. `#{}` 和 `${}` 的区别？** ★
- `#{}` 预编译占位符，防 SQL 注入；`${}` 字符串直接拼接，有注入风险。
- `${}` 只用于动态表名、排序字段，且必须白名单校验。前端类比：`#{}` ≈ 参数化查询，`${}` ≈ 模板字符串拼 SQL。

**78. MyBatis 执行流程？** ★★
- `SqlSessionFactory` → `SqlSession` → Mapper 动态代理（`MapperProxy`）→ `Executor` → `StatementHandler`（`ParameterHandler` 设参）→ JDBC 执行 → `ResultSetHandler` 映射结果。

**79. Mapper 接口没有实现类为什么能调用？** ★★
- MyBatis 用 JDK 动态代理为接口生成代理，按「接口全限定名 + 方法名」找到对应 `MappedStatement` 执行。

**80. 一级缓存和二级缓存？** ★★
- 一级：SqlSession 级，默认开启；与 Spring 集成时每次调用新的 SqlSession，事务外基本不生效。
- 二级：Mapper namespace 级，默认关闭；多实例下有脏数据风险，生产一般不用，交给 Redis。

**81. MyBatis-Plus 的常用能力？乐观锁如何实现？** ★
- 通用 CRUD（`BaseMapper`）、条件构造器（`LambdaQueryWrapper`）、分页插件、逻辑删除、自动填充。
- 乐观锁：字段加 `@Version`，注册 `OptimisticLockerInnerInterceptor`，更新时自动拼 `WHERE version = ?` 并 +1。

**82. MyBatis 如何做批量插入？分页插件原理？** ★★
- 批量：`<foreach>` 拼多值 INSERT（控制每批 500～1000 条）或 `ExecutorType.BATCH`；MP 的 `saveBatch`。
- 分页：拦截器拦截 SQL，先执行 COUNT，再按方言改写追加 `LIMIT`。

### 11.8 Redis

**83. Redis 为什么快？** ★
- 纯内存；单线程处理命令无锁竞争与上下文切换；IO 多路复用（epoll）；高效数据结构。
- Redis 6 引入多线程仅用于网络 IO 读写，命令执行仍是单线程。
- 前端类比：和 Node 单线程 + 事件循环处理高并发 IO 是同一思路。

**84. 五种基本数据类型、底层编码与应用场景？** ★★
- String（SDS）：缓存、计数器、分布式锁；Hash（listpack/hashtable）：对象字段；List（quicklist）：消息列表；Set（intset/hashtable）：去重、共同好友；ZSet（listpack/跳表+哈希）：排行榜、延迟队列。
- 扩展：Bitmap（签到）、HyperLogLog（UV）、GEO、Stream。

**85. ZSet 为什么用跳表而不是红黑树？** ★★★
- 跳表范围查询更简单（底层链表顺序遍历）、实现简单、插入删除只需局部调整，平均 O(log n)。
- 小数据量时用 listpack 节省内存。

**86. RDB 和 AOF？** ★★
- RDB：定时快照（fork 子进程，写时复制），恢复快，可能丢最近数据。
- AOF：追加写命令，`appendfsync everysec` 最多丢 1 秒；AOF 重写压缩体积。
- 4.0+ 混合持久化：AOF 重写时前半段写 RDB 格式。

**87. 过期删除与内存淘汰策略？** ★★
- 过期删除：惰性删除（访问时检查）+ 定期删除（随机抽样）。
- 淘汰策略：`noeviction`、`allkeys-lru`、`volatile-lru`、`allkeys-lfu`、`volatile-ttl`、random 等；缓存场景常用 `allkeys-lru`。

**88. 缓存穿透、击穿、雪崩及解决方案？** ★★
- 穿透：查不存在的数据 → 缓存空值（短 TTL）、布隆过滤器、参数校验。
- 击穿：热点 key 过期瞬间大量请求打 DB → 互斥锁重建、逻辑过期、热点不过期。
- 雪崩：大量 key 同时过期或 Redis 宕机 → 随机 TTL、多级缓存、集群高可用、限流降级。

**89. 缓存与数据库一致性怎么保证？** ★★★
- 推荐 Cache Aside：读：先缓存后 DB 再回填；写：**先更新 DB，再删除缓存**（不是更新缓存）。
- 为什么删而不更新：避免并发写导致缓存是旧值，且懒加载省资源。
- 删除失败：重试（MQ）或订阅 binlog（Canal）异步删除；极端并发下的旧值回填靠 TTL 兜底，或延迟双删。
- 强一致需求不要用缓存，或接受读主库。前端类比：SWR 的「先改服务端，再 invalidate 缓存」。

**90. Redis 分布式锁怎么实现？有哪些坑？** ★★★
- 加锁：`SET key uuid NX PX 30000`（原子设置值 + 过期）；解锁：Lua 判断 value 是自己的再 DEL。
- 坑：未设过期导致死锁；业务超时锁过期被他人获取 → 看门狗续期；误删他人锁 → value 校验；主从切换锁丢失 → RedLock（有争议）或改用 ZooKeeper/etcd。
- 生产用 Redisson：可重入（Hash 计数）、看门狗（默认 30s，每 10s 续期）、公平锁、读写锁。

**91. Redis 主从复制、哨兵、Cluster？** ★★
- 主从：全量同步（RDB）+ 增量同步（复制积压缓冲区），读写分离。
- 哨兵：监控主节点，主观下线 → 客观下线 → 选举 Leader 哨兵 → 故障转移。
- Cluster：16384 个哈希槽分片，`CRC16(key) % 16384`，去中心化，自动故障转移；多 key 操作需用 hash tag `{}` 落同一槽。

**92. 大 key 和热 key 问题？** ★★
- 大 key（String > 10KB、集合元素上万）：阻塞、网络拥塞、迁移慢 → 拆分、压缩、`UNLINK` 异步删除；`redis-cli --bigkeys` 发现。
- 热 key：单分片压力过大 → 本地缓存、key 加随机后缀分散到多分片、读副本。

**93. Redis 事务与 Lua 脚本？** ★★
- `MULTI/EXEC` 打包执行，无回滚，中途命令出错其余仍执行。
- Lua 脚本原子执行，适合「判断 + 修改」组合（扣库存、解锁）；脚本不宜过长，会阻塞其他命令。

**94. 如何用 Redis 实现排行榜、限流、延迟队列？** ★★
- 排行榜：ZSet `ZINCRBY` + `ZREVRANGE`。
- 限流：固定窗口 `INCR + EXPIRE`；滑动窗口 ZSet；令牌桶 Lua。
- 延迟队列：ZSet score 为执行时间戳，轮询 `ZRANGEBYSCORE`；可靠性要求高时用 MQ 延迟消息。

**95. 为什么 Redis 单线程还要用 Lua/分布式锁？pipeline 是什么？** ★★
- 单线程保证单条命令原子，但多条命令之间可被其他客户端插入，所以组合操作需要 Lua。
- pipeline：批量发送命令减少 RTT，不保证原子性。

**96. 本地缓存与 Redis 如何组合（多级缓存）？** ★★★
- Caffeine（L1，进程内，微秒级）+ Redis（L2，分布式）+ DB。
- 一致性：L1 设短 TTL；数据变更时通过 Redis Pub/Sub 或 MQ 广播各实例清除 L1。
- 适用：读极多、能容忍秒级不一致的数据（商品详情、配置）。

### 11.9 消息队列

**97. 为什么用 MQ？带来哪些问题？** ★
- 解耦、异步、削峰。
- 问题：系统复杂度、消息丢失、重复消费、顺序性、积压、最终一致。
- 前端类比：跨进程的 EventEmitter，但带持久化和重试。

**98. RocketMQ 的架构？** ★★
- NameServer（路由注册，无状态）、Broker（存储，主从）、Producer、Consumer（集群消费/广播消费）。
- Topic 分为多个 MessageQueue；存储上所有消息顺序写 CommitLog，ConsumeQueue 作为索引。

**99. 如何保证消息不丢失？** ★★★
- 生产端：同步发送 + 失败重试；或事务消息/本地消息表。
- Broker：同步刷盘 + 主从同步复制。
- 消费端：业务处理成功后才返回 `CONSUME_SUCCESS`，异常则重试；不在消费中异步处理后立即 ACK。

**100. 如何保证消息幂等（重复消费）？** ★★★
- MQ 只保证 at-least-once，重复不可避免，幂等由业务保证。
- 手段：数据库唯一索引（消息 ID/业务单号）、状态机条件更新（`WHERE status = 0`）、去重表、Redis `SETNX` 记录已处理。
- 推荐用业务主键而非 msgId（生产者重发时 msgId 可能变化）。

**101. 如何保证消息顺序？** ★★
- 全局有序代价太高，一般做分区有序：同一订单的消息按 orderNo 哈希到同一个 Queue（`MessageQueueSelector`），消费端用顺序消费模式单线程处理该队列。
- Kafka 同理：同 key 进同一 Partition。

**102. 消息积压怎么处理？** ★★
- 先定位原因：消费者慢（下游慢、异常重试）还是生产突增。
- 临时扩容消费者（不超过队列数），或写临时程序把消息转发到更多队列的新 Topic 并行消费；修复后批量补偿。
- 预防：监控消费延迟告警、消费端批量处理、异步化下游。

**103. RocketMQ 事务消息原理？** ★★★
- 发送半消息（消费者不可见）→ 执行本地事务 → 提交 Commit/Rollback。
- Broker 未收到确认时回查生产者 `checkLocalTransaction`，根据本地事务状态决定提交或回滚。
- 用于「本地事务成功 ⇔ 消息必达」，实现最终一致。

**104. 延迟消息怎么实现？** ★★
- RocketMQ 4.x 固定 18 个延迟级别（1s～2h），内部转存到 `SCHEDULE_TOPIC_XXXX` 定时投递；5.x 支持任意时间（时间轮）。
- 典型应用：订单 30 分钟超时取消（见 §5.3），需配合消费幂等与定时任务兜底。

**105. Kafka 和 RocketMQ 怎么选？Kafka 为什么吞吐高？** ★★
- Kafka：吞吐极高，适合日志、大数据流；RocketMQ：事务消息、延迟消息、消息查询、重试/死信更完善，适合业务消息。
- Kafka 高吞吐：顺序写磁盘、页缓存、零拷贝（sendfile）、批量压缩、分区并行。

**106. 消费失败如何处理？死信队列？** ★★
- RocketMQ 集群消费失败按退避重试最多 16 次，之后进入死信队列 `%DLQ%consumerGroup`。
- 对死信队列配告警 + 人工/程序补偿；不可重试的错误（数据非法）直接记录并返回成功，避免无效重试。

### 11.10 微服务/分布式

**107. CAP 与 BASE？** ★★
- CAP：一致性、可用性、分区容错，网络分区必然存在，只能在 C 与 A 间取舍；Nacos 注册中心 AP，ZooKeeper CP。
- BASE：基本可用、软状态、最终一致，是互联网系统的常规选择。

**108. 分布式事务有哪些方案？** ★★★
- 2PC/XA：强一致，阻塞、性能差；Seata AT：基于 undo 日志自动补偿，对业务无侵入。
- TCC：Try-Confirm-Cancel，性能好但侵入大，要处理空回滚、悬挂、幂等。
- 本地消息表 / 事务消息：最终一致，最常用；Saga：长事务，正向 + 补偿。
- 选型：能不用就不用（合并服务边界）→ 最终一致（消息）→ 必要时 TCC/Seata。

**109. 本地消息表方案流程？** ★★
- 业务操作与「写消息表」在同一本地事务 → 定时任务扫描未发送消息投递 MQ → 消费方幂等处理 → 回调或标记完成。
- 优点：简单可靠、不依赖 MQ 事务特性；缺点：耦合消息表、需要定时扫描。

**110. 分布式 ID 方案？雪花算法原理与时钟回拨？** ★★★
- 方案：UUID（无序、太长）、数据库自增/号段（Leaf-segment）、Redis INCR、雪花算法。
- 雪花：1 位符号 + 41 位毫秒时间戳（约 69 年）+ 10 位机器 ID + 12 位序列号（每毫秒 4096 个），趋势递增，适合做主键。
- 时钟回拨：小幅回拨等待；大幅回拨报错或使用备用位；或用 Leaf 依赖 ZooKeeper 校验；机器 ID 分配需要中心化协调（K8s Pod 重建）。

**111. 限流算法有哪些？** ★★★
- 固定窗口：简单但有临界突刺；滑动窗口：更平滑。
- 漏桶：恒定速率流出，削平突发；令牌桶：按速率放令牌，允许一定突发（Guava RateLimiter、Sentinel）。
- 分布式限流：Redis + Lua；网关层统一限流（Sentinel + Gateway）。
- 前端类比：漏桶 ≈ throttle，以固定节奏放行。

**112. 熔断与降级？** ★★
- 熔断：依赖错误率/慢调用比例超阈值时断开，直接走 fallback，一段时间后半开探测（Closed → Open → Half-Open）。
- 降级：牺牲非核心功能保核心（关闭推荐、返回兜底数据）。工具：Sentinel、Resilience4j。

**113. 注册中心原理？Nacos 与 Eureka、ZooKeeper 区别？** ★★
- 服务启动注册、心跳续约、消费者拉取/订阅服务列表并本地缓存、客户端负载均衡。
- Nacos：支持 AP（临时实例）与 CP（持久实例，Raft），兼配置中心；Eureka：AP，已停更；ZooKeeper：CP，选举期间不可用。

**114. 一次 OpenFeign 调用经历了什么？** ★★
- 动态代理生成接口实现 → 解析注解构建请求 → LoadBalancer 从注册中心实例列表选一个 → HTTP 客户端发请求 → 解码响应。
- 必配：连接/读超时、重试策略（非幂等接口禁止重试）、熔断 fallback。

**115. 如何设计接口幂等？** ★★★
- Token 机制：先获取 token 存 Redis，提交时 `DEL` 成功才执行（原子）。
- 唯一索引：业务单号/请求 ID 唯一约束，重复插入报 `DuplicateKeyException` 视为成功。
- 状态机：`UPDATE ... WHERE status = 旧状态`；乐观锁 version。
- 分布式锁 + 查询判断：适合无法用唯一键的场景。
- 前端类比：按钮防重复点击只是体验层，真正的幂等必须在后端。

**116. 网关的作用？** ★
- 路由转发、统一鉴权、限流熔断、灰度、日志与 TraceId、协议转换。前端类比：BFF / Nginx 反向代理的增强版。

**117. 分布式链路追踪原理？** ★★
- 入口生成 TraceId，每一跳生成 SpanId，通过 HTTP Header/MQ 属性透传；采集上报后按 TraceId 拼出调用树（SkyWalking、Zipkin）。
- 日志 MDC 打印 TraceId 实现日志串联。

**118. 配置中心动态刷新原理？** ★★
- Nacos 客户端长轮询（2.x 改为 gRPC 长连接）监听配置变更 → 推送后刷新 `Environment` → `@RefreshScope` Bean 重建或 `@NacosValue` 自动更新。

**119. 如何拆分微服务？拆分原则？** ★★★
- 按业务边界（DDD 限界上下文）拆，高内聚低耦合；数据库随服务拆分，禁止跨服务直接访问库。
- 先单体模块化，团队规模与发布冲突成为瓶颈时再拆；警惕「分布式单体」（服务间同步强依赖链过长）。

**120. 分布式定时任务如何保证只执行一次？** ★★
- XXL-Job：调度中心统一调度，路由策略选一台执行器；分片广播把大任务拆给多实例。
- 自研：分布式锁 / 数据库行锁抢占；任务本身仍需幂等。前端类比：`setInterval` 在多标签页会各跑一次。

### 11.11 系统设计

**121. 设计一个秒杀系统？** ★★★
- 漏斗分层：前端防抖/验证码 → 网关限流 → 本地售罄标记 → Redis Lua 预扣库存 + 限购 → MQ 异步下单 → DB 条件扣减兜底。
- 隔离：独立服务、独立 Redis/Topic；超时未支付回补库存；对账修正少卖。（详见 §7.1）

**122. 设计一个短链系统？** ★★
- 发号器（号段）+ 62 进制编码；布隆过滤器防穿透 + Redis 缓存；302 跳转便于统计；访问日志异步。（详见 §7.2）

**123. 设计 Feed 流 / 朋友圈？** ★★★
- 推（写扩散）、拉（读扩散）、推拉结合（大 V 拉、普通用户推）；收件箱用 ZSet，游标分页。（详见 §7.3）

**124. 设计一个分布式 ID 生成服务？** ★★
- 号段模式（DB 双 buffer 预加载）+ 雪花算法双模式；高可用部署、监控号段消耗；客户端本地缓存一段 ID。

**125. 设计一个排行榜（千万用户）？** ★★
- Redis ZSet，单 key 过大时按分数段或分桶分片，Top N 合并；同分按时间排序可把时间编码到 score 小数位。
- 持久化到 DB 定时快照，Redis 故障可重建。

**126. 设计一个站内通知/消息中心？** ★★
- 公告读扩散（一条记录 + 用户已读游标），个人消息写扩散（按 user_id 分表）；未读数 Redis 计数。
- 推送：WebSocket/长连接网关 + MQ 广播到连接所在节点；离线消息拉取补齐。

### 11.12 场景题

**127. 线上 CPU 飙高如何排查？** ★★★
- `top` 找到进程 → `top -Hp pid` 找到最耗 CPU 的线程 → `printf '%x' tid` 转 16 进制 → `jstack pid | grep -A 30 nid=0x...` 看堆栈。
- 或直接用 Arthas `thread -n 3`。
- 常见原因：死循环、正则回溯、频繁 GC（GC 线程占 CPU，看 `jstat`）、大量序列化、锁自旋。

**128. 线上内存持续上涨 / OOM 如何排查？** ★★★
- `jstat -gcutil` 观察老年代是否只升不降 → `jmap -histo:live pid` 看对象排行 → `jmap -dump` 或 OOM 自动 dump → MAT 看 Dominator Tree 与 GC Roots 引用链。
- 常见：无上限本地缓存、静态集合、ThreadLocal 未清理、一次查全表、未关闭的流/连接。

**129. 接口突然变慢如何排查？** ★★
- 链路追踪看耗时卡在哪一段 → 慢 SQL 日志/数据库负载 → Redis 慢日志 → 下游接口 RT → 线程池是否打满（`jstack` 看线程状态）→ GC 停顿。
- 同时对照最近的发布与配置变更，必要时先回滚止血。

**130. 如何防止用户重复下单？** ★★
- 前端按钮置灰（体验）；后端提交 token 或 Redisson 锁 `lock:order:{userId}`；订单表唯一业务键兜底。

**131. 并发扣库存如何防止超卖？** ★★
- 单库：`UPDATE ... SET stock = stock - n WHERE id = ? AND stock >= n`，判断影响行数。
- 高并发：Redis Lua 预扣 + MQ 异步 + DB 兜底；热点商品库存分段。

**132. 支付回调与超时取消并发了怎么办？** ★★★
- 双方都用状态机条件更新：支付 `WHERE status = 0 → 1`，取消 `WHERE status = 0 → 2`，只有一个能成功。
- 支付回调更新失败且订单已取消 → 触发自动退款并告警；所有回调接口必须幂等（重复回调）。

**133. 大表加字段如何不影响线上？** ★★
- MySQL 8 `ALGORITHM=INSTANT` 加列（追加到末尾）秒级完成；其他变更用 gh-ost/pt-osc 影子表同步。
- 低峰执行、新字段可空或带默认值、先 DDL 后发代码、多个变更合并为一条 ALTER。

**134. 如何把 1000 万订单导出成 Excel？** ★★
- 异步任务：提交后返回任务 ID，前端轮询或通知下载。
- 游标分批查询（`id > lastId LIMIT 1000`）+ 流式写（EasyExcel），避免一次进内存；导出线程池隔离；文件上传对象存储。

**135. Redis 宕机了系统怎么办？** ★★
- 架构：哨兵/Cluster 高可用。
- 应用：缓存访问加超时与熔断，降级直连 DB 时必须限流，防止 DB 被打挂；锁、库存等强依赖 Redis 的功能直接降级关闭。

**136. MQ 消息发送了但本地事务回滚了（或反之）怎么办？** ★★★
- 这是「双写一致性」问题：用事务消息、本地消息表，或 `@TransactionalEventListener(AFTER_COMMIT)` 提交后再发 + 定时任务补偿。
- 禁止在事务中间发消息后又可能回滚。

**137. 如何做一次平滑的数据迁移（换表/换库）？** ★★★
- 双写（以旧库为准）→ 全量迁移历史数据 → 增量校验对账 → 灰度切读 → 切写以新库为准 → 观察后下线旧库。
- 每一步可回滚，配开关控制。

**138. 某个下游接口经常超时，如何治理？** ★★
- 设合理超时 + 有限重试（仅幂等接口）+ 熔断降级 + 独立线程池隔离；能异步就异步，能缓存就缓存；推动下游优化并约定 SLA。

**139. 如何设计一个对账系统？** ★★
- 定时（XXL-Job）拉取渠道账单与本地流水，按单号比对：长款、短款、金额不一致；差异入差错表并告警，支持自动/人工补单。
- 前提：所有流水有唯一业务单号、对账逻辑幂等可重跑。

**140. 让你负责一个新模块，你会怎么推进？** ★★★
- 澄清需求与非功能指标 → 写技术方案（接口、DDL、组件、链路四要素）并评审 → 拆任务与排期 → 编码 + 单测 + Code Review → 压测与预案（开关、回滚、监控告警）→ 灰度上线 → 复盘沉淀。
- 加分点：主动识别风险（并发、一致性、容量）与跨团队依赖，给出兜底方案。

---

> 读到这里，你已经走完了从前端到高级 Java 工程师的整条路线。回到 [总纲](./00-outline.md) 对照第 7 节能力模型，检查自己还缺哪一块，然后在 mini-mall 里把它亲手写一遍。
