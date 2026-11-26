> [← 总纲](./00-outline.md) | [上一章：Spring Boot 与 Web 开发](./07-spring-boot-web.md) | [下一章：Redis 与缓存](./09-redis-cache.md)

# 08 数据库与持久层：MySQL 索引/事务/锁 + MyBatis-Plus

---

## 1. 本章地图

前端工程师和数据库打交道，通常止步于「调接口拿 JSON」，或在 Node 里用 Prisma 写几行 `findMany`。服务端的现实是：**绝大多数线上性能问题、数据错乱问题，最后都落在数据库上**。

```
① Controller → ② 编排 Component → ③ 功能单元(@Transactional)
                                            │
                                            ▼
                         ④ DAO（OrderDao / ProductDao）   ← 本章：怎么写、怎么封装
                                            │
                                            ▼
                         Mapper（MyBatis-Plus） → JDBC → HikariCP 连接池
                                            │  TCP
                                            ▼
                         MySQL 8（InnoDB）                ← 本章：索引、事务、MVCC、锁
```

本章要回答的问题：

| 问题 | 小节 |
|---|---|
| 一条 SQL 在 MySQL 里是怎么被执行的？ | 3.1 |
| 表怎么建才「规范」？金额、时间、主键怎么选？ | 3.3 / 3.4 |
| 索引为什么是 B+ 树？为什么加了索引还是慢？ | 3.5 / 3.6 |
| 事务的 ACID 靠什么实现？MVCC 是什么？ | 4.1 ~ 4.3 |
| 为什么会死锁？怎么排查？ | 4.4 |
| 深分页、count、join 怎么优化？ | 4.5 |
| JDBC / MyBatis / MyBatis-Plus 是什么关系？DAO 层怎么写？ | 5 |
| mini-mall 的表、实体、DAO、乐观锁扣库存、慢 SQL 案例 | 6 |

---

## 2. 前端类比

| 前端熟悉的东西 | 数据库里的对应物 | 差异点（重点） |
|---|---|---|
| 一个 JSON 数组 `orders[]` | 一张表 | 表有 schema 约束，字段类型、长度、是否可空都要提前定 |
| `orders.find(o => o.id === 1)`（O(n) 遍历） | 全表扫描 | 百万行时就是灾难 |
| `new Map(orders.map(o => [o.id, o]))` 预建索引 | 索引 | 索引是有序的 B+ 树，不只支持等值，还支持范围、排序 |
| Prisma / TypeORM | MyBatis-Plus / JPA | 国内主流是「SQL 可控」的 MyBatis 系 |
| `prisma migrate` 生成迁移文件 | 手写 DDL + 评审 + DBA 执行 | 线上大表改结构可能锁表，必须评审 |
| React `setState` 批量合并、要么全生效 | 事务 | 事务还要解决**并发**：多个请求同时改同一行 |
| 乐观更新 + 冲突回滚（SWR mutate） | 乐观锁 `version` | 思路一致：先不加锁，提交时检查版本 |
| IndexedDB 的 `readwrite` 事务 | InnoDB 事务 | IndexedDB 是单用户；MySQL 是成千上万连接并发 |

> 核心思维转变：前端的数据是「单用户、内存里、丢了刷新就行」；数据库的数据是「多用户并发写、落盘持久、错了就是资损」。

---

## 3. 核心概念

### 3.1 MySQL 架构：一条 SQL 的旅程

```
客户端（HikariCP 连接）
   │  SELECT * FROM t_order WHERE user_id = 1001 ORDER BY create_time DESC LIMIT 10
   ▼
┌───────────────────────── Server 层 ─────────────────────────┐
│ 连接器：TCP 握手、鉴权、权限读取、维持连接（wait_timeout）  │
│   ▼                                                           │
│ （查询缓存：MySQL 8.0 已删除，命中率低、写多时频繁失效）     │
│   ▼                                                           │
│ 分析器：词法/语法分析 → 语法树（表、列是否存在）              │
│   ▼                                                           │
│ 优化器：选索引、定 join 顺序 → 执行计划（基于成本 CBO）       │
│   ▼                                                           │
│ 执行器：校验权限，按计划调用存储引擎接口，逐行取数据、过滤    │
└──────────────────────────┬────────────────────────────────────┘
                           │ handler API（读一行/下一行）
                           ▼
┌──────────────────────── 存储引擎层（插件式）─────────────────┐
│ InnoDB：Buffer Pool、B+ 树索引、redo/undo log、行锁、MVCC     │
└────────────────────────────────────────────────────────────────┘
                           │
                           ▼
                 磁盘：.ibd 数据文件、redo log、binlog（Server 层）
```

要点：

- **Server 层与引擎层分离**：binlog 属于 Server 层（所有引擎都有），redo/undo log 属于 InnoDB。这一点是理解「两阶段提交」的前提。
- **优化器可能选错索引**：它基于统计信息估算成本，统计信息不准时会选错。可用 `ANALYZE TABLE` 更新统计，或 `FORCE INDEX` 兜底（不推荐常态使用）。
- **长连接与内存**：连接里的临时内存在断开时才释放，所以要靠连接池控制连接数和生命周期（见 5.2）。

### 3.2 InnoDB vs MyISAM

| 维度 | InnoDB（默认，必选） | MyISAM（历史） |
|---|---|---|
| 事务 | 支持 | 不支持 |
| 锁粒度 | 行锁 | 表锁 |
| 崩溃恢复 | redo log 保证 | 可能损坏，需要修复 |
| 外键 | 支持 | 不支持 |
| 数据组织 | 聚簇索引：数据就存在主键 B+ 树叶子上 | 堆表：索引和数据分开存 |
| `COUNT(*)` | 需要扫描（MVCC 下每个事务看到的行数不同） | 直接存了总行数 |
| MVCC | 支持 | 不支持 |

结论：**业务表一律 InnoDB**。面试问 MyISAM 只是为了让你讲清 InnoDB 为什么好。

### 3.3 表设计规范

#### 3.3.1 字段类型选择

| 场景 | 推荐类型 | 反例 / 原因 |
|---|---|---|
| 主键 | `BIGINT UNSIGNED` | `INT` 上限约 21 亿，订单表迟早爆 |
| 状态/类型 | `TINYINT` + 注释写清枚举 | 不用 `ENUM` 类型：加枚举值要改表结构 |
| 布尔 | `TINYINT(1)`，字段名不加 `is_` 前缀也可，团队统一即可 | — |
| 金额 | `DECIMAL(10,2)` 或 `BIGINT` 存「分」 | **绝不用 FLOAT/DOUBLE**：二进制浮点无法精确表示 0.1 |
| 短字符串 | `VARCHAR(n)`，n 按业务上限给 | 不要无脑 `VARCHAR(255)`：排序/临时表按定义长度分配内存 |
| 长文本 | `TEXT`，最好拆到扩展表 | 大字段让每页存的行变少，拖慢主表扫描 |
| 时间 | `DATETIME` | `TIMESTAMP` 有 2038 年问题，且受会话时区影响 |
| 手机号、订单号 | `VARCHAR` | 不是数字：有前导 0、不参与计算 |

金额在 Java 里对应 `BigDecimal`，在 TS 里你可能习惯 `number`——这正是前端最容易踩的坑：

```ts
// TS：0.1 + 0.2 !== 0.3，前端通常用「分」为整数规避
const total = 0.1 + 0.2; // 0.30000000000000004
const totalFen = 10 + 20; // 30 分
```

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * 金额计算示例。
 */
public class MoneyDemo {

    /**
     * 计算商品小计：单价 × 数量，保留 2 位小数。
     *
     * @param price    单价（来自 DECIMAL(10,2) 字段）
     * @param quantity 购买数量
     * @return 小计金额，四舍五入保留 2 位
     */
    public static BigDecimal subtotal(BigDecimal price, int quantity) {
        // 必须用 BigDecimal 运算，且用字符串/valueOf 构造，不能 new BigDecimal(0.1)
        return price.multiply(BigDecimal.valueOf(quantity)).setScale(2, RoundingMode.HALF_UP);
    }
}
```

#### 3.3.2 主键选型：自增 vs 雪花 vs UUID

| 方案 | 有序性 | 长度 | 优点 | 缺点 | 适用 |
|---|---|---|---|---|---|
| 自增 `AUTO_INCREMENT` | 严格递增 | 8 字节 | 简单；插入总在 B+ 树末尾，几乎无页分裂 | 分库分表后不唯一；ID 可被遍历猜出业务量 | 单库、非对外暴露 |
| 雪花算法 Snowflake | 趋势递增 | 8 字节 | 分布式唯一、有序、可反解时间 | 依赖机器时钟（时钟回拨问题）；需分配 workerId | 分库分表、对外暴露的 ID（MP 的 `ASSIGN_ID` 默认就是） |
| UUID | 完全随机 | 36 字符 | 无需协调 | 长、随机插入导致**大量页分裂**和二级索引膨胀 | 不建议作 InnoDB 主键 |

为什么随机主键慢？InnoDB 主键索引是聚簇索引，数据按主键顺序存放。递增主键每次追加到最后一页；随机主键要插到中间，页满了就要分裂、搬数据，Buffer Pool 命中率也下降。

mini-mall 选择：`id` 用 MP 的 `ASSIGN_ID`（雪花），为第 11 章分库分表预留；对外展示的 `order_no` 另行生成（带日期前缀，方便客服查单）。

#### 3.3.3 为什么互联网项目不用外键

| 外键的问题 | 说明 |
|---|---|
| 性能 | 每次写子表都要检查父表、加共享锁，高并发下锁冲突 |
| 级联不可控 | `ON DELETE CASCADE` 一删一大片，且不走业务日志 |
| 分库分表 | 跨库无法建立外键 |
| 运维 | 数据修复、迁移时外键约束成为阻碍 |

替代方案：**在应用层保证关联关系**（功能单元里先查父再写子，放在同一事务中），字段上建普通索引。

#### 3.3.4 逻辑删除

物理删除 `DELETE` 不可恢复，也不利于审计。逻辑删除加一列 `deleted TINYINT NOT NULL DEFAULT 0`：

- 所有查询都要带 `deleted = 0`（MP 的 `@TableLogic` 自动处理）；
- **坑：唯一索引冲突**。用户名 `alice` 被逻辑删除后再注册 `alice` 会撞唯一键。解法：唯一索引改为 `(username, delete_token)`，删除时把 `delete_token` 设为 id 或时间戳；
- 订单这类「不会被删、只会改状态」的数据，用状态字段即可，不需要逻辑删除。

#### 3.3.5 create_time / update_time

每张表都应有：

```sql
create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
```

用途：排查问题、增量同步（数仓按 `update_time` 拉增量）、对账。数据库默认值 + 应用层 MP 自动填充双保险（见 5.4.4）。

### 3.4 DDL 规范

#### 3.4.1 基本要求

1. 表和每个字段都写**中文 COMMENT**，枚举字段把取值写全；
2. 字段 `NOT NULL` + 合理默认值优先（NULL 让索引统计、`!=` 判断、`COUNT(col)` 都变复杂）；
3. 显式指定 `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`（`utf8` 在 MySQL 里只有 3 字节，存不了 emoji）；
4. 索引命名：唯一索引 `uk_字段`，普通索引 `idx_字段`。

#### 3.4.2 同一张表的多个 ALTER 合并成一条

```sql
-- 反例：三条 ALTER，大表上会重建/拷贝三次表
ALTER TABLE t_order ADD COLUMN pay_time DATETIME NULL COMMENT '支付时间';
ALTER TABLE t_order ADD COLUMN cancel_reason VARCHAR(128) NOT NULL DEFAULT '' COMMENT '取消原因';
ALTER TABLE t_order ADD INDEX idx_status_create_time (status, create_time);

-- 正例：t_order 增加支付时间、取消原因，并为超时取消任务增加索引（一条语句，只扫一次表）
ALTER TABLE t_order
    ADD COLUMN pay_time DATETIME NULL COMMENT '支付时间，未支付为 NULL',
    ADD COLUMN cancel_reason VARCHAR(128) NOT NULL DEFAULT '' COMMENT '取消原因',
    ADD INDEX idx_status_create_time (status, create_time);
```

#### 3.4.3 线上兼容：新字段必须有 DEFAULT 或允许 NULL

发布顺序通常是「先执行 DDL，再发新代码」。在新代码上线前，**老代码的 INSERT 不带新字段**：

```sql
-- 老代码仍在执行
INSERT INTO t_order (id, order_no, user_id, total_amount, status) VALUES (...);
```

- 新字段 `NOT NULL` 且无 `DEFAULT` → 严格模式下直接报错 `Field 'xxx' doesn't have a default value`，**线上下单全挂**；
- 所以新字段要么 `NULL`，要么 `NOT NULL DEFAULT 某值`；
- 同理，**删字段要反着来**：先发不再读写该字段的代码，再删字段；改名 = 加新字段 + 双写 + 迁移 + 删旧字段。

#### 3.4.4 大表 DDL：Online DDL 与 gh-ost

| 方式 | 原理 | 注意 |
|---|---|---|
| `ALGORITHM=INSTANT`（8.0.12+） | 只改元数据，秒级完成 | 8.0.29 起支持任意位置加列；加索引不支持 INSTANT |
| `ALGORITHM=INPLACE, LOCK=NONE` | 引擎内重建，期间允许读写，增量记到 row log 最后回放 | 开始和结束仍需短暂 MDL 写锁；耗 IO，主从延迟 |
| gh-ost / pt-osc | 建影子表 → 拷数据 → 同步增量（gh-ost 读 binlog）→ 原子 rename | 可限速、可暂停，大表首选 |

**MDL 锁陷阱**：DDL 要拿元数据写锁，若前面有一个长事务持有该表的 MDL 读锁，DDL 会等待；而后续所有查询又排在 DDL 后面 → 整张表不可读写，看起来像「数据库挂了」。执行 DDL 前先查 `information_schema.innodb_trx` 有没有长事务，并设置 `lock_wait_timeout`。

### 3.5 索引

#### 3.5.1 B+ 树结构

```
                         ┌───────────────────┐
         根节点（非叶子）│  100  │  200      │           只存 key + 子页指针
                         └──┬────────┬───────┬┘
               ┌────────────┘        │       └─────────────┐
               ▼                     ▼                     ▼
        ┌────────────┐        ┌────────────┐        ┌────────────┐
        │ 10 │ 50    │        │ 120 │ 160  │        │ 230 │ 300  │   非叶子
        └─┬────┬───┬─┘        └──┬─────┬───┬┘        └──┬────┬───┬┘
          ▼    ▼   ▼             ▼     ▼   ▼            ▼    ▼   ▼
 叶子：  [1..9]⇄[10..49]⇄[50..99]⇄[100..119]⇄ ... ⇄[230..299]⇄[300..]
          │
          └── 聚簇索引：叶子存整行数据；二级索引：叶子存 (索引列, 主键)
              叶子之间双向链表 → 范围查询、排序只需顺序扫描
```

一页 16KB，非叶子节点每个条目 = 主键 8 字节 + 指针 6 字节 ≈ 14 字节，一页能放约 1170 个；若叶子每行 1KB 能放 16 行，三层能存 `1170 × 1170 × 16 ≈ 2000 万` 行。**所以千万级表通常只需 3 次磁盘 IO**（根节点和第二层常驻 Buffer Pool，实际更少）。

为什么不用其他结构？

| 结构 | 不选的原因 |
|---|---|
| 哈希表 | 只支持等值；不支持范围、排序、最左前缀（InnoDB 有自适应哈希索引作为内部优化） |
| 二叉搜索树 / 红黑树 | 每个节点只有 2 个分叉，树太高，百万数据要 20 层 → 20 次磁盘 IO |
| B 树 | 非叶子节点也存数据 → 每页能放的 key 少，树更高；范围查询要中序遍历跨层回溯 |
| B+ 树 | 非叶子只存 key（扇出大、树矮）；所有数据在叶子且有链表（范围扫描高效）；查询路径长度稳定 |

#### 3.5.2 聚簇索引、二级索引与回表

```
SELECT * FROM t_order WHERE order_no = 'M20261126000001';

① 二级索引 uk_order_no 的 B+ 树
   叶子：('M20261126000001', id=1863...)  → 拿到主键 id
                                              │ 回表
② 聚簇索引（主键 B+ 树）                      ▼
   叶子：(id=1863..., order_no, user_id, total_amount, status, ...)  → 整行
```

- **聚簇索引**：InnoDB 表本身就是一棵按主键组织的 B+ 树，每表只有一个；
- **二级索引**：叶子存「索引列 + 主键值」，查其他列要拿主键回聚簇索引再查一次，称为**回表**；
- 为什么二级索引存主键而不是行地址？因为页分裂会移动行，存主键则二级索引不用跟着改。

#### 3.5.3 覆盖索引

如果查询需要的列全在二级索引里，就不用回表：

```sql
-- 索引 idx_user_create_time(user_id, create_time)，叶子含 (user_id, create_time, id)
SELECT id, create_time FROM t_order WHERE user_id = 1001;   -- Extra: Using index（覆盖）
SELECT * FROM t_order WHERE user_id = 1001;                 -- 需要回表
```

这就是「不要写 `SELECT *`」的性能理由之一，也是深分页优化（4.5.1）的基础。

#### 3.5.4 联合索引与最左前缀

联合索引 `(a, b, c)` 的 B+ 树按 a 排序，a 相同按 b，b 相同按 c——就像前端的多字段排序：

```ts
// 联合索引 (user_id, status, create_time) 的排序规则，等价于：
rows.sort((x, y) =>
  x.userId - y.userId || x.status - y.status || x.createTime - y.createTime);
```

| 查询条件 | 能否用索引 | 说明 |
|---|---|---|
| `a = 1` | ✔ | — |
| `a = 1 AND b = 2` | ✔ | — |
| `b = 2 AND a = 1` | ✔ | 优化器会调整顺序，与书写顺序无关 |
| `b = 2` | ✘ | 跳过了最左列，b 全局无序（8.0.13+ 的 Skip Scan 在 a 基数极低时可能用上） |
| `a = 1 AND c = 3` | 部分 | 只有 a 能用于定位，c 可通过索引下推过滤 |
| `a > 1 AND b = 2` | 部分 | 范围查询后的列无法用于定位 |
| `a = 1 ORDER BY b` | ✔ | a 固定后 b 有序，免排序 |
| `a = 1 ORDER BY c` | ✘ 排序 | 出现 `Using filesort` |

**联合索引设计口诀**：等值条件列在前、范围/排序列在后；区分度高的在前（在等值列之间）；能覆盖高频查询就更好。

#### 3.5.5 索引下推（ICP，Index Condition Pushdown）

```sql
-- 索引 idx_user_status_create(user_id, status, create_time)
SELECT * FROM t_order WHERE user_id = 1001 AND create_time > '2026-01-01';
```

- 无 ICP（5.6 前）：引擎按 `user_id = 1001` 找到所有索引条目，**逐条回表**，Server 层再判断 `create_time`；
- 有 ICP：引擎在二级索引上就先用 `create_time` 过滤（虽然这列不能用于定位，但它就在索引里），过滤后才回表。EXPLAIN 显示 `Using index condition`。

#### 3.5.6 索引失效的常见场景

| 场景 | 反例 | 正确写法 |
|---|---|---|
| 对索引列做函数/运算 | `WHERE DATE(create_time) = '2026-11-26'` | `WHERE create_time >= '2026-11-26' AND create_time < '2026-11-27'` |
| 隐式类型转换 | `order_no` 是 VARCHAR，`WHERE order_no = 123` | `WHERE order_no = '123'`（字符串列 vs 数字常量 → 列被转换） |
| 左模糊 | `LIKE '%手机'` | 右模糊 `LIKE '手机%'`；全文搜索走 ES |
| 违反最左前缀 | 见上表 | 调整索引或补条件 |
| `OR` 有一边无索引 | `WHERE user_id = 1 OR product_name = 'x'` | 两边都建索引（index_merge）或改 `UNION ALL` |
| `!=` / `NOT IN` / `IS NOT NULL` | 结果集太大 | 优化器判断全表扫描更便宜，不是「不能用」 |
| 区分度低 | `WHERE status = 1`，90% 都是 1 | 不单独给低区分度列建索引 |
| 字符集不一致的 join | utf8 表 join utf8mb4 表 | 统一字符集 |

> 核心原理只有一条：**B+ 树按「索引列的原始值」有序**。任何让 MySQL 不能直接拿原始值在树上二分查找的写法，都会让索引失效（或只能扫描）。

### 3.6 EXPLAIN 逐列解读

```sql
EXPLAIN SELECT id, order_no, total_amount, status, create_time
FROM t_order WHERE user_id = 1001 ORDER BY create_time DESC LIMIT 10;
```

| 列 | 含义 | 关注点 |
|---|---|---|
| id | 查询序号 | 子查询/UNION 时有多个；id 大的先执行，相同从上往下 |
| select_type | SIMPLE / PRIMARY / SUBQUERY / DERIVED / UNION | DERIVED 表示派生表（FROM 子查询） |
| table | 访问的表 | — |
| partitions | 命中的分区 | — |
| **type** | 访问类型，从好到差：`system > const > eq_ref > ref > range > index > ALL` | 至少要 `range`，最好 `ref`；`index` 是扫整棵索引树，`ALL` 是全表扫 |
| possible_keys | 可能用的索引 | — |
| **key** | 实际用的索引 | NULL 就是没走索引 |
| **key_len** | 用到的索引字节数 | 判断联合索引用了几列（VARCHAR(n) utf8mb4 = 4n+2，可空再 +1） |
| ref | 与索引比较的是常量还是哪一列 | — |
| **rows** | 预估扫描行数 | 估算值，量级比精确值重要 |
| filtered | 经 WHERE 过滤后剩余百分比 | rows × filtered 约等于返回给上层的行数 |
| **Extra** | 额外信息 | 见下表 |

Extra 常见值：

| 值 | 好坏 | 含义 |
|---|---|---|
| Using index | 好 | 覆盖索引，不回表 |
| Using index condition | 较好 | 索引下推 |
| Using where | 中性 | Server 层还要过滤 |
| Using filesort | 差 | 无法利用索引排序，要额外排序（内存不够还会落盘） |
| Using temporary | 差 | 用了临时表（GROUP BY/DISTINCT 常见） |
| Using join buffer | 差 | 被驱动表 join 字段没索引 |

MySQL 8 还可以用 `EXPLAIN ANALYZE` 真实执行并给出每步耗时与实际行数，排查「估算和实际差很多」的情况时很有用。

---

## 4. 原理深挖

### 4.1 事务 ACID 与实现

| 特性 | 含义 | InnoDB 靠什么实现 |
|---|---|---|
| A 原子性 | 要么全成功，要么全回滚 | **undo log**：记录反向操作，回滚时执行 |
| C 一致性 | 数据从一个合法状态到另一个合法状态 | 由 A、I、D 共同保证 + 应用层约束（目的，不是手段） |
| I 隔离性 | 并发事务互不干扰 | **MVCC + 锁** |
| D 持久性 | 提交后不丢 | **redo log**（WAL）+ 崩溃恢复 |

#### 4.1.1 三种日志

| 日志 | 所属层 | 内容 | 作用 |
|---|---|---|---|
| redo log | InnoDB | 物理日志：「某页某偏移改成什么」 | 崩溃恢复；循环写固定大小文件 |
| undo log | InnoDB | 逻辑日志：「插入的反操作是删除」等 | 回滚 + MVCC 版本链 |
| binlog | Server | 逻辑日志：SQL 语句或行变更（ROW 格式） | 主从复制、数据恢复、Canal 订阅 |

**WAL（Write-Ahead Logging）**：改数据时只改内存中的页（变成「脏页」），同时顺序写 redo log；脏页由后台慢慢刷盘。顺序写日志远快于随机写数据页——这是数据库「写得快又不丢」的核心思路。

#### 4.1.2 一条 UPDATE 的执行与两阶段提交

```
UPDATE t_product SET stock = stock - 1 WHERE id = 1;

执行器                                  InnoDB
  │ 1. 取 id=1 这行 ───────────────────▶ 在 Buffer Pool 吗？不在则从磁盘读页
  │ ◀──────────────────────────────── 返回行
  │ 2. 计算 stock-1，调用写接口 ───────▶ 写 undo log（旧值，用于回滚/MVCC）
  │                                      更新内存页（脏页）
  │                                      写 redo log，状态 = prepare     ← 阶段一
  │ 3. 写 binlog ──▶ binlog 刷盘
  │ 4. 提交 ──────────────────────────▶ redo log 状态 = commit           ← 阶段二
```

**为什么要两阶段？** redo log 决定主库自己恢复出什么数据，binlog 决定从库和备份恢复出什么数据，两者必须一致：

| 崩溃时刻 | 恢复时的判断 | 结果 |
|---|---|---|
| redo prepare 之后、binlog 写入之前 | binlog 里没有该事务 | 回滚，主从都没有 |
| binlog 写完、redo commit 之前 | redo 是 prepare，但 binlog 完整（用 XID 关联） | 提交，主从都有 |

若不用两阶段（先写完 redo 再写 binlog，中间崩溃），主库有数据、从库没有，主从永久不一致。

刷盘参数「双 1」：`innodb_flush_log_at_trx_commit=1`（每次提交 redo 刷盘）+ `sync_binlog=1`（每次提交 binlog 刷盘），是金融/订单类业务的默认要求。

### 4.2 隔离级别与并发问题

| 并发问题 | 现象 |
|---|---|
| 脏读 | 读到别的事务**未提交**的数据 |
| 不可重复读 | 同一事务内两次读同一行，值变了（别人 UPDATE 并提交） |
| 幻读 | 同一事务内两次范围查询，行数变了（别人 INSERT 并提交） |

| 隔离级别 | 脏读 | 不可重复读 | 幻读 | 实现 |
|---|---|---|---|---|
| READ UNCOMMITTED | 可能 | 可能 | 可能 | 直接读最新数据 |
| READ COMMITTED（RC） | ✘ | 可能 | 可能 | 每次 SELECT 生成新 ReadView |
| REPEATABLE READ（RR，MySQL 默认） | ✘ | ✘ | 大部分避免 | 事务首次 SELECT 生成 ReadView 并复用；当前读加临键锁 |
| SERIALIZABLE | ✘ | ✘ | ✘ | 读也加锁 |

> 很多互联网公司把隔离级别改为 **RC**：没有间隙锁，死锁更少、并发更高；binlog 用 ROW 格式即可保证主从一致。理解两者差异比记住默认值更重要。

### 4.3 MVCC 原理

MVCC（多版本并发控制）让**读不加锁、读写不冲突**。类比前端：Immer/Redux 的不可变数据——每次修改产生新版本，旧引用仍能读到旧快照。

#### 4.3.1 隐藏列与版本链

每行有两个关键隐藏列：

- `DB_TRX_ID`：最后一次修改该行的事务 ID；
- `DB_ROLL_PTR`：回滚指针，指向 undo log 中的上一个版本；
- （无主键时还有 `DB_ROW_ID`）

```
聚簇索引中的当前行
┌─────────┬───────┬────────────┬─────────────┐
│ id=1    │ stock=7│ trx_id=300 │ roll_ptr ───┼──┐
└─────────┴───────┴────────────┴─────────────┘  │
                                                ▼  undo log
                                  ┌───────┬────────────┬──────────┐
                                  │stock=8│ trx_id=200 │ roll_ptr ┼──┐
                                  └───────┴────────────┴──────────┘  │
                                                                     ▼
                                                     ┌────────┬────────────┬──────┐
                                                     │stock=10│ trx_id=100 │ NULL │
                                                     └────────┴────────────┴──────┘
```

#### 4.3.2 ReadView 与可见性判断

快照读（普通 `SELECT`）时生成 ReadView，包含：

| 字段 | 含义 |
|---|---|
| `m_ids` | 生成时所有**活跃**（未提交）事务 ID 列表 |
| `min_trx_id` | `m_ids` 中最小值 |
| `max_trx_id` | 生成时系统将分配的下一个事务 ID |
| `creator_trx_id` | 创建该 ReadView 的事务自身 ID |

沿版本链从新到旧，对每个版本的 `trx_id` 判断：

```
trx_id == creator_trx_id   → 可见（自己改的）
trx_id <  min_trx_id       → 可见（生成 ReadView 前已提交）
trx_id >= max_trx_id       → 不可见（ReadView 之后才开启的事务）
min ≤ trx_id < max:
    trx_id ∈ m_ids         → 不可见（还没提交）
    trx_id ∉ m_ids         → 可见（已提交）
不可见 → 顺着 roll_ptr 找上一个版本，继续判断
```

- **RC**：每条 SELECT 都新建 ReadView → 能看到别人新提交的 → 不可重复读；
- **RR**：事务第一条 SELECT 建 ReadView，之后复用 → 可重复读。

#### 4.3.3 快照读 vs 当前读：RR 真的没有幻读吗？

- **快照读**：普通 `SELECT`，读版本链，不加锁；
- **当前读**：`SELECT ... FOR UPDATE`、`UPDATE`、`DELETE`、`INSERT`，读最新已提交版本并加锁。

RR 下快照读靠 MVCC 防幻读，当前读靠临键锁防幻读。但混用时仍会「幻」：

```
事务 A：SELECT * FROM t_product WHERE id = 99;   -- 快照读，空
事务 B：INSERT id=99 并提交
事务 A：UPDATE t_product SET stock = 0 WHERE id = 99;  -- 当前读，更新成功！
事务 A：SELECT * FROM t_product WHERE id = 99;   -- 这一行的 trx_id 变成 A 自己，可见 → 幻读
```

这就是为什么「先查再改」的业务逻辑，要么用当前读加锁，要么用条件更新（6.5 节的扣库存写法）。

### 4.4 锁

#### 4.4.1 锁的分类

```
全局锁   FLUSH TABLES WITH READ LOCK（全库备份）
表级锁   表锁 · 元数据锁 MDL · 意向锁 IS/IX · 自增锁
行级锁   Record Lock（记录锁）· Gap Lock（间隙锁）· Next-Key Lock（临键锁 = 记录 + 前面的间隙）
         · 插入意向锁
```

| 锁 | 锁住什么 | 作用 |
|---|---|---|
| 记录锁 | 索引上的某条记录 | — |
| 间隙锁 | 两条索引记录之间的开区间，如 (10, 20) | 阻止其他事务往间隙里插入 → 防幻读；**间隙锁之间不互斥** |
| 临键锁 | 左开右闭区间，如 (10, 20] | RR 下加锁的基本单位 |
| 意向锁 IS/IX | 表级标记：「表里有行被加了 S/X 锁」 | 加表锁时不必逐行检查，看意向锁即可；意向锁之间互相兼容 |

**行锁加在索引上**：如果 `WHERE` 条件没走索引，就会扫全表并给每一行加锁——效果等同锁表。这是「UPDATE 没加索引导致全站卡死」的经典事故。

#### 4.4.2 RR 下的加锁规则（简化版）

以 `t_product` 中 `id` 有 5、10、20 三行为例：

| 语句 | 加锁 |
|---|---|
| `... WHERE id = 10 FOR UPDATE`（唯一索引等值命中） | 退化为记录锁：只锁 10 |
| `... WHERE id = 15 FOR UPDATE`（唯一索引等值未命中） | 退化为间隙锁：(10, 20) |
| `... WHERE id >= 10 AND id < 15 FOR UPDATE` | 记录锁 10 + 间隙 (10, 20) |
| 非唯一索引等值 `WHERE user_id = 1001` | 命中的记录的临键锁 + 后面的间隙锁 + 对应主键记录锁 |
| 无索引条件 | 全表每行临键锁 |

RC 级别下基本只有记录锁（外键和唯一性检查除外），这就是 RC 死锁少的原因。

#### 4.4.3 死锁案例与排查

**案例一：加锁顺序相反**（下单扣多个商品库存时）

```
时间  事务 A（买商品 1 和 2）              事务 B（买商品 2 和 1）
 t1   UPDATE product id=1  锁住 1
 t2                                        UPDATE product id=2  锁住 2
 t3   UPDATE product id=2  等待 B 释放 2
 t4                                        UPDATE product id=1  等待 A 释放 1 → 死锁
```

解法：**按 productId 升序扣减库存**，所有事务加锁顺序一致就不会形成环（mini-mall 下单就这么做）。

**案例二：间隙锁 + 插入意向锁**

```
两个事务都执行：SELECT ... WHERE id = 15 FOR UPDATE（不存在）→ 都拿到间隙锁 (10,20)（间隙锁不互斥）
然后都 INSERT id=15 → 插入意向锁与对方的间隙锁冲突，互相等待 → 死锁
```

这是「先查不存在再插入」写法的经典死锁。解法：用唯一索引 + 直接 INSERT，捕获 `DuplicateKeyException`；或改用 RC。

**排查步骤**：

1. InnoDB 会自动检测死锁并回滚代价小的事务，应用报 `Deadlock found when trying to get lock`；
2. `SHOW ENGINE INNODB STATUS\G` 看 `LATEST DETECTED DEADLOCK`：两个事务各自持有什么锁（`HOLDS THE LOCK`）、等待什么锁（`WAITING FOR THIS LOCK`）、执行的 SQL；
3. 开启 `innodb_print_all_deadlocks=ON` 把所有死锁写入错误日志；
4. 实时锁等待：`performance_schema.data_locks`、`data_lock_waits`（8.0），配合 `information_schema.innodb_trx` 找长事务；
5. 根据 SQL 反推索引与加锁范围，调整加锁顺序、缩小事务、补索引。

### 4.5 慢 SQL 优化实战

先开启慢查询日志 `slow_query_log=ON, long_query_time=1`，再用 `pt-query-digest` 聚合，挑「总耗时最高」的而不是「单次最慢」的先优化。

#### 4.5.1 深分页

```sql
-- 慢：要先扫描并丢弃 100 万行（每行还要回表），再取 10 行
SELECT * FROM t_order WHERE user_id = 1001 ORDER BY create_time DESC LIMIT 1000000, 10;
```

| 方案 | SQL | 说明 |
|---|---|---|
| 延迟关联 | 先在覆盖索引里找出 10 个 id，再 join 回表 | 扫描仍在，但扫的是轻量的索引，且只回表 10 次 |
| 游标分页（推荐） | `WHERE user_id = ? AND (create_time, id) < (?, ?)` + `LIMIT 10` | 每页都是 O(10)；不能跳页，适合 App 下拉加载 |
| 业务限制 | 最多翻 100 页 | 电商搜索都这样做 |

```sql
-- 延迟关联
SELECT o.* FROM t_order o
JOIN (SELECT id FROM t_order WHERE user_id = 1001
      ORDER BY create_time DESC LIMIT 1000000, 10) t ON o.id = t.id;

-- 游标分页（上一页最后一条的 create_time 和 id 作为游标）
SELECT * FROM t_order
WHERE user_id = 1001
  AND (create_time < '2026-11-01 10:00:00' OR (create_time = '2026-11-01 10:00:00' AND id < 1863))
ORDER BY create_time DESC, id DESC LIMIT 10;
```

前端视角：游标分页就是 GraphQL Relay 的 `after: cursor`，或无限滚动列表的 `nextCursor`。

#### 4.5.2 count 优化

| 写法 | 结论 |
|---|---|
| `COUNT(*)` / `COUNT(1)` | 等价，InnoDB 会选最小的二级索引来扫；推荐 `COUNT(*)` |
| `COUNT(id)` | 要取出 id 判断非空，略慢 |
| `COUNT(col)` | 只统计 col 非 NULL 的行，**语义不同** |

大表 count 本质上无法 O(1)，方案：分页列表不显示精确总数（「1000+」）；用 Redis 计数器 / 统计表异步维护；按条件 count 时保证走覆盖索引；MP 分页可关闭 count（`page.setSearchCount(false)`）。

#### 4.5.3 join 优化

- MySQL join 是嵌套循环：**小表（过滤后的结果集小）驱动大表**，被驱动表的 join 字段**必须有索引**（走 Index Nested-Loop），否则是 Block Nested-Loop / 8.0.18+ 的 Hash Join，仍要大量扫描；
- 阿里规范：超过三个表禁止 join；高并发核心链路，常改为「分别单表查询 + 内存组装」，便于缓存和分库分表；
- 两个字段类型、字符集必须一致，否则隐式转换导致索引失效。

#### 4.5.4 批量写

| 方式 | 性能 | 说明 |
|---|---|---|
| 循环单条 INSERT | 最差 | N 次网络往返 + N 次事务提交 |
| 一个事务里循环 | 好一些 | 只提交一次 |
| `INSERT ... VALUES (...),(...)` 多值插入 | 最好 | 单条 SQL 控制在 500～1000 行，避免超过 `max_allowed_packet` |
| JDBC batch + `rewriteBatchedStatements=true` | 好 | MySQL 驱动把批量语句改写为多值插入；**不开这个参数，batch 基本无效** |

批量更新/删除同样要分批（如每次 1000 条，按主键范围），避免一个大事务持锁过久、undo 膨胀、主从延迟。

---

## 5. 持久层框架

### 5.1 JDBC → MyBatis → MyBatis-Plus 演进

| 层次 | Java | Node 对应物 | 你要写什么 |
|---|---|---|---|
| 驱动 | JDBC | `mysql2` | 连接、PreparedStatement、手动映射 ResultSet |
| SQL 映射 | MyBatis | `knex` + 手写映射 | SQL 写在 XML/注解，框架负责参数绑定和结果映射 |
| 增强 | MyBatis-Plus | Prisma 的 CRUD + 原生 SQL 兜底 | 单表 CRUD 零 SQL；复杂查询仍写 XML |
| 全 ORM | JPA/Hibernate | TypeORM | 对象关系映射、自动生成 SQL；SQL 不透明，国内互联网用得少 |

同一个「按用户查订单」在几种写法下：

```ts
// TypeScript + Prisma
const orders = await prisma.order.findMany({
  where: { userId: 1001n, status: 1 },
  orderBy: { createTime: 'desc' },
  take: 10,
});
```

```java
// 1) 原生 JDBC：所有事情都要自己做
/**
 * 用 JDBC 查询用户已支付订单的订单号。
 *
 * @param dataSource 数据源（连接池）
 * @param userId     用户 ID
 * @return 订单号列表
 * @throws SQLException 数据库异常（受检异常，必须处理）
 */
public List<String> listOrderNos(DataSource dataSource, long userId) throws SQLException {
    String sql = "SELECT order_no FROM t_order WHERE user_id = ? AND status = ? "
            + "ORDER BY create_time DESC LIMIT 10";
    List<String> result = new ArrayList<>();
    // try-with-resources 自动关闭连接（归还连接池）、语句、结果集
    try (Connection conn = dataSource.getConnection();
         PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setLong(1, userId);   // 参数占位，防 SQL 注入
        ps.setInt(2, 1);
        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                result.add(rs.getString("order_no")); // 手动映射每一列
            }
        }
    }
    return result;
}

// 2) MyBatis-Plus：Lambda 条件构造，字段引用有编译期检查
List<OrderPO> orders = orderMapper.selectList(new LambdaQueryWrapper<OrderPO>()
        .eq(OrderPO::getUserId, 1001L)
        .eq(OrderPO::getStatus, OrderStatusEnum.PAID.getCode())
        .orderByDesc(OrderPO::getCreateTime)
        .last("LIMIT 10"));
```

为什么国内偏爱 MyBatis 系而不是 JPA？**SQL 完全可见、可控**：DBA 能评审、能针对性优化索引、出问题能直接 EXPLAIN。代价是要多写 SQL，MP 补上了单表 CRUD 这一块。

### 5.2 连接池 HikariCP

和前端的 HTTP keep-alive 一个道理：TCP 握手 + MySQL 鉴权很贵，所以复用连接。Spring Boot 默认 HikariCP。

```yaml
spring:
  datasource:
    url: jdbc:mysql://127.0.0.1:3306/mini_mall?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai&rewriteBatchedStatements=true
    username: mall
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 20        # 最大连接数，不是越大越好
      minimum-idle: 20             # 官方建议与最大值相同，作为固定大小池
      connection-timeout: 3000     # 从池里拿连接的最长等待（ms），超时抛异常，快速失败
      idle-timeout: 600000         # 空闲连接回收时间（minimum-idle < max 时才生效）
      max-lifetime: 1800000        # 连接最大存活，须小于 MySQL wait_timeout，避免拿到已被服务端断开的连接
      keepalive-time: 60000        # 定期探活
      leak-detection-threshold: 10000  # 连接借出超过 10s 未归还则打印堆栈，排查连接泄漏/长事务
```

**池大小怎么定？** HikariCP 官方经验公式：`连接数 = CPU 核数 × 2 + 有效磁盘数`。数据库同时能真正干活的线程有限，连接太多只会增加上下文切换和锁竞争。还要算总量：`应用实例数 × maximum-pool-size` 不能超过 MySQL `max_connections`。

**连接池耗尽**的典型原因：事务里调了慢的 HTTP 接口（连接被长期占用）、慢 SQL、连接泄漏。现象是大量 `Connection is not available, request timed out after 3000ms`。

### 5.3 MyBatis 核心

#### 5.3.1 Mapper 接口 + XML

Mapper 是一个**接口**，没有实现类：MyBatis 启动时用 JDK 动态代理生成实现，方法调用时按「接口全限定名 + 方法名」找到 XML 里对应的 SQL。

```java
package com.example.mall.dao.mapper;

/**
 * 订单 Mapper：继承 BaseMapper 获得单表 CRUD，复杂 SQL 写在 OrderMapper.xml。
 */
@Mapper
public interface OrderMapper extends BaseMapper<OrderPO> {

    /**
     * 按订单号查询订单（演示 XML 写法）。
     *
     * @param orderNo 订单号
     * @return 订单实体，不存在返回 null
     */
    OrderPO selectByOrderNo(@Param("orderNo") String orderNo);
}
```

```xml
<!-- resources/mapper/OrderMapper.xml，namespace 必须是接口全限定名 -->
<mapper namespace="com.example.mall.dao.mapper.OrderMapper">
    <select id="selectByOrderNo" resultType="com.example.mall.model.po.OrderPO">
        SELECT id, order_no, user_id, total_amount, status, create_time, update_time
        FROM t_order
        WHERE order_no = #{orderNo}
    </select>
</mapper>
```

#### 5.3.2 `#{}` vs `${}` 与 SQL 注入

| | `#{}` | `${}` |
|---|---|---|
| 处理方式 | 预编译占位符 `?`，参数由驱动转义绑定 | 字符串直接拼接进 SQL |
| 安全 | 安全 | **SQL 注入风险** |
| 用途 | 所有值参数 | 只用于表名、列名、`ORDER BY` 字段等无法用 `?` 的位置 |

```xml
<!-- 危险：前端传 sortField = "create_time; DROP TABLE t_order" -->
ORDER BY ${sortField}
```

用 `${}` 时**必须白名单校验**（前端传枚举，后端映射为列名），这和前端拼 `innerHTML` 防 XSS 是同一类问题：永远不要把用户输入当代码执行。

#### 5.3.3 动态 SQL

```xml
<select id="selectByCondition" resultMap="OrderResultMap">
    SELECT id, order_no, user_id, total_amount, status, create_time
    FROM t_order
    <where>                                   <!-- 自动处理第一个 AND，没条件时不输出 WHERE -->
        <if test="userId != null">AND user_id = #{userId}</if>
        <if test="status != null">AND status = #{status}</if>
        <if test="statusList != null and statusList.size() > 0">
            AND status IN
            <foreach collection="statusList" item="s" open="(" separator="," close=")">#{s}</foreach>
        </if>
    </where>
    ORDER BY create_time DESC
</select>
```

类比：这就是 JSX 里的 `{cond && <Item/>}` 和 `list.map(...)`，只是渲染的是 SQL。

#### 5.3.4 resultMap

列名与属性不一致、或需要一对多嵌套时用 resultMap（开启 `map-underscore-to-camel-case` 后简单场景无需配置）：

```xml
<resultMap id="OrderDetailMap" type="com.example.mall.model.po.OrderDetailPO">
    <id column="id" property="id"/>
    <result column="order_no" property="orderNo"/>
    <!-- 一对多：订单 → 明细；注意 N+1 与笛卡尔积问题，大列表慎用 -->
    <collection property="items" ofType="com.example.mall.model.po.OrderItemPO">
        <id column="item_id" property="id"/>
        <result column="product_name" property="productName"/>
    </collection>
</resultMap>
```

> 实践建议：mini-mall 不用嵌套映射，订单与明细分两次单表查询再由转换器组装，SQL 更简单、更易缓存、方便分库。

#### 5.3.5 一级缓存与二级缓存

| | 一级缓存 | 二级缓存 |
|---|---|---|
| 范围 | 同一个 SqlSession | 同一个 Mapper namespace，跨 SqlSession |
| 默认 | 开启 | 关闭 |
| 在 Spring 中 | **非事务方法里每次调用都是新 SqlSession，基本不生效**；同一事务内相同查询会命中 | — |
| 建议 | 了解即可；注意事务内「先查、别人改了、再查」仍拿到旧对象 | **不要开**：多实例部署下各进程缓存不一致；用 Redis（第 9 章） |

### 5.4 MyBatis-Plus

依赖（Spring Boot 3 需用 boot3 专用 starter；3.5.9 起分页插件拆到 jsqlparser 模块）：

```xml
<dependency>
    <groupId>com.baomidou</groupId>
    <artifactId>mybatis-plus-spring-boot3-starter</artifactId>
    <version>3.5.9</version>
</dependency>
<dependency>
    <groupId>com.baomidou</groupId>
    <artifactId>mybatis-plus-jsqlparser</artifactId>
    <version>3.5.9</version>
</dependency>
```

#### 5.4.1 BaseMapper

继承 `BaseMapper<T>` 即获得：`insert`、`deleteById`、`updateById`、`selectById`、`selectByIds`（3.5.8 前叫 `selectBatchIds`）、`selectOne`、`selectList`、`selectPage`、`selectCount`、`update(entity, wrapper)` 等。注意：`updateById` **只更新非 null 字段**（默认策略 `NOT_NULL`），想把字段置 null 要用 `LambdaUpdateWrapper.set`。

#### 5.4.2 LambdaQueryWrapper

```java
// 字符串写法：列名写错只能运行时发现
new QueryWrapper<OrderPO>().eq("user_id", 1001L);

// Lambda 写法（推荐）：方法引用解析出列名，重构安全
new LambdaQueryWrapper<OrderPO>()
        .eq(OrderPO::getUserId, 1001L)
        .eq(status != null, OrderPO::getStatus, status)   // 第一个参数为 false 时不拼接该条件
        .ge(OrderPO::getCreateTime, startTime)
        .select(OrderPO::getId, OrderPO::getOrderNo)       // 只查需要的列
        .orderByDesc(OrderPO::getCreateTime);
```

带 `condition` 参数的重载就是动态 SQL 的 Java 版，类似前端 `{...(status && { status })}` 构造查询参数。

#### 5.4.3 分页插件、自动填充、乐观锁插件配置

```java
package com.example.mall.config;

/**
 * MyBatis-Plus 插件配置：分页、乐观锁、防全表更新删除。
 */
@Configuration
public class MybatisPlusConfig {

    /**
     * 注册 MyBatis-Plus 拦截器链。
     *
     * @return 拦截器，内部插件按添加顺序执行
     */
    @Bean
    public MybatisPlusInterceptor mybatisPlusInterceptor() {
        MybatisPlusInterceptor interceptor = new MybatisPlusInterceptor();
        // 乐观锁：updateById 时自动追加 WHERE version = ? 并 SET version = version + 1
        interceptor.addInnerInterceptor(new OptimisticLockerInnerInterceptor());
        // 防止不带 WHERE 的全表 UPDATE/DELETE
        interceptor.addInnerInterceptor(new BlockAttackInnerInterceptor());
        // 分页：自动改写 LIMIT 并执行 count；分页插件建议放最后
        PaginationInnerInterceptor pagination = new PaginationInnerInterceptor(DbType.MYSQL);
        pagination.setMaxLimit(500L); // 单页上限，防止前端传 pageSize=100000
        interceptor.addInnerInterceptor(pagination);
        return interceptor;
    }
}
```

```java
package com.example.mall.config;

/**
 * 公共字段自动填充：插入时填 createTime/updateTime，更新时填 updateTime。
 */
@Component
public class MallMetaObjectHandler implements MetaObjectHandler {

    /**
     * 插入时填充。
     *
     * @param metaObject 待插入实体的元对象
     */
    @Override
    public void insertFill(MetaObject metaObject) {
        LocalDateTime now = LocalDateTime.now();
        // strictInsertFill：只在字段为 null 且标注了 FieldFill.INSERT 系列时填充
        this.strictInsertFill(metaObject, "createTime", LocalDateTime.class, now);
        this.strictInsertFill(metaObject, "updateTime", LocalDateTime.class, now);
    }

    /**
     * 更新时填充。
     *
     * @param metaObject 待更新实体的元对象
     */
    @Override
    public void updateFill(MetaObject metaObject) {
        this.strictUpdateFill(metaObject, "updateTime", LocalDateTime.class, LocalDateTime.now());
    }
}
```

> 自动填充只对「传实体」的方法生效（`insert`、`updateById`、`update(entity, wrapper)`）；XML 手写 SQL 和 `update(null, wrapper)` 不会填，所以表上的 `ON UPDATE CURRENT_TIMESTAMP` 是兜底。

#### 5.4.4 乐观锁 @Version 与逻辑删除 @TableLogic

```java
@Version                 // 乐观锁版本号
private Integer version;

@TableLogic              // 逻辑删除：deleteById 变为 UPDATE ... SET deleted = 1，查询自动加 deleted = 0
private Integer deleted;
```

`@Version` 的工作方式：先 `selectById` 拿到 version=3，再 `updateById` 时生成 `UPDATE ... SET ..., version = 4 WHERE id = ? AND version = 3`，返回影响行数 0 即冲突。它要求「先读后写」，扣库存这种高并发场景更推荐 6.5 节的单条条件更新。

#### 5.4.5 批量操作

| 方法 | 实际行为 |
|---|---|
| `IService.saveBatch(list, 1000)` | JDBC batch，每 1000 条 flush；配合 `rewriteBatchedStatements=true` 才真正快 |
| `BaseMapper.insert(Collection)`（3.5.7+） | 同样走 batch |
| XML `<foreach>` 拼多值 INSERT | 最快，但要自己控制每批大小 |

mini-mall 下单写订单明细就用 `orderItemMapper.insert(items)`（一单明细通常不多）。

### 5.5 DAO 层封装规范

为什么不让编排层直接用 Mapper / Wrapper？

| 问题 | 后果 |
|---|---|
| Wrapper 散落在各个 Service 中 | 同一个「查用户订单」条件写了 5 遍，加个 `deleted` 条件要改 5 处 |
| 业务层知道列名 | 表结构变化影响面不可控 |
| 无法统一加限制 | 有人忘了 `LIMIT`，一次查出 100 万行 |

规范：

1. **DAO 是第四层能力单元**：一个 DAO 对应一张表，封装该表的全部读写；
2. **DAO 不写业务逻辑**：不判断订单状态是否允许取消、不抛业务异常，只返回数据或影响行数；
3. **查询条件构建抽成独立私有方法**：`buildXxxWrapper(...)`，列表和 count 复用同一个条件；
4. **方法名表达意图**：`getByOrderNo`、`pageByUser`、`deductStock`，而不是暴露 `selectList(wrapper)`；
5. **入参是明确类型**：不传 `Map<String, Object>`。

---

## 6. mini-mall 实战

### 6.1 四张表完整 DDL

```sql
-- 用户表
CREATE TABLE t_user (
    id           BIGINT UNSIGNED NOT NULL COMMENT '主键，雪花 ID',
    username     VARCHAR(64)     NOT NULL COMMENT '用户名',
    phone        VARCHAR(20)     NOT NULL DEFAULT '' COMMENT '手机号',
    deleted      TINYINT         NOT NULL DEFAULT 0 COMMENT '逻辑删除：0 正常，1 已删除',
    create_time  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_username (username),
    KEY idx_phone (phone)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '用户表';

-- 商品表
CREATE TABLE t_product (
    id           BIGINT UNSIGNED NOT NULL COMMENT '主键，雪花 ID',
    name         VARCHAR(128)    NOT NULL COMMENT '商品名称',
    price        DECIMAL(10, 2)  NOT NULL COMMENT '售价（元）',
    stock        INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '可售库存',
    version      INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '乐观锁版本号',
    deleted      TINYINT         NOT NULL DEFAULT 0 COMMENT '逻辑删除：0 正常，1 已删除',
    create_time  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '商品表';

-- 订单表
CREATE TABLE t_order (
    id            BIGINT UNSIGNED NOT NULL COMMENT '主键，雪花 ID',
    order_no      VARCHAR(32)     NOT NULL COMMENT '订单号，对外展示',
    user_id       BIGINT UNSIGNED NOT NULL COMMENT '下单用户 ID',
    total_amount  DECIMAL(10, 2)  NOT NULL COMMENT '订单总金额（元）',
    status        TINYINT         NOT NULL DEFAULT 0 COMMENT '订单状态：0 待支付，1 已支付，2 已取消，3 已发货，4 已完成',
    create_time   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_order_no (order_no),
    KEY idx_user_create_time (user_id, create_time),
    KEY idx_status_create_time (status, create_time)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '订单表';

-- 订单明细表
CREATE TABLE t_order_item (
    id            BIGINT UNSIGNED NOT NULL COMMENT '主键，雪花 ID',
    order_id      BIGINT UNSIGNED NOT NULL COMMENT '订单 ID',
    product_id    BIGINT UNSIGNED NOT NULL COMMENT '商品 ID',
    product_name  VARCHAR(128)    NOT NULL COMMENT '商品名称快照（下单时）',
    price         DECIMAL(10, 2)  NOT NULL COMMENT '成交单价快照（元）',
    quantity      INT UNSIGNED    NOT NULL COMMENT '购买数量',
    create_time   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_order_id (order_id),
    KEY idx_product_id (product_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '订单明细表';
```

索引设计说明：

| 表 | 索引 | 服务的查询 | 设计理由 |
|---|---|---|---|
| t_user | `uk_username` | 登录、注册查重 | 唯一约束由数据库兜底，比应用层先查再插更可靠 |
| t_user | `idx_phone` | 按手机号查用户 | — |
| t_product | 仅主键 | 详情、扣库存都按 id | 商品检索走搜索引擎，不在 MySQL 建 name 索引 |
| t_order | `uk_order_no` | 按订单号查单、支付回调 | 唯一约束同时防重复下单落库 |
| t_order | `idx_user_create_time` | 「我的订单」按时间倒序分页 | user_id 等值 + create_time 排序 → 免 filesort；也服务于游标分页 |
| t_order | `idx_status_create_time` | 超时取消任务：`status = 0 AND create_time < ?` | 等值列在前、范围列在后 |
| t_order_item | `idx_order_id` | 查订单明细 | 无外键，靠普通索引支撑关联查询 |
| t_order_item | `idx_product_id` | 按商品统计销量、售后 | — |

为什么「我的订单」不把 status 放进索引（`user_id, status, create_time`）？列表页默认「全部订单」不带 status，若 status 放中间，`ORDER BY create_time` 就无法利用索引排序。带 status 筛选时，单个用户订单量不大，`idx_user_create_time` + 索引下推足够。**索引为高频查询服务，而不是为每个条件组合服务**。

> 明细表的 `product_name`、`price` 是**快照**：商品改名、改价后历史订单不能变。这是业务正确性问题，不是冗余。

### 6.2 实体 PO

```java
package com.example.mall.model.po;

/**
 * 商品表 t_product 实体。
 */
@Data
@TableName("t_product")
public class ProductPO {

    /** 主键，雪花算法生成 */
    @TableId(type = IdType.ASSIGN_ID)
    private Long id;

    /** 商品名称 */
    private String name;

    /** 售价（元），对应 DECIMAL(10,2) */
    private BigDecimal price;

    /** 可售库存 */
    private Integer stock;

    /** 乐观锁版本号 */
    @Version
    private Integer version;

    /** 逻辑删除标记：0 正常，1 已删除 */
    @TableLogic
    private Integer deleted;

    /** 创建时间，插入时自动填充 */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createTime;

    /** 更新时间，插入和更新时自动填充 */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updateTime;
}
```

```java
package com.example.mall.model.po;

/**
 * 订单表 t_order 实体。
 */
@Data
@TableName("t_order")
public class OrderPO {

    /** 主键，雪花算法生成 */
    @TableId(type = IdType.ASSIGN_ID)
    private Long id;

    /** 订单号，对外展示，全局唯一 */
    private String orderNo;

    /** 下单用户 ID */
    private Long userId;

    /** 订单总金额（元） */
    private BigDecimal totalAmount;

    /** 订单状态，取值见 OrderStatusEnum#getCode */
    private Integer status;

    /** 创建时间 */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createTime;

    /** 更新时间 */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updateTime;
}
```

`OrderItemPO` 同理（字段：id、orderId、productId、productName、price、quantity、createTime），不再赘述。

> PO 的 `status` 用 `Integer` 而不是 `OrderStatusEnum`：PO 是表结构的忠实映射，枚举转换放在转换器（第五层）或 VO 中，避免未知编码导致反序列化失败。MP 也支持 `@EnumValue` 直接映射枚举，团队统一即可。

### 6.3 Mapper

```java
package com.example.mall.dao.mapper;

/**
 * 商品 Mapper：单表 CRUD 继承自 BaseMapper，扣库存使用自定义条件更新。
 */
@Mapper
public interface ProductMapper extends BaseMapper<ProductPO> {

    /**
     * 乐观锁扣减库存：版本号匹配且库存充足才扣减。
     *
     * @param id       商品 ID
     * @param quantity 扣减数量
     * @param version  调用方读到的版本号
     * @return 影响行数：1 成功，0 版本冲突或库存不足
     */
    @Update("UPDATE t_product SET stock = stock - #{quantity}, version = version + 1 "
            + "WHERE id = #{id} AND stock >= #{quantity} AND version = #{version} AND deleted = 0")
    int deductStockWithVersion(@Param("id") Long id,
                               @Param("quantity") int quantity,
                               @Param("version") int version);

    /**
     * 条件扣减库存：不依赖版本号，库存充足即扣减（推荐写法）。
     *
     * @param id       商品 ID
     * @param quantity 扣减数量
     * @return 影响行数：1 成功，0 库存不足或商品不存在
     */
    @Update("UPDATE t_product SET stock = stock - #{quantity}, version = version + 1 "
            + "WHERE id = #{id} AND stock >= #{quantity} AND deleted = 0")
    int deductStock(@Param("id") Long id, @Param("quantity") int quantity);

    /**
     * 回补库存（订单取消时）。
     *
     * @param id       商品 ID
     * @param quantity 回补数量
     * @return 影响行数
     */
    @Update("UPDATE t_product SET stock = stock + #{quantity}, version = version + 1 "
            + "WHERE id = #{id} AND deleted = 0")
    int restoreStock(@Param("id") Long id, @Param("quantity") int quantity);
}
```

```java
package com.example.mall.dao.mapper;

/**
 * 订单 Mapper。
 */
@Mapper
public interface OrderMapper extends BaseMapper<OrderPO> {

    /**
     * 延迟关联分页：先在覆盖索引 idx_user_create_time 上定位主键，再回表取整行。
     *
     * @param userId 用户 ID
     * @param offset 偏移量
     * @param limit  条数
     * @return 当前页订单，按创建时间倒序
     */
    @Select("SELECT o.* FROM t_order o JOIN ("
            + "  SELECT id FROM t_order WHERE user_id = #{userId}"
            + "  ORDER BY create_time DESC, id DESC LIMIT #{offset}, #{limit}"
            + ") t ON o.id = t.id ORDER BY o.create_time DESC, o.id DESC")
    List<OrderPO> selectPageByUserDeferredJoin(@Param("userId") Long userId,
                                               @Param("offset") long offset,
                                               @Param("limit") int limit);
}
```

> 注：InnoDB 二级索引叶子天然包含主键，`idx_user_create_time` 实际排序为 `(user_id, create_time, id)`，所以 `ORDER BY create_time DESC, id DESC` 同样可以走索引免排序。加上 `id` 作为第二排序键，是为了保证同一秒内多个订单的**顺序稳定**，否则翻页可能重复或漏数据。

### 6.4 DAO 封装

先定义分页查询入参（DTO，第 07 章 Controller 接收后传下来）：

```java
package com.example.mall.model.dto;

/**
 * 「我的订单」分页查询入参。
 *
 * @param userId   当前登录用户 ID（由拦截器注入，不信任前端传值）
 * @param status   订单状态筛选，取值见 OrderStatusEnum#getCode；null 表示全部
 * @param pageNo   页码，从 1 开始
 * @param pageSize 每页条数
 */
public record OrderPageQueryDTO(Long userId, Integer status, int pageNo, int pageSize) {
}
```

```java
package com.example.mall.dao;

/**
 * 订单表 t_order 能力单元：只负责订单表的读写，不包含业务判断。
 */
@Repository
@RequiredArgsConstructor
public class OrderDao {

    private final OrderMapper orderMapper;

    /**
     * 新增订单。
     *
     * @param order 订单实体，id 为空时由 MP 生成雪花 ID
     * @return 影响行数
     */
    public int insert(OrderPO order) {
        return orderMapper.insert(order);
    }

    /**
     * 按订单号查询。
     *
     * @param orderNo 订单号
     * @return 订单，不存在返回 null
     */
    public OrderPO getByOrderNo(String orderNo) {
        return orderMapper.selectOne(new LambdaQueryWrapper<OrderPO>()
                .eq(OrderPO::getOrderNo, orderNo));
    }

    /**
     * 按状态条件更新订单状态（状态机 CAS：只有当前状态匹配才更新）。
     *
     * @param orderId    订单 ID
     * @param fromStatus 期望的当前状态
     * @param toStatus   目标状态
     * @return 影响行数：1 成功，0 状态已变化
     */
    public int updateStatus(Long orderId, int fromStatus, int toStatus) {
        return orderMapper.update(null, new LambdaUpdateWrapper<OrderPO>()
                .set(OrderPO::getStatus, toStatus)
                .eq(OrderPO::getId, orderId)
                .eq(OrderPO::getStatus, fromStatus));
    }

    /**
     * 「我的订单」分页查询（页码分页，适合 PC 端跳页）。
     *
     * @param query 分页查询条件
     * @return MP 分页结果，含总数与当前页数据
     */
    public IPage<OrderPO> pageByUser(OrderPageQueryDTO query) {
        Page<OrderPO> page = Page.of(query.pageNo(), query.pageSize());
        return orderMapper.selectPage(page, buildUserOrderWrapper(query.userId(), query.status()));
    }

    /**
     * 「我的订单」游标分页（适合 App 下拉加载，无深分页问题）。
     *
     * @param userId         用户 ID
     * @param status         状态筛选，null 表示全部
     * @param lastCreateTime 上一页最后一条的创建时间，首页传 null
     * @param lastId         上一页最后一条的 ID，首页传 null
     * @param size           本页条数
     * @return 当前页订单
     */
    public List<OrderPO> listByUserAfterCursor(Long userId, Integer status,
                                               LocalDateTime lastCreateTime, Long lastId, int size) {
        LambdaQueryWrapper<OrderPO> wrapper = buildUserOrderWrapper(userId, status);
        if (lastCreateTime != null && lastId != null) {
            // (create_time, id) < (lastCreateTime, lastId)，拆成 OR 以便优化器使用索引范围扫描
            wrapper.and(w -> w.lt(OrderPO::getCreateTime, lastCreateTime)
                    .or(o -> o.eq(OrderPO::getCreateTime, lastCreateTime).lt(OrderPO::getId, lastId)));
        }
        return orderMapper.selectList(wrapper.last("LIMIT " + size));
    }

    /**
     * 构建「用户订单列表」的公共查询条件，列表查询与分页 count 共用。
     *
     * @param userId 用户 ID，必填
     * @param status 状态筛选，null 不拼接
     * @return 查询条件（已带排序）
     */
    private LambdaQueryWrapper<OrderPO> buildUserOrderWrapper(Long userId, Integer status) {
        return new LambdaQueryWrapper<OrderPO>()
                .eq(OrderPO::getUserId, userId)
                .eq(status != null, OrderPO::getStatus, status)
                .orderByDesc(OrderPO::getCreateTime)
                .orderByDesc(OrderPO::getId);
    }
}
```

> `wrapper.last("LIMIT " + size)` 是字符串拼接，这里 `size` 是 `int` 且已在 Controller 校验范围，安全；**绝不能把字符串类型的用户输入拼进 `last()`**。

```java
package com.example.mall.dao;

/**
 * 商品表 t_product 能力单元。
 */
@Repository
@RequiredArgsConstructor
public class ProductDao {

    private final ProductMapper productMapper;

    /**
     * 按 ID 查询商品（自动过滤已逻辑删除的）。
     *
     * @param productId 商品 ID
     * @return 商品，不存在返回 null
     */
    public ProductPO getById(Long productId) {
        return productMapper.selectById(productId);
    }

    /**
     * 批量查询商品。
     *
     * @param productIds 商品 ID 集合，调用方保证非空
     * @return 商品列表，顺序不保证
     */
    public List<ProductPO> listByIds(Collection<Long> productIds) {
        return productMapper.selectByIds(productIds);
    }

    /**
     * 扣减库存（条件更新，不依赖版本号）。
     *
     * @param productId 商品 ID
     * @param quantity  扣减数量，调用方保证大于 0
     * @return true 扣减成功；false 库存不足或商品不存在
     */
    public boolean deductStock(Long productId, int quantity) {
        return productMapper.deductStock(productId, quantity) == 1;
    }

    /**
     * 扣减库存（乐观锁版本号）。
     *
     * @param productId 商品 ID
     * @param quantity  扣减数量
     * @param version   读取时的版本号
     * @return true 成功；false 版本冲突或库存不足
     */
    public boolean deductStockWithVersion(Long productId, int quantity, int version) {
        return productMapper.deductStockWithVersion(productId, quantity, version) == 1;
    }

    /**
     * 回补库存。
     *
     * @param productId 商品 ID
     * @param quantity  回补数量
     * @return true 成功
     */
    public boolean restoreStock(Long productId, int quantity) {
        return productMapper.restoreStock(productId, quantity) == 1;
    }

    /**
     * 修改商品价格。
     *
     * @param productId 商品 ID
     * @param newPrice  新价格
     * @return true 成功
     */
    public boolean updatePrice(Long productId, BigDecimal newPrice) {
        return productMapper.update(null, new LambdaUpdateWrapper<ProductPO>()
                .set(ProductPO::getPrice, newPrice)
                .eq(ProductPO::getId, productId)) == 1;
    }
}
```

### 6.5 扣库存：乐观锁 vs 条件更新

**错误写法：先查后改（check-then-act）**

```java
// 反例：两个请求同时读到 stock=1，都判断通过，都扣成功 → 超卖
ProductPO p = productDao.getById(id);
if (p.getStock() >= quantity) {
    p.setStock(p.getStock() - quantity);
    productMapper.updateById(p);
}
```

这和前端里「读 state → 计算 → setState(newValue)」在并发异步回调中丢失更新是同一个问题（所以 React 推荐 `setState(prev => prev - 1)`）。数据库层面的「函数式更新」就是 `SET stock = stock - ?`。

**写法 A：版本号乐观锁**

```sql
UPDATE t_product SET stock = stock - ?, version = version + 1
WHERE id = ? AND stock >= ? AND version = ?;
```

**写法 B：条件更新（无 version）**

```sql
UPDATE t_product SET stock = stock - ?
WHERE id = ? AND stock >= ?;
```

| 维度 | A：带 version | B：只带 `stock >= ?` |
|---|---|---|
| 正确性（防超卖） | ✔ | ✔：UPDATE 是当前读，对该行加 X 锁，`stock >= ?` 在锁内判断，原子 |
| 是否需要先查 | 需要先查出 version | 不需要，一条 SQL 完成 |
| 并发冲突时 | 任何别人的修改都会让本次失败（即使库存充足），需要**重试** | 只要库存够就成功，无需重试 |
| 高并发表现 | 失败率高、重试放大流量 | 吞吐更高 |
| 适用场景 | 「读 - 计算 - 写」的复杂更新，写入值依赖读到的多个字段（如改价格同时改促销信息） | 纯数值增减的扣减类操作 |

结论：**扣库存用写法 B**；`version` 字段仍保留，用于后台编辑商品这类「读-改-写」场景防止覆盖他人修改，B 写法顺带 `version + 1` 让其他持有旧版本的编辑感知到变化。

在功能单元中的使用（第 07 章的 `OrderCreateUnit` 内部）：

```java
/**
 * 按商品 ID 升序逐个扣减库存，任一失败抛业务异常触发整个下单事务回滚。
 *
 * @param quantityByProductId key 为商品 ID，value 为购买数量
 */
private void deductStocks(Map<Long, Integer> quantityByProductId) {
    // TreeMap 按 key 升序：所有事务以相同顺序加行锁，避免死锁（见 4.4.3）
    new TreeMap<>(quantityByProductId).forEach((productId, quantity) -> {
        if (!productDao.deductStock(productId, quantity)) {
            throw new BizException(ErrorCode.STOCK_NOT_ENOUGH);
        }
    });
}
```

> 高并发秒杀时，所有请求都更新同一行，行锁排队成为瓶颈。第 9 章会把库存预扣挪到 Redis + Lua，数据库只承接真正成功的请求。

### 6.6 订单分页查询链路

```
GET /api/orders?status=1&pageNo=1&pageSize=10
  │
  ▼
① OrderController.pageMyOrders：校验 pageSize ∈ [1, 50]，从登录上下文取 userId
  │
  ▼
② OrderBizComponent.pageMyOrders(OrderPageQueryDTO)
  │   ├─ OrderDao.pageByUser(query)                 → IPage<OrderPO>
  │   ├─ 收集当前页 orderIds
  │   ├─ OrderItemDao.listByOrderIds(orderIds)      → 一次查出全部明细（避免 N+1）
  │   └─ OrderConverter.toPageVO(page, itemsByOrderId) → PageResult<OrderVO>
  ▼
Result<PageResult<OrderVO>>
```

MP 分页会执行两条 SQL：

```sql
SELECT COUNT(*) FROM t_order WHERE user_id = ? AND status = ?;
SELECT ... FROM t_order WHERE user_id = ? AND status = ? ORDER BY create_time DESC, id DESC LIMIT 0, 10;
```

### 6.7 「我的订单」慢 SQL 优化案例

**背景**：上线半年，某批发商户账号有 120 万订单，进入「我的订单」翻到后面时接口 P99 达 4 秒，同时拖慢整个库。

**第一步：拿到慢 SQL**

```sql
-- 慢日志：Query_time: 3.8  Rows_examined: 1200010
SELECT id, order_no, user_id, total_amount, status, create_time, update_time
FROM t_order WHERE user_id = 88001 ORDER BY create_time DESC LIMIT 600000, 10;
```

**第二步：EXPLAIN**

当时线上只有 `KEY idx_user_id (user_id)`：

| type | key | rows | Extra |
|---|---|---|---|
| ref | idx_user_id | 1180000 | Using filesort |

分析：

1. `idx_user_id` 能定位到该用户的 120 万行，但它们在索引里按 `id` 排序而非 `create_time` → **filesort**，要把 120 万行取出排序；
2. `SELECT` 的列不在索引里，每行都要**回表**；
3. `LIMIT 600000, 10` 要排序后丢弃 60 万行。

**第三步：优化**

| 步骤 | 动作 | 效果 |
|---|---|---|
| 1 | 索引改为 `idx_user_create_time (user_id, create_time)`（加新、观察、再删旧） | 去掉 filesort，按索引顺序读 |
| 2 | 改为延迟关联（`OrderMapper.selectPageByUserDeferredJoin`） | 60 万行只在二级索引上扫，只回表 10 次 |
| 3 | App 端改用游标分页 `listByUserAfterCursor` | 每页稳定 O(10) |
| 4 | count 单独优化：总数超过 1 万时前端显示「1万+」，`page.setSearchCount(false)` + 单独 count 结果缓存 5 分钟 | 消除每页一次全量 count |

```sql
-- t_order：为「我的订单」按时间倒序分页新增联合索引（Online DDL，不锁表）
ALTER TABLE t_order ADD INDEX idx_user_create_time (user_id, create_time), ALGORITHM = INPLACE, LOCK = NONE;
-- 观察一周确认 idx_user_id 无其他查询依赖后：
-- t_order：删除被联合索引覆盖的冗余单列索引（最左前缀已包含 user_id）
ALTER TABLE t_order DROP INDEX idx_user_id;
```

**结果**：

| 方案 | Rows_examined | 耗时 |
|---|---|---|
| 原始 | 1,200,010 | 3.8s |
| 联合索引 | 600,010 | 0.9s |
| 联合索引 + 延迟关联 | 600,010（仅索引） | 0.12s |
| 游标分页 | 10 | 2ms |

**复盘**：索引要和 `ORDER BY` 一起设计；深分页的根因是「先扫再丢」，最终解法是改变交互（游标），这需要和前端/产品一起定——这恰恰是前端转岗工程师的优势。

---

## 7. 常见坑

| 坑 | 后果 | 正确做法 |
|---|---|---|
| 金额用 `double` / `FLOAT` | 对账差几分钱 | `DECIMAL` + `BigDecimal` |
| `new BigDecimal(0.1)` | 得到 0.1000000000000000055… | `new BigDecimal("0.1")` 或 `BigDecimal.valueOf(0.1)` |
| `BigDecimal` 用 `equals` 比较 | `2.0` 与 `2.00` 不相等（scale 不同） | 用 `compareTo` |
| 新增字段 `NOT NULL` 无默认值 | 老代码 INSERT 报错，线上故障 | 加 `DEFAULT` 或允许 NULL |
| UPDATE/DELETE 条件没走索引 | 锁全表 | 先 EXPLAIN；开 `BlockAttackInnerInterceptor` |
| 事务里调用 RPC/HTTP/发 MQ | 长事务：连接被占、锁持有久、undo 膨胀 | 事务只包数据库操作，外部调用放事务外（第 06 章） |
| 先查是否存在再插入 | 并发下重复数据 / 间隙锁死锁 | 唯一索引 + 捕获 `DuplicateKeyException` |
| `${}` 拼接用户输入 | SQL 注入 | `#{}`；`${}` 只用于白名单内的列名 |
| `selectList` 不加限制 | 一次加载百万行 OOM（第 03 章案例） | DAO 统一加 LIMIT 或分批 |
| `updateById` 想把字段改为 null | 不生效（默认忽略 null） | `LambdaUpdateWrapper.set(col, null)` |
| 分页排序字段不唯一 | 翻页数据重复/遗漏 | 追加 `id` 作为第二排序键 |
| JDBC URL 缺 `serverTimezone` | 时间差 8 小时 | 显式配置时区，Java 侧用 `LocalDateTime` |
| 批量插入没开 `rewriteBatchedStatements` | batch 退化为逐条执行 | URL 加上该参数 |
| 逻辑删除 + 唯一索引 | 删除后无法再创建同名数据 | 唯一索引加入删除标识列 |

---

## 8. 高级视角

### 8.1 读写分离与主从延迟

```
            写 ──▶ 主库 ──binlog──▶ 从库1 ◀── 读
应用                       └──────▶ 从库2 ◀── 读

主从复制：主库写 binlog → 从库 IO 线程拉取写入 relay log → SQL 线程（8.0 多线程并行）回放
```

主从延迟的来源：大事务（主库执行 10 秒，从库也要回放 10 秒）、从库机器差、单线程回放、大表 DDL。

**典型问题**：用户下单后立即跳转订单详情，读从库查不到——「我刚下的单不见了」。

| 方案 | 说明 |
|---|---|
| 关键读走主库 | 写后立即读的场景强制路由主库（ShardingSphere 的 `HintManager.setWriteRouteOnly()`） |
| 会话粘滞 | 用户写操作后 N 秒内其读请求走主库 |
| 前端配合 | 下单成功页直接用接口返回的数据渲染，不再立刻回查（前端最熟悉的乐观 UI） |
| 判断延迟 | 监控 `Seconds_Behind_Master`，延迟大时降级读主 |

对于库存、余额这类「读完要据此写」的数据，**永远读主库**。

### 8.2 分库分表

**什么时候需要？** 单表行数到千万级且持续增长（经验值，不是硬限制）、单库 QPS/连接数/磁盘成为瓶颈。先考虑：索引优化 → 读写分离 → 缓存 → 冷热数据归档，都不够再分。

| 拆分方式 | 说明 | 例子 |
|---|---|---|
| 垂直分库 | 按业务拆库 | 用户库、商品库、订单库（第 11 章微服务拆分） |
| 垂直分表 | 大字段/冷字段拆出去 | `t_product` 与 `t_product_detail`（详情富文本） |
| 水平分表 | 同一张表按分片键拆成 N 张 | `t_order_0 ~ t_order_15` |
| 水平分库 | 分表再分散到多个库 | 4 库 × 16 表 |

**分片键选择**——最关键的决策：

| 原则 | 订单表的分析 |
|---|---|
| 覆盖最高频查询 | 「我的订单」按 user_id 查 → 用 `user_id` 分片，同一用户的订单在同一张表 |
| 数据分布均匀 | user_id 足够离散；但「大商户」可能形成热点 |
| 其他维度查询怎么办 | 按 `order_no` 查：**基因法**——生成 order_no 时嵌入 user_id 的低几位，可直接算出分片；商家维度查询：异构一份按商家分片的数据或同步到 ES |

**ShardingSphere-JDBC** 是一个 JDBC 层的代理：应用照常写 `SELECT ... WHERE user_id = ?`，它解析 SQL、根据分片规则改写为 `t_order_5`，必要时并发查多个分片再归并结果。核心概念：

| 概念 | 含义 |
|---|---|
| 逻辑表 / 真实表 | `t_order` / `t_order_0..15` |
| 分片键 | 用于计算路由的列 |
| 分片算法 | 取模、范围、哈希、自定义 |
| 绑定表 | `t_order` 与 `t_order_item` 用相同分片键，join 时不会笛卡尔积路由 |
| 广播表 | 每个库都有完整一份的小表（如字典表） |

分库分表带来的代价：全局唯一 ID（雪花）、跨分片分页排序、跨库事务（第 11 章 Seata / 本地消息表）、扩容迁移。**能不分就不分**。

### 8.3 高级工程师的数据库素养

- **任何新 SQL 都先 EXPLAIN**，评审时看 type、key、rows、Extra 四列；
- **事务尽量小、尽量短**，事务边界与锁范围是一回事；
- **以并发视角审视每一处「先读后写」**：是否该用条件更新、唯一索引、乐观锁或分布式锁（第 9 章）；
- **DDL 以「线上兼容 + 可回滚」为前提**：加字段带默认值、加索引用 Online DDL、删字段晚于代码；
- **用数据说话**：慢日志聚合、`performance_schema`、`sys` 库（`sys.schema_unused_indexes` 找无用索引，`sys.schema_redundant_indexes` 找冗余索引）。

---

## 9. 小练习

1. 本地建好四张表，用存储过程或脚本给 `t_order` 灌 200 万行（其中一个 user_id 占 100 万），复现 6.7 的慢 SQL，并逐步验证每种优化的 `Rows_examined` 与耗时。
2. 对以下 SQL 分别 EXPLAIN，解释 key_len 和 Extra 的差异：
   - `WHERE user_id = 1 ORDER BY create_time DESC`
   - `WHERE user_id = 1 ORDER BY id`
   - `WHERE DATE(create_time) = '2026-11-26'`
   - `WHERE order_no = 20261126001`
3. 开两个 MySQL 会话，在 RR 和 RC 下分别重现：不可重复读、4.3.3 中的「快照读 + 当前读」幻读、4.4.3 的两个死锁案例，并用 `SHOW ENGINE INNODB STATUS` 读懂死锁日志。
4. 写一个 JUnit 测试：100 个线程并发对库存为 10 的商品分别调用「先查后改」和 `ProductDao.deductStock`，统计成功次数与最终库存，验证超卖与不超卖。
5. 为 `t_order` 设计一条线上兼容的 DDL：增加 `pay_time`（支付时间）和 `remark`（买家备注，最长 200 字），说明为什么老版本代码的 INSERT 不会报错。
6. 把 `OrderDao.pageByUser` 改为在总数超过 1 万时不再精确 count，思考前端分页组件需要做什么配合。
