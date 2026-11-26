# 06 Spring 核心：IoC、Bean 生命周期、AOP、事务

> [← 总纲](./00-outline.md) | [上一章：05 工程化](./05-engineering.md) | [下一章：07 Spring Boot 与 Web 开发 →](./07-spring-boot-web.md)

---

## 1. 本章地图

前面五章解决的是「JVM 进程本身」：语言、集合、JVM、并发、工程化。从这一章开始进入「进程内的框架」。

```
┌──────────────── 订单服务（Spring Boot 进程）────────────────┐
│  Controller → 编排层 → 功能单元 → DAO                        │
│      ▲            ▲          ▲         ▲                     │
│      └──── 谁来 new 它们？谁来把它们连起来？ ── IoC 容器 ─────┤ ← 6.3~6.6
│                                                              │
│  日志、权限、事务这些「横切逻辑」写在哪？ ──────── AOP ───────┤ ← 6.7
│                                                              │
│  写 3 张表怎么保证要么全成功要么全失败？ ──── @Transactional ─┤ ← 6.8
└──────────────────────────────────────────────────────────────┘
```

本章回答三个问题：

| 问题 | Spring 的答案 | 你需要掌握到的深度 |
|---|---|---|
| 对象由谁创建、依赖由谁注入 | IoC 容器 + DI | 能讲清 Bean 生命周期、三级缓存解决循环依赖 |
| 横切逻辑如何不侵入业务代码 | AOP（动态代理） | 能手写 JDK 动态代理，说清 JDK vs CGLIB |
| 多表写入如何保证原子性 | 声明式事务 | 能说出事务实现链路、7 种传播行为、10 种失效场景 |

学完本章，你会给 mini-mall 加上：IoC 组装 `OrderBizComponent` / `OrderCreateUnit`、`@LogCost` 耗时切面、下单事务，以及一次「自调用导致事务失效」的复现。

---

## 2. 前端类比

| 前端 | Spring | 相同点 | 关键差异 |
|---|---|---|---|
| NestJS `@Injectable()` + 构造器注入 | `@Component` + 构造器注入 | 几乎一模一样（NestJS 就是照着 Spring 设计的） | Spring 容器能力更多：生命周期回调、作用域、条件装配、AOP 代理 |
| Angular `providers` | `@Configuration` + `@Bean` | 都是「声明如何创建一个依赖」 | Spring 的 `@Configuration` 类本身会被 CGLIB 增强 |
| React Context（Provider/useContext） | IoC 容器 | 都是「依赖不靠层层传参，而是从容器里拿」 | Context 是运行时树形作用域；Spring 容器是全局单例注册表 |
| TS 装饰器 / 高阶函数 `withLog(fn)` | AOP | 都是「不改原函数，给它包一层」 | Spring AOP 靠运行时生成代理类，**只有通过代理调用才生效** |
| EventEmitter `on/emit` | `ApplicationEventPublisher` + `@EventListener` | 进程内发布订阅 | Spring 事件可以绑定事务阶段（提交后再触发） |
| 前端没有对应物 | `@Transactional` | — | 本章最容易踩坑的部分 |

一句话：**如果你写过 NestJS，IoC 部分你已经会了 70%；AOP 和事务是前端几乎没有的新东西，要重点学。**

---

## 3. 为什么需要 Spring：从手动 new 说起

### 3.1 手动 new 的痛点

假设没有任何框架，「创建订单」需要这样组装对象：

```java
/**
 * 无框架时的手动组装：入口处一层层 new 出所有依赖。
 */
public class ManualApp {

    /**
     * 程序入口：手动构建对象图并调用下单。
     *
     * @param args 命令行参数（未使用）
     */
    public static void main(String[] args) {
        // 1. 最底层：数据源
        DataSource dataSource = new HikariDataSource(buildHikariConfig());
        // 2. 能力单元层：DAO 依赖数据源
        OrderDao orderDao = new OrderDao(dataSource);
        ProductDao productDao = new ProductDao(dataSource);
        // 3. 功能单元层：依赖两个 DAO
        OrderCreateUnit orderCreateUnit = new OrderCreateUnit(orderDao, productDao);
        // 4. 编排层：依赖功能单元
        OrderBizComponent orderBiz = new OrderBizComponent(orderCreateUnit, orderDao);
        // 5. 接口层
        OrderController controller = new OrderController(orderBiz);
    }
}
```

问题清单：

| 痛点 | 说明 |
|---|---|
| 组装代码爆炸 | 100 个类就有 100 行 new，且顺序必须正确 |
| 单例难管理 | `OrderDao` 被 10 个类用，要保证只 new 一次并到处传 |
| 替换实现困难 | 测试时想把 `PayClient` 换成 Mock，要改所有 new 的地方 |
| 横切逻辑无处安放 | 想给所有 DAO 方法加事务、加日志，只能每个方法手写 |
| 生命周期无人管 | 连接池什么时候初始化、进程退出时谁来关闭 |

### 3.2 IoC 与 DI：把「new」交出去

- **IoC（Inversion of Control，控制反转）**：对象的创建和组装权从业务代码「反转」给容器。
- **DI（Dependency Injection，依赖注入）**：IoC 的实现方式——容器把依赖「注入」给你，而不是你自己去找。

```
传统方式：  OrderBizComponent ──主动 new──▶ OrderCreateUnit
IoC 方式：  OrderBizComponent ◀──容器注入── [ IoC 容器 ] ──创建──▶ OrderCreateUnit
```

### 3.3 TS ↔ Java 对照：同一件事的三种写法

```ts
// NestJS：与 Spring 几乎同构
@Injectable()
export class OrderCreateUnit {
  constructor(
    private readonly orderDao: OrderDao,
    private readonly productDao: ProductDao,
  ) {}
}

@Injectable()
export class OrderBizComponent {
  // 构造器参数类型即依赖声明，容器按类型注入
  constructor(private readonly orderCreateUnit: OrderCreateUnit) {}
}

// React Context：依赖不靠 props 层层传，而是从「容器」里取
const OrderServiceContext = createContext<OrderService | null>(null);
function OrderPage() {
  const orderService = useContext(OrderServiceContext);
  // ...
}
```

```java
// Spring：标注 @Component 即注册到容器，构造器参数即依赖
@Component
public class OrderCreateUnit {

    private final OrderDao orderDao;
    private final ProductDao productDao;

    /**
     * 构造器注入：容器按参数类型查找 Bean 并传入。
     * 只有一个构造器时 @Autowired 可省略（Spring 4.3+）。
     *
     * @param orderDao   订单表读写能力
     * @param productDao 商品表读写能力
     */
    public OrderCreateUnit(OrderDao orderDao, ProductDao productDao) {
        this.orderDao = orderDao;
        this.productDao = productDao;
    }
}
```

> 实际项目里用 Lombok 的 `@RequiredArgsConstructor` 为所有 `final` 字段生成构造器，效果同上，后文都这么写。

---

## 4. IoC 容器

### 4.1 BeanFactory vs ApplicationContext

```
          BeanFactory                      ← 最核心的接口：getBean()，懒加载
              ▲
     ┌────────┴──────────┐
ListableBeanFactory   HierarchicalBeanFactory
              ▲
      ApplicationContext                   ← 面向应用的「增强版容器」
              ▲
  ConfigurableApplicationContext
              ▲
  AnnotationConfigApplicationContext          ← 纯 Spring 注解启动
  AnnotationConfigServletWebServerApplicationContext  ← Spring Boot Web 应用实际用的
```

| 对比项 | BeanFactory | ApplicationContext |
|---|---|---|
| 定位 | 底层 IoC 基础设施 | 面向应用开发者的完整容器 |
| 单例创建时机 | 首次 `getBean` 时（懒） | `refresh()` 时预先创建所有非懒加载单例 |
| BeanPostProcessor | 需手动注册 | 自动发现并注册 |
| 事件机制 | 无 | 有（`publishEvent`） |
| 国际化、资源加载、环境变量 | 无 | 有（`MessageSource`、`ResourceLoader`、`Environment`） |
| 实际使用 | 几乎不直接用 | **日常用的都是它** |

**设计取舍**：ApplicationContext 启动时就创建所有单例，代价是启动慢一点，换来的是「配置错误在启动时就暴露」（快速失败），而不是在第一个请求时才炸。这和前端「构建期报错优于运行期报错」是同一思想。

ApplicationContext 内部**组合**了一个 `DefaultListableBeanFactory`，真正干活的是它：

```
ApplicationContext
   └── DefaultListableBeanFactory
         ├── beanDefinitionMap   Map<String, BeanDefinition>   key: beanName，value: Bean 的「图纸」
         ├── singletonObjects    Map<String, Object>           key: beanName，value: 完整单例（一级缓存）
         └── beanPostProcessors  List<BeanPostProcessor>       扩展点列表
```

**BeanDefinition 是关键**：容器先把所有类「扫描成图纸」（类名、作用域、是否懒加载、依赖、初始化方法……），再统一按图纸生产对象。分成两阶段，才有了在「生产前改图纸」的扩展点 `BeanFactoryPostProcessor`。

### 4.2 Bean 的定义方式

| 方式 | 适用场景 | 示例 |
|---|---|---|
| `@Component` | 通用组件 | 编排层、功能单元 |
| `@Service` | 业务服务（语义化，等同 `@Component`） | 传统三层的 Service |
| `@Repository` | 数据访问层，额外开启持久化异常转换 | DAO |
| `@Controller` / `@RestController` | Web 接口层 | Controller |
| `@Configuration` + `@Bean` | **第三方类**（无法在源码上加注解）、需要复杂构建逻辑 | 线程池、RestClient、Redisson |

```java
/**
 * 订单模块基础设施配置：为无法加注解的第三方类声明 Bean。
 */
@Configuration
public class OrderInfraConfig {

    /**
     * 订单导出专用线程池（第 04 章已讲参数含义）。
     *
     * @return 有界队列 + 调用者执行拒绝策略的线程池
     */
    @Bean(destroyMethod = "shutdown")
    public ThreadPoolExecutor orderExportExecutor() {
        return new ThreadPoolExecutor(
                4, 8, 60, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(200),
                Thread.ofPlatform().name("order-export-", 0).factory(),
                new ThreadPoolExecutor.CallerRunsPolicy());
    }
}
```

**`@Configuration` 的 Full 模式与 Lite 模式**（高频原理题）：

```java
@Configuration // Full 模式：类会被 CGLIB 增强
public class DemoConfig {

    /**
     * 声明 A。
     *
     * @return A 的实例
     */
    @Bean
    public A a() {
        return new A(b()); // 这里调用 b() 会被代理拦截，返回容器里的单例 B
    }

    /**
     * 声明 B。
     *
     * @return B 的实例
     */
    @Bean
    public B b() {
        return new B();
    }
}
```

- Full 模式（`@Configuration`）：配置类被 CGLIB 子类化，`b()` 调用被拦截 → 先查容器，保证单例语义。
- Lite 模式（`@Component` 里写 `@Bean`，或 `@Configuration(proxyBeanMethods = false)`）：`b()` 就是普通方法调用，每次 new 一个新 B。
- Spring Boot 自身的自动配置类大量使用 `proxyBeanMethods = false`：**少一次 CGLIB 增强，启动更快**，前提是方法之间不互相调用（改用方法参数注入）。

### 4.3 依赖注入的方式

```java
@Component
@RequiredArgsConstructor
public class OrderBizComponent {

    // ✅ 方式一：构造器注入（推荐）。final + Lombok 生成构造器
    private final OrderCreateUnit orderCreateUnit;

    // ⚠️ 方式二：字段注入。简洁，但有下文所述缺陷
    // @Autowired
    // private OrderDao orderDao;

    // ⚠️ 方式三：Setter 注入。适合「可选依赖」
    // @Autowired(required = false)
    // public void setPayClient(PayClient payClient) { ... }
}
```

**为什么推荐构造器注入**：

| 维度 | 构造器注入 | 字段注入 |
|---|---|---|
| 不可变 | 字段可以 `final` | 不能 `final` |
| 依赖完整性 | 对象创建即完整，不存在「半成品」 | 创建后才反射赋值，中间态字段为 null |
| 单元测试 | 直接 `new X(mockA, mockB)` | 必须靠反射或启动容器 |
| 依赖过多的信号 | 构造器参数 8 个时一眼看出「这个类职责太多了」 | 字段注入把问题藏起来 |
| 循环依赖 | 启动即报错（逼你修设计） | 被三级缓存「默默」解决，隐藏设计问题 |
| 与容器解耦 | 纯 Java，离开 Spring 也能用 | 强依赖 Spring 反射 |

### 4.4 @Autowired / @Resource / @Qualifier / @Primary

同一类型有多个实现时，容器要知道注入哪一个。

```java
/**
 * 支付渠道能力接口。
 */
public interface PayClient {

    /**
     * 发起支付。
     *
     * @param orderNo 订单号
     * @param amount  支付金额
     * @return 三方支付流水号
     */
    String pay(String orderNo, BigDecimal amount);

    /**
     * 发起退款。
     *
     * @param orderNo 订单号
     * @param amount  退款金额
     */
    void refund(String orderNo, BigDecimal amount);
}

@Primary          // 有多个候选时默认选我
@Component("alipayClient")
public class AlipayClient implements PayClient { /* ... */ }

@Component("wechatPayClient")
public class WechatPayClient implements PayClient { /* ... */ }
```

```java
@Component
public class PayBizComponent {

    private final PayClient defaultClient;
    private final PayClient wechatClient;
    /** 所有支付渠道，key：beanName（如 alipayClient），value：对应实现 */
    private final Map<String, PayClient> clientMap;

    /**
     * 注入多个支付渠道。
     *
     * @param defaultClient 无限定时注入 @Primary 的实现（支付宝）
     * @param wechatClient  @Qualifier 按 beanName 精确指定
     * @param clientMap     注入 Map 时，容器把同类型所有 Bean 以 beanName 为 key 放入
     */
    public PayBizComponent(PayClient defaultClient,
                           @Qualifier("wechatPayClient") PayClient wechatClient,
                           Map<String, PayClient> clientMap) {
        this.defaultClient = defaultClient;
        this.wechatClient = wechatClient;
        this.clientMap = clientMap;
    }
}
```

| 注解 | 来源 | 默认匹配规则 | 备注 |
|---|---|---|---|
| `@Autowired` | Spring | **先按类型**，多个候选再按 `@Primary` → `@Priority` → 参数/字段名匹配 beanName | 可配 `required=false` |
| `@Resource` | Jakarta（JSR-250） | **先按名称**（name 属性或字段名），找不到再按类型 | 不支持构造器参数 |
| `@Qualifier("x")` | Spring | 按 beanName 精确限定 | 与 `@Autowired` 搭配 |
| `@Primary` | Spring | 声明在实现类上，多候选时的默认选择 | 用于「主实现 + 少数特例」 |

> 注入 `Map<String, PayClient>` / `List<PayClient>` 是**策略模式**的标准写法：新增一个支付渠道只需加一个 `@Component`，编排层零修改。13 章设计模式会再提。

### 4.5 Bean 作用域

| 作用域 | 含义 | 典型场景 |
|---|---|---|
| `singleton`（默认） | 容器内只有一个实例 | 99% 的 Bean：无状态的 Component、DAO |
| `prototype` | 每次 `getBean` / 注入都新建 | 有状态的、非线程安全的对象（如某个 Builder） |
| `request` | 每个 HTTP 请求一个 | 请求级上下文（但实践中更常用 ThreadLocal） |
| `session` | 每个 HTTP Session 一个 | 传统有状态 Web，前后端分离后很少用 |
| `application` | 每个 ServletContext 一个 | 极少用 |

**单例 Bean 必须无状态**——这是前端转岗最容易忽视的一点。Node 单线程里模块级变量随便用，但 Spring 单例被**所有请求线程同时调用**：

```java
@Component
public class BadOrderBizComponent {

    // ❌ 单例 Bean 的成员变量被所有线程共享，并发下 A 用户可能拿到 B 用户的 userId
    private Long currentUserId;

    /**
     * 错误示范：把请求级数据存到单例字段里。
     *
     * @param userId 当前用户
     */
    public void handle(Long userId) {
        this.currentUserId = userId;
        // ... 其他线程此时可能已经改掉了 currentUserId
    }
}
```

**单例里注入 prototype 的陷阱**：单例只在创建时注入一次，prototype 也就只创建了一次。需要每次拿新实例时，注入 `ObjectProvider<T>`：

```java
@Component
@RequiredArgsConstructor
public class ReportBizComponent {

    /** 延迟获取器：每次 getObject() 都会向容器要一个新的 prototype 实例 */
    private final ObjectProvider<ReportBuilder> reportBuilderProvider;

    /**
     * 生成报表，每次调用使用全新的 Builder。
     *
     * @return 报表内容
     */
    public String build() {
        ReportBuilder builder = reportBuilderProvider.getObject();
        return builder.append("header").toString();
    }
}
```

---

## 5. Bean 的完整生命周期

### 5.1 全景图

```
  ┌──────────────────────────── 容器启动 refresh() ────────────────────────────┐
  │ ① 扫描/解析 → 生成 BeanDefinition（图纸）                                   │
  │ ② BeanFactoryPostProcessor：修改图纸（如解析 ${} 占位符、解析 @Configuration）│
  │ ③ 注册所有 BeanPostProcessor                                                │
  │ ④ 逐个创建非懒加载单例 ↓                                                     │
  └────────────────────────────────────────────────────────────────────────────┘
                                   │
        ┌──────────────────────────▼──────────────────────────┐
        │ 1. 实例化 Instantiation                              │  createBeanInstance：反射调用构造器
        │    （构造器注入的依赖在这一步就要准备好）             │
        └──────────────────────────┬──────────────────────────┘
                                   │  ← 单例在此时把「半成品工厂」放入三级缓存（解决循环依赖）
        ┌──────────────────────────▼──────────────────────────┐
        │ 2. 属性填充 Populate                                 │  populateBean：@Autowired 字段/Setter、@Value
        └──────────────────────────┬──────────────────────────┘
        ┌──────────────────────────▼──────────────────────────┐
        │ 3. Aware 回调                                        │  BeanNameAware → BeanClassLoaderAware
        │                                                      │  → BeanFactoryAware
        └──────────────────────────┬──────────────────────────┘
        ┌──────────────────────────▼──────────────────────────┐
        │ 4. BeanPostProcessor#postProcessBeforeInitialization │  ApplicationContextAware 在这里回调
        │                                                      │  @PostConstruct 也在这里执行
        └──────────────────────────┬──────────────────────────┘
        ┌──────────────────────────▼──────────────────────────┐
        │ 5. 初始化 Initialization                             │  InitializingBean#afterPropertiesSet
        │                                                      │  → 自定义 init-method
        └──────────────────────────┬──────────────────────────┘
        ┌──────────────────────────▼──────────────────────────┐
        │ 6. BeanPostProcessor#postProcessAfterInitialization  │  ★ AOP 在这里生成代理对象并替换原对象
        └──────────────────────────┬──────────────────────────┘
                                   ▼
                       放入一级缓存 singletonObjects，可以使用
                                   │
                              容器关闭 close()
        ┌──────────────────────────▼──────────────────────────┐
        │ 7. 销毁                                              │  @PreDestroy → DisposableBean#destroy
        │                                                      │  → 自定义 destroy-method
        └─────────────────────────────────────────────────────┘
```

记忆口诀：**实例化 → 填属性 → Aware → 前置处理 → 初始化 → 后置处理（AOP）→ 使用 → 销毁**。

### 5.2 代码验证

```java
/**
 * 生命周期演示 Bean：按回调顺序打印日志。
 */
@Slf4j
@Component
public class LifecycleDemoBean implements BeanNameAware, ApplicationContextAware,
        InitializingBean, DisposableBean {

    private OrderDao orderDao;

    /**
     * 1. 构造器：实例化阶段。
     */
    public LifecycleDemoBean() {
        log.info("1. 构造器执行");
    }

    /**
     * 2. Setter 注入：属性填充阶段。
     *
     * @param orderDao 订单 DAO
     */
    @Autowired
    public void setOrderDao(OrderDao orderDao) {
        log.info("2. 属性填充 orderDao");
        this.orderDao = orderDao;
    }

    /**
     * 3. Aware：容器把 beanName 告诉我。
     *
     * @param name 当前 Bean 的名称
     */
    @Override
    public void setBeanName(String name) {
        log.info("3. BeanNameAware: {}", name);
    }

    /**
     * 4a. ApplicationContextAware：由 BeanPostProcessor 前置阶段回调。
     *
     * @param ctx 应用上下文
     */
    @Override
    public void setApplicationContext(ApplicationContext ctx) {
        log.info("4a. ApplicationContextAware");
    }

    /**
     * 4b. @PostConstruct：由 CommonAnnotationBeanPostProcessor 前置阶段回调。
     */
    @PostConstruct
    public void postConstruct() {
        log.info("4b. @PostConstruct");
    }

    /**
     * 5a. InitializingBean：所有属性设置完毕后的初始化。
     */
    @Override
    public void afterPropertiesSet() {
        log.info("5a. afterPropertiesSet");
    }

    /**
     * 7a. @PreDestroy：容器关闭时最先回调。
     */
    @PreDestroy
    public void preDestroy() {
        log.info("7a. @PreDestroy");
    }

    /**
     * 7b. DisposableBean：销毁回调。
     */
    @Override
    public void destroy() {
        log.info("7b. DisposableBean#destroy");
    }
}
```

| 初始化方式 | 推荐度 | 说明 |
|---|---|---|
| `@PostConstruct` | ⭐⭐⭐ | 业务代码首选，标准注解，与 Spring 接口解耦 |
| `InitializingBean` | ⭐⭐ | 框架/中间件代码常用，无反射开销 |
| `@Bean(initMethod=...)` | ⭐⭐ | 第三方类无法加注解时用 |

> **前端类比**：`@PostConstruct` ≈ React 的 `useEffect(() => {...}, [])` / Vue 的 `mounted`，「依赖都就绪了，可以做初始化」；`@PreDestroy` ≈ `useEffect` 返回的清理函数 / `beforeUnmount`。

---

## 6. 扩展点与事件机制

Spring 之所以能成为「框架的框架」（MyBatis、Dubbo、Feign 都是通过扩展点接入的），靠的就是下面三个扩展点。

### 6.1 BeanFactoryPostProcessor：改图纸

时机：所有 BeanDefinition 加载完、**任何 Bean 实例化之前**。能改的是「图纸」，不是对象。

```java
/**
 * 演示：启动时把 com.example.mall.biz 包下的所有 Bean 设为懒加载。
 * 真实场景：PropertySourcesPlaceholderConfigurer 解析 ${xxx} 占位符；
 * ConfigurationClassPostProcessor 解析 @Configuration / @ComponentScan / @Import。
 */
@Component
public class LazyBizBeanFactoryPostProcessor implements BeanFactoryPostProcessor {

    /**
     * 遍历所有 BeanDefinition，按包名修改懒加载属性。
     *
     * @param beanFactory 可配置的 BeanFactory，此时只有图纸没有实例
     */
    @Override
    public void postProcessBeanFactory(ConfigurableListableBeanFactory beanFactory) {
        for (String name : beanFactory.getBeanDefinitionNames()) {
            BeanDefinition bd = beanFactory.getBeanDefinition(name);
            String className = bd.getBeanClassName();
            // 只处理编排层，其余保持原样
            if (className != null && className.startsWith("com.example.mall.biz")) {
                bd.setLazyInit(true);
            }
        }
    }
}
```

> ⚠️ BFPP 本身必须尽早实例化，如果用 `@Bean` 声明它，方法要写成 `static`，否则会导致所在配置类被过早创建、其 `@Autowired` 失效。

### 6.2 BeanPostProcessor：改对象

时机：**每个 Bean** 初始化前后。可以返回一个**不同的对象**替换原 Bean——AOP 代理就是这样「偷梁换柱」的。

```java
/**
 * 检测初始化耗时过长的 Bean（拖慢启动的元凶）。
 */
@Slf4j
@Component
public class SlowBeanInitDetector implements BeanPostProcessor {

    /** 慢初始化阈值（毫秒） */
    private static final long SLOW_THRESHOLD_MS = 200;

    /** 初始化开始时间，key：beanName，value：开始时刻（毫秒时间戳） */
    private final Map<String, Long> startTimeMap = new ConcurrentHashMap<>();

    /**
     * 初始化前记录开始时间。
     *
     * @param bean     原始 Bean
     * @param beanName Bean 名称
     * @return 原样返回，不替换
     */
    @Override
    public Object postProcessBeforeInitialization(Object bean, String beanName) {
        startTimeMap.put(beanName, System.currentTimeMillis());
        return bean;
    }

    /**
     * 初始化后计算耗时，超阈值则告警。
     *
     * @param bean     已初始化的 Bean
     * @param beanName Bean 名称
     * @return 原样返回；AOP 的 AbstractAutoProxyCreator 就是在这里返回代理对象
     */
    @Override
    public Object postProcessAfterInitialization(Object bean, String beanName) {
        Long start = startTimeMap.remove(beanName);
        if (start != null) {
            long cost = System.currentTimeMillis() - start;
            if (cost > SLOW_THRESHOLD_MS) {
                log.warn("Bean [{}] 初始化耗时 {} ms", beanName, cost);
            }
        }
        return bean;
    }
}
```

> 方法签名里的 `Object` 是框架接口约定（任何类型的 Bean 都要经过它），不属于「用 Object 充当数据结构」。

| 扩展点 | 作用对象 | 时机 | 典型实现 |
|---|---|---|---|
| `BeanDefinitionRegistryPostProcessor` | 图纸注册表 | 最早，可**新增**图纸 | `ConfigurationClassPostProcessor`、MyBatis 的 `MapperScannerConfigurer` |
| `BeanFactoryPostProcessor` | 图纸 | 实例化前 | `PropertySourcesPlaceholderConfigurer` |
| `InstantiationAwareBeanPostProcessor` | 对象 | 实例化前后、属性填充 | `AutowiredAnnotationBeanPostProcessor`（处理 @Autowired） |
| `BeanPostProcessor` | 对象 | 初始化前后 | `AnnotationAwareAspectJAutoProxyCreator`（AOP） |

> MyBatis 的 Mapper 只是接口，为什么能注入？`MapperScannerConfigurer` 在注册阶段为每个 Mapper 接口注册一个 `MapperFactoryBean` 图纸，后者的 `getObject()` 返回 JDK 动态代理。**扩展点 + FactoryBean + 动态代理**，是几乎所有「接口即可调用」框架（Feign、Dubbo）的共同套路。

### 6.3 ApplicationListener：事件机制

```ts
// 前端 / Node：EventEmitter
const bus = new EventEmitter();
bus.on('orderCreated', (e: { orderNo: string }) => sendSms(e.orderNo));
bus.emit('orderCreated', { orderNo: 'O123' });
```

```java
/**
 * 订单创建成功事件（进程内事件，第 10 章会换成 MQ 消息）。
 *
 * @param orderNo 订单号
 * @param userId  下单用户 ID
 */
public record OrderCreatedEvent(String orderNo, Long userId) {
}
```

```java
/**
 * 订单创建事件监听器：处理下单后的非核心动作。
 */
@Slf4j
@Component
public class OrderCreatedListener {

    /**
     * 事务提交后发送下单通知。
     * AFTER_COMMIT：只有下单事务真正提交才执行，回滚则不触发，避免「订单没了短信却发了」。
     *
     * @param event 订单创建事件
     */
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        log.info("发送下单通知，orderNo={}", event.orderNo());
    }
}
```

```java
// 发布方：注入 ApplicationEventPublisher
applicationEventPublisher.publishEvent(new OrderCreatedEvent(order.getOrderNo(), userId));
```

| 对比 | EventEmitter | Spring 事件 |
|---|---|---|
| 执行方式 | 同步调用 listener | **默认同步**，在发布者线程执行；加 `@Async` 变异步 |
| 异常 | listener 抛错会冒泡到 emit | 同步监听器抛异常会传播给发布者（可能导致事务回滚） |
| 与事务联动 | 无 | `@TransactionalEventListener` 可绑定 BEFORE_COMMIT / AFTER_COMMIT / AFTER_ROLLBACK / AFTER_COMPLETION |
| 跨进程 | 否 | 否，跨进程要用 MQ（第 10 章） |

Spring 自身的生命周期事件：`ContextRefreshedEvent`、`ApplicationReadyEvent`（Boot，应用可接收流量时）、`ContextClosedEvent`。缓存预热常放在 `ApplicationReadyEvent` 里。

---

## 7. 循环依赖与三级缓存

### 7.1 什么是循环依赖

```
A ──依赖──▶ B
▲           │
└──依赖─────┘
```

```java
@Component
public class A {
    @Autowired
    private B b;
}

@Component
public class B {
    @Autowired
    private A a;
}
```

### 7.2 三级缓存

`DefaultSingletonBeanRegistry` 中的三个 Map：

| 级别 | 字段 | key / value | 存放内容 |
|---|---|---|---|
| 一级 | `singletonObjects` | beanName → Bean | 完整的单例，可直接用 |
| 二级 | `earlySingletonObjects` | beanName → Bean | **提前暴露**的早期引用（可能是代理），属性尚未填充完 |
| 三级 | `singletonFactories` | beanName → `ObjectFactory` | 生成早期引用的**工厂**（lambda：`() -> getEarlyBeanReference(...)`） |

### 7.3 解决过程（字段注入）

```
getBean(A)
 │ 1. 一二三级缓存都没有 A → 开始创建
 │ 2. 实例化 A（构造器执行完，得到「半成品 A」）
 │ 3. 往三级缓存放 A 的 ObjectFactory
 │ 4. 填充 A 的属性 → 发现需要 B → getBean(B)
 │     │ 4.1 实例化 B，三级缓存放 B 的 ObjectFactory
 │     │ 4.2 填充 B 的属性 → 需要 A → getBean(A)
 │     │      │ 一级没有 → 二级没有 → 三级有！
 │     │      │ 调用 ObjectFactory.getObject()
 │     │      │   └─ 若 A 需要 AOP，在此【提前】创建 A 的代理；否则返回原始 A
 │     │      │ 结果放入二级缓存，删除三级缓存
 │     │      └─ 返回早期 A
 │     │ 4.3 B 拿到早期 A，完成初始化 → 放入一级缓存
 │     └─ 返回完整的 B
 │ 5. A 拿到 B，完成初始化
 │ 6. postProcessAfterInitialization：发现 A 已提前代理过，不再重复代理
 │ 7. 从二级缓存取出早期引用（代理）作为最终对象 → 放入一级缓存
 └─ 完成
```

### 7.4 为什么要三级，二级不行吗？

- 只为解决循环依赖，**二级就够了**：实例化后直接把半成品放进二级缓存即可。
- 问题在于 **AOP**：如果 A 需要被代理，B 拿到的必须是 A 的**代理**，而不是原始 A，否则 B 调用 A 时事务、日志统统失效。
- 用二级缓存的话，只能在实例化后**立刻**为每个 Bean 创建代理——这违背了 Spring 的设计：「代理在初始化完成后（BPP after 阶段）才创建」。
- 三级缓存存的是**工厂**而不是对象：**只有真的发生循环依赖时才调用工厂提前创建代理**；没有循环依赖的 Bean（绝大多数）仍按正常节奏在最后一步创建代理。

本质：**三级缓存是用「延迟决策」来兼顾「解决循环依赖」与「不打乱 AOP 正常时机」的设计取舍。**

### 7.5 哪些循环依赖解决不了

| 场景 | 能否解决 | 原因 |
|---|---|---|
| 单例 + 字段/Setter 注入 | ✅ | 上述流程 |
| **构造器注入** | ❌ | 实例化 A 时就需要 B，而此时 A 连半成品都没有，无法放入三级缓存 |
| prototype 作用域 | ❌ | prototype 不进缓存，每次新建会无限递归 |
| `@Async` 标注的 Bean 参与循环 | ❌（常见报错） | `@Async` 的代理由另一个 BPP 在 after 阶段创建，未参与早期引用，导致注入出去的和最终的不是同一个对象 |

构造器注入可以用 `@Lazy` 打破：注入一个延迟代理，首次调用时才真正去容器取。

```java
/**
 * 用 @Lazy 打破构造器循环依赖（治标手段）。
 *
 * @param b 实际注入的是 B 的延迟代理
 */
public A(@Lazy B b) {
    this.b = b;
}
```

### 7.6 Spring Boot 2.6+ 默认禁止循环依赖

Spring Boot 2.6 起 `spring.main.allow-circular-references` 默认 `false`，出现循环依赖直接启动失败：

```
***************************
APPLICATION FAILED TO START
***************************
The dependencies of some of the beans in the application context form a cycle:
┌─────┐
|  a (field private com.example.B com.example.A.b)
↑     ↓
|  b (field private com.example.A com.example.B.a)
└─────┘
```

**官方态度很明确：循环依赖是设计问题，不该由框架兜底。** 正确的修法：

1. 抽出公共部分到第三个类 C，A、B 都依赖 C；
2. 按本系列的五层架构，**依赖只能自上而下单向**——编排层依赖功能单元，功能单元绝不反向依赖编排层，同层之间不互相依赖。遵守分层，循环依赖基本不会出现；
3. 改用事件解耦（A 发事件，B 监听）。

---

## 8. AOP：面向切面编程

### 8.1 问题：横切逻辑

接口耗时日志、权限校验、事务、缓存……这些逻辑「横着」切过所有业务方法：

```
           createOrder()   getOrder()   cancelOrder()
               │               │              │
 耗时日志 ─────┼───────────────┼──────────────┼────── ← 一个切面
 事    务 ─────┼───────────────┼──────────────┼────── ← 一个切面
               │               │              │
```

### 8.2 TS ↔ Java 对照

```ts
// 前端：高阶函数包一层
function withLogCost<T extends (...args: any[]) => any>(name: string, fn: T): T {
  return ((...args) => {
    const start = Date.now();
    try {
      return fn(...args);
    } finally {
      console.log(`${name} cost ${Date.now() - start}ms`);
    }
  }) as T;
}
const createOrder = withLogCost('createOrder', rawCreateOrder);

// TS 方法装饰器：本质是在类定义时替换 descriptor.value
function LogCost(name: string) {
  return (target: any, key: string, desc: PropertyDescriptor) => {
    const raw = desc.value;
    desc.value = function (...args: any[]) {
      const start = Date.now();
      try { return raw.apply(this, args); }
      finally { console.log(`${name} cost ${Date.now() - start}ms`); }
    };
  };
}
```

```java
// Java：注解只是「标记」，真正的增强逻辑写在切面里，运行时由代理织入
@LogCost("创建订单")
public OrderVO createOrder(CreateOrderDTO dto) { ... }
```

**关键差异**：TS 装饰器**直接改写了类上的方法**，所以 `this.method()` 也会走增强逻辑；Spring AOP **不改原类**，而是生成一个代理对象包在外面——**只有经过代理的调用才会被增强**。这是后文「事务自调用失效」的根源。

### 8.3 核心概念

| 术语 | 英文 | 含义 | 类比 |
|---|---|---|---|
| 连接点 | JoinPoint | 可以被增强的点，Spring AOP 中**只有方法执行** | 所有可被包装的函数 |
| 切点 | Pointcut | 一个表达式，**筛选**哪些连接点要增强 | 「哪些函数要包一层」的规则 |
| 通知 | Advice | 增强逻辑本身 + 执行时机 | 高阶函数里新增的代码 |
| 切面 | Aspect | 切点 + 通知 的组合 | 一个完整的 `withXxx` |
| 目标对象 | Target | 被代理的原始对象 | 原函数 |
| 织入 | Weaving | 把切面应用到目标、生成代理的过程 | 调用 `withXxx(fn)` |

通知类型与执行顺序（Spring 5.2.7+，同一切面内）：

```
@Around（前半段）
   └─▶ @Before
         └─▶ 目标方法
               ├─ 正常返回 ─▶ @AfterReturning
               └─ 抛出异常 ─▶ @AfterThrowing
         └─▶ @After（类似 finally，总会执行）
@Around（后半段）
```

常用切点表达式：

| 表达式 | 含义 |
|---|---|
| `execution(* com.example.mall.biz..*.*(..))` | biz 包及子包下所有类的所有方法 |
| `@annotation(com.example.mall.common.annotation.LogCost)` | 标注了 `@LogCost` 的方法 |
| `within(com.example.mall.controller..*)` | controller 包下所有类型内的方法 |
| `bean(*BizComponent)` | beanName 以 BizComponent 结尾的 Bean |

> 实践建议：**优先用注解型切点**。`execution` 按包名大面积匹配容易误伤，而注解是显式声明，读代码的人知道这个方法被增强了。

### 8.4 原理：JDK 动态代理 vs CGLIB

```
              调用方
                │ orderBiz.createOrder()
                ▼
     ┌─────────────────────────┐
     │  代理对象 $Proxy / $$SpringCGLIB$$ │  ← 容器里注册的是它
     │   1. 执行前置通知        │
     │   2. 调用 target.xxx() ──┼──▶  原始对象 OrderBizComponent
     │   3. 执行后置通知        │
     └─────────────────────────┘
```

| 对比 | JDK 动态代理 | CGLIB |
|---|---|---|
| 原理 | 运行时生成实现**同一接口**的类 `$Proxy0` | 运行时用 ASM 生成**目标类的子类**，重写方法 |
| 前提 | 目标**必须实现接口** | 目标类不能是 `final`；被代理的方法不能是 `final`/`private`/`static` |
| 注入类型 | 只能按接口类型注入 | 接口、实现类都可以 |
| Spring Boot 默认 | — | **Spring Boot 2.0+ 默认 CGLIB**（`spring.aop.proxy-target-class=true`） |

> Spring Boot 默认 CGLIB 的原因：开发者常常直接注入实现类（`@Autowired OrderBizComponent`），若用 JDK 代理，容器里的对象是 `$Proxy` 而不是 `OrderBizComponent`，会报类型不匹配。CGLIB 的子类既是接口类型也是实现类类型，更不容易出错。

### 8.5 手写一个 JDK 动态代理

```java
/**
 * 订单查询能力接口（JDK 代理要求目标实现接口）。
 */
public interface OrderQueryApi {

    /**
     * 按订单号查询订单状态描述。
     *
     * @param orderNo 订单号
     * @return 状态描述
     */
    String queryStatus(String orderNo);
}

/**
 * 目标类：真实业务实现。
 */
public class OrderQueryApiImpl implements OrderQueryApi {

    /**
     * 模拟查询。
     *
     * @param orderNo 订单号
     * @return 固定返回「待支付」
     */
    @Override
    public String queryStatus(String orderNo) {
        return OrderStatusEnum.CREATED.getDesc();
    }
}
```

```java
/**
 * 耗时统计的调用处理器：JDK 代理把所有方法调用都转发到 invoke。
 */
public class LogCostInvocationHandler implements InvocationHandler {

    /** 被代理的原始对象 */
    private final OrderQueryApi target;

    /**
     * @param target 被代理的原始对象
     */
    public LogCostInvocationHandler(OrderQueryApi target) {
        this.target = target;
    }

    /**
     * 代理对象上的每次方法调用都会进入这里。
     *
     * @param proxy  代理对象本身（不要在这里调用 proxy 的方法，会无限递归）
     * @param method 被调用的接口方法
     * @param args   调用参数
     * @return 目标方法的返回值
     * @throws Throwable 目标方法抛出的原始异常
     */
    @Override
    public Object invoke(Object proxy, Method method, Object[] args) throws Throwable {
        long start = System.nanoTime();
        try {
            // 反射调用原始对象的同名方法
            return method.invoke(target, args);
        } catch (InvocationTargetException e) {
            // 反射会把业务异常包一层，这里拆出来原样抛出
            throw e.getTargetException();
        } finally {
            System.out.printf("%s cost %d μs%n", method.getName(), (System.nanoTime() - start) / 1000);
        }
    }

    /**
     * 演示入口：生成代理并调用。
     *
     * @param args 命令行参数
     */
    public static void main(String[] args) {
        OrderQueryApi target = new OrderQueryApiImpl();
        OrderQueryApi proxy = (OrderQueryApi) Proxy.newProxyInstance(
                OrderQueryApi.class.getClassLoader(),
                new Class<?>[]{OrderQueryApi.class},
                new LogCostInvocationHandler(target));
        // 输出：待支付，并打印 queryStatus cost xx μs
        System.out.println(proxy.queryStatus("O20261126000001"));
        // 输出：class jdk.proxy1.$Proxy0 —— 容器里存的就是这种对象
        System.out.println(proxy.getClass());
    }
}
```

对应的 CGLIB 版本（使用 Spring 内置的重打包版 `org.springframework.cglib`）：

```java
/**
 * CGLIB 代理演示：无需接口，生成目标类的子类。
 */
public class CglibDemo {

    /**
     * 生成 OrderQueryApiImpl 的子类代理并调用。
     *
     * @param args 命令行参数
     */
    public static void main(String[] args) {
        Enhancer enhancer = new Enhancer();
        enhancer.setSuperclass(OrderQueryApiImpl.class);
        // MethodInterceptor：子类重写的每个方法都会进入这里
        enhancer.setCallback((MethodInterceptor) (obj, method, methodArgs, methodProxy) -> {
            long start = System.nanoTime();
            try {
                // invokeSuper 调用父类（原始类）方法，不走反射，性能更好
                return methodProxy.invokeSuper(obj, methodArgs);
            } finally {
                System.out.printf("%s cost %d μs%n", method.getName(), (System.nanoTime() - start) / 1000);
            }
        });
        OrderQueryApiImpl proxy = (OrderQueryApiImpl) enhancer.create();
        System.out.println(proxy.queryStatus("O20261126000001"));
    }
}
```

> 注意 CGLIB 里 `invokeSuper(obj, ...)` 是在**代理对象自身**上调父类方法，所以「代理对象内部的 this 调用」也会被拦截；而 **Spring AOP 不是这么用的**——Spring 的 CGLIB 代理持有一个独立的 target 对象，调用时转发给 target，target 内部的 `this` 指向原始对象，所以自调用**不会**被增强。这一点决定了第 9 节的事务自调用失效。

### 8.6 Spring AOP vs AspectJ

| 对比 | Spring AOP | AspectJ |
|---|---|---|
| 织入时机 | 运行时（动态代理） | 编译期 / 类加载期（改字节码） |
| 连接点 | 仅方法执行 | 方法、构造器、字段读写、静态初始化…… |
| 自调用 | ❌ 不生效 | ✅ 生效 |
| 使用成本 | 零配置 | 需要 ajc 编译器或 Java Agent |

Spring 借用了 AspectJ 的**注解和切点表达式语法**（`@Aspect`、`@Around`），但底层仍是动态代理。绝大多数项目用 Spring AOP 就够了。

---

## 9. 声明式事务 @Transactional

### 9.1 先回顾：数据库事务

```sql
START TRANSACTION;
INSERT INTO t_order (...) VALUES (...);
INSERT INTO t_order_item (...) VALUES (...);
UPDATE t_product SET stock = stock - 1 WHERE id = 1001 AND stock >= 1;
COMMIT;   -- 任何一步失败则 ROLLBACK
```

ACID 与隔离级别的数据库底层实现（undo log、MVCC、锁）在第 08 章展开，本章关注 **Spring 如何帮你管理这段 BEGIN/COMMIT/ROLLBACK**。

### 9.2 编程式 → 声明式

不用 Spring 时，事务代码是这样的：

```java
/**
 * 手写 JDBC 事务：业务逻辑被事务样板代码淹没。
 *
 * @param dataSource 数据源
 * @throws SQLException 数据库异常
 */
public void createOrderManually(DataSource dataSource) throws SQLException {
    Connection conn = dataSource.getConnection();
    try {
        conn.setAutoCommit(false);          // 开启事务
        insertOrder(conn);                  // 每个 DAO 方法都得传 conn，才能共用同一个连接
        insertItems(conn);
        deductStock(conn);
        conn.commit();
    } catch (Exception e) {
        conn.rollback();
        throw e;
    } finally {
        conn.close();
    }
}
```

两个痛点：① 样板代码；② **conn 必须层层传参**才能保证多个 DAO 用同一个连接（同一个连接才是同一个事务）。

Spring 的方案：

```java
@Transactional(rollbackFor = Exception.class)
public OrderPO createOrder(Long userId, List<OrderItemDTO> items) {
    // 只写业务，DAO 内部自动拿到同一个连接
}
```

### 9.3 原理：AOP 代理 + TransactionManager + ThreadLocal

```
调用方 orderCreateUnit.createOrder()
   │
   ▼
CGLIB 代理 ── TransactionInterceptor（一个 AOP 通知）
   │ 1. 解析方法上的 @Transactional → TransactionAttribute（传播行为、隔离级别、rollbackFor…）
   │ 2. PlatformTransactionManager.getTransaction(attr)
   │       └─ DataSourceTransactionManager：
   │            a. 从连接池拿一个 Connection
   │            b. conn.setAutoCommit(false)
   │            c. TransactionSynchronizationManager.bindResource(dataSource, connHolder)
   │               └─ 本质：ThreadLocal<Map<DataSource, ConnectionHolder>>
   │                         key：数据源，value：持有连接的 Holder
   │ 3. 调用目标方法 ───────────────────────────────────────────────┐
   │                                                                 ▼
   │                                    OrderDao → MyBatis → SqlSessionTemplate
   │                                    → DataSourceUtils.getConnection(dataSource)
   │                                    → 先查 ThreadLocal，有则复用同一个连接 ✅
   │ 4a. 正常返回 → commit
   │ 4b. 抛出异常 → 判断 rollbackOn(ex)：是则 rollback，否则仍 commit
   │ 5. 解绑 ThreadLocal，归还连接（恢复 autoCommit）
   ▼
返回调用方
```

三个关键结论，后面所有坑都能从这里推导：

1. **靠 AOP 代理**：不经过代理的调用（自调用、new 出来的对象），事务不生效；
2. **靠异常判断回滚**：异常被吞、异常类型不匹配，就不回滚；
3. **靠 ThreadLocal 绑定连接**：换了线程就拿不到同一个连接，就不在同一个事务里。

### 9.4 传播行为（Propagation）

传播行为回答的是：**一个事务方法调用另一个事务方法时，内层用外层的事务，还是自己开一个？**

| 传播行为 | 外层有事务 | 外层无事务 | 使用频率 |
|---|---|---|---|
| `REQUIRED`（默认） | 加入外层 | 新建 | ⭐⭐⭐⭐⭐ |
| `REQUIRES_NEW` | **挂起外层，新建独立事务** | 新建 | ⭐⭐⭐ |
| `NESTED` | 在外层事务内建**保存点**（savepoint） | 新建 | ⭐ |
| `SUPPORTS` | 加入外层 | 非事务执行 | ⭐ |
| `NOT_SUPPORTED` | 挂起外层，非事务执行 | 非事务执行 | ⭐ |
| `MANDATORY` | 加入外层 | 抛异常 | 很少 |
| `NEVER` | 抛异常 | 非事务执行 | 很少 |

重点区分 REQUIRED / REQUIRES_NEW / NESTED：

```
REQUIRED：         外层事务 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                   内层                ┗━ 同一个事务 ━┛
                   → 同生共死：内层抛异常，整个事务被标记回滚

REQUIRES_NEW：     外层事务 ━━━━━━━┓（挂起）          ┏━━━━━━━━━━
                   内层               ┗━ 独立新事务（新连接）━┛
                   → 互不影响：内层已提交，外层回滚也不会撤销内层

NESTED：           外层事务 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                   内层                 ↑SAVEPOINT ━━━ 
                   → 内层失败只回滚到保存点，外层可继续；外层回滚则内层一起回滚
```

| 场景 | 选择 | 原因 |
|---|---|---|
| 下单：写订单 + 明细 + 扣库存 | `REQUIRED` | 必须原子 |
| 下单失败也要记录失败日志 | 日志方法用 `REQUIRES_NEW` | 外层回滚时日志不能跟着回滚 |
| 批量导入，单条失败不影响其他条，但整体失败要全撤销 | 单条用 `NESTED` | 保存点语义 |

`REQUIRES_NEW` 的代价：**会占用第二个连接**。如果连接池 10 个连接，10 个并发请求都持有外层连接、等待内层新连接 → **连接池死锁**。高并发路径慎用。

### 9.5 隔离级别

| 隔离级别 | 脏读 | 不可重复读 | 幻读 | 说明 |
|---|---|---|---|---|
| `READ_UNCOMMITTED` | ✅ | ✅ | ✅ | 几乎不用 |
| `READ_COMMITTED` | ❌ | ✅ | ✅ | Oracle、PostgreSQL 默认；很多互联网公司把 MySQL 也调成它 |
| `REPEATABLE_READ` | ❌ | ❌ | 部分避免 | **MySQL InnoDB 默认**，MVCC + 间隙锁大幅避免幻读 |
| `SERIALIZABLE` | ❌ | ❌ | ❌ | 性能最差 |
| `DEFAULT`（Spring 默认） | — | — | — | 使用数据库自身的默认级别 |

`@Transactional(isolation = ...)` 只是在开启事务时执行 `SET TRANSACTION ISOLATION LEVEL`，99% 的情况用 `DEFAULT` 即可。底层原理见第 08 章。

### 9.6 rollbackFor：默认只回滚非受检异常

```
Throwable
├── Error                 ← 默认回滚
└── Exception
    ├── RuntimeException  ← 默认回滚（NPE、BizException…）
    └── IOException 等受检异常  ← ⚠️ 默认【不】回滚，照常提交！
```

> 为什么这样设计？这是沿袭 EJB 的约定：受检异常被视为「业务上可预期的结果」，调用方应该处理，而非系统故障。但这个约定和大多数人的直觉相反，所以**团队规范通常强制 `rollbackFor = Exception.class`**。

### 9.7 事务失效的十种场景

#### ① 自调用（最高频）

```java
@Component
@RequiredArgsConstructor
public class SelfInvokeDemo {

    private final OrderDao orderDao;

    /**
     * 外层无事务方法，内部用 this 调用事务方法。
     *
     * @param order 订单
     */
    public void entry(OrderPO order) {
        // ❌ this 指向原始对象，不是代理 → 绕过 TransactionInterceptor
        this.doSave(order);
    }

    /**
     * 期望有事务，实际没有。
     *
     * @param order 订单
     */
    @Transactional(rollbackFor = Exception.class)
    public void doSave(OrderPO order) {
        orderDao.insertOrder(order);
        throw new BizException(ErrorCode.SYSTEM_ERROR); // 订单不会回滚
    }
}
```

修复方式（按推荐度）：

| 方式 | 做法 | 评价 |
|---|---|---|
| 拆到另一个 Bean | 把事务方法放进独立的功能单元（如 `OrderCreateUnit`） | ✅ **最推荐**，也符合五层架构 |
| 注入自己 | `@Lazy @Autowired private SelfInvokeDemo self;` 调用 `self.doSave()` | 可用，但有点绕 |
| `AopContext.currentProxy()` | 需 `@EnableAspectJAutoProxy(exposeProxy = true)` | 侵入性强，不推荐 |
| 编程式事务 | `TransactionTemplate` | 适合只想包一小段代码 |

#### ② 方法不是 public / 是 final / 是 static

```java
@Transactional
private void save() { }          // ❌ private：CGLIB 子类无法重写

@Transactional
public final void save() { }     // ❌ final：无法重写，调用直接落到原始对象（且其字段为 null，常伴随 NPE）

@Transactional
public static void save() { }    // ❌ static：不属于对象，代理无从拦截
```

> 版本差异：Spring 5.x 及以前（含 Java 8 存量项目）`protected` / 包可见方法上的 `@Transactional` 会被**静默忽略**；Spring 6.0+ 在 CGLIB 代理下支持 `protected` 和包可见方法。为了跨版本一致，**统一用 public**。

#### ③ 异常被 catch 吞掉

```java
/**
 * ❌ 异常被吞：拦截器看不到异常，判定为正常结束而提交。
 *
 * @param order 订单
 */
@Transactional(rollbackFor = Exception.class)
public void createSwallow(OrderPO order) {
    try {
        orderDao.insertOrder(order);
        productDao.deductStock(1001L, 1);
    } catch (Exception e) {
        log.error("下单失败", e);  // 吞掉了 → 订单已插入，但库存未扣，数据不一致
    }
}
```

修复：catch 后**重新抛出**；或确实不想抛时手动标记回滚：

```java
} catch (Exception e) {
    log.error("下单失败", e);
    TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
}
```

#### ④ 受检异常未配置 rollbackFor

```java
/**
 * ❌ IOException 是受检异常，默认不回滚。
 *
 * @param order 订单
 * @throws IOException 写文件失败
 */
@Transactional
public void createAndWriteFile(OrderPO order) throws IOException {
    orderDao.insertOrder(order);
    Files.writeString(Path.of("/readonly/order.txt"), order.getOrderNo()); // 抛 IOException → 订单仍提交
}
```

修复：`@Transactional(rollbackFor = Exception.class)`。

#### ⑤ 多线程

```java
/**
 * ❌ 子线程里的 DAO 拿不到主线程 ThreadLocal 里的连接，自己开了新连接（自动提交）。
 *
 * @param order 订单
 * @param items 明细
 */
@Transactional(rollbackFor = Exception.class)
public void createParallel(OrderPO order, List<OrderItemPO> items) {
    orderDao.insertOrder(order);
    CompletableFuture.runAsync(() -> orderDao.batchInsertItems(items), executor); // 不在事务内
    throw new BizException(ErrorCode.SYSTEM_ERROR); // 订单回滚了，明细却已提交
}
```

结论：**一个事务 = 一个线程 + 一个连接**。需要并行时，并行做「读」和「计算」，把「写」收拢到一个线程的事务里。

#### ⑥ 对象不是 Spring 管理的

```java
OrderCreateUnit unit = new OrderCreateUnit(orderDao, productDao, orderConverter); // ❌ 自己 new 的，没有代理
unit.createOrder(userId, items);
```

#### ⑦ 传播行为配置导致「没有事务」

```java
/**
 * ❌ 外层没有事务时，SUPPORTS 以非事务方式运行，NOT_SUPPORTED 永远非事务运行。
 *
 * @param order 订单
 */
@Transactional(propagation = Propagation.SUPPORTS)
public void save(OrderPO order) { ... }
```

#### ⑧ 数据库引擎不支持事务

MySQL 的 MyISAM 引擎不支持事务，Spring 发出的 ROLLBACK 无效。确认表引擎：`SHOW TABLE STATUS LIKE 't_order';`，统一用 InnoDB。

#### ⑨ 多数据源时事务管理器不匹配

```java
/**
 * ❌ 方法操作的是 orderDataSource，但 @Transactional 用了默认（绑定 productDataSource 的）事务管理器，
 * 绑定到 ThreadLocal 的是另一个数据源的连接，DAO 拿不到，自动提交。
 *
 * @param order 订单
 */
@Transactional(rollbackFor = Exception.class)
public void save(OrderPO order) { ... }

// ✅ 显式指定：@Transactional(transactionManager = "orderTransactionManager", rollbackFor = Exception.class)
```

#### ⑩ 内层 REQUIRED 抛异常、外层 catch：UnexpectedRollbackException

这不是「失效」，而是「意外回滚」，非常经典：

```java
/**
 * 外层：想「内层失败就算了，继续执行」。
 *
 * @param order 订单
 */
@Transactional(rollbackFor = Exception.class)
public void outer(OrderPO order) {
    orderDao.insertOrder(order);
    try {
        pointUnit.addPoints(order.getUserId()); // 内层 REQUIRED，抛了异常
    } catch (Exception e) {
        log.warn("加积分失败，忽略");
    }
    // 方法正常结束，准备 commit……
}
// 结果：抛出 UnexpectedRollbackException: Transaction silently rolled back
//       because it has been marked as rollback-only
```

原因：内层与外层是**同一个事务**，内层抛异常时，内层的拦截器已把这个共享事务标记为 rollback-only；外层吞了异常想提交，Spring 发现标记，只能回滚并抛出此异常告诉你。
修复：内层改 `REQUIRES_NEW` 或 `NESTED`；或者内层不抛异常而是返回结果。

#### 一张表总结

| # | 场景 | 根因 |
|---|---|---|
| 1 | 自调用 | 没经过代理 |
| 2 | 非 public / final / static | 代理无法重写 |
| 3 | 异常被吞 | 拦截器看不到异常 |
| 4 | 受检异常 | 默认只回滚 RuntimeException / Error |
| 5 | 多线程 | ThreadLocal 绑定的连接跨不了线程 |
| 6 | 非 Spring Bean | 没有代理 |
| 7 | 传播行为配错 | 根本没开事务 |
| 8 | MyISAM | 数据库不支持 |
| 9 | 多数据源 | 事务管理器绑错数据源 |
| 10 | 内层标记 rollback-only | 共享事务被标记，外层无法提交 |

### 9.8 编程式事务 TransactionTemplate

声明式事务的粒度是「整个方法」，而很多时候只有其中一小段需要事务：

```java
/**
 * 订单取消功能单元：演示用 TransactionTemplate 精确控制事务边界。
 */
@Component
@RequiredArgsConstructor
public class OrderCancelUnit {

    private final TransactionTemplate transactionTemplate;
    private final OrderDao orderDao;
    private final ProductDao productDao;
    private final PayClient payClient;

    /**
     * 取消订单：先调三方退款（慢、不可回滚），再在一个短事务里改状态并回补库存。
     *
     * @param order 待取消的订单
     * @param items 订单明细，用于回补库存
     */
    public void cancel(OrderPO order, List<OrderItemPO> items) {
        // 1. 远程调用放在事务外：网络慢不会长时间占用数据库连接
        payClient.refund(order.getOrderNo(), order.getTotalAmount());
        // 2. 只把两张表的写操作包进事务
        transactionTemplate.executeWithoutResult(status -> {
            orderDao.updateStatus(order.getId(), OrderStatusEnum.CREATED.getCode(), OrderStatusEnum.CANCELLED.getCode());
            items.forEach(item -> productDao.restoreStock(item.getProductId(), item.getQuantity()));
        });
    }
}
```

| 对比 | 声明式 `@Transactional` | 编程式 `TransactionTemplate` |
|---|---|---|
| 粒度 | 方法级 | 代码块级 |
| 自调用问题 | 有 | 无 |
| 可读性 | 业务代码干净 | 多一层 lambda |
| 适用 | 绝大多数场景 | 需要精确控制边界、避免大事务 |

### 9.9 大事务的危害

```java
@Transactional(rollbackFor = Exception.class)
public void createOrderBad(CreateOrderDTO dto) {
    ProductPO product = productDao.getById(...);   // 查询，无需事务
    riskClient.check(...);                         // ❌ RPC 调用 800ms
    orderDao.insertOrder(...);
    productDao.deductStock(...);                   // 行锁从这里开始持有……
    smsClient.send(...);                           // ❌ 发短信 500ms
    mqProducer.send(...);                          // ❌ 发 MQ，且事务回滚了消息却已发出
}                                                  // ……直到这里才释放
```

| 危害 | 说明 |
|---|---|
| 连接池耗尽 | 一个请求占用连接 1.5s，连接池 20 个 → QPS 上限约 13 |
| 锁持有时间长 | 扣库存的行锁一直持有到提交，同商品的其他下单请求全部排队 |
| 回滚代价大 | undo log 多，回滚慢 |
| 主从延迟 | 大事务的 binlog 一次性写入，从库回放慢 |
| 数据不一致 | 事务内发的 MQ / 短信无法回滚 |

治理原则：

1. 查询、校验、RPC 调用移到事务外；
2. 事务内只放**必须原子**的写操作；
3. 消息、通知放到事务提交后（`@TransactionalEventListener(AFTER_COMMIT)`，或第 10 章的事务消息 / 本地消息表）；
4. 必要时用 `TransactionTemplate` 精确控制边界。

---

## 10. mini-mall 实战

### 10.1 IoC 组装：五层依赖关系

```
OrderController            （① 接口层，第 07 章实现）
   │ 构造器注入
   ▼
OrderBizComponent          （② 编排层）
   │ 构造器注入
   ▼
OrderCreateUnit            （③ 功能单元，事务边界）
   │ 构造器注入
   ├──────────────┬───────────────┬──────────────────────────┐
   ▼              ▼               ▼                          ▼
OrderDao       ProductDao     OrderConverter        ApplicationEventPublisher
（④ 能力单元）  （④ 能力单元） （⑤ 转换，MapStruct）   （Spring 内置 Bean）
```

依赖**自上而下单向**，不存在循环依赖。

公共基础类（第 07 章会完整讲解，错误码枚举 `ErrorCode` 也在第 07 章定义，这里先给出本章用到的部分）：

```java
/**
 * 订单状态枚举，code 与 t_order.status 一一对应。
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

    /** 数据库存储值 */
    private final int code;
    /** 展示文案 */
    private final String desc;
}
```

```java
/**
 * 业务异常：携带错误码，由全局异常处理器转换为 Result（第 07 章）。
 * 继承 RuntimeException，保证 @Transactional 默认即可回滚。
 */
@Getter
public class BizException extends RuntimeException {

    /** 错误码 */
    private final ErrorCode errorCode;

    /**
     * 使用错误码默认文案构造。
     *
     * @param errorCode 错误码
     */
    public BizException(ErrorCode errorCode) {
        super(errorCode.getMessage());
        this.errorCode = errorCode;
    }

    /**
     * 使用自定义文案构造（如带上具体商品 ID）。
     *
     * @param errorCode 错误码
     * @param message   覆盖默认文案的提示信息
     */
    public BizException(ErrorCode errorCode, String message) {
        super(message);
        this.errorCode = errorCode;
    }
}
```

### 10.2 能力单元：DAO

```java
/**
 * 订单与订单明细表读写能力（t_order、t_order_item）。
 */
@Repository
@RequiredArgsConstructor
public class OrderDao {

    private final OrderMapper orderMapper;
    private final OrderItemMapper orderItemMapper;

    /**
     * 插入订单主表，插入后 order.id 会被回填。
     *
     * @param order 订单 PO
     */
    public void insertOrder(OrderPO order) {
        orderMapper.insert(order);
    }

    /**
     * 批量插入订单明细（MyBatis-Plus 3.5.7+ 支持 insert(Collection)）。
     *
     * @param items 明细 PO 列表，orderId 须已设置
     */
    public void batchInsertItems(List<OrderItemPO> items) {
        orderItemMapper.insert(items);
    }

    /**
     * 按订单号查询订单。
     *
     * @param orderNo 订单号
     * @return 订单 PO，不存在返回 null
     */
    public OrderPO getByOrderNo(String orderNo) {
        return orderMapper.selectOne(Wrappers.<OrderPO>lambdaQuery().eq(OrderPO::getOrderNo, orderNo));
    }

    /**
     * 查询订单下的所有明细。
     *
     * @param orderId 订单主键
     * @return 明细列表，无数据返回空列表
     */
    public List<OrderItemPO> listItemsByOrderId(Long orderId) {
        return orderItemMapper.selectList(
                Wrappers.<OrderItemPO>lambdaQuery().eq(OrderItemPO::getOrderId, orderId));
    }

    /**
     * 条件更新订单状态（只有当前状态等于 fromStatus 才更新，防并发覆盖，详见 08/10 章）。
     *
     * @param orderId    订单主键
     * @param fromStatus 期望的当前状态码，取值见 OrderStatusEnum
     * @param toStatus   目标状态码
     * @return 影响行数：1 成功，0 当前状态已不是 fromStatus
     */
    public int updateStatus(Long orderId, int fromStatus, int toStatus) {
        return orderMapper.update(null, Wrappers.<OrderPO>lambdaUpdate()
                .set(OrderPO::getStatus, toStatus)
                .eq(OrderPO::getId, orderId)
                .eq(OrderPO::getStatus, fromStatus));
    }
}
```

```java
/**
 * 商品表读写能力（t_product）。
 */
@Repository
@RequiredArgsConstructor
public class ProductDao {

    private final ProductMapper productMapper;

    /**
     * 按主键批量查询商品。
     *
     * @param ids 商品 ID 集合
     * @return 商品列表（不存在的 ID 不会出现在结果中）
     */
    public List<ProductPO> listByIds(Collection<Long> ids) {
        return productMapper.selectBatchIds(ids);
    }

    /**
     * 扣减库存：利用 WHERE stock >= quantity 做条件更新，防止超卖。
     *
     * @param productId 商品 ID
     * @param quantity  扣减数量
     * @return true 扣减成功；false 库存不足
     */
    public boolean deductStock(Long productId, int quantity) {
        return productMapper.deductStock(productId, quantity) > 0;
    }

    /**
     * 回补库存（取消订单时）。
     *
     * @param productId 商品 ID
     * @param quantity  回补数量
     */
    public void restoreStock(Long productId, int quantity) {
        productMapper.restoreStock(productId, quantity);
    }
}
```

```java
/**
 * 商品表 Mapper，自定义扣减/回补库存 SQL（第 08 章会改造为乐观锁版本）。
 */
public interface ProductMapper extends BaseMapper<ProductPO> {

    /**
     * 条件扣减库存。
     *
     * @param productId 商品 ID
     * @param quantity  扣减数量
     * @return 影响行数，0 表示库存不足
     */
    @Update("UPDATE t_product SET stock = stock - #{quantity}, version = version + 1 "
            + "WHERE id = #{productId} AND stock >= #{quantity}")
    int deductStock(@Param("productId") Long productId, @Param("quantity") int quantity);

    /**
     * 回补库存。
     *
     * @param productId 商品 ID
     * @param quantity  回补数量
     * @return 影响行数
     */
    @Update("UPDATE t_product SET stock = stock + #{quantity}, version = version + 1 WHERE id = #{productId}")
    int restoreStock(@Param("productId") Long productId, @Param("quantity") int quantity);
}
```

### 10.3 功能单元：OrderCreateUnit（事务边界）

下单要写 `t_order`、`t_order_item`，并更新 `t_product`，三张表必须原子——按规范封装为一个功能单元，对外只暴露一个事务方法。

```java
/**
 * 下单功能单元：校验商品 → 扣库存 → 写订单主表 → 写订单明细，在同一个事务中完成。
 * 对外提供稳定的「创建订单」能力，被下单接口、批量导单、后台补单等不同入口复用。
 */
@Component
@RequiredArgsConstructor
public class OrderCreateUnit {

    private final OrderDao orderDao;
    private final ProductDao productDao;
    private final OrderConverter orderConverter;
    private final ApplicationEventPublisher eventPublisher;

    /**
     * 创建订单（事务方法）。任一步骤抛出异常，三张表的写操作整体回滚。
     *
     * @param userId 下单用户 ID
     * @param items  下单商品明细（productId + quantity）
     * @return 已落库的订单 PO（含自增 id 与 orderNo）
     * @throws BizException 商品不存在（PRODUCT_NOT_FOUND）或库存不足（STOCK_NOT_ENOUGH）
     */
    @Transactional(rollbackFor = Exception.class)
    public OrderPO createOrder(Long userId, List<OrderItemDTO> items) {
        // 1. 合并同一商品的数量，并按 productId 升序排列
        Map<Long, Integer> quantityMap = mergeQuantity(items);
        // 2. 批量查询商品并校验存在性（价格以数据库为准，不信任前端传值）
        Map<Long, ProductPO> productMap = loadProducts(quantityMap.keySet());
        // 3. 逐个扣减库存，任何一个不足则抛异常回滚
        deductStock(quantityMap);
        // 4. 组装明细与主表
        List<OrderItemPO> itemPOs = buildItems(quantityMap, productMap);
        OrderPO order = buildOrder(userId, itemPOs);
        // 5. 先写主表拿到 id，再回填明细的 orderId 后批量写入
        orderDao.insertOrder(order);
        itemPOs.forEach(item -> item.setOrderId(order.getId()));
        orderDao.batchInsertItems(itemPOs);
        // 6. 在事务内发布事件；监听器为 AFTER_COMMIT，提交成功后才真正执行，回滚则丢弃
        eventPublisher.publishEvent(new OrderCreatedEvent(order.getOrderNo(), userId));
        return order;
    }

    /**
     * 合并重复商品的购买数量。
     * 使用 TreeMap 保证按 productId 升序：并发下单时所有事务以相同顺序加行锁，避免死锁。
     *
     * @param items 下单明细
     * @return key：productId，value：该商品的购买总数
     */
    private Map<Long, Integer> mergeQuantity(List<OrderItemDTO> items) {
        return items.stream().collect(Collectors.toMap(
                OrderItemDTO::getProductId, OrderItemDTO::getQuantity, Integer::sum, TreeMap::new));
    }

    /**
     * 批量加载商品，有任一商品不存在则抛出业务异常。
     *
     * @param productIds 商品 ID 集合
     * @return key：productId，value：商品 PO
     */
    private Map<Long, ProductPO> loadProducts(Set<Long> productIds) {
        Map<Long, ProductPO> productMap = productDao.listByIds(productIds).stream()
                .collect(Collectors.toMap(ProductPO::getId, Function.identity()));
        for (Long id : productIds) {
            if (!productMap.containsKey(id)) {
                throw new BizException(ErrorCode.PRODUCT_NOT_FOUND, "商品不存在：" + id);
            }
        }
        return productMap;
    }

    /**
     * 按顺序扣减库存。
     *
     * @param quantityMap key：productId，value：扣减数量（已按 productId 升序）
     */
    private void deductStock(Map<Long, Integer> quantityMap) {
        quantityMap.forEach((productId, quantity) -> {
            if (!productDao.deductStock(productId, quantity)) {
                throw new BizException(ErrorCode.STOCK_NOT_ENOUGH, "库存不足：" + productId);
            }
        });
    }

    /**
     * 组装订单明细（商品名、单价做快照，避免后续商品改价影响历史订单）。
     *
     * @param quantityMap key：productId，value：购买数量
     * @param productMap  key：productId，value：商品 PO
     * @return 明细 PO 列表（orderId 尚未设置）
     */
    private List<OrderItemPO> buildItems(Map<Long, Integer> quantityMap, Map<Long, ProductPO> productMap) {
        return quantityMap.entrySet().stream()
                .map(e -> orderConverter.toItemPO(productMap.get(e.getKey()), e.getValue()))
                .toList();
    }

    /**
     * 组装订单主表：生成订单号、汇总金额、初始状态为待支付。
     *
     * @param userId  下单用户 ID
     * @param itemPOs 订单明细
     * @return 订单 PO（id 尚未生成）
     */
    private OrderPO buildOrder(Long userId, List<OrderItemPO> itemPOs) {
        // 金额必须用 BigDecimal 累加，避免浮点误差
        BigDecimal total = itemPOs.stream()
                .map(i -> i.getPrice().multiply(BigDecimal.valueOf(i.getQuantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        OrderPO order = new OrderPO();
        order.setOrderNo(OrderNoUtil.generate());
        order.setUserId(userId);
        order.setTotalAmount(total);
        order.setStatus(OrderStatusEnum.CREATED.getCode());
        return order;
    }
}
```

> **设计说明**：所有 private 方法都在同一个事务里执行（它们是被 `createOrder` 通过 `this` 调用的普通方法，不需要单独的事务）。事务注解**只加在对外的入口方法上**。

### 10.4 编排层：OrderBizComponent

```java
/**
 * 订单编排组件：组合功能单元与通知能力，实现「下单」「查单」业务流程。
 * 业务流程变化（如下单前加风控、下单后加积分）优先只改这一层。
 */
@Component
@RequiredArgsConstructor
public class OrderBizComponent {

    private final OrderCreateUnit orderCreateUnit;
    private final OrderDao orderDao;
    private final OrderConverter orderConverter;

    /**
     * 创建订单编排：调用下单功能单元 → 查询明细 → 转换出参。
     *
     * @param userId 当前登录用户 ID
     * @param dto    下单入参
     * @return 订单详情 VO
     */
    @LogCost("创建订单")
    public OrderVO createOrder(Long userId, CreateOrderDTO dto) {
        // 1. 事务在功能单元内部开启和提交（跨 Bean 调用，经过代理 ✅）
        OrderPO order = orderCreateUnit.createOrder(userId, dto.getItems());
        // 2. 查询明细并组装返回值
        return orderConverter.toVO(order, orderDao.listItemsByOrderId(order.getId()));
    }
}
```

> 注意：`@TransactionalEventListener` 默认只在「发布时存在事务」时触发，所以事件在 `OrderCreateUnit` 的事务**内**发布；若在事务外发布，监听器会被静默跳过（除非设置 `fallbackExecution = true`）。

### 10.5 AOP 实战：@LogCost 接口耗时切面

```java
/**
 * 方法耗时日志注解：标注后由 LogCostAspect 打印耗时，超过阈值打印 WARN。
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME) // 必须是 RUNTIME，否则运行时反射读不到
@Documented
public @interface LogCost {

    /**
     * @return 业务名称，打印在日志中，便于检索
     */
    String value() default "";

    /**
     * @return 慢调用阈值（毫秒），超过则打印 WARN
     */
    long slowMs() default 500;
}
```

```java
/**
 * 耗时日志切面：拦截所有标注 @LogCost 的方法。
 */
@Slf4j
@Aspect
@Component
public class LogCostAspect {

    /**
     * 环绕通知：记录方法执行耗时，异常照常抛出，不改变原方法行为。
     *
     * @param pjp     连接点，可获取方法签名、参数并执行原方法
     * @param logCost 方法上的注解实例（通过参数名绑定）
     * @return 原方法返回值
     * @throws Throwable 原方法抛出的异常，原样向上抛
     */
    @Around("@annotation(logCost)")
    public Object around(ProceedingJoinPoint pjp, LogCost logCost) throws Throwable {
        String name = resolveName(pjp, logCost);
        long start = System.currentTimeMillis();
        boolean success = false;
        try {
            Object result = pjp.proceed();
            success = true;
            return result;
        } finally {
            // finally 中统一记录：成功、失败都要有耗时
            logCost(name, System.currentTimeMillis() - start, logCost.slowMs(), success);
        }
    }

    /**
     * 解析日志名称：注解未填 value 时，使用「类名.方法名」。
     *
     * @param pjp     连接点
     * @param logCost 注解
     * @return 日志中展示的名称
     */
    private String resolveName(ProceedingJoinPoint pjp, LogCost logCost) {
        if (!logCost.value().isEmpty()) {
            return logCost.value();
        }
        MethodSignature sig = (MethodSignature) pjp.getSignature();
        return sig.getDeclaringType().getSimpleName() + "." + sig.getName();
    }

    /**
     * 按阈值输出不同级别的日志。
     *
     * @param name    业务名称
     * @param costMs  耗时（毫秒）
     * @param slowMs  慢调用阈值（毫秒）
     * @param success 是否正常返回
     */
    private void logCost(String name, long costMs, long slowMs, boolean success) {
        if (costMs > slowMs) {
            log.warn("[LogCost] {} 慢调用 cost={}ms success={}", name, costMs, success);
        } else {
            log.info("[LogCost] {} cost={}ms success={}", name, costMs, success);
        }
    }
}
```

> `around` 的返回类型 `Object` 是 AspectJ 通知签名的强制约定（被拦截的方法可能返回任意类型）。依赖：`spring-boot-starter-aop`（Spring Boot 3.x 中 web starter 不再间接引入，需显式添加）。

调用 `POST /api/orders` 后日志：

```
INFO  [LogCost] 创建订单 cost=37ms success=true
```

**切面执行顺序**：一个方法同时有 `@LogCost` 和 `@Transactional` 时，谁在外层？用 `@Order` 控制，数值越小越靠外。事务切面默认 `Ordered.LOWEST_PRECEDENCE`（最内层），所以自定义切面默认包在事务外面——`@LogCost` 统计的耗时**包含**事务提交时间，正合我们意。

### 10.6 演示：自调用导致事务失效

把事务方法错误地写在编排层内部，并用 `this` 调用：

```java
/**
 * 反例：事务方法与调用方在同一个类中。
 */
@Component
@RequiredArgsConstructor
public class BadOrderBizComponent {

    private final OrderDao orderDao;
    private final ProductDao productDao;

    /**
     * 编排入口（无事务）。
     *
     * @param order 订单
     * @param item  明细
     */
    public void createOrder(OrderPO order, OrderItemPO item) {
        // ❌ this 调用，不经过代理，doCreate 上的 @Transactional 形同虚设
        this.doCreate(order, item);
    }

    /**
     * 期望是事务方法。
     *
     * @param order 订单
     * @param item  明细
     */
    @Transactional(rollbackFor = Exception.class)
    public void doCreate(OrderPO order, OrderItemPO item) {
        orderDao.insertOrder(order);                       // 自动提交，已落库
        if (!productDao.deductStock(item.getProductId(), item.getQuantity())) {
            throw new BizException(ErrorCode.STOCK_NOT_ENOUGH);  // 抛异常，但订单不会回滚！
        }
    }
}
```

用单测复现（第 05 章的 JUnit 5 + Spring Boot Test）：

```java
@SpringBootTest
class BadOrderBizComponentTest {

    @Autowired
    private BadOrderBizComponent badOrderBiz;
    @Autowired
    private OrderDao orderDao;

    /**
     * 验证：库存不足抛异常后，订单仍残留在库中（事务失效）。
     */
    @Test
    void selfInvocationShouldNotRollback() {
        OrderPO order = newOrder("SELF_INVOKE_001");
        OrderItemPO item = newItem(1001L, 999_999); // 故意超过库存
        assertThatThrownBy(() -> badOrderBiz.createOrder(order, item))
                .isInstanceOf(BizException.class);
        // 断言：订单没有被回滚
        assertThat(orderDao.getByOrderNo("SELF_INVOKE_001")).isNotNull();
    }

    /**
     * 构造测试订单。
     *
     * @param orderNo 订单号
     * @return 待支付状态的订单 PO
     */
    private OrderPO newOrder(String orderNo) {
        OrderPO order = new OrderPO();
        order.setOrderNo(orderNo);
        order.setUserId(1L);
        order.setTotalAmount(BigDecimal.ZERO);
        order.setStatus(OrderStatusEnum.CREATED.getCode());
        return order;
    }

    /**
     * 构造测试明细。
     *
     * @param productId 商品 ID
     * @param quantity  购买数量
     * @return 明细 PO
     */
    private OrderItemPO newItem(Long productId, int quantity) {
        OrderItemPO item = new OrderItemPO();
        item.setProductId(productId);
        item.setQuantity(quantity);
        return item;
    }
}
```

**排查技巧**：在 `doCreate` 内打断点，看调用栈——如果没有 `TransactionInterceptor.invoke` 这一帧，就是没经过代理。也可以调用 `TransactionSynchronizationManager.isActualTransactionActive()` 打印当前是否在事务中。

修复即本节 10.3 的设计：**事务方法放在独立的功能单元 `OrderCreateUnit` 中，编排层跨 Bean 调用**。分层架构不仅是「代码整洁」，还直接避开了这一类 bug。

---

## 11. 常见坑

| # | 坑 | 后果 | 正确做法 |
|---|---|---|---|
| 1 | 单例 Bean 里存请求级数据 | 并发串号 | Bean 无状态；请求数据放方法参数或 ThreadLocal |
| 2 | 字段注入 + 循环依赖 | 2.6+ 启动失败；或隐藏设计问题 | 构造器注入 + 分层单向依赖 |
| 3 | `@Transactional` 加在 Controller 或编排层的大方法上 | 大事务 | 事务边界收敛在功能单元 |
| 4 | 不写 `rollbackFor` | 受检异常不回滚 | 统一 `rollbackFor = Exception.class` |
| 5 | catch 异常后只打日志 | 事务提交，数据不一致 | 重新抛出或 `setRollbackOnly()` |
| 6 | 事务内发 MQ / 调 RPC | 回滚后无法撤回；长事务 | 提交后再发（AFTER_COMMIT / 事务消息） |
| 7 | 在 `@PostConstruct` 里调用本类 `@Transactional` 方法 | 此时代理尚未生成 + 自调用，双重失效 | 放到 `ApplicationReadyEvent` 监听里通过 Bean 调用 |
| 8 | `@Configuration` 里直接 `new` 依赖并在多个 `@Bean` 方法里调用 | Lite 模式下产生多个实例 | 用方法参数注入依赖 |
| 9 | 切面里 `pjp.proceed()` 后忘记 `return` | 被拦截方法返回 null | 环绕通知必须返回原结果 |
| 10 | 用 `@Async` 却没加 `@EnableAsync` / 自调用 | 依然同步执行 | 与事务同理，必须跨 Bean 调用 |

---

## 12. 高级视角

### 12.1 读源码的入口

| 想搞懂 | 从这里开始读 |
|---|---|
| 容器启动 | `AbstractApplicationContext#refresh`（12 个步骤，是一切的总纲） |
| Bean 创建 | `AbstractAutowireCapableBeanFactory#doCreateBean` |
| 三级缓存 | `DefaultSingletonBeanRegistry#getSingleton(String, boolean)` |
| AOP 代理创建 | `AbstractAutoProxyCreator#wrapIfNecessary` |
| 事务拦截 | `TransactionAspectSupport#invokeWithinTransaction` |
| 传播行为 | `AbstractPlatformTransactionManager#getTransaction` / `handleExistingTransaction` |

建议用 IDEA 在 `doCreateBean` 打条件断点（`beanName.equals("orderCreateUnit")`），一步步走一遍，比读十篇文章都管用。

### 12.2 设计思想

- **模板方法**：`AbstractPlatformTransactionManager` 定义事务流程骨架，`DataSourceTransactionManager` / `JpaTransactionManager` 只实现 `doBegin` / `doCommit` 等钩子。
- **开闭原则**：Spring 核心几乎不需要修改，所有集成都通过扩展点完成。你写的功能单元也应该如此：对外契约稳定，内部可替换。
- **约定优于配置 + 快速失败**：启动时创建所有单例、2.6+ 禁止循环依赖，都是「让问题尽早暴露」。

### 12.3 事务与分布式

本章的事务都是**单库本地事务**。到第 11 章拆成订单服务、商品服务后，「扣库存」和「写订单」不在一个数据库里，`@Transactional` 就无能为力了，需要 Seata、本地消息表、事务消息等分布式事务方案。先把本地事务吃透，分布式事务才学得会。

### 12.4 性能视角

- 代理调用本身的开销是纳秒级，可忽略；真正的开销是**事务持有连接的时间**。
- 只读查询可以加 `@Transactional(readOnly = true)`：对 MySQL 驱动会设置连接只读，在读写分离路由中常被用作「走从库」的标识。但没必要给单条查询加事务。
- Java 21 虚拟线程下，ThreadLocal 绑定连接的机制依然成立（虚拟线程也有自己的 ThreadLocal），但大量虚拟线程并发时，**连接池大小才是真正的瓶颈**。

---

## 13. 小练习

1. **生命周期**：运行 5.2 节的 `LifecycleDemoBean`，再加一个自定义 `BeanPostProcessor` 打印 before/after，验证日志顺序与 5.1 节的图一致。
2. **循环依赖**：写两个互相字段注入的 Bean，分别在 `allow-circular-references` 为 `true` / `false` 下启动；再改为构造器注入，用 `@Lazy` 让它启动成功，打印注入对象的 `getClass()` 观察是什么。
3. **手写代理**：参照 8.5 节，用 JDK 动态代理实现一个「方法执行失败自动重试 3 次」的代理。
4. **AOP**：给 `@LogCost` 增加 `boolean logArgs() default false`，开启时打印入参（注意脱敏手机号）。
5. **传播行为**：写一个 `OrderLogUnit.saveFailLog()`，分别用 `REQUIRED` 和 `REQUIRES_NEW`，在下单失败时调用，观察失败日志是否落库；再复现第 ⑩ 种 `UnexpectedRollbackException`。
6. **事务失效**：把 9.7 节的十种场景各写一个单测，断言「数据被提交了」，加深记忆。
7. **大事务改造**：把 9.9 节的 `createOrderBad` 按治理原则拆分，画出改造前后的事务边界图。
