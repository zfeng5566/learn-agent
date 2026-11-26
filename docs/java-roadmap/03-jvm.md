> [← 总纲](./00-outline.md) | [上一章：02 集合框架与常用 API](./02-collections-and-api.md) | [下一章：04 并发编程](./04-concurrency.md)

# 03 JVM 原理：用 V8 的眼睛看 HotSpot

---

## 0. 本章地图

```
            你写的代码              本章关注的部分
OrderController.java ──javac──► .class 字节码 ──► ┌──────────── JVM 进程 ────────────┐
                                                  │ 类加载子系统（加载/链接/初始化）  │
                                                  │ 运行时数据区（堆/栈/元空间…）     │
                                                  │ 执行引擎（解释器 + JIT + GC）     │
                                                  └──────────────┬──────────────────┘
                                                                 ▼
                                                     操作系统 / 容器（cgroup 限额）
```

本章回答四个问题：

| 问题 | 对应小节 | 为什么高级工程师必须懂 |
|---|---|---|
| 代码是怎么跑起来的？ | 2.1、2.2、2.5、3.5 | 理解启动慢、预热、类冲突（`NoSuchMethodError`）的根源 |
| 对象放在哪、占多大？ | 2.3、2.4 | 估算内存、读懂 OOM 报错、定位内存泄漏 |
| 垃圾是怎么回收的？ | 2.6、3.1～3.4 | 选收集器、调 GC 参数、解释接口偶发卡顿（STW） |
| 出了问题怎么查？ | 2.8、4 实战、6.2～6.4 SOP | 线上 OOM / CPU 飙高 / Full GC 频繁时能独立止血和定位 |

在全景图中的位置：01-02 章讲「写什么」，本章讲「写出来的东西在哪里、怎么运行」，04 章讲「多个线程同时运行时会怎样」。

---

## 1. 前端类比：你其实已经懂一半了

| 前端 / Node（V8） | Java（HotSpot JVM） | 差异要点 |
|---|---|---|
| V8 引擎 | HotSpot 虚拟机 | V8 直接吃源码；JVM 吃**字节码**（`.class`），编译与运行分离 |
| Ignition 解释器 + TurboFan 优化编译器 | 解释器 + C1/C2 即时编译器（JIT） | 思路几乎一样：先解释、热点再编译、假设失败就去优化 |
| Hidden Class / Inline Cache | Klass 元数据 / 内联缓存 + 类层次分析 | Java 类型是静态的，对象布局在类加载时就确定，不会「形状变化」 |
| V8 堆：新生代（Scavenge）+ 老生代（Mark-Sweep-Compact） | JVM 堆：年轻代 + 老年代（G1/ZGC） | **几乎同一套分代思想**；但 JVM 堆可以到几十 GB，且进程常驻数月 |
| `node --max-old-space-size=4096` | `-Xmx4g` | Node 默认堆有上限（约 2～4GB）；JVM 默认取物理内存 / 容器内存的 1/4 |
| `require` / ESM 模块加载 | 类加载器（ClassLoader）+ 双亲委派 | Java 运行时可同时存在「同名不同加载器」的两个类 |
| `WeakMap` / `WeakRef` / `FinalizationRegistry` | `WeakHashMap` / `WeakReference` / `Cleaner` | Java 还有软引用、虚引用 |
| Chrome DevTools → Memory → Heap Snapshot | `jmap -dump` / `jcmd GC.heap_dump` + MAT | 线上没有 GUI，靠命令行导出、离线分析 |
| Chrome Performance 火焰图 / `--prof` | JFR + JMC、async-profiler、Arthas `profiler` | — |
| 页面卡顿（长任务阻塞主线程） | GC 停顿（Stop-The-World） | STW 会冻结**所有**业务线程，接口 RT 毛刺的常见元凶 |
| 刷新页面就清空内存 | 进程跑几个月不重启 | 前端泄漏刷新就好；服务端泄漏会累积到 OOM，这是心态上最大的差别 |

**对照代码：最常见的内存泄漏，在两边长得一模一样**

```ts
// TS：模块级缓存只增不减 —— 单页应用跑久了内存一直涨
const orderCache = new Map<string, Order>();   // key: 订单号

export function getOrder(orderNo: string): Order {
  if (!orderCache.has(orderNo)) {
    orderCache.set(orderNo, loadOrder(orderNo)); // 从不删除
  }
  return orderCache.get(orderNo)!;
}
```

```java
/**
 * 反面示例：静态 Map 做缓存，只增不减，最终导致 OOM。
 */
public class LeakyOrderCache {

    /** 订单缓存，key：订单号 orderNo，value：订单实体。static 意味着被类持有，类不卸载它就永远可达 */
    private static final Map<String, OrderPO> ORDER_CACHE = new HashMap<>();

    /**
     * 按订单号查询订单（带缓存）。
     *
     * @param orderNo 订单号
     * @return 订单实体
     */
    public OrderPO getOrder(String orderNo) {
        // computeIfAbsent：不存在才加载，但永远不会淘汰
        return ORDER_CACHE.computeIfAbsent(orderNo, this::loadOrder);
    }

    /**
     * 从数据库加载订单（示意）。
     *
     * @param orderNo 订单号
     * @return 订单实体
     */
    private OrderPO loadOrder(String orderNo) {
        OrderPO po = new OrderPO();
        po.setOrderNo(orderNo);
        return po;
    }
}
```

> 正确姿势：本地缓存用 Caffeine（有容量上限和过期），分布式缓存用 Redis（09 章）。

---

## 2. 核心概念

### 2.1 JDK、JRE、JVM 的关系

```
┌──────────────────────────── JDK（开发工具包）────────────────────────────┐
│  javac  javap  jar  jshell  jcmd  jstack  jmap  jstat  jfr  jlink ...      │
│  ┌──────────────────────── JRE（运行环境）────────────────────────────┐  │
│  │  核心类库：java.lang / java.util / java.time ...（模块化后在 jmods）│  │
│  │  ┌──────────────────────── JVM ─────────────────────────────────┐ │  │
│  │  │ 类加载器 │ 运行时数据区 │ 执行引擎（解释器/JIT/GC）│ JNI      │ │  │
│  │  └──────────────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

| 名词 | 类比 Node 生态 | 说明 |
|---|---|---|
| JVM | V8 | 规范（《Java 虚拟机规范》）+ 实现（HotSpot 最主流，另有 OpenJ9、GraalVM） |
| JRE | Node 运行时（V8 + 内置模块） | Java 11 起官方不再单独发 JRE，可用 `jlink` 裁剪出最小运行时 |
| JDK | Node + npm + 各种 CLI | 开发、诊断工具全在这里；**生产镜像建议用 JDK 而非 JRE**，否则线上没有 jstack/jcmd 可用 |
| 发行版 | Node 官方 / 各云厂商构建 | Oracle JDK、OpenJDK、Eclipse Temurin、Amazon Corretto、阿里 Dragonwell……内核都是 OpenJDK |

> **Java 8 存量差异**：Java 8 有独立 JRE 目录、扩展类加载器 `ExtClassLoader`、`rt.jar`；Java 9 引入模块系统（JPMS）后这些都变了，2.5 节会提到。

### 2.2 从 `.java` 到运行的全过程

```
OrderService.java
     │ ① javac 编译（前端编译）：词法/语法分析 → 语义分析 → 泛型擦除 → 语法糖解糖 → 生成字节码
     ▼
OrderService.class   （平台无关的字节码，魔数 0xCAFEBABE）
     │ ② 打包：mvn package → mini-mall.jar（fat jar，内含所有依赖 jar）
     ▼
java -jar mini-mall.jar
     │ ③ 启动 JVM 进程：解析参数、初始化堆、启动 GC 线程/JIT 编译线程
     │ ④ 类加载：按需加载 main 所在类及其依赖（懒加载，用到才加载）
     │ ⑤ 解释执行字节码
     │ ⑥ 热点方法被 JIT 编译为本地机器码（C1 → C2）
     ▼
CPU 执行机器码
```

用 `javap` 看字节码，就像在 DevTools 里看 V8 的 bytecode（`node --print-bytecode`）：

```java
/**
 * 演示 javap 反编译的最小类。
 */
public class Calc {

    /**
     * 计算两数之和。
     *
     * @param a 加数
     * @param b 加数
     * @return 和
     */
    public int add(int a, int b) {
        return a + b;
    }
}
```

```bash
javac Calc.java && javap -c Calc
#  public int add(int, int);
#    Code:
#       0: iload_1        // 把局部变量表 1 号槽（a）压入操作数栈
#       1: iload_2        // 把 b 压栈
#       2: iadd           // 弹出两个 int 相加，结果压栈
#       3: ireturn        // 返回栈顶 int
```

> 局部变量表 0 号槽是 `this`。JVM 是**基于栈**的虚拟机（V8 的 Ignition 是基于寄存器 + 累加器），所以字节码紧凑、易移植，但指令数更多——这也是 JIT 必须存在的原因。

### 2.3 运行时数据区

```
┌─────────────────────────────── JVM 进程内存 ────────────────────────────────┐
│ 线程共享                                                                     │
│ ┌─────────────────────────────────────────────┐ ┌─────────────────────────┐ │
│ │ 堆 Heap（-Xms / -Xmx）                       │ │ 元空间 Metaspace         │ │
│ │  ┌────────────── 年轻代 ─────────┐┌────────┐ │ │ （本地内存，非堆）        │ │
│ │  │ Eden │ Survivor0 │ Survivor1 ││ 老年代  │ │ │ 类元数据、方法字节码、    │ │
│ │  └───────────────────────────────┘└────────┘ │ │ 运行时常量池              │ │
│ │  对象实例、数组、字符串常量池、静态变量(*)   │ │ -XX:MaxMetaspaceSize     │ │
│ └─────────────────────────────────────────────┘ └─────────────────────────┘ │
│ 线程私有（每个线程一份）                                                       │
│ ┌─────────────────┐ ┌──────────────────┐ ┌─────────────────┐                │
│ │ 虚拟机栈 -Xss    │ │ 本地方法栈        │ │ 程序计数器 PC   │                │
│ │ 栈帧：局部变量表 │ │ （JNI 调用 C 代码）│ │ 当前字节码行号  │                │
│ │ 操作数栈/返回地址│ │                  │ │ 唯一不会 OOM    │                │
│ └─────────────────┘ └──────────────────┘ └─────────────────┘                │
│ 其他本地内存：直接内存(NIO/Netty) · 线程栈 · JIT 代码缓存(CodeCache) · GC 数据结构 │
└──────────────────────────────────────────────────────────────────────────────┘
(*) Java 7 起字符串常量池、类静态变量移到堆中；Java 8 起永久代 PermGen 被元空间替代
```

| 区域 | 存什么 | 大小参数 | 溢出表现 | V8 对应 |
|---|---|---|---|---|
| 堆 | 所有 `new` 出来的对象 | `-Xms` `-Xmx` | `OutOfMemoryError: Java heap space` | V8 堆（new space / old space） |
| 虚拟机栈 | 方法调用的栈帧 | `-Xss`（默认 1MB） | `StackOverflowError`（递归太深） | JS 调用栈（`Maximum call stack size exceeded`） |
| 元空间 | 类的结构信息 | `-XX:MaxMetaspaceSize` | `OutOfMemoryError: Metaspace` | V8 的 code space / map space |
| 程序计数器 | 下一条字节码地址 | — | 不会溢出 | Ignition 的 bytecode offset |
| 直接内存 | `ByteBuffer.allocateDirect`、Netty | `-XX:MaxDirectMemorySize` | `OutOfMemoryError: Direct buffer memory` | Node 的 `Buffer`（堆外 ArrayBuffer） |

**一个方法调用在栈上长什么样：**

```java
/**
 * 演示对象与引用在栈/堆上的分布。
 */
public class StackHeapDemo {

    /**
     * 创建订单并计算金额。
     *
     * @param userId 用户 ID（基本类型 long，值直接放在栈帧局部变量表）
     * @return 订单实体（对象在堆上，栈上只存引用）
     */
    public OrderPO create(long userId) {
        int quantity = 2;                          // 基本类型：值在栈上
        OrderPO order = new OrderPO();             // order 引用在栈上，OrderPO 对象在堆上
        order.setUserId(userId);
        order.setTotalAmount(new BigDecimal("99.00").multiply(BigDecimal.valueOf(quantity)));
        return order;                              // 方法返回，栈帧弹出；对象是否存活取决于是否还有引用
    }
}
```

```
 线程栈                               堆
┌─────────────────────┐
│ create() 栈帧        │
│  this ──────────────┼──────► StackHeapDemo 对象
│  userId = 1001      │
│  quantity = 2       │
│  order ─────────────┼──────► OrderPO{userId=1001, totalAmount ─► BigDecimal(198.00)}
├─────────────────────┤
│ 调用者的栈帧 ...     │
└─────────────────────┘
```

> 和 JS 的区别：JS 里除了小整数（Smi）几乎所有值都在堆上；Java 的 8 种基本类型（`int`、`long`……）作为局部变量时直接放在栈帧里，不产生 GC 压力。这也是为什么 Java 推荐热点代码用 `long` 而不是 `Long`。

### 2.4 对象的创建与内存布局

**`new OrderPO()` 背后发生了什么：**

```
new 指令
  │
  ├─① 类加载检查：OrderPO 类加载过了吗？没有则先走类加载（2.5）
  ├─② 分配内存：
  │     ├─ 优先在线程私有的 TLAB（Thread Local Allocation Buffer）里「指针碰撞」分配，无锁，极快
  │     └─ TLAB 不够 → 在 Eden 用 CAS 分配；Eden 不够 → 触发 Young GC
  ├─③ 内存清零：所有字段置为零值（0 / false / null），所以字段不赋值也能用
  ├─④ 设置对象头：类型指针、哈希码（延迟计算）、GC 年龄、锁状态
  └─⑤ 执行构造方法 <init>：按代码给字段赋值
```

> TLAB 是 JVM 分配速度快的关键：绝大多数 `new` 只是「指针往后挪 N 个字节」，比 C 的 `malloc` 还快。代价是 GC 要负责回收。

**对象内存布局（64 位 HotSpot，开启指针压缩）：**

```
┌──────────────────────── 对象头 Header (12 字节) ─────────────────────────┐
│ Mark Word (8 字节)                          │ Klass Pointer (4 字节)      │
│ 哈希码 / GC 分代年龄(4bit) / 锁标志位        │ 指向元空间中的类元数据      │
├────────────────────────────────────────────────────────────────────────────┤
│ 实例数据 Instance Data：字段按 long/double → int/float → short/char → byte/boolean → 引用 重排 │
├────────────────────────────────────────────────────────────────────────────┤
│ 对齐填充 Padding：对象大小必须是 8 字节的倍数                               │
└────────────────────────────────────────────────────────────────────────────┘
数组对象额外多一个 4 字节的 length 字段。
```

GC 年龄只有 4 bit，所以对象最多熬过 15 次 Young GC 就晋升老年代（`-XX:MaxTenuringThreshold` 最大 15）。

**算一个 `OrderPO` 有多大：**

| 部分 | 字段 | 字节 |
|---|---|---|
| 对象头 | Mark Word + 压缩 Klass 指针 | 12 |
| 引用字段 ×7 | `id(Long)`、`orderNo`、`userId(Long)`、`totalAmount`、`status(Integer)`、`createTime`、`updateTime` | 7 × 4 = 28 |
| 对齐 | 40 → 补齐到 8 的倍数 | 40 |

只有 40 字节？这是**浅大小（Shallow Size）**。它引用的 `String`（订单号，约 24 + 48 字节）、`BigDecimal`（约 40 字节+）、两个 `LocalDateTime`（各含 `LocalDate` + `LocalTime`，合计约 70 字节）、包装类型……加起来，一个订单的**保留大小（Retained Size）约 300～400 字节**。100 万订单 ≈ 300～400MB——这正是第 4 节 OOM 实验的理论依据。

> 用 JOL（`org.openjdk.jol:jol-core`）可以实测：`System.out.println(ClassLayout.parseInstance(order).toPrintable());`

**指针压缩（Compressed Oops）：**

- 64 位系统上一个引用本应 8 字节；JVM 利用「对象 8 字节对齐」这一事实，把地址右移 3 位存成 32 位，4 字节就能寻址 2³² × 8 = **32GB**。
- 堆 < 32GB 时默认开启（`-XX:+UseCompressedOops`）。**堆设成 33GB 反而比 31GB 能装的对象更少**，因为所有引用都膨胀成了 8 字节。这是「堆不要超过 31GB」这条经验的来源。
- 高级补充：Java 24 引入实验性的紧凑对象头（JEP 450，`-XX:+UseCompactObjectHeaders`），对象头压到 8 字节，对小对象密集的应用能省 10%+ 内存。

### 2.5 类加载机制

**生命周期：**

```
 加载 Loading ──► 链接 Linking ──────────────────────► 初始化 Initialization ──► 使用 ──► 卸载
 读取 .class     ├ 验证：字节码合法吗（魔数、类型安全）   执行 <clinit>：             （类加载器被回收时
 生成 Class 对象 ├ 准备：给 static 字段分配内存、赋零值   static 字段赋值 + static 块    才可能卸载）
                └ 解析：符号引用 → 直接引用（可延迟）
```

> 和 ESM 的相似点：都是「按需加载 + 只初始化一次」；Java 的 `<clinit>` 由 JVM 加锁保证只执行一次且线程安全，这是「静态内部类单例」写法的理论基础（04 章）。

**什么时候触发初始化（主动使用）：** `new`、访问非常量的 static 字段/方法、反射 `Class.forName`、初始化子类先初始化父类、`main` 所在类。**引用 `static final` 编译期常量不会触发**（已被内联到调用方）。

**类加载器层级（Java 9+）：**

```
       Bootstrap ClassLoader（C++ 实现，Java 中表示为 null）
         │  加载 java.base 等核心模块：java.lang.String、java.util.*
         ▼
       Platform ClassLoader（Java 8 叫 Extension ClassLoader）
         │  加载 java.sql、java.xml 等平台模块
         ▼
       Application ClassLoader（AppClassLoader）
         │  加载 classpath 上的类：你的代码 + 第三方 jar
         ▼
       自定义 ClassLoader（Spring Boot 的 LaunchedClassLoader、Tomcat 的 WebappClassLoader ...）
```

**双亲委派模型：**

```
loadClass("com.example.mall.model.po.OrderPO")
  │
  ├─① 已加载过？（findLoadedClass）是 → 直接返回
  ├─② 委派给父加载器 parent.loadClass(...)  —— 一路向上直到 Bootstrap
  ├─③ 父加载器都找不到 → 自己 findClass(...) 读字节码并 defineClass
  └─④ 自己也找不到 → ClassNotFoundException
```

```java
/**
 * 双亲委派的核心逻辑（简化自 java.lang.ClassLoader#loadClass）。
 */
public abstract class SimplifiedClassLoader extends ClassLoader {

    /**
     * 构造函数。
     *
     * @param parent 父加载器
     */
    protected SimplifiedClassLoader(ClassLoader parent) {
        super(parent);
    }

    /**
     * 按双亲委派规则加载类。
     *
     * @param name    类的全限定名
     * @param resolve 是否立即解析
     * @return 加载得到的 Class 对象
     * @throws ClassNotFoundException 所有加载器都找不到时抛出
     */
    @Override
    protected Class<?> loadClass(String name, boolean resolve) throws ClassNotFoundException {
        synchronized (getClassLoadingLock(name)) {
            // 1. 先查缓存：同一个加载器同名类只加载一次
            Class<?> c = findLoadedClass(name);
            if (c == null) {
                try {
                    // 2. 先交给父加载器（getParent() 为 null 时代表 Bootstrap）
                    c = getParent() != null
                            ? getParent().loadClass(name)
                            : findSystemClass(name);
                } catch (ClassNotFoundException ignored) {
                    // 父加载器找不到，属正常情况，继续往下
                }
                if (c == null) {
                    // 3. 父加载器都找不到，才由自己加载
                    c = findClass(name);
                }
            }
            if (resolve) {
                resolveClass(c);
            }
            return c;
        }
    }
}
```

为什么要双亲委派？

| 目的 | 说明 |
|---|---|
| 安全 | 你写一个 `java.lang.String` 也不会被加载，核心类永远由 Bootstrap 加载，防止被篡改 |
| 唯一性 | **类的身份 = 全限定名 + 加载它的类加载器**。委派保证核心类在 JVM 里只有一份 |

> 第二点是很多诡异问题的根源：同一个 `OrderPO`，被两个不同加载器加载，`instanceof` 会返回 false，强转会抛 `ClassCastException: OrderPO cannot be cast to OrderPO`。Spring Boot DevTools 的热重启就常引发这个问题。

**打破双亲委派的三个经典场景：**

**① SPI（JDBC）——父加载器需要加载子加载器才能看到的类**

```
DriverManager（java.sql，由 Platform/Bootstrap 加载）
   需要加载 com.mysql.cj.jdbc.Driver（在 classpath 的 mysql-connector.jar 里，只有 AppClassLoader 看得到）
   父加载器「向下」看不到子加载器的类 → 违背委派方向
解决：线程上下文类加载器（Thread Context ClassLoader, TCCL）
   ServiceLoader.load(Driver.class) 内部用 Thread.currentThread().getContextClassLoader()（默认就是 AppClassLoader）
   去读 META-INF/services/java.sql.Driver 文件，反射实例化
```

> Spring Boot 的自动配置（`META-INF/spring/...AutoConfiguration.imports`）和 Dubbo 的扩展机制都是 SPI 思想的变体，07、11 章会再见到。

**② Tomcat——同一进程隔离多个 Web 应用**

```
         Bootstrap
            │
         Platform / System
            │
         Common ClassLoader      ← Tomcat 自身与所有应用共享的类（servlet-api）
          ┌─┴──────────┐
  WebappClassLoader-A  WebappClassLoader-B   ← 每个 war 一个
  （应用 A 的 spring 5）（应用 B 的 spring 6）
```

`WebappClassLoader` 的规则：`java.*` 等核心类仍先交给上层，**其余类先在自己的 `WEB-INF/classes`、`WEB-INF/lib` 里找，找不到才委派给父加载器**。这样两个应用可以各用各的 Spring 版本互不干扰。热部署时直接丢弃整个 WebappClassLoader，类就能被卸载。

**③ 热部署 / 插件化 / Arthas**：每次重新创建新的类加载器加载新版本的类。

> Spring Boot fat jar 呢？它用 `LaunchedClassLoader` 读取 jar 中嵌套的 `BOOT-INF/lib/*.jar`，但**仍然遵循双亲委派**，只是扩展了「去哪找字节码」。

### 2.6 GC 基础：什么是垃圾

**判断对象是否存活：可达性分析（Reachability Analysis）**

引用计数（Python、早期 IE 的 COM 对象）解决不了循环引用。JVM 和 V8 都用可达性分析：从一组 **GC Roots** 出发遍历引用图，走不到的就是垃圾。

```
GC Roots                         堆
 ├─ 线程栈中的局部变量 ──────► A ──► B ──► C        A、B、C 可达，存活
 ├─ 类的静态字段     ──────► D                      D 可达，存活
 ├─ 常量池引用                  E ◄──► F            E、F 互相引用，但 Roots 到不了 → 垃圾
 ├─ synchronized 持有的锁对象
 ├─ JNI 引用
 └─ JVM 内部（类加载器、常驻异常对象等）
```

> V8 的 Roots 是全局对象、当前执行栈、Handle 等，思想完全一致。

**四种引用强度：**

| 引用类型 | 回收时机 | 典型用途 | JS 对应 |
|---|---|---|---|
| 强引用 `Order o = new Order()` | 永不回收，宁可 OOM | 日常代码 | 普通引用 |
| 软引用 `SoftReference` | **内存不足**时回收 | 内存敏感缓存（现在更推荐 Caffeine） | 无 |
| 弱引用 `WeakReference` | **下一次 GC** 就回收 | `WeakHashMap`、`ThreadLocalMap` 的 key（04 章） | `WeakRef` / `WeakMap` |
| 虚引用 `PhantomReference` | 随时，`get()` 永远返回 null | 配合引用队列感知回收，释放堆外内存（`Cleaner`） | `FinalizationRegistry` |

```ts
// TS：WeakRef —— 对象被回收后 deref() 返回 undefined
let big: { data: number[] } | null = { data: new Array(1e6).fill(0) };
const ref = new WeakRef(big);
big = null;                       // 去掉强引用
// 某次 GC 之后
console.log(ref.deref());         // undefined（时机不确定）
```

```java
import java.lang.ref.WeakReference;

/**
 * 演示弱引用在 GC 后被回收。
 */
public class WeakRefDemo {

    /**
     * 程序入口。
     *
     * @param args 命令行参数（未使用）
     */
    public static void main(String[] args) {
        byte[] big = new byte[10 * 1024 * 1024];                 // 强引用一个 10MB 数组
        WeakReference<byte[]> ref = new WeakReference<>(big);
        big = null;                                               // 去掉强引用，只剩弱引用
        System.gc();                                              // 建议 GC（仅演示用，生产禁止调用）
        System.out.println("回收后：" + ref.get());               // 大概率输出 null
    }
}
```

> `finalize()` 已在 Java 9 废弃、Java 18 标记为待删除（JEP 421）：执行时机不确定、会让对象「复活」、拖慢 GC。需要释放资源请用 `try-with-resources` 或 `Cleaner`。

### 2.7 常用 JVM 参数速查

参数分三类：标准参数（`-version`）、`-X` 非标准参数、`-XX` 高级参数（`-XX:+开启` / `-XX:-关闭` / `-XX:键=值`）。

| 分类 | 参数 | 作用 / 建议 |
|---|---|---|
| 堆 | `-Xms4g -Xmx4g` | 初始/最大堆。**生产建议相等**，避免运行中扩缩容引发停顿 |
| 堆（容器） | `-XX:MaxRAMPercentage=75.0` | 按容器内存百分比设置最大堆，见 3.6 |
| 栈 | `-Xss512k` | 单线程栈大小，线程数极多时可适当调小 |
| 元空间 | `-XX:MetaspaceSize=256m -XX:MaxMetaspaceSize=512m` | 前者是首次触发元空间 GC 的阈值；后者给个上限防止无限膨胀 |
| 直接内存 | `-XX:MaxDirectMemorySize=512m` | 默认约等于 `-Xmx`，用 Netty 的服务建议显式设置 |
| 收集器 | `-XX:+UseG1GC` / `-XX:+UseZGC -XX:+ZGenerational` | Java 21 默认 G1；ZGC 分代需显式开启（Java 23 起分代为默认） |
| G1 | `-XX:MaxGCPauseMillis=200` | 停顿目标，G1 据此调整年轻代大小，**不要设得过小** |
| OOM 现场 | `-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/data/dump/` | **生产必开**，OOM 时自动 dump 堆 |
| OOM 处理 | `-XX:+ExitOnOutOfMemoryError` | OOM 后直接退出，让 K8s 重启，避免「半死不活」 |
| GC 日志 | `-Xlog:gc*:file=/data/logs/gc.log:time,uptime,level,tags:filecount=10,filesize=50m` | Java 9+ 统一日志；Java 8 是 `-XX:+PrintGCDetails -Xloggc:` |
| JFR | `-XX:StartFlightRecording=duration=0,maxsize=200m,filename=/data/jfr/app.jfr` | 低开销（<1%）飞行记录仪，可常开 |
| 诊断 | `-XX:+PrintFlagsFinal` | 打印所有参数的最终值，排查「到底生效没有」 |

**一份生产起步模板（4C8G 容器，Java 21）：**

```bash
java \
  -XX:MaxRAMPercentage=75.0 -XX:InitialRAMPercentage=75.0 \
  -XX:+UseG1GC -XX:MaxGCPauseMillis=200 \
  -XX:MaxMetaspaceSize=512m \
  -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/data/dump/ \
  -XX:+ExitOnOutOfMemoryError \
  -Xlog:gc*:file=/data/logs/gc.log:time,uptime:filecount=10,filesize=50m \
  -jar mini-mall.jar
```

> 原则：**先用默认值 + 监控，有证据再调**。网上流传的几十个参数的「调优模板」大多是 CMS 时代的遗产，对 G1/ZGC 有害无益。

### 2.8 排障工具箱

| 工具 | 一句话 | 常用命令 | 前端类比 |
|---|---|---|---|
| `jps` | 列出 Java 进程 | `jps -lv` | `ps aux \| grep node` |
| `jstat` | 实时看 GC 统计 | `jstat -gcutil <pid> 1000 10`（每秒一次，共 10 次） | DevTools Memory 实时曲线 |
| `jstack` | 线程快照 | `jstack -l <pid> > thread.txt` | Performance 面板调用栈 |
| `jmap` | 堆信息 / dump | `jmap -histo:live <pid> \| head -30`、`jmap -dump:live,format=b,file=heap.hprof <pid>` | Heap Snapshot |
| `jcmd` | **瑞士军刀，推荐优先用** | `jcmd <pid> help`、`GC.heap_dump`、`Thread.print`、`VM.flags`、`VM.native_memory`、`JFR.start` | — |
| MAT | 离线分析 hprof | Leak Suspects、Dominator Tree、Histogram | DevTools Memory 的 Retainers 视图 |
| Arthas | 阿里开源在线诊断 | `dashboard`、`thread -n 3`、`trace`、`watch`、`jad`、`profiler` | 给线上进程开了个 DevTools |
| JFR + JMC | 飞行记录仪 + 可视化 | `jcmd <pid> JFR.start duration=60s filename=a.jfr` | Performance 录制 |
| async-profiler | 火焰图 | `asprof -d 30 -f flame.html <pid>` | Performance 火焰图 |

`jstat -gcutil` 输出怎么读：

```
  S0     S1     E      O      M     CCS    YGC   YGCT    FGC    FGCT     CGC    CGCT     GCT
  0.00 100.00  45.21  62.30  95.10  92.40   1203  15.321    3   2.104     58   0.892   18.317
  ↑Survivor    ↑Eden  ↑老年代 ↑元空间      ↑Young GC 次数/总耗时 ↑Full GC 次数/耗时 ↑并发GC
```

关注点：**O（老年代使用率）是否只涨不降、FGC 是否在增长、YGC 频率与单次耗时（YGCT/YGC）**。

> ⚠️ `jmap -dump` 和 `jmap -histo:live` 都会触发 STW，堆越大停越久（10GB 堆可能停几十秒）。线上操作前**先把实例从负载均衡摘掉**。

---

## 3. 原理深挖

### 3.1 GC 算法

| 算法 | 过程 | 优点 | 缺点 | 用在哪 |
|---|---|---|---|---|
| 标记-清除 Mark-Sweep | 标记存活 → 清除未标记 | 简单，不移动对象 | **内存碎片**；分配需维护空闲链表 | CMS 老年代 |
| 复制 Copying | 内存分两块，存活对象复制到另一块 | 无碎片、分配用指针碰撞、只处理存活对象 | 浪费空间；存活率高时复制成本大 | 年轻代（Eden + 2 Survivor） |
| 标记-整理 Mark-Compact | 标记 → 存活对象向一端移动 → 清理边界外 | 无碎片、不浪费空间 | 移动对象要更新所有引用，停顿长 | Serial Old、Parallel Old |
| 分代收集 | 按对象年龄分区，各用合适的算法 | 扬长避短 | 需处理跨代引用 | 几乎所有现代 GC |

```
标记-清除：  [A][ ][B][ ][ ][C][ ]   → 碎片，大对象可能放不下
复制：      From[A][x][B][x] → To[A][B][   ][   ]   → 规整
标记-整理：  [A][x][B][x][x][C] → [A][B][C][      ]   → 规整，但要搬家
```

**分代假说**（V8 也基于同样的观察）：

1. 弱分代假说：**绝大多数对象朝生夕死**（一次请求里创建的 DTO、VO、临时集合）。
2. 强分代假说：熬过越多次 GC 的对象越难死（缓存、连接池、Spring Bean）。
3. 跨代引用假说：跨代引用相对少数。

**年轻代的复制过程：**

```
                Eden (80%)            S0 (10%)     S1 (10%)
① 新对象分配到  [■■■■■■■■■■] 满了 ──► Young GC
② 存活对象复制到                       [■■]（年龄+1）
   Eden 整体清空 [          ]
③ 下次 Young GC：Eden + S0 的存活对象 → S1，Eden、S0 清空（S0/S1 轮流做 To 区）
④ 年龄达到阈值（默认 15）或 Survivor 放不下 → 晋升老年代
⑤ 大对象（G1 中超过 Region 一半）直接进老年代（Humongous 区）
```

> V8 的新生代 Scavenge 是一模一样的半空间复制算法（from-space / to-space），对象熬过两次就晋升老生代。

**跨代引用怎么处理？** Young GC 只扫年轻代，但老年代的对象可能引用年轻代对象（也是 Root）。全扫老年代太贵，于是用 **卡表（Card Table）**：老年代按 512 字节划成卡页，某卡页中有对象引用了年轻代时，通过**写屏障**把对应卡标记为脏；Young GC 只扫脏卡。G1 在此基础上为每个 Region 维护 **记忆集（Remembered Set）**。

**三色标记与并发标记的难题**（CMS、G1、ZGC 共同的底层理论）：

```
白：尚未访问（标记结束仍为白 = 垃圾）
灰：自身已访问，但引用的对象还没扫完
黑：自身和引用都扫完了

并发标记时用户线程还在改引用，可能「漏标」——把活对象当垃圾回收掉（致命）：
   条件 1：黑对象新增了指向白对象的引用
   条件 2：灰对象删除了指向该白对象的所有引用
破坏任一条件即可：
   CMS：增量更新（记录条件 1 中的黑对象，重新标记阶段再扫）
   G1：原始快照 SATB（记录条件 2 中被删除的引用，按标记开始时的快照处理）
   ZGC：染色指针 + 读屏障
```

> 这正是 V8 的 Orinoco 并发标记也要用写屏障的原因——只要「标记」和「修改」同时发生，就必须有屏障。

### 3.2 收集器演进

```
年代：  1999          2004            2005~2017           2017（Java 9 默认）    2018~2023
       Serial  ──►  Parallel  ──►  CMS（并发标记清除）──►  G1（分区）    ──►   ZGC / Shenandoah
       单线程        多线程吞吐优先   低停顿先驱             平衡吞吐与停顿        亚毫秒级停顿
                                    Java 9 废弃/14 移除
```

| 收集器 | 年轻代/老年代 | 线程模型 | 停顿 | 适用 | 启用 |
|---|---|---|---|---|---|
| Serial / Serial Old | 复制 / 标记整理 | 单线程 STW | 长 | 客户端、<2 核或 <2GB 的小容器 | `-XX:+UseSerialGC` |
| Parallel / Parallel Old | 复制 / 标记整理 | 多线程 STW | 中 | 批处理、离线计算（吞吐优先） | `-XX:+UseParallelGC`（Java 8 默认） |
| CMS | 配合 ParNew / 标记清除 | 并发标记+清除 | 短，但有碎片和并发失败退化 | 已移除 | Java 14 移除 |
| G1 | Region 化分代，复制 | 并发标记 + 并行回收 | 可预测，几十～几百 ms | **通用默认，堆 4～32GB** | Java 9+ 默认 |
| ZGC | Region 化（分代 Java 21+），并发复制 | 几乎全并发 | **< 1ms，与堆大小无关** | 大堆、低延迟（交易、网关） | `-XX:+UseZGC` |
| Shenandoah | 类 ZGC | 几乎全并发 | < 10ms | Red Hat 系 | `-XX:+UseShenandoahGC` |

**Java 21 默认收集器**：JVM 判断为「服务器级机器」（≥2 个 CPU 且 ≥1792MB 内存）时用 **G1**，否则用 **Serial**。

> ⚠️ 容器陷阱：一个 `limits.cpu: 1` 的 Pod 里，JVM 看到 1 个 CPU，会**静默选择 Serial GC**。如果你发现线上 GC 停顿异常长，先 `jcmd <pid> VM.flags | grep GC` 确认实际用的是什么收集器。

### 3.3 G1 详解

```
传统分代：  [  年轻代（连续）  |        老年代（连续）           ]

G1：堆被划分为约 2048 个等大 Region（1～32MB，-XX:G1HeapRegionSize）
┌──┬──┬──┬──┬──┬──┬──┬──┐
│E │O │E │S │  │O │H │H │   E=Eden  S=Survivor  O=Old  H=Humongous(大对象)  空=Free
├──┼──┼──┼──┼──┼──┼──┼──┤
│O │  │E │O │O │  │E │  │   每个 Region 的角色是动态的
└──┴──┴──┴──┴──┴──┴──┴──┘
```

**G1 的三种回收：**

| 回收类型 | 触发 | 回收范围 | 说明 |
|---|---|---|---|
| Young GC | Eden Region 用完 | 所有年轻代 Region | STW，并行复制 |
| Mixed GC | 老年代占比超过 IHOP（`-XX:InitiatingHeapOccupancyPercent`，默认 45%，会自适应） | 全部年轻代 + **回收价值最高的部分老年代 Region** | 先经过并发标记周期，**按停顿目标挑 Region**——这就是 G1 名字 Garbage First 的由来 |
| Full GC | 回收速度跟不上分配（Evacuation Failure）、Humongous 分配失败、元空间满 | 整堆 | 退化为单线程（Java 10 起并行）标记整理，**要避免** |

**并发标记周期：**

```
初始标记(STW，借道 Young GC) → 并发标记 → 最终标记(STW，处理 SATB) → 清理(STW，统计各 Region 存活率) → Mixed GC × N 次
```

**G1 调优就一条主线**：设一个合理的 `MaxGCPauseMillis`，让 G1 自己调整年轻代大小；**不要再手动设 `-Xmn` / `NewRatio`**，否则停顿目标会失效。

### 3.4 ZGC：为什么能做到亚毫秒

- **染色指针（Colored Pointers）**：把对象的 GC 状态（标记位、重映射位）存在 64 位指针的高位里，不用访问对象本身就知道它处于什么状态。
- **读屏障（Load Barrier）**：用户线程从堆中读取引用时，若发现指针「颜色」不对（对象已被搬走），当场修正为新地址（自愈）。
- **并发转移**：标记、转移、重定位全部并发进行，STW 只剩扫描 GC Roots，且耗时与堆大小无关。
- **代价**：读屏障带来约 5%～10% 的吞吐损失；Java 21 之前不分代，回收频率高、更吃 CPU。**Java 21 的分代 ZGC（JEP 439）** 解决了这个问题。

**选型建议（Java 21）：**

```
堆 < 2GB 或 CPU = 1 ───────────────────► Serial（或至少给 2 核再用 G1）
离线批处理，只关心吞吐 ─────────────────► Parallel
普通业务服务（4～16GB 堆，P99 要求百毫秒级）──► G1（默认，先用它）
大堆（>16GB）或 P99 要求 10ms 以内 ──────► 分代 ZGC：-XX:+UseZGC -XX:+ZGenerational
```

### 3.5 解释执行 + JIT：对照 V8

```
              V8                                     HotSpot（Java 21）
JS 源码 → 解析 → AST                       .class 字节码（已由 javac 编译好）
   │                                              │
Ignition 解释器（生成并执行 bytecode）        解释器（模板解释器）               ← 第 0 层
   │ 收集类型反馈 (Feedback Vector)               │ 收集 profile（调用次数、分支、类型）
   ▼                                              ▼
Sparkplug / Maglev（快速编译）                 C1 编译器（快速、轻度优化）       ← 第 1~3 层
   │                                              │
TurboFan（重度优化）                           C2 编译器（重度优化）             ← 第 4 层
   │ 假设被打破 → 去优化 (Deopt)                   │ 假设被打破 → 去优化，回到解释器
```

**分层编译（Tiered Compilation）5 个层级：**

| 层 | 执行方式 | 说明 |
|---|---|---|
| 0 | 解释执行 | 启动时所有方法都在这层 |
| 1 | C1，无 profiling | 简单方法（如 getter），编到这层就够了 |
| 2 | C1，有限 profiling | C2 队列太忙时的过渡 |
| 3 | C1，完整 profiling | 最常见的路径：收集数据给 C2 用 |
| 4 | C2 | 基于 profile 激进优化，峰值性能 |

触发编译靠计数器：方法调用计数器 + 回边计数器（循环次数）。循环特别热时还会做 **OSR（栈上替换）**，在循环执行中途换成编译后的代码。

**C2 的主要优化手段：**

| 优化 | 说明 | V8 是否有 |
|---|---|---|
| 方法内联 | 把被调方法体直接展开，消除调用开销，是其他优化的前提 | 有 |
| 去虚拟化 | `List list` 实际永远是 `ArrayList` → 直接调用 `ArrayList.get`（类层次分析 CHA + 类型 profile） | 有（Inline Cache） |
| 逃逸分析 | 见下文 | 有（TurboFan 也做） |
| 循环优化 | 循环展开、范围检查消除、向量化 | 有 |
| 空值检查消除 | 用隐式的段错误信号代替显式 `if (x == null)` | — |

**逃逸分析（Escape Analysis）**：分析对象的作用域是否「逃出」方法。

```java
/**
 * 演示逃逸分析：未逃逸的对象可能被标量替换，不在堆上分配。
 */
public class EscapeDemo {

    /** 金额区间，仅用于演示 */
    record PriceRange(long min, long max) { }

    /**
     * 判断价格是否在区间内。PriceRange 只在方法内使用，未逃逸。
     *
     * @param price 价格（分）
     * @return 是否在 [100, 10000] 之间
     */
    public boolean inRange(long price) {
        // C2 编译后：range 对象不会真的 new，而被「标量替换」为两个局部变量 min=100, max=10000
        PriceRange range = new PriceRange(100, 10_000);
        return price >= range.min() && price <= range.max();
    }

    /** 最近一次记录的区间（静态字段，用于演示全局逃逸） */
    private static PriceRange lastRange;

    /**
     * 对比：对象被赋给静态字段，发生「全局逃逸」，必须在堆上分配。
     *
     * @param min 下限
     * @param max 上限
     */
    public void remember(long min, long max) {
        lastRange = new PriceRange(min, max);
    }
}
```

逃逸分析带来三种优化：**标量替换**（对象拆成局部变量，等效于栈上分配）、**锁消除**（对象不逃逸，对它加的 `synchronized` 直接去掉）、栈上分配（HotSpot 实际通过标量替换实现）。

> 💡 高级认知：**写 Java 不需要像写 JS 那样刻意避免「变形」**（V8 怕对象形状变化导致 megamorphic）。但有两个类似的坑：①方法过大（>8000 字节码）不会被 JIT 编译（`-XX:-DontCompileHugeMethods` 才放开）；②接口有 3 个以上实现类在同一调用点频繁切换时（megamorphic），去虚拟化失效。

**预热（Warm-up）问题**：服务刚启动时全是解释执行，RT 可能是稳定后的数倍。发布时常见现象「新实例上线的前 1 分钟接口超时」。对策：
- 网关/注册中心做**流量预热**（Nacos、Dubbo 支持按启动时间逐步加权）；
- 启动后用脚本自调热点接口；
- Java 21 可用 CDS/AppCDS 加速类加载；更激进的方案是 CRaC（检查点恢复）或 GraalVM Native Image（AOT 编译，启动毫秒级，但牺牲反射等动态特性）。

### 3.6 容器环境下的 JVM

在 K8s 中最常见的事故：**Pod 被 OOMKilled（退出码 137），但应用日志里没有任何 OOM 异常。**

原因链路：

```
容器 limits.memory = 4Gi
      │
JVM 进程实际占用 = 堆(-Xmx) + 元空间 + 线程栈(线程数 × Xss) + 直接内存 + CodeCache + GC 自身结构 + JNI/glibc malloc
      │
若 -Xmx4g → 堆还没满，总占用已超 4Gi → cgroup 直接 kill -9 → JVM 来不及 dump，也打不出日志
```

| 问题 | 历史 | 现状 |
|---|---|---|
| JVM 看不到容器限额 | Java 8u131 之前读的是宿主机内存/CPU，64G 宿主机上默认堆 16G | Java 8u191+ / 10+ 默认 `-XX:+UseContainerSupport`，能识别 cgroup v1；Java 17（及 11.0.16+、8u372+）支持 cgroup v2 |
| 默认堆只占 25% | `MaxRAMPercentage` 默认 25.0 | 4G 容器默认只用 1G 堆，浪费 |

**推荐做法：**

```yaml
# K8s Deployment 片段
resources:
  requests: { cpu: "2", memory: "4Gi" }
  limits:   { cpu: "2", memory: "4Gi" }     # 内存 requests = limits，避免被驱逐
env:
  - name: JAVA_TOOL_OPTIONS
    value: >-
      -XX:MaxRAMPercentage=75.0
      -XX:InitialRAMPercentage=75.0
      -XX:+HeapDumpOnOutOfMemoryError
      -XX:HeapDumpPath=/data/dump/
```

- 堆用 **百分比** 而非写死 `-Xmx`，改 Pod 规格时不用改启动参数。
- **75% 是上限经验值**，给非堆留至少 25%（且不少于 ~1GB）；大量用 Netty / 线程数多的服务降到 60%～65%。
- `HeapDumpPath` 要挂载**持久卷**，否则 Pod 重启后 dump 文件随容器销毁。
- 怀疑非堆内存泄漏时开 `-XX:NativeMemoryTracking=summary`，用 `jcmd <pid> VM.native_memory summary` 看各区域占用。
- CPU：`limits.cpu` 小于 2 时，GC 线程数、`ForkJoinPool` 并行度、默认收集器都会受影响，可用 `-XX:ActiveProcessorCount=N` 显式指定。

---

## 4. mini-mall 实战：一次性加载百万订单导致 OOM

### 4.1 场景

运营要求「导出全部订单为 CSV」。新人写出了这样的代码：

```java
package com.example.mall.biz;

import com.example.mall.dao.OrderDao;
import com.example.mall.model.po.OrderPO;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.io.Writer;
import java.util.List;

/**
 * 订单导出编排组件（第二层：编排层）。—— 有问题的第一版
 */
@Component
public class OrderExportBizComponent {

    private final OrderDao orderDao;

    /**
     * 构造注入。
     *
     * @param orderDao 订单 DAO
     */
    public OrderExportBizComponent(OrderDao orderDao) {
        this.orderDao = orderDao;
    }

    /**
     * 导出全部订单到 CSV。
     *
     * @param writer CSV 输出目标
     * @throws IOException 写出失败
     */
    public void exportAll(Writer writer) throws IOException {
        // ❌ 一次性把 t_order 全表 100 万行查进内存
        List<OrderPO> orders = orderDao.listAll();
        for (OrderPO order : orders) {
            writer.write(order.getOrderNo() + "," + order.getTotalAmount() + "\n");
        }
    }
}
```

测试环境 1 万条数据，一切正常；上线后数据量 100 万，第一次点击导出，服务挂了。

### 4.2 复现

不依赖数据库也能稳定复现（模拟 DAO 返回 100 万个订单对象）：

```java
package com.example.mall.lab;

import com.example.mall.model.enums.OrderStatusEnum;
import com.example.mall.model.po.OrderPO;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * OOM 复现实验：模拟一次性加载百万订单。
 * 运行参数：-Xmx256m -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=./dump/ -Xlog:gc
 */
public class OrderOomLab {

    /** 模拟的订单总数 */
    private static final int TOTAL = 1_000_000;

    /**
     * 程序入口。
     *
     * @param args 命令行参数（未使用）
     */
    public static void main(String[] args) {
        List<OrderPO> orders = mockListAll();
        System.out.println("加载完成：" + orders.size());
    }

    /**
     * 模拟 orderDao.listAll()：把全部订单放进一个 List 返回。
     *
     * @return 全部订单
     */
    private static List<OrderPO> mockListAll() {
        List<OrderPO> list = new ArrayList<>();
        for (long i = 1; i <= TOTAL; i++) {
            list.add(buildOrder(i));          // 所有对象被 list 强引用，GC 无法回收
        }
        return list;
    }

    /**
     * 构造一个模拟订单。
     *
     * @param id 订单 ID
     * @return 订单实体
     */
    private static OrderPO buildOrder(long id) {
        OrderPO po = new OrderPO();
        po.setId(id);
        po.setOrderNo("MM" + String.format("%018d", id));     // 20 位订单号
        po.setUserId(id % 10_000);
        po.setTotalAmount(new BigDecimal("199.00"));
        po.setStatus(OrderStatusEnum.PAID.getCode());
        po.setCreateTime(LocalDateTime.now());
        po.setUpdateTime(LocalDateTime.now());
        return po;
    }
}
```

运行结果：

```
[0.912s][info][gc] GC(12) Pause Young (Normal) (G1 Evacuation Pause) 180M->176M(256M) 21.3ms
[1.204s][info][gc] GC(15) Pause Full (G1 Compaction Pause) 255M->254M(256M) 310.5ms   ← Full GC 回收不掉任何东西
[1.530s][info][gc] GC(16) Pause Full (G1 Compaction Pause) 255M->255M(256M) 298.1ms
java.lang.OutOfMemoryError: Java heap space
Dumping heap to ./dump/java_pid41235.hprof ...
Heap dump file created [268435612 bytes in 1.102 secs]
```

> 观察信号：**Full GC 后内存几乎不下降**（255M→254M）= 对象全部存活 = 要么真的需要这么多内存，要么有东西一直引用着它们。

### 4.3 用 MAT 定位

打开 `java_pid41235.hprof`（MAT 需要的内存比 dump 文件大，大文件可用 `ParseHeapDump.sh` 在服务器上离线解析）：

**① Leak Suspects（泄漏嫌疑报告）**

```
Problem Suspect 1
One instance of "java.util.ArrayList" loaded by "<system class loader>"
occupies 241,563,280 (94.12%) bytes.
The memory is accumulated in one instance of "java.lang.Object[]" ...
Keywords: java.util.ArrayList  java.lang.Object[]
```

**② Dominator Tree（支配树：谁「独占」了这些内存）**

| Class Name | Shallow Heap | Retained Heap | Percentage |
|---|---|---|---|
| `java.lang.Thread @ 0x... main` | 120 | 241,570,104 | 94.12% |
| └ `java.util.ArrayList @ 0x...` | 24 | 241,563,280 | 94.12% |
| &nbsp;&nbsp;└ `java.lang.Object[688,931]` | 2,755,744 | 241,563,256 | 94.12% |
| &nbsp;&nbsp;&nbsp;&nbsp;└ `com.example.mall.model.po.OrderPO @ ...` | 40 | 352 | 0.00% |

**③ 查看 GC Root 路径**：在 ArrayList 上右键 → *Path To GC Roots → exclude weak/soft references*：

```
java.lang.Thread "main"                              ← GC Root：线程栈
  └─ <Java Local> OrderOomLab.mockListAll() 局部变量 list
       └─ java.util.ArrayList
            └─ elementData Object[]
                 └─ OrderPO × 688,931
```

**④ Thread Overview**：在线上 dump 里看 OOM 发生时的线程栈，会直接看到 `OrderExportBizComponent.exportAll` → `OrderDao.listAll` 这一帧，定位到具体代码行。

**结论**：每个 `OrderPO` 保留大小约 352 字节，68 万个时已用掉 240MB，与 2.4 节的估算吻合。根因不是泄漏，而是**一次性把无界数据集加载进内存**。

> MAT 的 **Histogram** 视图按类统计数量和大小，类似 DevTools 的 Summary 视图；**Dominator Tree** 类似 Retainers 视图里的 Retained Size 排序。两者结合：先找「谁最多」，再找「谁持有它们」。

### 4.4 修复：游标分页（推荐）

思路：**每次只取一批（如 1000 条），处理完就丢弃，内存占用恒定**。

为什么不用 `LIMIT offset, size`？深分页时 MySQL 要先扫描并丢弃前 offset 行，越往后越慢（`LIMIT 990000, 1000` 要扫 99 万行）。用「上一批最大 id」作为游标，每次都走主键索引，耗时恒定（08 章详解）。

**第四层：DAO 提供游标查询能力**

```java
package com.example.mall.dao;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.example.mall.dao.mapper.OrderMapper;
import com.example.mall.model.po.OrderPO;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * 订单 DAO（第四层：能力单元，封装 t_order 读写）。
 */
@Repository
public class OrderDao {

    private final OrderMapper orderMapper;

    /**
     * 构造注入。
     *
     * @param orderMapper MyBatis-Plus 生成的订单 Mapper
     */
    public OrderDao(OrderMapper orderMapper) {
        this.orderMapper = orderMapper;
    }

    /**
     * 按主键游标分批查询订单：WHERE id > lastId ORDER BY id LIMIT batchSize。
     *
     * @param lastId    上一批最后一条的 id，首次传 0
     * @param batchSize 每批条数，建议 500～2000
     * @return 本批订单，按 id 升序；为空表示已查完
     */
    public List<OrderPO> scanByIdCursor(long lastId, int batchSize) {
        LambdaQueryWrapper<OrderPO> wrapper = new LambdaQueryWrapper<OrderPO>()
                .gt(OrderPO::getId, lastId)
                .orderByAsc(OrderPO::getId)
                .last("LIMIT " + batchSize);   // batchSize 为内部受控 int，无注入风险
        return orderMapper.selectList(wrapper);
    }
}
```

**第二层：编排组件改为分批处理**

```java
package com.example.mall.biz;

import com.example.mall.dao.OrderDao;
import com.example.mall.model.po.OrderPO;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.io.Writer;
import java.util.List;

/**
 * 订单导出编排组件（第二层：编排层）。—— 修复版：游标分批，内存占用恒定。
 */
@Component
public class OrderExportBizComponent {

    /** 每批读取条数 */
    private static final int BATCH_SIZE = 1000;

    private final OrderDao orderDao;

    /**
     * 构造注入。
     *
     * @param orderDao 订单 DAO
     */
    public OrderExportBizComponent(OrderDao orderDao) {
        this.orderDao = orderDao;
    }

    /**
     * 导出全部订单到 CSV，按主键游标分批读取。
     *
     * @param writer CSV 输出目标（调用方负责关闭）
     * @return 导出的总行数
     * @throws IOException 写出失败
     */
    public long exportAll(Writer writer) throws IOException {
        writer.write("order_no,user_id,total_amount,status\n");
        long lastId = 0L;
        long total = 0L;
        while (true) {
            // 1. 读一批：只走主键索引，每批耗时稳定
            List<OrderPO> batch = orderDao.scanByIdCursor(lastId, BATCH_SIZE);
            if (batch.isEmpty()) {
                break;
            }
            // 2. 写一批：处理完后 batch 不再被引用，下一次 Young GC 即可回收
            writeBatch(writer, batch);
            total += batch.size();
            // 3. 推进游标
            lastId = batch.get(batch.size() - 1).getId();
        }
        writer.flush();
        return total;
    }

    /**
     * 把一批订单写成 CSV 行。
     *
     * @param writer 输出目标
     * @param batch  一批订单
     * @throws IOException 写出失败
     */
    private void writeBatch(Writer writer, List<OrderPO> batch) throws IOException {
        for (OrderPO o : batch) {
            writer.write(o.getOrderNo() + "," + o.getUserId() + ","
                    + o.getTotalAmount().toPlainString() + "," + o.getStatus() + "\n");
        }
    }
}
```

### 4.5 备选：MyBatis 流式查询（Cursor）

一条 SQL、服务端逐行推送，适合不方便按 id 切分的复杂查询：

```java
package com.example.mall.dao.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.example.mall.model.po.OrderPO;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.cursor.Cursor;
import org.apache.ibatis.mapping.ResultSetType;

/**
 * 订单 Mapper（MyBatis-Plus）。
 */
public interface OrderMapper extends BaseMapper<OrderPO> {

    /**
     * 流式扫描全部订单。fetchSize = Integer.MIN_VALUE 让 MySQL 驱动逐行返回，而不是一次读完结果集。
     *
     * @return 订单游标，必须在事务（或打开的 SqlSession）内迭代，用完关闭
     */
    @Select("SELECT id, order_no, user_id, total_amount, status FROM t_order")
    @Options(resultSetType = ResultSetType.FORWARD_ONLY, fetchSize = Integer.MIN_VALUE)
    Cursor<OrderPO> streamAll();
}
```

调用侧必须在 `@Transactional(readOnly = true)` 方法里用 `try (Cursor<OrderPO> cursor = orderMapper.streamAll()) { for (OrderPO o : cursor) {...} }` 迭代，否则方法返回后连接已归还，游标读取会报错。

| 方案 | 内存 | 数据库压力 | 断点续传 | 推荐场景 |
|---|---|---|---|---|
| 一次性 `listAll` | O(N) ❌ | 一次大查询 | 不支持 | 只适用于确定很小的表 |
| `LIMIT offset` 分页 | O(批) | 深分页越来越慢 | 支持 | 数据量 < 10 万 |
| **主键游标分页** | O(批) | 稳定 | 支持（记录 lastId） | **默认选择** |
| 流式 Cursor | O(1 行) | 长时间占用连接 | 不支持 | 复杂查询、单次导出 |

### 4.6 验证与防御

- 再用 `-Xmx256m` 跑修复后的导出，`jstat -gcutil <pid> 1000` 观察：O（老年代）保持平稳，只有 YGC 在增长，FGC 为 0。
- 防御措施（编排层兜底）：导出接口限制时间范围、单次最大行数（如 50 万），超出改为异步任务 + 文件下载链接（04 章用线程池实现异步导出）。
- 代码评审红线：**任何 `listAll()` / 无 `WHERE` + `LIMIT` 的查询都要打问号**；MyBatis-Plus 可加 `BlockAttackInnerInterceptor` 阻止全表更新删除。

---

## 5. 常见坑

| # | 坑 | 后果 | 正确做法 |
|---|---|---|---|
| 1 | 容器里用 `-Xmx` 等于容器内存 | OOMKilled（137），无 dump 无日志 | `-XX:MaxRAMPercentage=75` 或更低，给非堆留余量 |
| 2 | 没开 `HeapDumpOnOutOfMemoryError` | OOM 后现场丢失，只能猜 | 生产必开，dump 路径挂持久卷 |
| 3 | 把 `-Xms` 设得很小 | 堆反复扩容、频繁 GC | 生产 `Xms = Xmx`（或 `InitialRAMPercentage = MaxRAMPercentage`） |
| 4 | 代码里调用 `System.gc()` | 触发 Full GC 造成停顿 | 删掉；必要时 `-XX:+DisableExplicitGC`（注意 NIO 直接内存依赖它回收，用 Netty 时慎开） |
| 5 | 用 `static Map` 做缓存 | 缓慢泄漏，几天后 OOM | Caffeine（有界 + 过期）或 Redis |
| 6 | `ThreadLocal` 用完不 `remove` | 线程池场景下泄漏 + 串数据 | `try/finally` 中 `remove()`（04 章） |
| 7 | 线上直接 `jmap -dump` | 大堆 STW 数十秒，接口全超时 | 先摘流量；或依赖 OOM 自动 dump |
| 8 | 一次性加载大结果集 / 大文件 | OOM | 分页、流式、`BufferedReader` 逐行读 |
| 9 | 盲目套用网上的 GC 参数模板 | 参数冲突，性能更差 | 默认值 + 监控 + 有证据再调 |
| 10 | 动态生成类不缓存（如每次 `new` 一个 CGLIB 代理、Groovy 脚本反复编译） | `Metaspace` OOM | 缓存生成的类；给 `MaxMetaspaceSize` 设上限便于早发现 |
| 11 | 堆设到 32GB 以上 | 指针压缩失效，可用空间反而变小 | 不超过 31GB，更大内存考虑多实例或 ZGC |
| 12 | 以为 `OutOfMemoryError` 可以 `catch` 后继续跑 | 进程状态已不可信 | 不捕获 Error；配 `ExitOnOutOfMemoryError` 让平台重启 |

---

## 6. 高级视角

### 6.1 OOM 类型速查

| 报错信息 | 区域 | 常见原因 | 第一步动作 |
|---|---|---|---|
| `Java heap space` | 堆 | 大结果集、内存泄漏（集合只增不减）、堆太小 | 分析 heap dump（Dominator Tree） |
| `GC overhead limit exceeded` | 堆 | 98% 时间在 GC 却只回收不到 2%（Parallel GC 的保护机制） | 同上，本质是快要 heap space 了 |
| `Metaspace` | 元空间 | 动态代理/字节码生成泄漏、热部署类加载器泄漏 | `jcmd <pid> VM.classloader_stats`、MAT 看 ClassLoader 数量 |
| `Direct buffer memory` | 直接内存 | Netty `ByteBuf` 未 `release`、NIO 使用不当 | 开 Netty 泄漏检测 `-Dio.netty.leakDetection.level=paranoid`（仅测试环境） |
| `unable to create native thread` | 操作系统 | 线程数过多（无界线程池）、ulimit/容器 pid 限制 | `jstack` 数线程、找出创建线程的池（04 章） |
| `Requested array size exceeds VM limit` | 堆 | 试图创建超大数组 | 检查代码中的数组/集合扩容 |
| `StackOverflowError`（不是 OOM，但常一起问） | 栈 | 无限递归、`toString`/`equals` 循环引用（Lombok `@Data` 双向关联） | 看堆栈中重复的帧 |
| **Pod OOMKilled（137）** | 进程总内存 | 堆比例过高、堆外泄漏 | `kubectl describe pod` 看 `Last State`；NMT 对比各区域 |

### 6.2 OOM 排查 SOP

```
告警：服务 OOM / 实例重启
  │
  ├─① 止血：确认是否有实例存活；扩容或重启恢复服务；有异常导出/批量任务就先下线入口
  │
  ├─② 定类型：看日志中 OutOfMemoryError 后面的描述；没日志看 K8s 事件是否 OOMKilled
  │      └─ 不同类型走 6.1 表格的不同分支
  │
  ├─③ 拿现场：
  │      ├─ 有自动 dump → 从持久卷取回 .hprof
  │      └─ 没有 → 在一台问题未恢复的实例上摘流量后 jcmd <pid> GC.heap_dump /data/dump/h.hprof
  │      同时保留：GC 日志、OOM 前后 10 分钟的业务日志、监控截图（堆、GC 次数、QPS）
  │
  ├─④ 分析（MAT）：
  │      Leak Suspects → Dominator Tree 找最大对象 → Path To GC Roots 找持有者
  │      → Thread Overview 找当时执行的业务代码
  │
  ├─⑤ 判性质：
  │      ├─ 「大」：单次请求加载过多数据（本章案例）→ 分页/流式/限制条件
  │      └─ 「漏」：内存随时间单调上涨，Full GC 也降不下来 → 找只增不减的集合/缓存/监听器
  │
  └─⑥ 修复 + 复盘：修代码 → 压测验证 → 加监控（老年代使用率告警）→ 写入 Code Review 清单
```

> 判断「大」还是「漏」：看堆监控曲线。**锯齿形且每次 GC 后基线持平 = 正常；每次 GC 后基线持续抬高 = 泄漏；突然垂直拉满 = 大对象/大查询。**

### 6.3 CPU 飙高排查 SOP

```
① 找进程：  top                         → 找到 CPU 最高的 java 进程 PID，例如 12345
② 找线程：  top -Hp 12345               → 找到 CPU 最高的线程 TID，例如 12401
③ 转 16 进制：printf '%x\n' 12401       → 3071
④ 看线程栈：jstack 12345 | grep -A 30 'nid=0x3071'
            （多抓 3 次、间隔 5 秒，看是否一直停在同一段代码）
⑤ 判断：
   ├─ 线程名是 "GC Thread#"/"G1 Conc#" → 不是业务代码，是 GC 忙 → 转 6.4 Full GC 排查
   ├─ 线程名是 "C2 CompilerThread"     → 刚启动在 JIT 编译，通常几分钟内回落
   └─ 业务线程（http-nio-8080-exec-xx） → 看栈顶：死循环？正则回溯？大集合排序？序列化大对象？
```

**用 Arthas 一步到位（推荐）：**

```bash
curl -O https://arthas.aliyun.com/arthas-boot.jar && java -jar arthas-boot.jar   # 选择目标进程
[arthas]$ dashboard            # 总览：线程 CPU 排行、堆、GC
[arthas]$ thread -n 3          # CPU 最高的 3 个线程及其完整栈
[arthas]$ thread -b            # 找出阻塞其他线程的那个线程（死锁/锁竞争）
[arthas]$ profiler start       # 采样 30 秒后 profiler stop --format html 生成火焰图
[arthas]$ trace com.example.mall.biz.OrderBizComponent getOrderDetail '#cost > 200'  # 只看耗时 >200ms 的调用路径
```

**常见元凶**：正则灾难性回溯、`HashMap` 并发扩容死循环（Java 7）、无退出条件的 `while(true)` 重试、大 JSON 序列化、频繁 GC、自旋锁空转、日志打印巨大对象。

### 6.4 Full GC 频繁排查

先用 `jstat -gcutil <pid> 1000` 和 GC 日志确认现象，再按原因分支：

| 现象（GC 日志 / jstat） | 原因 | 处理 |
|---|---|---|
| Full GC 后老年代几乎不降 | 内存泄漏或真实数据量太大 | heap dump 分析（6.2） |
| Full GC 后老年代大幅下降，但很快又满 | 对象**过早晋升**：Survivor 太小 / 短命对象太大（一次请求创建大量对象） | 降低单次请求的对象分配；G1 下检查是否手动设了 `-Xmn` 破坏了自适应 |
| 日志出现 `Humongous` 大量分配 | 大对象（超过 Region 一半）直接进老年代 | 减小大数组/大 `byte[]`；或调大 `G1HeapRegionSize` |
| `Pause Full (Metadata GC Threshold)` | 元空间满 | 调大 `MetaspaceSize`，或排查类加载泄漏 |
| `Pause Full (System.gc())` | 代码或依赖显式调用 | 找出调用方（Arthas `stack java.lang.System gc`） |
| `to-space exhausted` / `Evacuation Failure` | G1 来不及回收（分配速率太高 / 堆太小 / IHOP 太高） | 扩大堆；降低 `InitiatingHeapOccupancyPercent`；减少分配 |

**看懂一行 G1 日志：**

```
[2026-11-26T10:20:31.512+0800][info][gc] GC(1024) Pause Young (Mixed) (G1 Evacuation Pause) 3412M->1210M(4096M) 48.317ms
                                          ↑序号   ↑类型：Mixed GC     ↑触发原因            ↑GC前->GC后(堆总量) ↑停顿时长
```

### 6.5 监控指标（12 章展开）

| 指标 | 告警阈值参考 | 含义 |
|---|---|---|
| 老年代使用率（GC 后） | > 80% 持续 10 分钟 | 泄漏或堆不足 |
| Full GC 次数 | > 0 次/小时（G1 下正常应接近 0） | G1 退化 |
| GC 停顿 P99 | > 目标值 2 倍 | 收集器选型/参数问题 |
| 线程数 | 突增或持续上涨 | 线程池配置不当、线程泄漏 |
| 元空间使用率 | 持续上涨 | 类加载泄漏 |
| 容器内存使用率（RSS / limit） | > 90% | 即将 OOMKilled |

Spring Boot 只需引入 `spring-boot-starter-actuator` + `micrometer-registry-prometheus`，以上 JVM 指标（`jvm_memory_used_bytes`、`jvm_gc_pause_seconds` 等）自动暴露。

### 6.6 高级工程师的 JVM 观

1. **JVM 调优 ≠ 调参数**。90% 的「GC 问题」根因在代码：大查询、无界缓存、对象分配过多。先改代码，再动参数。
2. **吞吐、延迟、内存是不可能三角**。Parallel 要吞吐，ZGC 要延迟，Serial 要省内存。先明确业务目标再选型。
3. **可观测先于问题**：上线前 GC 日志、OOM dump、JFR、指标告警都要就位。出了事再加参数，现场已经没了。
4. **把 JVM 当成容器里的一个进程看**：内存 = 堆 + 一堆非堆；CPU 限额影响 GC 线程数和默认收集器。

---

## 7. 小练习

1. **看字节码**：写一个包含 `i++` 和字符串拼接 `"a" + b + c` 的方法，用 `javap -c` 反编译。观察 `i++` 对应几条指令（04 章会用到），以及 Java 9+ 字符串拼接被编译成了 `invokedynamic`（`StringConcatFactory`）。
2. **测对象大小**：引入 JOL，打印 `OrderPO`、`new Object()`、`new int[10]` 的内存布局；再加 `-XX:-UseCompressedOops` 对比差异。
3. **复现 OOM**：运行 4.2 的 `OrderOomLab`（`-Xmx256m`），用 MAT 打开 dump，独立找到 Dominator Tree 和 GC Root 路径。再把 `TOTAL` 改为 50 万、堆改为 512m，用 `jstat -gcutil` 观察 Young GC 与晋升过程。
4. **对比收集器**：同一个程序分别用 `-XX:+UseSerialGC`、`-XX:+UseParallelGC`、`-XX:+UseG1GC`、`-XX:+UseZGC -XX:+ZGenerational` 运行，开 `-Xlog:gc`，比较停顿时间和总耗时。
5. **容器默认值**：在 `docker run -m 1g --cpus=1 eclipse-temurin:21` 容器中执行 `java -XX:+PrintFlagsFinal -version | grep -E 'MaxHeapSize|UseSerialGC|UseG1GC'`，验证默认堆为 1/4、默认收集器为 Serial；改为 `--cpus=2 -m 2g` 再看。
6. **CPU 排查演练**：写一个在某个接口里死循环的 Spring Boot 程序，用「top → top -Hp → printf → jstack」走一遍 SOP，再用 Arthas `thread -n 3` 验证。
7. **打破双亲委派**：写一个自定义 `ClassLoader` 从指定目录加载 `OrderPO.class`，验证它和 AppClassLoader 加载的 `OrderPO` 之间 `instanceof` 返回 false。
