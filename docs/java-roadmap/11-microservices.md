# 第 11 章 微服务与分布式：Spring Cloud Alibaba、分布式事务、分布式 ID、定时任务

> [← 总纲](./00-outline.md) | [上一章：消息队列](./10-message-queue.md) | [下一章：部署、监控与线上排查](./12-devops-observability.md)

---

## 1. 本章地图

```
                         浏览器 / App
                              │
                              ▼
                    mall-gateway（Spring Cloud Gateway）  ← 统一鉴权、路由、限流
                              │ lb://mall-order
         ┌────────────────────┼─────────────────────┐
         ▼                    ▼                     ▼
     mall-user           mall-order ──OpenFeign──▶ mall-product
                              │                     │
                              └──── RocketMQ ───────┘     ← 最终一致性
  ─────────────────────────────────────────────────────────────────────
  Nacos（注册 + 配置） · Sentinel（限流熔断） · Seata（可选） · XXL-Job · SkyWalking
```

| 问题 | 小节 |
|---|---|
| 什么时候拆、怎么拆、什么时候别拆 | 2、3.1 |
| 服务怎么互相找到、怎么调用、怎么扛住故障 | 3.3 ~ 3.7 |
| 跨服务的数据一致性怎么保证 | 3.8、4.3、5.5 |
| 分布式 ID、分布式定时任务、链路追踪、幂等、灰度 | 3.9 ~ 3.13 |
| mini-mall 拆分落地 | 5 |

---

## 2. 前端类比

### 2.1 微前端 vs 微服务

| 维度 | 微前端（qiankun / Module Federation） | 微服务 |
|---|---|---|
| 拆分动机 | 多团队并行开发、独立发布、技术栈异构 | 同左 + **独立扩容**、**故障隔离** |
| 运行形态 | 同一个浏览器标签页内多个子应用 | **多个独立进程**，通过网络通信 |
| 通信方式 | props、全局状态、CustomEvent | HTTP（Feign）、RPC（Dubbo）、MQ |
| 失败影响 | 子应用白屏，主应用通常还在 | 一个服务慢 → 调用方线程被占满 → **雪崩** |
| 数据 | 共享同一份后端数据 | **每个服务有自己的库**，跨库无事务 |
| 基座 | 主应用负责路由与加载 | 网关负责路由；注册中心负责寻址 |

> 微前端拆完，最坏是一个区域白屏；微服务拆完，**网络调用会失败、会超时、会重复，数据会不一致**。这才是微服务难的地方。

### 2.2 一组对照

| 前端 | 微服务世界 |
|---|---|
| axios 实例 + 拦截器 | OpenFeign + `RequestInterceptor` |
| `baseURL` 写死或从 env 读 | 服务名 `lb://mall-product`，由注册中心解析为 IP 列表 |
| 请求失败 → 展示兜底数据 | Sentinel 熔断 → fallback |
| BFF（Node 聚合层） | API 网关（偏通用横切）+ 聚合服务（偏业务） |
| `setInterval` | XXL-Job |
| Sentry 的 traceId / 前端埋点 | SkyWalking 全链路追踪 |
| 远程配置 / Feature Flag | Nacos 配置中心 + `@RefreshScope` |
| 防重复提交（按钮 loading） | 接口幂等（token / 唯一索引） |
| 灰度发布（按用户分流到新版前端） | 网关按 header/用户 ID 分流到新版本实例 |

---

## 3. 核心概念

### 3.1 从单体到微服务

```
阶段 1：单体             阶段 2：垂直拆分 + 共享库      阶段 3：微服务（库也拆）
┌─────────────┐        ┌──────┐ ┌──────┐            ┌──────┐   ┌──────┐
│ user        │        │order │ │product│           │order │──▶│product│
│ product     │   ─▶   └──┬───┘ └──┬───┘     ─▶    └──┬───┘   └──┬───┘
│ order       │           └───┬────┘                  │          │
└──────┬──────┘               ▼                       ▼          ▼
       ▼                   一个库                   order_db   product_db
     一个库             （过渡态，耦合仍在）
```

**拆分原则**：

| 原则 | 说明 |
|---|---|
| 按业务能力 / 领域边界拆（DDD 限界上下文） | 用户、商品、订单、支付、库存是天然边界 |
| 高内聚低耦合 | 经常一起修改的代码放一起；拆完如果每个需求都要改 3 个服务，说明拆错了 |
| 数据归属唯一 | 每张表只有一个服务能写，其他服务通过接口或消息获取 |
| 按变化频率 / 资源特征 | 秒杀、搜索这种流量特征差异大的，独立部署独立扩容 |
| 康威定律 | 服务边界最终会和团队边界对齐：**一个服务最好由一个团队负责** |

**何时不该拆**：

- 团队 < 10 人、业务还在快速试错：单体 + 良好分层（第 7 章的五层）就够了。
- 没有基础设施：没有 CI/CD、监控、链路追踪、配置中心，拆了只会更难排查。
- 拆分理由只是「技术先进」：微服务带来的分布式事务、网络故障、运维成本是实打实的。

> 务实路线：**模块化单体**（Maven 多模块，模块间只通过接口调用，不跨模块访问表）→ 需要时再把模块独立成服务。

### 3.2 CAP 与 BASE

```
         C 一致性（所有节点同一时刻看到相同数据）
              ▲
             / \
            /   \       网络分区（P）在分布式系统中必然发生，
           /     \      所以真实的选择是：分区时保 C 还是保 A
          ▼───────▼
  A 可用性           P 分区容错
```

| 选择 | 行为 | 例子 |
|---|---|---|
| CP | 分区时拒绝服务，保证数据一致 | ZooKeeper、etcd、Nacos 的 CP 模式（持久化实例，Raft） |
| AP | 分区时继续服务，数据可能短暂不一致 | Eureka、Nacos 的 AP 模式（临时实例，Distro 协议） |

**BASE**：Basically Available（基本可用）、Soft state（软状态，允许中间态）、Eventually consistent（最终一致）。
它是互联网业务对 CAP 的工程化回答：**放弃强一致，追求最终一致**。订单的「待支付」「库存已预扣」本质都是软状态。

### 3.3 Spring Cloud 与 Spring Cloud Alibaba 全景

| 能力 | Spring Cloud Netflix（多已停更） | Spring Cloud 官方 | **Spring Cloud Alibaba（本系列选型）** |
|---|---|---|---|
| 注册中心 | Eureka | Consul / ZooKeeper | **Nacos** |
| 配置中心 | — | Spring Cloud Config | **Nacos** |
| 服务调用 | Feign | **OpenFeign** | OpenFeign / Dubbo |
| 负载均衡 | Ribbon | **Spring Cloud LoadBalancer** | 同左 |
| 网关 | Zuul | **Spring Cloud Gateway** | 同左 |
| 熔断限流 | Hystrix | Resilience4j | **Sentinel** |
| 分布式事务 | — | — | **Seata** |
| 消息 | — | Spring Cloud Stream | **RocketMQ** |
| 链路追踪 | Sleuth（已并入 Micrometer Tracing） | Micrometer Tracing | 常用 **SkyWalking** |
| 定时任务 | — | — | 社区常用 **XXL-Job** |

版本对应关系很重要（Spring Boot 3.2.x ↔ Spring Cloud 2023.0.x ↔ Spring Cloud Alibaba 2023.0.x），统一在父 pom 中用 BOM 管理：

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>2023.0.3</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>com.alibaba.cloud</groupId>
            <artifactId>spring-cloud-alibaba-dependencies</artifactId>
            <version>2023.0.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

### 3.4 Nacos：注册中心与配置中心

**服务注册发现流程**：

```
 mall-product 实例启动
   │ ① 注册：服务名 + IP:端口 + 元数据（version=v2、weight）
   ▼
 Nacos Server ◀── ② 临时实例：gRPC 长连接保活（2.x）；1.x 为每 5s 心跳，15s 不健康，30s 剔除
   │
   │ ③ 订阅 + 推送：实例变化时 Nacos 主动推送给订阅者（UDP/gRPC）
   ▼
 mall-order（本地缓存实例列表 → LoadBalancer 选一个 → 发 HTTP）
```

| 要点 | 说明 |
|---|---|
| 临时实例 vs 持久实例 | 临时实例（默认）靠客户端保活，AP（Distro 协议）；持久实例由服务端主动探测，CP（Raft） |
| 客户端缓存 | 调用方本地有实例列表缓存，**Nacos 挂了已有调用不受影响**（只是感知不到新变化） |
| 下线感知延迟 | 实例被 kill -9 时，调用方要等到连接断开/心跳超时才知道 → 期间请求会打到死实例，所以必须配合**重试**和**优雅下线** |
| 命名空间 / 分组 | namespace 隔离环境（dev/test/prod），group 隔离业务 |

**动态配置**：

```yaml
# bootstrap 方式已废弃，Spring Boot 3 用 spring.config.import
spring:
  application:
    name: mall-order
  cloud:
    nacos:
      server-addr: 127.0.0.1:8848
      discovery:
        namespace: dev
      config:
        namespace: dev
  config:
    import:
      - nacos:mall-order.yaml?refreshEnabled=true
      - nacos:mall-common.yaml        # 多服务共享配置
```

```java
/**
 * 订单业务开关配置，绑定 Nacos 中 mall.order 前缀的配置项。
 * 使用 @ConfigurationProperties 时，Nacos 配置变更会自动重新绑定，无需 @RefreshScope。
 */
@Data
@Component
@ConfigurationProperties(prefix = "mall.order")
public class OrderProperties {

    /** 单笔订单最大商品种类数 */
    private int maxItemCount = 20;

    /** 是否开启下单（大促期间可一键关闭） */
    private boolean createEnabled = true;
}
```

```java
/**
 * 使用 @Value 读取的配置，需要 @RefreshScope 才能在变更后刷新：
 * 原理是该 Bean 被放入 refresh 作用域，配置变化时销毁旧实例，下次访问时重新创建。
 */
@RefreshScope
@RestController
public class FeatureController {

    /** 首页公告文案 */
    @Value("${mall.notice:}")
    private String notice;
}
```

TS 对照：

```ts
// 前端的远程配置 / Feature Flag：轮询或订阅后更新内存值
const flags = await fetch('/api/flags').then(r => r.json());
if (flags.createEnabled) { /* ... */ }
```

> 推荐 `@ConfigurationProperties`：类型安全、自动刷新、可集中管理。`@RefreshScope` 会让 Bean 变成代理并在刷新时重建，和定时任务、长连接对象混用容易出问题。

### 3.5 OpenFeign：声明式 HTTP 客户端

```ts
// TS：axios 封装的接口层
const productApi = axios.create({ baseURL: '/product-service', timeout: 2000 });
productApi.interceptors.request.use(cfg => {
  cfg.headers['X-Trace-Id'] = getTraceId();
  return cfg;
});
export const deductStock = (dto: DeductStockDTO) =>
  productApi.post<Result<void>>('/inner/product/stock/deduct', dto);
```

```java
/**
 * 商品服务远程调用客户端（定义在 mall-product-api 模块，由调用方依赖）。
 * name 为 Nacos 中的服务名，运行时由 LoadBalancer 解析为具体实例。
 */
@FeignClient(name = "mall-product", path = "/inner/product", fallbackFactory = ProductClientFallbackFactory.class)
public interface ProductClient {

    /**
     * 批量扣减库存（幂等：同一 orderNo 重复调用只扣一次）。
     *
     * @param dto 扣库存请求，包含订单号与商品明细
     * @return 统一返回；code != 0 表示扣减失败（如库存不足）
     */
    @PostMapping("/stock/deduct")
    Result<Void> deductStock(@RequestBody DeductStockDTO dto);

    /**
     * 按订单号回补库存（幂等：只有已扣减且未回补的记录才会回补）。
     *
     * @param orderNo 订单号
     * @return 统一返回
     */
    @PostMapping("/stock/restore")
    Result<Void> restoreStock(@RequestParam("orderNo") String orderNo);

    /**
     * 批量查询商品信息。
     *
     * @param ids 商品 ID 列表
     * @return 商品信息列表
     */
    @GetMapping("/list")
    Result<List<ProductDTO>> listByIds(@RequestParam("ids") List<Long> ids);
}
```

**超时与重试**：

```yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          default:
            connect-timeout: 1000    # 建连超时 1s
            read-timeout: 3000       # 读超时 3s
          mall-product:
            read-timeout: 2000       # 按服务覆盖
      httpclient:
        hc5:
          enabled: true              # 用连接池替代默认的 HttpURLConnection
```

| 要点 | 说明 |
|---|---|
| 默认不重试 | OpenFeign 默认 `Retryer.NEVER_RETRY`，这是对的 |
| 重试只能用于幂等接口 | 扣库存超时重试 → 可能扣两次。**要么接口幂等，要么不重试** |
| 超时设置 | 调用方超时 < 被调用方超时 < 网关超时；整体要小于用户能接受的时间 |

**拦截器透传 TraceId 与用户信息**：

```java
/**
 * Feign 请求拦截器：把当前线程上下文中的 TraceId 与用户 ID 透传给下游服务。
 * 下游服务的 Filter 负责从 Header 中取出并写回 MDC / UserContext。
 */
@Component
public class FeignContextInterceptor implements RequestInterceptor {

    /** 链路追踪 ID 的 Header 名 */
    public static final String HEADER_TRACE_ID = "X-Trace-Id";

    /** 当前登录用户 ID 的 Header 名（仅内网服务间信任，网关会剔除外部传入的同名 Header） */
    public static final String HEADER_USER_ID = "X-User-Id";

    /**
     * 在请求发出前追加 Header。
     *
     * @param template Feign 请求模板
     */
    @Override
    public void apply(RequestTemplate template) {
        // 1. TraceId 来自日志 MDC（由入口 Filter 写入）
        String traceId = MDC.get("traceId");
        if (traceId != null) {
            template.header(HEADER_TRACE_ID, traceId);
        }
        // 2. 用户 ID 来自 ThreadLocal 上下文
        Long userId = UserContext.getUserId();
        if (userId != null) {
            template.header(HEADER_USER_ID, String.valueOf(userId));
        }
    }
}
```

> ⚠️ ThreadLocal / MDC 在线程切换时会丢失：Feign 调用如果放进 `CompletableFuture`，需要用装饰线程池（`TaskDecorator`）把上下文拷贝过去（第 4 章）。

**fallback**：

```java
/**
 * ProductClient 的降级工厂：远程调用失败或被 Sentinel 熔断时返回兜底结果。
 * 用 FallbackFactory 而不是 fallback，可以拿到失败原因用于日志。
 */
@Slf4j
@Component
public class ProductClientFallbackFactory implements FallbackFactory<ProductClient> {

    /**
     * 创建降级实现。
     *
     * @param cause 触发降级的异常
     * @return 降级实现
     */
    @Override
    public ProductClient create(Throwable cause) {
        return new ProductClient() {
            @Override
            public Result<Void> deductStock(DeductStockDTO dto) {
                // 写操作不能「假装成功」：返回失败让调用方走失败分支
                log.error("扣库存调用失败, orderNo={}", dto.orderNo(), cause);
                return Result.fail(ErrorCode.REMOTE_CALL_FAILED);
            }

            @Override
            public Result<Void> restoreStock(String orderNo) {
                log.error("回补库存调用失败, orderNo={}", orderNo, cause);
                return Result.fail(ErrorCode.REMOTE_CALL_FAILED);
            }

            @Override
            public Result<List<ProductDTO>> listByIds(List<Long> ids) {
                // 读操作可以降级为空列表，由页面展示「商品信息加载失败」
                return Result.success(List.of());
            }
        };
    }
}
```

> 降级原则：**读可以兜底，写不能假装成功**。超时的写请求结果是「不确定」，而不是「失败」——后面幂等与对账都是为这一点服务的。

### 3.6 负载均衡：Spring Cloud LoadBalancer

| 维度 | 说明 |
|---|---|
| 位置 | **客户端负载均衡**：调用方从本地实例列表中选择，不经过中心代理（对比 Nginx 是服务端负载均衡） |
| 策略 | 默认 `RoundRobinLoadBalancer`；还有 `RandomLoadBalancer`；Nacos 提供按权重的 `NacosLoadBalancer` |
| 扩展 | 实现 `ReactorServiceInstanceLoadBalancer` 可做同机房优先、按版本元数据路由（灰度） |
| 缓存 | 实例列表默认缓存 35s（`spring.cloud.loadbalancer.cache.ttl`），Nacos 推送会主动刷新 |

### 3.7 API 网关：Spring Cloud Gateway

```
请求 ─▶ Gateway Handler Mapping ─(断言 Predicate 匹配路由)─▶ Filter 链（pre）─▶ 下游服务
                                                          ◀─ Filter 链（post）◀─
```

| 概念 | 说明 | 例子 |
|---|---|---|
| Route 路由 | id + 目标 uri + 断言 + 过滤器 | `/api/order/** → lb://mall-order` |
| Predicate 断言 | 决定请求是否匹配该路由 | Path、Method、Header、Weight |
| Filter 过滤器 | 修改请求/响应 | StripPrefix、RequestRateLimiter、自定义 GlobalFilter |

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: mall-order
          uri: lb://mall-order          # lb:// 表示走注册中心 + 负载均衡
          predicates:
            - Path=/api/order/**
          filters:
            - StripPrefix=1             # /api/order/create → /order/create
        - id: mall-product
          uri: lb://mall-product
          predicates:
            - Path=/api/product/**
          filters:
            - StripPrefix=1
```

统一鉴权（Gateway 基于 **WebFlux 响应式**，不能用 ThreadLocal、不能写阻塞代码）：

```java
/**
 * 网关统一鉴权过滤器：校验 JWT，解析出用户 ID 写入下游 Header；白名单路径放行。
 */
@Component
@RequiredArgsConstructor
public class AuthGlobalFilter implements GlobalFilter, Ordered {

    /** 无需登录的路径前缀 */
    private static final List<String> WHITE_LIST = List.of("/api/user/login", "/api/product/detail");

    private final JwtUtil jwtUtil;

    /**
     * 鉴权逻辑。
     *
     * @param exchange 当前请求上下文
     * @param chain    过滤器链
     * @return 异步完成信号
     */
    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String path = exchange.getRequest().getURI().getPath();
        // 1. 先剔除外部伪造的内部 Header，防止越权
        ServerHttpRequest.Builder builder = exchange.getRequest().mutate()
                .headers(h -> h.remove(FeignContextInterceptor.HEADER_USER_ID));
        if (isWhiteListed(path)) {
            return chain.filter(exchange.mutate().request(builder.build()).build());
        }
        // 2. 校验 Token
        String token = exchange.getRequest().getHeaders().getFirst(HttpHeaders.AUTHORIZATION);
        Long userId = jwtUtil.parseUserId(token);
        if (userId == null) {
            exchange.getResponse().setStatusCode(HttpStatus.UNAUTHORIZED);
            return exchange.getResponse().setComplete();
        }
        // 3. 透传用户 ID 给下游
        builder.header(FeignContextInterceptor.HEADER_USER_ID, String.valueOf(userId));
        return chain.filter(exchange.mutate().request(builder.build()).build());
    }

    /**
     * 判断路径是否在白名单内。
     *
     * @param path 请求路径
     * @return true 表示无需鉴权
     */
    private boolean isWhiteListed(String path) {
        return WHITE_LIST.stream().anyMatch(path::startsWith);
    }

    /**
     * 过滤器顺序，越小越先执行；鉴权要尽量靠前。
     *
     * @return 顺序值
     */
    @Override
    public int getOrder() {
        return -100;
    }
}
```

**网关 vs BFF**：

| 维度 | API 网关 | BFF（Backend For Frontend） |
|---|---|---|
| 职责 | 横切关注点：路由、鉴权、限流、灰度、协议转换 | 面向某个端的**数据聚合与裁剪** |
| 是否有业务 | 不应有 | 有（页面级编排） |
| 数量 | 通常一个（或按内外网分） | 每个端一个（Web BFF、App BFF） |
| 技术 | Spring Cloud Gateway / Nginx / APISIX | Node（前端团队维护）或 Java 聚合服务 |

> 两者常常同时存在：`客户端 → 网关 → BFF → 领域服务`。不要把业务聚合写进网关。

### 3.8 Sentinel：限流、熔断、降级

```ts
// 前端兜底：请求失败展示缓存数据
try {
  return await api.getRecommend();
} catch {
  return cachedRecommend ?? [];
}
```

前端的兜底只保护「自己的页面」；Sentinel 要保护的是「**整个系统不被拖垮**」：

```
雪崩：product 变慢(5s) → order 的 Tomcat 线程全部阻塞在 Feign 调用上
     → order 不可用 → gateway 线程也堆积 → 全站不可用

熔断器状态机：
  CLOSED ──(慢调用比例/异常比例超阈值)──▶ OPEN ──(熔断时长到)──▶ HALF_OPEN
     ▲                                     │ 直接走 fallback             │ 放一个探测请求
     └──────────────── 探测成功 ◀──────────┴──────── 探测失败 → OPEN ◀──┘
```

| 能力 | 说明 | 典型配置 |
|---|---|---|
| 流量控制 | QPS / 并发线程数阈值；直接拒绝、Warm Up 预热、匀速排队 | 下单接口 QPS 500 |
| 熔断降级 | 慢调用比例、异常比例、异常数 | RT > 1s 比例 > 50% 熔断 10s |
| 热点参数限流 | 对某个参数值单独限流 | 单个商品 ID 每秒 100 次（防刷爆款） |
| 系统自适应保护 | 按 Load、CPU、整体 QPS 兜底 | CPU > 80% 拒绝入口流量 |
| 规则持久化 | 默认规则在内存中，重启丢失 → 推模式持久化到 Nacos | 生产必做 |

```java
/**
 * 查询商品详情，接入 Sentinel 资源保护。
 *
 * @param productId 商品 ID
 * @return 商品详情
 */
@SentinelResource(value = "getProductDetail",
        blockHandler = "detailBlocked",      // 被限流/熔断时调用
        fallback = "detailFallback")         // 业务异常时调用
public ProductVO getProductDetail(Long productId) {
    return productQueryUnit.getDetail(productId);
}

/**
 * 限流/熔断处理：参数列表与原方法一致，末尾多一个 BlockException。
 *
 * @param productId 商品 ID
 * @param ex        Sentinel 拦截异常
 * @return 降级结果
 */
public ProductVO detailBlocked(Long productId, BlockException ex) {
    throw new BizException(ErrorCode.SYSTEM_BUSY);
}

/**
 * 业务异常兜底：返回缓存中的旧数据。
 *
 * @param productId 商品 ID
 * @param ex        业务异常
 * @return 兜底结果
 */
public ProductVO detailFallback(Long productId, Throwable ex) {
    return productCacheDao.getStale(productId);
}
```

### 3.9 分布式事务

单体时代：`@Transactional` 一把梭。拆分后：订单在 `order_db`，库存在 `product_db`，**本地事务管不了两个库**。

| 方案 | 原理 | 一致性 | 性能 | 侵入性 | 适用 |
|---|---|---|---|---|---|
| **2PC / XA** | 协调者：Prepare 全部成功 → Commit | 强一致 | 差：资源锁定贯穿两阶段 | 低（数据库支持） | 内部低并发、强一致 |
| **3PC** | 加 CanCommit 与超时机制减少阻塞 | 仍有不一致窗口 | 差 | — | 基本只存在于教科书 |
| **TCC** | Try 预留 → Confirm 确认 / Cancel 释放 | 最终一致（准实时） | 好 | **高**：每个操作写三个接口，处理空回滚、悬挂、幂等 | 资金、库存等核心 |
| **Saga** | 正向操作链 + 每步的补偿操作 | 最终一致 | 好 | 中：写补偿 | 长流程（订机票+酒店） |
| **Seata AT** | 自动生成反向 SQL（undo_log）+ 全局锁 | 最终一致（读未提交级别隔离需注意） | 中 | **低**：加注解 | 内部系统、并发不高 |
| **本地消息表** | 业务 + 消息同库同事务，异步投递 + 重试 | 最终一致 | 好 | 中 | **最通用** |
| **事务消息** | 半消息 + 回查（第 10 章） | 最终一致 | 好 | 中 | 用 RocketMQ 时 |
| **最大努力通知** | 按退避策略多次通知，提供查询接口兜底 | 弱 | 好 | 低 | 跨公司：支付回调 |

TCC 三个经典问题：

| 问题 | 场景 | 解决 |
|---|---|---|
| 空回滚 | Try 未执行（网络丢失）却收到 Cancel | Cancel 时发现无 Try 记录 → 记录一条「已取消」并直接成功 |
| 悬挂 | Cancel 先到并完成，Try 后到又预留了资源 | Try 前检查是否已有「已取消」记录 |
| 幂等 | Confirm/Cancel 被重复调用 | 事务日志表 + 状态判断 |

> **选型建议**：绝大多数互联网业务追求**最终一致性**。优先级：「能不能避免分布式事务（调整服务边界）」>「本地消息表 / 事务消息 + 幂等 + 对账」> TCC（核心资金）> Seata AT（内部系统、追求开发效率）。2PC/XA 在高并发场景几乎不用。

### 3.10 分布式 ID

为什么不用数据库自增：分库分表后各库自增会重复；ID 连续会暴露业务量；依赖数据库写入才能拿到 ID。

| 方案 | 结构 | 优点 | 缺点 |
|---|---|---|---|
| UUID | 128 位随机 | 本地生成 | 无序 → B+ 树页分裂，**不适合做主键**；太长 |
| 数据库号段（Leaf-segment） | 每次从 DB 取一段 [1000, 2000) 缓存在内存 | 趋势递增、高性能 | 依赖 DB；双 buffer 预加载避免取号抖动 |
| **雪花算法 Snowflake** | 1 位符号 + 41 位毫秒时间戳 + 10 位机器 ID + 12 位序列号 | 本地生成、趋势递增、单机每毫秒 4096 个 | **依赖时钟**；机器 ID 需分配 |
| Leaf-snowflake | 雪花 + ZooKeeper 分配机器 ID + 时钟校验 | 解决 workerId 分配 | 依赖 ZK |
| Redis INCR | 原子自增 | 简单 | 依赖 Redis 持久化 |

```
雪花 ID 64 位：
 0 | 41 位时间戳（相对自定义纪元，可用约 69 年） | 5 位数据中心 | 5 位机器 | 12 位序列号
```

**时钟回拨**：NTP 校时可能让系统时间倒退，生成的 ID 就可能重复。处理策略：回拨很小（如 ≤ 5ms）则等待追上；回拨较大则拒绝生成并告警，或切换备用 workerId。

```java
/**
 * 雪花算法 ID 生成器（单机线程安全版），带时钟回拨保护。
 * 生产环境建议直接使用 MyBatis-Plus 的 IdWorker 或美团 Leaf，此实现用于理解原理。
 */
public class SnowflakeIdGenerator {

    /** 自定义纪元：2024-01-01 00:00:00 UTC 的毫秒值 */
    private static final long EPOCH = 1704067200000L;
    /** 机器 ID 占用位数（此处把数据中心与机器合并为 10 位） */
    private static final long WORKER_ID_BITS = 10L;
    /** 序列号占用位数 */
    private static final long SEQUENCE_BITS = 12L;
    /** 序列号最大值 4095 */
    private static final long MAX_SEQUENCE = (1L << SEQUENCE_BITS) - 1;
    /** 可容忍的最大时钟回拨毫秒数 */
    private static final long MAX_BACKWARD_MS = 5L;

    /** 当前机器 ID，0 ~ 1023 */
    private final long workerId;
    /** 上一次生成 ID 的时间戳 */
    private long lastTimestamp = -1L;
    /** 当前毫秒内的序列号 */
    private long sequence = 0L;

    /**
     * 构造生成器。
     *
     * @param workerId 机器 ID，需保证集群内唯一（可由 Nacos 元数据或 K8s StatefulSet 序号分配）
     */
    public SnowflakeIdGenerator(long workerId) {
        if (workerId < 0 || workerId > (1L << WORKER_ID_BITS) - 1) {
            throw new IllegalArgumentException("workerId 超出范围: " + workerId);
        }
        this.workerId = workerId;
    }

    /**
     * 生成下一个 ID。
     *
     * @return 64 位趋势递增 ID
     */
    public synchronized long nextId() {
        long now = System.currentTimeMillis();
        // 1. 时钟回拨处理：小幅回拨等待，大幅回拨直接失败
        if (now < lastTimestamp) {
            now = waitForClockCatchUp(now);
        }
        // 2. 同一毫秒内序列号自增，溢出则自旋到下一毫秒
        if (now == lastTimestamp) {
            sequence = (sequence + 1) & MAX_SEQUENCE;
            if (sequence == 0) {
                now = spinToNextMillis(lastTimestamp);
            }
        } else {
            sequence = 0L;
        }
        lastTimestamp = now;
        // 3. 拼接：时间戳 | 机器 ID | 序列号
        return ((now - EPOCH) << (WORKER_ID_BITS + SEQUENCE_BITS))
                | (workerId << SEQUENCE_BITS)
                | sequence;
    }

    /**
     * 等待时钟追上上次时间戳；回拨超过阈值时抛异常。
     *
     * @param now 当前时间戳
     * @return 追上后的时间戳
     */
    private long waitForClockCatchUp(long now) {
        long offset = lastTimestamp - now;
        if (offset > MAX_BACKWARD_MS) {
            throw new IllegalStateException("时钟回拨 " + offset + "ms，拒绝生成 ID");
        }
        return spinToNextMillis(lastTimestamp - 1);
    }

    /**
     * 自旋直到当前时间大于给定时间戳。
     *
     * @param timestamp 参照时间戳
     * @return 新的时间戳
     */
    private long spinToNextMillis(long timestamp) {
        long now = System.currentTimeMillis();
        while (now <= timestamp) {
            now = System.currentTimeMillis();
        }
        return now;
    }
}
```

> 订单号 `order_no` 通常不直接用雪花 ID，而是「业务前缀 + 日期 + 雪花/号段 + 用户 ID 后几位」（便于分库分表按用户路由），例如 `M20261126` + 序列。

### 3.11 分布式定时任务：XXL-Job

```ts
// 前端：每个打开的标签页都会执行一次
setInterval(() => syncDraft(), 60_000);
```

后端同样的问题：订单服务部署 4 个实例，用 Spring `@Scheduled` → **4 个实例各执行一次**，对账跑 4 遍、通知发 4 遍。

```
@Scheduled：                       XXL-Job：
 实例1 ── 02:00 执行                 调度中心(admin) ── 02:00 触发 ──▶ 按路由策略选一个执行器实例
 实例2 ── 02:00 执行  ❌重复                │                          （第一个/轮询/故障转移/分片广播）
 实例3 ── 02:00 执行                        └── 记录日志、失败重试、告警、手动触发、查看执行记录
```

| 特性 | 说明 |
|---|---|
| 架构 | **调度中心**（独立部署，存 MySQL，基于数据库行锁保证集群只调度一次）+ **执行器**（业务服务内嵌，注册到调度中心） |
| 路由策略 | FIRST、ROUND、RANDOM、CONSISTENT_HASH、FAILOVER（故障转移）、**SHARDING_BROADCAST（分片广播）** |
| 阻塞策略 | 单机串行 / 丢弃后续调度 / 覆盖之前调度 |
| 分片广播 | 所有执行器都执行，各自拿到 `shardIndex / shardTotal`，按 `id % total == index` 分摊数据 |
| 其他 | 超时控制、失败重试、子任务、GLUE 在线代码（生产慎用） |

> 轻量替代：ShedLock（`@Scheduled` + 数据库/Redis 锁，保证只一个实例执行）。任务多、需要管理界面时用 XXL-Job。

### 3.12 链路追踪

```
TraceId: 7f3a...（一次请求全局唯一）
 gateway  [Span A 0ms ─────────────────────────────── 120ms]
  order   [Span B   5ms ───────────────────────── 115ms]
   product  [Span C 10ms ── 40ms]                         ← Feign 调用
   MySQL         [Span D 45ms ─ 60ms]
   RocketMQ           [Span E 62ms ─ 65ms]
```

| 概念 | 说明 |
|---|---|
| Trace | 一次完整请求链路，由 TraceId 标识 |
| Span | 链路中的一个操作（一次 RPC、一次 SQL），有 SpanId 与 ParentSpanId |
| 透传 | HTTP Header（W3C `traceparent` 或自定义 `X-Trace-Id`）、MQ 消息属性 |
| SkyWalking | **Java Agent 字节码增强**，业务代码零侵入；自动采集 Feign/MySQL/Redis/MQ 的 Span；提供拓扑图、慢调用、告警 |

把 TraceId 打进日志（第 12 章 ELK 会用到）：

```xml
<!-- logback-spring.xml：使用 SkyWalking 的 TraceId 转换器 -->
<pattern>%d{HH:mm:ss.SSS} [%thread] [%X{traceId}] [%tid] %-5level %logger{36} - %msg%n</pattern>
```

### 3.13 接口幂等

同一请求执行一次和多次，结果一致。重复来源：用户连点、前端重试、网关重试、Feign 超时重试、MQ 重投。

| 方案 | 流程 | 适用 |
|---|---|---|
| **Token 机制** | ① 打开下单页时 `GET /order/token` 生成 token 存 Redis；② 提交时带 token；③ 服务端 `DEL token` 返回 1 才执行（原子删除即判断） | 前端表单提交、防重复下单 |
| **唯一索引** | 业务唯一键（如 `order_no`、`(order_no, biz_type)`）建唯一索引，插入冲突即重复 | 最终兜底，**一定要有** |
| 状态机 | `UPDATE ... WHERE status = 旧状态` | 状态流转 |
| 分布式锁 | Redisson 锁住业务键，期间重复请求被拒绝 | 防并发，不防「先后」重复，需配合唯一索引 |

```ts
// 前端：按钮 loading 只能防住同一页面的连点，防不住重试、刷新、多端
const [loading, setLoading] = useState(false);
```

```java
/**
 * 校验并消费下单防重 token：Redis DEL 是原子的，返回 1 说明本次请求抢到了 token。
 *
 * @param userId 用户 ID
 * @param token  前端提交的 token
 * @return true 首次提交；false 重复提交或 token 已过期
 */
public boolean consumeSubmitToken(Long userId, String token) {
    String key = "order:submit:token:" + userId + ":" + token;
    return Boolean.TRUE.equals(stringRedisTemplate.delete(key));
}
```

### 3.14 服务间 DTO 契约与 api 模块

```
mall-product
├── mall-product-api        ← 对外契约：ProductClient、DeductStockDTO、ProductDTO（只依赖 mall-common）
└── mall-product-service    ← 实现：Controller、Biz、Unit、Dao、PO

mall-order-service 依赖 mall-product-api（而不是 service）
```

| 规则 | 原因 |
|---|---|
| api 模块只放接口与 DTO，不放实现、不引入重依赖 | 调用方不应被迫引入你的 MyBatis、Redis |
| **PO 绝不出现在 api 模块** | 表结构变化不应影响调用方 |
| DTO 只增字段不删改，兼容旧版本 | 两个服务不会同时发布 |
| 版本号随服务发布 | 调用方升级 api 版本时有明确的变更记录 |
| 内部接口统一前缀 `/inner/**`，网关不对外暴露 | 防止被外部直接调用 |

> 这就是前端熟悉的「OpenAPI 生成 TS 类型」的 Java 版本：**契约先行，双方依赖同一份类型定义**。

### 3.15 灰度发布

```
                       ┌── header X-Gray=true 或 userId % 100 < 5 ──▶ mall-order v2（metadata.version=v2）
请求 ─▶ Gateway ───────┤
                       └── 其余 ─────────────────────────────────────▶ mall-order v1
```

实现：实例在 Nacos 注册时带 `metadata.version`；网关和 Feign 侧自定义 LoadBalancer，根据请求 Header 选择版本；灰度标记要**沿链路透传**（和 TraceId 一样），保证「灰度请求只走灰度实例」。K8s 场景也可用 Ingress/Service Mesh（Istio）按权重分流。

---

## 4. 原理深挖

### 4.1 OpenFeign 是怎么「调接口就发请求」的

```
@EnableFeignClients 扫描 @FeignClient 接口
  → 为每个接口注册 FeignClientFactoryBean
  → getObject() 时用 JDK 动态代理生成实现类（第 6 章 AOP 原理）
调用 productClient.deductStock(dto)
  → InvocationHandler 找到方法对应的 MethodHandler
  → Contract 解析 Spring MVC 注解 → 构造 RequestTemplate
  → RequestInterceptor 链（追加 Header）
  → Encoder 序列化 body（Jackson）
  → LoadBalancer 把 mall-product 替换为 10.0.0.12:8080
  → Client（HttpClient5 / OkHttp）发出 HTTP
  → Decoder 反序列化响应为 Result<Void>；非 2xx 交给 ErrorDecoder
```

> 本质和前端用 TS 类型 + axios 生成 SDK 一样，只是 Java 在**运行时**用动态代理生成实现。

### 4.2 Nacos 配置推送原理

- 客户端启动拉取配置并缓存到本地文件（`~/nacos/config`），Nacos 不可用时降级读本地快照。
- 1.x 用 **HTTP 长轮询**（30s 挂起，有变更立即返回 dataId），2.x 改为 **gRPC 长连接推送**。
- 客户端拿到变更 → 拉取新内容 → 发布 `EnvironmentChangeEvent` / `RefreshEvent` → `@ConfigurationProperties` 重新绑定、`@RefreshScope` Bean 销毁重建。

### 4.3 Seata AT 模式原理

```
角色：TC（事务协调者，独立部署）  TM（事务发起方，@GlobalTransactional）  RM（各服务的数据源代理）

一阶段（每个分支本地提交）：
  order 服务 RM 拦截 SQL：INSERT INTO t_order ...
    ① 解析 SQL，查询「前镜像」（INSERT 无前镜像）
    ② 执行业务 SQL
    ③ 查询「后镜像」
    ④ 把前后镜像写入 undo_log（与业务 SQL 同一本地事务）
    ⑤ 向 TC 注册分支并申请「全局锁」（锁住修改的行主键）
    ⑥ 本地提交（释放数据库行锁，但全局锁仍持有）
  product 服务 RM 同理：UPDATE t_product SET stock = stock - 1 ...

二阶段：
  全部成功 → TC 通知各 RM 提交：异步删除 undo_log（很快）
  任一失败 → TC 通知各 RM 回滚：根据 undo_log 生成反向 SQL；
            先校验当前数据 == 后镜像（否则说明被「脏写」，需人工介入）
```

| 设计取舍 | 说明 |
|---|---|
| 一阶段就本地提交 | 不像 XA 那样长时间持有数据库锁，性能比 XA 好 |
| 全局锁 | 防止其他全局事务修改同一行导致回滚失败（写隔离）；但**不走 Seata 的本地写操作不受全局锁约束**，可能造成脏写 |
| 默认读未提交 | 其他事务能读到一阶段已提交、但全局可能回滚的数据；需要 `SELECT ... FOR UPDATE` 才能读已提交 |
| 依赖 | 每个库要建 `undo_log` 表；要部署 TC 集群（TC 本身需高可用，存储用 DB 或 Raft） |
| 热点问题 | 爆款商品的库存行全局锁竞争激烈，高并发下吞吐差 |

### 4.4 XXL-Job 为什么「多实例只执行一次」

```
调度中心集群（多个 admin 实例）
  每个 admin 的调度线程循环：
    ① BEGIN; SELECT * FROM xxl_job_lock WHERE lock_name='schedule_lock' FOR UPDATE;  ← 数据库悲观锁，集群只有一个 admin 能进入
    ② 预读未来 5s 内要触发的任务，放入时间轮
    ③ 更新任务下次触发时间；COMMIT
  时间轮到点 → 按路由策略选执行器 → HTTP 调用执行器的 /run 接口
执行器（嵌入 mall-order 中）
  收到 /run → 放入该任务的队列 → JobThread 执行 @XxlJob 方法 → 回调结果给 admin
```

所以「只执行一次」由**调度中心的数据库锁 + 路由到单个执行器**共同保证；分片广播则是有意让每个执行器都执行一次、各处理一部分数据。

### 4.5 SkyWalking Agent 原理

- 启动参数 `-javaagent:skywalking-agent.jar`，JVM 在加载业务类之前先执行 Agent 的 `premain`。
- Agent 用 **ByteBuddy** 在类加载时修改字节码：在 `feign.Client#execute`、`DispatcherServlet#doDispatch`、JDBC `PreparedStatement#execute` 等方法前后插入「开始 Span / 结束 Span」代码。
- 跨进程：出站请求时把上下文写入 Header `sw8`，入站时解析恢复。跨线程需要插件或 `@TraceCrossThread` 包装。
- Span 数据异步批量通过 gRPC 发给 OAP Server，存储到 ES/BanyanDB，UI 展示。

---

## 5. mini-mall 实战：拆分为微服务

### 5.1 多模块结构

```
mini-mall（parent pom：统一 BOM、插件版本）
├── mall-common                 Result<T>、BizException、ErrorCode、UserContext、FeignContextInterceptor、工具类
├── mall-gateway                Spring Cloud Gateway：路由、AuthGlobalFilter、限流
├── mall-user
│   ├── mall-user-api           UserClient、UserDTO
│   └── mall-user-service       t_user
├── mall-product
│   ├── mall-product-api        ProductClient、DeductStockDTO、ProductDTO
│   └── mall-product-service    t_product、t_stock_deduct_log
└── mall-order
    ├── mall-order-api          （对外暴露订单查询时使用）
    └── mall-order-service      t_order、t_order_item、t_local_message
                                依赖 mall-product-api、mall-user-api
```

| 服务 | 数据库 | 拥有的表 | 对外能力 |
|---|---|---|---|
| mall-user | user_db | t_user | 用户信息、登录 |
| mall-product | product_db | t_product、t_stock_deduct_log | 商品查询、扣/回补库存（幂等） |
| mall-order | order_db | t_order、t_order_item、t_local_message | 下单、订单查询、取消 |

### 5.2 契约 DTO

```java
package com.example.mall.product.api.dto;

/**
 * 扣库存请求（mall-product-api 中的服务间契约）。
 *
 * @param orderNo 订单号，作为扣库存操作的幂等键
 * @param items   扣减明细，不可为空
 */
public record DeductStockDTO(@NotBlank String orderNo, @NotEmpty List<StockItem> items) {

    /**
     * 单个商品扣减项。
     *
     * @param productId 商品 ID
     * @param quantity  扣减数量，必须大于 0
     */
    public record StockItem(@NotNull Long productId, @Min(1) Integer quantity) {
    }
}
```

商品服务新增扣减流水表，作为扣库存与回补的幂等依据：

```sql
-- t_stock_deduct_log：库存扣减流水，order_no 唯一保证同一订单只扣一次；status 保证只回补一次
CREATE TABLE t_stock_deduct_log (
    id          BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
    order_no    VARCHAR(32) NOT NULL COMMENT '订单号',
    items_json  JSON        NOT NULL COMMENT '扣减明细 [{productId, quantity}]',
    status      TINYINT     NOT NULL DEFAULT 1 COMMENT '状态：1 已扣减 2 已回补',
    create_time DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_order_no (order_no),
    KEY idx_create_time (create_time)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '库存扣减流水';
```

```java
package com.example.mall.product.domain;

/**
 * 库存扣减功能单元（商品服务）：写扣减流水 + 扣减各商品库存，同一事务。
 */
@Component
@RequiredArgsConstructor
public class StockDeductUnit {

    /** 扣减流水状态：已扣减 */
    private static final int STATUS_DEDUCTED = 1;

    private final StockDeductLogDao stockDeductLogDao;
    private final ProductDao productDao;

    /**
     * 幂等扣减库存：同一订单号重复调用直接返回成功。
     *
     * @param dto 扣减请求
     * @throws BizException 任一商品库存不足时抛出，整体回滚
     */
    @Transactional(rollbackFor = Exception.class)
    public void deduct(DeductStockDTO dto) {
        // 1. 唯一键抢占：已存在说明之前扣过（可能是调用方超时重试）
        if (!stockDeductLogDao.insertIgnoreDuplicate(dto.orderNo(), dto.items(), STATUS_DEDUCTED)) {
            return;
        }
        // 2. 逐个扣减：UPDATE t_product SET stock = stock - ? WHERE id = ? AND stock >= ?
        for (DeductStockDTO.StockItem item : dto.items()) {
            if (!productDao.deductStock(item.productId(), item.quantity())) {
                throw new BizException(ErrorCode.STOCK_NOT_ENOUGH);
            }
        }
    }
}
```

`StockRestoreUnit.restore(orderNo)` 同理：`UPDATE t_stock_deduct_log SET status=2 WHERE order_no=? AND status=1`，影响 1 行才按 `items_json` 回补库存；记录不存在（空回滚）直接返回成功。

### 5.3 下单一致性方案对比

问题：下单 = 扣库存（product_db）+ 写订单（order_db），两个库。

**方案 A：Seata AT**

```java
/**
 * 下单（Seata AT 版本）：一个注解开启全局事务，任一环节异常时 TC 驱动所有分支回滚。
 *
 * @param dto 下单入参
 * @return 订单号
 */
@GlobalTransactional(name = "mall-create-order", rollbackFor = Exception.class)
public String createOrderWithSeata(CreateOrderDTO dto) {
    String orderNo = orderNoGenerator.next();
    // 分支 1：远程扣库存（product 服务的数据源被 Seata 代理，生成 undo_log）
    Result<Void> r = productClient.deductStock(orderConverter.toDeductStockDTO(orderNo, dto));
    if (!r.isSuccess()) {
        throw new BizException(ErrorCode.STOCK_NOT_ENOUGH);
    }
    // 分支 2：本地写订单 + 明细
    orderCreateUnit.create(orderNo, dto);
    return orderNo;
}
```

**方案 B：先扣库存（幂等）+ 本地事务（订单 + 本地消息表）+ 异步补偿 + 对账**

| 对比项 | Seata AT | 本地消息表 + MQ |
|---|---|---|
| 开发成本 | 低：一个注解 | 中：消息表、投递任务、补偿、对账 |
| 运维成本 | **高**：TC 集群、每个库 undo_log、版本兼容 | 低：复用已有 MQ 与 XXL-Job |
| 性能 | 全局锁 + 多次与 TC 交互，热点商品吞吐差 | 只有本地事务，吞吐高 |
| 一致性 | 「看起来像」强一致，但隔离性弱（读未提交、非 Seata 写操作可能脏写） | 最终一致，有明确的中间态与补偿 |
| 故障场景 | TC 不可用 → 所有全局事务失败 | MQ 不可用 → 消息留在表里，恢复后补发 |
| 可观测/可审计 | undo_log 删除后无痕 | 消息表与扣减流水可追溯、可人工重放 |
| 适用 | 内部管理系统、低并发、追求开发效率 | **C 端交易链路（推荐）** |

> 推荐方案 B。理由：电商下单是高并发核心链路，不能依赖一个额外的协调者集群；最终一致 + 可对账才是长期可维护的方案。

### 5.4 本地消息表

```sql
-- t_local_message：本地消息表（order_db），与业务数据同库同事务写入，保证「业务成功则消息一定存在」
CREATE TABLE t_local_message (
    id              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    msg_key         VARCHAR(64)  NOT NULL COMMENT '业务消息 Key，如订单号',
    topic           VARCHAR(64)  NOT NULL COMMENT '目标 Topic',
    tag             VARCHAR(64)  NOT NULL COMMENT '目标 Tag',
    payload         JSON         NOT NULL COMMENT '消息体',
    status          TINYINT      NOT NULL DEFAULT 0 COMMENT '状态：0 待发送 1 已发送 2 发送失败(超过最大重试)',
    retry_count     INT          NOT NULL DEFAULT 0 COMMENT '已重试次数',
    next_retry_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '下次重试时间',
    create_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_msg_key_tag (msg_key, tag),
    KEY idx_status_retry (status, next_retry_time)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '本地消息表';
```

```java
/**
 * 本地消息状态枚举。
 */
@Getter
@AllArgsConstructor
public enum LocalMessageStatusEnum {

    /** 待发送：已随业务事务落库，尚未投递成功 */
    PENDING(0, "待发送"),
    /** 已发送：MQ 已确认接收 */
    SENT(1, "已发送"),
    /** 发送失败：超过最大重试次数，需要人工介入 */
    FAILED(2, "发送失败");

    /** 状态码，对应 t_local_message.status */
    private final int code;
    /** 状态描述 */
    private final String desc;
}
```

### 5.5 推荐方案完整流程

```
OrderController.create
  → OrderBizComponent.createOrder
     ① 校验 + 防重 token（Redis DEL）
     ② orderNo = OrderNoGenerator.next()
     ③ ProductClient.deductStock(orderNo, items)            ─── Feign ──▶ mall-product
            │                                                         StockDeductUnit.deduct（幂等，同事务）
            ├─ 返回失败（库存不足）→ 直接返回用户「库存不足」，无需补偿
            ├─ 超时/网络异常（结果不确定）→ 发布「回补库存」补偿（④'），返回「下单失败请重试」
            └─ 成功 ↓
     ④ OrderCreateUnit.createWithMessage  @Transactional（order_db 单库）
            ├─ INSERT t_order(status=0) / t_order_item
            └─ INSERT t_local_message(ORDER_CREATED, PENDING)
            │
            ├─ 失败 → ④' StockCompensateComponent.compensate(orderNo)
            │         → ProductClient.restoreStock（幂等）；再失败则记录 → 由对账任务兜底
            └─ 成功 ↓
     ⑤ 事务提交后（afterCommit）立即尝试投递 ORDER_CREATED、延迟 30 分钟 ORDER_TIMEOUT_CHECK
            ├─ 成功 → t_local_message.status = SENT
            └─ 失败 → 保持 PENDING，由 LocalMessageRelayJob（XXL-Job 每分钟）按 next_retry_time 重投
     ⑥ 返回订单 VO
  ─────────────────────────────── 异步 ───────────────────────────────
  RocketMQ ORDER_CREATED   ─▶ 积分、通知消费者（第 10 章，幂等）
  RocketMQ 超时检查（30min）─▶ mall-order OrderCancelUnit.cancelIfUnpaid
                                 ├─ UPDATE status 0→2（状态机）
                                 └─ 写本地消息 STOCK_RESTORE ─▶ mall-product 消费 → StockRestoreUnit（幂等）
  每日 02:00 OrderReconcileJob ─▶ 对比扣减流水与订单，修复残留不一致
```

关键编排代码：

```java
/**
 * 下单编排（微服务版）：远程扣库存 → 本地事务写订单与消息 → 失败补偿。
 *
 * @param dto 下单入参
 * @return 订单视图
 */
public OrderVO createOrder(CreateOrderDTO dto) {
    String orderNo = orderNoGenerator.next();
    // 1. 远程扣库存：失败分为「明确失败」与「结果不确定」两类
    deductStockOrThrow(orderNo, dto);
    try {
        // 2. 本地事务：订单 + 明细 + 本地消息，原子写入
        orderCreateUnit.createWithMessage(orderNo, dto);
    } catch (Exception e) {
        // 3. 订单写入失败 → 回补库存（幂等，失败也无妨，对账兜底）
        stockCompensateComponent.compensate(orderNo);
        throw e;
    }
    return orderConverter.toVO(orderDao.getByOrderNo(orderNo));
}

/**
 * 调用商品服务扣库存；超时等不确定结果也触发补偿，避免库存被「悬空」扣减。
 *
 * @param orderNo 订单号
 * @param dto     下单入参
 */
private void deductStockOrThrow(String orderNo, CreateOrderDTO dto) {
    Result<Void> result;
    try {
        result = productClient.deductStock(orderConverter.toDeductStockDTO(orderNo, dto));
    } catch (Exception e) {
        // 超时：对方可能已经扣减成功，必须补偿
        stockCompensateComponent.compensate(orderNo);
        throw new BizException(ErrorCode.ORDER_CREATE_FAILED);
    }
    if (!result.isSuccess()) {
        throw new BizException(ErrorCode.STOCK_NOT_ENOUGH);
    }
}
```

```java
package com.example.mall.order.domain;

/**
 * 订单创建功能单元（微服务版）：写订单、明细、本地消息三张表，同一本地事务。
 */
@Component
@RequiredArgsConstructor
public class OrderCreateUnit {

    private final OrderDao orderDao;
    private final OrderItemDao orderItemDao;
    private final LocalMessageDao localMessageDao;
    private final OrderConverter orderConverter;
    private final LocalMessageRelay localMessageRelay;

    /**
     * 创建订单并登记待发送消息；事务提交后触发一次即时投递。
     *
     * @param orderNo 订单号
     * @param dto     下单入参
     */
    @Transactional(rollbackFor = Exception.class)
    public void createWithMessage(String orderNo, CreateOrderDTO dto) {
        // 1. 写订单主表与明细
        OrderPO order = orderConverter.toPO(orderNo, dto);
        orderDao.insert(order);
        orderItemDao.batchInsert(orderConverter.toItemPOs(order.getId(), dto));
        // 2. 写本地消息：与订单同库同事务，业务成功则消息一定存在
        OrderCreatedEvent event = orderConverter.toCreatedEvent(order);
        localMessageDao.insert(orderNo, MqConstants.TOPIC_ORDER, MqConstants.TAG_ORDER_CREATED, event);
        // 3. 注册事务提交后的回调：提交成功才投递，回滚则不会执行
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                localMessageRelay.relayQuietly(orderNo, MqConstants.TAG_ORDER_CREATED);
            }
        });
    }
}
```

```java
/**
 * 本地消息投递器：负责把 t_local_message 中的待发送消息投递到 MQ，并更新状态。
 * 被两处复用：事务提交后的即时投递、XXL-Job 定时重扫。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class LocalMessageRelay {

    /** 最大重试次数，超过后置为 FAILED 并告警 */
    private static final int MAX_RETRY = 10;

    private final LocalMessageDao localMessageDao;
    private final RocketMQTemplate rocketMQTemplate;

    /**
     * 投递单条消息，异常只记录不抛出（调用方是事务回调或定时任务，不应影响主流程）。
     *
     * @param msgKey 业务 Key
     * @param tag    消息 Tag
     */
    public void relayQuietly(String msgKey, String tag) {
        LocalMessagePO msg = localMessageDao.getPending(msgKey, tag);
        if (msg == null) {
            return;
        }
        try {
            // 1. 同步发送，payload 为 JSON 字符串，消费端按事件类型反序列化
            rocketMQTemplate.syncSend(msg.getTopic() + ":" + msg.getTag(),
                    MessageBuilder.withPayload(msg.getPayload())
                            .setHeader(MessageConst.PROPERTY_KEYS, msg.getMsgKey()).build());
            // 2. 发送成功标记 SENT；若此处失败，下次重扫会再发一次 → 消费端幂等兜底
            localMessageDao.markSent(msg.getId());
        } catch (Exception e) {
            // 3. 发送失败：重试次数 +1，按指数退避计算下次时间
            localMessageDao.markRetry(msg.getId(), msg.getRetryCount() + 1, MAX_RETRY);
            log.warn("本地消息投递失败, key={}, tag={}, retry={}", msgKey, tag, msg.getRetryCount() + 1, e);
        }
    }
}
```

> 注意：`afterCommit` 中的代码运行时事务已提交，但仍在原线程中执行，会增加接口 RT；可以交给异步线程池执行。
> 与第 10 章事务消息的关系：两者解决同一个问题。单体 + RocketMQ 可用事务消息；微服务里推荐本地消息表——**不绑定 MQ 产品、可审计、能复用于「回补库存」等多种补偿消息**。

### 5.6 XXL-Job：每日订单对账

对账目标：找出 product 服务「已扣减」但 order 服务「没有订单」的记录（下单失败但补偿也失败），回补库存。

```java
package com.example.mall.product.job;

/**
 * 每日库存扣减对账任务（部署在商品服务，接口层：只负责分片与调用）。
 * 路由策略配置为「分片广播」：每个实例按 id 取模处理自己负责的那一部分。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class OrderReconcileJob {

    /** 每批处理的记录数 */
    private static final int PAGE_SIZE = 200;

    private final StockReconcileComponent stockReconcileComponent;

    /**
     * 对账入口：每天 02:00 执行（Cron 在调度中心配置：0 0 2 * * ?），处理前一天的扣减流水。
     */
    @XxlJob("orderReconcileJob")
    public void execute() {
        int shardIndex = XxlJobHelper.getShardIndex();
        int shardTotal = XxlJobHelper.getShardTotal();
        // 支持在调度中心手动传参指定日期，便于补跑
        LocalDate bizDate = parseBizDate(XxlJobHelper.getJobParam());
        ReconcileResult result = stockReconcileComponent.reconcile(bizDate, shardIndex, shardTotal, PAGE_SIZE);
        XxlJobHelper.log("对账完成 date={}, shard={}/{}, checked={}, fixed={}",
                bizDate, shardIndex, shardTotal, result.checked(), result.fixed());
        XxlJobHelper.handleSuccess();
    }

    /**
     * 解析任务参数中的业务日期，未传则取昨天。
     *
     * @param param 任务参数，格式 yyyy-MM-dd，可为空
     * @return 对账日期
     */
    private LocalDate parseBizDate(String param) {
        return (param == null || param.isBlank()) ? LocalDate.now().minusDays(1) : LocalDate.parse(param);
    }
}
```

```java
/**
 * 对账结果。
 *
 * @param checked 检查的流水条数
 * @param fixed   修复（回补库存）的条数
 */
public record ReconcileResult(int checked, int fixed) {
}
```

```java
/**
 * 库存对账编排组件：分页扫描扣减流水 → 批量向订单服务确认订单是否存在 → 不存在则回补。
 */
@Component
@RequiredArgsConstructor
public class StockReconcileComponent {

    private final StockDeductLogDao stockDeductLogDao;
    private final OrderClient orderClient;
    private final StockRestoreUnit stockRestoreUnit;

    /**
     * 对指定日期、指定分片的扣减流水做对账。
     *
     * @param bizDate    业务日期
     * @param shardIndex 当前分片序号
     * @param shardTotal 分片总数
     * @param pageSize   每批数量
     * @return 对账结果
     */
    public ReconcileResult reconcile(LocalDate bizDate, int shardIndex, int shardTotal, int pageSize) {
        int checked = 0;
        int fixed = 0;
        long lastId = 0L;
        while (true) {
            // 1. 游标分页：WHERE id > lastId AND create_time 在当日 AND status=1 AND MOD(id, total)=index
            List<StockDeductLogPO> logs =
                    stockDeductLogDao.pageDeducted(bizDate, shardIndex, shardTotal, lastId, pageSize);
            if (logs.isEmpty()) {
                break;
            }
            // 2. 批量查询订单是否存在（避免 N 次远程调用）
            List<String> orderNos = logs.stream().map(StockDeductLogPO::getOrderNo).toList();
            Set<String> existing = new HashSet<>(orderClient.listExistingOrderNos(orderNos).getData());
            // 3. 订单不存在的流水 → 回补库存（幂等）
            for (StockDeductLogPO deductLog : logs) {
                if (!existing.contains(deductLog.getOrderNo()) && stockRestoreUnit.restore(deductLog.getOrderNo())) {
                    fixed++;
                }
            }
            checked += logs.size();
            lastId = logs.get(logs.size() - 1).getId();
        }
        return new ReconcileResult(checked, fixed);
    }
}
```

> ⚠️ 对账窗口要避开「正在进行中」的数据：只对账 T-1 日数据，或只处理 `create_time < now - 10min` 的流水，避免把刚扣减、订单还没提交的请求误回补。
> `OrderClient.listExistingOrderNos` 是订单服务新增的内部接口（`/inner/order/exists`），定义在 `mall-order-api`。

### 5.7 服务调用链路图（下单）

```
[Browser]
   │ POST /api/order/create  (Authorization: Bearer xxx)
   ▼
[mall-gateway]
   │ AuthGlobalFilter：JWT → userId；生成/透传 X-Trace-Id；剔除外部 X-User-Id
   │ Sentinel 网关限流：/api/order/create QPS ≤ 500
   │ 路由 lb://mall-order，StripPrefix=1
   ▼
[mall-order] Filter: Header → MDC.traceId / UserContext
   │ OrderController.create → @Valid 校验
   │ OrderBizComponent.createOrder
   │   ├─ RedisDao.consumeSubmitToken                       （防重复提交）
   │   ├─ ProductClient.deductStock ── Feign + FeignContextInterceptor(X-Trace-Id, X-User-Id)
   │   │        ▼
   │   │   [mall-product] StockDeductUnit.deduct → product_db（t_stock_deduct_log + t_product）
   │   ├─ OrderCreateUnit.createWithMessage → order_db（t_order + t_order_item + t_local_message）
   │   └─ afterCommit → LocalMessageRelay → RocketMQ（ORDER_CREATED、延迟 ORDER_TIMEOUT_CHECK）
   ▼
 返回 Result<OrderVO>
异步：RocketMQ → 积分/通知消费者；30 分钟后 → 超时取消 → STOCK_RESTORE → mall-product
定时：XXL-Job LocalMessageRelayJob（每分钟）· OrderReconcileJob（每日 02:00，分片广播）
旁路：SkyWalking 按 TraceId 串起 gateway → order → product → MySQL → RocketMQ
```

---

## 6. 常见坑

| # | 坑 | 后果 | 正确做法 |
|---|---|---|---|
| 1 | 为拆而拆，一个人维护 8 个服务 | 一个需求改 5 个服务、发 5 次版 | 先模块化单体，按团队和业务边界拆 |
| 2 | 多个服务共用一个库、跨服务直接查别人的表 | 「分布式单体」：耦合没减少，复杂度却上来了 | 数据归属唯一，跨服务只走接口/消息 |
| 3 | Feign 不设超时或超时过长 | 下游变慢 → 上游线程池打满 → 雪崩 | 显式设置超时 + 熔断 |
| 4 | 对非幂等写接口开启重试 | 重复扣库存 | 写接口要么幂等要么不重试 |
| 5 | 把超时当失败处理 | 对方实际成功，本地认为失败 → 数据不一致 | 超时 = 未知，走补偿 + 对账 |
| 6 | 在 `@Transactional` 内部调用远程服务 | 本地事务回滚不了远程操作；长事务占连接 | 远程调用放事务外，事务只包本地写 |
| 7 | fallback 返回「成功」 | 写操作假成功 | 写操作 fallback 返回失败 |
| 8 | `@Scheduled` 在多实例上执行 | 任务重复执行 | XXL-Job 或 ShedLock |
| 9 | 异步线程丢失 TraceId / 用户信息 | 日志串不起来、下游拿不到用户 | 线程池 `TaskDecorator` 拷贝上下文 |
| 10 | Sentinel 规则只配在控制台 | 应用重启规则丢失 | 规则持久化到 Nacos |
| 11 | 网关信任客户端传入的 `X-User-Id` | 越权 | 网关先删除再写入 |
| 12 | Seata AT 下有不走全局事务的代码修改同一张表 | 回滚时镜像校验失败，需人工处理 | 所有写入口都纳入全局事务，或换方案 |
| 13 | 雪花算法的 workerId 配置写死 | 多实例 ID 冲突 | 启动时动态分配并校验唯一 |
| 14 | api 模块引入了 service 的依赖或 PO | 调用方被迫引入数据库驱动等 | api 只放接口与 DTO |

---

## 7. 高级视角

### 7.1 服务治理清单

| 维度 | 要点 |
|---|---|
| 超时 | 全链路超时预算：网关 10s > 订单 5s > 商品 2s；越靠下游越短 |
| 重试 | 只在幂等接口、只在入口层重试一次，避免「重试风暴」（3 层 × 3 次 = 27 倍流量） |
| 隔离 | 不同下游用不同线程池/信号量（舱壁模式），一个下游故障不拖垮全部 |
| 限流 | 入口限流（网关）+ 服务自我保护（Sentinel） |
| 降级 | 非核心功能（推荐、积分展示）可一键关闭（Nacos 开关） |
| 容量 | 每个服务知道自己的单机 QPS 上限与依赖关系 |

### 7.2 一致性的工程方法论

1. **先问能不能不分布**：把强一致需求放到一个服务、一个库内（如库存预扣与订单同属交易域）。
2. **定义中间态**：「库存已扣、订单未建」是合法的中间态，有明确的超时与补偿规则。
3. **所有操作幂等**：扣减、回补、消息消费、回调都必须能安全重复。
4. **可补偿 + 可对账**：补偿解决「已知失败」，对账解决「未知失败」。**对账是最终一致性的最后一道防线**。
5. **可观测**：每个不一致都能被发现（告警）、被定位（TraceId + 流水表）、被修复（重放/人工工具）。

### 7.3 Service Mesh 与云原生

- Istio/Envoy 把服务发现、负载均衡、熔断、mTLS、灰度从 SDK 下沉到 Sidecar，多语言统一治理。
- 代价：每个 Pod 多一个代理、延迟增加、运维复杂度高。
- 国内大量团队仍以 Spring Cloud Alibaba 为主；了解 Mesh 的思想即可，按团队规模选择。

### 7.4 拆分演进的反模式

| 反模式 | 表现 |
|---|---|
| 分布式单体 | 服务必须一起发布，共享库，同步调用链很深 |
| 纳米服务 | 一个 CRUD 一个服务，调用链 10 跳 |
| 链式同步调用 | A → B → C → D 全同步，可用性 = 各服务可用性相乘（0.99⁴ ≈ 0.96） |
| 共享 api 大包 | 所有服务的 DTO 放在一个 common 包，任何改动全员升级 |

---

## 8. 小练习

1. 用 docker-compose 起 Nacos（见第 12 章），把 mini-mall 拆成 `mall-order` 和 `mall-product` 两个服务，完成服务注册并在 Nacos 控制台看到实例。
2. 实现 `ProductClient` 与 `FeignContextInterceptor`，在 product 服务打印日志，验证 TraceId 与 userId 透传成功。
3. 在 product 的扣库存接口里 `Thread.sleep(5000)`，观察 order 侧超时异常；接入 Sentinel 配置慢调用熔断，观察熔断后快速失败与恢复。
4. 在 `OrderCreateUnit.createWithMessage` 末尾抛异常，验证补偿回补了库存；再让补偿也失败，运行对账任务验证能修复。
5. 部署两个 `mall-product` 实例，配置 `orderReconcileJob` 为分片广播，验证两个实例各自处理了一半数据。
6. 为 `SnowflakeIdGenerator` 写单测：多线程生成 100 万个 ID 无重复；模拟时钟回拨（提示：把取时间抽成可注入的 `LongSupplier`）。
7. 思考题：如果把「扣库存」改为下单时只在 Redis 预扣（第 9 章），真正的数据库扣减放到支付成功后异步执行，一致性方案需要怎样调整？
