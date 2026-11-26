# 07 Spring Boot 与 Web 开发：自动配置、接口开发全套、五层分层架构

> [← 总纲](./00-outline.md) | [上一章：06 Spring 核心](./06-spring-core.md) | [下一章：08 数据库与持久层 →](./08-database-orm.md)

---

## 1. 本章地图

第 06 章讲的是「容器怎么管理对象」。本章把容器接上 HTTP，讲清楚一个请求从进入进程到返回 JSON 的全过程，并把 mini-mall 的「创建订单 / 查询订单」两个接口按五层架构完整落地。

```
浏览器 ──HTTP──▶ ┌─────────────── Spring Boot 进程 ───────────────┐
                 │ 内嵌 Tomcat（线程池接请求）            ← 4.4    │
                 │   ▼                                             │
                 │ Filter 链（TraceId、CORS）             ← 3.8/3.9│
                 │   ▼                                             │
                 │ DispatcherServlet（Spring MVC 总入口） ← 4.5    │
                 │   ▼                                             │
                 │ Interceptor（登录鉴权）                ← 3.10   │
                 │   ▼                                             │
                 │ 参数解析 + 校验（@RequestBody @Valid）  ← 3.4/3.5│
                 │   ▼                                             │
                 │ Controller → 编排 → 功能单元 → DAO     ← 3.14/5 │
                 │   ▼                                             │
                 │ 统一返回 Result<T> / 全局异常处理  ← 3.6/3.7  │
                 └─────────────────────────────────────────────────┘
  启动时：自动配置把上面这些组件全部装配好                ← 3.2/4.1/4.2
```

---

## 2. 前端类比

| 前端 | Spring Boot | 关键差异 |
|---|---|---|
| Vite / Next.js「约定优于配置」 | Spring Boot 自动配置 | Boot 的约定靠 `@Conditional` 条件装配，**你声明了同类 Bean 它就让位** |
| `npm i @nestjs/typeorm` 装一个包就能用 | Starter 依赖 | Starter 本身几乎没代码，只是「依赖清单 + 自动配置」 |
| `.env` / `.env.production` / `vite --mode` | `application.yml` / `application-prod.yml` / `--spring.profiles.active` | 支持层级结构、类型绑定、配置中心动态刷新 |
| Express `app.get('/x', handler)` | `@GetMapping("/x")` | 注解声明式路由，启动时扫描注册 |
| NestJS `@Body()` / `@Param()` / `@Query()` | `@RequestBody` / `@PathVariable` / `@RequestParam` | 几乎一一对应 |
| zod / class-validator | Bean Validation（`@NotNull` `@Valid`） | 注解写在 DTO 字段上 |
| Koa 洋葱中间件 | Filter + Interceptor + AOP | 三层，位置不同，能力不同 |
| NestJS ExceptionFilter | `@RestControllerAdvice` | 全局统一异常 → 统一 JSON |
| axios 响应拦截器里判断 `code` | `Result<T>` 统一返回 | 你以前是消费方，现在是定义方 |
| TS 里请求类型、响应类型、表单类型 | DTO / VO / PO | 按层分对象，不混用 |

---

## 3. 核心概念

### 3.1 Spring、Spring MVC、Spring Boot 的关系

```
┌────────────────────── Spring Boot ──────────────────────┐
│  自动配置 · Starter · 内嵌服务器 · 外部化配置 · Actuator │  ← 「脚手架 + 默认配置」
│  ┌─────────────────── Spring Framework ──────────────┐  │
│  │ Spring MVC（Web）· 事务 · AOP · JDBC · 测试 ……     │  │  ← 各功能模块
│  │ ┌───────────── Spring Core（IoC 容器）──────────┐ │  │  ← 第 06 章
│  │ └───────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

| 角色 | 一句话 | 前端类比 |
|---|---|---|
| Spring Framework | IoC + AOP + 一堆功能模块 | React 本身 |
| Spring MVC | Spring 里做 Web 的模块，核心是 `DispatcherServlet` | React Router + fetch 层 |
| Spring Boot | 把 Spring 及常用组件「开箱即用」地装配好 | Next.js / Vite：零配置跑起来 |

没有 Boot 的年代（Java 8 存量项目里你可能还会见到）：手写 `web.xml` 注册 DispatcherServlet、XML 配置数据源和事务管理器、打成 war 包部署到外部 Tomcat。Boot 把这些全部变成了「默认就有」。

### 3.2 Starter 与自动配置：怎么用

引入一个 starter：

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

就自动拥有了：内嵌 Tomcat、Spring MVC、Jackson、默认错误页、编码过滤器……一行配置都不用写。

| 常用 Starter | 带来什么 |
|---|---|
| `spring-boot-starter-web` | Spring MVC + Tomcat + Jackson |
| `spring-boot-starter-validation` | Hibernate Validator（Bean Validation 实现） |
| `spring-boot-starter-aop` | Spring AOP + AspectJ 织入器 |
| `spring-boot-starter-actuator` | 健康检查、指标（第 12 章） |
| `mybatis-plus-spring-boot3-starter` | MyBatis-Plus（第 08 章；**注意 Boot 3 要用带 boot3 的 artifact**） |
| `spring-boot-starter-data-redis` | Lettuce + RedisTemplate（第 09 章） |

**覆盖默认配置**：自动配置几乎都带 `@ConditionalOnMissingBean`，你自己声明一个同类型 Bean，它就自动让位：

```java
/**
 * 覆盖 Boot 默认的 Jackson 配置：Long 序列化为字符串，避免前端 JS 精度丢失。
 */
@Configuration
public class JacksonConfig {

    /**
     * 自定义 ObjectMapper 构建器。Boot 会把所有 Jackson2ObjectMapperBuilderCustomizer 应用到默认 ObjectMapper 上。
     *
     * @return 定制器
     */
    @Bean
    public Jackson2ObjectMapperBuilderCustomizer longToStringCustomizer() {
        return builder -> builder.serializerByType(Long.class, ToStringSerializer.instance);
    }
}
```

> 这是前端最该记住的配置之一：JS 的 `Number.MAX_SAFE_INTEGER` 是 2^53-1，而雪花 ID 是 64 位 long，**不转字符串前端拿到的 ID 末几位会变**。

### 3.3 配置体系

#### application.yml 与多环境

```
src/main/resources/
├── application.yml          ← 公共配置 + 指定激活哪个环境
├── application-dev.yml      ← 本地开发
├── application-test.yml     ← 测试环境
└── application-prod.yml     ← 生产环境
```

```yaml
# application.yml
spring:
  application:
    name: mini-mall
  profiles:
    active: dev            # 默认激活 dev，部署时用 --spring.profiles.active=prod 覆盖
server:
  port: 8080
mall:
  order:
    timeout-minutes: 30    # 订单超时自动取消时间（第 10 章用）
    max-items: 20          # 单笔订单最多商品种类数
  jwt:
    secret: ${JWT_SECRET:dev-only-secret-key-at-least-32-bytes!!}  # 优先读环境变量，没有则用默认值
    expire-hours: 24
```

```yaml
# application-prod.yml：只写与公共配置不同的部分
spring:
  datasource:
    url: jdbc:mysql://prod-mysql:3306/mini_mall?useSSL=true&serverTimezone=Asia/Shanghai
    username: mall
    password: ${DB_PASSWORD}   # 敏感信息绝不写进仓库
```

| 前端 | Spring Boot |
|---|---|
| `.env` | `application.yml` |
| `.env.production` | `application-prod.yml` |
| `vite --mode production` | `java -jar app.jar --spring.profiles.active=prod` |
| `import.meta.env.VITE_API_URL` | `@Value("${mall.order.timeout-minutes}")` / `@ConfigurationProperties` |
| 构建时注入，打进包里 | **运行时读取**，同一个 jar 部署到不同环境 |

最后一行是关键差异：前端的 env 在构建时被替换成常量；Java 的 jar **只构建一次**，环境差异在启动时注入。这是「一次构建，到处部署」的基础（第 12 章）。

#### @Value vs @ConfigurationProperties

```java
/**
 * 订单相关配置，绑定 application.yml 中 mall.order 前缀。
 *
 * @param timeoutMinutes 未支付订单超时取消时间（分钟），对应 mall.order.timeout-minutes
 * @param maxItems       单笔订单最多商品种类数，对应 mall.order.max-items
 */
@Validated
@ConfigurationProperties(prefix = "mall.order")
public record OrderProperties(
        @Min(1) int timeoutMinutes,
        @Min(1) @Max(100) int maxItems) {
}
```

```java
// 启动类上开启扫描：@ConfigurationPropertiesScan("com.example.mall")
// 使用：像普通 Bean 一样构造器注入
private final OrderProperties orderProperties;
```

| 对比 | `@Value("${x.y}")` | `@ConfigurationProperties` |
|---|---|---|
| 粒度 | 单个值 | 一组相关配置，绑定为对象 |
| 松散绑定（`max-items` ↔ `maxItems` ↔ `MALL_ORDER_MAXITEMS`） | 有限 | ✅ 完整支持 |
| 校验 | ❌ | ✅ 配 `@Validated`，启动时校验失败直接报错 |
| IDE 提示 | ❌ | ✅（加 `spring-boot-configuration-processor`） |
| 推荐 | 零星单值 | **业务配置首选** |

#### 配置优先级（高 → 低，常用部分）

```
1. 命令行参数                    --server.port=9090
2. Java 系统属性                 -Dserver.port=9090
3. 操作系统环境变量               SERVER_PORT=9090        ← K8s 中最常用
4. jar 包外的 application-{profile}.yml
5. jar 包外的 application.yml
6. jar 包内的 application-{profile}.yml
7. jar 包内的 application.yml
8. @PropertySource 指定的文件
9. 默认值
```

规律：**越靠近运行时、越具体（带 profile）的配置优先级越高**。线上排查「配置为什么不生效」，先看是不是被环境变量或启动参数覆盖了。另外，第 11 章的 Nacos 配置中心会作为另一个属性源加入这个链条。

### 3.4 Controller 开发

```ts
// Express
app.post('/api/orders', auth, async (req, res) => {
  const order = await orderService.create(req.user.id, req.body);
  res.json({ code: 0, message: 'success', data: order });
});
app.get('/api/orders/:orderNo', auth, async (req, res) => {
  res.json({ code: 0, data: await orderService.get(req.params.orderNo) });
});

// NestJS
@Controller('api/orders')
export class OrderController {
  constructor(private readonly orderBiz: OrderBizComponent) {}

  @Post()
  create(@Body() dto: CreateOrderDto) { return this.orderBiz.create(dto); }

  @Get(':orderNo')
  detail(@Param('orderNo') orderNo: string) { return this.orderBiz.detail(orderNo); }
}
```

```java
// Spring MVC：与 NestJS 几乎一一对应
@RestController                       // = @Controller + @ResponseBody：返回值直接序列化为 JSON
@RequestMapping("/api/orders")
@RequiredArgsConstructor
public class OrderController {

    private final OrderBizComponent orderBizComponent;

    /**
     * 创建订单。
     *
     * @param dto 下单入参（JSON 请求体）
     * @return 订单详情
     */
    @PostMapping
    public Result<OrderVO> create(@RequestBody @Valid CreateOrderDTO dto) {
        return Result.success(orderBizComponent.createOrder(UserContext.requireUserId(), dto));
    }

    /**
     * 查询订单详情。
     *
     * @param orderNo 订单号（路径参数）
     * @return 订单详情
     */
    @GetMapping("/{orderNo}")
    public Result<OrderVO> detail(@PathVariable String orderNo) {
        return Result.success(orderBizComponent.getOrderDetail(UserContext.requireUserId(), orderNo));
    }
}
```

参数注解速查：

| 注解 | 取值位置 | 示例 | NestJS 对应 |
|---|---|---|---|
| `@PathVariable` | 路径 | `/orders/{orderNo}` | `@Param()` |
| `@RequestParam` | Query 或 form 表单 | `?page=1&size=20` | `@Query()` |
| `@RequestBody` | JSON 请求体 | `{"items":[...]}` | `@Body()` |
| `@RequestHeader` | 请求头 | `Authorization` | `@Headers()` |
| `@CookieValue` | Cookie | — | `@Req()` 取 |
| 无注解的对象参数 | Query 参数绑定到对象字段 | `OrderQueryDTO query` | `@Query() dto` |

| Mapping | HTTP 方法 | 语义 |
|---|---|---|
| `@GetMapping` | GET | 查询 |
| `@PostMapping` | POST | 创建 |
| `@PutMapping` | PUT | 全量更新 |
| `@PatchMapping` | PATCH | 部分更新 |
| `@DeleteMapping` | DELETE | 删除 |

> 编译参数：`@PathVariable String orderNo` 能省略名称，依赖编译时加 `-parameters`（Spring Boot 的 parent POM 已默认开启）。Spring 6.1 起不再从字节码调试信息推断参数名，没开 `-parameters` 会直接报错——升级老项目时常见。

### 3.5 参数校验：Bean Validation

```ts
// zod
const OrderItem = z.object({
  productId: z.number().int().positive(),
  quantity: z.number().int().min(1).max(99),
});
const CreateOrder = z.object({ items: z.array(OrderItem).min(1).max(20) });
```

```java
/**
 * 创建订单入参。
 */
@Data
public class CreateOrderDTO {

    /** 下单商品列表，1~20 项；@Valid 触发对列表内每个元素的级联校验 */
    @NotEmpty(message = "商品不能为空")
    @Size(max = 20, message = "单次最多购买 20 种商品")
    private List<@Valid OrderItemDTO> items;

    /**
     * 按商品聚合购买数量（同一商品多行时求和），供 Redis 预扣库存（09 章）、按 ID 升序扣库存（08 章）复用。
     *
     * @return key 为商品 ID，value 为该商品的总购买数量
     */
    public Map<Long, Integer> quantityByProductId() {
        return items.stream().collect(Collectors.toMap(
                OrderItemDTO::getProductId, OrderItemDTO::getQuantity, Integer::sum));
    }
}
```

```java
/**
 * 下单商品明细入参。
 */
@Data
public class OrderItemDTO {

    /** 商品 ID */
    @NotNull(message = "商品 ID 不能为空")
    @Positive(message = "商品 ID 非法")
    private Long productId;

    /** 购买数量，1~99 */
    @NotNull(message = "购买数量不能为空")
    @Min(value = 1, message = "购买数量至少为 1")
    @Max(value = 99, message = "单个商品最多购买 99 件")
    private Integer quantity;
}
```

常用注解：

| 注解 | 作用 | zod 对应 |
|---|---|---|
| `@NotNull` | 不为 null | 非 `.optional()` |
| `@NotBlank` | 字符串非 null 且去空格后非空 | `.string().trim().min(1)` |
| `@NotEmpty` | 集合/字符串非 null 且非空 | `.array().min(1)` |
| `@Size(min, max)` | 长度/大小范围 | `.min().max()` |
| `@Min` / `@Max` / `@Positive` | 数值范围 | `.min()` / `.positive()` |
| `@Pattern(regexp)` | 正则 | `.regex()` |
| `@Email` | 邮箱格式 | `.email()` |
| `@Valid` | 级联校验嵌套对象/集合元素 | 嵌套 schema 自动校验 |

**触发方式**：

| 位置 | 写法 | 失败时抛出 |
|---|---|---|
| `@RequestBody` 对象 | `@RequestBody @Valid CreateOrderDTO dto` | `MethodArgumentNotValidException` |
| Query 绑定对象 | `@Valid OrderQueryDTO query` | `BindException`（前者的父类） |
| 单个 `@RequestParam` / `@PathVariable` | `@PathVariable @Size(max = 32) String orderNo` | Spring 6.1+：`HandlerMethodValidationException`；旧版需类上加 `@Validated`，抛 `ConstraintViolationException` |

#### 分组校验

同一个 DTO 在「新增」和「修改」时规则不同：

```java
/**
 * 商品保存入参：新增时 id 必须为空，修改时 id 必填。
 */
@Data
public class ProductSaveDTO {

    /** 新增分组标记接口 */
    public interface Create {}
    /** 修改分组标记接口 */
    public interface Update {}

    /** 商品 ID */
    @Null(groups = Create.class, message = "新增时不能指定 ID")
    @NotNull(groups = Update.class, message = "修改时 ID 必填")
    private Long id;

    /** 商品名称，新增与修改都必填 */
    @NotBlank(groups = {Create.class, Update.class})
    private String name;
}
```

```java
@PostMapping
public Result<Long> create(@RequestBody @Validated(ProductSaveDTO.Create.class) ProductSaveDTO dto) { ... }

@PutMapping
public Result<Void> update(@RequestBody @Validated(ProductSaveDTO.Update.class) ProductSaveDTO dto) { ... }
```

> `@Valid` 是 Jakarta 标准注解，不支持分组；`@Validated` 是 Spring 的，支持分组。嵌套级联只能用 `@Valid`。

#### 自定义校验注解

校验「状态码必须是某个枚举里的合法 code」：

```java
/**
 * 校验 Integer 值是否为指定枚举中的合法 code。
 */
@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = InEnumValidator.class)
public @interface InEnum {

    /** @return 实现了 CodeEnum 的枚举类型 */
    Class<? extends CodeEnum> value();

    /** @return 校验失败提示 */
    String message() default "取值不在枚举范围内";

    /** @return 分组 */
    Class<?>[] groups() default {};

    /** @return 负载（规范要求，一般不用） */
    Class<? extends Payload>[] payload() default {};
}
```

```java
/**
 * 带 code 的枚举统一接口，供 @InEnum 读取合法值。
 */
public interface CodeEnum {

    /**
     * @return 枚举对应的存储值
     */
    int getCode();
}
```

```java
/**
 * @InEnum 的校验器实现。
 */
public class InEnumValidator implements ConstraintValidator<InEnum, Integer> {

    /** 合法 code 集合 */
    private Set<Integer> validCodes;

    /**
     * 初始化：读取枚举所有 code。
     *
     * @param annotation 注解实例
     */
    @Override
    public void initialize(InEnum annotation) {
        validCodes = Arrays.stream(annotation.value().getEnumConstants())
                .map(CodeEnum::getCode)
                .collect(Collectors.toSet());
    }

    /**
     * 校验单个值。null 视为合法，是否必填交给 @NotNull 负责（单一职责）。
     *
     * @param value   待校验值
     * @param context 校验上下文
     * @return 是否合法
     */
    @Override
    public boolean isValid(Integer value, ConstraintValidatorContext context) {
        return value == null || validCodes.contains(value);
    }
}
```

```java
// 使用：让 OrderStatusEnum implements CodeEnum 后
@InEnum(OrderStatusEnum.class)
private Integer status;
```

### 3.6 统一返回 Result<T> 与错误码设计

```ts
// 前端 axios 拦截器里你写过的逻辑
http.interceptors.response.use((res) => {
  const { code, message, data } = res.data;
  if (code !== 0) { toast.error(message); return Promise.reject(res.data); }
  return data;
});
```

现在你是定义这个契约的一方：

```java
/**
 * 统一返回体。
 *
 * @param <T> 业务数据类型
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class Result<T> {

    /** 业务码：0 成功，非 0 失败，取值见 ErrorCode */
    private int code;
    /** 提示信息，失败时可直接展示给用户 */
    private String message;
    /** 业务数据，失败时为 null */
    private T data;

    /**
     * 构造成功结果。
     *
     * @param data 业务数据
     * @param <T>  数据类型
     * @return code=0 的结果
     */
    public static <T> Result<T> success(T data) {
        return new Result<>(ErrorCode.SUCCESS.getCode(), ErrorCode.SUCCESS.getMessage(), data);
    }

    /**
     * 构造失败结果（使用错误码默认文案）。
     *
     * @param errorCode 错误码
     * @param <T>       数据类型
     * @return 失败结果
     */
    public static <T> Result<T> fail(ErrorCode errorCode) {
        return new Result<>(errorCode.getCode(), errorCode.getMessage(), null);
    }

    /**
     * 构造失败结果（自定义文案）。
     *
     * @param errorCode 错误码
     * @param message   覆盖默认文案
     * @param <T>       数据类型
     * @return 失败结果
     */
    public static <T> Result<T> fail(ErrorCode errorCode, String message) {
        return new Result<>(errorCode.getCode(), message, null);
    }
}
```

```java
/**
 * 错误码枚举。编码规则：5 位数字，首位表示类别。
 * 0：成功；1xxxx：通用/参数/鉴权；2xxxx：商品域；3xxxx：订单域；9xxxx：系统错误。
 */
@Getter
@AllArgsConstructor
public enum ErrorCode {
    /** 成功 */
    SUCCESS(0, "成功"),
    /** 参数校验失败 */
    PARAM_ERROR(10001, "参数错误"),
    /** 未登录或登录已过期 */
    UNAUTHORIZED(10002, "请先登录"),
    /** 无权访问该资源 */
    FORBIDDEN(10003, "无权访问"),
    /** 资源不存在（通用） */
    NOT_FOUND(10004, "资源不存在"),
    /** 重复提交（防重锁未抢到，见 09 章） */
    REPEAT_SUBMIT(10005, "请勿重复提交"),
    /** 请求过于频繁（限流，见 09/11 章） */
    TOO_MANY_REQUESTS(10006, "请求过于频繁，请稍后再试"),
    /** 商品不存在 */
    PRODUCT_NOT_FOUND(20001, "商品不存在"),
    /** 商品库存不足 */
    STOCK_NOT_ENOUGH(20002, "库存不足"),
    /** 订单不存在 */
    ORDER_NOT_FOUND(30001, "订单不存在"),
    /** 订单状态不允许当前操作（状态机校验，见 01/10 章） */
    ORDER_STATUS_ILLEGAL(30002, "订单状态不允许当前操作"),
    /** 下单失败（微服务下单补偿后，见 11 章） */
    ORDER_CREATE_FAILED(30003, "下单失败，请重试"),
    /** 远程服务调用失败（OpenFeign，见 11 章） */
    REMOTE_CALL_FAILED(90001, "依赖服务暂不可用"),
    /** 系统繁忙（线程池满/查询超时，见 04 章） */
    SYSTEM_BUSY(90002, "系统繁忙，请稍后重试"),
    /** 未知系统错误 */
    SYSTEM_ERROR(99999, "系统繁忙，请稍后重试");

    /** 业务码 */
    private final int code;
    /** 默认提示文案 */
    private final String message;
}
```

**错误码设计要点**：

| 原则 | 说明 |
|---|---|
| 业务码与 HTTP 状态码分离 | 主流做法：业务错误 HTTP 返回 200 + 非 0 code；鉴权失败可额外返回 401 方便网关/前端统一处理。**团队统一即可**，关键是一致 |
| 按域分段 | 一眼看出是哪个模块的问题，微服务化后可按服务分配号段 |
| 文案面向用户 | `message` 可直接 toast；技术细节写日志，**绝不把异常堆栈、SQL 返回给前端**（安全问题） |
| 只增不改 | 前端、App 可能按 code 写了分支，已发布的 code 含义不能变 |

### 3.7 全局异常处理 @RestControllerAdvice

```java
/**
 * 全局异常处理器：把各类异常统一转换为 Result，避免异常堆栈直接暴露给前端。
 */
@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    /**
     * 业务异常：可预期，打 WARN，返回业务错误码。
     *
     * @param e 业务异常
     * @return 失败结果
     */
    @ExceptionHandler(BizException.class)
    public Result<Void> handleBiz(BizException e) {
        log.warn("业务异常 code={} msg={}", e.getErrorCode().getCode(), e.getMessage());
        return Result.fail(e.getErrorCode(), e.getMessage());
    }

    /**
     * 请求体 / Query 对象校验失败：取第一条错误信息返回。
     *
     * @param e 绑定异常（MethodArgumentNotValidException 是其子类）
     * @return 参数错误结果
     */
    @ExceptionHandler(BindException.class)
    public Result<Void> handleBind(BindException e) {
        String msg = e.getBindingResult().getFieldErrors().stream()
                .findFirst()
                .map(err -> err.getField() + " " + err.getDefaultMessage())
                .orElse(ErrorCode.PARAM_ERROR.getMessage());
        return Result.fail(ErrorCode.PARAM_ERROR, msg);
    }

    /**
     * 方法参数级校验失败（Spring 6.1+，如 @PathVariable 上的约束）。
     *
     * @param e 方法校验异常
     * @return 参数错误结果
     */
    @ExceptionHandler(HandlerMethodValidationException.class)
    public Result<Void> handleMethodValidation(HandlerMethodValidationException e) {
        String msg = e.getAllErrors().stream()
                .findFirst()
                .map(MessageSourceResolvable::getDefaultMessage)
                .orElse(ErrorCode.PARAM_ERROR.getMessage());
        return Result.fail(ErrorCode.PARAM_ERROR, msg);
    }

    /**
     * JSON 格式错误、类型不匹配（如 quantity 传了 "abc"）。
     *
     * @param e 消息不可读异常
     * @return 参数错误结果
     */
    @ExceptionHandler(HttpMessageNotReadableException.class)
    public Result<Void> handleNotReadable(HttpMessageNotReadableException e) {
        log.warn("请求体解析失败: {}", e.getMessage());
        return Result.fail(ErrorCode.PARAM_ERROR, "请求体格式错误");
    }

    /**
     * 兜底：未知异常打 ERROR 并带堆栈，返回通用文案，不暴露细节。
     *
     * @param e 未知异常
     * @return 系统错误结果
     */
    @ExceptionHandler(Exception.class)
    public Result<Void> handleUnknown(Exception e) {
        log.error("系统异常", e);
        return Result.fail(ErrorCode.SYSTEM_ERROR);
    }
}
```

匹配规则：**按异常类型就近匹配**（最具体的处理器优先），与声明顺序无关；都匹配不上才落到 `Exception`。

> 注意：**Filter 中抛出的异常不会进入 `@RestControllerAdvice`**——它在 DispatcherServlet 之外。Filter 里需要自己写响应，或交给 Boot 的 `/error` 端点（`BasicErrorController`）。

### 3.8 Filter vs Interceptor vs AOP

```ts
// Koa 洋葱模型
app.use(async (ctx, next) => {
  const start = Date.now();
  await next();                      // 进入内层
  console.log(Date.now() - start);   // 回到外层
});
```

```
请求 ──▶ ┌ Filter 1 (TraceIdFilter) ──────────────────────────────────────────┐
        │ ┌ Filter 2 (CorsFilter) ────────────────────────────────────────┐  │
        │ │ ┌ DispatcherServlet ────────────────────────────────────────┐ │  │
        │ │ │  Interceptor.preHandle（LoginInterceptor）                │ │  │
        │ │ │   ┌ 参数解析 & 校验 ───────────────────────────────────┐ │ │  │
        │ │ │   │ ┌ AOP 代理（@LogCost、@Transactional）──────────┐ │ │ │  │
        │ │ │   │ │          Controller / Biz 方法                │ │ │ │  │
        │ │ │   │ └───────────────────────────────────────────────┘ │ │ │  │
        │ │ │   └ 返回值处理（此时 JSON 已写入响应）──────────────┘ │ │  │
        │ │ │  Interceptor.postHandle（@ResponseBody 场景下已改不了响应体）│ │
        │ │ │  Interceptor.afterCompletion（无论成败都执行，适合清理）  │ │  │
        │ │ └───────────────────────────────────────────────────────────┘ │  │
        │ └───────────────────────────────────────────────────────────────┘  │
        └────────────────────────────────────────────────────────────────────┘ ──▶ 响应
```

| 对比 | Filter | Interceptor | AOP |
|---|---|---|---|
| 规范归属 | Servlet 规范（Jakarta） | Spring MVC | Spring |
| 作用范围 | 所有请求（包括静态资源、`/error`） | 进入 DispatcherServlet 且匹配到 Handler 的请求 | 任意 Spring Bean 的方法 |
| 能拿到什么 | 原始 `ServletRequest/Response`，可包装替换 | Request + **Handler（知道调哪个 Controller 方法、有什么注解）** | 方法参数、返回值、注解 |
| 能否修改请求体 | ✅（包装 Request） | ❌ | ✅（改参数） |
| 异常进入全局处理器 | ❌ | ✅ | ✅ |
| 典型用途 | 编码、CORS、TraceId、请求体缓存、XSS 过滤 | 登录鉴权、权限、接口幂等 Token | 日志、事务、缓存、分布式锁 |

**选型口诀**：与 HTTP 协议相关、与业务无关 → Filter；需要知道「调的是哪个接口」→ Interceptor；与 HTTP 无关、针对业务方法 → AOP。

### 3.9 跨域 CORS：换个角度看

前端视角：「浏览器报了 CORS 错误，找后端加个头」。服务端视角要理解的是：

```
浏览器（https://mall.example.com）                         服务端（https://api.example.com）
   │ 1. 非简单请求（如 Content-Type: application/json，或带 Authorization 头）
   │──── OPTIONS /api/orders ─────────────────────────────────▶│ 预检请求
   │     Origin: https://mall.example.com                      │ ★ 这个请求不带 Token！
   │     Access-Control-Request-Method: POST                   │
   │     Access-Control-Request-Headers: authorization,content-type
   │◀─── 200 ─────────────────────────────────────────────────│
   │     Access-Control-Allow-Origin: https://mall.example.com │
   │     Access-Control-Allow-Headers: authorization,content-type
   │     Access-Control-Max-Age: 3600（缓存预检结果）            │
   │ 2. 真正的请求                                               │
   │──── POST /api/orders + Authorization ────────────────────▶│
```

**服务端视角的三个关键认知**：

1. CORS 是**浏览器**的安全策略，服务端从来不「拦」跨域请求——curl、Postman 直接调都没事。服务端做的只是**告诉浏览器「我允许」**。
2. **预检 OPTIONS 不带 Token**。如果登录拦截器在 CORS 处理之前执行，预检被判为未登录返回 401，浏览器就报 CORS 错误——这是前后端联调最经典的「CORS 报错，其实是鉴权问题」。
3. `allowCredentials(true)` 时 `Access-Control-Allow-Origin` 不能是 `*`，要用 `allowedOriginPatterns`。

推荐用 `CorsFilter`（Filter 层，先于所有拦截器执行，预检请求在这里直接返回）：

```java
/**
 * 跨域配置：在 Filter 层处理，保证预检请求不会被登录拦截器拦截。
 */
@Configuration
public class CorsConfig {

    /**
     * 注册 CORS 过滤器，并设为最高优先级。
     *
     * @return 过滤器注册 Bean
     */
    @Bean
    public FilterRegistrationBean<CorsFilter> corsFilter() {
        CorsConfiguration config = new CorsConfiguration();
        // 允许的前端域名，生产环境不要用 *
        config.setAllowedOriginPatterns(List.of("https://*.example.com", "http://localhost:[*]"));
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
        config.setAllowedHeaders(List.of("*"));
        config.setAllowCredentials(true);
        config.setMaxAge(3600L);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        FilterRegistrationBean<CorsFilter> bean = new FilterRegistrationBean<>(new CorsFilter(source));
        bean.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return bean;
    }
}
```

> 其他方式：`@CrossOrigin`（单个 Controller，散落各处不推荐）、`WebMvcConfigurer#addCorsMappings`（在 MVC 层处理，Spring 会对预检请求跳过普通拦截器，通常也可行）。生产环境更常见的是**在 Nginx / 网关统一处理 CORS**，业务服务不管——此时服务端不要重复加头，否则浏览器会因出现两个 `Access-Control-Allow-Origin` 而报错。

### 3.10 登录鉴权：JWT + 拦截器 + ThreadLocal

```
登录：POST /api/auth/login ──▶ 校验账号密码 ──▶ 签发 JWT（含 userId，24h 过期）──▶ 前端存储
请求：Authorization: Bearer <jwt>
       │
       ▼
LoginInterceptor.preHandle
   ├─ 方法/类标注 @NoLogin？ ──是──▶ 放行
   ├─ 无 Token / 验签失败 / 过期 ──▶ 抛 BizException(UNAUTHORIZED) → 全局异常 → {code:10002}
   └─ 成功 ──▶ UserContext.set(userId) ──▶ 放行
       │
       ▼
Controller / Biz：UserContext.requireUserId()   ← 任意深度都能取，无需层层传参
       │
       ▼
LoginInterceptor.afterCompletion ──▶ UserContext.clear()   ★ 必须清理
```

为什么用 ThreadLocal？在 Tomcat 的「一个请求一个线程」模型下，ThreadLocal 就是「请求级的全局变量」——类似前端的 React Context：不用 props drilling 就能在深层组件里拿到当前用户。

**为什么必须 clear**：Tomcat 线程是**池化复用**的。不清理，下一个落到这个线程的请求（可能是未登录接口）会读到上一个用户的 userId——严重的越权漏洞。代码见第 5 节。

| 方案 | 适合 | 特点 |
|---|---|---|
| JWT + 拦截器（本章） | 中小项目、学习原理 | 简单透明，代码量少 |
| Sa-Token | 国内中小项目 | 注解式鉴权、踢人下线、多端登录，开箱即用 |
| Spring Security | 企业级、OAuth2/SSO | 功能最全，基于 Filter 链，学习曲线陡 |

JWT 的服务端视角：它是**无状态**的，服务端不存 session，验签即可，天然适合多实例部署；代价是**无法主动失效**（改密码、踢下线），实践中常结合 Redis 黑名单或「短 Token + 刷新 Token」（第 09 章）。

### 3.11 文件上传与下载

```java
/**
 * 文件上传下载示例接口。
 */
@RestController
@RequestMapping("/api/files")
public class FileController {

    /** 本地存储目录（生产应使用对象存储 OSS/S3） */
    private static final Path STORAGE_DIR = Path.of("/data/mini-mall/upload");

    /**
     * 上传商品图片。
     *
     * @param file multipart 表单中的文件字段 file
     * @return 存储后的文件名
     * @throws IOException 写盘失败
     */
    @PostMapping("/upload")
    public Result<String> upload(@RequestParam("file") MultipartFile file) throws IOException {
        // 1. 校验类型：不信任前端传来的文件名后缀，至少校验 Content-Type
        if (!List.of("image/png", "image/jpeg").contains(file.getContentType())) {
            throw new BizException(ErrorCode.PARAM_ERROR, "仅支持 png/jpg");
        }
        // 2. 服务端生成文件名，防止路径穿越（如 ../../etc/passwd）
        String fileName = UUID.randomUUID() + (MediaType.IMAGE_PNG_VALUE.equals(file.getContentType()) ? ".png" : ".jpg");
        // 3. 流式写盘，不把整个文件读进内存
        file.transferTo(STORAGE_DIR.resolve(fileName));
        return Result.success(fileName);
    }

    /**
     * 下载文件。
     *
     * @param fileName 文件名（只允许 UUID 格式，防路径穿越）
     * @return 文件流响应
     */
    @GetMapping("/{fileName:[0-9a-f\\-]{36}\\.(?:png|jpg)}")
    public ResponseEntity<Resource> download(@PathVariable String fileName) {
        Resource resource = new FileSystemResource(STORAGE_DIR.resolve(fileName));
        if (!resource.exists()) {
            throw new BizException(ErrorCode.NOT_FOUND);
        }
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment().filename(fileName).build().toString())
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .body(resource);
    }
}
```

```yaml
spring:
  servlet:
    multipart:
      max-file-size: 5MB       # 单文件上限，超限抛 MaxUploadSizeExceededException
      max-request-size: 10MB   # 整个请求上限
```

> 大文件导出（如订单 Excel）用 `StreamingResponseBody` 或 EasyExcel 边查边写，**不要一次性查出百万行再写**——这正是第 03 章复现的 OOM 场景。

### 3.12 接口文档：SpringDoc / OpenAPI

| 对比 | Springfox（Swagger 2） | SpringDoc |
|---|---|---|
| 规范 | Swagger 2.0 | OpenAPI 3 |
| Spring Boot 3 | ❌ 已停更，不兼容 | ✅ `springdoc-openapi-starter-webmvc-ui` 2.x |
| 注解 | `@Api` `@ApiOperation` `@ApiModelProperty` | `@Tag` `@Operation` `@Schema` |

```java
@Tag(name = "订单")
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @Operation(summary = "创建订单")
    @PostMapping
    public Result<OrderVO> create(@RequestBody @Valid CreateOrderDTO dto) { ... }
}

@Data
public class OrderItemDTO {
    @Schema(description = "商品 ID", example = "1001")
    @NotNull
    private Long productId;
}
```

启动后访问 `/swagger-ui.html` 看页面，`/v3/api-docs` 拿 JSON。**前端的价值点**：用 `openapi-typescript` / `orval` 从 `/v3/api-docs` 直接生成 TS 类型和请求函数，前后端类型一致。生产环境用 `springdoc.api-docs.enabled=false` 关闭。

### 3.13 DTO / VO / PO 分层与 MapStruct

| 对象 | 全称 | 所在层 | 职责 | TS 类比 |
|---|---|---|---|---|
| DTO | Data Transfer Object | 接口层入参 | 接收请求，带校验注解 | 请求参数类型 / 表单类型 |
| VO | View Object | 接口层出参 | 返回给前端，字段按页面需要裁剪、格式化 | 接口响应类型 |
| PO | Persistent Object | DAO 层 | 与表一一对应（MyBatis-Plus Entity） | Prisma Model |
| BO | Business Object | 编排/功能单元内部（可选） | 跨多个 PO 的业务聚合 | — |

**为什么不能一个对象走到底**：

| 混用后果 | 例子 |
|---|---|
| 泄露敏感字段 | `UserPO` 直接返回，带出了密码哈希、手机号 |
| 越权写入 | 用 PO 接收入参，攻击者传 `"status": 1` 直接把订单改成已支付（批量赋值漏洞） |
| 表结构绑架接口 | 表加个字段，接口契约就变了；前端 / App 跟着出问题 |

转换用 **MapStruct**：编译期生成普通 getter/setter 代码，零反射、性能等同手写，类型不匹配**编译期报错**。

| 方式 | 原理 | 性能 | 类型安全 |
|---|---|---|---|
| 手写 get/set | — | 最快 | ✅ 但啰嗦 |
| `BeanUtils.copyProperties` | 运行时反射 | 慢 | ❌ 字段名错了静默忽略 |
| **MapStruct** | 编译期生成代码 | 等同手写 | ✅ 未映射字段编译期警告 |

> Lombok 与 MapStruct 同时使用时，`annotationProcessorPaths` 中需依次配置 `lombok`、`lombok-mapstruct-binding`、`mapstruct-processor`，否则 MapStruct 看不到 Lombok 生成的 getter（第 05 章 Maven 配置）。

### 3.14 五层架构详解

| 层级 | 名称 | 职责 | mini-mall 载体 | 变化频率 |
|---|---|---|---|---|
| ① | 接口层 | 接收触发、解析入参、基础校验、调用下层并翻译返回结果，**不写业务逻辑** | `OrderController`、XXL-Job 任务、MQ 消费者 | 中 |
| ② | 编排层 | 单个接口的业务流程编排：按顺序、分支、失败策略组合能力，汇总结果 | `OrderBizComponent` | **高** |
| ③ | 功能单元层 | 聚合操作多张表的完整功能，对外提供稳定契约，**事务边界在这里** | `OrderCreateUnit` | 低 |
| ④ | 能力单元层 | 单一能力：一张表的读写、一个三方接口的调用 | `OrderDao`、`ProductDao`、`PayClient` | 很低 |
| ⑤ | 最小能力单元层 | 数据转换、校验、工具函数 | `OrderConverter`、`OrderNoUtil` | 极低 |

```
            越上层：越贴近业务、越常变化
  ① 接口层        ┃  OrderController / OrderTimeoutJob / OrderMqConsumer
  ② 编排层        ┃  OrderBizComponent
  ③ 功能单元层    ┃  OrderCreateUnit
  ④ 能力单元层    ┃  OrderDao  ProductDao  PayClient
  ⑤ 工具层        ▼  OrderConverter  OrderNoUtil
            越底层：越稳定、越容易复用
```

**规则**：

1. **依赖自上而下单向**，下层不感知上层：DAO 不知道谁在调它，功能单元不 import 任何 DTO 之外的接口层对象（更不能用 `HttpServletRequest`）。
2. **同层不互调**（编排层不调另一个编排层）：需要复用时，下沉为功能单元。
3. **业务变更优先只改编排层**。例如「下单前加风控校验」「下单后送积分」，都是在 `OrderBizComponent` 里加一步；`OrderCreateUnit` 一行不改。
4. **功能单元为多入口复用而设计**：`OrderCreateUnit.createOrder` 既被 HTTP 下单调用，也可以被「后台补单」「批量导单」的编排复用，入口不同、核心能力一致。

> **前端类比**：页面容器组件（② 编排）→ 自定义 hooks（③ 功能单元，如 `useCreateOrder`）→ `api/` 请求层（④）→ `utils/`（⑤）。你在前端已经在做这种分层了，只是后端多了「事务边界」这个硬约束。

与传统「Controller / Service / DAO 三层」的对比：三层里的 Service 往往既做编排又做数据聚合，一个 `OrderServiceImpl` 两三千行，事务注解到处都是。五层的本质是把 Service **按变化频率拆成编排层和功能单元层**。

---

## 4. 原理深挖

### 4.1 自动配置原理

```
@SpringBootApplication
 ├── @SpringBootConfiguration        ≈ @Configuration：启动类本身是配置类
 ├── @ComponentScan                  扫描启动类所在包及子包（所以启动类要放在根包 com.example.mall）
 └── @EnableAutoConfiguration
      ├── @AutoConfigurationPackage  记录根包，供 MyBatis-Plus 等扫描用
      └── @Import(AutoConfigurationImportSelector.class)
               │ 它是 DeferredImportSelector：等用户配置全部解析完再处理（为了让 @ConditionalOnMissingBean 判断准确）
               ▼
        读取所有 jar 中的
        META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
        （每行一个自动配置类全限定名，Boot 2.7 引入，Boot 3 起是唯一方式；之前是 spring.factories）
               │
               ▼
        约 150 个候选自动配置类 → 排除 exclude → 按 @Conditional 过滤 → 生效的注册为 BeanDefinition
```

以 `DataSourceAutoConfiguration` 为例（简化）：

```java
@AutoConfiguration(before = SqlInitializationAutoConfiguration.class)
@ConditionalOnClass({DataSource.class, EmbeddedDatabaseType.class})  // classpath 有 JDBC 才生效
@EnableConfigurationProperties(DataSourceProperties.class)           // 绑定 spring.datasource.*
public class DataSourceAutoConfiguration {
    // 内部再按 @ConditionalOnMissingBean(DataSource.class) 决定是否创建 HikariDataSource
}
```

`@Conditional` 系列：

| 注解 | 条件 | 典型用途 |
|---|---|---|
| `@ConditionalOnClass` | classpath 有某类 | 引了 starter 才生效 |
| `@ConditionalOnMissingClass` | classpath 没有某类 | — |
| `@ConditionalOnBean` | 容器有某 Bean | 依赖另一个组件 |
| `@ConditionalOnMissingBean` | 容器没有某 Bean | **用户自定义优先**的关键 |
| `@ConditionalOnProperty` | 配置项满足条件 | 功能开关 |
| `@ConditionalOnWebApplication` | 是 Web 应用 | Web 相关组件 |

**调试技巧**：启动参数加 `--debug`，日志会打印 `CONDITIONS EVALUATION REPORT`，列出每个自动配置为什么生效/不生效。「我的配置怎么没生效」「这个 Bean 哪来的」，先看这份报告。

### 4.2 手写一个简易 Starter：mall-trace-spring-boot-starter

需求：引入依赖即自动为每个请求生成 TraceId，放入日志 MDC 和响应头；可通过配置关闭。

```
mall-trace-spring-boot-starter/
├── pom.xml                         依赖 spring-boot-autoconfigure，web 依赖设为 provided/optional
└── src/main/
    ├── java/com/example/mall/trace/
    │   ├── TraceProperties.java
    │   ├── TraceIdFilter.java
    │   └── TraceAutoConfiguration.java
    └── resources/META-INF/spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

```java
/**
 * TraceId 配置，前缀 mall.trace。
 *
 * @param enabled    是否启用，默认 true
 * @param headerName 透传 TraceId 的请求/响应头名称，默认 X-Trace-Id
 */
@ConfigurationProperties(prefix = "mall.trace")
public record TraceProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("X-Trace-Id") String headerName) {
}
```

```java
/**
 * TraceId 过滤器：优先沿用上游（网关）传来的 TraceId，否则新生成；请求结束清理 MDC。
 */
public class TraceIdFilter extends OncePerRequestFilter {

    /** 日志 MDC 中的 key，logback pattern 中用 %X{traceId} 输出 */
    public static final String MDC_KEY = "traceId";

    private final String headerName;

    /**
     * @param headerName 透传 TraceId 的 Header 名
     */
    public TraceIdFilter(String headerName) {
        this.headerName = headerName;
    }

    /**
     * 为当前请求绑定 TraceId。
     *
     * @param request  请求
     * @param response 响应
     * @param chain    过滤器链
     * @throws ServletException Servlet 异常
     * @throws IOException      IO 异常
     */
    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String traceId = Optional.ofNullable(request.getHeader(headerName))
                .filter(s -> !s.isBlank())
                .orElseGet(() -> UUID.randomUUID().toString().replace("-", ""));
        MDC.put(MDC_KEY, traceId);
        response.setHeader(headerName, traceId);
        try {
            chain.doFilter(request, response);
        } finally {
            // 线程池复用，必须清理
            MDC.remove(MDC_KEY);
        }
    }
}
```

```java
/**
 * TraceId 自动配置：Servlet Web 应用 + 未关闭开关 + 用户未自定义时生效。
 */
@AutoConfiguration
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
@ConditionalOnProperty(prefix = "mall.trace", name = "enabled", havingValue = "true", matchIfMissing = true)
@EnableConfigurationProperties(TraceProperties.class)
public class TraceAutoConfiguration {

    /**
     * 注册 TraceId 过滤器，排在 CORS 之后、其他过滤器之前。
     *
     * @param props TraceId 配置
     * @return 过滤器注册 Bean
     */
    @Bean
    @ConditionalOnMissingBean(name = "traceIdFilter")
    public FilterRegistrationBean<TraceIdFilter> traceIdFilter(TraceProperties props) {
        FilterRegistrationBean<TraceIdFilter> bean = new FilterRegistrationBean<>(new TraceIdFilter(props.headerName()));
        bean.setOrder(Ordered.HIGHEST_PRECEDENCE + 1);
        bean.addUrlPatterns("/*");
        return bean;
    }
}
```

```
# META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
com.example.mall.trace.TraceAutoConfiguration
```

mini-mall 引入该依赖后，在 `logback-spring.xml` 的 pattern 里加 `[%X{traceId}]`，每行日志就带上了 TraceId（第 12 章链路追踪的基础）。

> 命名约定：官方 starter 叫 `spring-boot-starter-xxx`，第三方叫 `xxx-spring-boot-starter`。

### 4.3 启动流程概览

```
main() → SpringApplication.run(MiniMallApplication.class, args)
 │
 ├─ 1. 推断应用类型（classpath 有 DispatcherServlet → SERVLET）
 ├─ 2. 准备 Environment：加载命令行参数、环境变量、application*.yml，确定激活的 profile
 ├─ 3. 打印 Banner
 ├─ 4. 创建 ApplicationContext（Servlet 应用为 AnnotationConfigServletWebServerApplicationContext）
 ├─ 5. prepareContext：把启动类注册为 BeanDefinition
 ├─ 6. refresh() ← 第 06 章讲的容器刷新，关键步骤：
 │     ├─ invokeBeanFactoryPostProcessors
 │     │    └─ ConfigurationClassPostProcessor 解析 @ComponentScan、@Import
 │     │       → 触发自动配置导入 → 注册所有 BeanDefinition
 │     ├─ registerBeanPostProcessors
 │     ├─ onRefresh() → createWebServer()：创建内嵌 Tomcat（此时还不接收请求）
 │     ├─ finishBeanFactoryInitialization：实例化所有非懒加载单例（Controller、Biz、DAO……）
 │     └─ finishRefresh：启动 Tomcat 开始监听端口
 ├─ 7. 回调 ApplicationRunner / CommandLineRunner
 └─ 8. 发布 ApplicationReadyEvent → 应用就绪，K8s 就绪探针此后返回成功
```

启动慢排查：用第 06 章的 `SlowBeanInitDetector`，或 Boot 的 `ApplicationStartup`（`BufferingApplicationStartup` + Actuator `/actuator/startup`）找最慢的 Bean。

### 4.4 内嵌 Tomcat 与 Servlet 基础

**Servlet** 是 Java Web 的底层规范：一个接口，`service(request, response)` 处理请求。Spring MVC 整个框架对 Tomcat 来说**只是一个 Servlet**——`DispatcherServlet`。

```
                         Tomcat
┌──────────────────────────────────────────────────────────┐
│ Connector（NIO）                                          │
│   Acceptor 线程 ──接收连接──▶ Poller 线程（多路复用，监听可读）│
│                                    │ 有数据可读            │
│                                    ▼                      │
│                     Worker 线程池（默认 max 200）           │
│                     「一个请求占用一个线程直到响应完成」    │
│                                    │                      │
│ Container  ─▶ Filter 链 ─▶ DispatcherServlet.service()    │
└──────────────────────────────────────────────────────────┘
```

**与 Node 的根本差异**：Node 一个线程处理所有请求，遇到 IO 让出；Tomcat 每个请求独占一个工作线程，遇到 IO（查库、调 RPC）**线程阻塞等待**。所以：

- 并发能力 ≈ 线程数 / 单请求耗时。200 线程、每请求 100ms → 约 2000 QPS；接口变慢到 1s → 200 QPS，后续请求排队（`accept-count`），再满就拒绝连接。
- 「一个慢接口拖垮整个服务」：慢 SQL 把 200 个线程全占住，健康检查接口也进不来。
- Java 21 **虚拟线程**改变了这一点：`spring.threads.virtual.enabled=true`（Boot 3.2+），每个请求一个虚拟线程，IO 阻塞时自动让出载体线程——写法仍是同步阻塞，吞吐接近异步模型。此时瓶颈转移到数据库连接池（第 04 章）。

关键配置：

```yaml
server:
  tomcat:
    threads:
      max: 200            # 最大工作线程
      min-spare: 10       # 最小空闲线程
    accept-count: 100     # 线程满后的排队长度
    max-connections: 8192 # 最大连接数（NIO 可远大于线程数）
    connection-timeout: 5s
```

### 4.5 一次请求在 Spring MVC 中的流转

```
HTTP POST /api/orders  Authorization: Bearer xxx  {"items":[{"productId":1001,"quantity":2}]}
 │
 ▼ Tomcat Worker 线程
Filter 链（CorsFilter → TraceIdFilter → CharacterEncodingFilter ...）
 │
 ▼
DispatcherServlet.doDispatch()
 │
 ├─① getHandler(request)
 │     遍历 HandlerMapping，RequestMappingHandlerMapping 命中
 │     （启动时已把所有 @RequestMapping 扫描进 Map：key 为 RequestMappingInfo（路径+方法+…），value 为 HandlerMethod）
 │     返回 HandlerExecutionChain = HandlerMethod(OrderController#create) + 匹配的 Interceptor 列表
 │     └─ 找不到 → 404
 │
 ├─② getHandlerAdapter(handler) → RequestMappingHandlerAdapter（适配器模式：统一不同类型 Handler 的调用方式）
 │
 ├─③ mappedHandler.applyPreHandle()  → LoginInterceptor.preHandle()
 │     └─ 返回 false 或抛异常 → 中断
 │
 ├─④ ha.handle() → invokeHandlerMethod()
 │     ├─ 参数解析：对每个参数找 HandlerMethodArgumentResolver
 │     │    @RequestBody → RequestResponseBodyMethodProcessor
 │     │       └─ 按 Content-Type 选 HttpMessageConverter
 │     │          MappingJackson2HttpMessageConverter：JSON → CreateOrderDTO
 │     │       └─ 有 @Valid → 执行 Bean Validation，失败抛 MethodArgumentNotValidException
 │     │    @PathVariable → PathVariableMethodArgumentResolver
 │     ├─ 反射调用 OrderController.create(dto)   ← 若 Bean 被 AOP 代理，这里先进代理
 │     └─ 返回值处理：HandlerMethodReturnValueHandler
 │          @ResponseBody → RequestResponseBodyMethodProcessor
 │             └─ 按 Accept 选 HttpMessageConverter：Result<OrderVO> → JSON，写入响应流
 │
 ├─⑤ applyPostHandle()   → Interceptor.postHandle()（响应体已写出，只能做旁路逻辑）
 │
 ├─⑥ processDispatchResult()
 │     └─ ④ 中若抛异常 → HandlerExceptionResolver
 │          ExceptionHandlerExceptionResolver → 找到 @RestControllerAdvice 中匹配的 @ExceptionHandler
 │          → 返回 Result.fail(...) → 同样经 HttpMessageConverter 写成 JSON
 │
 └─⑦ triggerAfterCompletion() → Interceptor.afterCompletion()（无论成败都执行：清理 ThreadLocal）
 │
 ▼
Filter 链反向返回 → Tomcat 写回响应
```

几个由此推出的结论：

| 现象 | 原因 |
|---|---|
| 返回 `Result<OrderVO>` 自动变 JSON | 返回值处理器 + Jackson 转换器 |
| `LocalDateTime` 返回成数组 / 格式不对 | Jackson 配置问题：`spring.jackson.date-format` 或 `@JsonFormat` |
| 前端传 `Content-Type: text/plain` 报 415 | 没有能把 text/plain 转成 DTO 的转换器 |
| `postHandle` 里改响应体无效 | `@ResponseBody` 在 ④ 中已写出 |
| 拦截器抛的异常也能被全局处理 | ③ 在 DispatcherServlet 内部，异常进 ⑥ |

---

## 5. mini-mall 实战：创建订单与查询订单

### 5.1 接口设计

| 接口 | 变更类型 | 方法 & 路径 | 鉴权 |
|---|---|---|---|
| 创建订单 | 新增 | `POST /api/orders` | 需登录 |
| 查询订单详情 | 新增 | `GET /api/orders/{orderNo}` | 需登录，且只能查自己的订单 |

**创建订单 入参 `CreateOrderDTO`**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| items | `List<OrderItemDTO>` | 是 | 1~20 项 |
| items[].productId | Long | 是 | 商品 ID，正数 |
| items[].quantity | Integer | 是 | 购买数量 1~99 |

**出参 `Result<OrderVO>`**（两个接口共用）

| 字段 | 类型 | 说明 |
|---|---|---|
| orderNo | String | 订单号 |
| totalAmount | BigDecimal | 订单总额（元，2 位小数） |
| status | Integer | 状态码，取值见 `OrderStatusEnum`：0 待支付 / 1 已支付 / 2 已取消 / 3 已发货 / 4 已完成 |
| statusDesc | String | 状态文案 |
| createTime | LocalDateTime | 下单时间，格式 `yyyy-MM-dd HH:mm:ss` |
| items | `List<OrderItemVO>` | 明细：productId、productName、price、quantity |

```json
{
  "code": 0,
  "message": "成功",
  "data": {
    "orderNo": "20261126143012123456",
    "totalAmount": 199.80,
    "status": 0,
    "statusDesc": "待支付",
    "createTime": "2026-11-26 14:30:12",
    "items": [{ "productId": 1001, "productName": "机械键盘", "price": 99.90, "quantity": 2 }]
  }
}
```

### 5.2 调用链路流程图

**创建订单**

```
POST /api/orders  Header: Authorization: Bearer <jwt>  Body: CreateOrderDTO
 │
 ▼ ① 接口层
CorsFilter / TraceIdFilter（生成 traceId → MDC）
 │
LoginInterceptor.preHandle
 ├─ Token 缺失/无效/过期 ──▶ BizException(UNAUTHORIZED) ──▶ GlobalExceptionHandler ──▶ {code:10002}
 └─ 有效 ──▶ UserContext.set(userId)
 │
OrderController.create(@Valid CreateOrderDTO)
 ├─ 校验失败 ──▶ MethodArgumentNotValidException ──▶ {code:10001, message:"items[0].quantity 购买数量至少为 1"}
 └─ userId = UserContext.requireUserId()
 │
 ▼ ② 编排层（@LogCost 切面记录耗时）
OrderBizComponent.createOrder(userId, dto)
 │
 ▼ ③ 功能单元（@Transactional 开启事务，绑定连接到 ThreadLocal）
OrderCreateUnit.createOrder(userId, items)
 ├─ mergeQuantity：items → Map<productId, quantity>（TreeMap 升序）
 ├─ ProductDao.listByIds ──▶ SELECT t_product
 │    └─ 有 ID 不存在 ──▶ BizException(PRODUCT_NOT_FOUND) ──▶ 回滚 ──▶ {code:20001}
 ├─ ProductDao.deductStock（逐个）──▶ UPDATE t_product ... WHERE stock >= ?
 │    └─ 影响行数 0 ──▶ BizException(STOCK_NOT_ENOUGH) ──▶ 回滚（已扣的库存一并恢复）──▶ {code:20002}
 ├─ OrderConverter.toItemPO（商品快照）+ 计算总额 + OrderNoUtil.generate()
 ├─ OrderDao.insertOrder ──▶ INSERT t_order（回填 id）
 ├─ OrderDao.batchInsertItems ──▶ INSERT t_order_item
 └─ publishEvent(OrderCreatedEvent)
 │ 提交事务 ──▶ AFTER_COMMIT 监听器发送通知
 │
 ▼ 回到 ② 编排层
OrderDao.listItemsByOrderId ──▶ OrderConverter.toVO(OrderPO, List<OrderItemPO>) ──▶ OrderVO
 │
 ▼ 回到 ① 接口层
Result.success(OrderVO) ──▶ Jackson 序列化 ──▶ LoginInterceptor.afterCompletion: UserContext.clear()
```

**查询订单详情**

```
GET /api/orders/{orderNo}
 │
LoginInterceptor ──▶ UserContext.set(userId)
 │
OrderController.detail(orderNo)
 │
OrderBizComponent.getOrderDetail(userId, orderNo)
 ├─ OrderDao.getByOrderNo ──▶ SELECT t_order WHERE order_no = ?
 │    └─ null ──▶ BizException(ORDER_NOT_FOUND) ──▶ {code:30001}
 ├─ order.userId ≠ 当前 userId ──▶ BizException(ORDER_NOT_FOUND)   ★ 不返回 FORBIDDEN，避免泄露「订单号存在」
 ├─ OrderDao.listItemsByOrderId ──▶ SELECT t_order_item WHERE order_id = ?
 └─ OrderConverter.toVO ──▶ OrderVO
 │
Result.success(OrderVO)
```

> 查询只涉及读，不需要功能单元和事务，编排层直接组合 DAO 即可——**分层是为了隔离变化，不是为了凑层数**。

### 5.3 公共层：Result、ErrorCode、BizException、UserContext

`Result<T>`、`ErrorCode` 见 3.6 节，`BizException` 见第 06 章 10.1 节。用户上下文：

```java
/**
 * 当前请求的用户上下文，基于 ThreadLocal 实现。
 * 由 LoginInterceptor 写入与清理，业务代码只读。
 */
public final class UserContext {

    /** 当前线程绑定的登录用户 ID */
    private static final ThreadLocal<Long> USER_ID_HOLDER = new ThreadLocal<>();

    private UserContext() {
    }

    /**
     * 绑定当前用户。
     *
     * @param userId 登录用户 ID
     */
    public static void set(Long userId) {
        USER_ID_HOLDER.set(userId);
    }

    /**
     * 获取当前用户 ID，未登录时抛出异常（用于必须登录的业务）。
     *
     * @return 当前登录用户 ID
     * @throws BizException 未登录（UNAUTHORIZED）
     */
    public static Long requireUserId() {
        Long userId = USER_ID_HOLDER.get();
        if (userId == null) {
            throw new BizException(ErrorCode.UNAUTHORIZED);
        }
        return userId;
    }

    /**
     * 清理当前线程的用户信息，防止线程复用导致串号。
     */
    public static void clear() {
        USER_ID_HOLDER.remove();
    }
}
```

> 注意 ThreadLocal **不会自动传给子线程或线程池**。在编排层用 `CompletableFuture` 并行查询时（第 04 章），要在主线程先取出 userId 作为参数传入，或使用阿里的 `TransmittableThreadLocal`。

### 5.4 登录拦截器

```java
/**
 * JWT 工具：签发与解析 Token（依赖 io.jsonwebtoken:jjwt-api 0.12.x）。
 */
@Component
public class JwtUtil {

    /** 存放用户 ID 的 claim 名称 */
    private static final String CLAIM_USER_ID = "uid";

    private final SecretKey key;
    private final Duration expire;

    /**
     * @param secret      HMAC 密钥，至少 32 字节，来自配置 mall.jwt.secret
     * @param expireHours Token 有效期（小时），来自配置 mall.jwt.expire-hours
     */
    public JwtUtil(@Value("${mall.jwt.secret}") String secret,
                   @Value("${mall.jwt.expire-hours}") long expireHours) {
        this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        this.expire = Duration.ofHours(expireHours);
    }

    /**
     * 为用户签发 Token。
     *
     * @param userId 用户 ID
     * @return JWT 字符串
     */
    public String generate(Long userId) {
        Instant now = Instant.now();
        return Jwts.builder()
                .claim(CLAIM_USER_ID, userId)
                .issuedAt(Date.from(now))
                .expiration(Date.from(now.plus(expire)))
                .signWith(key)
                .compact();
    }

    /**
     * 解析 Token 得到用户 ID。验签失败、过期、格式错误一律返回 empty。
     *
     * @param token JWT 字符串
     * @return 用户 ID
     */
    public Optional<Long> parseUserId(String token) {
        try {
            Claims claims = Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload();
            return Optional.ofNullable(claims.get(CLAIM_USER_ID, Long.class));
        } catch (JwtException | IllegalArgumentException e) {
            return Optional.empty();
        }
    }
}
```

```java
/**
 * 免登录标记：标注在 Controller 类或方法上，LoginInterceptor 直接放行。
 */
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
public @interface NoLogin {
}
```

```java
/**
 * 登录拦截器：校验 JWT，将 userId 绑定到 UserContext，请求结束后清理。
 */
@Component
@RequiredArgsConstructor
public class LoginInterceptor implements HandlerInterceptor {

    /** Bearer Token 前缀 */
    private static final String BEARER_PREFIX = "Bearer ";

    private final JwtUtil jwtUtil;

    /**
     * 前置校验：免登录接口直接放行，否则解析 Token。
     *
     * @param request  请求
     * @param response 响应
     * @param handler  命中的处理器，Controller 方法时为 HandlerMethod
     * @return true 放行
     * @throws BizException 未登录时抛出，由全局异常处理器转为 {code:10002}
     */
    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        // 1. 非 Controller 方法（如静态资源）或标注了 @NoLogin 的直接放行
        if (!(handler instanceof HandlerMethod hm) || isNoLogin(hm)) {
            return true;
        }
        // 2. 解析 Token 并绑定上下文
        Long userId = resolveToken(request)
                .flatMap(jwtUtil::parseUserId)
                .orElseThrow(() -> new BizException(ErrorCode.UNAUTHORIZED));
        UserContext.set(userId);
        return true;
    }

    /**
     * 请求完成（含异常）后清理上下文。
     *
     * @param request  请求
     * @param response 响应
     * @param handler  处理器
     * @param ex       处理过程中的异常，可能为 null
     */
    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response,
                                Object handler, Exception ex) {
        UserContext.clear();
    }

    /**
     * 判断方法或其所在类是否标注 @NoLogin。
     *
     * @param hm Controller 方法
     * @return 是否免登录
     */
    private boolean isNoLogin(HandlerMethod hm) {
        return hm.hasMethodAnnotation(NoLogin.class) || hm.getBeanType().isAnnotationPresent(NoLogin.class);
    }

    /**
     * 从 Authorization 头中提取 Bearer Token。
     *
     * @param request 请求
     * @return Token 字符串，缺失或格式不对返回 empty
     */
    private Optional<String> resolveToken(HttpServletRequest request) {
        String header = request.getHeader(HttpHeaders.AUTHORIZATION);
        if (header == null || !header.startsWith(BEARER_PREFIX)) {
            return Optional.empty();
        }
        return Optional.of(header.substring(BEARER_PREFIX.length()));
    }
}
```

```java
/**
 * Spring MVC 配置：注册拦截器。
 */
@Configuration
@RequiredArgsConstructor
public class WebMvcConfig implements WebMvcConfigurer {

    private final LoginInterceptor loginInterceptor;

    /**
     * 登录拦截器作用于 /api/**，排除接口文档路径。
     *
     * @param registry 拦截器注册表
     */
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(loginInterceptor)
                .addPathPatterns("/api/**")
                .excludePathPatterns("/v3/api-docs/**", "/swagger-ui/**");
    }
}
```

> 为什么拦截器是 `@Component` 并通过注入注册，而不是 `new LoginInterceptor()`？因为它依赖 `JwtUtil`——自己 new 出来的对象不归容器管，依赖注入不进去（第 06 章 IoC）。

### 5.5 接口层：OrderController

```java
/**
 * 订单接口层：只负责取参、校验、取当前用户、调用编排层、包装返回值。
 */
@Tag(name = "订单")
@RestController
@RequestMapping("/api/orders")
@RequiredArgsConstructor
public class OrderController {

    private final OrderBizComponent orderBizComponent;

    /**
     * 创建订单。
     *
     * @param dto 下单入参，经 Bean Validation 校验
     * @return 订单详情
     */
    @Operation(summary = "创建订单")
    @PostMapping
    public Result<OrderVO> create(@RequestBody @Valid CreateOrderDTO dto) {
        return Result.success(orderBizComponent.createOrder(UserContext.requireUserId(), dto));
    }

    /**
     * 查询当前用户的订单详情。
     *
     * @param orderNo 订单号，最长 32 位
     * @return 订单详情
     */
    @Operation(summary = "查询订单详情")
    @GetMapping("/{orderNo}")
    public Result<OrderVO> detail(@PathVariable @NotBlank @Size(max = 32) String orderNo) {
        return Result.success(orderBizComponent.getOrderDetail(UserContext.requireUserId(), orderNo));
    }
}
```

Controller 里没有 `if`、没有 `try/catch`、没有 DAO——**这就是「接口层不写业务逻辑」的样子**。

### 5.6 编排层：OrderBizComponent

```java
/**
 * 订单编排组件：组合功能单元、DAO、转换器，实现下单与查单流程。
 * 业务流程变化（加风控、送积分、查物流）优先只改这一层。
 */
@Component
@RequiredArgsConstructor
public class OrderBizComponent {

    private final OrderCreateUnit orderCreateUnit;
    private final OrderDao orderDao;
    private final OrderConverter orderConverter;

    /**
     * 下单编排。
     *
     * @param userId 当前登录用户 ID
     * @param dto    下单入参
     * @return 订单详情 VO
     */
    @LogCost("创建订单")
    public OrderVO createOrder(Long userId, CreateOrderDTO dto) {
        // 1. 调用下单功能单元（事务在其内部）
        OrderPO order = orderCreateUnit.createOrder(userId, dto.getItems());
        // 2. 查明细并组装出参
        return orderConverter.toVO(order, orderDao.listItemsByOrderId(order.getId()));
    }

    /**
     * 查单编排：查订单 → 校验归属 → 查明细 → 转换。
     *
     * @param userId  当前登录用户 ID
     * @param orderNo 订单号
     * @return 订单详情 VO
     * @throws BizException 订单不存在或不属于当前用户（ORDER_NOT_FOUND）
     */
    @LogCost("查询订单详情")
    public OrderVO getOrderDetail(Long userId, String orderNo) {
        OrderPO order = requireOwnOrder(userId, orderNo);
        return orderConverter.toVO(order, orderDao.listItemsByOrderId(order.getId()));
    }

    /**
     * 查询订单并校验归属。不属于当前用户时与「不存在」返回相同错误，避免订单号被枚举探测。
     *
     * @param userId  当前用户 ID
     * @param orderNo 订单号
     * @return 属于当前用户的订单
     */
    private OrderPO requireOwnOrder(Long userId, String orderNo) {
        OrderPO order = orderDao.getByOrderNo(orderNo);
        if (order == null || !order.getUserId().equals(userId)) {
            throw new BizException(ErrorCode.ORDER_NOT_FOUND);
        }
        return order;
    }
}
```

> 当前 `createOrder` 只有一步，看起来编排层「很薄」。业务迭代时它会长成这样，而 `OrderCreateUnit` 一行不改：
> ```java
> riskClient.check(userId);                                    // 新需求：下单前风控（事务外）
> OrderPO order = orderCreateUnit.createOrder(userId, dto.getItems());
> couponUnit.useCoupon(userId, dto.getCouponId(), order);      // 新需求：用券
> ```

### 5.7 功能单元：OrderCreateUnit

完整代码与逐行说明见第 06 章 10.3 节，此处只列契约：

```java
/**
 * 下单功能单元：校验商品 → 扣库存 → 写 t_order → 写 t_order_item → 发布 OrderCreatedEvent，同一事务。
 */
@Component
@RequiredArgsConstructor
public class OrderCreateUnit {

    /**
     * 创建订单（事务方法）。
     *
     * @param userId 下单用户 ID
     * @param items  下单商品明细
     * @return 已落库的订单 PO（含 id、orderNo）
     * @throws BizException PRODUCT_NOT_FOUND / STOCK_NOT_ENOUGH，抛出即整体回滚
     */
    @Transactional(rollbackFor = Exception.class)
    public OrderPO createOrder(Long userId, List<OrderItemDTO> items) { /* 见第 06 章 */ }
}
```

> 功能单元的入参用的是 `OrderItemDTO`（接口层对象）。严格来说可以再定义一个 `OrderCreateCmd` 隔离，但在 DTO 足够稳定时，这是可以接受的务实取舍；当出现第二个入口（如 MQ 导单）入参结构不同时再抽。

### 5.8 能力单元与 PO

`OrderDao`、`ProductDao`、`ProductMapper` 代码见第 06 章 10.2 节。PO 定义：

```java
/**
 * 订单表 t_order 实体。
 */
@Data
@TableName("t_order")
public class OrderPO {

    /** 主键，自增 */
    @TableId(type = IdType.AUTO)
    private Long id;
    /** 订单号，唯一 */
    private String orderNo;
    /** 下单用户 ID */
    private Long userId;
    /** 订单总额（元） */
    private BigDecimal totalAmount;
    /** 订单状态，取值见 OrderStatusEnum */
    private Integer status;
    /** 创建时间，由数据库默认值填充 */
    private LocalDateTime createTime;
    /** 更新时间，由数据库 ON UPDATE 填充 */
    private LocalDateTime updateTime;
}
```

```java
/**
 * 订单明细表 t_order_item 实体。
 */
@Data
@TableName("t_order_item")
public class OrderItemPO {

    /** 主键，自增 */
    @TableId(type = IdType.AUTO)
    private Long id;
    /** 所属订单 ID */
    private Long orderId;
    /** 商品 ID */
    private Long productId;
    /** 商品名称快照 */
    private String productName;
    /** 下单时单价快照（元） */
    private BigDecimal price;
    /** 购买数量 */
    private Integer quantity;
    /** 创建时间 */
    private LocalDateTime createTime;
}
```

> `createTime` 由数据库默认值填充，`insert` 后 PO 里仍为 null。若创建接口需要返回准确的下单时间，可在第 08 章用 MyBatis-Plus 的 `MetaObjectHandler` 在应用侧自动填充。

### 5.9 工具层：OrderConverter 与 OrderNoUtil

```java
/**
 * 订单出参 VO。
 */
@Data
public class OrderVO {

    /** 订单号 */
    private String orderNo;
    /** 订单总额（元） */
    private BigDecimal totalAmount;
    /** 状态码，取值见 OrderStatusEnum */
    private Integer status;
    /** 状态文案 */
    private String statusDesc;
    /** 下单时间 */
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime createTime;
    /** 订单明细 */
    private List<OrderItemVO> items;
}
```

```java
/**
 * 订单明细出参 VO。
 */
@Data
public class OrderItemVO {

    /** 商品 ID */
    private Long productId;
    /** 商品名称 */
    private String productName;
    /** 单价（元） */
    private BigDecimal price;
    /** 购买数量 */
    private Integer quantity;
}
```

给 `OrderStatusEnum` 增加按 code 查文案的方法（第 06 章已定义枚举本体）：

```java
/**
 * 按 code 查询状态文案。
 *
 * @param code 状态码
 * @return 状态文案，未知 code 返回「未知」
 */
public static String descOf(Integer code) {
    for (OrderStatusEnum e : values()) {
        if (code != null && e.code == code) {
            return e.desc;
        }
    }
    return "未知";
}
```

```java
/**
 * 订单对象转换器（MapStruct 编译期生成实现类，注册为 Spring Bean）。
 */
@Mapper(componentModel = MappingConstants.ComponentModel.SPRING, imports = OrderStatusEnum.class)
public interface OrderConverter {

    /**
     * 订单 PO + 明细 PO → 订单 VO。
     *
     * @param order 订单 PO
     * @param items 明细 PO 列表
     * @return 订单 VO
     */
    @Mapping(target = "statusDesc", expression = "java(OrderStatusEnum.descOf(order.getStatus()))")
    @Mapping(target = "items", source = "items")
    OrderVO toVO(OrderPO order, List<OrderItemPO> items);

    /**
     * 明细 PO → 明细 VO（toVO 中处理 List 时自动调用）。
     *
     * @param item 明细 PO
     * @return 明细 VO
     */
    OrderItemVO toItemVO(OrderItemPO item);

    /**
     * 商品 + 数量 → 订单明细 PO（做名称、价格快照）。
     *
     * @param product  商品 PO
     * @param quantity 购买数量
     * @return 明细 PO（id、orderId、createTime 未设置）
     */
    @Mapping(target = "id", ignore = true)
    @Mapping(target = "orderId", ignore = true)
    @Mapping(target = "createTime", ignore = true)
    @Mapping(target = "productId", source = "product.id")
    @Mapping(target = "productName", source = "product.name")
    @Mapping(target = "price", source = "product.price")
    @Mapping(target = "quantity", source = "quantity")
    OrderItemPO toItemPO(ProductPO product, Integer quantity);
}
```

编译后 MapStruct 生成的 `OrderConverterImpl` 就是普通的 `vo.setOrderNo(order.getOrderNo())` 代码，可以在 `target/generated-sources` 里直接看到。

```java
/**
 * 订单号生成工具。
 */
public final class OrderNoUtil {

    /** 时间部分格式：精确到毫秒，17 位 */
    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("yyyyMMddHHmmssSSS");

    private OrderNoUtil() {
    }

    /**
     * 生成订单号：17 位时间 + 3 位随机数，共 20 位，满足 order_no VARCHAR(32)。
     * 单机低并发可用；毫秒内超过 1000 单会有冲突风险，由 order_no 唯一索引兜底，第 11 章换成分布式 ID。
     *
     * @return 订单号
     */
    public static String generate() {
        return LocalDateTime.now().format(FORMATTER)
                + String.format("%03d", ThreadLocalRandom.current().nextInt(1000));
    }
}
```

### 5.10 包结构总览

```
com.example.mall
├── MiniMallApplication.java          @SpringBootApplication @ConfigurationPropertiesScan
├── config        WebMvcConfig · CorsConfig · JacksonConfig
├── interceptor   LoginInterceptor
├── controller    OrderController                                    ①
├── biz           OrderBizComponent                                  ②
├── domain        OrderCreateUnit · OrderCreatedEvent · OrderCreatedListener   ③
├── dao           OrderDao · ProductDao                              ④
│   └── mapper    OrderMapper · OrderItemMapper · ProductMapper
├── convert       OrderConverter                                     ⑤
├── util          OrderNoUtil · JwtUtil                              ⑤
├── model
│   ├── dto       CreateOrderDTO · OrderItemDTO
│   ├── vo        OrderVO · OrderItemVO
│   ├── po        OrderPO · OrderItemPO · ProductPO · UserPO
│   └── enums     OrderStatusEnum
└── common        Result · ErrorCode · BizException · UserContext · GlobalExceptionHandler
    ├── annotation  LogCost · NoLogin
    └── aspect      LogCostAspect
```

### 5.11 用 curl 验证

```bash
# 未登录
curl -s -X POST localhost:8080/api/orders -H 'Content-Type: application/json' -d '{"items":[]}'
# {"code":10002,"message":"请先登录","data":null}

# 参数错误
curl -s -X POST localhost:8080/api/orders -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' -d '{"items":[{"productId":1001,"quantity":0}]}'
# {"code":10001,"message":"items[0].quantity 购买数量至少为 1","data":null}

# 下单成功
curl -s -X POST localhost:8080/api/orders -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' -d '{"items":[{"productId":1001,"quantity":2}]}'

# 查别人的订单
curl -s localhost:8080/api/orders/20261126143012123456 -H "Authorization: Bearer $OTHER_TOKEN"
# {"code":30001,"message":"订单不存在","data":null}
```

---

## 6. 常见坑

| # | 坑 | 后果 | 正确做法 |
|---|---|---|---|
| 1 | 启动类不在根包 | 部分 Bean 扫描不到，注入失败 | 启动类放 `com.example.mall` |
| 2 | Long 型 ID 直接返回 | 前端精度丢失，ID 末位变化 | 全局 Long → String 序列化 |
| 3 | 嵌套对象/List 元素忘加 `@Valid` | 内层校验注解不生效 | `List<@Valid OrderItemDTO>` |
| 4 | 用 PO 直接接收入参或返回 | 越权写字段、泄露敏感字段 | DTO 入、VO 出 |
| 5 | ThreadLocal 不清理 | 线程复用导致用户串号（严重越权） | `afterCompletion` 中 `remove()` |
| 6 | 登录拦截器拦了 OPTIONS 预检 | 前端报 CORS 错误 | CORS 放在 Filter 层先处理 |
| 7 | Filter 中抛异常期望被全局处理 | 返回 Boot 默认错误页 JSON，格式不统一 | Filter 中自行写响应 |
| 8 | 把异常 message / 堆栈返回给前端 | 泄露表结构、SQL | 兜底返回通用文案，细节进日志 |
| 9 | `BeanUtils.copyProperties` 到处用 | 字段名改了静默丢值 | MapStruct |
| 10 | 敏感配置写进 `application-prod.yml` 提交仓库 | 密码泄露 | 环境变量 / 配置中心 / K8s Secret |
| 11 | Spring Boot 3 用了 `javax.*` 包 | 编译失败 | Boot 3 全面迁移到 `jakarta.*`（`jakarta.validation`、`jakarta.servlet`） |
| 12 | Controller 里写业务逻辑、加事务 | 无法复用，大事务 | 按五层落位 |

---

## 7. 高级视角

### 7.1 接口设计的工程素养

| 关注点 | 做法 |
|---|---|
| 幂等 | 下单接口被重复提交（前端双击、网关重试）怎么办？→ 前端传 `requestId`，服务端用 Redis `SETNX` 或唯一索引去重（第 09 章） |
| 版本兼容 | 出参**只加字段不删改**；App 老版本还在线上 |
| 分页 | 深分页 `LIMIT 100000, 20` 很慢，改游标分页（第 08 章） |
| 限流 | 网关层 + 应用层（Sentinel，第 11 章） |
| 超时 | 每个外部调用都要有超时，否则一个慢依赖耗尽 Tomcat 线程 |
| 可观测 | TraceId 贯穿、`@LogCost` 慢接口告警（第 12 章） |

### 7.2 前端出身的优势如何发挥

- 你最懂接口契约的使用方：错误码文案能否直接展示、字段命名是否一致、空值是 `null` 还是不返回——这些细节决定了前端开发体验。
- 用 SpringDoc + `orval` 打通类型生成，在团队里推动「接口即契约」。
- BFF 思维：VO 按页面需要组装，而不是把表结构扔给前端拼。

### 7.3 何时打破分层

分层是工具不是教条。纯读接口（如本章的查单）不需要功能单元；内部运维接口可以更薄。**判断标准始终是：这次变更会不会波及不该改的地方？** 会，就该拆；不会，就别为了分层而分层。

### 7.4 Spring WebFlux 要不要学

WebFlux 是 Spring 的响应式 Web 栈（基于 Netty，类似 Node 的非阻塞模型），写法是 `Mono` / `Flux` 链式调用。在 Java 21 虚拟线程普及后，**同步写法 + 虚拟线程**已能拿到接近的吞吐，而代码可读性、调试、生态（MyBatis、JDBC 都是阻塞的）都远好于响应式。结论：业务开发以 Spring MVC 为主，WebFlux 了解概念、在网关（Spring Cloud Gateway 基于 WebFlux）场景能读懂即可。

---

## 8. 小练习

1. **自动配置**：启动时加 `--debug`，在报告中找到 `DataSourceAutoConfiguration` 和 `RedisAutoConfiguration`，解释它们为什么生效 / 不生效。
2. **手写 Starter**：完成 4.2 节的 `mall-trace-spring-boot-starter`，在 mini-mall 中引入，验证日志带 TraceId；再配置 `mall.trace.enabled=false` 验证关闭。
3. **请求流转**：在 `DispatcherServlet#doDispatch` 打断点，跟一次 `POST /api/orders`，找出参数解析和 JSON 序列化分别发生在哪个类。
4. **校验**：给查询订单列表接口 `GET /api/orders?status=&page=&size=` 定义 `OrderQueryDTO`，用 `@InEnum(OrderStatusEnum.class)` 校验 status，`size` 最大 100。
5. **执行顺序**：分别写一个 Filter、Interceptor、`@LogCost` 切面，各自打印进入/退出日志，画出一次请求的实际打印顺序，与 3.8 节的图对照。
6. **鉴权**：实现 `POST /api/auth/login`（标注 `@NoLogin`），用 `t_user` 的 phone 登录返回 JWT；然后验证：用户 A 的 Token 查询用户 B 的订单返回 30001。
7. **分层演进**：需求变更「下单后给用户加积分，积分失败不影响下单」，说出你要改哪些层、新增哪些类、积分逻辑放在事务内还是事务外，为什么。
