# 01 Java 语言基础：用 TS 的眼睛看 Java

> [← 总纲](./00-outline.md) | 上一章：无 | 下一章：[02 集合框架与常用 API →](./02-collections-and-api.md)

---

## 1. 本章地图

**本章解决的问题**：你已经会写 TS，现在要在最短时间内「读懂并写对」Java 代码。

```
全景图中的位置：
┌──────────── 一个 Spring Boot 进程（JVM） ────────────┐
│  Controller / Component / DAO ...  ← 全部用 Java 写   │
│  ↑ 本章：这些代码的「语法 + 类型系统 + 惯用法」       │
└──────────────────────────────────────────────────────┘
```

| 主题 | 你需要带走的结论 |
|---|---|
| 编译与运行 | `.java → javac → .class 字节码 → JVM 解释 + JIT`；类型在编译期检查，**运行时也保留大部分类型信息**（泛型除外） |
| 类型系统 | 静态、名义类型；8 种基本类型 + 引用类型；金额用 `BigDecimal` |
| 面向对象 | 一切代码都在类里；单继承 + 多接口；访问修饰符真的生效 |
| 泛型 | 写法像 TS，但运行时被擦除；PECS 规则 |
| 异常 | 受检 vs 非受检；业务异常用自定义 `RuntimeException` |
| 函数式 | Lambda 只能赋给函数式接口；Stream ≈ 惰性的数组方法链；Optional ≈ `?.` + `??` |
| 新特性 | Java 8 → 21：`var`、switch 表达式、文本块、record、sealed、模式匹配 |

mini-mall 本章产出（包名 `com.example.mall`）：

| 类 | 包 | 作用 |
|---|---|---|
| `OrderStatusEnum` | `model.enums` | 订单状态枚举（code 0~4） |
| `ErrorCode` | `common` | 错误码枚举 |
| `BizException` | `common` | 业务异常 |
| `OrderPO` / `OrderItemPO` | `model.po` | 对应 `t_order` / `t_order_item` 表的实体 |
| `OrderAmountUtil` | `util` | 用 Stream 计算订单总额 |

---

## 2. 前端类比：先建立第一印象

| 你熟悉的 TS 世界 | Java 世界 | 一句话差异 |
|---|---|---|
| 文件里可以直接写函数、变量 | **所有代码都必须在类里** | 没有顶层函数，工具函数写成 `static` 方法 |
| `tsc` 把 TS 擦成 JS，类型全部消失 | `javac` 产出字节码，类型信息大部分保留 | Java 运行时能反射拿到字段类型、注解 |
| 结构化类型（长得像就兼容） | 名义类型（必须声明 `implements`） | 「鸭子类型」在 Java 不存在 |
| `number` 一把梭 | `int / long / double / BigDecimal` | 溢出、精度都需要你自己负责 |
| `{ a: 1 }` 对象字面量 | 先定义类，再 `new` | 数据结构必须先有类型 |
| `null` 和 `undefined` | 只有 `null` | NPE（空指针）是第一大异常 |
| 抛什么都行 `throw "x"` | 只能抛 `Throwable` 子类，部分异常编译器强制处理 | 受检异常是 Java 独有设计 |
| `import x from './x'` | `import com.example.mall.common.BizException;` | 按「包名 + 类名」导入，包名 = 目录 |

**最重要的心态转变**：TS 的类型是「给编辑器看的注释」，运行时一切皆可变；Java 的类型是「契约」，编译器和 JVM 都会严格执行。在 Java 里，**先设计类型，再写逻辑**。

---

## 3. 核心概念

### 3.1 编译与运行：javac、字节码、JVM

```
TS 流水线：
  order.ts ──tsc──▶ order.js ──V8 解析──▶ 字节码(Ignition) ──热点──▶ 机器码(TurboFan)
           (类型擦除)              (运行时才知道 JS 文本)

Java 流水线：
  Order.java ──javac──▶ Order.class(字节码) ──JVM 类加载──▶ 解释执行 ──热点──▶ JIT(C1/C2) 机器码
           (类型检查)    (平台无关, 含类型信息)
```

| 对比项 | TS + V8 | Java + JVM |
|---|---|---|
| 编译产物 | JS 源码（文本） | `.class` 字节码（二进制，平台无关） |
| 类型何时检查 | 只在 `tsc` 阶段；运行时无类型 | `javac` 检查 + JVM 加载时字节码校验 |
| 分发单位 | 打包后的 bundle | `.jar`（本质是 zip，内含 `.class` 和资源） |
| 启动 | 快 | 相对慢（类加载 + JIT 预热），Spring 应用秒级 |
| 长期运行性能 | JIT 优化 | JIT 优化更激进（C2、逃逸分析），服务端长跑更稳 |

最小可运行程序：

```ts
// TS：main.ts —— 顶层直接写
const name: string = "mini-mall";
console.log(`hello ${name}`);
```

```java
// Java：Main.java —— 文件名必须与 public 类名一致
package com.example.mall;

/**
 * 程序入口类。
 */
public class Main {

    /**
     * JVM 启动入口：JVM 会找 public static void main(String[]) 这个签名。
     *
     * @param args 命令行参数，等价于 Node 的 process.argv.slice(2)
     */
    public static void main(String[] args) {
        String name = "mini-mall";
        // 字符串模板 Java 没有，用 + 拼接或 String.format / formatted
        System.out.println("hello %s".formatted(name));
    }
}
```

```bash
javac -d out src/com/example/mall/Main.java   # 编译，产出 out/com/example/mall/Main.class
java -cp out com.example.mall.Main            # 运行，按「全限定类名」找入口
javap -c -cp out com.example.mall.Main        # 反编译查看字节码（相当于看 V8 的 --print-bytecode）
```

> `main` 为什么必须是 `static`？JVM 启动时还没有任何对象，只能调用「属于类本身」的方法。
> Java 21 有预览特性「未命名类与实例 main」可以省掉 `class` 和 `static`，但工程中不用。

### 3.2 静态类型与 `var`

```ts
let count = 1;          // 推断为 number
const list: string[] = [];
```

```java
int count = 1;                      // 显式声明
var list = new ArrayList<String>(); // Java 10+：编译期推断为 ArrayList<String>
final var max = 100;                // final ≈ const：引用不可再赋值
// list = 1;                        // 编译错误：var 不是 any，推断后类型就固定了
```

`var` 的规则：

| 能用 | 不能用 |
|---|---|
| 局部变量（有初始化值） | 字段、方法参数、返回值 |
| for 循环变量、try-with-resources | `var x = null;`（推不出类型） |
| Lambda 参数（Java 11+，为了加注解） | 数组初始化 `var a = {1, 2};` |

> 团队规范建议：右侧类型一眼可见时用 `var`（`var map = new HashMap<Long, OrderPO>()`），否则写明类型。

### 3.3 8 种基本类型与包装类型

| 基本类型 | 字节 | 范围/说明 | 包装类型 | TS 对应 |
|---|---|---|---|---|
| `byte` | 1 | -128 ~ 127 | `Byte` | number |
| `short` | 2 | ±3.2 万 | `Short` | number |
| `int` | 4 | ±21 亿 | `Integer` | number |
| `long` | 8 | ±9.2×10¹⁸（写 `100L`） | `Long` | number / bigint |
| `float` | 4 | 单精度（写 `1.0f`） | `Float` | number |
| `double` | 8 | 双精度，与 JS number 相同 | `Double` | number |
| `char` | 2 | 一个 UTF-16 码元 `'a'` | `Character` | string（长度 1） |
| `boolean` | — | `true/false` | `Boolean` | boolean |

**基本类型 vs 包装类型**：

```
int a = 10;               Integer b = 10;
栈上直接存值              栈上存引用 ──▶ 堆上 Integer 对象 { value: 10 }
不能为 null               可以为 null
不能做泛型参数            List<Integer> 只能用包装类型
```

**自动装箱/拆箱**：编译器帮你插入转换代码。

```java
Integer boxed = 100;      // 编译后：Integer.valueOf(100)   —— 装箱
int raw = boxed;          // 编译后：boxed.intValue()       —— 拆箱
Integer nullValue = null;
int boom = nullValue;     // 运行时 NullPointerException！拆箱调用了 null.intValue()
```

**选型规则（阿里规范同款）**：

| 场景 | 用什么 | 原因 |
|---|---|---|
| PO/DTO/VO 字段 | 包装类型 `Integer`、`Long` | 数据库字段可能为 NULL；基本类型默认值 0 会掩盖「没传」 |
| 局部变量、循环计数 | 基本类型 `int`、`long` | 无对象开销 |
| 主键 id | `Long` | 21 亿上限对订单表不够用 |
| 金额 | `BigDecimal` | 浮点无法精确表示十进制小数 |

**金额为什么不能用 double**（JS 同样有这个问题）：

```ts
0.1 + 0.2 === 0.3  // false，0.30000000000000004
```

```java
System.out.println(0.1 + 0.2);                                   // 0.30000000000000004
BigDecimal a = new BigDecimal("0.1");                            // 必须用字符串构造！
BigDecimal b = new BigDecimal("0.2");
System.out.println(a.add(b));                                    // 0.3
System.out.println(new BigDecimal(0.1));                         // 0.1000000000000000055511151231257827...
System.out.println(BigDecimal.valueOf(0.1));                     // 0.1（内部走 Double.toString）
// 比较大小用 compareTo，不要用 equals：equals 会比较精度（scale）
System.out.println(new BigDecimal("1.0").equals(new BigDecimal("1.00")));    // false
System.out.println(new BigDecimal("1.0").compareTo(new BigDecimal("1.00"))); // 0
// 除法必须指定舍入，否则除不尽时抛 ArithmeticException
BigDecimal avg = new BigDecimal("10").divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP); // 3.33
```

### 3.4 String：不可变、equals vs ==、StringBuilder

```ts
const a = "mall"; const b = "ma" + "ll";
a === b;   // true：JS 的 === 对字符串比较的是值
```

```java
String a = "mall";
String b = new String("mall");
System.out.println(a == b);        // false：== 比较引用（是不是同一个对象）
System.out.println(a.equals(b));   // true ：equals 比较内容
System.out.println("mall".equals(input)); // 常量写前面，input 为 null 也不会 NPE
System.out.println(Objects.equals(a, b)); // 两边都可能为 null 时的首选
```

**为什么 String 设计成不可变**：

1. **字符串常量池**：字面量 `"mall"` 在池中只存一份，多处共享——前提是谁都改不了它。
2. **hashCode 可缓存**：String 是 HashMap 最常用的 key，不可变才能缓存 hash。
3. **线程安全**：多线程共享无需加锁（前端没有这个顾虑，Java 有，见 04 章）。
4. **安全**：类名、URL、文件路径都是 String，被篡改会出事。

不可变的代价是拼接会产生新对象。循环里拼接用 `StringBuilder`：

```java
/**
 * 把订单号列表拼成逗号分隔字符串。
 *
 * @param orderNos 订单号列表
 * @return 形如 "A001,A002" 的字符串
 */
public static String joinOrderNos(List<String> orderNos) {
    StringBuilder sb = new StringBuilder();
    for (String no : orderNos) {
        if (!sb.isEmpty()) {          // Java 15+ 才有 isEmpty，老版本用 length() > 0
            sb.append(',');
        }
        sb.append(no);
    }
    return sb.toString();
    // 实际项目直接用：String.join(",", orderNos)
}
```

| 类 | 可变 | 线程安全 | 用途 |
|---|---|---|---|
| `String` | 否 | 是 | 一切常规场景 |
| `StringBuilder` | 是 | 否 | 方法内拼接（99% 场景） |
| `StringBuffer` | 是 | 是（synchronized） | 历史遗留，基本不用 |

> 单行 `"a" + b + "c"` 不必手动改 StringBuilder，编译器会优化（Java 9+ 用 `invokedynamic` + `StringConcatFactory`）。只有**循环中**的 `+=` 才有性能问题。

常用 API 对照：

| JS | Java |
|---|---|
| `s.length` | `s.length()` |
| `s.includes(x)` | `s.contains(x)` |
| `s.trim()` | `s.trim()` / `s.strip()`（Java 11+，支持 Unicode 空白） |
| `s.split(",")` | `s.split(",")`（参数是**正则**，`"."` 要写 `"\\."`） |
| `` `a${b}` `` | `"a%s".formatted(b)` / `String.format` |
| `s === ''` | `s.isEmpty()`；空白判断 `s.isBlank()`（Java 11+） |
| `s.padStart(5,'0')` | `String.format("%05d", n)` |

### 3.5 类、对象、构造器、访问修饰符、static、final

```ts
class Product {
  private stock: number;
  static count = 0;
  constructor(public readonly name: string, stock: number) {
    this.stock = stock;
    Product.count++;
  }
  deduct(n: number): boolean { /* ... */ return true; }
}
```

```java
/**
 * 商品示例类（仅演示语法，正式 PO 见 mini-mall 实战）。
 */
public class Product {

    /** 已创建实例数，属于类而非对象（≈ TS 的 static 字段） */
    private static int count = 0;

    /** 商品名，final 表示构造后不可再赋值（≈ readonly） */
    private final String name;

    /** 库存 */
    private int stock;

    /**
     * 构造器：与类同名、无返回值。
     *
     * @param name  商品名
     * @param stock 初始库存
     */
    public Product(String name, int stock) {
        this.name = name;
        this.stock = stock;
        count++;
    }

    /**
     * 重载构造器：不传库存时默认 0（Java 没有参数默认值，靠重载实现）。
     *
     * @param name 商品名
     */
    public Product(String name) {
        this(name, 0); // 调用另一个构造器，必须是第一行
    }

    /**
     * 扣减库存。
     *
     * @param n 扣减数量
     * @return 库存足够并扣减成功返回 true
     */
    public boolean deduct(int n) {
        if (stock < n) {
            return false;
        }
        stock -= n;
        return true;
    }

    /**
     * 获取商品名（Java 没有 TS 的 get 访问器语法，约定写 getXxx 方法）。
     *
     * @return 商品名
     */
    public String getName() {
        return name;
    }
}
```

**访问修饰符**（TS 的 `private` 只在编译期生效，Java 运行时也生效）：

| 修饰符 | 同类 | 同包 | 子类 | 任意位置 | 典型用途 |
|---|---|---|---|---|---|
| `private` | ✓ | | | | 字段、内部辅助方法 |
| （默认，不写） | ✓ | ✓ | | | 包内协作类 |
| `protected` | ✓ | ✓ | ✓ | | 留给子类覆写的扩展点 |
| `public` | ✓ | ✓ | ✓ | ✓ | 对外 API |

**static 与 final 速查**：

| 用在 | `static` | `final` |
|---|---|---|
| 字段 | 属于类，所有对象共享一份 | 只能赋值一次 |
| 方法 | 不需要对象即可调用，不能用 `this` | 不能被子类覆写 |
| 类 | 只能修饰内部类（静态内部类） | 不能被继承（如 `String`） |
| 局部变量 | 不可用 | 不可再赋值 |

> 常量写法：`public static final int MAX_QUANTITY = 99;`（≈ `export const MAX_QUANTITY = 99`）。
> `final` 只保证**引用**不变：`final List<String> list` 仍然可以 `list.add(...)`，与 TS `const arr` 一样。

### 3.6 继承与多态

```java
/**
 * 支付方式抽象基类。
 */
public abstract class PayChannel {

    /**
     * 发起支付，由子类实现具体渠道逻辑。
     *
     * @param orderNo 订单号
     * @param amount  支付金额
     * @return 渠道返回的支付流水号
     */
    public abstract String pay(String orderNo, BigDecimal amount);

    /**
     * 模板方法：统一的支付流程（校验 → 调用子类实现）。
     *
     * @param orderNo 订单号
     * @param amount  支付金额
     * @return 支付流水号
     */
    public final String doPay(String orderNo, BigDecimal amount) {
        // 统一校验金额必须大于 0
        if (amount.compareTo(BigDecimal.ZERO) <= 0) {
            throw new IllegalArgumentException("金额必须大于 0");
        }
        // 动态分派：运行时根据对象真实类型调用对应子类的 pay
        return pay(orderNo, amount);
    }
}

/**
 * 支付宝渠道实现。
 */
public class AlipayChannel extends PayChannel {

    /**
     * 调用支付宝下单（示例返回假流水号）。
     *
     * @param orderNo 订单号
     * @param amount  支付金额
     * @return 支付流水号
     */
    @Override // 注解：让编译器检查确实覆写了父类方法，签名写错会编译失败
    public String pay(String orderNo, BigDecimal amount) {
        return "ALI-" + orderNo;
    }
}

// 多态：声明类型是父类，实际对象是子类
PayChannel channel = new AlipayChannel();
channel.doPay("A001", new BigDecimal("9.90")); // 执行 AlipayChannel.pay
```

**多态的底层（原理深挖会展开）**：编译期按「声明类型」检查方法存在，运行期按「实际类型」查虚方法表（vtable）决定调用哪个实现。

**重载 vs 覆写**：

| | 重载 Overload | 覆写 Override |
|---|---|---|
| 位置 | 同一个类 | 父子类之间 |
| 签名 | 方法名同，参数列表不同 | 完全相同 |
| 决议时机 | **编译期**（按声明类型选） | **运行期**（按实际类型选） |
| TS 对应 | 函数重载签名（只有一个实现） | 子类覆写方法 |

### 3.7 抽象类 vs 接口；名义类型 vs 结构化类型

```ts
interface Priced { getPrice(): number }
class Book { getPrice() { return 10 } }          // 没写 implements
const p: Priced = new Book();                    // ✓ TS：结构匹配即可
```

```java
/**
 * 有价格的事物。
 */
public interface Priced {

    /**
     * 获取价格。
     *
     * @return 价格
     */
    BigDecimal getPrice();

    /**
     * 默认方法（Java 8+）：接口里可以带实现，实现类可直接继承或覆写。
     *
     * @param quantity 数量
     * @return 单价 × 数量
     */
    default BigDecimal totalOf(int quantity) {
        return getPrice().multiply(BigDecimal.valueOf(quantity));
    }
}

public class Book {
    /** 价格 */
    public BigDecimal getPrice() { return BigDecimal.TEN; }
}

// Priced p = new Book();  // ✗ 编译错误：Book 没有声明 implements Priced，长得像也不行
```

| 对比 | 抽象类 `abstract class` | 接口 `interface` |
|---|---|---|
| 继承数量 | 只能 `extends` 一个 | 可以 `implements` 多个 |
| 字段 | 任意实例字段 | 只能有 `public static final` 常量 |
| 构造器 | 有 | 无 |
| 方法 | 抽象 + 具体 | 抽象 + `default` + `static` + `private`（Java 9+） |
| 语义 | 「是什么」（is-a），共享状态和模板流程 | 「能做什么」（can-do），定义能力契约 |
| 工程用法 | 模板方法模式的基类 | Service 契约、策略、回调、函数式接口 |

**名义类型的好处**：意图明确、重构安全（搜 `implements Priced` 就能找到所有实现）、IDE 和框架（Spring 按接口类型注入）都依赖它。代价是需要「适配器」把第三方类接进你的接口。

### 3.8 内部类与匿名类

```java
public class OrderService {

    /**
     * 静态内部类：不持有外部类引用，常用于 Builder、私有 DTO。
     * 首选这种，避免隐式持有外部对象导致内存泄漏。
     */
    public static class QueryParam {
        /** 用户 id */
        private Long userId;
    }

    /**
     * 成员内部类：隐式持有 OrderService.this，可直接访问外部实例字段。
     */
    private class Worker {
    }

    /**
     * 演示匿名类与 Lambda 的等价写法。
     */
    public void demo() {
        // 匿名类：就地实现接口，Java 8 之前的「回调」写法
        Runnable r1 = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous");
            }
        };
        // Lambda：函数式接口的简写（≈ 箭头函数）
        Runnable r2 = () -> System.out.println("lambda");
    }
}
```

| 类型 | 持有外部实例 | 用途 |
|---|---|---|
| 静态内部类 | 否 | Builder、嵌套数据结构（首选） |
| 成员内部类 | 是 | 迭代器实现等紧耦合场景 |
| 局部类 | 是（在实例方法中） | 很少用 |
| 匿名类 | 是（在实例方法中） | 实现多方法接口/抽象类；单方法时用 Lambda 替代 |

> 匿名类和 Lambda 的 `this` 不同：匿名类的 `this` 是匿名类对象自己；Lambda 的 `this` 是外部类对象（与箭头函数的词法 this 一致）。

### 3.9 enum：完整的类

```ts
type OrderStatus = 'CREATED' | 'PAID' | 'CANCELLED';            // 只是字符串
enum OrderStatusTs { CREATED = 0, PAID = 1 }                    // TS 数字枚举，反向映射
```

```java
// Java 枚举：每个值都是该枚举类的一个单例对象，可以有字段、构造器、方法
public enum PayType {
    /** 支付宝 */
    ALIPAY("支付宝"),
    /** 微信支付 */
    WECHAT("微信");

    /** 展示名称 */
    private final String label;

    /**
     * 枚举构造器，隐式 private。
     *
     * @param label 展示名称
     */
    PayType(String label) {
        this.label = label;
    }

    /**
     * 获取展示名称。
     *
     * @return 展示名称
     */
    public String getLabel() {
        return label;
    }
}
```

枚举的内置能力：

| API | 作用 | 注意 |
|---|---|---|
| `PayType.valueOf("ALIPAY")` | 按名字取枚举 | 名字不存在抛 `IllegalArgumentException` |
| `PayType.values()` | 所有枚举值数组 | 每次调用复制一个新数组 |
| `e.name()` | 枚举名字符串 | 不要存库，改名就断 |
| `e.ordinal()` | 声明顺序下标 | **绝不能存库**，插入新值就错位 |
| `==` 比较 | 枚举是单例，`==` 安全 | `switch` 可直接用 |
| `EnumMap` / `EnumSet` | 以枚举为 key 的高效集合 | 内部是数组/位图 |

> 存库规范：给枚举定义显式 `code` 字段，数据库存 code，读出后用 `of(code)` 反查。见 mini-mall 实战。

### 3.10 record：不可变数据类（Java 16+）

```ts
type Money = { readonly amount: number; readonly currency: string };
const m: Money = { amount: 1, currency: 'CNY' };
```

```java
/**
 * 金额值对象：record 自动生成 private final 字段、全参构造器、
 * 访问器 amount()/currency()、equals/hashCode/toString。
 *
 * @param amount   金额
 * @param currency 币种，如 CNY
 */
public record Money(BigDecimal amount, String currency) {

    /**
     * 紧凑构造器：做参数校验。
     */
    public Money {
        Objects.requireNonNull(amount, "amount 不能为空");
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("金额不能为负");
        }
    }

    /**
     * 金额相加，返回新对象（不可变风格）。
     *
     * @param other 另一笔金额（币种需一致）
     * @return 相加后的新 Money
     */
    public Money add(Money other) {
        return new Money(amount.add(other.amount), currency);
    }
}
```

| 用 record | 不用 record |
|---|---|
| 值对象、方法内部临时元组、DTO/VO（Jackson 2.12+ 支持） | MyBatis-Plus 的 PO（需要无参构造 + setter）、JPA Entity |
| 不可变、按值比较 | 需要继承（record 隐式 final） |

### 3.11 泛型：写法像 TS，运行时被擦除

```ts
function first<T>(list: T[]): T | undefined { return list[0]; }
interface Result<T> { code: number; message: string; data: T }
```

```java
/**
 * 统一返回体（mini-mall 的 Result<T>，07 章会补全静态工厂方法）。
 *
 * @param <T> 业务数据类型
 */
public class Result<T> {
    /** 业务码，0 表示成功 */
    private int code;
    /** 提示信息 */
    private String message;
    /** 业务数据 */
    private T data;
}

/**
 * 泛型方法：类型参数写在返回值前面。
 *
 * @param list 列表
 * @param <T>  元素类型
 * @return 第一个元素，空列表返回 null
 */
public static <T> T first(List<T> list) {
    return list.isEmpty() ? null : list.get(0);
}

/**
 * 有界类型参数（≈ TS 的 T extends Comparable<T>）。
 *
 * @param a   第一个值
 * @param b   第二个值
 * @param <T> 可比较的类型
 * @return 较大者
 */
public static <T extends Comparable<T>> T max(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

**通配符与 PECS**：

Java 泛型是**不变**的：`List<Integer>` 不是 `List<Number>` 的子类型（TS 的数组却是协变的，这在 TS 里是个已知的不安全点）。

```java
List<Integer> ints = List.of(1, 2);
// List<Number> nums = ints;          // ✗ 编译错误：否则 nums.add(1.5) 会把 double 塞进 int 列表
List<? extends Number> nums = ints;   // ✓ 协变视图：只能读（读出 Number），不能写
```

| 写法 | 能读出 | 能写入 | 口诀 |
|---|---|---|---|
| `List<T>` | `T` | `T` | 精确类型 |
| `List<? extends T>` | `T` | 只能写 `null` | **Producer Extends**：从它取数据 |
| `List<? super T>` | `Object` | `T` 及子类 | **Consumer Super**：往它放数据 |
| `List<?>` | `Object` | 只能写 `null` | 不关心元素类型 |

```java
/**
 * PECS 经典示例（Collections.copy 同款签名）：src 生产数据用 extends，dest 消费数据用 super。
 *
 * @param dest 目标列表，可接收 T 或其父类元素
 * @param src  源列表，提供 T 或其子类元素
 * @param <T>  元素类型
 */
public static <T> void copyAll(List<? super T> dest, List<? extends T> src) {
    for (T item : src) {
        dest.add(item);
    }
}
```

**类型擦除的直接后果**：

```java
// 以下都是编译错误或无效：
// new T();                          运行时不知道 T 是谁
// new T[10];                        同上
// if (obj instanceof List<String>)  运行时只剩 List
// 重载 void f(List<String>) 和 void f(List<Integer>)  擦除后签名相同，冲突
List<String> a = new ArrayList<>();
List<Integer> b = new ArrayList<>();
System.out.println(a.getClass() == b.getClass()); // true，都是 ArrayList
```

需要运行时类型时，显式传 `Class<T>`：`objectMapper.readValue(json, OrderVO.class)`；需要泛型嵌套类型时用 `TypeReference`（02 章 Jackson 部分）。

### 3.12 异常体系

```
                    Throwable
                   /         \
               Error          Exception
     (JVM 级，不要捕获)       /          \
     OutOfMemoryError   受检异常          RuntimeException（非受检）
     StackOverflowError IOException      NullPointerException
                        SQLException     IllegalArgumentException
                        (编译器强制处理)  IllegalStateException
                                         BizException（我们自定义的）
```

| 类别 | 编译器要求 | 语义 | 例子 |
|---|---|---|---|
| 受检异常 checked | 必须 `try/catch` 或在方法签名 `throws` | 可预期、调用方应当处理的外部失败 | `IOException` |
| 非受检异常 unchecked | 不强制 | 编程错误或业务规则违反 | `NPE`、`BizException` |
| Error | 不应捕获 | JVM 无法恢复的问题 | `OOM` |

```ts
try { await fetchOrder(); } catch (e) { /* e: unknown */ } finally { }
```

```java
/**
 * 读取配置文件内容。
 *
 * @param path 文件路径
 * @return 文件全部文本
 * @throws IOException 文件不存在或读取失败（受检异常，调用方必须处理）
 */
public static String readConfig(Path path) throws IOException {
    // try-with-resources：括号里的资源在块结束时自动 close（≈ TS 5.2 的 using）
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        return reader.lines().collect(Collectors.joining("\n"));
    }
}

/**
 * 多 catch、按子类到父类顺序捕获。
 */
public static void demo() {
    try {
        readConfig(Path.of("app.conf"));
    } catch (NoSuchFileException e) {
        // 更具体的异常放前面
        System.out.println("文件不存在：" + e.getFile());
    } catch (IOException | UncheckedIOException e) {
        // 多异常合并捕获（Java 7+）
        throw new IllegalStateException("读取配置失败", e); // 包装时务必传 cause，保留原始堆栈
    } finally {
        System.out.println("finally 一定执行");
    }
}
```

**业务异常的设计**：业界共识是业务异常继承 `RuntimeException`，原因：
- 受检异常会沿着调用链「传染」所有方法签名，且与 Lambda 不兼容（`Function` 不允许抛受检异常）；
- Spring 的 `@Transactional` 默认只对 `RuntimeException` 回滚（06 章）；
- 统一由全局异常处理器（07 章 `@RestControllerAdvice`）翻译成 `Result`。

### 3.13 Lambda 与函数式接口

**函数式接口** = 只有一个抽象方法的接口。Lambda 是它的实例。Java 没有「函数类型」，只有「只有一个方法的接口」。

```ts
const double = (x: number) => x * 2;
const isPaid: (s: number) => boolean = s => s === 1;
```

```java
Function<Integer, Integer> doubler = x -> x * 2;
Predicate<Integer> isPaid = s -> s == 1;
System.out.println(doubler.apply(3));  // 6 —— 调用要写方法名 apply，不能 doubler(3)
```

`java.util.function` 常用接口：

| 接口 | 签名 | TS 对应 | 典型用途 |
|---|---|---|---|
| `Function<T,R>` | `R apply(T)` | `(t: T) => R` | `map` |
| `Predicate<T>` | `boolean test(T)` | `(t: T) => boolean` | `filter` |
| `Consumer<T>` | `void accept(T)` | `(t: T) => void` | `forEach` |
| `Supplier<T>` | `T get()` | `() => T` | 延迟创建、`orElseGet` |
| `BiFunction<T,U,R>` | `R apply(T,U)` | `(t: T, u: U) => R` | `reduce`、`Map.merge` |
| `UnaryOperator<T>` | `T apply(T)` | `(t: T) => T` | `replaceAll` |
| `Runnable` | `void run()` | `() => void` | 线程任务 |
| `Callable<V>` | `V call() throws Exception` | `() => V` | 有返回值的线程任务 |

自定义函数式接口：

```java
/**
 * 价格计算策略。
 */
@FunctionalInterface // 编译器检查确实只有一个抽象方法
public interface PriceStrategy {

    /**
     * 计算最终价格。
     *
     * @param origin 原价
     * @return 折后价
     */
    BigDecimal calc(BigDecimal origin);
}

PriceStrategy vip = origin -> origin.multiply(new BigDecimal("0.9"));
```

**变量捕获规则**：Lambda 只能捕获 **effectively final** 的局部变量（赋值后没再改过）。

```java
int count = 0;
// list.forEach(x -> count++);   // ✗ 编译错误
// 原因：Lambda 可能在另一个线程执行，局部变量在栈上，复制一份值进去才安全；
//      允许修改会造成「改的是副本」的困惑。JS 闭包捕获的是变量本身，没有这个限制。
```

### 3.14 方法引用

| 形式 | 示例 | 等价 Lambda |
|---|---|---|
| 静态方法 | `Integer::parseInt` | `s -> Integer.parseInt(s)` |
| 特定对象的实例方法 | `System.out::println` | `x -> System.out.println(x)` |
| 任意对象的实例方法 | `OrderPO::getUserId` | `o -> o.getUserId()` |
| 构造器 | `ArrayList::new` | `() -> new ArrayList<>()` |

`OrderPO::getUserId` 是最高频写法，在 Stream、MyBatis-Plus 的 `LambdaQueryWrapper`（08 章）中随处可见。

### 3.15 Stream API 入门（对比数组方法）

```ts
const total = items
  .filter(i => i.quantity > 0)
  .map(i => i.price * i.quantity)
  .reduce((a, b) => a + b, 0);
```

```java
BigDecimal total = items.stream()
        .filter(i -> i.getQuantity() > 0)
        .map(i -> i.getPrice().multiply(BigDecimal.valueOf(i.getQuantity())))
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

| JS 数组方法 | Java Stream | 备注 |
|---|---|---|
| `map` | `map` / `mapToInt` | 基本类型流避免装箱 |
| `filter` | `filter` | |
| `reduce` | `reduce` | |
| `find` | `filter(..).findFirst()` | 返回 `Optional` |
| `some` / `every` | `anyMatch` / `allMatch` | 短路 |
| `flatMap` | `flatMap` | Java 需返回 Stream |
| `slice(0, n)` | `limit(n)` / `skip(n)` | |
| `sort` | `sorted(Comparator)` | 不修改原集合 |
| `[...new Set(a)]` | `distinct()` | 依赖 equals/hashCode |
| `forEach` | `forEach` | 终结操作 |
| `arr.length` | `count()` | |
| 结果就是数组 | `toList()`（Java 16+）/ `collect(Collectors.toList())` | `toList()` 返回不可变列表 |

**与 JS 数组方法的本质差异**：

```
JS：  [1..5].filter(f).map(g)  → filter 遍历 5 次产出新数组，再 map 遍历
Java：stream.filter(f).map(g).toList()
      中间操作只是「搭流水线」，终结操作 toList 触发后，每个元素依次穿过 f → g
      元素1: f → g → 收集
      元素2: f ✗（被过滤，不进 g）
      ...
```

1. **惰性求值**：没有终结操作（`toList/collect/reduce/forEach/count`），什么都不执行。
2. **只能消费一次**：同一个 Stream 第二次使用抛 `IllegalStateException`。
3. **不修改源集合**。

### 3.16 Optional（对比 `?.` 与 `??`）

```ts
const city = order?.user?.address?.city ?? '未知';
```

```java
String city = Optional.ofNullable(order)
        .map(OrderDetail::getUser)
        .map(User::getAddress)
        .map(Address::getCity)
        .orElse("未知");
```

| TS | Java Optional |
|---|---|
| `a ?? b` | `Optional.ofNullable(a).orElse(b)` |
| `a ?? compute()` | `.orElseGet(() -> compute())`（懒执行） |
| `a?.b` | `.map(A::getB)` |
| `if (!a) throw` | `.orElseThrow(() -> new BizException(...))` |
| `if (a) use(a)` | `.ifPresent(this::use)` |

**使用规范**：
- ✓ 作为**方法返回值**，表达「可能没有」：`Optional<OrderPO> findByOrderNo(String no)`。
- ✗ 不作为字段、方法参数、集合元素（不可序列化、徒增包装）。
- ✗ 不要 `opt.get()` 不判空；不要 `opt.isPresent() ? opt.get() : x`（这就是换了个写法的 `!= null`）。
- `orElse(x)` 的 `x` 总会被求值，有开销的默认值用 `orElseGet`。

### 3.17 equals / hashCode 约定

JS 的 `Map`/`Set` 用引用（`SameValueZero`）判断对象 key；Java 的 `HashMap`/`HashSet` 用 `hashCode()` 找桶，再用 `equals()` 判等。**自定义类作 key 或放 Set，必须同时覆写两者**。

约定（`Object` 文档规定）：
1. `a.equals(b)` 为 true ⇒ `a.hashCode() == b.hashCode()`（反之不要求）。
2. 自反、对称、传递、一致；`x.equals(null)` 为 false。
3. 参与 hashCode 计算的字段，放进 HashSet 后不应再修改，否则再也找不到它。

```java
/**
 * 商品 SKU 键：用 productId + specId 唯一确定一个 SKU。
 */
public final class SkuKey {
    /** 商品 id */
    private final Long productId;
    /** 规格 id */
    private final Long specId;

    /**
     * @param productId 商品 id
     * @param specId    规格 id
     */
    public SkuKey(Long productId, Long specId) {
        this.productId = productId;
        this.specId = specId;
    }

    /**
     * 按 productId + specId 判断相等。
     *
     * @param o 另一个对象
     * @return 两个字段都相等返回 true
     */
    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof SkuKey other)) return false; // Java 16+ 模式匹配
        return Objects.equals(productId, other.productId) && Objects.equals(specId, other.specId);
    }

    /**
     * 与 equals 使用相同字段计算哈希。
     *
     * @return 哈希值
     */
    @Override
    public int hashCode() {
        return Objects.hash(productId, specId);
    }
}
// 更简单：public record SkuKey(Long productId, Long specId) {} —— record 自动生成正确的 equals/hashCode
```

只覆写 `equals` 不覆写 `hashCode` 的后果：两个「相等」的对象落到不同的桶，`set.contains` 返回 false、`HashSet` 里出现「重复」元素。

### 3.18 Java 8 → 21 新特性速览

| 版本 | 特性 | 一句话 |
|---|---|---|
| 8 | Lambda、Stream、Optional、`java.time`、接口默认方法 | 大量存量项目停留在此 |
| 9 | 模块系统、`List.of`、接口私有方法 | |
| 10 | `var` | |
| 11 LTS | `String.isBlank/strip/lines/repeat`、`HttpClient` | |
| 14 | switch 表达式（正式） | |
| 15 | 文本块 `"""` | |
| 16 | record、`instanceof` 模式匹配、`Stream.toList()` | |
| 17 LTS | sealed 类 | Spring Boot 3 的最低版本 |
| 21 LTS | 虚拟线程、switch 模式匹配、record 模式、`SequencedCollection` | 本系列基线 |

**switch 表达式**（对比 TS 的 switch 语句）：

```java
// Java 8：语句式，容易漏 break 造成穿透
String label;
switch (status) {
    case 0: label = "待支付"; break;
    case 1: label = "已支付"; break;
    default: label = "未知";
}

// Java 14+：表达式式，箭头不穿透，可直接返回值；对枚举 switch 编译器检查是否穷举
String label2 = switch (statusEnum) {
    case CREATED -> "待支付";
    case PAID -> "已支付";
    case CANCELLED, SHIPPED, COMPLETED -> "其他";
};
```

**文本块**（≈ 模板字符串的多行能力，但没有插值）：

```java
String sql = """
        SELECT id, order_no, total_amount
        FROM t_order
        WHERE user_id = ? AND status = ?
        """;
String json = """
        {"orderNo": "%s", "amount": %s}
        """.formatted("A001", "9.90");
```

**sealed 类 + 模式匹配**（≈ TS 可辨识联合 + 穷尽检查）：

```ts
type PayResult =
  | { kind: 'success'; tradeNo: string }
  | { kind: 'fail'; reason: string };
function msg(r: PayResult) {
  switch (r.kind) {
    case 'success': return `成功 ${r.tradeNo}`;
    case 'fail': return `失败 ${r.reason}`;
  }
}
```

```java
/**
 * 支付结果：sealed 限定只有这两种实现，编译器可做穷尽检查。
 */
public sealed interface PayResult permits PayResult.Success, PayResult.Fail {

    /**
     * 支付成功。
     *
     * @param tradeNo 支付流水号
     */
    record Success(String tradeNo) implements PayResult { }

    /**
     * 支付失败。
     *
     * @param reason 失败原因
     */
    record Fail(String reason) implements PayResult { }

    /**
     * 生成提示文案（Java 21 switch 模式匹配 + record 解构）。
     *
     * @param r 支付结果
     * @return 提示文案
     */
    static String message(PayResult r) {
        return switch (r) {
            case Success(String tradeNo) -> "成功 " + tradeNo;
            case Fail(String reason) -> "失败 " + reason;
            // 不需要 default：sealed 已穷尽，新增子类型时这里会编译报错
        };
    }
}
```

---

## 4. 原理深挖

### 4.1 Integer 缓存：`==` 的经典坑

```java
Integer a = 127, b = 127;
System.out.println(a == b);   // true
Integer c = 128, d = 128;
System.out.println(c == d);   // false ！
System.out.println(c.equals(d)); // true
```

原因：自动装箱调用 `Integer.valueOf(int)`，其源码：

```java
public static Integer valueOf(int i) {
    if (i >= IntegerCache.low && i <= IntegerCache.high)   // 默认 -128 ~ 127
        return IntegerCache.cache[i + (-IntegerCache.low)]; // 返回缓存的同一个对象
    return new Integer(i);                                  // 超出范围每次新建
}
```

- `Byte/Short/Long/Character(0~127)/Boolean` 都有类似缓存；`Float/Double` 没有。
- 上限可用 `-XX:AutoBoxCacheMax=` 调整（只影响 Integer）。
- **线上真实事故模式**：`if (order.getUserId() == currentUserId)`，两边都是 `Long`。测试环境用户 id 小于 128，全部通过；线上 id 很大，永远 false。**包装类型比较一律用 `equals` 或 `Objects.equals`**。

### 4.2 多态的实现：虚方法表

```
            方法区（元空间）中的类元数据
PayChannel vtable:              AlipayChannel vtable:
 [0] toString → Object.toString   [0] toString → Object.toString
 [1] pay      → (abstract)        [1] pay      → AlipayChannel.pay   ← 覆写替换槽位
 [2] doPay    → PayChannel.doPay  [2] doPay    → PayChannel.doPay

channel.pay(...) 编译为 invokevirtual PayChannel.pay
运行时：取对象头中的类指针 → 找到 AlipayChannel 的 vtable → 槽位 [1] → 调用
```

- 字节码有 5 种调用指令：`invokestatic`（静态）、`invokespecial`（构造器/私有/super）、`invokevirtual`（虚方法）、`invokeinterface`（接口方法）、`invokedynamic`（Lambda、字符串拼接）。
- JIT 会做**内联缓存**：若某调用点实际只出现过一种类型（单态），直接内联成普通调用；多态调用点超过 2 种类型（megamorphic）才走虚表。这就是「接口只有一个实现时几乎零开销」的原因。
- `final`/`private`/`static` 方法无需动态分派。

### 4.3 Lambda 不是匿名类的语法糖

```
匿名类：  javac 生成 OrderService$1.class，每处匿名类一个文件，运行时 new 出对象
Lambda：  javac 把 Lambda 体编译为本类的私有静态方法 lambda$demo$0
          调用点生成 invokedynamic 指令
          首次执行时 LambdaMetafactory 动态生成实现类（内存中），之后复用
```

好处：不产生大量 `.class` 文件、类加载开销低；无捕获的 Lambda 会被缓存成单例。这也解释了为何 Lambda 里的 `this` 是外部对象——它本来就是外部类的一个方法。

### 4.4 类型擦除：为什么 Java 选择擦除

```java
// 源码
List<String> list = new ArrayList<>();
list.add("a");
String s = list.get(0);

// 擦除后的字节码等价物
List list = new ArrayList();
list.add("a");
String s = (String) list.get(0);   // 编译器自动插入强转
```

设计取舍：Java 5 引入泛型时，要求**新代码能与没有泛型的老 jar 二进制兼容**（迁移兼容性），所以选了擦除。代价：

| 代价 | 规避方式 |
|---|---|
| 不能 `new T()` / `new T[]` | 传 `Class<T>` 或 `Supplier<T>` |
| 不能 `instanceof List<String>` | 检查元素类型 |
| 基本类型不能做泛型参数 → 装箱开销 | `IntStream`、专用集合库 |
| 堆污染（raw type 混入错误类型） | 不用原始类型 `List`，开启编译警告 |

对比：TS 泛型也被完全擦除（连类都没了），C# 泛型是「具化」的（运行时保留）。注意 **擦除并不彻底**：类声明、字段、方法签名上的泛型信息作为元数据保留在 `.class` 中，可以反射读到——Jackson 的 `TypeReference`、Spring 的泛型注入都靠这一点。

### 4.5 受检异常：设计初衷与争议

- 初衷：把「可能失败」写进方法签名，编译器强制调用方思考失败路径（类似 Rust 的 `Result`）。
- 争议：大量代码只是 `catch (Exception e) { e.printStackTrace(); }` 或层层 `throws`；与 Lambda/Stream 不兼容；后来的 JVM 语言（Kotlin、Scala）都取消了受检异常。
- 工程实践：底层 I/O 抛受检异常 → 在能力单元层（DAO/Client）捕获并**包装为非受检异常**（保留 cause）→ 上层统一处理。

**异常的性能成本**：创建异常时 `fillInStackTrace` 会遍历栈帧，是主要开销。高频业务异常（如参数校验失败）可覆写 `fillInStackTrace` 或用 `super(message, null, false, false)` 关闭栈追踪；但常规业务异常保留堆栈更利于排查，不要过早优化。

### 4.6 String 的内存与常量池

```
String a = "mall";            String b = new String("mall");
      │                              │
      ▼                              ▼
  ┌ 字符串常量池（堆中）┐        堆：String 对象 ──value──┐
  │  "mall" ◀───────────┼──────────────────────────────────┘ 共享底层 byte[]
  └────────────────────┘
b.intern() → 返回池中的 "mall"，于是 a == b.intern() 为 true
```

- Java 9+ **紧凑字符串**：纯 Latin-1 内容用 `byte[]` 每字符 1 字节存，否则用 UTF-16 每字符 2 字节，节省约一半内存。
- 编译期常量折叠：`"ma" + "ll"` 在编译期就合并成 `"mall"`，所以与字面量 `==` 为 true；含变量的拼接在运行期产生新对象。

---

## 5. mini-mall 实战

目标：定义订单领域的基础类型，并用 Stream 计算订单总额。

```
本章产出在分层中的位置：
com.example.mall
├── common        ErrorCode、BizException
├── model
│   ├── enums     OrderStatusEnum
│   └── po        OrderPO、OrderItemPO
└── util          OrderAmountUtil
```

### 5.1 OrderStatusEnum

```java
package com.example.mall.model.enums;

import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * 订单状态枚举，code 与 t_order.status（TINYINT）一一对应。
 */
public enum OrderStatusEnum {

    /** 待支付：下单成功后的初始状态 */
    CREATED(0, "待支付"),
    /** 已支付 */
    PAID(1, "已支付"),
    /** 已取消：超时未支付或用户主动取消 */
    CANCELLED(2, "已取消"),
    /** 已发货 */
    SHIPPED(3, "已发货"),
    /** 已完成：用户确认收货 */
    COMPLETED(4, "已完成");

    /** 存库编码，禁止修改已有值 */
    private final int code;

    /** 中文描述，用于展示 */
    private final String desc;

    /** 反查缓存，key 为 code，value 为对应枚举；类加载时构建一次 */
    private static final Map<Integer, OrderStatusEnum> CODE_MAP = Arrays.stream(values())
            .collect(Collectors.toUnmodifiableMap(OrderStatusEnum::getCode, Function.identity()));

    /**
     * 枚举构造器。
     *
     * @param code 存库编码
     * @param desc 中文描述
     */
    OrderStatusEnum(int code, String desc) {
        this.code = code;
        this.desc = desc;
    }

    /**
     * 获取存库编码。
     *
     * @return 编码
     */
    public int getCode() {
        return code;
    }

    /**
     * 获取中文描述。
     *
     * @return 描述
     */
    public String getDesc() {
        return desc;
    }

    /**
     * 根据编码查找枚举。
     *
     * @param code 存库编码，可为 null
     * @return 对应枚举；code 为 null 或不存在时返回 null
     */
    public static OrderStatusEnum of(Integer code) {
        return code == null ? null : CODE_MAP.get(code);
    }

    /**
     * 判断当前状态能否流转到目标状态（状态机规则集中在枚举内，避免散落在业务代码里）。
     *
     * @param target 目标状态
     * @return 允许流转返回 true
     */
    public boolean canTransitTo(OrderStatusEnum target) {
        return switch (this) {
            // 待支付 → 已支付 / 已取消
            case CREATED -> target == PAID || target == CANCELLED;
            // 已支付 → 已发货
            case PAID -> target == SHIPPED;
            // 已发货 → 已完成
            case SHIPPED -> target == COMPLETED;
            // 终态不可再流转
            case CANCELLED, COMPLETED -> false;
        };
    }
}
```

> 为什么用 `Map` 缓存而不是每次 `values()` 遍历？`values()` 每次复制数组，`of` 在列表接口中高频调用。5 个值时差别不大，但这是标准写法。

### 5.2 ErrorCode 与 BizException

```java
package com.example.mall.common;

/**
 * 业务错误码。code 规则（全书统一，完整清单见 07 章）：0 成功；1xxxx 通用/参数/鉴权；2xxxx 商品域；3xxxx 订单域；9xxxx 系统错误。
 */
public enum ErrorCode {

    /** 成功 */
    SUCCESS(0, "成功"),
    /** 参数错误 */
    PARAM_ERROR(10001, "参数错误"),
    /** 系统繁忙（兜底未知异常） */
    SYSTEM_ERROR(99999, "系统繁忙，请稍后重试"),
    /** 订单不存在 */
    ORDER_NOT_FOUND(30001, "订单不存在"),
    /** 订单状态不允许当前操作 */
    ORDER_STATUS_ILLEGAL(30002, "订单状态不允许当前操作"),
    /** 商品库存不足 */
    STOCK_NOT_ENOUGH(20002, "商品库存不足");

    /** 错误码，返回给前端 Result.code */
    private final int code;

    /** 默认提示信息 */
    private final String message;

    /**
     * @param code    错误码
     * @param message 默认提示信息
     */
    ErrorCode(int code, String message) {
        this.code = code;
        this.message = message;
    }

    /**
     * 获取错误码。
     *
     * @return 错误码
     */
    public int getCode() {
        return code;
    }

    /**
     * 获取默认提示信息。
     *
     * @return 提示信息
     */
    public String getMessage() {
        return message;
    }
}
```

```java
package com.example.mall.common;

/**
 * 业务异常：表示业务规则不满足（非系统故障），由全局异常处理器翻译为 Result 返回。
 * 继承 RuntimeException：不强制调用方捕获，且能触发 @Transactional 默认回滚。
 */
public class BizException extends RuntimeException {

    /** 错误码 */
    private final ErrorCode errorCode;

    /**
     * 使用错误码默认提示信息构造。
     *
     * @param errorCode 错误码
     */
    public BizException(ErrorCode errorCode) {
        super(errorCode.getMessage());
        this.errorCode = errorCode;
    }

    /**
     * 使用自定义提示信息构造（如带上具体订单号）。
     *
     * @param errorCode 错误码
     * @param message   自定义提示信息
     */
    public BizException(ErrorCode errorCode, String message) {
        super(message);
        this.errorCode = errorCode;
    }

    /**
     * 包装底层异常，保留原始 cause 便于排查。
     *
     * @param errorCode 错误码
     * @param message   提示信息
     * @param cause     原始异常
     */
    public BizException(ErrorCode errorCode, String message, Throwable cause) {
        super(message, cause);
        this.errorCode = errorCode;
    }

    /**
     * 获取错误码。
     *
     * @return 错误码
     */
    public ErrorCode getErrorCode() {
        return errorCode;
    }
}
```

### 5.3 OrderPO 与 OrderItemPO

> 这里手写 getter/setter 以便看清本质；05 章引入 Lombok 后用 `@Data` 替代，08 章再加 MyBatis-Plus 注解。

```java
package com.example.mall.model.po;

import com.example.mall.model.enums.OrderStatusEnum;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 订单表 t_order 的实体。字段一律使用包装类型，以区分「数据库 NULL」与「0」。
 */
public class OrderPO {

    /** 主键 */
    private Long id;
    /** 订单号，全局唯一 */
    private String orderNo;
    /** 下单用户 id */
    private Long userId;
    /** 订单总金额，对应 DECIMAL(10,2) */
    private BigDecimal totalAmount;
    /** 订单状态编码，取值见 OrderStatusEnum */
    private Integer status;
    /** 创建时间 */
    private LocalDateTime createTime;
    /** 更新时间 */
    private LocalDateTime updateTime;

    /** @return 主键 */
    public Long getId() { return id; }
    /** @param id 主键 */
    public void setId(Long id) { this.id = id; }
    /** @return 订单号 */
    public String getOrderNo() { return orderNo; }
    /** @param orderNo 订单号 */
    public void setOrderNo(String orderNo) { this.orderNo = orderNo; }
    /** @return 用户 id */
    public Long getUserId() { return userId; }
    /** @param userId 用户 id */
    public void setUserId(Long userId) { this.userId = userId; }
    /** @return 订单总金额 */
    public BigDecimal getTotalAmount() { return totalAmount; }
    /** @param totalAmount 订单总金额 */
    public void setTotalAmount(BigDecimal totalAmount) { this.totalAmount = totalAmount; }
    /** @return 状态编码 */
    public Integer getStatus() { return status; }
    /** @param status 状态编码 */
    public void setStatus(Integer status) { this.status = status; }
    /** @return 创建时间 */
    public LocalDateTime getCreateTime() { return createTime; }
    /** @param createTime 创建时间 */
    public void setCreateTime(LocalDateTime createTime) { this.createTime = createTime; }
    /** @return 更新时间 */
    public LocalDateTime getUpdateTime() { return updateTime; }
    /** @param updateTime 更新时间 */
    public void setUpdateTime(LocalDateTime updateTime) { this.updateTime = updateTime; }

    /**
     * 获取状态枚举，避免业务代码到处写魔法数字。
     *
     * @return 状态枚举，status 为空时返回 null
     */
    public OrderStatusEnum statusEnum() {
        return OrderStatusEnum.of(status);
    }
}
```

> `statusEnum()` 故意不叫 `getStatusEnum()`：很多框架（Jackson、BeanUtils）把 `getXxx` 当作属性，会多序列化一个字段。

```java
package com.example.mall.model.po;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 订单明细表 t_order_item 的实体。商品名、单价是下单时的快照，不随商品表变化。
 */
public class OrderItemPO {

    /** 主键 */
    private Long id;
    /** 所属订单 id */
    private Long orderId;
    /** 商品 id */
    private Long productId;
    /** 商品名快照 */
    private String productName;
    /** 下单时单价快照 */
    private BigDecimal price;
    /** 购买数量 */
    private Integer quantity;
    /** 创建时间 */
    private LocalDateTime createTime;

    /** @return 主键 */
    public Long getId() { return id; }
    /** @param id 主键 */
    public void setId(Long id) { this.id = id; }
    /** @return 订单 id */
    public Long getOrderId() { return orderId; }
    /** @param orderId 订单 id */
    public void setOrderId(Long orderId) { this.orderId = orderId; }
    /** @return 商品 id */
    public Long getProductId() { return productId; }
    /** @param productId 商品 id */
    public void setProductId(Long productId) { this.productId = productId; }
    /** @return 商品名快照 */
    public String getProductName() { return productName; }
    /** @param productName 商品名快照 */
    public void setProductName(String productName) { this.productName = productName; }
    /** @return 单价快照 */
    public BigDecimal getPrice() { return price; }
    /** @param price 单价快照 */
    public void setPrice(BigDecimal price) { this.price = price; }
    /** @return 购买数量 */
    public Integer getQuantity() { return quantity; }
    /** @param quantity 购买数量 */
    public void setQuantity(Integer quantity) { this.quantity = quantity; }
    /** @return 创建时间 */
    public LocalDateTime getCreateTime() { return createTime; }
    /** @param createTime 创建时间 */
    public void setCreateTime(LocalDateTime createTime) { this.createTime = createTime; }
}
```

### 5.4 用 Stream 计算订单总额

```java
package com.example.mall.util;

import com.example.mall.common.BizException;
import com.example.mall.common.ErrorCode;
import com.example.mall.model.po.OrderItemPO;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

/**
 * 订单金额计算工具（第五层：最小能力单元，无状态、纯函数）。
 */
public final class OrderAmountUtil {

    /** 金额保留小数位，与 DECIMAL(10,2) 一致 */
    private static final int AMOUNT_SCALE = 2;

    /**
     * 工具类禁止实例化。
     */
    private OrderAmountUtil() {
    }

    /**
     * 计算单条明细金额 = 单价 × 数量。
     *
     * @param item 订单明细，price、quantity 不能为空
     * @return 明细金额
     */
    public static BigDecimal calcItemAmount(OrderItemPO item) {
        // 校验：空值与非法数量属于参数错误
        if (item.getPrice() == null || item.getQuantity() == null || item.getQuantity() <= 0) {
            throw new BizException(ErrorCode.PARAM_ERROR, "明细价格或数量非法，productId=" + item.getProductId());
        }
        return item.getPrice().multiply(BigDecimal.valueOf(item.getQuantity()));
    }

    /**
     * 计算订单总额：对所有明细金额求和，并按两位小数四舍五入。
     *
     * @param items 订单明细列表，可为空列表
     * @return 订单总额；空列表返回 0.00
     */
    public static BigDecimal calcTotalAmount(List<OrderItemPO> items) {
        return items.stream()
                // 每条明细映射为金额
                .map(OrderAmountUtil::calcItemAmount)
                // 以 0 为初始值累加，BigDecimal::add 是 BinaryOperator<BigDecimal>
                .reduce(BigDecimal.ZERO, BigDecimal::add)
                // 统一精度，避免 1.5 与 1.50 在比较或存库时出现差异
                .setScale(AMOUNT_SCALE, RoundingMode.HALF_UP);
    }
}
```

调用示例（相当于一个自检的 main，05 章会改写成 JUnit 测试）：

```java
/**
 * OrderAmountUtil 的手工自检入口。
 *
 * @param args 未使用
 */
public static void main(String[] args) {
    OrderItemPO apple = new OrderItemPO();
    apple.setProductId(1L);
    apple.setPrice(new BigDecimal("3.30"));
    apple.setQuantity(3);

    OrderItemPO milk = new OrderItemPO();
    milk.setProductId(2L);
    milk.setPrice(new BigDecimal("0.10"));
    milk.setQuantity(2);

    BigDecimal total = OrderAmountUtil.calcTotalAmount(List.of(apple, milk));
    // 3.30*3 + 0.10*2 = 10.10；若用 double 计算会得到 10.099999999999998
    if (total.compareTo(new BigDecimal("10.10")) != 0) {
        throw new AssertionError("总额计算错误：" + total);
    }
    System.out.println("total = " + total); // total = 10.10
}
```

**状态流转校验**（组合枚举 + 业务异常的典型写法，07 章编排层会复用）：

```java
/**
 * 校验订单能否流转到目标状态，不能则抛业务异常。
 *
 * @param order  订单
 * @param target 目标状态
 */
public static void checkTransit(OrderPO order, OrderStatusEnum target) {
    OrderStatusEnum current = order.statusEnum();
    // current 为空说明数据异常，也视为不可流转
    if (current == null || !current.canTransitTo(target)) {
        throw new BizException(ErrorCode.ORDER_STATUS_ILLEGAL,
                "订单 %s 当前状态 %s 不能变更为 %s".formatted(order.getOrderNo(),
                        current == null ? "未知" : current.getDesc(), target.getDesc()));
    }
}
```

---

## 6. 常见坑

| # | 坑 | 错误写法 | 正确写法 |
|---|---|---|---|
| 1 | 包装类型用 `==` 比较 | `order.getUserId() == userId` | `Objects.equals(order.getUserId(), userId)` |
| 2 | 字符串用 `==` 比较 | `if (status == "PAID")` | `"PAID".equals(status)` |
| 3 | 自动拆箱 NPE | `int s = order.getStatus();`（status 为 null） | 先判空，或用包装类型接收 |
| 4 | 三目运算符隐式拆箱 | `Integer x = flag ? order.getStatus() : 0;` status 为 null 时 NPE | 两个分支类型统一为 `Integer`：`flag ? order.getStatus() : Integer.valueOf(0)` |
| 5 | `new BigDecimal(0.1)` | 精度丢失 | `new BigDecimal("0.1")` 或 `BigDecimal.valueOf(0.1)` |
| 6 | BigDecimal 用 `equals` 比大小 | `"1.0" equals "1.00"` 为 false | `compareTo == 0` |
| 7 | BigDecimal 除法不指定舍入 | `a.divide(b)` 除不尽抛异常 | `a.divide(b, 2, RoundingMode.HALF_UP)` |
| 8 | 整数溢出不报错 | `int total = price * 100_000_000;` 静默变负数 | 用 `long`，或 `Math.multiplyExact` 溢出时抛异常 |
| 9 | 整数除法 | `1 / 2 == 0` | 需要小数时 `1.0 / 2` 或 BigDecimal |
| 10 | 吞异常 | `catch (Exception e) {}` | 至少记日志；包装重抛时传 cause |
| 11 | 只覆写 equals | HashSet 去重失效 | 同时覆写 hashCode，或用 record |
| 12 | 枚举存 `ordinal()` | 新增枚举值后数据错乱 | 存显式 `code` |
| 13 | Stream 复用 | 第二次消费抛 `IllegalStateException` | 每次从集合重新 `.stream()` |
| 14 | `Stream.toList()` 后修改 | 抛 `UnsupportedOperationException` | 需要可变时 `collect(Collectors.toCollection(ArrayList::new))` |
| 15 | `Optional.get()` 不判空 | `NoSuchElementException` | `orElseThrow(() -> new BizException(...))` |
| 16 | `String.split` 当普通字符串 | `"a.b".split(".")` 返回空数组 | `split("\\.")` 或 `Pattern.quote(".")` |
| 17 | 在 `finally` 里 `return` | 覆盖 try 的返回值并吞掉异常 | finally 只做清理 |

---

## 7. 高级视角

### 7.1 不可变优先

高级工程师默认让对象不可变：`final` 字段、无 setter、record、`List.copyOf`。收益是线程安全（04 章）、可安全作为 Map key、推理简单。PO 由于框架需要 setter 是例外，但**值对象、DTO、配置对象、缓存对象**应尽量不可变。

### 7.2 领域规则内聚

`OrderStatusEnum.canTransitTo` 体现了「把规则放在数据旁边」：状态机规则写在枚举里，而不是在 5 个 Service 里各写一遍 `if (status == 0 || status == 1)`。这是从「事务脚本」走向「富领域模型」（13 章 DDD）的第一步，也是五层架构中「下层稳定、上层易变」的体现。

### 7.3 异常设计的边界

| 层 | 处理方式 |
|---|---|
| ④ DAO / Client | 捕获三方/IO 受检异常，包装为非受检异常（保留 cause），不吞掉 |
| ②③ 编排 / 功能单元 | 业务规则不满足抛 `BizException`；不 catch 自己处理不了的异常 |
| ① Controller | 不写 try/catch，交给全局异常处理器 |
| 全局处理器 | `BizException` → `Result(code, msg)`，记 warn；未知异常 → `SYSTEM_ERROR`，记 error + 堆栈 |

原则：**异常要么处理，要么向上抛，不要两样都做**（记日志后再抛，会导致同一异常被打印多次）。

### 7.4 Java 8 存量项目的迁移视角

你多半会接手 Java 8 项目。需要知道：没有 `var`/record/`toList()`/文本块/switch 表达式；`List.of` 用 `Collections.unmodifiableList(Arrays.asList(..))` 替代；Spring Boot 2.x 最高支持到 Java 17 左右，Spring Boot 3 要求 Java 17+ 且 `javax.*` 包名全部改为 `jakarta.*`——这是升级的主要工作量来源。

### 7.5 读懂字节码与 JDK 源码

遇到「为什么」类问题，直接看证据：`javap -c -v` 看字节码（如验证装箱、字符串拼接、Lambda 的 invokedynamic）；IDE 中 Ctrl/Cmd+点击进入 JDK 源码（如 `Integer.valueOf`、`String.hashCode`）。这是从「会用」到「懂原理」的关键习惯。

---

## 8. 小练习

1. **装箱实验**：写一段代码比较 `Long a = 127L, b = 127L` 与 `Long c = 128L, d = 128L` 的 `==` 结果，再用 `javap -c` 找出编译器插入的 `Long.valueOf` 调用。
2. **金额计算**：用 `double` 和 `BigDecimal` 分别计算 `19.9 × 3 - 0.7`，对比结果；再计算「100 元三人均摊，保留两位小数，最后一人兜底差额」。
3. **枚举状态机**：给 `OrderStatusEnum` 增加 `REFUNDED(5, "已退款")`，只允许 `PAID → REFUNDED`。用 switch 表达式实现后，观察如果漏写 `REFUNDED` 分支编译器给出什么错误。
4. **equals/hashCode**：定义一个只覆写 `equals` 的 `SkuKey` 类，放两个「相等」的对象进 `HashSet`，打印 `size()`；再改为 record 对比。
5. **PECS**：实现 `static void addAllOrders(List<? super OrderPO> target, List<? extends OrderPO> source)`，思考为什么两个参数的通配符方向相反。
6. **Stream 改写**：把下面的 TS 改写为 Java Stream：`orders.filter(o => o.status === 1).map(o => o.orderNo).slice(0, 10)`。
7. **sealed + 模式匹配**：用 sealed interface 定义 `DiscountRule`（满减 `FullReduce(threshold, minus)`、折扣 `Percent(rate)`），写一个 `apply(rule, amount)` 方法用 switch 模式匹配计算优惠后金额。
