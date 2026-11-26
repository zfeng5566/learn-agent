# 02 集合框架与常用 API

> [← 总纲](./00-outline.md) | 上一章：[← 01 Java 语言基础](./01-java-basics.md) | 下一章：[03 JVM 原理 →](./03-jvm.md)

---

## 1. 本章地图

**本章解决的问题**：业务代码里 80% 的数据处理都是「拿到一批对象 → 分组、去重、排序、查找 → 转成 JSON 返回」。前端用 `Array/Map/Set` + lodash + dayjs + `JSON` 搞定；Java 对应的是集合框架 + Stream + `java.time` + Jackson。

```
全景图中的位置：
Controller ── JSON ⇄ 对象（Jackson）
   │
编排层 / 功能单元 ── List/Map/Set 组装数据、Stream 分组统计、java.time 处理时间
   │
DAO ── 查询结果 List<OrderPO>
```

| 主题 | 你需要带走的结论 |
|---|---|
| 集合选型 | 按「有序？可重复？要排序？线程安全？」四个问题选实现 |
| HashMap 原理 | 数组 + 链表/红黑树，`(n-1) & hash` 定位，0.75 负载因子扩容，线程不安全 |
| 迭代 | 遍历时修改集合会 fail-fast，用 `removeIf` / `Iterator.remove` |
| Stream 进阶 | `groupingBy` / `partitioningBy` / `toMap`（键重复会抛异常） |
| 时间 | 一律用 `java.time`，不用 `Date` / `SimpleDateFormat` |
| JSON | Jackson `ObjectMapper` 单例复用；`Long` 传给前端要防精度丢失 |

mini-mall 本章产出：

| 类 | 包 | 作用 |
|---|---|---|
| `ProductPO` | `model.po` | 商品表 `t_product` 实体 |
| `OrderStatUtil` | `util` | 订单按用户 / 状态分组统计 |
| `LruCache<K, V>` | `util` | 基于 LinkedHashMap 的 LRU 缓存，用于本地商品缓存 |
| `OrderTimeUtil` | `util` | 订单时间处理：支付超时判断、按天查询区间、格式化 |
| `JsonUtil` | `util` | 全局共享的 ObjectMapper 封装 |

---

## 2. 前端类比

| 前端 | Java | 差异要点 |
|---|---|---|
| `Array` | `ArrayList`（日常）、`int[]`（定长数组） | Java 数组长度固定；`List` 只能装对象（`Integer` 非 `int`） |
| `Map` | `HashMap`（无序）/ `LinkedHashMap`（插入序）/ `TreeMap`（按 key 排序） | JS `Map` 保持插入顺序，等价于 `LinkedHashMap` |
| 对象当字典 `{[id]: order}` | `Map<Long, OrderPO>` | Java 的 key 可以是任意类型，判等靠 `equals/hashCode` |
| `Set` | `HashSet` / `LinkedHashSet` / `TreeSet` | JS `Set` 对对象按引用判重，Java 按 `equals` |
| lodash `groupBy` / `keyBy` / `partition` | `Collectors.groupingBy` / `toMap` / `partitioningBy` | 标准库自带 |
| `arr.sort((a, b) => a - b)` | `list.sort(Comparator.comparing(..))` | Comparator 可链式组合 |
| `Object.freeze` | `List.of` / `List.copyOf` | 修改时直接抛异常，而不是静默失败 |
| dayjs | `java.time` | 不可变、线程安全，API 设计与 dayjs 类似 |
| `JSON.stringify/parse` | Jackson `ObjectMapper` | 必须指定目标类型 |
| `fs.readFile` / stream | `Files` / `InputStream` / NIO | 资源用完必须关闭 |

---

## 3. 核心概念

### 3.1 集合体系全景图

```
                          Iterable<E>
                              │
                        Collection<E>
          ┌───────────────────┼─────────────────────┐
        List<E>             Set<E>               Queue<E>
     有序、可重复         不可重复              队列语义
     ├ ArrayList          ├ HashSet             ├ PriorityQueue（堆）
     ├ LinkedList ────────┼───────────────────── ┤ Deque<E> 双端队列
     └ CopyOnWriteArrayList│  └ LinkedHashSet    │  ├ ArrayDeque（首选栈/队列）
       (并发，04章)        └ SortedSet           │  └ LinkedList
                              └ TreeSet         └ BlockingQueue（并发，04章）

                            Map<K,V>（不继承 Collection）
                 ├ HashMap ── LinkedHashMap
                 ├ TreeMap（SortedMap/NavigableMap，红黑树）
                 ├ ConcurrentHashMap（并发，04章）
                 └ EnumMap / IdentityHashMap / WeakHashMap（特殊用途）
```

**选型决策流程**：

```
需要 key → value 映射？
├─ 是 → 需要按 key 排序/范围查询？ ─是→ TreeMap
│        └─ 否 → 需要保持插入/访问顺序？ ─是→ LinkedHashMap
│                 └─ 否 → 多线程共享？ ─是→ ConcurrentHashMap ─否→ HashMap
└─ 否 → 需要去重？
         ├─ 是 → 需要排序？ ─是→ TreeSet  ─否→ 保序？ ─是→ LinkedHashSet ─否→ HashSet
         └─ 否 → 队列/栈语义？ ─是→ ArrayDeque（优先级 → PriorityQueue）
                  └─ 否 → ArrayList
```

> 声明时面向接口：`List<OrderPO> list = new ArrayList<>();`，而不是 `ArrayList<OrderPO> list`。方法参数和返回值同理，方便替换实现。

### 3.2 List：ArrayList vs LinkedList

```ts
const ids: number[] = [];
ids.push(1); ids[0]; ids.length; ids.splice(0, 1);
```

```java
List<Long> ids = new ArrayList<>();
ids.add(1L);          // push
ids.get(0);           // ids[0]，越界抛 IndexOutOfBoundsException（JS 返回 undefined）
ids.size();           // length
ids.remove(0);        // 按下标删除 —— 注意：List<Integer> 的 remove(1) 是删下标 1，不是删值 1
ids.remove(Long.valueOf(1L)); // 按值删除
ids.contains(1L);     // includes，O(n)
```

| 对比 | ArrayList | LinkedList |
|---|---|---|
| 底层 | `Object[]` 动态数组 | 双向链表 |
| 随机访问 `get(i)` | O(1) | O(n) |
| 尾部追加 | 均摊 O(1) | O(1) |
| 中间插入/删除 | O(n)（`System.arraycopy` 搬移） | 定位 O(n) + 改指针 O(1) |
| 内存 | 紧凑，CPU 缓存友好 | 每个节点额外两个指针 + 对象头 |
| 结论 | **99% 场景用它** | 几乎不用；要队列/栈用 `ArrayDeque` |

ArrayList 扩容：默认首次 `add` 时容量 10，满了扩到 **1.5 倍**（`old + (old >> 1)`），复制旧数组。已知数据量时 `new ArrayList<>(n)` 预分配。

> LinkedList「插入快」是理论值：真实场景要先 O(n) 遍历找到位置，加上缓存不友好，实测大多比 ArrayList 慢。

### 3.3 Map 基本用法

```ts
const m = new Map<number, Order>();
m.set(1, o); m.get(1); m.has(1); m.delete(1);
for (const [k, v] of m) {}
const cnt = m.get(k) ?? 0; m.set(k, cnt + 1);
```

```java
Map<Long, OrderPO> m = new HashMap<>();
m.put(1L, o);
m.get(1L);                 // 不存在返回 null
m.containsKey(1L);
m.remove(1L);
for (Map.Entry<Long, OrderPO> e : m.entrySet()) { e.getKey(); e.getValue(); }

// Java 8+ 的高频便捷方法
m.getOrDefault(2L, null);
m.putIfAbsent(2L, o);
Map<Long, Integer> counter = new HashMap<>();
counter.merge(userId, 1, Integer::sum);                       // 计数：不存在放 1，存在则相加
Map<Long, List<OrderPO>> group = new HashMap<>();
group.computeIfAbsent(userId, k -> new ArrayList<>()).add(o); // 分组：没有列表就先建
```

### 3.4 HashMap 的使用要点（原理见第 4 节）

- key 必须正确实现 `equals` + `hashCode`（01 章 3.17）；**放入后不要修改 key 中参与 hash 的字段**。
- 允许一个 `null` key 和多个 `null` value；`ConcurrentHashMap` 两者都不允许。
- 遍历顺序**不保证**，也不保证稳定（扩容后会变）。需要顺序用 `LinkedHashMap`。
- 已知大小时预设容量，避免反复扩容：

```java
// 预计放 1000 个元素：容量需 ≥ 1000 / 0.75 ≈ 1334，HashMap 会向上取到 2048
Map<Long, OrderPO> map = new HashMap<>((int) (1000 / 0.75f) + 1);
// Java 19+ 直接用工厂方法，内部替你算
Map<Long, OrderPO> map2 = HashMap.newHashMap(1000);
```

### 3.5 LinkedHashMap 与 TreeMap

**LinkedHashMap** = HashMap + 一条贯穿所有节点的双向链表，用来维护顺序。

```
HashMap 桶数组：[0]→A   [1]   [2]→C→D   [3]→B
双向链表：      head ⇄ A ⇄ B ⇄ C ⇄ D ⇄ tail   （插入序，或 accessOrder=true 时的访问序）
```

| 构造参数 | 顺序 | 用途 |
|---|---|---|
| `new LinkedHashMap<>()` | 插入顺序 | 保持查询结果顺序的 Map（如 `groupingBy` 后按原顺序输出） |
| `new LinkedHashMap<>(16, 0.75f, true)` | 访问顺序（`get` 会把节点移到尾部） | **LRU 缓存** |

配合覆写 `removeEldestEntry`，每次 `put` 后若返回 true 就删除链表头（最久未访问）——10 行代码实现 LRU，见 mini-mall 实战。

**TreeMap**：红黑树实现，key 有序，所有操作 O(log n)，支持范围查询。

```java
TreeMap<BigDecimal, String> levels = new TreeMap<>();
levels.put(new BigDecimal("0"), "普通");
levels.put(new BigDecimal("1000"), "白银");
levels.put(new BigDecimal("5000"), "黄金");
// floorEntry：≤ 给定 key 的最大项，适合「区间 → 等级」映射
String level = levels.floorEntry(new BigDecimal("3200")).getValue(); // 白银
levels.headMap(new BigDecimal("1000"));    // key < 1000 的视图
levels.firstKey(); levels.lastKey();
```

> TreeMap 用 `compareTo`/`Comparator` 判断 key 是否相同，**不调用 equals**。所以 `new BigDecimal("1.0")` 和 `"1.00"` 在 TreeMap 中是同一个 key，在 HashMap 中是两个 key。

### 3.6 Set

| 实现 | 底层 | 顺序 | 复杂度 |
|---|---|---|---|
| `HashSet` | 内部就是一个 `HashMap`，元素作 key，value 为固定占位对象 `PRESENT` | 无序 | O(1) |
| `LinkedHashSet` | `LinkedHashMap` | 插入序 | O(1) |
| `TreeSet` | `TreeMap` | 排序 | O(log n) |

```java
Set<Long> userIds = new HashSet<>();
boolean added = userIds.add(1L);   // 已存在返回 false，可直接用于「首次出现」判断
// 交集 / 并集 / 差集（会修改调用方，必要时先复制）
Set<Long> a = new HashSet<>(List.of(1L, 2L, 3L));
a.retainAll(Set.of(2L, 3L, 4L));   // 交集 → [2, 3]
a.addAll(Set.of(9L));              // 并集
a.removeAll(Set.of(2L));           // 差集
```

### 3.7 Queue、Deque、PriorityQueue

```ts
const stack = []; stack.push(1); stack.pop();
const queue = []; queue.push(1); queue.shift();   // shift 是 O(n)
```

```java
Deque<Long> stack = new ArrayDeque<>();
stack.push(1L);  stack.pop();  stack.peek();      // 栈：头部进出
Deque<Long> queue = new ArrayDeque<>();
queue.offer(1L); queue.poll(); queue.peek();      // 队列：尾进头出，O(1)
```

Queue 的方法成对出现，区别在失败时的行为：

| 操作 | 抛异常 | 返回特殊值 |
|---|---|---|
| 插入 | `add(e)` | `offer(e)` → false |
| 删除头 | `remove()` | `poll()` → null |
| 查看头 | `element()` | `peek()` → null |

> 不要用 `Stack` 类（继承自 `Vector`，全方法加锁，历史遗留）；`ArrayDeque` 不允许 `null` 元素。

**PriorityQueue**：二叉小顶堆，`offer/poll` O(log n)，`peek` O(1)。

```java
// 取金额最大的 Top 3 订单：维护一个容量为 3 的小顶堆，堆顶是当前第 3 大
PriorityQueue<OrderPO> heap = new PriorityQueue<>(Comparator.comparing(OrderPO::getTotalAmount));
for (OrderPO o : orders) {
    heap.offer(o);
    if (heap.size() > 3) {
        heap.poll();     // 弹出最小的，保留较大的 3 个
    }
}
// 注意：遍历 PriorityQueue 的顺序不是有序的，只有 poll 出来是有序的
```

### 3.8 迭代与 fail-fast

```ts
const arr = [1, 2, 3];
for (const x of arr) { if (x === 2) arr.splice(arr.indexOf(x), 1); } // JS 不报错，但会跳过元素
```

```java
List<Integer> list = new ArrayList<>(List.of(1, 2, 3, 4));
for (Integer x : list) {
    if (x == 2) list.remove(x);   // 抛 ConcurrentModificationException
}
```

正确写法：

```java
list.removeIf(x -> x == 2);                     // 首选，Java 8+

Iterator<Integer> it = list.iterator();          // 需要复杂逻辑时用迭代器自己的 remove
while (it.hasNext()) {
    if (it.next() == 2) {
        it.remove();
    }
}

List<Integer> kept = list.stream().filter(x -> x != 2).toList(); // 不修改原集合，生成新集合
```

Map 同理：`map.entrySet().removeIf(e -> e.getValue() == null);`。

### 3.9 Collections / Arrays 工具类与不可变集合

| 工具方法 | 作用 | 前端类比 |
|---|---|---|
| `Collections.sort(list)` / `list.sort(cmp)` | 原地排序（稳定的 TimSort） | `arr.sort` |
| `Collections.reverse` / `shuffle` | 反转 / 打乱 | `reverse` / lodash `shuffle` |
| `Collections.max(coll, cmp)` | 最大值 | lodash `maxBy` |
| `Collections.emptyList()` | 共享的空不可变列表 | `[]`（返回值避免 null） |
| `Collections.unmodifiableList(list)` | 只读**视图**（原列表改了它也变） | — |
| `Arrays.asList(a, b)` | 数组包装成**定长** List | — |
| `Arrays.sort(arr)` / `Arrays.toString(arr)` | 数组排序 / 打印 | — |
| `List.of(..)` / `Set.of` / `Map.of` | 真正不可变集合（Java 9+） | `Object.freeze` |
| `List.copyOf(coll)` | 不可变副本（Java 10+） | `Object.freeze([...arr])` |

三种「不可变」的区别：

| | `Arrays.asList` | `Collections.unmodifiableList` | `List.of` / `copyOf` |
|---|---|---|---|
| `add/remove` | ✗ 抛异常 | ✗ | ✗ |
| `set(i, x)` | ✓ 可以（写回原数组） | ✗ | ✗ |
| 原数据变化是否可见 | 是（共享数组） | 是（视图） | 否（独立副本） |
| 允许 `null` | 是 | 是 | **否**，`List.of(null)` 直接 NPE |

### 3.10 Comparable 与 Comparator

```ts
orders.sort((a, b) => b.totalAmount - a.totalAmount || a.createTime - b.createTime);
```

```java
// Comparator 链式组合：按金额降序，金额相同按创建时间升序，status 为 null 的排最后
orders.sort(Comparator.comparing(OrderPO::getTotalAmount).reversed()
        .thenComparing(OrderPO::getCreateTime)
        .thenComparing(OrderPO::getStatus, Comparator.nullsLast(Comparator.naturalOrder())));
```

| | `Comparable<T>` | `Comparator<T>` |
|---|---|---|
| 位置 | 类自己实现 `compareTo` | 外部定义比较器 |
| 含义 | 「自然顺序」，只有一种 | 可以定义任意多种 |
| 典型 | `String`、`Integer`、`BigDecimal`、`LocalDateTime` | 业务排序规则 |

```java
/**
 * 版本号：自然顺序为数值升序。
 *
 * @param major 主版本
 * @param minor 次版本
 */
public record Version(int major, int minor) implements Comparable<Version> {

    /**
     * 先比主版本，再比次版本。
     *
     * @param o 另一个版本
     * @return 负数表示小于，0 表示相等，正数表示大于
     */
    @Override
    public int compareTo(Version o) {
        // 不要写 this.major - o.major：大数相减可能溢出，用 Integer.compare
        int c = Integer.compare(major, o.major);
        return c != 0 ? c : Integer.compare(minor, o.minor);
    }
}
```

> 注意 `Comparator.comparing(A::getX).reversed()` 是把**整个链**反转。写 `comparing(a).thenComparing(b).reversed()` 会让 a、b 都降序。只想让某一段降序，用 `thenComparing(b, Comparator.reverseOrder())`。

### 3.11 Stream 进阶：Collectors

01 章讲了 `map/filter/reduce`。业务代码最常用的其实是 `collect` 的各种收集器：

| lodash / 手写 | Java Collectors | 结果类型 |
|---|---|---|
| `_.groupBy(orders, 'userId')` | `groupingBy(OrderPO::getUserId)` | `Map<Long, List<OrderPO>>` |
| `_.countBy(orders, 'status')` | `groupingBy(OrderPO::getStatus, counting())` | `Map<Integer, Long>` |
| `_.keyBy(orders, 'orderNo')` | `toMap(OrderPO::getOrderNo, Function.identity())` | `Map<String, OrderPO>` |
| `_.partition(orders, isPaid)` | `partitioningBy(isPaid)` | `Map<Boolean, List<OrderPO>>` |
| `arr.map(..).join(',')` | `map(..).collect(joining(","))` | `String` |
| `_.sumBy` | `summingInt` / `reducing(BigDecimal.ZERO, .., BigDecimal::add)` | 数值 |
| `_.uniq` 后转 Set | `toSet()` / `toCollection(TreeSet::new)` | `Set` |

`groupingBy` 的三个重载：

```java
// 1. 只分组
Map<Long, List<OrderPO>> byUser = orders.stream()
        .collect(Collectors.groupingBy(OrderPO::getUserId));

// 2. 分组 + 下游收集器：每个状态的订单数
Map<Integer, Long> countByStatus = orders.stream()
        .collect(Collectors.groupingBy(OrderPO::getStatus, Collectors.counting()));

// 3. 指定 Map 实现 + 下游：按用户分组，只取订单号，结果按 userId 排序
Map<Long, List<String>> orderNosByUser = orders.stream()
        .collect(Collectors.groupingBy(OrderPO::getUserId, TreeMap::new,
                Collectors.mapping(OrderPO::getOrderNo, Collectors.toList())));
```

**`partitioningBy`**：按布尔条件一分为二，结果 Map **总是**同时包含 `true` 和 `false` 两个 key（哪怕某边为空列表），这点与 `groupingBy` 不同。

**`toMap` 的两个坑**（线上高频）：

```java
// 坑 1：key 重复直接抛 IllegalStateException: Duplicate key
Map<Long, OrderPO> byUser = orders.stream()
        .collect(Collectors.toMap(OrderPO::getUserId, Function.identity())); // 同一用户多单 → 炸

// 正确：提供合并函数，明确冲突时保留谁
Map<Long, OrderPO> latestByUser = orders.stream()
        .collect(Collectors.toMap(OrderPO::getUserId, Function.identity(),
                (a, b) -> a.getCreateTime().isAfter(b.getCreateTime()) ? a : b));

// 坑 2：value 为 null 直接 NPE（内部用的 HashMap.merge 不接受 null value）
Map<String, Integer> statusByNo = orders.stream()
        .collect(Collectors.toMap(OrderPO::getOrderNo, OrderPO::getStatus)); // status 为 null → NPE
// 解决：先 filter 掉 null，或改用普通 for 循环 put
```

**flatMap**：一对多展开。

```ts
const allItems = orders.flatMap(o => o.items);
```

```java
// 订单详情列表 → 所有明细的商品 id（去重）
Set<Long> productIds = orderDetails.stream()
        .flatMap(d -> d.items().stream())       // 每个订单的明细流拼接成一个流
        .map(OrderItemPO::getProductId)
        .collect(Collectors.toSet());
```

**并行流**：`list.parallelStream()` 把任务拆给 `ForkJoinPool.commonPool()`（线程数 = CPU 核数 - 1）。

| 注意点 | 说明 |
|---|---|
| 共享线程池 | 整个 JVM 共用一个 commonPool，一个慢任务（尤其是 IO）会拖垮所有并行流 |
| 线程安全 | 在 `forEach` 里往外部 `ArrayList` 加元素会丢数据 / 越界，必须用 `collect` |
| 收益门槛 | 数据量小（< 万级）或任务轻时，拆分合并开销大于收益 |
| 顺序 | `forEach` 无序；需要顺序用 `forEachOrdered`（失去大部分并行收益） |
| 结论 | **Web 服务里基本不用**，请求本身已经是多线程并发；并行 IO 用自定义线程池 + CompletableFuture（04 章） |

### 3.12 java.time：现代时间 API

```ts
dayjs().add(30, 'minute').format('YYYY-MM-DD HH:mm:ss');
dayjs('2026-11-26').startOf('day');
dayjs(b).diff(a, 'minute');
```

```java
LocalDateTime.now().plusMinutes(30).format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
LocalDate.parse("2026-11-26").atStartOfDay();
Duration.between(a, b).toMinutes();
```

| 类 | 含义 | 例子 | 使用场景 |
|---|---|---|---|
| `LocalDate` | 日期，无时区 | `2026-11-26` | 生日、账单日、按天统计 |
| `LocalTime` | 时间，无时区 | `10:30:00` | 营业时间 |
| `LocalDateTime` | 日期 + 时间，无时区 | `2026-11-26T10:30` | **业务表的 create_time**（MySQL DATETIME） |
| `Instant` | 时间线上的绝对时刻（UTC 纪元毫秒/纳秒） | `2026-11-26T02:30:00Z` | 日志、跨时区系统、≈ `Date.now()` |
| `ZonedDateTime` | 带时区的日期时间 | `...T10:30+08:00[Asia/Shanghai]` | 跨时区展示、夏令时计算 |
| `Duration` | 基于秒/纳秒的时长 | `PT30M` | 超时、耗时 |
| `Period` | 基于年月日的时长 | `P1M` | 「一个月后」到期 |
| `DateTimeFormatter` | 格式化/解析，**线程安全** | `ofPattern("yyyy-MM-dd")` | 定义为常量复用 |

dayjs 对照：

| dayjs | java.time |
|---|---|
| `dayjs()` | `LocalDateTime.now()` |
| `.add(1, 'day')` | `.plusDays(1)` |
| `.subtract(1, 'month')` | `.minusMonths(1)` |
| `.startOf('day')` | `date.atStartOfDay()` / `dt.toLocalDate().atStartOfDay()` |
| `.startOf('month')` | `date.withDayOfMonth(1)` / `date.with(TemporalAdjusters.firstDayOfMonth())` |
| `.isBefore(b)` / `.isAfter(b)` | `isBefore` / `isAfter`（相等用 `isEqual` 或 `equals`） |
| `.diff(a, 'day')` | `ChronoUnit.DAYS.between(a, b)` |
| `.format('YYYY-MM-DD')` | `.format(DateTimeFormatter.ofPattern("yyyy-MM-dd"))` |
| `.valueOf()` | `instant.toEpochMilli()` |
| `dayjs(ms)` | `Instant.ofEpochMilli(ms).atZone(ZoneId.of("Asia/Shanghai")).toLocalDateTime()` |

转换关系：

```
               atZone(zone)                   toInstant()
LocalDateTime ─────────────▶ ZonedDateTime ─────────────▶ Instant
              ◀───────────── toLocalDateTime()  ◀───────── atZone(zone)
LocalDate ── atStartOfDay() / atTime(LocalTime) ──▶ LocalDateTime
```

**格式化模式字母区分大小写**（与 dayjs 不同！）：`yyyy` 年、`MM` 月、`dd` 日、`HH` 24 小时、`mm` 分、`ss` 秒。`YYYY` 是「周年份」（week-based year），在跨年那一周会出错；`DD` 是「一年中的第几天」。

**为什么不用 `Date` / `SimpleDateFormat`**：

| 问题 | 旧 API | java.time |
|---|---|---|
| 可变性 | `Date.setTime()` 可变，传出去会被改 | 全部不可变，`plusDays` 返回新对象 |
| 线程安全 | `SimpleDateFormat` 内部共享一个 `Calendar` 字段，多线程 `parse/format` 互相覆盖，产生错误日期甚至异常 | `DateTimeFormatter` 不可变，可做全局常量 |
| 语义 | `Date` 名字叫日期，实际是时间戳；月份从 0 开始；年份从 1900 起算 | 类型各司其职，月份 1~12 |
| 时区 | 隐式使用 JVM 默认时区 | 显式 `ZoneId` |

> JS 的 `Date` 有同样的设计问题（可变、月份从 0 开始），这也是 dayjs/Temporal 出现的原因。

### 3.13 IO 与 NIO 入门

服务端日常 IO 主要是：读配置/模板文件、导出 CSV/Excel、上传下载。网络 IO 已被框架（Tomcat/Netty）封装。

```ts
import { readFile, writeFile } from 'node:fs/promises';
const text = await readFile('a.txt', 'utf8');
await writeFile('b.txt', text);
```

```java
// java.nio.file.Files：一行搞定的常用操作（Java 11+）
Path path = Path.of("a.txt");
String text = Files.readString(path);                       // 默认 UTF-8
List<String> lines = Files.readAllLines(path);
Files.writeString(Path.of("b.txt"), text);

// 大文件逐行处理：Files.lines 返回的 Stream 持有文件句柄，必须关闭
try (Stream<String> s = Files.lines(path)) {
    long count = s.filter(line -> line.contains("ERROR")).count();
}
```

**IO 类体系**：

| 维度 | 字节流（二进制） | 字符流（文本，需指定编码） |
|---|---|---|
| 输入 | `InputStream` → `FileInputStream`、`BufferedInputStream` | `Reader` → `InputStreamReader`、`BufferedReader` |
| 输出 | `OutputStream` → `FileOutputStream`、`BufferedOutputStream` | `Writer` → `OutputStreamWriter`、`BufferedWriter` |

设计上用了**装饰器模式**：`new BufferedReader(new InputStreamReader(new FileInputStream(f), UTF_8))`，每层增加一种能力（缓冲、字节转字符）。

**BIO / NIO / AIO**：

| 模型 | 核心 | 线程模型 | 代表 |
|---|---|---|---|
| BIO（阻塞 IO） | `InputStream.read()` 阻塞到有数据 | 一连接一线程 | 传统 Tomcat BIO（已淘汰） |
| NIO（非阻塞 + 多路复用） | `Channel` + `Buffer` + `Selector` | 少量线程轮询大量连接 | Netty、Tomcat NIO、Redis 客户端 Lettuce |
| AIO（异步 IO） | 回调通知 | 操作系统完成后回调 | Linux 上支持一般，少用 |

```
NIO 多路复用：
 连接1 ─┐
 连接2 ─┼──▶ Selector（epoll）──▶ 1 个线程：哪个连接就绪就处理哪个
 连接3 ─┘
```

这与 Node.js 的事件循环（libuv 封装 epoll）是同一底层机制。区别在于 Node 只有一个 JS 线程处理回调，Netty 用一组 EventLoop 线程。Java 21 的虚拟线程则让你用 BIO 的同步写法获得接近 NIO 的吞吐（04 章）。

### 3.14 Jackson：JSON 序列化

```ts
const json = JSON.stringify(order);
const o = JSON.parse(json) as Order;          // as 只是骗编译器，运行时无校验
```

```java
ObjectMapper mapper = new ObjectMapper();               // 线程安全，全局复用一个
String json = mapper.writeValueAsString(order);          // stringify
OrderVO vo = mapper.readValue(json, OrderVO.class);      // parse，真实按类结构绑定
// 泛型类型：由于类型擦除，List<OrderVO>.class 写不出来，用 TypeReference 保留泛型信息
List<OrderVO> list = mapper.readValue(json, new TypeReference<List<OrderVO>>() { });
// 不确定结构时用树模型（≈ 操作 any）
JsonNode node = mapper.readTree(json);
String orderNo = node.path("orderNo").asText();
```

常用注解：

| 注解 | 作用 | 前端类比 |
|---|---|---|
| `@JsonProperty("order_no")` | 指定 JSON 字段名 | 手写字段映射 |
| `@JsonIgnore` | 不序列化（如密码） | `delete obj.password` |
| `@JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "GMT+8")` | 时间格式 | dayjs format |
| `@JsonInclude(JsonInclude.Include.NON_NULL)` | null 字段不输出 | `JSON.stringify` 自动跳过 `undefined` |
| `@JsonSerialize(using = ToStringSerializer.class)` | 按字符串输出（Long 防精度丢失） | — |

常用配置：

| 配置 | 默认 | 建议 | 原因 |
|---|---|---|---|
| `FAIL_ON_UNKNOWN_PROPERTIES` | true | **false** | 对方多加一个字段你就反序列化失败，不利于兼容（Spring Boot 默认已关） |
| `WRITE_DATES_AS_TIMESTAMPS` | true | false | 否则 `LocalDateTime` 输出成数组 `[2026,11,26,10,30]` |
| 注册 `JavaTimeModule` | 未注册 | 注册 | 否则无法序列化 `java.time` 类型（Spring Boot 自动注册） |

> **前端必知：Long 精度丢失**。JS `Number.MAX_SAFE_INTEGER` = 2⁵³-1 ≈ 9×10¹⁵，而雪花算法 ID（11 章）是 19 位的 `Long`。后端原样输出数字，前端 `JSON.parse` 后末几位变成 0。解决：后端把 `Long` 序列化成字符串（全局配置 `ToStringSerializer`，或字段加 `@JsonSerialize`）。这是前后端联调最经典的 bug 之一，你在前端时可能就踩过。

---

## 4. 原理深挖

### 4.1 HashMap 的结构（JDK 8）

```
table: Node<K,V>[]，长度永远是 2 的幂（默认 16）

 index  0     1      2       3      ...    15
      ┌────┬──────┬──────┬───────┬─────┬──────┐
      │null│ Node │ null │ Tree  │ ... │ Node │
      └────┴──┬───┴──────┴───┬───┴─────┴──┬───┘
              ▼              ▼            ▼
            Node           TreeNode      Node
              ▼            /     \        ▼
            Node      TreeNode TreeNode  null
              ▼
            null
   链表（冲突 < 8）      红黑树（冲突 ≥ 8 且 table ≥ 64）

Node { final int hash; final K key; V value; Node<K,V> next; }
```

### 4.2 put 流程

```
put(key, value)
  │
  ├─ ① hash = (h = key.hashCode()) ^ (h >>> 16)     扰动函数；null key 的 hash 为 0
  ├─ ② table 为空？ → resize() 初始化（懒加载，new 时不分配数组）
  ├─ ③ index = (n - 1) & hash                       等价于 hash % n，但更快
  ├─ ④ 桶为空？ → 直接放新 Node
  ├─ ⑤ 桶不为空：
  │     ├─ 首节点 key 相同（hash 相等 且 (== 或 equals)）→ 覆盖 value
  │     ├─ 是 TreeNode → 红黑树插入 putTreeVal
  │     └─ 是链表 → 遍历；找到相同 key 则覆盖，否则**尾插**
  │              └─ 插入后链表长度 ≥ 8 → treeifyBin
  │                     ├─ table 长度 < 64 → 优先 resize 扩容（冲突多半因为数组太小）
  │                     └─ 否则 → 链表转红黑树
  ├─ ⑥ ++modCount（供 fail-fast 用）
  └─ ⑦ ++size > threshold（容量 × 0.75）？ → resize() 扩容为 2 倍
```

**为什么长度必须是 2 的幂**：
1. `(n-1) & hash` 只有在 n 为 2 的幂时才等价于取模（n-1 的二进制全是 1）。位运算比除法快得多。
2. 扩容时可以巧妙地拆分链表（见 4.3）。
3. 你传入 `new HashMap<>(10)`，内部 `tableSizeFor` 会向上取到 16。

**为什么要扰动 `h ^ (h >>> 16)`**：table 较小时，`(n-1) & hash` 只用到 hash 的低几位。如果一批 key 的 hashCode 只在高位不同（例如某些对象地址、浮点数），会全部挤进同一个桶。把高 16 位异或到低 16 位，让高位也参与定位，代价只有一次位运算。

**为什么树化阈值是 8**：源码注释给出了依据——在 hashCode 分布良好时，桶中节点数服从泊松分布（λ≈0.5），一个桶出现 8 个节点的概率约千万分之六。正常情况下几乎不会树化；树化是**应对极差 hashCode 或哈希碰撞攻击**的兜底，把最坏情况从 O(n) 降到 O(log n)。退化回链表的阈值是 6，中间留出间隔防止在 7、8 之间反复转换。

**为什么负载因子是 0.75**：时间与空间的折中。负载因子越大越省内存但冲突越多；越小冲突越少但浪费空间、扩容更频繁。0.75 下配合泊松分布，链表平均长度很短。

### 4.3 resize 扩容

```
旧 table 长度 16 → 新 table 长度 32
对旧桶中的每个节点，看 hash & oldCap（即 hash 的第 5 位，16 = 0b10000）：
   = 0 → 留在原下标 j          （lo 链表）
   ≠ 0 → 移到下标 j + oldCap   （hi 链表）

例：hash = 0b1_0101 (21)，旧下标 21 & 15 = 5；21 & 16 ≠ 0 → 新下标 5 + 16 = 21 ✓
    hash = 0b0_0101 (5)， 旧下标 5；        5 & 16 = 0  → 新下标仍为 5      ✓
```

不需要对每个节点重新计算 hash 和取模，且 JDK 8 保持 lo/hi 链表中节点的**相对顺序**不变。

### 4.4 JDK 7 与 JDK 8 的差异

| 对比 | JDK 7 | JDK 8 |
|---|---|---|
| 结构 | 数组 + 链表 | 数组 + 链表 + 红黑树 |
| 插入方式 | **头插法** | **尾插法** |
| 扰动函数 | 4 次位移 + 5 次异或 | 1 次位移 + 1 次异或 |
| 扩容 | 每个节点重新计算下标，链表顺序反转 | lo/hi 拆分，保持顺序 |
| 并发扩容 | 可能形成**环形链表**，`get` 死循环 CPU 100% | 不会成环，但仍会丢数据 |
| 节点类 | `Entry` | `Node` / `TreeNode` |

**JDK 7 死循环成因简述**：两个线程同时扩容，线程 A 读到 `e = 1, next = 2` 后挂起；线程 B 完成扩容，头插法让新链表变成 `2 → 1`；线程 A 恢复后继续按旧的 next 关系头插，最终造成 `1 → 2 → 1` 的环。之后任何 `get` 落到这个桶都会无限循环。

### 4.5 HashMap 为什么线程不安全

即使在 JDK 8 中，并发写仍有以下问题：

| 问题 | 场景 |
|---|---|
| 数据覆盖丢失 | 两个线程同时 `put` 到同一个空桶，都判断「桶为空」，后写的覆盖先写的 |
| `size` 不准 | `++size` 不是原子操作（读-改-写），并发下丢失更新 |
| 扩容期间读到 null | 新 table 已发布但节点尚未迁移完 |
| 可见性 | 没有 `volatile` / 锁，一个线程的写入对另一个线程不一定可见（04 章 JMM） |

**怎么选**：

| 方案 | 说明 |
|---|---|
| `ConcurrentHashMap` | **首选**。JDK 8：CAS 写空桶 + `synchronized` 锁单个桶头节点，读不加锁（04 章详解） |
| `Collections.synchronizedMap` | 全表一把锁，并发度差 |
| `Hashtable` | 历史遗留，全方法 synchronized，不用 |
| 不共享 | 最好的线程安全是不共享：方法内局部的 HashMap 完全没问题 |

> 前端视角：浏览器 JS 单线程，你从没担心过 `Map` 被同时写。在 Java 里，**Spring Bean 默认单例，被所有请求线程共享**，Bean 里的 `HashMap` 字段就是并发写的典型事故现场。

### 4.6 fail-fast 机制

```java
// ArrayList 内部（简化）
protected transient int modCount = 0;   // 结构性修改计数（add/remove 时 ++）

private class Itr implements Iterator<E> {
    int expectedModCount = modCount;    // 创建迭代器时记录快照

    public E next() {
        checkForComodification();       // 每次 next 都检查
        // ...
    }

    final void checkForComodification() {
        if (modCount != expectedModCount)
            throw new ConcurrentModificationException();
    }

    public void remove() {
        ArrayList.this.remove(lastRet);
        expectedModCount = modCount;    // 迭代器自己的 remove 会同步快照，所以安全
    }
}
```

- 增强 for 循环 `for (x : list)` 编译后就是 `Iterator`，所以 `list.remove` 会触发异常。
- fail-fast 是**尽力而为**的错误检测，不是线程安全保证；多线程下不要依赖它。
- 一个反直觉的例子：删除**倒数第二个**元素时不会抛异常——删除后 `size` 减 1，`hasNext()`（`cursor != size`）直接返回 false，循环结束，最后一个元素被悄悄跳过。
- 并发集合（`ConcurrentHashMap`、`CopyOnWriteArrayList`）是 **fail-safe**：迭代基于快照或弱一致视图，不抛异常，但可能看不到最新修改。

### 4.7 LinkedHashMap 如何实现 LRU

```java
// LinkedHashMap 内部节点在 HashMap.Node 基础上加了前后指针
static class Entry<K,V> extends HashMap.Node<K,V> {
    Entry<K,V> before, after;
}
```

HashMap 预留了三个钩子方法，LinkedHashMap 覆写它们：

| 钩子 | 触发时机 | LinkedHashMap 的动作 |
|---|---|---|
| `afterNodeAccess(e)` | `get` / `put` 覆盖已有 key | `accessOrder=true` 时把节点移到链表尾部 |
| `afterNodeInsertion(evict)` | `put` 新 key 之后 | 调 `removeEldestEntry(head)`，返回 true 则删除头节点 |
| `afterNodeRemoval(e)` | 删除节点之后 | 从双向链表摘除 |

这是**模板方法模式**的教科书案例：父类定义流程并预留钩子，子类只填充差异。

### 4.8 Stream 的内部结构

```
list.stream()      →  Head（源阶段，持有 Spliterator）
   .filter(f)      →  StatelessOp
   .map(g)         →  StatelessOp
   .sorted()       →  StatefulOp（需要看到全部元素才能输出）
   .toList()       →  终结操作：从尾向头把各阶段包装成一条 Sink 链，再由源逐个推送元素

元素推送：source ──▶ filterSink.accept ──▶ mapSink.accept ──▶ sortedSink（缓冲）──end()──▶ 收集
```

- 无状态操作（`filter/map/flatMap`）可以融合为一次遍历；有状态操作（`sorted/distinct`）需要缓冲。
- 短路操作（`findFirst/anyMatch/limit`）会通知上游提前停止，所以 `Stream.iterate(1, x -> x + 1).filter(..).findFirst()` 在无限流上也能结束。
- 并行流靠 `Spliterator.trySplit()` 拆分数据源：`ArrayList`、数组易于均匀拆分；`LinkedList`、`Stream.iterate` 拆分效果差。

### 4.9 SimpleDateFormat 为什么线程不安全

```java
// SimpleDateFormat 继承自 DateFormat，内部持有一个共享的 Calendar 实例字段
protected Calendar calendar;

// format 时：
calendar.setTime(date);   // 线程 A 写入自己的日期
// ……此时线程 B 也调用 calendar.setTime(otherDate) 覆盖了它
subFormat(...);           // 线程 A 读到的是线程 B 的日期 → 输出错误
```

解决方案演进：每次 new（开销大）→ `ThreadLocal<SimpleDateFormat>`（Java 8 前的标准做法）→ `DateTimeFormatter`（不可变，直接做 `static final` 常量）。

---

## 5. mini-mall 实战

```
本章产出：
com.example.mall
├── model/po    ProductPO
└── util        OrderStatUtil、LruCache、OrderTimeUtil、JsonUtil
```

### 5.1 ProductPO

```java
package com.example.mall.model.po;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 商品表 t_product 的实体。version 用于乐观锁扣库存（08 章）。
 */
public class ProductPO {

    /** 主键 */
    private Long id;
    /** 商品名称 */
    private String name;
    /** 售价，对应 DECIMAL(10,2) */
    private BigDecimal price;
    /** 库存 */
    private Integer stock;
    /** 乐观锁版本号 */
    private Integer version;
    /** 创建时间 */
    private LocalDateTime createTime;
    /** 更新时间 */
    private LocalDateTime updateTime;

    /** @return 主键 */
    public Long getId() { return id; }
    /** @param id 主键 */
    public void setId(Long id) { this.id = id; }
    /** @return 商品名称 */
    public String getName() { return name; }
    /** @param name 商品名称 */
    public void setName(String name) { this.name = name; }
    /** @return 售价 */
    public BigDecimal getPrice() { return price; }
    /** @param price 售价 */
    public void setPrice(BigDecimal price) { this.price = price; }
    /** @return 库存 */
    public Integer getStock() { return stock; }
    /** @param stock 库存 */
    public void setStock(Integer stock) { this.stock = stock; }
    /** @return 版本号 */
    public Integer getVersion() { return version; }
    /** @param version 版本号 */
    public void setVersion(Integer version) { this.version = version; }
    /** @return 创建时间 */
    public LocalDateTime getCreateTime() { return createTime; }
    /** @param createTime 创建时间 */
    public void setCreateTime(LocalDateTime createTime) { this.createTime = createTime; }
    /** @return 更新时间 */
    public LocalDateTime getUpdateTime() { return updateTime; }
    /** @param updateTime 更新时间 */
    public void setUpdateTime(LocalDateTime updateTime) { this.updateTime = updateTime; }
}
```

### 5.2 订单分组统计：OrderStatUtil

需求（运营后台看板）：
1. 每个状态有多少单；
2. 每个用户的消费总额（只算已支付及之后的状态）；
3. 每个用户最近一笔订单；
4. 把订单拆成「待支付」和「其他」两组，用于催付。

```java
package com.example.mall.util;

import com.example.mall.model.enums.OrderStatusEnum;
import com.example.mall.model.po.OrderPO;

import java.math.BigDecimal;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.BinaryOperator;
import java.util.stream.Collectors;

/**
 * 订单统计工具（第五层：纯内存计算，不访问数据库）。
 * 入参是 DAO 查出的订单列表；数据量大时应改为 SQL GROUP BY（08 章），不要全量拉进内存。
 */
public final class OrderStatUtil {

    /** 计入消费额的状态：已支付、已发货、已完成 */
    private static final Set<OrderStatusEnum> CONSUMED_STATUSES =
            Set.of(OrderStatusEnum.PAID, OrderStatusEnum.SHIPPED, OrderStatusEnum.COMPLETED);

    /**
     * 工具类禁止实例化。
     */
    private OrderStatUtil() {
    }

    /**
     * 按状态统计订单数，结果包含全部状态（没有订单的状态计 0），便于前端直接渲染。
     *
     * @param orders 订单列表
     * @return key 为订单状态枚举，value 为该状态的订单数；按枚举声明顺序排列
     */
    public static Map<OrderStatusEnum, Long> countByStatus(List<OrderPO> orders) {
        // 先用 EnumMap 预置所有状态为 0：EnumMap 内部是数组，按枚举顺序迭代
        Map<OrderStatusEnum, Long> result = new EnumMap<>(OrderStatusEnum.class);
        for (OrderStatusEnum s : OrderStatusEnum.values()) {
            result.put(s, 0L);
        }
        // 再逐单累加；status 无法识别的脏数据跳过
        for (OrderPO o : orders) {
            OrderStatusEnum s = o.statusEnum();
            if (s != null) {
                result.merge(s, 1L, Long::sum);
            }
        }
        return result;
    }

    /**
     * 统计每个用户的消费总额（仅计已支付及之后的订单）。
     *
     * @param orders 订单列表
     * @return key 为用户 id，value 为该用户消费总额
     */
    public static Map<Long, BigDecimal> sumConsumedAmountByUser(List<OrderPO> orders) {
        return orders.stream()
                // 只保留计入消费额的状态；先判空：Set.of 的 contains(null) 会抛 NPE
                .filter(o -> o.statusEnum() != null && CONSUMED_STATUSES.contains(o.statusEnum()))
                // 按用户分组，下游用 reducing 对 BigDecimal 求和（没有 summingBigDecimal）
                .collect(Collectors.groupingBy(OrderPO::getUserId,
                        Collectors.reducing(BigDecimal.ZERO, OrderPO::getTotalAmount, BigDecimal::add)));
    }

    /**
     * 取每个用户最近创建的一笔订单。
     *
     * @param orders 订单列表
     * @return key 为用户 id，value 为该用户创建时间最晚的订单
     */
    public static Map<Long, OrderPO> latestOrderByUser(List<OrderPO> orders) {
        // 冲突合并函数：两单比较创建时间，保留较晚的；避免 toMap 的 Duplicate key 异常
        BinaryOperator<OrderPO> keepLatest =
                BinaryOperator.maxBy(Comparator.comparing(OrderPO::getCreateTime));
        return orders.stream()
                .collect(Collectors.toMap(OrderPO::getUserId, o -> o, keepLatest));
    }

    /**
     * 将订单拆分为「待支付」与「其他」两组。
     *
     * @param orders 订单列表
     * @return key 为是否待支付（true 待支付 / false 其他），value 为对应订单列表；两个 key 必定存在
     */
    public static Map<Boolean, List<OrderPO>> partitionUnpaid(List<OrderPO> orders) {
        return orders.stream()
                .collect(Collectors.partitioningBy(
                        o -> Objects.equals(o.getStatus(), OrderStatusEnum.CREATED.getCode())));
    }
}
```

设计说明：
- `countByStatus` 没用 `groupingBy(.., counting())`，因为那样**没有订单的状态不会出现在结果里**，前端还得补 0。这是「为调用方着想」的典型取舍。
- `latestOrderByUser` 若用 `groupingBy` + `maxBy`，value 会是 `Optional<OrderPO>`，不如 `toMap` + 合并函数直接。
- `sumConsumedAmountByUser` 里先判 `statusEnum() != null`：`Set.of` 创建的不可变集合调用 `contains(null)` 会直接抛 NPE（第 6 节第 9 条），这在代码评审中极易被忽略。

### 5.3 LRU 本地商品缓存：LruCache

场景：商品详情读多写少，在进程内缓存最热的 N 个商品，减少 DB 查询。

```java
package com.example.mall.util;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 基于 LinkedHashMap 访问顺序实现的 LRU 缓存。
 * 线程安全：所有方法加 synchronized，因为 accessOrder 模式下 get 也会修改链表结构。
 * ponytail: 全局一把锁，高并发下有竞争；生产环境用 Caffeine（W-TinyLFU，09 章）。
 *
 * @param <K> 缓存 key 类型
 * @param <V> 缓存 value 类型
 */
public class LruCache<K, V> {

    /** 默认负载因子，与 HashMap 一致 */
    private static final float LOAD_FACTOR = 0.75f;

    /** 实际存储，key 为缓存键，value 为缓存值；按访问顺序排列，链表头为最久未访问 */
    private final LinkedHashMap<K, V> store;

    /**
     * 创建指定容量的 LRU 缓存。
     *
     * @param capacity 最大缓存条数，超过后淘汰最久未访问的条目
     */
    public LruCache(int capacity) {
        // 第三个参数 accessOrder=true：get/put 命中时把节点移到链表尾部
        this.store = new LinkedHashMap<>((int) (capacity / LOAD_FACTOR) + 1, LOAD_FACTOR, true) {
            /**
             * 每次 put 新 key 后由 LinkedHashMap 回调，返回 true 则删除链表头。
             *
             * @param eldest 最久未访问的条目
             * @return 超出容量时返回 true
             */
            @Override
            protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
                return size() > capacity;
            }
        };
    }

    /**
     * 读取缓存，命中时刷新其「最近访问」位置。
     *
     * @param key 缓存键
     * @return 缓存值，不存在返回 null
     */
    public synchronized V get(K key) {
        return store.get(key);
    }

    /**
     * 写入缓存，必要时淘汰最久未访问的条目。
     *
     * @param key   缓存键
     * @param value 缓存值
     */
    public synchronized void put(K key, V value) {
        store.put(key, value);
    }

    /**
     * 删除缓存（商品信息变更后调用，保证不读到旧数据）。
     *
     * @param key 缓存键
     */
    public synchronized void remove(K key) {
        store.remove(key);
    }

    /**
     * 当前缓存条数。
     *
     * @return 条数
     */
    public synchronized int size() {
        return store.size();
    }
}
```

使用（07 章会把它注册为 Spring Bean，放在 DAO 外层）：

```java
/** 本地商品缓存，key 为商品 id，value 为商品实体；最多缓存 1000 个热门商品 */
private final LruCache<Long, ProductPO> productCache = new LruCache<>(1000);

/**
 * 查询商品，优先读本地缓存，未命中再查库并回填。
 *
 * @param productId 商品 id
 * @return 商品实体，不存在返回 null
 */
public ProductPO getProduct(Long productId) {
    // 1. 先查本地缓存
    ProductPO cached = productCache.get(productId);
    if (cached != null) {
        return cached;
    }
    // 2. 未命中查库（productDao 在 08 章实现）
    ProductPO product = productDao.getById(productId);
    // 3. 回填缓存；查不到不缓存（缓存穿透的处理见 09 章）
    if (product != null) {
        productCache.put(productId, product);
    }
    return product;
}
```

自检：

```java
/**
 * LruCache 淘汰顺序自检。
 *
 * @param args 未使用
 */
public static void main(String[] args) {
    LruCache<Long, String> cache = new LruCache<>(2);
    cache.put(1L, "苹果");
    cache.put(2L, "牛奶");
    cache.get(1L);            // 访问 1，此时最久未访问的是 2
    cache.put(3L, "面包");    // 超容量，淘汰 2
    if (cache.get(2L) != null || cache.get(1L) == null || cache.size() != 2) {
        throw new AssertionError("LRU 淘汰顺序错误");
    }
    System.out.println("LRU ok");
}
```

> 本地缓存的局限：多实例部署时各实例缓存不一致，且占用 JVM 堆。这引出 09 章的「Redis 分布式缓存 + 本地缓存二级架构」。

### 5.4 订单时间处理：OrderTimeUtil

需求：
1. 判断订单是否超过 30 分钟未支付（10 章延迟消息会复用这个超时时长）；
2. 计算支付截止时间并格式化给前端；
3. 「查询某天订单」时构造 `[当天 00:00, 次日 00:00)` 区间。

```java
package com.example.mall.util;

import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

/**
 * 订单时间工具。
 * 约定：数据库 DATETIME 与 LocalDateTime 均表示东八区本地时间。
 */
public final class OrderTimeUtil {

    /** 下单后允许支付的时长：30 分钟 */
    public static final Duration PAY_TIMEOUT = Duration.ofMinutes(30);

    /** 业务时区 */
    public static final ZoneId ZONE = ZoneId.of("Asia/Shanghai");

    /** 标准时间格式；DateTimeFormatter 不可变且线程安全，可作全局常量 */
    public static final DateTimeFormatter DATETIME_FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    /**
     * 工具类禁止实例化。
     */
    private OrderTimeUtil() {
    }

    /**
     * 计算支付截止时间。
     *
     * @param createTime 订单创建时间
     * @return 创建时间 + 30 分钟
     */
    public static LocalDateTime payDeadline(LocalDateTime createTime) {
        return createTime.plus(PAY_TIMEOUT);
    }

    /**
     * 判断订单是否已支付超时。now 由调用方传入而非内部取当前时间，便于单测固定时间。
     *
     * @param createTime 订单创建时间
     * @param now        当前时间
     * @return now 达到或超过截止时间返回 true
     */
    public static boolean isPayTimeout(LocalDateTime createTime, LocalDateTime now) {
        return !now.isBefore(payDeadline(createTime));
    }

    /**
     * 计算距离支付截止的剩余秒数，供前端倒计时。
     *
     * @param createTime 订单创建时间
     * @param now        当前时间
     * @return 剩余秒数，已超时返回 0
     */
    public static long remainingPaySeconds(LocalDateTime createTime, LocalDateTime now) {
        long seconds = Duration.between(now, payDeadline(createTime)).getSeconds();
        return Math.max(seconds, 0);
    }

    /**
     * 构造某一天的查询区间起点（含）。
     *
     * @param day 日期
     * @return 当天 00:00:00
     */
    public static LocalDateTime dayStart(LocalDate day) {
        return day.atStartOfDay();
    }

    /**
     * 构造某一天的查询区间终点（不含）。
     * 用左闭右开 [start, nextStart) 而非 23:59:59，避免漏掉 23:59:59.5 这类带毫秒的数据。
     *
     * @param day 日期
     * @return 次日 00:00:00
     */
    public static LocalDateTime dayEndExclusive(LocalDate day) {
        return day.plusDays(1).atStartOfDay();
    }

    /**
     * 本地时间转毫秒时间戳（给前端 dayjs(ms) 使用）。
     *
     * @param time 本地时间
     * @return 纪元毫秒
     */
    public static long toEpochMilli(LocalDateTime time) {
        return time.atZone(ZONE).toInstant().toEpochMilli();
    }

    /**
     * 格式化时间。
     *
     * @param time 时间，可为 null
     * @return yyyy-MM-dd HH:mm:ss 格式字符串；null 返回 null
     */
    public static String format(LocalDateTime time) {
        return time == null ? null : time.format(DATETIME_FMT);
    }
}
```

查询区间在 SQL 中的写法（08 章）：`WHERE create_time >= #{start} AND create_time < #{end}`——这样还能命中 `create_time` 上的索引，而 `DATE(create_time) = '2026-11-26'` 会让索引失效。

自检：

```java
/**
 * OrderTimeUtil 边界自检。
 *
 * @param args 未使用
 */
public static void main(String[] args) {
    LocalDateTime created = LocalDateTime.of(2026, 11, 26, 10, 0, 0);
    // 边界：恰好 30 分钟算超时，29 分 59 秒不算
    if (!OrderTimeUtil.isPayTimeout(created, created.plusMinutes(30))
            || OrderTimeUtil.isPayTimeout(created, created.plusMinutes(30).minusSeconds(1))) {
        throw new AssertionError("超时判断边界错误");
    }
    if (OrderTimeUtil.remainingPaySeconds(created, created.plusMinutes(10)) != 1200) {
        throw new AssertionError("剩余秒数错误");
    }
    System.out.println(OrderTimeUtil.format(OrderTimeUtil.payDeadline(created))); // 2026-11-26 10:30:00
}
```

### 5.5 JsonUtil：全局 ObjectMapper

```java
package com.example.mall.util;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

/**
 * JSON 工具：用于非 Spring 管理的场景（如日志、MQ 消息体、Redis 值）。
 * Web 层的 JSON 转换由 Spring Boot 自动配置的 ObjectMapper 完成（07 章），两者配置应保持一致。
 */
public final class JsonUtil {

    /** 全局共享实例：ObjectMapper 配置完成后线程安全，创建开销大，禁止每次 new */
    private static final ObjectMapper MAPPER = new ObjectMapper()
            // 支持 LocalDateTime 等 java.time 类型
            .registerModule(new JavaTimeModule())
            // 时间输出为 ISO 字符串而非数组
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            // 遇到未知字段不报错，提升上下游兼容性
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

    /**
     * 工具类禁止实例化。
     */
    private JsonUtil() {
    }

    /**
     * 对象序列化为 JSON 字符串。
     *
     * @param value 任意可序列化对象
     * @return JSON 字符串
     */
    public static String toJson(Object value) {
        try {
            return MAPPER.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            // 受检异常包装为非受检，保留 cause
            throw new IllegalStateException("JSON 序列化失败", e);
        }
    }

    /**
     * JSON 反序列化为指定类型。
     *
     * @param json  JSON 字符串
     * @param clazz 目标类型
     * @param <T>   目标类型参数
     * @return 反序列化后的对象
     */
    public static <T> T fromJson(String json, Class<T> clazz) {
        try {
            return MAPPER.readValue(json, clazz);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("JSON 反序列化失败", e);
        }
    }

    /**
     * JSON 反序列化为泛型类型，如 List&lt;OrderPO&gt;。
     *
     * @param json JSON 字符串
     * @param type 携带完整泛型信息的类型引用
     * @param <T>  目标类型参数
     * @return 反序列化后的对象
     */
    public static <T> T fromJson(String json, TypeReference<T> type) {
        try {
            return MAPPER.readValue(json, type);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("JSON 反序列化失败", e);
        }
    }
}
```

> `toJson(Object value)` 的参数是 `Object`，这是「接收任意类型」的 API 入参，不是用 `Object` 充当数据结构，属于合理用法。
> 依赖：`jackson-databind` + `jackson-datatype-jsr310`（Spring Boot 的 `spring-boot-starter-json` 已包含）。

```java
// 使用
String json = JsonUtil.toJson(order);
// {"id":1,"orderNo":"A001","userId":10,"totalAmount":10.10,"status":0,"createTime":"2026-11-26T10:00:00",...}
List<OrderPO> list = JsonUtil.fromJson(arrayJson, new TypeReference<List<OrderPO>>() { });
```

注意：`OrderPO.statusEnum()` 不以 `get` 开头，所以不会被序列化成额外字段——这正是 01 章命名取舍的用处。

---

## 6. 常见坑

| # | 坑 | 现象 | 正确做法 |
|---|---|---|---|
| 1 | foreach 中 `list.remove` | `ConcurrentModificationException` | `removeIf` / `Iterator.remove` |
| 2 | `Arrays.asList(..).add(x)` | `UnsupportedOperationException` | `new ArrayList<>(Arrays.asList(..))` |
| 3 | `Arrays.asList(int[])` | 得到 `List<int[]>`，size 为 1 | 用 `Integer[]` 或 `IntStream.of(arr).boxed().toList()` |
| 4 | `List<Integer>.remove(1)` | 删的是下标 1 | `remove(Integer.valueOf(1))` |
| 5 | `toMap` 键重复 | `IllegalStateException: Duplicate key` | 提供合并函数 |
| 6 | `toMap` value 为 null | NPE | 先过滤 null 或手写循环 |
| 7 | 可变对象作 HashMap key 后修改 | `get` 不到、内存泄漏 | key 用不可变对象（String、Long、record） |
| 8 | 共享 HashMap 被多线程写 | 数据丢失，JDK 7 下 CPU 100% | `ConcurrentHashMap` 或不共享 |
| 9 | `List.of / Set.of` 遇到 null | `List.of(null)` 与 `Set.of(..).contains(null)` 都抛 NPE | 先判空；需要 null 时用 `ArrayList/HashSet` |
| 10 | 方法返回 `null` 集合 | 调用方遍历 NPE | 返回 `Collections.emptyList()` / `List.of()` |
| 11 | `subList` 当独立列表用 | 修改原列表后访问 subList 抛 CME | `new ArrayList<>(list.subList(a, b))` |
| 12 | 并行流里写外部集合 | 数据丢失或越界 | 用 `collect` |
| 13 | 日期格式 `YYYY-MM-dd` / `hh` | 跨年周年份错误 / 12 小时制 | `yyyy-MM-dd HH:mm:ss` |
| 14 | `static SimpleDateFormat` | 并发下日期错乱 | `static final DateTimeFormatter` |
| 15 | 用 `23:59:59` 作当天终点 | 漏掉带毫秒的数据 | 左闭右开 `< 次日 00:00` |
| 16 | 服务器时区与业务时区不同 | 时间差 8 小时 | JVM 启动参数 `-Duser.timezone=Asia/Shanghai`；JDBC URL 配 `serverTimezone`；跨时区系统用 `Instant` |
| 17 | 每次 `new ObjectMapper()` | 性能差（创建开销大，缓存无法复用） | 全局单例 |
| 18 | Long 型 id 直接返回前端 | 前端精度丢失，末位变 0 | Long 序列化为字符串 |
| 19 | `Files.lines` 不关闭 | 文件句柄泄漏 | try-with-resources |
| 20 | 读写文件不指定编码（Java 17 及以前） | 不同服务器默认编码不同导致乱码 | 显式 `StandardCharsets.UTF_8`（Java 18+ 默认 UTF-8） |

---

## 7. 高级视角

### 7.1 集合的内存账本

服务端进程常驻且数据量大，集合的内存开销必须心里有数（64 位 JVM，开启压缩指针）：

| 结构 | 每元素大致开销 |
|---|---|
| `Long` 对象 | 24 字节（对象头 12 + 值 8 = 20，按 8 字节对齐到 24） |
| `ArrayList<Long>` | 4 字节引用 + Long 对象本身 |
| `HashMap<Long, Long>` | Node 32 字节 + key/value 两个 Long 共 48 字节 + 桶数组引用 ≈ **80+ 字节/条** |
| `long[]` | 8 字节/元素 |

结论：100 万条 `HashMap<Long, Long>` ≈ 80MB+；同样数据用 `long[]` 只要 16MB。这就是 03 章「一次加载百万订单 OOM」的根源之一。海量基本类型数据考虑原生数组、分批处理、或 fastutil/Eclipse Collections 等原始类型集合库。

### 7.2 内存计算 vs 数据库计算

`OrderStatUtil` 适合**已在内存中的小批量数据**（如一个用户的订单列表、一页数据）。全站统计必须下推到数据库（`GROUP BY`）或数仓。判断标准：数据量是否有上界、上界是多少。「先查全量再在 Java 里 groupingBy」是线上 OOM 和慢接口的常见源头。

### 7.3 HashMap 与安全

如果攻击者能控制大量 key（如 HTTP 参数名、JSON 字段名），可构造 hashCode 全部相同的字符串，让 HashMap 退化。JDK 7 时代这是真实的 DoS 漏洞（Hash Collision DoS）；JDK 8 的红黑树把最坏复杂度降到 O(log n)，Tomcat 也限制了参数个数（`maxParameterCount`）。这说明**数据结构的最坏情况复杂度也是安全问题**。

### 7.4 时间设计的工程规范

- 存储：业务时间用 `DATETIME` + 约定时区（国内系统常见做法），或统一 UTC 存储、展示时转换（跨国系统）。团队必须**明确一种**。
- 接口：对前端传时间戳（毫秒）还是格式化字符串要全局统一；时间戳无时区歧义，更适合多端。
- 代码：业务逻辑中不要直接 `LocalDateTime.now()`，通过参数传入或注入 `Clock`（`LocalDateTime.now(clock)`），单测才能固定时间，见 `isPayTimeout` 的设计。

### 7.5 JSON 的兼容性契约

接口一旦发布，JSON 结构就是契约。向后兼容的规则：只加字段不删字段、不改字段类型和含义、枚举新增值要确认调用方能容忍未知值。Jackson 的 `FAIL_ON_UNKNOWN_PROPERTIES=false` 是**接收方的宽容**，对应前端的「对后端多返回的字段视而不见」；发送方仍需遵守不删不改。

---

## 8. 小练习

1. **HashMap 观察**：写一个 `hashCode()` 永远返回 1 的 key 类，往 HashMap 中放 10000 个，对比与正常 key 的 `get` 耗时；在 IDE 调试器中观察 `table` 长度变化与桶内节点何时变成 `TreeNode`。
2. **fail-fast**：对 `List.of(1,2,3,4)` 复制出的 ArrayList，在 foreach 中分别删除元素 `3`（倒数第二个）与 `2`，解释为什么一个抛异常一个不抛，以及不抛的那个漏掉了什么。
3. **分组统计**：基于 `OrderStatUtil` 增加 `Map<LocalDate, BigDecimal> sumAmountByDay(List<OrderPO>)`，按创建日期统计金额，并要求结果按日期升序（提示：`groupingBy` 的 mapFactory 传 `TreeMap::new`）。
4. **Top N**：用 `PriorityQueue` 实现「消费额最高的 3 个用户」，与 `sorted().limit(3)` 对比，思考数据量 1 亿时哪个更合适。
5. **LRU 改造**：给 `LruCache` 增加过期时间（每个条目写入后 10 分钟失效），思考 value 需要包装成什么结构（用 record 定义，而不是 `Object[]`）。
6. **时间**：实现 `List<LocalDate> lastNDays(LocalDate today, int n)`，返回包括今天在内最近 n 天；再实现「本月第一天 00:00 到下月第一天 00:00」区间。
7. **Jackson**：把 `OrderPO` 的 `id` 设为 `1876543210987654321L` 序列化后，在浏览器控制台 `JSON.parse` 观察精度丢失；然后用 `@JsonSerialize(using = ToStringSerializer.class)` 修复。
