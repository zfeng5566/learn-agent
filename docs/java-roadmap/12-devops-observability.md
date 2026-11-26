# 第 12 章 部署、监控与线上排查

> [← 总纲](./00-outline.md) | [上一章：微服务与分布式](./11-microservices.md) | [下一章：高级工程师之路](./13-senior-engineer.md)

---

## 1. 本章地图

```
 代码 ──▶ CI（编译/单测/扫描）──▶ 镜像仓库 ──▶ CD（K8s 滚动发布）──▶ 线上运行
                                                                    │
                    ┌───────────────────────────────────────────────┤ 可观测性三支柱
                    ▼                       ▼                       ▼
             日志 Logs（ELK/EFK）    指标 Metrics（Prometheus）  链路 Traces（SkyWalking）
                    └───────────────────────┼───────────────────────┘
                                            ▼
                                 告警 → 排查 SOP → Arthas → 修复 / 回滚
```

| 问题 | 小节 |
|---|---|
| 服务端怎么部署，和前端部署有什么不同 | 2、3.1 |
| Linux、Docker、K8s 必备知识 | 3.2 ~ 3.5 |
| CI/CD、日志、监控、链路追踪 | 3.6 ~ 3.9 |
| 线上出问题怎么查：各类故障的 SOP | 4 |
| mini-mall：Dockerfile、K8s YAML、Prometheus、CPU 飙高演练 | 5 |
| 发布规范、稳定性建设 | 7 |

---

## 2. 前端类比

### 2.1 部署形态对比

```
前端：                                           服务端：
npm run build → dist/（静态文件）                  mvn package → app.jar → Docker 镜像
   │                                                  │
   ▼                                                  ▼
上传 OSS/CDN（无状态、全球缓存）                   K8s 启动 N 个 Pod（常驻进程，占 CPU/内存）
   │                                                  │
用户浏览器下载执行（出错只影响该用户）               所有用户请求共享这些进程（出错影响所有人）
回滚：切换 index.html 指向旧版本（秒级）           回滚：重新部署旧镜像（分钟级，有数据兼容问题）
```

| 维度 | 前端静态资源 | Java 服务 |
|---|---|---|
| 产物 | HTML/JS/CSS，带 hash 的文件名 | jar → Docker 镜像（带版本 tag） |
| 运行在哪 | 用户浏览器 | 自己的服务器，**你为它的 CPU/内存/稳定性负责** |
| 有状态吗 | 无 | 进程内有连接池、缓存、线程；外部有数据库 |
| 发布影响 | 新用户拿新版本，老页面继续用旧 JS | 进程重启，**正在处理的请求可能中断** → 优雅停机 |
| 版本共存 | 天然共存（hash 文件名） | 滚动发布期间新旧版本同时在线 → 接口/表/消息必须兼容 |
| 出问题的信号 | Sentry 报错、用户反馈 | 告警：错误率、RT、CPU、GC、连接池 |
| 排查手段 | DevTools、Source Map | 日志、指标、链路、jstack、Arthas |

### 2.2 可观测性对照

| 前端 | 服务端 |
|---|---|
| `console.log` / Sentry breadcrumb | 结构化日志 + ELK |
| Web Vitals、性能监控 | Prometheus 指标（RED、JVM） |
| Sentry 的 trace / 请求瀑布图 | SkyWalking 链路 |
| Chrome Performance 面板 | Arthas `profiler` 火焰图 |
| Memory 面板 heap snapshot | `jmap` 堆转储 + MAT |
| 网络面板看哪个请求慢 | Arthas `trace` 看哪个方法慢 |

---

## 3. 核心概念

### 3.1 服务端部署全景

```
 用户 ─▶ DNS ─▶ CDN（静态资源）
           └──▶ SLB/Ingress（HTTPS 卸载）─▶ Gateway Pod ×2 ─▶ Order Pod ×4 ─▶ MySQL 主从
                                                       └──▶ Product Pod ×3 ─▶ Redis 集群
                                                                         ─▶ RocketMQ 集群
 旁路：Nacos · XXL-Job Admin · Prometheus · Grafana · ES/Kibana · SkyWalking OAP
```

### 3.2 Linux 常用命令

**资源查看**：

| 命令 | 作用 | 关注点 |
|---|---|---|
| `top` / `htop` | 进程 CPU、内存、负载 | `load average` 三个值（1/5/15 分钟）> CPU 核数说明排队；`%wa` 高说明 IO 等待 |
| `top -Hp <pid>` | 某进程的**线程**级 CPU | 找出最耗 CPU 的线程 ID |
| `free -h` | 内存 | 看 `available` 而不是 `free`（buff/cache 可回收） |
| `df -h` / `du -sh *` | 磁盘使用 | 日志打满磁盘是高频事故 |
| `iostat -x 1` | 磁盘 IO | `%util` 接近 100% 说明磁盘瓶颈 |
| `vmstat 1` | CPU/内存/上下文切换 | `cs` 过高说明线程切换频繁 |

**网络**：

| 命令 | 作用 |
|---|---|
| `ss -lntp` | 查看监听端口及进程（比 `netstat` 快） |
| `ss -ant \| awk '{print $1}' \| sort \| uniq -c` | 统计各 TCP 状态数量，`TIME_WAIT`/`CLOSE_WAIT` 过多要警惕 |
| `netstat -anp \| grep 3306 \| wc -l` | 到 MySQL 的连接数 |
| `lsof -i :8080` | 谁占用了端口 |
| `lsof -p <pid> \| wc -l` | 进程打开的文件句柄数（`Too many open files`） |
| `curl -w '%{time_total}\n' -o /dev/null -s URL` | 测接口耗时 |
| `telnet host port` / `nc -zv host port` | 端口连通性 |

**日志检索**：

```bash
# 实时追踪日志并过滤 ERROR
tail -f app.log | grep --line-buffered ERROR

# 按 TraceId 查询完整请求日志（含前后 5 行上下文）
grep -C 5 '7f3a9c2e' app.log

# 统计近一小时各异常出现次数（假设日志行内含异常类名）
grep 'Exception' app.log | grep -oE '[A-Za-z.]+Exception' | sort | uniq -c | sort -rn | head

# 统计接口耗时 Top 10（假设日志格式：... uri=/order/create cost=123ms）
grep 'cost=' access.log | awk -F'cost=' '{split($2,a,"ms"); print a[1], $0}' | sort -rn | head -10

# 按时间段截取日志
sed -n '/2026-11-26 14:00/,/2026-11-26 14:10/p' app.log > slice.log

# 压缩日志直接检索
zgrep 'orderNo=M20261126' app.log.2026-11-25.gz
```

### 3.3 Docker

```
镜像 Image（只读、分层）           容器 Container（镜像 + 可写层 + 进程）
┌──────────────────────┐           ┌──────────────────────┐
│ app 代码层 (2MB)     │ ◀ 常变     │ 可写层（运行时写入）  │
│ 依赖 jar 层 (80MB)   │           ├──────────────────────┤
│ JRE 层 (190MB)       │           │ 只读镜像层（共享）    │
│ OS 基础层 (30MB)     │ ◀ 不变     └──────────────────────┘
└──────────────────────┘
```

| 概念 | 前端类比 | 说明 |
|---|---|---|
| Dockerfile | 构建脚本 | 每条指令生成一层 |
| 镜像分层缓存 | `node_modules` 缓存 / `package.json` 先 COPY 再 install | **变化少的放前面**，代码改动只重建最后一层 |
| 多阶段构建 | 构建用 node 镜像，产物拷到 nginx 镜像 | 编译用 JDK+Maven，运行只要 JRE |
| 容器 | 一个隔离的进程 | 本质是 Linux namespace + cgroups，不是虚拟机 |

**JVM 与容器**：

| 问题 | 说明 | 做法 |
|---|---|---|
| JVM 识别容器内存限制 | JDK 8u191+/10+ 默认开启 `UseContainerSupport` | 不要写死 `-Xmx`，用 `-XX:MaxRAMPercentage=75.0` |
| 为什么不是 100% | 堆外还有元空间、线程栈、直接内存、JIT 代码缓存 | 堆占容器内存 60%~75% |
| 容器被 OOMKilled | 进程总内存超过 limit，被内核杀死，**没有 Java OOM 日志** | 看 `kubectl describe pod` 的 `OOMKilled`；调整比例或 limit |
| CPU 识别 | JVM 根据 CPU limit 决定 GC 线程数、`availableProcessors` | limit 太小（< 1 核）会导致 GC 与 ForkJoinPool 并行度过低 |
| PID 1 信号 | `ENTRYPOINT java ...`（exec 形式）让 Java 成为 PID 1，能收到 SIGTERM | 不要用 shell 形式 `sh -c`，否则优雅停机失效 |

### 3.4 docker-compose：本地拉起依赖

```yaml
# docker-compose.yml：mini-mall 本地开发依赖（仅用于开发环境，账号密码勿用于生产）
services:
  mysql:
    image: mysql:8.0.36
    environment:
      MYSQL_ROOT_PASSWORD: root123
      MYSQL_DATABASE: mini_mall
      TZ: Asia/Shanghai
    command: --character-set-server=utf8mb4 --collation-server=utf8mb4_0900_ai_ci
    ports: ["3306:3306"]
    volumes:
      - mysql-data:/var/lib/mysql
      - ./sql:/docker-entrypoint-initdb.d      # 首次启动自动执行建表脚本
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-proot123"]
      interval: 10s
      retries: 5

  redis:
    image: redis:7.2
    command: redis-server --appendonly yes
    ports: ["6379:6379"]

  rmq-namesrv:
    image: apache/rocketmq:5.3.1
    command: sh mqnamesrv
    ports: ["9876:9876"]

  rmq-broker:
    image: apache/rocketmq:5.3.1
    command: sh mqbroker -n rmq-namesrv:9876 --enable-proxy
    environment:
      JAVA_OPT_EXT: "-Xms512m -Xmx512m"
    ports: ["10911:10911", "8081:8081"]
    depends_on: [rmq-namesrv]

  nacos:
    image: nacos/nacos-server:v2.4.3
    environment:
      MODE: standalone
    ports: ["8848:8848", "9848:9848"]   # 9848 为 2.x gRPC 端口，客户端必须能访问

volumes:
  mysql-data:
```

```bash
docker compose up -d           # 后台启动
docker compose ps              # 查看状态
docker compose logs -f broker  # 查看日志
docker compose down            # 停止（加 -v 同时删除数据卷）
```

> RocketMQ Broker 在容器中默认向 NameServer 注册容器 IP，宿主机上的应用可能连不上；本地开发需在 `broker.conf` 设置 `brokerIP1=宿主机IP`。

### 3.5 Kubernetes 基础

```
              Ingress（域名/路径 → Service，类似 Nginx 路由）
                 │
              Service（稳定的虚拟 IP + DNS 名：mall-order.mall.svc，负载均衡到 Pod）
                 │ label selector: app=mall-order
     ┌───────────┼───────────┐
    Pod         Pod         Pod      ← 最小调度单元：一个或多个容器 + 共享网络/存储
     ▲
 Deployment（声明期望副本数与镜像版本，负责滚动更新与回滚）
 ConfigMap / Secret（配置与密钥，以环境变量或文件注入）
```

| 对象 | 作用 | 前端类比 |
|---|---|---|
| Pod | 运行容器的最小单元，IP 不固定，随时可能重建 | 一个浏览器标签页 |
| Deployment | 管理一组同版本 Pod，滚动发布 | 发布平台的「版本」 |
| Service | 稳定访问入口 | 固定域名 |
| Ingress | 七层路由 | Nginx `location` |
| ConfigMap/Secret | 配置注入 | `.env` |
| HPA | 按 CPU/自定义指标自动扩缩容 | — |

**探针与 Actuator**：

| 探针 | 失败后果 | 对接 Actuator | 应检查什么 |
|---|---|---|---|
| `startupProbe` | 启动期间不进行其他探测，超时则重启 | `/actuator/health/liveness` | 给 Spring 启动留足时间（30~120s） |
| `livenessProbe` 存活 | **重启容器** | `/actuator/health/liveness` | 只检查进程自身是否卡死，**不要包含数据库、Redis** |
| `readinessProbe` 就绪 | 从 Service 摘除，不再接流量 | `/actuator/health/readiness` | 是否可以接流量（启动完成、未处于停机中） |

> 为什么 liveness 不能检查数据库：数据库抖动 → 所有 Pod liveness 失败 → 全部重启 → 重启风暴，故障被放大。

**滚动发布与优雅停机**：

```
滚动发布（maxSurge=1, maxUnavailable=0）：
 v1 v1 v1 v1  →  v1 v1 v1 v1 v2(就绪?)  →  v1 v1 v1 v2  →  ...  →  v2 v2 v2 v2

单个 Pod 停机时序：
 ① K8s 把 Pod 标记 Terminating，同时：
    a. 从 Service Endpoints 中移除（异步传播到各节点 iptables/ipvs，需要几秒）
    b. 执行 preStop（sleep 10s：等待 a 传播完成，避免新请求打到正在关闭的 Pod）
 ② preStop 结束后发送 SIGTERM
 ③ Spring Boot 优雅停机：停止接收新请求，等待进行中的请求完成（最多 timeout-per-shutdown-phase）
    → 关闭线程池、MQ 消费者、从 Nacos 注销、关闭连接池
 ④ 超过 terminationGracePeriodSeconds 仍未退出 → SIGKILL
```

```yaml
# application.yml 优雅停机与探针
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
management:
  endpoint:
    health:
      probes:
        enabled: true          # 暴露 /actuator/health/liveness 与 /readiness（K8s 环境下自动开启）
```

> 微服务额外注意：Nacos 注册的实例要在停机时**先注销**，否则其他服务的 LoadBalancer 仍会把请求发过来。Spring Cloud Alibaba 在 Spring 容器关闭时会自动注销，但调用方缓存最长 30s 左右才更新——所以调用方要有重试，或在 preStop 中先调用 Nacos 下线接口。

### 3.6 CI/CD 流水线

| 阶段 | 前端流水线 | Java 流水线 |
|---|---|---|
| 依赖 | `pnpm install`（缓存 store） | `mvn -B dependency:go-offline`（缓存 `~/.m2`） |
| 检查 | ESLint、tsc | Checkstyle / Spotless、编译 |
| 测试 | Vitest | `mvn test`（JUnit + Jacoco 覆盖率） |
| 扫描 | npm audit | SonarQube、OWASP Dependency-Check |
| 构建 | `vite build` | `mvn package` → `docker build` → push 镜像 |
| 部署 | 上传 CDN、刷新缓存 | 更新 K8s Deployment 镜像 tag（`kubectl set image` / Helm / ArgoCD） |
| 验证 | 冒烟 | 冒烟用例、观察指标 |

```yaml
# .gitlab-ci.yml（mall-order 精简版）
stages: [test, build, deploy]

variables:
  MAVEN_OPTS: "-Dmaven.repo.local=$CI_PROJECT_DIR/.m2/repository"
  IMAGE: registry.example.com/mall/mall-order:$CI_COMMIT_SHORT_SHA   # 用 commit SHA 做 tag，可追溯

cache:
  key: maven-$CI_COMMIT_REF_SLUG
  paths: [.m2/repository]

test:
  stage: test
  image: maven:3.9-eclipse-temurin-21
  script:
    - mvn -B -pl mall-order/mall-order-service -am verify     # 编译 + 单测 + 静态检查
  artifacts:
    reports:
      junit: "**/target/surefire-reports/TEST-*.xml"

build-image:
  stage: build
  image: docker:27
  services: [docker:27-dind]
  script:
    - docker build -t $IMAGE -f mall-order/Dockerfile .
    - docker push $IMAGE
  only: [main, /^release\/.*$/]

deploy-test:
  stage: deploy
  image: bitnami/kubectl:1.30
  script:
    - kubectl -n mall-test set image deployment/mall-order app=$IMAGE
    - kubectl -n mall-test rollout status deployment/mall-order --timeout=300s   # 等待滚动完成，失败则流水线失败
  environment: test
  only: [main]

deploy-prod:
  stage: deploy
  image: bitnami/kubectl:1.30
  script:
    - kubectl -n mall-prod set image deployment/mall-order app=$IMAGE
    - kubectl -n mall-prod rollout status deployment/mall-order --timeout=600s
  environment: production
  when: manual                  # 生产需人工确认
  only: [/^release\/.*$/]
```

> 镜像 tag **不要用 latest**：无法追溯、无法回滚。Jenkins 用 Jenkinsfile 声明同样的 stage 即可，思路一致。

### 3.7 日志体系

```
应用（Logback 输出 JSON 到 stdout 或文件）
   │
   ▼
Filebeat / Fluent Bit（每个节点 DaemonSet 采集）
   │
   ▼
（可选）Kafka 缓冲 ─▶ Logstash（解析、脱敏）─▶ Elasticsearch ─▶ Kibana 检索
                              EFK：Fluentd 替换 Logstash
```

**结构化日志**：

```xml
<!-- logback-spring.xml 片段：使用 logstash-logback-encoder 输出 JSON -->
<appender name="JSON_STDOUT" class="ch.qos.logback.core.ConsoleAppender">
    <encoder class="net.logstash.logback.encoder.LogstashEncoder">
        <includeMdcKeyName>traceId</includeMdcKeyName>
        <includeMdcKeyName>userId</includeMdcKeyName>
        <customFields>{"app":"mall-order"}</customFields>
    </encoder>
</appender>
```

输出：

```json
{"@timestamp":"2026-11-26T14:03:12.481+08:00","level":"INFO","logger_name":"c.e.m.biz.OrderBizComponent",
 "thread_name":"http-nio-8080-exec-12","message":"下单成功, orderNo=M20261126000123",
 "traceId":"7f3a9c2e41d0","userId":"1001","app":"mall-order"}
```

**日志规范**：

| 规范 | 说明 |
|---|---|
| 用占位符 | `log.info("orderNo={}", no)`，不要字符串拼接 |
| 异常打完整堆栈 | `log.error("下单失败, orderNo={}", no, e)`——异常对象放最后一个参数 |
| 关键节点打业务键 | orderNo、userId，方便检索 |
| 级别 | ERROR 需要人处理；WARN 可自愈的异常；INFO 关键业务节点；DEBUG 默认关闭 |
| 脱敏 | 手机号、身份证、token 不得明文 |
| 不在循环里打 INFO | 日志量爆炸，磁盘与 ES 成本飙升 |

**TraceId 串联**：入口 Filter 生成或读取 `X-Trace-Id` 写入 MDC，Feign 拦截器透传（第 11 章），MQ 消息属性透传，异步线程池用 `TaskDecorator` 拷贝 MDC。接入 SkyWalking 时直接使用其 TraceId。

```java
/**
 * TraceId 过滤器：请求进入时写入 MDC，响应头回写 TraceId 方便前端/用户反馈时提供。
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceIdFilter extends OncePerRequestFilter {

    /** MDC 中的 TraceId 键名 */
    private static final String MDC_TRACE_ID = "traceId";

    /**
     * 为每个请求设置 TraceId，请求结束后清理，避免线程复用导致串号。
     *
     * @param request  HTTP 请求
     * @param response HTTP 响应
     * @param chain    过滤器链
     */
    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String traceId = request.getHeader("X-Trace-Id");
        if (traceId == null || traceId.isBlank()) {
            traceId = UUID.randomUUID().toString().replace("-", "").substring(0, 16);
        }
        MDC.put(MDC_TRACE_ID, traceId);
        response.setHeader("X-Trace-Id", traceId);
        try {
            chain.doFilter(request, response);
        } finally {
            // 必须清理：Tomcat 线程是复用的
            MDC.remove(MDC_TRACE_ID);
        }
    }
}
```

### 3.8 监控：Actuator + Micrometer + Prometheus + Grafana

```
Spring Boot App
 ├─ Actuator：暴露 /actuator/health、/actuator/prometheus
 └─ Micrometer：指标门面（类似 SLF4J 之于日志），自动采集 JVM、Tomcat、HikariCP、HTTP 指标
          ▲ 每 15s 拉取（Pull 模型）
 Prometheus（时序库 + PromQL + 告警规则）──▶ Alertmanager ──▶ 钉钉/企微/电话
          │
 Grafana（看板）
```

**两套方法论**：

| 方法 | 适用对象 | 指标 |
|---|---|---|
| **RED** | 服务/接口 | **R**ate 请求速率、**E**rrors 错误率、**D**uration 耗时分布（P99） |
| **USE** | 资源（CPU、内存、磁盘、连接池、线程池） | **U**tilization 使用率、**S**aturation 饱和度（排队）、**E**rrors 错误 |

**JVM 关键指标**：

| 指标 | Micrometer 名称 | 关注点 |
|---|---|---|
| 堆使用 | `jvm_memory_used_bytes{area="heap"}` | Full GC 后仍居高不下 → 泄漏 |
| GC 停顿 | `jvm_gc_pause_seconds_*` | P99 停顿、Full GC 频率 |
| 线程数 | `jvm_threads_live_threads`、`jvm_threads_states_threads` | BLOCKED 线程数突增 |
| CPU | `process_cpu_usage`、`system_cpu_usage` | — |
| Tomcat | `tomcat_threads_busy_threads` / `tomcat_threads_config_max_threads` | 接近 1 → 线程池打满 |
| 连接池 | `hikaricp_connections_active`、`hikaricp_connections_pending` | pending > 0 持续 → 连接池耗尽 |
| HTTP | `http_server_requests_seconds_*` | RED 的数据源 |

**常用 PromQL**：

```promql
# QPS（按接口）
sum(rate(http_server_requests_seconds_count{application="mall-order"}[1m])) by (uri)

# 错误率（5xx 占比）
sum(rate(http_server_requests_seconds_count{application="mall-order",status=~"5.."}[5m]))
  / sum(rate(http_server_requests_seconds_count{application="mall-order"}[5m]))

# P99 耗时（需开启 histogram）
histogram_quantile(0.99, sum(rate(http_server_requests_seconds_bucket{application="mall-order"}[5m])) by (le, uri))

# 老年代使用率（G1）
jvm_memory_used_bytes{area="heap",id="G1 Old Gen"} / jvm_memory_max_bytes{area="heap",id="G1 Old Gen"}
```

**告警设计原则**：

| 原则 | 说明 |
|---|---|
| 告警要可行动 | 每条告警都有对应的处理手册；不需要处理的告警就是噪音 |
| 优先告「症状」 | 错误率、P99、订单量骤降（用户可感知）优先于「CPU 70%」（原因） |
| 分级 | P0 电话（下单失败率 > 5%）、P1 即时消息、P2 日报 |
| 持续时间 | `for: 3m` 避免抖动；但核心链路不宜太长 |
| 业务指标 | 下单量同比/环比骤降往往比技术指标更早发现问题 |

### 3.9 链路追踪：SkyWalking

已在第 11 章讲过原理。部署要点：

```bash
# 启动参数挂载 Agent（镜像中预置 agent 目录）
java -javaagent:/skywalking/agent/skywalking-agent.jar \
     -Dskywalking.agent.service_name=mall-order \
     -Dskywalking.collector.backend_service=oap.observability:11800 \
     -jar app.jar
```

使用场景：

- **拓扑图**：一眼看出调用关系和哪条边红了。
- **慢 Trace**：找到一个慢请求，展开看时间花在哪个 Span（SQL？Feign？Redis？）。
- **Trace ↔ 日志**：日志中打印 `%tid`，从 Trace 跳到 Kibana 查同一 TraceId 的日志。

---

## 4. 原理深挖：线上问题排查 SOP

> 总原则：**先止血，再定位，后根治**。止血手段：回滚、扩容、限流、降级、重启（重启前先保留现场：`jstack`、`jmap`）。

### 4.0 排查工具箱

| 工具 | 用途 | 常用命令 |
|---|---|---|
| `jps -l` | 列出 Java 进程 | — |
| `jstack <pid>` | 线程堆栈 | `jstack <pid> > stack.txt` |
| `jmap` | 堆信息、堆转储 | `jmap -histo:live <pid> \| head -30`；`jmap -dump:live,format=b,file=heap.hprof <pid>` |
| `jstat` | GC 统计 | `jstat -gcutil <pid> 1000 10` |
| `jcmd` | 万能命令（推荐替代上面几个） | `jcmd <pid> Thread.print`、`GC.heap_dump`、`VM.flags` |
| **Arthas** | 在线诊断：不重启看方法耗时、入参返回值、热更新 | `dashboard`、`thread`、`trace`、`watch`、`profiler` |
| MAT / JProfiler | 分析 heap dump | Dominator Tree、Leak Suspects |
| async-profiler | CPU/内存火焰图 | Arthas 内置 `profiler` |

> ⚠️ `jmap -dump` 和 `jmap -histo:live` 会触发 **STW**（大堆可能停顿数秒到数十秒）：先把该实例从流量中摘除再执行。

**Arthas 速查**：

```bash
# 启动并 attach 到目标进程（容器中：kubectl exec -it <pod> -- bash）
curl -O https://arthas.aliyun.com/arthas-boot.jar && java -jar arthas-boot.jar

dashboard                                            # 总览：线程 CPU、内存、GC
thread -n 3                                          # 最忙的 3 个线程及堆栈
thread -b                                            # 找出持有锁并阻塞其他线程的线程（死锁）
thread --state BLOCKED                               # 所有 BLOCKED 线程
trace com.example.mall.biz.OrderBizComponent createOrder '#cost > 200'   # 方法内部各调用耗时，只看 >200ms
watch com.example.mall.dao.OrderDao getByOrderNo '{params, returnObj, throwExp}' -x 2   # 看入参、返回、异常
stack com.example.mall.dao.ProductDao deductStock  # 谁调用了这个方法
tt -t com.example.mall.biz.OrderBizComponent createOrder   # 时光隧道：记录调用，事后回放
profiler start --event cpu ; profiler stop --format html  # 生成 CPU 火焰图
ognl '@com.example.mall.common.MqConstants@TOPIC_ORDER'  # 查看静态字段
vmtool --action getInstances --className com.zaxxer.hikari.HikariDataSource --express 'instances[0].getHikariPoolMXBean().getActiveConnections()'
```

### 4.1 接口变慢

```
告警：/order/create P99 从 80ms → 2s
 │
 ├─ ① 范围：所有接口都慢？（→ 资源问题：CPU/GC/连接池）
 │          还是单个接口慢？（→ 该接口的依赖）
 │          所有实例都慢？还是单个实例？（→ 单机问题：宿主机、GC）
 ├─ ② 链路：SkyWalking 找慢 Trace，看时间花在哪个 Span
 │          ├─ SQL Span 慢 → 4.7 慢 SQL
 │          ├─ Feign Span 慢 → 去下游服务继续查
 │          ├─ Redis Span 慢 → 4.8
 │          └─ 无明显慢 Span，但总时间长 → 本进程内：锁等待、线程池排队、GC
 ├─ ③ 进程内：Arthas trace 逐层下钻
 │          trace com.example.mall.biz.OrderBizComponent createOrder '#cost > 500'
 └─ ④ 关联变更：最近有无发布、配置变更、数据量突增、大促流量
```

### 4.2 CPU 飙高

```
① top                    → 找到 CPU 高的 Java 进程 PID（如 12345）
② top -Hp 12345          → 找到 CPU 高的线程 TID（十进制，如 12408）
③ printf '%x\n' 12408    → 转十六进制 307c
④ jstack 12345 | grep -A 30 'nid=0x307c'   → 定位线程堆栈
   或直接：Arthas thread -n 3
⑤ 判断线程类型：
   ├─ 业务线程（http-nio-8080-exec-*）→ 死循环、正则回溯、大对象序列化、大集合计算
   ├─ GC 线程（GC Thread#0、G1 Conc#0）→ 不是 CPU 问题，是内存问题 → 4.3 / 4.4
   └─ C2 CompilerThread → JIT 编译，通常发布后短时间内正常
⑥ 连续采集 3~5 次（间隔 5s）：同一位置反复出现才是热点
⑦ 火焰图：profiler start → 等 30s → profiler stop，看最宽的「平顶」
```

### 4.3 内存泄漏 / OOM

| OOM 类型 | 原因 | 方向 |
|---|---|---|
| `Java heap space` | 堆不够：泄漏或一次加载过多数据 | heap dump 分析 |
| `GC overhead limit exceeded` | GC 时间占 98% 以上却回收不到 2% | 同上，通常是泄漏 |
| `Metaspace` | 类太多：动态代理、Groovy 脚本、反复创建 ClassLoader | 检查动态生成类 |
| `Direct buffer memory` | 堆外内存：Netty、NIO | `-XX:MaxDirectMemorySize`，检查 ByteBuf 释放 |
| `unable to create native thread` | 线程数超限 | 检查线程池是否无界、是否每次请求 new Thread |
| 容器 OOMKilled（无 Java 日志） | 进程总内存 > 容器 limit | 降低 `MaxRAMPercentage` 或提高 limit；查堆外 |

```
预防：启动参数必须有
  -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/dumps/   （挂持久卷，否则 Pod 重启就没了）

排查：
① 监控：老年代使用率呈「锯齿上升」，每次 Full GC 后的低点越来越高 → 泄漏
② jmap -histo:live <pid> | head -30   → 哪类对象实例最多（快速看）
③ jcmd <pid> GC.heap_dump /dumps/heap.hprof   （先摘流量）
④ MAT 打开 → Leak Suspects / Dominator Tree → 看谁持有大量对象 → Path to GC Roots
⑤ 常见元凶：
   ├─ static Map 当缓存只增不删
   ├─ ThreadLocal 未 remove（线程池线程长期存活）
   ├─ 一次查询全表（第 3 章：百万订单一次加载）
   ├─ 无界队列（LinkedBlockingQueue 默认 Integer.MAX_VALUE）堆积任务
   └─ 监听器/回调注册了不注销
```

### 4.4 频繁 Full GC

```
① jstat -gcutil <pid> 1000 20
     S0  S1   E     O     M    YGC  YGCT  FGC  FGCT
     0   0   45   98.7  95.1   812  9.4   156  220.3     ← O(老年代) 接近 100%，FGC 持续增长
② GC 日志：-Xlog:gc*:file=/logs/gc.log:time,uptime:filecount=5,filesize=50m
   看每次 Full GC 的原因（Allocation Failure / Metadata GC Threshold / System.gc()）
③ 分类处理：
   ├─ Full GC 后老年代降不下来 → 内存泄漏 → 按 4.3
   ├─ Full GC 后能降下来，但很快又满 → 对象晋升过快：大对象、Survivor 太小、短期大批量数据 → 调代大小或改代码
   ├─ Metaspace 触发 → 调 MaxMetaspaceSize / 查动态类
   └─ System.gc() 触发 → 代码或 RMI 主动调用，-XX:+DisableExplicitGC（注意 NIO 直接内存回收依赖它）
```

### 4.5 线程池打满

```
现象：RejectedExecutionException；或接口大量超时但 CPU 不高
① 监控：tomcat_threads_busy_threads 达到 max（默认 200）
② Arthas thread --state WAITING / TIMED_WAITING，或 jstack 统计线程状态：
   jstack <pid> | grep 'java.lang.Thread.State' | sort | uniq -c
③ 看大多数业务线程卡在哪：
   ├─ SocketInputStream.read / feign → 下游慢，且无超时或超时过长
   ├─ HikariPool.getConnection → 连接池耗尽 → 4.6
   ├─ BLOCKED on 某把锁 → 锁竞争，thread -b 找持有者
   └─ LockSupport.park + CompletableFuture.get → 异步任务在等另一个已满的线程池（池间互相等待，死锁）
④ 止血：扩容、对下游熔断降级、调小超时
⑤ 根治：所有外部调用设超时；不同下游隔离线程池；自定义线程池要有界并配拒绝策略
```

### 4.6 数据库连接池耗尽

```
现象：SQLTransientConnectionException: HikariPool-1 - Connection is not available, request timed out after 30000ms
① 指标：hikaricp_connections_active == max，pending > 0
② 原因：
   ├─ 慢 SQL：每个连接被占用很久 → 4.7
   ├─ 长事务：@Transactional 方法里调用了远程接口/MQ/sleep → 连接一直被持有
   ├─ 连接泄漏：手动获取 Connection 未关闭 → 开启 leakDetectionThreshold=60000 打印泄漏堆栈
   └─ 池太小：maxPoolSize 远小于并发需求（但盲目调大会压垮数据库）
③ 数据库侧：SHOW PROCESSLIST; SELECT * FROM information_schema.innodb_trx ORDER BY trx_started; 找长事务
```

> 连接池大小经验：`connections = CPU 核数 × 2 + 有效磁盘数`（HikariCP 推荐公式，对数据库端而言）；应用侧 × 实例数不能超过数据库 `max_connections`。

### 4.7 慢 SQL

```
① 来源：MySQL 慢查询日志（long_query_time=1）、SkyWalking SQL Span、Druid/p6spy 监控
② EXPLAIN 看执行计划（第 8 章）：type=ALL 全表扫描、key=NULL、rows 巨大、Using filesort / Using temporary
③ 常见原因：缺索引、索引失效（函数、隐式类型转换、前导 %、OR）、深分页、大事务锁等待
④ 锁等待：SELECT * FROM performance_schema.data_lock_waits;
⑤ 修复：加索引（大表用 Online DDL / gh-ost）、改写 SQL、游标分页、拆分大事务
```

### 4.8 Redis 慢查询

```
① SLOWLOG GET 10              → 慢命令列表（默认 > 10ms 记录）
② redis-cli --bigkeys / MEMORY USAGE key   → 大 Key
③ redis-cli --hotkeys（需 LFU 策略）       → 热 Key
④ INFO stats / INFO commandstats            → 命令统计、命中率
⑤ 常见原因：KEYS *、HGETALL 大 Hash、大 Key 删除阻塞（用 UNLINK）、
   批量过期集中到期、fork（RDB/AOF 重写）导致延迟抖动、网络或客户端连接池不足
```

### 4.9 SOP 总表

| 现象 | 第一条命令 | 关键证据 | 常见根因 |
|---|---|---|---|
| 接口慢 | SkyWalking 慢 Trace | 慢 Span | 慢 SQL、下游慢、锁 |
| CPU 高 | `top -Hp` + `thread -n 3` | 热点线程堆栈 | 死循环、正则回溯、GC |
| 内存高/OOM | `jstat -gcutil` | heap dump | 泄漏、大查询 |
| Full GC 频繁 | `jstat -gcutil` + GC 日志 | 老年代曲线 | 泄漏、晋升过快 |
| 线程池满 | `thread` 统计状态 | 线程卡点 | 下游无超时、锁、连接池 |
| 连接池耗尽 | Hikari 指标 | innodb_trx | 慢 SQL、长事务 |
| Redis 慢 | `SLOWLOG GET` | 大 Key/慢命令 | KEYS、大 Key |
| Pod 反复重启 | `kubectl describe pod` | Last State: OOMKilled / 探针失败 | 内存 limit、liveness 配置错误 |

---

## 5. mini-mall 实战

### 5.1 订单服务 Dockerfile

```dockerfile
# ===== 阶段 1：构建 =====
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace
# 先只复制 pom，利用层缓存：依赖不变时不重新下载
COPY pom.xml .
COPY mall-common/pom.xml mall-common/
COPY mall-product/mall-product-api/pom.xml mall-product/mall-product-api/
COPY mall-user/mall-user-api/pom.xml mall-user/mall-user-api/
COPY mall-order/mall-order-api/pom.xml mall-order/mall-order-api/
COPY mall-order/mall-order-service/pom.xml mall-order/mall-order-service/
RUN mvn -B -q -pl mall-order/mall-order-service -am dependency:go-offline
# 再复制源码并打包
COPY . .
RUN mvn -B -q -pl mall-order/mall-order-service -am package -DskipTests
# 按 Spring Boot 分层解压：依赖层与应用层分开，代码改动时只有最后一层变化（Boot 3.3+ 写法）
RUN java -Djarmode=tools -jar mall-order/mall-order-service/target/mall-order-service.jar \
        extract --layers --launcher --destination /extracted

# ===== 阶段 2：运行 =====
FROM eclipse-temurin:21-jre-jammy
# 非 root 用户运行，降低容器逃逸风险
RUN groupadd --system app && useradd --system --gid app app \
    && mkdir -p /dumps /logs && chown app:app /dumps /logs
WORKDIR /app
# 变化频率从低到高依次复制
COPY --from=build --chown=app:app /extracted/dependencies/ ./
COPY --from=build --chown=app:app /extracted/spring-boot-loader/ ./
COPY --from=build --chown=app:app /extracted/snapshot-dependencies/ ./
COPY --from=build --chown=app:app /extracted/application/ ./
USER app
# JVM 容器参数：按容器内存比例分配堆；OOM 时转储；GC 日志滚动
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=75.0 -XX:InitialRAMPercentage=75.0 \
 -XX:+UseG1GC -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/dumps \
 -Xlog:gc*:file=/logs/gc.log:time,uptime:filecount=5,filesize=20m \
 -Duser.timezone=Asia/Shanghai -Dfile.encoding=UTF-8"
EXPOSE 8080
# exec 形式：java 成为 PID 1，能直接收到 SIGTERM 完成优雅停机
ENTRYPOINT ["java", "org.springframework.boot.loader.launch.JarLauncher"]
```

| 实践 | 收益 |
|---|---|
| 多阶段构建 | 最终镜像不含 JDK、Maven、源码：约 900MB → 约 280MB |
| 先 COPY pom 再 COPY 源码 | 依赖层缓存命中，构建从几分钟降到几十秒 |
| 分层解压 | 推送/拉取时只传变化的应用层（几 MB） |
| JRE 镜像 | 体积小、攻击面小；需要 jstack/jcmd 时用 JDK 镜像或临时注入 Arthas |
| 非 root | 安全基线 |
| `JAVA_TOOL_OPTIONS` | 无需改 ENTRYPOINT 即可被 K8s 环境变量覆盖 |

> Boot 3.2 及以下用 `java -Djarmode=layertools -jar app.jar extract`，启动类为 `org.springframework.boot.loader.launch.JarLauncher`（3.2+）或 `org.springframework.boot.loader.JarLauncher`（3.1 及以下）。
> JRE 镜像没有 `jstack`/`jcmd`：排查时可 `kubectl debug` 挂一个 JDK 临时容器，或使用 Arthas（自带能力，只需 JRE）。

### 5.2 K8s Deployment 与 Service

```yaml
# mall-order-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mall-order
  namespace: mall-prod
  labels: { app: mall-order }
spec:
  replicas: 4
  revisionHistoryLimit: 10                # 保留 10 个历史版本用于回滚
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1                         # 发布时最多多出 1 个 Pod
      maxUnavailable: 0                   # 发布期间可用 Pod 数不减少
  selector:
    matchLabels: { app: mall-order }
  template:
    metadata:
      labels: { app: mall-order }
      annotations:                        # 供 Prometheus 自动发现（使用 annotation 发现规则时）
        prometheus.io/scrape: "true"
        prometheus.io/path: /actuator/prometheus
        prometheus.io/port: "8080"
    spec:
      terminationGracePeriodSeconds: 60   # 需大于 preStop + Spring 优雅停机时间
      containers:
        - name: app
          image: registry.example.com/mall/mall-order:a1b2c3d
          ports:
            - containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
            - name: NACOS_ADDR
              valueFrom:
                configMapKeyRef: { name: mall-common-config, key: nacos.addr }
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef: { name: mall-order-secret, key: db.password }
          resources:
            requests: { cpu: "1", memory: 2Gi }   # 调度依据
            limits:   { cpu: "2", memory: 2Gi }   # 内存 request=limit，避免被优先驱逐；堆 = 2Gi × 75%
          startupProbe:
            httpGet: { path: /actuator/health/liveness, port: 8080 }
            periodSeconds: 5
            failureThreshold: 30                  # 最多给 150s 启动时间
          livenessProbe:
            httpGet: { path: /actuator/health/liveness, port: 8080 }
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet: { path: /actuator/health/readiness, port: 8080 }
            periodSeconds: 5
            failureThreshold: 3
          lifecycle:
            preStop:
              exec:
                command: ["sh", "-c", "sleep 10"]   # 等待 Endpoints 摘除传播完成
          volumeMounts:
            - { name: dumps, mountPath: /dumps }
      volumes:
        - name: dumps
          hostPath: { path: /data/dumps/mall-order, type: DirectoryOrCreate }   # 生产建议用 PVC
---
apiVersion: v1
kind: Service
metadata:
  name: mall-order
  namespace: mall-prod
spec:
  selector: { app: mall-order }
  ports:
    - name: http
      port: 80
      targetPort: 8080
```

> 微服务间调用走 Nacos 注册的 Pod IP，Service 主要给网关 Ingress、Prometheus 和集群内非 Nacos 调用方使用。

发布与回滚命令：

```bash
kubectl -n mall-prod set image deployment/mall-order app=registry.example.com/mall/mall-order:e4f5g6h
kubectl -n mall-prod rollout status deployment/mall-order       # 观察滚动进度
kubectl -n mall-prod rollout pause deployment/mall-order        # 发现异常先暂停
kubectl -n mall-prod rollout undo deployment/mall-order         # 回滚到上一版本
kubectl -n mall-prod rollout history deployment/mall-order      # 历史版本
kubectl -n mall-prod get pods -l app=mall-order -o wide
kubectl -n mall-prod logs -f <pod> --tail=200
kubectl -n mall-prod describe pod <pod>                         # 看事件：OOMKilled、探针失败、拉镜像失败
kubectl -n mall-prod top pod -l app=mall-order                  # CPU/内存实时用量
```

### 5.3 Prometheus 监控接入

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
```

```yaml
management:
  server:
    port: 8080                       # 也可以独立端口（如 8081）避免对外暴露
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  metrics:
    tags:
      application: ${spring.application.name}   # 所有指标带上应用名，便于多服务区分
    distribution:
      percentiles-histogram:
        http.server.requests: true   # 生成 bucket，Prometheus 才能算 P99
```

> 网关要禁止外部访问 `/actuator/**`，否则会泄露环境信息。

**业务指标**：

```java
package com.example.mall.biz.metrics;

/**
 * 订单业务指标：下单次数（按结果打标签）与下单耗时。
 * 指标命名遵循 Micrometer 约定（点分隔），导出到 Prometheus 时会转为下划线：order_create_total。
 */
@Component
public class OrderMetrics {

    /** 下单结果标签取值：成功 */
    public static final String RESULT_SUCCESS = "success";
    /** 下单结果标签取值：业务失败（库存不足等） */
    public static final String RESULT_BIZ_FAIL = "biz_fail";
    /** 下单结果标签取值：系统异常 */
    public static final String RESULT_ERROR = "error";

    private final MeterRegistry meterRegistry;
    private final Timer createTimer;

    /**
     * 构造并注册下单耗时 Timer。
     *
     * @param meterRegistry Micrometer 注册表，由 Spring Boot 自动配置
     */
    public OrderMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
        this.createTimer = Timer.builder("order.create.duration")
                .description("下单耗时")
                .publishPercentileHistogram()
                .register(meterRegistry);
    }

    /**
     * 记录一次下单结果。
     *
     * @param result 结果标签，取值见 RESULT_* 常量（标签值必须是有限集合，禁止放订单号等高基数值）
     */
    public void recordCreate(String result) {
        meterRegistry.counter("order.create", "result", result).increment();
    }

    /**
     * 包装下单逻辑并记录耗时。
     *
     * @param action 下单逻辑
     * @param <T>    返回值类型
     * @return 下单逻辑的返回值
     */
    public <T> T timeCreate(Supplier<T> action) {
        return createTimer.record(action);
    }
}
```

**Prometheus 告警规则**：

```yaml
# mall-order-alerts.yaml
groups:
  - name: mall-order
    rules:
      - alert: OrderCreateErrorRateHigh
        expr: |
          sum(rate(order_create_total{result="error"}[5m]))
            / sum(rate(order_create_total[5m])) > 0.05
        for: 2m
        labels: { severity: P0 }
        annotations:
          summary: "下单系统异常率超过 5%"
          runbook: "https://wiki.example.com/runbook/order-create-error"
      - alert: OrderApiP99High
        expr: |
          histogram_quantile(0.99, sum(rate(http_server_requests_seconds_bucket{application="mall-order",uri="/order/create"}[5m])) by (le)) > 1
        for: 5m
        labels: { severity: P1 }
        annotations:
          summary: "下单接口 P99 超过 1s"
      - alert: HikariPoolPending
        expr: max(hikaricp_connections_pending{application="mall-order"}) > 5
        for: 2m
        labels: { severity: P1 }
        annotations:
          summary: "订单服务数据库连接池出现排队"
      - alert: JvmOldGenHigh
        expr: |
          max by (pod) (jvm_memory_used_bytes{application="mall-order",id="G1 Old Gen"}
            / jvm_memory_max_bytes{application="mall-order",id="G1 Old Gen"}) > 0.85
        for: 10m
        labels: { severity: P2 }
        annotations:
          summary: "订单服务老年代使用率持续高于 85%"
```

**Grafana 看板建议布局**：

```
┌─ 第一行：业务 ───────────────────────────────────────────────────┐
│ 下单量/分钟（同比昨日） │ 下单成功率 │ 支付转化率 │ 超时取消数      │
├─ 第二行：RED ───────────────────────────────────────────────────┤
│ 各接口 QPS │ 各接口错误率 │ 各接口 P50/P99                        │
├─ 第三行：JVM / 资源（USE）──────────────────────────────────────┤
│ 堆/老年代 │ GC 次数与停顿 │ 线程数与状态 │ CPU │ Tomcat 繁忙线程 │ Hikari │
├─ 第四行：依赖 ──────────────────────────────────────────────────┤
│ Feign 调用耗时/错误 │ Redis 命令耗时 │ MQ 发送失败数 / 消费堆积量    │
└────────────────────────────────────────────────────────────────┘
```

### 5.4 演练：订单接口 CPU 飙高

**背景**：周五 20:10 告警「mall-order Pod CPU > 90%」「/order/create P99 > 3s」，持续 5 分钟。

**第 0 步：止血判断**

```
- 查发布记录：19:30 发布了 v1.8.3（新增「订单备注」字段及其格式校验）
- 影响面：4 个 Pod 中 3 个 CPU 打满，下单成功率从 99.6% 降至 82%
- 决策：先扩容到 8 个 Pod 缓解（5 分钟内），同时保留 1 个异常 Pod 做现场分析；若 15 分钟内无法定位则回滚
```

**第 1 步：确认是哪个线程**

```bash
$ kubectl -n mall-prod exec -it mall-order-7d9f-xk2lp -- bash
$ top -Hp 1          # 容器内 Java 是 PID 1
  PID USER   %CPU  COMMAND
   87 app    99.3  http-nio-8080-e
   91 app    98.7  http-nio-8080-e
  103 app    97.9  http-nio-8080-e
   23 app     3.1  GC Thread#0          ← GC 线程 CPU 不高，排除内存问题
$ printf '%x\n' 87
57
```

**第 2 步：看堆栈（Arthas 一步到位）**

```
$ java -jar arthas-boot.jar 1
[arthas@1]$ thread -n 3
"http-nio-8080-exec-12" Id=87 cpuUsage=99.21% RUNNABLE
    at java.util.regex.Pattern$Loop.match(Pattern.java:5048)
    at java.util.regex.Pattern$GroupTail.match(Pattern.java:4899)
    at java.util.regex.Pattern$Curly.match0(Pattern.java:4372)
    at java.util.regex.Pattern$Curly.match(Pattern.java:4347)
    at java.util.regex.Pattern$GroupHead.match(Pattern.java:4840)
    at java.util.regex.Pattern$Loop.match(Pattern.java:5057)
    ...（几十层重复）
    at java.util.regex.Matcher.matches(Matcher.java:720)
    at com.example.mall.util.RemarkValidator.isValid(RemarkValidator.java:23)
    at com.example.mall.biz.OrderBizComponent.createOrder(OrderBizComponent.java:58)
    ...
```

多次执行 `thread -n 3`，三个线程都卡在 `RemarkValidator.isValid` 的正则匹配上。

**第 3 步：查看问题代码与入参**

```
[arthas@1]$ jad com.example.mall.util.RemarkValidator
    private static final Pattern REMARK = Pattern.compile("^([a-zA-Z0-9\\u4e00-\\u9fa5]+\\s?)+$");
    public static boolean isValid(String remark) {
        return remark == null || REMARK.matcher(remark).matches();
    }

[arthas@1]$ watch com.example.mall.util.RemarkValidator isValid '{params[0].length(), #cost}' '#cost > 100' -n 3
method=...isValid cost=8213.4ms  @ArrayList[@Integer[58], @Double[8213.4]]
```

**第 4 步：根因**

`([a-zA-Z0-9中文]+\s?)+$` 是典型的**灾难性回溯（ReDoS）**：外层 `+` 与内层 `+` 可以用指数种方式切分同一段字符；当字符串末尾出现不匹配字符（例如用户输入了一个 emoji 或标点 `!`），引擎会尝试所有切分方式后才判定失败，耗时随长度**指数增长**。58 个字符 → 8 秒。

```
"aaaa…a!"  切分方式：(aaaa)(…)  (aa)(aa)(…)  (a)(aaa)(…) … 共 2^(n-1) 种，每种都失败
```

**第 5 步：修复与验证**

```java
/**
 * 订单备注校验工具：只允许中英文、数字与单个空格分隔，长度不超过 100。
 */
public final class RemarkValidator {

    /** 备注最大长度 */
    private static final int MAX_LENGTH = 100;

    /**
     * 合法备注正则：去掉嵌套量词，用「字符类 + 可选的 (空格 + 字符类)」线性匹配，不会回溯爆炸。
     */
    private static final Pattern REMARK =
            Pattern.compile("^[a-zA-Z0-9\\u4e00-\\u9fa5]+(?: [a-zA-Z0-9\\u4e00-\\u9fa5]+)*$");

    private RemarkValidator() {
    }

    /**
     * 校验订单备注是否合法。
     *
     * @param remark 备注，可为 null（表示未填写）
     * @return true 合法
     */
    public static boolean isValid(String remark) {
        if (remark == null) {
            return true;
        }
        // 先做长度校验：任何正则都应限制输入长度，防止被构造的超长输入攻击
        return remark.length() <= MAX_LENGTH && REMARK.matcher(remark).matches();
    }
}
```

```java
/**
 * 回归测试：构造会触发回溯的输入，断言 50ms 内完成。
 */
@Test
void shouldNotBacktrackCatastrophically() {
    String evil = "a".repeat(60) + "!";
    assertTimeoutPreemptively(Duration.ofMillis(50), () -> assertFalse(RemarkValidator.isValid(evil)));
}
```

**第 6 步：发布与复盘**

| 项 | 内容 |
|---|---|
| 时间线 | 19:30 发布 → 20:05 首单恶意/异常输入 → 20:10 告警 → 20:15 扩容 → 20:28 定位 → 21:05 修复版本发布 → 21:20 恢复 |
| 根因 | 正则嵌套量词导致灾难性回溯 |
| 为什么测试没发现 | 单测只覆盖了合法输入；没有异常输入与性能用例 |
| 改进项 | ① 代码规范：禁止嵌套量词，Sonar 规则开启 ReDoS 检测；② 所有正则前置长度校验；③ 下单接口加入 Sentinel 并发线程数限流，单接口异常不拖垮整个实例；④ 发布后 30 分钟观察期内设置 CPU/P99 加强告警 |

> 演练要点：**`top -Hp` → 线程 → 堆栈 → 入参 → 根因**，每一步都有证据。如果第 1 步发现是 GC 线程在烧 CPU，就要转去 4.3/4.4 的内存排查路线。

---

## 6. 常见坑

| # | 坑 | 后果 | 正确做法 |
|---|---|---|---|
| 1 | Dockerfile 写死 `-Xmx4g` 而容器 limit 2Gi | 容器被 OOMKilled，无 Java 日志 | `MaxRAMPercentage` |
| 2 | `ENTRYPOINT java -jar app.jar`（shell 形式） | Java 不是 PID 1，收不到 SIGTERM，被强杀 | exec 数组形式 |
| 3 | liveness 探针包含数据库健康检查 | 数据库抖动 → 全部 Pod 重启 | liveness 只看进程自身 |
| 4 | 无 startupProbe，liveness 初始延迟太短 | 启动慢的服务被反复重启 | 配 startupProbe |
| 5 | 无 preStop sleep | 发布时出现少量 502 | preStop sleep 5~10s + 优雅停机 |
| 6 | 镜像 tag 用 latest | 无法回滚、节点缓存旧镜像 | commit SHA / 版本号 |
| 7 | 日志打到容器文件且无滚动 | 磁盘打满，节点驱逐 | stdout + 采集；或滚动 + 清理 |
| 8 | 指标标签放 orderNo、userId | Prometheus 高基数，内存爆炸 | 标签值必须是有限集合 |
| 9 | 直接在线上 `jmap -dump` 不摘流量 | STW 数十秒，大量请求超时 | 先摘流量再 dump |
| 10 | 出问题先重启 | 现场丢失，问题会再次出现 | 重启前 jstack/jmap 保留现场（至少保留一个实例） |
| 11 | 告警太多没人看 | 真正的故障淹没在噪音里 | 告警可行动、分级、定期治理 |
| 12 | Actuator 端点对公网暴露 | 泄露配置、heapdump 可被下载 | 网关屏蔽 + 独立管理端口 |

---

## 7. 高级视角

### 7.1 发布规范与回滚

| 阶段 | 要求 |
|---|---|
| 发布前 | 变更评审（DDL、配置、依赖服务）；明确回滚方案；**兼容性检查**：新旧版本同时在线时，接口、消息体、表结构都必须兼容 |
| 发布顺序 | DDL 先行（只加不删）→ 被调用方（提供新接口）→ 调用方 → 前端 → 开关打开 |
| 发布中 | 灰度：1 个 Pod 或 5% 流量 → 观察 10~30 分钟（错误率、P99、业务量）→ 分批全量 |
| 发布窗口 | 避开高峰与周五晚上；大促前封网 |
| 回滚 | 应用回滚（`rollout undo`）分钟级；**数据回滚困难** → 所以 DDL 只做向前兼容的变更；功能用开关控制，关开关比回滚更快 |
| 发布后 | 观察期、值班、复盘 |

> 删字段的「三步走」：① 代码不再读写该字段并发布；② 观察一个周期；③ 再执行 DROP COLUMN。

### 7.2 稳定性建设

**容量评估**：

```
峰值 QPS 估算 = 日均请求量 / 86400 × 峰值系数（通常 3~10，大促按历史峰值 × 增长预期）
所需实例数  = 峰值 QPS / 单实例安全 QPS（压测极限的 60%~70%）× 冗余系数（1.3~1.5，覆盖单机房故障）
例：日 800 万下单请求，峰值系数 6 → 峰值约 555 QPS；单实例压测极限 200 → 安全值 130 → 需 5 个 × 1.5 ≈ 8 个实例
```

**压测**：

| 工具 | 特点 | 用途 |
|---|---|---|
| wrk | 轻量、高性能、Lua 脚本 | 单接口基准压测 |
| JMeter | GUI + 脚本，场景编排丰富 | 多接口业务场景 |
| 全链路压测 | 流量染色、影子库/影子表 | 大促前生产环境压测 |

```bash
# wrk：8 线程、200 连接、压 60s，输出延迟分布
wrk -t8 -c200 -d60s --latency -s create_order.lua http://mall-order.test/order/create
```

压测要点：从小到大阶梯加压，找到拐点（RT 陡增或错误率上升的 QPS）；同时观察 CPU、GC、连接池、下游，**瓶颈往往不在被压的服务本身**。

**预案**：

| 场景 | 预案 | 演练方式 |
|---|---|---|
| 流量超预期 | 网关限流阈值、HPA 扩容 | 压测验证 |
| 下游故障 | Sentinel 熔断 + 降级开关 | 故障注入（ChaosBlade） |
| 数据库主库故障 | 主从切换；只读降级 | 定期切换演练 |
| Redis 故障 | 本地缓存兜底、限流保护数据库 | 演练 |
| MQ 堆积 | 扩消费者、非核心消息降级 | 演练 |
| 发布故障 | 一键回滚、功能开关 | 每次发布都具备 |

### 7.3 SLO 思维

- **SLI**（指标）：下单接口成功率、P99 延迟。
- **SLO**（目标）：月度成功率 ≥ 99.95%，P99 ≤ 500ms。
- **错误预算**：99.95% 意味着每月约 21.6 分钟的不可用额度。预算耗尽时冻结功能发布，优先投入稳定性。

这让「稳定性 vs 迭代速度」的争论有了可量化的依据。

### 7.4 故障复盘模板

| 项 | 内容 |
|---|---|
| 影响 | 时间段、影响用户数、损失金额 |
| 时间线 | 发生 → 发现 → 响应 → 定位 → 止血 → 恢复（精确到分钟） |
| 根因 | 技术根因 + 流程根因（为什么测试/评审/监控没拦住） |
| 改进项 | 每项有负责人与截止时间，并跟踪关闭 |
| 原则 | 对事不对人；关注「发现时间」与「恢复时间」能否缩短 |

---

## 8. 小练习

1. 用本章 docker-compose 拉起 MySQL/Redis/RocketMQ/Nacos，让 mini-mall 在本地完整跑起来。
2. 按 5.1 编写 Dockerfile，对比单阶段与多阶段构建的镜像体积；修改一行业务代码后重新构建，观察哪些层被复用。
3. 用 kind 或 minikube 部署 5.2 的 YAML；执行一次滚动发布，同时用 `wrk` 持续压测，观察是否出现错误；去掉 preStop 和优雅停机后再试一次，对比结果。
4. 接入 Prometheus + Grafana，按 5.3 的布局建一个看板，并用 `OrderMetrics` 记录下单结果。
5. **CPU 演练**：在本地复现 5.4 的正则回溯，完整走一遍 `top -Hp → printf → jstack → Arthas thread/watch` 链路。
6. **内存演练**：写一个把订单放进 `static Map` 且不清理的接口，用 `wrk` 压测，观察老年代曲线，dump 后用 MAT 找到泄漏点。
7. **连接池演练**：在 `@Transactional` 方法里 `Thread.sleep(3000)`，把 `maximum-pool-size` 设为 5，压测后观察 Hikari 指标与报错，再用 Arthas 定位。
