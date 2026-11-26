> [← 总纲](./00-outline.md) | [上一章：03 JVM 原理](./03-jvm.md) | [下一章：05 工程化](./05-engineering.md)

# 04 并发编程：从事件循环到多线程

---

## 0. 本章地图

```
            前端 / Node 的世界                          Java 服务端的世界
   ┌───────────────────────────────┐        ┌──────────────────────────────────────┐
   │  一个 JS 线程 + 事件循环        │        │  Tomcat 线程池（默认最多 200 个线程） │
   │  I/O 交给 libuv / 内核          │  ───►  │  每个请求占一个线程，同步阻塞地跑完    │
   │  天然没有「两段 JS 同时执行」    │        │  多个线程同时读写同一块堆内存          │
   └───────────────────────────────┘        └──────────────────────────────────────┘
                                                     ▼
                                       线程安全问题：超卖、计数不准、数据错乱
```

本章是前端转 Java 最需要「从零建立」的一章：

| 模块 | 小节 | 解决什么问题 |
|---|---|---|
| 为什么要多线程 | 1、2.1 | 理解 Java 和 Node 两种并发模型的根本差异 |
| 线程基础 | 2.2 | 创建线程、线程状态 |
| 线程安全 | 2.3～2.7、3.1～3.4 | 原子性/可见性/有序性；`synchronized`、`volatile`、锁、CAS、AQS |
| 并发工具 | 2.8～2.11 | 同步器、线程池、`ConcurrentHashMap`、`ThreadLocal` |
| 异步编排 | 2.12 | `CompletableFuture`（对照 Promise） |
| 新时代 | 2.13、3.6 | Java 21 虚拟线程（对照 async/await） |
| 排障 | 2.14 | 死锁 |
| 实战 | 4 | 订单详情并行查询、导出线程池、并发扣库存 |

---

## 1. 前端类比：为什么服务端需要多线程

### 1.1 Node 是怎么做并发的

```
           ┌──────────── Node 进程 ────────────┐
请求 A ──► │ JS 主线程（只有一个）              │
请求 B ──► │   事件循环：timers → poll → check  │
请求 C ──► │      │ 遇到 I/O 就注册回调，立即处理下一个请求
           │      ▼                             │
           │  libuv                             │
           │   ├─ 网络 I/O：epoll/kqueue（不占线程）│
           │   └─ 线程池（默认 4 个，UV_THREADPOOL_SIZE）：fs、dns.lookup、crypto、zlib │
           └────────────────────────────────────┘
```

Node 的前提是：**所有 I/O 都是非阻塞的**，`await db.query()` 期间主线程去干别的事。

### 1.2 Java 传统模型：一个请求一个线程

```
           ┌──────────── JVM 进程 ─────────────────────────────┐
请求 A ──► │ http-nio-8080-exec-1：校验 → 查库(阻塞 20ms) → 返回 │
请求 B ──► │ http-nio-8080-exec-2：校验 → 调支付(阻塞 300ms) → 返回│
请求 C ──► │ http-nio-8080-exec-3：...                           │
           │        ↑ 所有线程共享同一个堆：Spring Bean、缓存、静态变量 │
           └────────────────────────────────────────────────────┘
```

为什么 Java 走了这条路：

| 原因 | 说明 |
|---|---|
| 生态是阻塞的 | JDBC、大部分 HTTP 客户端、文件 IO 都是同步阻塞 API。线程在等数据库时什么都干不了，只能用更多线程撑并发 |
| 利用多核 | Node 一个进程只能用一个核（要靠 cluster/PM2 多进程）；Java 一个进程的多线程天然铺满所有核 |
| 代码直观 | 同步写法，异常栈完整，调试简单。代价是**线程贵**（每个约 1MB 栈 + 内核调度），撑不了几万并发 |
| 共享内存 | 多线程共享堆，本地缓存、连接池全进程共用——效率高，但带来了**线程安全问题** |

> Java 21 的虚拟线程把「同步写法」和「Node 级的高并发」统一了起来（2.13）。但无论平台线程还是虚拟线程，**共享内存带来的线程安全问题都不会消失**，这是本章的重点。

### 1.3 概念对照

| 前端 / Node | Java | 关键差异 |
|---|---|---|
| 单线程事件循环 | 线程池 + 每请求一线程 | Java 多段代码**真正同时**执行 |
| `await fetch()` | 同步调用（线程阻塞等待） | Java 不需要关键字传染（没有「函数染色」问题） |
| `Promise` | `CompletableFuture` | 回调可能在别的线程执行 |
| `Promise.all` / `race` | `allOf` / `anyOf` | `allOf` 返回 `CompletableFuture<Void>`，要再逐个 `join` 拿结果 |
| Web Worker / `worker_threads` | `Thread` / `ExecutorService` | Worker 之间默认不共享内存（`postMessage` 拷贝）；Java 线程**默认共享** |
| `SharedArrayBuffer` + `Atomics.add` | `AtomicInteger.incrementAndGet` | JS 里罕见的场景，在 Java 里是日常 |
| 无 | `synchronized` / `Lock` / `volatile` | 前端几乎用不到，必须从零学 |
| `AsyncLocalStorage`（Node） | `ThreadLocal` | 请求级上下文（用户、TraceId）的存放处 |

---

## 2. 核心概念

### 2.1 进程、线程、协程

| | 进程 | 线程（平台线程） | 协程 / 虚拟线程 |
|---|---|---|---|
| 是什么 | 资源分配单位（独立地址空间） | CPU 调度单位（共享进程内存） | 用户态的轻量执行单元 |
| 创建成本 | 高（fork、页表） | 中（约 1MB 栈 + 内核对象，~几十 µs） | 极低（几百字节起，堆上分配） |
| 切换成本 | 高 | 中（内核态切换，~µs 级） | 低（用户态切换） |
| 调度者 | 操作系统 | 操作系统 | 运行时（JVM / Go runtime / JS 引擎） |
| 数量级 | 几十 | 几百～几千 | 百万 |
| 前端对应 | 浏览器多进程架构、Node cluster | Web Worker | `async` 函数 / Generator |

Java 平台线程与操作系统线程是 **1:1** 映射；虚拟线程是 **M:N** 映射（很多虚拟线程跑在少量平台线程上）。

### 2.2 线程的创建与生命周期

**创建方式（本质只有一种：`new Thread` 并 `start`，其余是任务的不同表达）：**

```ts
// TS / Node：worker_threads
import { Worker } from 'node:worker_threads';
const worker = new Worker('./export-worker.js', { workerData: { batch: 1 } });
worker.on('message', (count) => console.log('导出', count));
```

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/**
 * 演示线程的几种创建方式。
 */
public class ThreadCreateDemo {

    /**
     * 程序入口。
     *
     * @param args 命令行参数（未使用）
     * @throws Exception 等待结果时的中断或执行异常
     */
    public static void main(String[] args) throws Exception {
        // 方式 1：Runnable + Thread（无返回值）
        Thread t1 = new Thread(() -> System.out.println("导出批次 1"), "export-1");
        t1.start();                         // start 才会新建线程；直接调 run() 只是普通方法调用

        // 方式 2：Java 21 构建器风格
        Thread t2 = Thread.ofPlatform().name("export-2").start(() -> System.out.println("导出批次 2"));

        // 方式 3：Callable + 线程池（有返回值，生产唯一推荐的方式）
        try (ExecutorService pool = Executors.newFixedThreadPool(2)) {   // 仅演示；生产禁止用 Executors，见 2.9
            Callable<Integer> task = () -> 1000;                        // 返回导出条数
            Future<Integer> future = pool.submit(task);
            System.out.println("导出条数：" + future.get());             // get 会阻塞直到结果就绪
        }
        t1.join();
        t2.join();
    }
}
```

**六种状态（`Thread.State`）：**

```
                  start()
      NEW ─────────────────────► RUNNABLE ◄──────────────────────────┐
                                 （就绪 + 运行中，Java 不区分；        │
                                   阻塞式 I/O 时也显示为 RUNNABLE）     │
             ┌───── 抢 synchronized 锁失败 ──┤                         │
             ▼                               │ wait() / join()        │
         BLOCKED ── 抢到锁 ─────────────────►│ LockSupport.park()     │ notify() / unpark()
                                             ├──────────► WAITING ────┤ / 被 join 的线程结束
                                             │ sleep(ms) / wait(ms)   │
                                             ├──────────► TIMED_WAITING ┘（超时或被唤醒）
                                             │
                                             ▼ run() 结束或抛出未捕获异常
                                         TERMINATED
```

| 状态 | jstack 里常见的样子 | 意味着 |
|---|---|---|
| `RUNNABLE` | 栈顶是业务代码或 `socketRead0` | 在跑，或在等网络 I/O |
| `BLOCKED` | `waiting to lock <0x...>` | 在等 `synchronized` 锁，大量出现 = 锁竞争 |
| `WAITING` | `parking to wait for <...>`（`LockSupport.park`） | 在等 `ReentrantLock`/队列/`Future`，线程池空闲线程也是这个状态 |
| `TIMED_WAITING` | `sleeping` / `parkNanos` | 带超时的等待 |

> ⚠️ 中断（`interrupt()`）是 Java **唯一正确的停止线程方式**：它只是设置标志位，由目标线程在合适的地方检查 `Thread.currentThread().isInterrupted()` 或在 `sleep/wait` 时收到 `InterruptedException` 后自行退出。`Thread.stop()` 已废弃且在 Java 20 后直接抛异常。捕获 `InterruptedException` 后**不要吞掉**，至少要 `Thread.currentThread().interrupt()` 恢复标志。类比：`AbortController` —— 只发信号，任务自己决定如何响应。

### 2.3 线程安全问题的本质：从 `i++` 说起

```java
/**
 * 演示 i++ 的线程安全问题：10 个线程各加 1 万次，结果小于 10 万。
 */
public class CounterLab {

    /** 共享计数器，被所有线程同时读写 */
    private static int count = 0;

    /**
     * 程序入口。
     *
     * @param args 命令行参数（未使用）
     * @throws InterruptedException 等待线程结束时被中断
     */
    public static void main(String[] args) throws InterruptedException {
        Thread[] threads = new Thread[10];
        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(() -> {
                for (int j = 0; j < 10_000; j++) {
                    count++;                      // 看起来是一步，实际是三步
                }
            });
            threads[i].start();
        }
        for (Thread t : threads) {
            t.join();                            // 等待所有线程结束
        }
        System.out.println("期望 100000，实际 " + count);  // 例如：实际 61873，每次运行都不同
    }
}
```

同样的逻辑在 JS 里**永远是正确的**——因为没有第二个线程能在 `count++` 中间插进来。

**`javap -c` 看 `count++`：**

```
getstatic  count    // ① 读：从内存读 count 到操作数栈
iconst_1
iadd                // ② 改：栈上 +1
putstatic  count    // ③ 写：写回内存
```

**交错执行导致「丢失更新」：**

```
时间 ─────────────────────────────────────────────────►
线程 A：读 count=5 ─── +1=6 ───────────────── 写 6
线程 B：        读 count=5 ─── +1=6 ─── 写 6
结果：两次 ++，count 只从 5 变成 6
```

**并发三大问题：**

| 特性 | 含义 | `i++` 里的体现 | 根源 | 解决手段 |
|---|---|---|---|---|
| **原子性** | 操作不可被打断 | 读-改-写三步可被其他线程插入 | 线程切换 | `synchronized`、`Lock`、CAS（Atomic 类） |
| **可见性** | 一个线程改了，其他线程马上能看到 | 线程 A 写了 6，B 可能还在读自己 CPU 缓存里的 5 | CPU 多级缓存、寄存器、JIT 优化 | `volatile`、`synchronized`、`final` |
| **有序性** | 代码按写的顺序执行 | — （见 DCL 单例） | 编译器/CPU 指令重排 | `volatile`（内存屏障）、`synchronized` |

```
   CPU 0              CPU 1
 ┌───────┐         ┌───────┐
 │寄存器  │         │寄存器  │
 │L1/L2   │count=6  │L1/L2   │count=5  ← 线程 B 看到的是旧值
 └───┬───┘         └───┬───┘
     └──── L3 / 主内存 ─┘  count=?
```

**可见性问题的经典演示（可能永远不停）：**

```java
/**
 * 演示可见性问题：主线程修改 running，工作线程可能永远看不到。
 */
public class VisibilityLab {

    /** 运行标志。去掉 volatile 后，工作线程可能永不退出 */
    private static volatile boolean running = true;

    /**
     * 程序入口。
     *
     * @param args 命令行参数（未使用）
     * @throws InterruptedException 休眠被中断
     */
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            long loops = 0;
            // 没有 volatile 时，JIT 可能把 running 的读取提到循环外：if (running) while (true) {...}
            while (running) {
                loops++;
            }
            System.out.println("worker 退出，循环次数 " + loops);
        });
        worker.start();
        Thread.sleep(1000);
        running = false;                 // 主线程修改标志
        System.out.println("main 已设置 running=false");
    }
}
```

### 2.4 `synchronized`：最基础的互斥锁

```java
/**
 * 线程安全的计数器：三种 synchronized 写法。
 */
public class SafeCounter {

    /** 计数值 */
    private int count = 0;

    /** 专用锁对象，避免把 this 暴露为锁 */
    private final Object lock = new Object();

    /**
     * 写法 1：修饰实例方法，锁的是 this。
     */
    public synchronized void incrementA() {
        count++;
    }

    /**
     * 写法 2：同步代码块，锁的是指定对象（推荐：锁粒度可控）。
     */
    public void incrementB() {
        synchronized (lock) {
            count++;
        }
    }

    /**
     * 写法 3：修饰静态方法时锁的是 SafeCounter.class（全局唯一）——此处仅作说明。
     *
     * @return 当前计数
     */
    public synchronized int get() {
        return count;
    }
}
```

`synchronized` 同时保证**原子性、可见性、有序性**：进入时从主内存重新读，退出时把修改刷回主内存。它是**可重入**的（同一线程可再次获得已持有的锁），异常时自动释放锁。

> 前端类比：没有直接对应物。最接近的是「把一段代码丢进串行队列」——`synchronized` 就是让同一把锁下的代码块**排队执行**。

底层原理（Monitor、锁升级）见 3.2。

### 2.5 `volatile`：轻量级的可见性 + 有序性

| | `volatile` | `synchronized` |
|---|---|---|
| 原子性 | ❌（`volatile int` 的 `++` 依然不安全） | ✅ |
| 可见性 | ✅ | ✅ |
| 有序性 | ✅（禁止重排） | ✅ |
| 阻塞 | 不阻塞 | 可能阻塞 |
| 适用 | 状态标志、DCL 单例、一写多读 | 复合操作 |

**DCL（双重检查锁）单例——为什么必须加 `volatile`：**

```java
/**
 * 双重检查锁单例（演示 volatile 防止指令重排）。
 */
public class IdGenerator {

    /** 单例实例。volatile 防止「分配内存 → 赋值引用 → 初始化」的重排 */
    private static volatile IdGenerator instance;

    /**
     * 私有构造，禁止外部实例化。
     */
    private IdGenerator() {
    }

    /**
     * 获取单例。
     *
     * @return 全局唯一的 IdGenerator
     */
    public static IdGenerator getInstance() {
        if (instance == null) {                       // 第一次检查：已初始化则无锁返回
            synchronized (IdGenerator.class) {
                if (instance == null) {               // 第二次检查：防止多个线程排队后重复创建
                    // new 分三步：①分配内存 ②初始化 ③引用指向内存
                    // 若重排为 ①③②，其他线程在第一次检查处会拿到「未初始化完」的对象
                    instance = new IdGenerator();
                }
            }
        }
        return instance;
    }
}
```

> 实践中更推荐 **静态内部类** 或 **枚举** 单例（由类加载机制保证线程安全，见 03 章 2.5）；在 Spring 里，Bean 默认就是单例，几乎不需要手写。

### 2.6 `ReentrantLock` 与 `Condition`

`synchronized` 是关键字，功能固定；`ReentrantLock` 是 API，更灵活：

| 能力 | `synchronized` | `ReentrantLock` |
|---|---|---|
| 可重入 | ✅ | ✅ |
| 自动释放 | ✅（退出块/异常） | ❌ **必须在 finally 中 unlock** |
| 尝试加锁 / 超时 | ❌ | ✅ `tryLock()` / `tryLock(1, SECONDS)` |
| 可中断地等待锁 | ❌ | ✅ `lockInterruptibly()` |
| 公平锁 | ❌ 非公平 | 可选 `new ReentrantLock(true)` |
| 多个等待条件 | ❌ 只有一个 wait set | ✅ 多个 `Condition` |
| 选择建议 | **默认首选**（简单、JVM 持续优化） | 需要以上高级能力时 |

**用 Condition 实现一个有界阻塞队列（理解线程池队列的原理）：**

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

/**
 * 简化版有界阻塞队列：满了 put 阻塞，空了 take 阻塞。
 *
 * @param <T> 元素类型
 */
public class BoundedQueue<T> {

    /** 存储元素的双端队列 */
    private final Deque<T> items = new ArrayDeque<>();
    /** 最大容量 */
    private final int capacity;
    /** 互斥锁 */
    private final ReentrantLock lock = new ReentrantLock();
    /** 条件：队列不满（生产者在此等待） */
    private final Condition notFull = lock.newCondition();
    /** 条件：队列不空（消费者在此等待） */
    private final Condition notEmpty = lock.newCondition();

    /**
     * 构造函数。
     *
     * @param capacity 最大容量
     */
    public BoundedQueue(int capacity) {
        this.capacity = capacity;
    }

    /**
     * 放入元素，队列满时阻塞。
     *
     * @param item 元素
     * @throws InterruptedException 等待时被中断
     */
    public void put(T item) throws InterruptedException {
        lock.lock();
        try {
            while (items.size() == capacity) {   // 必须用 while 防止「虚假唤醒」
                notFull.await();                 // 释放锁并等待，被唤醒后重新竞争锁
            }
            items.addLast(item);
            notEmpty.signal();                   // 只唤醒等待「不空」的消费者
        } finally {
            lock.unlock();                       // 务必在 finally 中释放
        }
    }

    /**
     * 取出元素，队列空时阻塞。
     *
     * @return 队首元素
     * @throws InterruptedException 等待时被中断
     */
    public T take() throws InterruptedException {
        lock.lock();
        try {
            while (items.isEmpty()) {
                notEmpty.await();
            }
            T item = items.removeFirst();
            notFull.signal();                    // 腾出空间，唤醒生产者
            return item;
        } finally {
            lock.unlock();
        }
    }
}
```

JDK 的 `ArrayBlockingQueue` 就是这么实现的。`synchronized` + `wait/notifyAll` 也能写，但只有一个等待队列，`notifyAll` 会把生产者和消费者全部唤醒，效率更低。

### 2.7 CAS 与原子类

**CAS（Compare-And-Swap）**：一条 CPU 指令（x86 的 `lock cmpxchg`），语义是「如果内存值仍是我预期的旧值，就改成新值，否则失败」。失败了就重试（自旋），不阻塞线程——这就是**乐观锁**。

```ts
// TS：JS 也有 CAS！只在 SharedArrayBuffer 上可用
const sab = new SharedArrayBuffer(4);
const counter = new Int32Array(sab);
Atomics.add(counter, 0, 1);                              // 原子加
Atomics.compareExchange(counter, 0, /*expected*/1, /*new*/2);
```

```java
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 用 AtomicInteger 实现线程安全计数，并展示 CAS 自旋的原理。
 */
public class CasCounter {

    /** 原子计数器 */
    private final AtomicInteger count = new AtomicInteger(0);

    /**
     * 原子自增（JDK 已封装好）。
     *
     * @return 自增后的值
     */
    public int increment() {
        return count.incrementAndGet();
    }

    /**
     * 手写 CAS 自旋，等价于 incrementAndGet（用于理解原理）。
     *
     * @return 自增后的值
     */
    public int incrementByCas() {
        while (true) {
            int current = count.get();                  // 1. 读当前值
            int next = current + 1;                     // 2. 计算新值
            if (count.compareAndSet(current, next)) {   // 3. 值未被他人改过才写入，否则重试
                return next;
            }
        }
    }
}
```

| 原子类 | 用途 |
|---|---|
| `AtomicInteger` / `AtomicLong` / `AtomicBoolean` | 计数、开关 |
| `AtomicReference<V>` | 原子替换对象引用 |
| `AtomicStampedReference<V>` | 带版本号，解决 ABA |
| `LongAdder` | **高并发计数首选**（QPS 统计、接口调用次数） |

**ABA 问题**：线程 1 读到 A，准备改为 C；期间线程 2 把 A 改成 B 又改回 A；线程 1 的 CAS 依然成功，但「中间发生过变化」。对纯计数无害，对链表/栈结构有害。解决：加版本号（`AtomicStampedReference`）——**这和数据库乐观锁的 `version` 字段是同一个思想**（第 4 节扣库存会用到）。

**`LongAdder` 为什么比 `AtomicLong` 快：**

```
AtomicLong：            所有线程 CAS 同一个 value → 高并发下大量失败重试，CPU 空转
                         [ value ] ◄── T1 T2 T3 T4 T5 ...

LongAdder：             分散热点：base + Cell[] 数组，线程按哈希落到不同 Cell
                         [ base ] [Cell0] [Cell1] [Cell2] [Cell3]
                            T1      T2      T3      T4、T5
                         sum() = base + ΣCell（非精确快照）
```

代价：`sum()` 不是强一致的瞬时值，所以**适合统计，不适合用来做「余额 >= 0」这种判断**。`ConcurrentHashMap` 的 `size()` 用的也是这个思想。

### 2.8 同步工具：`CountDownLatch` / `CyclicBarrier` / `Semaphore`

| 工具 | 一句话 | 前端类比 | 可复用 |
|---|---|---|---|
| `CountDownLatch` | 等 N 件事做完再继续 | `await Promise.all([...])` | ❌ 一次性 |
| `CyclicBarrier` | N 个线程互相等，到齐了一起出发 | 无（多人游戏「全员准备」） | ✅ |
| `Semaphore` | 最多允许 N 个线程同时访问 | `p-limit(5)` 并发限制 | ✅ |

```ts
// TS：用 p-limit 限制最多 5 个并发请求
import pLimit from 'p-limit';
const limit = pLimit(5);
await Promise.all(orderNos.map((no) => limit(() => queryLogistics(no))));
```

```java
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Semaphore;

/**
 * 用 Semaphore 限流 + CountDownLatch 等待全部完成，对照 p-limit + Promise.all。
 */
public class LimitedBatchQuery {

    /** 最多 5 个并发调用物流接口（三方接口限流） */
    private final Semaphore permits = new Semaphore(5);

    /**
     * 批量查询物流，最多 5 个并发，全部完成后返回。
     *
     * @param orderNos 订单号列表
     * @param pool     执行任务的线程池
     * @throws InterruptedException 等待时被中断
     */
    public void queryAll(List<String> orderNos, ExecutorService pool) throws InterruptedException {
        CountDownLatch done = new CountDownLatch(orderNos.size());   // 计数 = 任务数
        for (String orderNo : orderNos) {
            pool.execute(() -> {
                try {
                    permits.acquire();                  // 拿许可，满 5 个则阻塞
                    try {
                        queryLogistics(orderNo);
                    } finally {
                        permits.release();              // 归还许可
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt(); // 恢复中断标志
                } finally {
                    done.countDown();                   // 无论成败都要减计数，否则 await 永远等下去
                }
            });
        }
        done.await();                                   // 等计数归零
    }

    /**
     * 调用物流接口（示意）。
     *
     * @param orderNo 订单号
     */
    private void queryLogistics(String orderNo) {
        System.out.println(Thread.currentThread().getName() + " 查询 " + orderNo);
    }
}
```

> 日常开发中，「等多个任务完成」更推荐用 2.12 的 `CompletableFuture.allOf`，可以拿到结果和异常；`CountDownLatch` 常用于测试中构造并发（第 4 节扣库存演示）。

### 2.9 线程池

**为什么要池化**：线程创建/销毁昂贵、数量无上限会拖垮系统。和数据库连接池、HTTP keep-alive 同理。

**`ThreadPoolExecutor` 的 7 个参数：**

```java
public ThreadPoolExecutor(
        int corePoolSize,                    // ① 核心线程数：常驻，默认不回收
        int maximumPoolSize,                 // ② 最大线程数：队列满后才会扩到这个数
        long keepAliveTime,                  // ③ 非核心线程空闲多久被回收
        TimeUnit unit,                       // ④ keepAliveTime 的单位
        BlockingQueue<Runnable> workQueue,   // ⑤ 任务队列：必须有界
        ThreadFactory threadFactory,         // ⑥ 线程工厂：给线程起有意义的名字
        RejectedExecutionHandler handler)    // ⑦ 拒绝策略：线程和队列都满时怎么办
```

**执行流程（面试必画，也是线上问题的根源）：**

```
submit(task)
   │
   ▼
运行线程数 < corePoolSize ？──是──► 创建核心线程执行该任务
   │否
   ▼
workQueue.offer(task) 成功？──是──► 入队，等待空闲线程来取
   │否（队列满）
   ▼
运行线程数 < maximumPoolSize ？──是──► 创建非核心线程执行该任务
   │否
   ▼
执行拒绝策略 handler.rejectedExecution(task)
```

> ⚠️ 反直觉点：**先排队，再扩容到最大线程**。如果用无界队列，`maximumPoolSize` 永远不会生效。Tomcat 的线程池改写了这个顺序（先扩线程再排队），因为 Web 请求更怕排队延迟。

**四种拒绝策略：**

| 策略 | 行为 | 适用 |
|---|---|---|
| `AbortPolicy`（默认） | 抛 `RejectedExecutionException` | 需要感知失败的场景，配合降级/提示「系统繁忙」 |
| `CallerRunsPolicy` | 由提交任务的线程自己执行 | 不能丢任务、可接受调用方变慢（天然的背压） |
| `DiscardPolicy` | 静默丢弃 | 几乎不用（丢了都不知道） |
| `DiscardOldestPolicy` | 丢弃队列最老的任务，再尝试提交 | 只关心最新数据的场景（如刷新状态） |

> ⚠️ `CallerRunsPolicy` 在 Tomcat 线程里提交任务时，会让 Web 请求线程去执行任务，可能把整个服务拖慢；在 `CompletableFuture` 中用时要清楚调用方是谁。

**为什么禁止用 `Executors` 创建线程池（阿里规约强制项）：**

| 工厂方法 | 内部实现 | 隐患 |
|---|---|---|
| `newFixedThreadPool(n)` | `LinkedBlockingQueue` **无界**（容量 `Integer.MAX_VALUE`） | 任务堆积 → OOM |
| `newSingleThreadExecutor()` | 同上 | 同上 |
| `newCachedThreadPool()` | `maximumPoolSize = Integer.MAX_VALUE` + `SynchronousQueue` | 任务突增时创建海量线程 → `unable to create native thread` |
| `newScheduledThreadPool(n)` | `DelayedWorkQueue` 无界 | 任务堆积 → OOM |

正确做法：**直接 `new ThreadPoolExecutor`，显式指定有界队列、线程名、拒绝策略**（第 4 节给出完整配置）。例外：`Executors.newVirtualThreadPerTaskExecutor()` 是推荐用法（虚拟线程不需要池化，2.13）。

**线程数如何设置：**

| 任务类型 | 经验公式 | 说明 |
|---|---|---|
| CPU 密集（计算、加解密、序列化） | `N核 + 1` | 多了只会增加切换 |
| I/O 密集（查库、调接口） | `N核 × (1 + 等待时间 / 计算时间)` | 例如 4 核，单次 RT 100ms 中 CPU 计算 10ms → 4 × (1 + 90/10) = 40 |
| 混合 | 拆成两个池分别配置 | — |

> 高级工程师的做法：公式只是起点。**用压测找拐点**（吞吐不再上升、RT 开始上升的点），并把核心参数做成可动态调整的（`setCorePoolSize` / `setMaximumPoolSize` 运行时可改；开源方案 Dynamic-TP、Hippo4j 支持配置中心热更新和监控告警）。还要记得**下游的容量**：40 个线程同时查库，数据库连接池只有 20 个，多出来的线程也只能干等。

**优雅关闭：**

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * 线程池关闭工具。
 */
public final class ExecutorShutdownUtil {

    /**
     * 私有构造，工具类禁止实例化。
     */
    private ExecutorShutdownUtil() {
    }

    /**
     * 优雅关闭线程池：先停止接收新任务，等待已提交任务完成，超时后强制中断。
     *
     * @param pool           待关闭的线程池
     * @param timeoutSeconds 最长等待秒数
     */
    public static void shutdownGracefully(ExecutorService pool, long timeoutSeconds) {
        pool.shutdown();                                              // 1. 不再接收新任务，已提交的继续执行
        try {
            if (!pool.awaitTermination(timeoutSeconds, TimeUnit.SECONDS)) {
                pool.shutdownNow();                                   // 2. 超时：中断正在执行的任务，返回队列中未执行的任务
                pool.awaitTermination(5, TimeUnit.SECONDS);           // 3. 再给 5 秒响应中断
            }
        } catch (InterruptedException e) {
            pool.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

> Java 19+ 的 `ExecutorService` 实现了 `AutoCloseable`，`close()` 会 `shutdown` 并**无限期**等待任务结束，适合 try-with-resources 的短生命周期池。Spring 管理的池在容器关闭时会调用销毁方法；配合 `server.shutdown=graceful` 让 Web 请求和后台任务都能正常收尾。K8s 的 `terminationGracePeriodSeconds`（默认 30s）要大于这些等待时间之和。

### 2.10 `ConcurrentHashMap`

`HashMap` 线程不安全（并发 put 丢数据；Java 7 扩容时甚至会形成环形链表导致 CPU 100%）。替代方案对比：

| 方案 | 实现 | 并发度 | 建议 |
|---|---|---|---|
| `Hashtable` | 所有方法 `synchronized` | 低（整表一把锁） | 弃用 |
| `Collections.synchronizedMap` | 包装一层 `synchronized` | 低 | 少用 |
| `ConcurrentHashMap` | CAS + 桶级 `synchronized` | 高 | **首选** |

**原子复合操作要用它提供的方法，不要自己「先 get 再 put」：**

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

/**
 * 按商品统计下单次数（并发安全）。
 */
public class ProductOrderCounter {

    /** 下单次数统计，key：商品 ID productId，value：累计下单次数 */
    private final ConcurrentHashMap<Long, LongAdder> counter = new ConcurrentHashMap<>();

    /**
     * 记录某商品被下单一次。
     *
     * @param productId 商品 ID
     */
    public void record(Long productId) {
        // ❌ 错误：if (!counter.containsKey(id)) counter.put(id, new LongAdder()); —— 检查与写入之间有竞态
        // ✅ computeIfAbsent 在桶锁内原子地完成「不存在则创建」
        counter.computeIfAbsent(productId, id -> new LongAdder()).increment();
    }

    /**
     * 查询某商品累计下单次数。
     *
     * @param productId 商品 ID
     * @return 下单次数，未下过单返回 0
     */
    public long count(Long productId) {
        LongAdder adder = counter.get(productId);
        return adder == null ? 0L : adder.sum();
    }
}
```

> ⚠️ `ConcurrentHashMap` 的 key 和 value **都不允许为 null**（`HashMap` 允许）。原因：并发场景下 `get` 返回 null 时无法区分「不存在」还是「值为 null」，而又无法像单线程那样用 `containsKey` 二次确认。原理见 3.5。

### 2.11 `ThreadLocal`：线程级的上下文

用途：在同一线程的调用链上隐式传递上下文（当前登录用户、TraceId、数据源路由），避免每个方法都加参数。

```ts
// Node：AsyncLocalStorage —— 在异步调用链上传递请求上下文
import { AsyncLocalStorage } from 'node:async_hooks';
const als = new AsyncLocalStorage<{ userId: number }>();
app.use((req, _res, next) => als.run({ userId: req.user.id }, next));
function currentUserId() { return als.getStore()?.userId; }
```

```java
/**
 * 登录用户上下文（基于 ThreadLocal）。由拦截器在请求开始时 set、结束时 clear（07 章）。
 */
public final class UserContext {

    /** 当前线程的登录用户 ID */
    private static final ThreadLocal<Long> CURRENT_USER_ID = new ThreadLocal<>();

    /**
     * 私有构造，工具类禁止实例化。
     */
    private UserContext() {
    }

    /**
     * 设置当前线程的登录用户。
     *
     * @param userId 用户 ID
     */
    public static void set(Long userId) {
        CURRENT_USER_ID.set(userId);
    }

    /**
     * 获取当前线程的登录用户。
     *
     * @return 用户 ID，未登录返回 null
     */
    public static Long get() {
        return CURRENT_USER_ID.get();
    }

    /**
     * 清理当前线程的上下文。必须在请求结束时于 finally 中调用。
     */
    public static void clear() {
        CURRENT_USER_ID.remove();
    }
}
```

**两个必须知道的问题：**

1. **用完必须 `remove()`**：线程池中线程会复用，不清理会导致内存泄漏，以及**下一个请求读到上一个用户的身份**（严重的安全事故）。原理见 3.6。
2. **切换线程后上下文丢失**：`CompletableFuture.supplyAsync` 的任务跑在别的线程，`UserContext.get()` 返回 null；日志 MDC 中的 TraceId 也会丢失。

**跨线程传递方案：**

| 方案 | 原理 | 线程池场景 |
|---|---|---|
| `InheritableThreadLocal` | **创建子线程时**拷贝父线程的值 | ❌ 线程池的线程早已创建好，后续任务拿到的是旧值 |
| 手动传参 / 包装 Runnable | 提交时捕获，执行时 set、结束时 remove | ✅ 但要处处记得 |
| Spring `TaskDecorator` | `ThreadPoolTaskExecutor` 的装饰钩子，统一做上面的事 | ✅ 仅限 Spring 线程池 |
| **阿里 TransmittableThreadLocal（TTL）** | 提交任务时快照、执行前回放、执行后恢复 | ✅ 通用；`TtlExecutors.getTtlExecutorService(pool)` 包装即可 |
| Java 21 `ScopedValue`（预览） | 不可变、有作用域的上下文，结构化并发配套 | 面向虚拟线程的未来方案 |

```java
import com.alibaba.ttl.TransmittableThreadLocal;
import com.alibaba.ttl.threadpool.TtlExecutors;

import java.util.concurrent.ExecutorService;

/**
 * 演示 TTL 在线程池中透传 TraceId。
 */
public class TraceContextDemo {

    /** 当前请求的链路追踪 ID */
    private static final TransmittableThreadLocal<String> TRACE_ID = new TransmittableThreadLocal<>();

    /**
     * 在线程池中执行任务并保持 TraceId。
     *
     * @param rawPool 原始线程池
     * @param traceId 当前请求的 TraceId
     */
    public void runWithTrace(ExecutorService rawPool, String traceId) {
        ExecutorService pool = TtlExecutors.getTtlExecutorService(rawPool);  // 包装后提交的任务自动透传
        TRACE_ID.set(traceId);
        try {
            pool.execute(() -> System.out.println("子任务 traceId=" + TRACE_ID.get()));  // 能拿到值
        } finally {
            TRACE_ID.remove();
        }
    }
}
```

### 2.12 `CompletableFuture`：Java 的 Promise

| Promise | CompletableFuture | 说明 |
|---|---|---|
| `new Promise(r => r(v))` / `Promise.resolve(v)` | `CompletableFuture.completedFuture(v)` | 已完成的 Future |
| `fetch()` 返回 Promise | `supplyAsync(supplier, executor)` | 在线程池中异步执行 |
| `.then(x => x * 2)` | `.thenApply(x -> x * 2)` | 同步变换（map） |
| `.then(x => fetchMore(x))` | `.thenCompose(x -> queryAsync(x))` | 返回新异步（flatMap） |
| `.then(x => console.log(x))` | `.thenAccept(x -> ...)` | 消费结果 |
| `.catch(e => fallback)` | `.exceptionally(e -> fallback)` | 异常兜底 |
| `.finally(...)` / `.then(ok, err)` | `.whenComplete((v, e) -> ...)` / `.handle((v, e) -> ...)` | `handle` 可改写结果 |
| `Promise.all([a, b])` | `CompletableFuture.allOf(a, b)` | 返回 `Void`，结果再 `a.join()` 取 |
| `Promise.any` / `race` | `anyOf(a, b)` | 第一个**完成**（含异常完成）的 |
| 合并两个结果 | `a.thenCombine(b, (x, y) -> ...)` | — |
| `await p` | `p.join()` / `p.get()` | **阻塞当前线程**；`join` 抛非受检 `CompletionException` |
| `AbortSignal.timeout(ms)` | `.orTimeout(1, SECONDS)` / `.completeOnTimeout(默认值, 1, SECONDS)` | Java 9+ |

```ts
// TS
async function getDetail(orderId: number) {
  const order = await queryOrder(orderId);
  const [user, items] = await Promise.all([queryUser(order.userId), queryItems(orderId)]);
  const logistics = await queryLogistics(order.orderNo).catch(() => null);
  return { order, user, items, logistics };
}
```

```java
// Java：结构一一对应，完整版见第 4 节 OrderBizComponent#getOrderDetail
CompletableFuture<UserPO> userF = CompletableFuture.supplyAsync(() -> userDao.getById(order.getUserId()), executor);
CompletableFuture<List<OrderItemPO>> itemsF = CompletableFuture.supplyAsync(() -> orderItemDao.listByOrderId(orderId), executor);
CompletableFuture<LogisticsTraceDTO> logisticsF = CompletableFuture
        .supplyAsync(() -> logisticsClient.queryTrace(order.getOrderNo()), executor)
        .exceptionally(ex -> LogisticsTraceDTO.empty());          // 对应 .catch(() => null)
CompletableFuture.allOf(userF, itemsF, logisticsF).join();        // 对应 await Promise.all
```

**和 Promise 最关键的三个差异：**

| 差异 | 后果 | 对策 |
|---|---|---|
| 不传 executor 时，默认用 `ForkJoinPool.commonPool()`（线程数 = 核数 - 1，全 JVM 共享） | I/O 任务把公共池占满，整个应用的并行流、其他异步任务全部卡住 | **永远传入自定义线程池** |
| `thenApply` 等非 Async 方法的回调，可能在「完成上一步的线程」或「调用 thenApply 的线程」中执行 | 回调线程不确定，`ThreadLocal` 拿不到值 | 需要指定线程时用 `thenApplyAsync(fn, executor)` |
| 异常被包装为 `CompletionException` | `exceptionally` 拿到的 `ex` 不是原始异常 | 用 `ex.getCause()` 取原始异常 |

### 2.13 Java 21 虚拟线程

**动机**：一请求一线程写法简单但线程贵；响应式编程（WebFlux、Reactor）并发高但写起来像回调地狱、调试困难。虚拟线程让你**用同步代码，获得异步的并发能力**。

```ts
// TS：async/await —— 函数被「染色」，调用链上每一层都要 async
async function handle(req: Request) {
  const user = await db.query('select ...');      // 让出事件循环
  const pay = await payClient.query(user.id);
  return { user, pay };
}
```

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.stream.IntStream;

/**
 * 演示虚拟线程：同时运行 10 万个阻塞任务。
 */
public class VirtualThreadDemo {

    /**
     * 程序入口。
     *
     * @param args 命令行参数（未使用）
     */
    public static void main(String[] args) {
        // 每个任务一个虚拟线程，不需要池化
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            IntStream.range(0, 100_000).forEach(i -> executor.submit(() -> {
                Thread.sleep(1000);      // 阻塞调用：虚拟线程被挂起（卸载），底层平台线程去跑别的虚拟线程
                return i;
            }));
        }   // close() 等待全部完成：约 1 秒多，而 10 万个平台线程会直接 OOM
    }
}
```

```
虚拟线程 VT1 VT2 VT3 ... VT100000（堆上的普通对象，栈帧也存在堆里）
          │ 挂载 mount / 卸载 unmount
          ▼
载体线程 Carrier Thread（ForkJoinPool，默认数量 = CPU 核数）
          │
          ▼
       操作系统线程
VT1 执行到阻塞 I/O → JDK 把它的栈保存到堆上、从载体线程卸载 → 载体线程去执行 VT2
I/O 就绪 → VT1 重新挂载到某个载体线程上继续执行
```

**与 async/await 对比：**

| | async/await（JS） | 虚拟线程（Java 21） |
|---|---|---|
| 写法 | 需要 `async`/`await` 关键字，函数染色 | **普通同步代码**，零改造 |
| 调度点 | 显式 `await` | 隐式：JDK 中所有阻塞操作（Socket、`sleep`、`Lock`、`BlockingQueue`） |
| 并行 | 单线程，无并行 | 多个载体线程，**真并行** |
| 线程安全 | 不需要考虑（`await` 之间的同步代码不会被打断） | **仍需要**（共享内存依旧） |
| 异常栈 | 异步栈常被截断 | 完整栈 |

**Spring Boot 3.2+ 一行开启**：`spring.threads.virtual.enabled=true`，Tomcat 请求处理、`@Async`、定时任务等改用虚拟线程。

**适用与不适用：**

| 场景 | 是否适合 |
|---|---|
| I/O 密集、高并发（调多个下游接口、查库） | ✅ 最适合 |
| CPU 密集（计算、压缩） | ❌ 没有收益，载体线程数 = 核数 |
| 需要限制对下游的并发（数据库连接池只有 20） | 用 `Semaphore` 限流，**不要**用固定大小线程池来限流 |
| 大量使用 `ThreadLocal` 存大对象 | ⚠️ 百万个虚拟线程各一份，内存爆炸 |
| 代码中 `synchronized` 内有阻塞 I/O（Java 21～23） | ⚠️ pinning，见 3.7 |

### 2.14 死锁与排查

**四个必要条件**：互斥、持有并等待、不可抢占、循环等待。破坏任一即可。

```java
/**
 * 死锁演示：两个线程以相反顺序获取两把锁。
 */
public class DeadlockLab {

    /** 商品 A 的锁 */
    private static final Object LOCK_A = new Object();
    /** 商品 B 的锁 */
    private static final Object LOCK_B = new Object();

    /**
     * 程序入口。
     *
     * @param args 命令行参数（未使用）
     */
    public static void main(String[] args) {
        new Thread(() -> lockBoth(LOCK_A, LOCK_B), "order-1").start();  // 订单 1：先 A 后 B
        new Thread(() -> lockBoth(LOCK_B, LOCK_A), "order-2").start();  // 订单 2：先 B 后 A
    }

    /**
     * 依次获取两把锁。
     *
     * @param first  先获取的锁
     * @param second 后获取的锁
     */
    private static void lockBoth(Object first, Object second) {
        synchronized (first) {
            sleepQuietly(100);                  // 放大时间窗口，确保另一线程拿到了它的第一把锁
            synchronized (second) {
                System.out.println(Thread.currentThread().getName() + " 扣减完成");
            }
        }
    }

    /**
     * 休眠指定毫秒，忽略中断。
     *
     * @param millis 毫秒数
     */
    private static void sleepQuietly(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
```

**排查：**

```bash
jstack <pid> | tail -40          # 或 jcmd <pid> Thread.print
# Found one Java-level deadlock:
# =============================
# "order-2":
#   waiting to lock monitor 0x... (object 0x...a0, a java.lang.Object),
#   which is held by "order-1"
# "order-1":
#   waiting to lock monitor 0x... (object 0x...b0, a java.lang.Object),
#   which is held by "order-2"
```

Arthas：`thread -b` 直接找出持有锁并阻塞他人的线程。

**避免：**

| 手段 | 做法 | mini-mall 中的体现 |
|---|---|---|
| 固定加锁顺序 | 按 ID 排序后依次加锁 | 一单多商品扣库存时，**先按 productId 升序排序**再逐个扣减（数据库行锁同理，08 章） |
| 超时放弃 | `tryLock(timeout)`，拿不到就释放已持有的锁并重试/失败 | Redisson `tryLock(waitTime, ...)` |
| 缩小锁范围 | 锁内不做 RPC、不做慢 I/O | 不在锁内调用支付接口 |
| 一次性申请所有资源 | 破坏「持有并等待」 | Redisson `MultiLock` |

---

## 3. 原理深挖

### 3.1 JMM 与 happens-before

**Java 内存模型（JMM）** 是一份规范：它定义了在什么条件下，一个线程的写对另一个线程**保证可见**。它屏蔽了不同 CPU 架构（x86 强内存序、ARM 弱内存序）的差异——同样的代码在 Mac M 系列芯片（ARM）上更容易暴露并发 bug。

```
线程 A 工作内存 ◄──► ┌────────┐ ◄──► 线程 B 工作内存
（寄存器/CPU 缓存的抽象）│ 主内存  │
                     └────────┘
JMM 规定：线程不能直接操作主内存的变量，只能操作自己工作内存中的副本。
```

**happens-before 规则**（A happens-before B ⟹ A 的结果对 B 可见，且 A 排在 B 之前）：

| 规则 | 含义 |
|---|---|
| 程序顺序规则 | 同一线程内，前面的操作 hb 后面的操作 |
| 监视器锁规则 | 对一个锁的 unlock hb 之后对**同一把锁**的 lock |
| volatile 规则 | 对 volatile 变量的写 hb 之后对它的读 |
| 线程启动规则 | `t.start()` hb 线程 t 中的任何操作 |
| 线程终止规则 | 线程 t 中的操作 hb 其他线程从 `t.join()` 返回 |
| 中断规则 | `t.interrupt()` hb t 检测到中断 |
| 传递性 | A hb B，B hb C ⟹ A hb C |

**传递性的威力——用一个 volatile 发布一堆普通变量：**

```java
/**
 * 演示 happens-before 传递性：volatile 写之前的普通写，对 volatile 读之后的代码可见。
 */
public class ConfigPublisher {

    /** 普通字段：限流阈值 */
    private int qpsLimit;
    /** 普通字段：开关 */
    private boolean degrade;
    /** 发布标志（volatile） */
    private volatile boolean ready;

    /**
     * 写线程：先写配置，再写 volatile 标志。
     */
    public void publish() {
        qpsLimit = 500;        // ① 普通写
        degrade = true;        // ② 普通写
        ready = true;          // ③ volatile 写（①② 不会被重排到 ③ 之后）
    }

    /**
     * 读线程：读到 ready=true 时，①② 一定可见。
     *
     * @return 当前限流阈值，未发布返回 -1
     */
    public int readLimit() {
        if (ready) {           // ④ volatile 读；③ hb ④，由传递性 ①② hb ⑤
            return qpsLimit;   // ⑤ 一定读到 500
        }
        return -1;
    }
}
```

**`volatile` 的实现：内存屏障**

```
volatile 写：  StoreStore 屏障 → 写 → StoreLoad 屏障
volatile 读：  读 → LoadLoad 屏障 → LoadStore 屏障
x86 上实际只有 StoreLoad 需要指令（lock addl $0,0(%rsp)），会触发缓存一致性协议（MESI）让其他核的缓存行失效
```

> `final` 字段也有特殊语义：构造函数正确完成后（期间没有把 `this` 泄漏出去），其他线程看到的 final 字段一定是初始化后的值。这是「不可变对象天然线程安全」的理论基础——`record`、`String`、`BigDecimal` 都可以放心共享。

### 3.2 `synchronized` 底层：Monitor 与锁升级

**字节码层面：**

```
synchronized 代码块 → monitorenter ... monitorexit（编译器额外生成一个异常路径的 monitorexit，保证异常时释放）
synchronized 方法   → 方法标志 ACC_SYNCHRONIZED，由 JVM 隐式加锁
```

**重量级锁：ObjectMonitor（C++ 实现）**

```
             ┌──────────── ObjectMonitor ───────────┐
竞争者 ──►   │ _cxq / _EntryList：等锁的线程（BLOCKED）│
             │ _owner：当前持有锁的线程               │
             │ _recursions：重入次数                  │
调 wait() ─► │ _WaitSet：调用了 wait 的线程（WAITING） │ ── notify() 移回 EntryList
             └──────────────────────────────────────┘
```

**锁状态在对象头 Mark Word 中（03 章 2.4）：**

| 锁状态 | 标志位 | 实现 | 适用场景 |
|---|---|---|---|
| 无锁 | 01 | — | — |
| ~~偏向锁~~ | 01（偏向位 1） | 记录线程 ID，同一线程再进入零开销 | **Java 15 默认关闭并废弃，Java 18 起移除**（撤销成本高，现代应用多线程竞争才是常态） |
| 轻量级锁 | 00 | 线程栈中的 Lock Record + CAS 替换 Mark Word | 多线程**交替**进入、几乎无竞争 |
| 重量级锁 | 10 | 指向 ObjectMonitor，阻塞/唤醒需要内核介入 | 真正的并发竞争 |

```
Java 21 的升级路径：

 无锁 ──第一个线程进入──► 轻量级锁（CAS 成功）
                           │ CAS 失败（有竞争）→ 短暂自适应自旋
                           ▼ 仍失败
                        重量级锁（膨胀为 ObjectMonitor，等待线程挂起）
锁一般只升级不降级（重量级锁在 GC 安全点可被回收为无锁）
```

> Java 8 存量项目：偏向锁默认开启，所以面试中常问「无锁 → 偏向 → 轻量 → 重量」。知道它在新版本已被移除、以及**为什么移除**，比背流程更有价值。Java 23 起轻量级锁也换成了新的 lock-stack 实现，对使用者透明。

**JIT 对锁的优化**：锁消除（逃逸分析发现锁对象不逃逸，03 章 3.5）、锁粗化（循环里反复加解同一把锁 → 合并为一次）。

### 3.3 AQS：Java 并发包的地基

`ReentrantLock`、`Semaphore`、`CountDownLatch`、`ReentrantReadWriteLock`、线程池的 `Worker` 都基于 **AbstractQueuedSynchronizer**。

```
AQS
├── volatile int state           // 同步状态，含义由子类定义
├── Node head, tail              // CLH 变体的双向等待队列（FIFO）
└── 模板方法：子类只需实现 tryAcquire / tryRelease（独占）或 tryAcquireShared / tryReleaseShared（共享）

       head                                       tail
        │                                          │
        ▼                                          ▼
     [哨兵] ⇄ [T2 等待] ⇄ [T3 等待] ⇄ [T4 等待]
     state=1，owner=T1
```

| 同步器 | state 的含义 | 模式 |
|---|---|---|
| `ReentrantLock` | 0=未锁，>0=重入次数 | 独占 |
| `Semaphore` | 剩余许可数 | 共享 |
| `CountDownLatch` | 剩余计数，0 时放行所有等待者 | 共享 |
| `ReentrantReadWriteLock` | 高 16 位读锁数、低 16 位写锁重入数 | 读共享/写独占 |

**`ReentrantLock.lock()` 流程（非公平）：**

```
lock()
 ├─① CAS(state, 0 → 1) 成功 → 设置 owner = 当前线程，返回          ← 非公平：新来的直接插队抢
 ├─② tryAcquire：state==0 再 CAS 一次；或 owner 是自己 → state+1（重入）
 ├─③ 失败 → 封装成 Node 加入队尾（CAS 设置 tail）
 └─④ 在队列中自旋检查：前驱是 head 就再试 tryAcquire；否则 LockSupport.park() 挂起
unlock()
 ├─ state-1，减到 0 时清空 owner
 └─ LockSupport.unpark(head 的后继节点)，被唤醒的线程回到 ④
```

**公平 vs 非公平**：公平锁在 ① 之前先检查队列里有没有人在等（`hasQueuedPredecessors`）。非公平锁吞吐更高（减少了唤醒线程的上下文切换），所以是默认值；代价是可能出现「饥饿」。

### 3.4 线程池源码要点

```java
// ThreadPoolExecutor 用一个 AtomicInteger 同时存两个信息
private final AtomicInteger ctl;   // 高 3 位：运行状态 runState；低 29 位：工作线程数 workerCount

// 运行状态
// RUNNING    ：接收新任务，处理队列任务
// SHUTDOWN   ：shutdown() 后，不接收新任务，继续处理队列
// STOP       ：shutdownNow() 后，不接收、不处理队列、中断正在执行的任务
// TIDYING    ：所有任务终止，workerCount=0，即将调用 terminated() 钩子
// TERMINATED ：terminated() 执行完毕
```

**Worker 是怎么「复用」线程的：**

```
Worker（继承 AQS 实现不可重入锁 + 实现 Runnable，持有一个 Thread）
run() → runWorker():
   task = firstTask
   while (task != null || (task = getTask()) != null) {
       beforeExecute(...)                     // 钩子：可用于设置上下文、埋点
       task.run()                             // 执行业务任务（异常会导致该 Worker 线程退出并被替换）
       afterExecute(...)                      // 钩子
   }
   processWorkerExit()                        // 线程退出

getTask():
   线程数 > corePoolSize（或 allowCoreThreadTimeOut）→ workQueue.poll(keepAliveTime)   // 超时返回 null → 线程退出
   否则 → workQueue.take()                                                           // 永久阻塞等任务
```

> 这就是「核心线程常驻、非核心线程空闲回收」的全部秘密：**线程复用 = 一个 while 循环不停地从阻塞队列取任务**。

> ⚠️ `execute()` 提交的任务抛异常会打印堆栈并替换线程；`submit()` 提交的任务异常会被吞进 `Future`，**不调用 `get()` 就永远看不到**。用 `submit` 时务必处理返回的 Future，或在任务内部 try/catch 记日志。

### 3.5 `ConcurrentHashMap` 原理（Java 8+）

```
Node<K,V>[] table
 ┌───┬───┬───┬───┬───┬───┬───┬───┐
 │ 0 │ 1 │ 2 │ 3 │ 4 │ 5 │ 6 │ 7 │
 └─┬─┴───┴─┬─┴───┴───┴─┬─┴───┴───┘
   ▼       ▼           ▼
  Node    Node        TreeBin（链表长度 ≥ 8 且数组长度 ≥ 64 时转红黑树）
   │       │
  Node    Node
```

**`put` 流程：**

```
① 计算 hash（spread：高 16 位异或低 16 位，且保证非负）
② table 未初始化 → CAS 初始化（sizeCtl 控制，只有一个线程能初始化）
③ 目标桶为空 → CAS 放入新 Node，无锁                   ← 大部分写入走这里
④ 桶头节点 hash == MOVED(-1) → 正在扩容，当前线程先协助扩容
⑤ 否则 synchronized(桶头节点) → 链表/红黑树中插入或覆盖    ← 锁粒度 = 单个桶
⑥ addCount：用 baseCount + CounterCell[] 计数（LongAdder 思想），超过阈值触发扩容
```

| 版本 | 结构 | 锁粒度 |
|---|---|---|
| Java 7 | `Segment[]`（继承 `ReentrantLock`）+ `HashEntry[]` | Segment 级，默认 16 个，并发度固定 |
| Java 8+ | `Node[]` + 链表/红黑树 | 桶级，CAS + `synchronized` |

**多线程协助扩容**：扩容时把旧数组按区间（每个线程至少领 16 个桶）分给多个线程迁移，已迁移的桶放一个 `ForwardingNode` 占位；读操作遇到 `ForwardingNode` 会转去新数组查找，**读全程无锁**（Node 的 `val` 和 `next` 都是 volatile）。

> 为什么 Java 8 用 `synchronized` 而不是 `ReentrantLock`？锁粒度已缩到单个桶，竞争极低，轻量级锁几乎够用；且 `synchronized` 不需要每个节点额外持有一个 Lock 对象，省内存。

### 3.6 `ThreadLocal` 原理与内存泄漏

```
Thread 对象
 └── threadLocals: ThreadLocalMap         ← 数据存在线程上，不是存在 ThreadLocal 上！
        └── Entry[] table（开放寻址法，不是链表）
              ├── Entry { key: WeakReference<ThreadLocal>（弱引用）, value: Long 1001（强引用）}
              └── Entry { key: WeakReference<ThreadLocal>, value: TraceId 字符串 }

ThreadLocal 本身只是一个「钥匙」：get() = Thread.currentThread().threadLocals.get(this)
```

**为什么会泄漏：**

```
引用链：
  线程池中的线程（长期存活，是 GC Root）
     └─► ThreadLocalMap
            └─► Entry
                 ├─ key   ──弱引用──► ThreadLocal 对象   （外部强引用消失后，key 被回收变为 null）
                 └─ value ──强引用──► 大对象              （value 仍然被 Entry 强引用 → 回收不掉！）
```

- key 用弱引用，是为了在 `ThreadLocal` 对象不再被使用时，至少 key 能被回收；
- `ThreadLocalMap` 在 `set/get/remove` 时会顺带清理 key 为 null 的 Entry（探测式清理），但**如果之后再也不调用，value 就一直挂着**；
- 更常见的现实问题不是泄漏，而是 `static final ThreadLocal` 永远不会被回收，**不 remove 就会被下一个复用该线程的请求读到**。

**结论：`ThreadLocal` 的使用模板永远是 `set → try { 业务 } finally { remove() }`。**

### 3.7 虚拟线程原理与 pinning

**实现**：虚拟线程 = `Continuation`（可暂停、可恢复的执行体）+ 调度器（`ForkJoinPool`）。JDK 把所有阻塞 API（`Socket`、`LockSupport.park`、`Thread.sleep` 等）都改造为：如果当前是虚拟线程，就 `Continuation.yield()` —— 把栈帧拷贝到堆上，释放载体线程。

**Pinning（钉住）**：某些情况下虚拟线程阻塞时无法卸载，会连同载体线程一起阻塞：

| 情况 | Java 21～23 | Java 24+ |
|---|---|---|
| 在 `synchronized` 块/方法内阻塞 | ❌ pinning | ✅ 已解决（JEP 491） |
| 在 native 方法 / 外部函数调用中阻塞 | ❌ pinning | ❌ 仍会 pinning |
| `Object.wait()` | ❌ pinning | ✅ 已解决 |

```
载体线程只有 8 个（8 核）
8 个虚拟线程同时在 synchronized 内调用 JDBC（阻塞）→ 8 个载体线程全部被钉住
→ 其余 10 万个虚拟线程无人调度 → 整个服务「假死」
```

**Java 21 应对：**
- 用 `-Djdk.tracePinnedThreads=full` 或 JFR 事件 `jdk.VirtualThreadPinned` 找出 pinning 位置；
- 自己的代码中，**包含阻塞 I/O 的临界区用 `ReentrantLock` 替代 `synchronized`**；
- 确认依赖库的兼容性（较新版本的 MySQL Connector/J、HikariCP 已把内部 `synchronized` 改为 `ReentrantLock`）；
- 或直接升级 Java 25 LTS。

---

## 4. mini-mall 实战

### 4.1 线程池配置

两个业务两个池（**隔离**：导出任务再慢，也不能拖垮订单详情查询）。

```java
package com.example.mall.config;

import com.example.mall.util.ExecutorShutdownUtil;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/**
 * 业务线程池配置。每类业务独立线程池，避免相互影响。
 */
@Configuration
public class ThreadPoolConfig {

    /** CPU 核数（容器环境下为 cgroup 限制后的值） */
    private static final int CPU = Runtime.getRuntime().availableProcessors();

    /**
     * 订单查询线程池：用于订单详情并行查询下游（I/O 密集）。
     * 队列小、拒绝时由调用线程执行，保证查询不失败（以变慢为代价）。
     *
     * @return 订单查询线程池
     */
    @Bean(name = "orderQueryExecutor", destroyMethod = "")
    public ThreadPoolExecutor orderQueryExecutor() {
        return new ThreadPoolExecutor(
                CPU * 4,                                     // 核心线程：I/O 密集，按 N×(1+W/C) 估算后压测修正
                CPU * 8,                                     // 最大线程
                60, TimeUnit.SECONDS,                        // 非核心线程空闲 60s 回收
                new ArrayBlockingQueue<>(200),               // 有界队列
                Thread.ofPlatform().name("order-query-", 0).factory(),  // 线程名：order-query-0、order-query-1…
                new ThreadPoolExecutor.CallerRunsPolicy());  // 满了由调用方（Tomcat 线程）自己执行
    }

    /**
     * 订单导出线程池：导出是重任务，严格限制并发，满了直接拒绝并提示用户稍后再试。
     *
     * @return 订单导出线程池
     */
    @Bean(name = "orderExportExecutor", destroyMethod = "")
    public ThreadPoolExecutor orderExportExecutor() {
        return new ThreadPoolExecutor(
                2, 2,                                        // 同时最多 2 个导出任务（保护数据库）
                0, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(10),                // 最多排队 10 个
                Thread.ofPlatform().name("order-export-", 0).factory(),
                new ThreadPoolExecutor.AbortPolicy());       // 满了抛异常，由编排层翻译为「系统繁忙」
    }

    /**
     * 容器关闭时优雅关闭业务线程池（destroyMethod="" 关闭了 Spring 的默认推断，统一在这里处理）。
     *
     * @param orderQueryExecutor  订单查询线程池
     * @param orderExportExecutor 订单导出线程池
     * @return 关闭钩子 Bean
     */
    @Bean
    public AutoCloseable businessExecutorShutdownHook(
            @Qualifier("orderQueryExecutor") ExecutorService orderQueryExecutor,
            @Qualifier("orderExportExecutor") ExecutorService orderExportExecutor) {
        return () -> {
            ExecutorShutdownUtil.shutdownGracefully(orderQueryExecutor, 10);
            ExecutorShutdownUtil.shutdownGracefully(orderExportExecutor, 60);  // 导出任务给更长时间收尾
        };
    }
}
```

> `@Bean` 返回 `AutoCloseable` 时，Spring 在容器关闭时会自动调用其 `close()`。如果项目统一使用 Spring 的 `ThreadPoolTaskExecutor`，可以用它的 `setWaitForTasksToCompleteOnShutdown(true)` + `setAwaitTerminationSeconds(60)` + `setTaskDecorator(...)`（透传上下文）达到同样效果。

### 4.2 订单详情并行查询（CompletableFuture + 自定义线程池）

**链路：**

```
GET /orders/{orderId}/detail
  │
OrderController.getDetail（① 接口层：参数校验）
  │
OrderBizComponent.getOrderDetail（② 编排层）
  ├─ OrderDao.getById(orderId)                        串行：后续查询依赖订单的 userId、orderNo
  │     └─ 不存在 → BizException(ORDER_NOT_FOUND)
  ├─ 并行（orderQueryExecutor）：
  │     ├─ UserDao.getById(userId)                    ~20ms
  │     ├─ OrderItemDao.listByOrderId(orderId)        ~20ms（商品名称/单价为下单时快照）
  │     └─ LogisticsClient.queryTrace(orderNo)        ~300ms，三方接口，超时 800ms 或失败 → 降级为空物流
  ├─ allOf(...).orTimeout(2s).join()                  总超时兜底
  └─ OrderConverter.toDetailVO(...)                   ⑤ 转换层组装 VO
串行耗时 ≈ 20 + 20 + 300 = 340ms → 并行耗时 ≈ max(20, 20, 300) = 300ms
```

**三方物流返回的 DTO 与出参 VO：**

```java
package com.example.mall.client.dto;

/**
 * 物流轨迹（三方物流接口返回）。
 *
 * @param company    物流公司名称
 * @param trackingNo 运单号
 * @param latestNode 最新物流节点描述
 */
public record LogisticsTraceDTO(String company, String trackingNo, String latestNode) {

    /**
     * 空物流信息，用于未发货或三方接口降级时返回。
     *
     * @return 字段均为空串的物流信息
     */
    public static LogisticsTraceDTO empty() {
        return new LogisticsTraceDTO("", "", "");
    }
}
```

```java
package com.example.mall.model.vo;

import com.example.mall.client.dto.LogisticsTraceDTO;

import java.math.BigDecimal;
import java.util.List;

/**
 * 订单详情出参。
 *
 * @param orderNo     订单号
 * @param status      订单状态码，取值见 OrderStatusEnum（0 待支付/1 已支付/2 已取消/3 已发货/4 已完成）
 * @param totalAmount 订单总金额
 * @param username    下单用户名
 * @param items       订单明细
 * @param logistics   物流信息，降级时为空物流
 */
public record OrderDetailVO(String orderNo, Integer status, BigDecimal totalAmount, String username,
                            List<OrderItemVO> items, LogisticsTraceDTO logistics) {

    /**
     * 订单明细出参。
     *
     * @param productName 商品名称（下单时快照）
     * @param price       单价（下单时快照）
     * @param quantity    购买数量
     */
    public record OrderItemVO(String productName, BigDecimal price, Integer quantity) {
    }
}
```

**编排层：**

```java
package com.example.mall.biz;

import com.example.mall.client.LogisticsClient;
import com.example.mall.client.dto.LogisticsTraceDTO;
import com.example.mall.common.BizException;
import com.example.mall.common.ErrorCode;
import com.example.mall.convert.OrderConverter;
import com.example.mall.dao.OrderDao;
import com.example.mall.dao.OrderItemDao;
import com.example.mall.dao.UserDao;
import com.example.mall.model.po.OrderItemPO;
import com.example.mall.model.po.OrderPO;
import com.example.mall.model.po.UserPO;
import com.example.mall.model.vo.OrderDetailVO;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;

/**
 * 订单编排组件（第二层：编排层）。
 */
@Component
public class OrderBizComponent {

    private static final Logger log = LoggerFactory.getLogger(OrderBizComponent.class);

    /** 物流查询超时时间（毫秒），超时降级 */
    private static final long LOGISTICS_TIMEOUT_MS = 800;
    /** 详情查询整体超时时间（秒） */
    private static final long DETAIL_TIMEOUT_S = 2;

    private final OrderDao orderDao;
    private final UserDao userDao;
    private final OrderItemDao orderItemDao;
    private final LogisticsClient logisticsClient;
    private final Executor orderQueryExecutor;

    /**
     * 构造注入。
     *
     * @param orderDao           订单 DAO
     * @param userDao            用户 DAO
     * @param orderItemDao       订单明细 DAO
     * @param logisticsClient    三方物流客户端
     * @param orderQueryExecutor 订单查询专用线程池
     */
    public OrderBizComponent(OrderDao orderDao, UserDao userDao, OrderItemDao orderItemDao,
                             LogisticsClient logisticsClient,
                             @Qualifier("orderQueryExecutor") Executor orderQueryExecutor) {
        this.orderDao = orderDao;
        this.userDao = userDao;
        this.orderItemDao = orderItemDao;
        this.logisticsClient = logisticsClient;
        this.orderQueryExecutor = orderQueryExecutor;
    }

    /**
     * 查询订单详情：并行查询用户、订单明细、物流后组装。
     *
     * @param orderId 订单 ID
     * @return 订单详情
     * @throws BizException 订单不存在（ORDER_NOT_FOUND）或查询超时（SYSTEM_BUSY）
     */
    // 注：07 章的正式接口为 getOrderDetail(Long userId, String orderNo) 返回 OrderVO；
    // 本章为突出并行查询，用 orderId 入参、带用户与物流信息的 OrderDetailVO 做演示
    public OrderDetailVO getOrderDetail(Long orderId) {
        // 1. 串行查订单：后续查询依赖 userId、orderNo
        OrderPO order = orderDao.getById(orderId);
        if (order == null) {
            throw new BizException(ErrorCode.ORDER_NOT_FOUND);
        }
        // 2. 并行发起三个查询，全部使用自定义线程池
        CompletableFuture<UserPO> userF = CompletableFuture.supplyAsync(
                () -> userDao.getById(order.getUserId()), orderQueryExecutor);
        CompletableFuture<List<OrderItemPO>> itemsF = CompletableFuture.supplyAsync(
                () -> orderItemDao.listByOrderId(orderId), orderQueryExecutor);
        CompletableFuture<LogisticsTraceDTO> logisticsF = queryLogisticsWithFallback(order.getOrderNo());
        // 3. 等待全部完成，整体超时兜底
        joinAll(userF, itemsF, logisticsF);
        // 4. 组装出参（此时各 Future 均已完成，join 不会阻塞）
        return OrderConverter.toDetailVO(order, userF.join(), itemsF.join(), logisticsF.join());
    }

    /**
     * 查询物流，超时或异常时降级为空物流（物流不是详情页的核心信息，不能因它失败）。
     *
     * @param orderNo 订单号
     * @return 物流查询 Future，永不异常完成
     */
    private CompletableFuture<LogisticsTraceDTO> queryLogisticsWithFallback(String orderNo) {
        return CompletableFuture
                .supplyAsync(() -> logisticsClient.queryTrace(orderNo), orderQueryExecutor)
                .completeOnTimeout(LogisticsTraceDTO.empty(), LOGISTICS_TIMEOUT_MS, TimeUnit.MILLISECONDS)
                .exceptionally(ex -> {
                    log.warn("物流查询失败，降级为空物流，orderNo={}", orderNo, ex);
                    return LogisticsTraceDTO.empty();
                });
    }

    /**
     * 等待所有 Future 完成；超时或任一核心查询失败时转换为业务异常。
     *
     * @param futures 需要等待的 Future
     * @throws BizException 超时或核心查询失败时抛出 SYSTEM_BUSY
     */
    private void joinAll(CompletableFuture<?>... futures) {
        try {
            CompletableFuture.allOf(futures).orTimeout(DETAIL_TIMEOUT_S, TimeUnit.SECONDS).join();
        } catch (CompletionException e) {
            // e.getCause() 才是原始异常（TimeoutException 或 DAO 抛出的异常）
            log.error("订单详情并行查询失败", e.getCause());
            throw new BizException(ErrorCode.SYSTEM_BUSY);
        }
    }
}
```

**转换层：**

```java
package com.example.mall.convert;

import com.example.mall.client.dto.LogisticsTraceDTO;
import com.example.mall.model.po.OrderItemPO;
import com.example.mall.model.po.OrderPO;
import com.example.mall.model.po.UserPO;
import com.example.mall.model.vo.OrderDetailVO;

import java.util.List;

/**
 * 订单对象转换器（第五层：数据转换）。
 */
public final class OrderConverter {

    /**
     * 私有构造，工具类禁止实例化。
     */
    private OrderConverter() {
    }

    /**
     * 组装订单详情出参。
     *
     * @param order     订单
     * @param user      下单用户，可能为 null（用户已注销）
     * @param items     订单明细
     * @param logistics 物流信息
     * @return 订单详情 VO
     */
    public static OrderDetailVO toDetailVO(OrderPO order, UserPO user, List<OrderItemPO> items,
                                           LogisticsTraceDTO logistics) {
        List<OrderDetailVO.OrderItemVO> itemVOs = items.stream()
                .map(i -> new OrderDetailVO.OrderItemVO(i.getProductName(), i.getPrice(), i.getQuantity()))
                .toList();
        String username = user == null ? "" : user.getUsername();
        return new OrderDetailVO(order.getOrderNo(), order.getStatus(), order.getTotalAmount(),
                username, itemVOs, logistics);
    }
}
```

**要点回顾：**

| 要点 | 代码位置 | 如果不这样做 |
|---|---|---|
| 指定自定义线程池 | 每个 `supplyAsync` 的第二个参数 | 占用 `commonPool`，影响全局 |
| 非核心依赖降级 | `queryLogisticsWithFallback` | 物流接口抖动拖垮详情页 |
| 单个调用超时 + 整体超时 | `completeOnTimeout` + `orTimeout` | Tomcat 线程被无限期占用 |
| 异常解包 | `e.getCause()` | 日志里只看到 `CompletionException`，找不到根因 |
| 上下文透传 | 若 DAO 内依赖 `UserContext`/MDC，需要 TTL 或 `TaskDecorator` | 子线程拿不到登录用户/TraceId |

> 用虚拟线程怎么写？把 `orderQueryExecutor` 换成 `Executors.newVirtualThreadPerTaskExecutor()` 即可，编排代码一行不改。Java 21 结构化并发（`StructuredTaskScope`，预览特性）能让「一个失败就取消其他」写得更自然。

### 4.3 订单导出线程池

03 章把导出改为游标分批，解决了 OOM。但导出 100 万行仍需几十秒，不能让 HTTP 请求一直等——改为**异步任务**：

```
POST /orders/export
  │
OrderController.export（①）
  │
OrderExportBizComponent.submitExport（②）
  ├─ 生成 taskId
  ├─ orderExportExecutor.execute(导出任务)
  │     ├─ 成功入池 → 立即返回 taskId，前端轮询任务状态
  │     └─ RejectedExecutionException（2 个在跑 + 10 个排队都满了）→ BizException(SYSTEM_BUSY)「导出任务较多，请稍后再试」
  └─ 导出任务（order-export-x 线程）：exportAll(writer) → 上传文件服务 → 更新任务状态（任务表/Redis，略）
```

```java
package com.example.mall.biz;

import com.example.mall.common.BizException;
import com.example.mall.common.ErrorCode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;

/**
 * 在 03 章 OrderExportBizComponent 基础上新增的异步提交方法（片段）。
 * 构造函数新增注入：@Qualifier("orderExportExecutor") Executor orderExportExecutor。
 */
public class OrderExportBizComponentAsyncPart {

    private static final Logger log = LoggerFactory.getLogger(OrderExportBizComponentAsyncPart.class);

    /** 导出专用线程池 */
    private Executor orderExportExecutor;

    /**
     * 提交异步导出任务。
     *
     * @return 导出任务 ID，前端据此轮询进度、下载文件
     * @throws BizException 线程池已满时抛出 SYSTEM_BUSY
     */
    public String submitExport() {
        String taskId = UUID.randomUUID().toString().replace("-", "");
        try {
            orderExportExecutor.execute(() -> runExport(taskId));
        } catch (RejectedExecutionException e) {
            // AbortPolicy 拒绝：把技术异常翻译为用户能理解的业务异常
            throw new BizException(ErrorCode.SYSTEM_BUSY);
        }
        return taskId;
    }

    /**
     * 执行导出（运行在 order-export-x 线程中）。异常必须在此捕获记录，否则会被线程池吞掉/替换线程。
     *
     * @param taskId 导出任务 ID
     */
    private void runExport(String taskId) {
        Path file = Path.of("/data/export", taskId + ".csv");
        try (Writer writer = Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
            long rows = exportAll(writer);           // 复用 03 章的游标分批导出
            log.info("导出完成 taskId={} rows={}", taskId, rows);
            // 上传文件服务、更新任务状态为成功（略）
        } catch (IOException | RuntimeException e) {
            log.error("导出失败 taskId={}", taskId, e);
            // 更新任务状态为失败（略）
        }
    }

    /**
     * 03 章已实现的游标分批导出（此处为占位声明）。
     *
     * @param writer 输出目标
     * @return 导出行数
     * @throws IOException 写出失败
     */
    private long exportAll(Writer writer) throws IOException {
        return 0L;
    }
}
```

> 实际项目里 `submitExport` / `runExport` 直接写在 `OrderExportBizComponent` 中，这里单独成类只为突出本章新增部分。多实例部署时，导出任务状态要存到数据库或 Redis，否则前端轮询打到另一台实例上查不到。更重的导出可以改为发 MQ 消息、由专门的消费者执行（10 章）。

### 4.4 并发扣库存：竞态演示与三种修复

#### 4.4.1 复现超卖

```java
package com.example.mall.lab;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 超卖复现：库存 100，1000 个线程同时各买 1 件。
 */
public class StockOversellLab {

    /** 商品库存（共享可变状态） */
    private int stock = 100;

    /**
     * 扣减库存：先检查后扣减（check-then-act），非原子。
     *
     * @param quantity 购买数量
     * @return 是否扣减成功
     */
    public boolean deduct(int quantity) {
        if (stock >= quantity) {          // ① 检查
            simulateLatency();            // 模拟查库/校验耗时，放大竞态窗口
            stock -= quantity;            // ② 扣减：多个线程可能都通过了 ①
            return true;
        }
        return false;
    }

    /**
     * 模拟 1ms 的业务耗时。
     */
    private void simulateLatency() {
        try {
            Thread.sleep(1);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    /**
     * 程序入口。
     *
     * @param args 命令行参数（未使用）
     * @throws InterruptedException 等待时被中断
     */
    public static void main(String[] args) throws InterruptedException {
        StockOversellLab lab = new StockOversellLab();
        AtomicInteger success = new AtomicInteger();
        CountDownLatch startGate = new CountDownLatch(1);         // 发令枪：让所有线程同时开抢
        CountDownLatch done = new CountDownLatch(1000);
        try (ExecutorService pool = Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < 1000; i++) {
                pool.execute(() -> {
                    try {
                        startGate.await();
                        if (lab.deduct(1)) {
                            success.incrementAndGet();
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    } finally {
                        done.countDown();
                    }
                });
            }
            startGate.countDown();                               // 开抢
            done.await();
        }
        // 典型输出：成功 1000 单，剩余库存 -900 —— 严重超卖
        System.out.println("成功 " + success.get() + " 单，剩余库存 " + lab.stock);
    }
}
```

真实系统中，「检查」和「扣减」之间隔着一次数据库读写，窗口更大：

```
时间 ───────────────────────────────────────────────────────────►
请求 A：SELECT stock → 1 ── 校验通过 ── UPDATE stock = 0
请求 B：     SELECT stock → 1 ── 校验通过 ── UPDATE stock = 0
结果：卖出 2 件，库存显示 0（实际超卖 1 件）
```

#### 4.4.2 修复一：`synchronized`（单机锁）

```java
package com.example.mall.domain;

import com.example.mall.common.BizException;
import com.example.mall.common.ErrorCode;
import com.example.mall.dao.ProductDao;
import com.example.mall.model.po.ProductPO;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * 库存扣减（修复一：synchronized）—— 仅用于说明问题，不推荐。
 */
@Component
public class StockDeductSyncUnit {

    private final ProductDao productDao;

    /**
     * 构造注入。
     *
     * @param productDao 商品 DAO
     */
    public StockDeductSyncUnit(ProductDao productDao) {
        this.productDao = productDao;
    }

    /**
     * 扣减库存。synchronized 保证同一 JVM 内串行执行。
     *
     * @param productId 商品 ID
     * @param quantity  扣减数量
     * @throws BizException 库存不足时抛出 STOCK_NOT_ENOUGH
     */
    @Transactional(rollbackFor = Exception.class)
    public synchronized void deduct(Long productId, int quantity) {
        ProductPO product = productDao.getById(productId);
        if (product.getStock() < quantity) {
            throw new BizException(ErrorCode.STOCK_NOT_ENOUGH);
        }
        product.setStock(product.getStock() - quantity);
        productDao.updateById(product);
    }   // ⚠️ 锁在这里释放，但事务由外层 AOP 代理在方法返回「之后」才提交
}
```

内存版 `StockOversellLab.deduct` 加上 `synchronized` 后结果完全正确。但放到真实服务中有两个致命问题：

**问题 1：锁与事务的边界错位（单机也会超卖）**

```
Spring 代理：开启事务 → 调用 deduct()（加锁 → 读 stock=1 → 写 stock=0 → 释放锁）→ 提交事务
                                                                     │
请求 B 在「释放锁」与「提交事务」的间隙拿到锁 ──► 读到的仍是未提交的旧值 stock=1（RR 隔离级别）→ 再次扣减
```

修正方式是让锁包住整个事务（在调用方加锁，再调用带 `@Transactional` 的方法），但问题 2 仍无解。

**问题 2：只在单个 JVM 内有效**

```
              ┌─ 实例 1：synchronized ─┐
负载均衡 ──►  ├─ 实例 2：synchronized ─┼──► 同一行 t_product
              └─ 实例 3：synchronized ─┘
三把锁互不相干 → 依然超卖
```

此外，`synchronized` 把所有商品的扣减串行化成一条队列（锁的是 `this`），吞吐极低。

#### 4.4.3 修复二：数据库乐观锁（推荐）

把「检查 + 扣减」合并为**一条原子 SQL**，让数据库行锁保证正确性——这就是 2.7 节 CAS 思想在数据库上的体现。

```java
package com.example.mall.dao.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.example.mall.model.po.ProductPO;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

/**
 * 商品 Mapper（MyBatis-Plus）。
 */
public interface ProductMapper extends BaseMapper<ProductPO> {

    /**
     * 条件扣减库存：库存充足才扣减，原子完成「检查 + 扣减」。
     *
     * @param productId 商品 ID
     * @param quantity  扣减数量
     * @return 影响行数：1 成功，0 库存不足
     */
    @Update("UPDATE t_product SET stock = stock - #{quantity}, version = version + 1, update_time = NOW() "
            + "WHERE id = #{productId} AND stock >= #{quantity}")
    int deductStock(@Param("productId") Long productId, @Param("quantity") int quantity);

    /**
     * 版本号乐观锁扣减（CAS 写法）：只有版本号未变才更新。
     *
     * @param productId 商品 ID
     * @param quantity  扣减数量
     * @param version   读取时的版本号
     * @return 影响行数：1 成功，0 版本冲突或库存不足
     */
    @Update("UPDATE t_product SET stock = stock - #{quantity}, version = version + 1, update_time = NOW() "
            + "WHERE id = #{productId} AND version = #{version} AND stock >= #{quantity}")
    int deductStockWithVersion(@Param("productId") Long productId, @Param("quantity") int quantity,
                             @Param("version") Integer version);
}
```

```java
package com.example.mall.dao;

import com.example.mall.dao.mapper.ProductMapper;
import org.springframework.stereotype.Repository;

/**
 * 商品 DAO（第四层：能力单元）。
 */
@Repository
public class ProductDao {

    private final ProductMapper productMapper;

    /**
     * 构造注入。
     *
     * @param productMapper 商品 Mapper
     */
    public ProductDao(ProductMapper productMapper) {
        this.productMapper = productMapper;
    }

    /**
     * 扣减库存（库存充足才扣减）。
     *
     * @param productId 商品 ID
     * @param quantity  扣减数量
     * @return true 扣减成功；false 库存不足
     */
    public boolean deductStock(Long productId, int quantity) {
        return productMapper.deductStock(productId, quantity) == 1;
    }
}
```

| 写法 | 原理 | 冲突时 | 适用 |
|---|---|---|---|
| `WHERE stock >= #{quantity}` | 依赖 InnoDB 行锁串行化 UPDATE，条件在锁内判断 | 无需重试，影响行数 0 即库存不足 | **扣库存首选**：简单、不会因冲突误失败 |
| `WHERE version = #{version}` | 典型 CAS：读版本号 → 带版本更新 | 影响行数 0 需重新读取并重试（限次数） | 需要基于读到的整体状态做复杂计算后再写回 |

优点：无应用层锁、天然支持多实例、粒度是单行。局限：热点商品（秒杀）所有请求都在同一行上排队等行锁，数据库扛不住——这时需要 Redis 预扣库存（09 章）。完整的索引、事务与行锁原理见 [08 章](./08-database-orm.md)。

#### 4.4.4 修复三：分布式锁（预告）

当扣减逻辑无法合并为一条 SQL（例如要同时校验限购、优惠券、多个外部状态），需要跨 JVM 的互斥：

```java
// 预告示意：Redisson 分布式锁，完整实现与坑点见 09 章
RLock lock = redissonClient.getLock(RedisKeys.stockLock(productId)); // key: mall:lock:stock:{productId}，见 09 章 RedisKeys
if (!lock.tryLock(1, TimeUnit.SECONDS)) {          // 最多等 1 秒；不指定租期时启用看门狗自动续期
    throw new BizException(ErrorCode.SYSTEM_BUSY);
}
try {
    stockDeductUnit.deduct(productId, quantity);   // 另一个 Bean 的 @Transactional 方法：锁包住整个事务
} finally {
    if (lock.isHeldByCurrentThread()) {
        lock.unlock();
    }
}
```

需要关注的问题：锁超时与业务耗时、主从切换导致锁丢失、锁粒度、与事务的先后顺序。详见 [09 章 Redis 与缓存](./09-redis-cache.md)。

#### 4.4.5 三种方案对比

| 方案 | 多实例 | 性能 | 复杂度 | 结论 |
|---|---|---|---|---|
| `synchronized` | ❌ | 差（全局串行） | 低，但有事务边界陷阱 | 只适合单机内存状态 |
| 数据库条件更新 / 乐观锁 | ✅ | 中（行锁，热点行受限） | 低 | **普通商品的默认方案** |
| Redis 分布式锁 | ✅ | 中（多一次网络往返） | 高 | 复杂校验逻辑需要互斥时 |
| Redis + Lua 预扣（09 章） | ✅ | 高 | 高（需保证与 DB 一致） | 秒杀等热点场景（13 章） |

> 一单多商品时，**先按 productId 升序排序再逐个扣减**，避免两个订单以相反顺序锁行导致数据库死锁（2.14）。

---

## 5. 常见坑

| # | 坑 | 后果 | 正确做法 |
|---|---|---|---|
| 1 | 用 `Executors.newFixedThreadPool` 等创建线程池 | 无界队列 OOM / 无限线程 | `new ThreadPoolExecutor` + 有界队列 + 命名 + 拒绝策略 |
| 2 | `CompletableFuture.supplyAsync` 不传线程池 | 占满 `commonPool`，并行流和其他异步任务全部卡住 | 永远传入业务线程池 |
| 3 | `ThreadLocal` 不 `remove` | 用户身份串号、内存泄漏 | `try/finally` 中 `remove` |
| 4 | 子线程拿不到 TraceId / 登录用户 | 日志断链、权限判断出错 | TTL 或 `TaskDecorator` |
| 5 | Spring 单例 Bean 中定义可变成员变量（如 `private int count`、`private SimpleDateFormat sdf`） | 所有请求线程共享，数据错乱 | Bean 保持无状态；用局部变量或线程安全类（`DateTimeFormatter`） |
| 6 | `volatile int` 做计数 | 依然丢失更新 | `AtomicInteger` / `LongAdder` |
| 7 | 锁住了不同的对象（如每次 `new Object()` 作锁、`synchronized` 锁了 `Integer` 等会变的引用） | 锁不住 | 锁对象用 `private final` 字段 |
| 8 | `synchronized` + `@Transactional` 在同一方法上 | 锁先于事务提交释放，仍然超卖 | 锁包住事务，或改用数据库条件更新 |
| 9 | `submit()` 提交任务不处理 Future | 异常被吞，问题无声无息 | 用 `execute()`，或任务内 try/catch 记录日志 |
| 10 | 捕获 `InterruptedException` 后什么都不做 | 线程池无法正常关闭 | `Thread.currentThread().interrupt()` |
| 11 | 在锁内调用远程接口 / 慢 SQL | 锁持有时间长，吞吐骤降，甚至连锁超时 | 锁内只做必要的内存/单条 SQL 操作 |
| 12 | 父子任务共用同一个线程池（父任务在池中等待子任务结果） | 线程全被父任务占满，子任务排队 → **线程池死锁** | 父子任务用不同线程池 |
| 13 | 虚拟线程 + `synchronized` 内阻塞 I/O（Java 21） | pinning，服务假死 | 用 `ReentrantLock`，或升级 Java 24+ |
| 14 | 用固定大小的虚拟线程池限流 | 违背虚拟线程设计、无意义 | 每任务一个虚拟线程 + `Semaphore` 限流 |
| 15 | `HashMap` 在多线程下读写 | 数据丢失，Java 7 下死循环 | `ConcurrentHashMap` |

---

## 6. 高级视角

### 6.1 线程池的可观测与治理

线程池是线上故障高发区，必须**可监控、可告警、可动态调整**：

| 指标 | 获取方式 | 告警含义 |
|---|---|---|
| 活跃线程数 / 最大线程数 | `getActiveCount()` / `getMaximumPoolSize()` | 接近 100% = 处理能力饱和 |
| 队列长度 / 队列容量 | `getQueue().size()` / `remainingCapacity()` | 持续增长 = 消费跟不上生产 |
| 拒绝次数 | 自定义 `RejectedExecutionHandler` 计数 | 已经在丢任务或降级 |
| 任务执行耗时 | 重写 `beforeExecute` / `afterExecute` | 下游变慢的先兆 |
| 任务排队耗时 | 提交时记录时间戳，执行时计算差值 | 排队时间比执行时间更能反映用户体验 |

Micrometer 提供 `ExecutorServiceMetrics.monitor(registry, executor, "orderQueryExecutor")` 一行接入 Prometheus（12 章）。

### 6.2 线程池隔离与舱壁模式

```
           ┌─ orderQueryExecutor（详情页）    ← 慢了只影响详情页
请求 ──►   ├─ orderExportExecutor（导出）     ← 满了直接拒绝，不影响其他
           └─ payCallbackExecutor（支付回调） ← 最关键，单独保障
```

这就是**舱壁模式（Bulkhead）**：船舱分隔，一个进水不会沉船。Sentinel、Resilience4j 都提供基于线程池或信号量的隔离（11 章）。

### 6.3 选择并发方案的决策树

```
需要并发处理吗？
 ├─ 多个独立 I/O 调用想并行 ──────────► CompletableFuture + 业务线程池（或虚拟线程）
 ├─ 高并发 I/O 密集型 Web 服务（Java 21+）► 开启虚拟线程，注意 pinning 与下游限流
 ├─ 后台批量任务 ───────────────────► 有界线程池 + 分批；更重的走 MQ（10 章）
 └─ 共享可变状态？
       ├─ 能不共享就不共享：局部变量、不可变对象（record）、ThreadLocal
       ├─ 单个变量的原子更新 ────────► Atomic* / LongAdder
       ├─ 并发容器能解决 ─────────────► ConcurrentHashMap / BlockingQueue
       ├─ 进程内复合操作 ────────────► synchronized（默认）/ ReentrantLock（需要超时、可中断）
       └─ 跨进程 / 多实例 ───────────► 数据库条件更新 / 乐观锁 → 分布式锁（08/09 章）
```

### 6.4 从「本地线程安全」到「分布式一致性」

本章的所有锁都只在**一个 JVM 内**生效。服务一旦多实例部署（几乎所有生产环境），「线程安全」问题就升级为「分布式一致性」问题：

| 单机概念 | 分布式对应 | 章节 |
|---|---|---|
| `synchronized` / `Lock` | 分布式锁（Redisson） | 09 |
| CAS / 版本号 | 数据库乐观锁、Redis `WATCH` / Lua | 08、09 |
| 原子性（一组操作全成或全不成） | 本地事务 → 分布式事务（Seata、本地消息表） | 08、11 |
| 可见性 | 缓存一致性（先更新库再删缓存） | 09 |
| 幂等（重复执行结果一致） | 唯一索引、去重表、Token | 10 |

> 高级工程师的思维习惯：**看到「先查后改」（check-then-act）就警觉**，无论它发生在内存、数据库还是 Redis 上；然后问三个问题：多线程下安全吗？多实例下安全吗？重试/重复消息下安全吗？

---

## 7. 小练习

1. **i++ 实验**：运行 2.3 的 `CounterLab`，分别用 `synchronized`、`AtomicInteger`、`LongAdder` 修复，用 JMH 或简单计时对比 10 个、100 个线程下三者的耗时。
2. **可见性实验**：运行 `VisibilityLab`，去掉 `volatile` 后观察程序是否退出；再加 `-Xint`（纯解释执行）运行，解释为什么结果不同（提示：JIT 的循环不变量外提）。
3. **线程池行为**：创建 `core=2, max=4, queue=2` 的线程池，提交 10 个各睡眠 1 秒的任务，打印每个任务的执行线程名和是否被拒绝，验证 2.9 的执行流程图；换成 `CallerRunsPolicy` 再观察。
4. **CompletableFuture 改写**：把一段 TS 代码 `const [a, b] = await Promise.all([f1(), f2()]); const c = await f3(a, b);` 用 `thenCombine` + `thenCompose` 改写为 Java，要求指定线程池并处理异常。
5. **ThreadLocal 串号**：用一个核心线程数为 1 的线程池提交两个任务，第一个任务 `set` 了用户 ID 但不 `remove`，验证第二个任务读到了脏数据；再用 TTL 改造。
6. **死锁排查**：运行 `DeadlockLab`，分别用 `jstack` 和 Arthas `thread -b` 定位；然后用「固定加锁顺序」修复。
7. **超卖修复**：运行 `StockOversellLab` 复现超卖；在本地 MySQL 中建 `t_product` 表，用 `deductStock` 条件更新 + 1000 个虚拟线程并发验证不再超卖，并统计成功单数是否恰好等于初始库存。
8. **虚拟线程 pinning**：Java 21 下写一个在 `synchronized` 中 `Thread.sleep(100)` 的任务，用 1 万个虚拟线程执行，开启 `-Djdk.tracePinnedThreads=full` 观察输出与总耗时；改用 `ReentrantLock` 后对比。
