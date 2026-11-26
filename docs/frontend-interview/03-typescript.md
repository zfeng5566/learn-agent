# TypeScript 面试知识点详解

> 对应总大纲 [第 4 节 TypeScript ★★★](../frontend-interview-outline.md)。
> 星级：★★★ 必考 / ★★ 常考 / ★ 加分项。版本基准：TypeScript 5.x（截至 2026，含 5.0–5.9 新特性，并提及 6.0 / 7.0 动向）。
> **侧重点**：类型体操不是重点，**用类型约束业务**才是。面试官更想听到「这个类型在项目里解决了什么问题」。

## 目录

- [0. 约定：类型断言工具](#0-约定类型断言工具)
- [1. interface vs type ★★★](#1-interface-vs-type-)
- [2. any / unknown / never ★★★](#2-any--unknown--never-)
- [3. 泛型与约束 ★★★](#3-泛型与约束-)
- [4. keyof / typeof / 索引访问类型 ★★★](#4-keyof--typeof--索引访问类型-)
- [5. 条件类型与分布式条件类型 ★★★](#5-条件类型与分布式条件类型-)
- [6. infer ★★★](#6-infer-)
- [7. 映射类型 ★★](#7-映射类型-)
- [8. 模板字面量类型 ★★](#8-模板字面量类型-)
- [9. 内置工具类型及手写实现 ★★★](#9-内置工具类型及手写实现-)
- [10. 类型守卫与类型收窄 ★★★](#10-类型守卫与类型收窄-)
- [11. 可辨识联合与穷尽检查 ★★★](#11-可辨识联合与穷尽检查-)
- [12. satisfies ★★](#12-satisfies-)
- [13. as const 与 const 类型参数 ★★](#13-as-const-与-const-类型参数-)
- [14. 协变 / 逆变与 strictFunctionTypes ★★](#14-协变--逆变与-strictfunctiontypes-)
- [15. tsconfig 关键项 ★★](#15-tsconfig-关键项-)
- [16. 声明文件 .d.ts ★★](#16-声明文件-dts-)
- [17. 高频题完整答案 ★★★](#17-高频题完整答案-)
- [18. 速记清单](#18-速记清单)

---

## 0. 约定：类型断言工具

下文用 `Expect<Equal<A, B>>` 在编译期断言两个类型完全相等（type-challenges 的标准写法），写错会直接编译报错。这本身也是一道题：**如何测试类型？**

```ts
// 利用「泛型函数类型的可赋值性」比较两个类型是否严格相同（能区分 any、readonly 等细微差别）
type Equal<X, Y> =
  (<T>() => T extends X ? 1 : 2) extends (<T>() => T extends Y ? 1 : 2) ? true : false;
type Expect<T extends true> = T;

type _ok = Expect<Equal<string, string>>;
// @ts-expect-error any 与 string 不相等
type _bad = Expect<Equal<any, string>>;
```

> `// @ts-expect-error` 表示「下一行必须报错」，不报错反而编译失败。下文用它标注**故意写错**的代码。

---

## 1. interface vs type ★★★

**是什么 / 原理**

- `interface` 只能描述**对象形状**（含函数、类实例），支持 `extends`、**声明合并**（同名 interface 自动合并）。
- `type` 是**类型别名**，可以给任何类型起名：联合、交叉、元组、原始类型、条件类型、映射类型等。
- 编译器层面：interface 有名字缓存，`extends` 的检查结果可缓存；大量交叉类型 `&` 每次都要重新计算，因此官方性能建议「对象继承优先用 interface extends」。

**代码示例**

```ts
interface User { id: number; name: string }
interface User { age?: number }            // 声明合并：User 现在有 id/name/age
interface Admin extends User { role: 'admin' }

type ID = string | number;                 // 联合：只能用 type
type Point = [x: number, y: number];       // 元组：只能用 type
type WithTime<T> = T & { createdAt: Date }; // 交叉
type Getters<T> = { [K in keyof T as `get${Capitalize<string & K>}`]: () => T[K] }; // 映射：只能用 type

// extends 冲突会直接报错，& 冲突会静默得到 never 属性
interface A { x: string }
// @ts-expect-error 属性 x 类型不兼容
interface B extends A { x: number }
type C = A & { x: number };                // 不报错，但 C['x'] 是 string & number = never
type _c = Expect<Equal<C['x'], never>>;

const u: User = { id: 1, name: 'a' };
const admin: Admin = { ...u, role: 'admin' };
```

**面试答题要点**

1. 能力范围：type 能表达任意类型（联合/元组/条件/映射），interface 只描述对象结构。
2. interface 支持声明合并，适合对外暴露、需要被使用者扩展的类型（如给 `Window`、第三方库扩展字段）。
3. 继承：interface 用 `extends`，冲突时报错；type 用 `&`，冲突时得到 `never`，更隐蔽。
4. 性能：大型项目对象继承优先 interface extends，编译器可缓存。
5. 实践：团队统一即可——对象/类契约用 interface，组合/计算类型用 type。

**易错点 / 追问**

- 追问「interface 能继承 type 吗？」——能，只要 type 是对象类型（或对象类型的交叉）；继承联合类型不行。
- 声明合并是双刃剑：全局同名 interface 可能被意外合并，库作者故意用它做扩展点。
- 两者都能被 `class implements`。
- type 别名不能递归引用自身的「直接展开」（如 `type T = T[]` 早期报错），但现在在对象/元组/数组位置的递归是允许的。

---

## 2. any / unknown / never ★★★

**是什么 / 原理**

| 类型 | 集合含义 | 可赋值给谁 | 谁能赋值给它 | 能否直接使用 |
|---|---|---|---|---|
| `any` | 关闭检查 | 任何类型 | 任何类型 | 能（无检查） |
| `unknown` | 全集（top type） | 只能给 `unknown` / `any` | 任何类型 | 不能，必须先收窄 |
| `never` | 空集（bottom type） | 任何类型 | 只有 `never` | 不存在值 |

**代码示例**

```ts
function parse(json: string): unknown {
  return JSON.parse(json);
}
const data = parse('{"a":1}');
// @ts-expect-error unknown 不能直接访问属性
data.a;
if (typeof data === 'object' && data !== null && 'a' in data) {
  console.log(data.a);                     // 收窄后可用
}

// never 的三种来源：不会返回的函数、穷尽后的分支、不可能的交叉
function fail(msg: string): never { throw new Error(msg); }
type Impossible = string & number;         // never
type _n = Expect<Equal<Impossible, never>>;

// never 在联合中被吸收：T | never = T，常用于过滤
type Filtered = string | never;
type _f = Expect<Equal<Filtered, string>>;
```

**面试答题要点**

1. `any` 是「关掉类型系统」，会传染：`any` 参与运算的结果仍是 `any`。
2. `unknown` 是类型安全的 any：接收任何值，但使用前必须通过类型守卫收窄。外部输入（接口返回、`JSON.parse`、`catch (e)`）首选 unknown。
3. `never` 表示不可能存在的值：抛错函数返回值、穷尽检查、条件类型中过滤成员。
4. 集合论视角：unknown 是全集、never 是空集，联合中 never 被吸收，交叉中 unknown 被吸收。

**易错点 / 追问**

- `useUnknownInCatchVariables`（strict 包含）下 `catch (e)` 的 e 是 unknown，需 `e instanceof Error` 再用。
- `void` 与 `never` 区别：void 函数正常返回（返回 undefined），never 函数永不返回。
- `object` / `Object` / `{}`：`{}` 表示「非 null/undefined 的任意值」，`object` 表示非原始类型，`Object` 基本不用。
- 追问「如何禁止项目里用 any？」——`noImplicitAny` + ESLint `@typescript-eslint/no-explicit-any`，第三方类型缺失用 `unknown` + 守卫兜底。

---

## 3. 泛型与约束 ★★★

**是什么 / 原理**

泛型是**类型层面的参数**：调用时由实参推断（或显式传入），让函数/类/类型在保持类型关联的同时可复用。`extends` 给泛型加约束（上界），`=` 给默认值。

**代码示例**

```ts
// 约束：K 必须是 T 的键，返回值类型跟随 K 变化
function getProp<T, K extends keyof T>(obj: T, key: K): T[K] {
  return obj[key];
}
const user = { id: 1, name: 'Tom' };
const n = getProp(user, 'name');           // string
// @ts-expect-error 'age' 不在 keyof typeof user 中
getProp(user, 'age');

// 默认类型参数 + 约束
interface ApiResult<T = unknown, E extends { code: number } = { code: number; msg: string }> {
  data?: T;
  error?: E;
}
const r: ApiResult<string[]> = { data: ['a'] };

// 泛型类
class Store<S extends object> {
  constructor(private state: S) {}
  get<K extends keyof S>(k: K): S[K] { return this.state[k]; }
  set<K extends keyof S>(k: K, v: S[K]): void { this.state[k] = v; }
}
const store = new Store({ count: 0 });
// @ts-expect-error count 是 number
store.set('count', '1');

// NoInfer（5.4）：阻止某个位置参与推断
function createFSM<S extends string>(states: S[], initial: NoInfer<S>) { return { states, initial }; }
// @ts-expect-error 'stop' 不在 states 中；没有 NoInfer 时 S 会被推断成 'idle'|'run'|'stop'
createFSM(['idle', 'run'], 'stop');
```

**面试答题要点**

1. 泛型的价值是**保留类型之间的关联**（入参和出参、键和值），而不是「随便什么类型」。
2. `extends` 是约束（类型必须可赋值给上界），常配 `keyof` 做安全的属性访问。
3. 推断优先于显式传参；推断不理想时用约束、默认值、`NoInfer` 或 `const` 类型参数调整。
4. 泛型不要滥用：如果类型参数只出现一次（只在入参或只在出参），往往不需要泛型。

**易错点 / 追问**

- 「泛型只出现一次」反模式：`function f<T>(x: T): void` 等价于 `(x: unknown) => void`。
- 在函数内部 `T` 是不透明的，不能对 `T` 做 `typeof x === 'string'` 后把 `T` 当 string 返回，常需要重载或断言。
- 箭头泛型在 `.tsx` 中写 `<T,>(x: T) => x` 或 `<T extends unknown>`，避免被解析成 JSX。
- 追问「泛型约束和条件类型的 extends 有何区别？」——前者是限制，后者是判断（类型层 if）。

---

## 4. keyof / typeof / 索引访问类型 ★★★

**是什么 / 原理**

- `keyof T`：取对象类型所有键组成的联合（字符串/数字/symbol 字面量）。
- `typeof x`（类型位置）：从**值**反推类型，「值 → 类型」的桥梁。
- `T[K]`：索引访问类型，取属性类型；`T[number]` 取数组/元组元素类型。

**代码示例**

```ts
const config = {
  env: 'prod',
  retry: 3,
  endpoints: { user: '/api/user', order: '/api/order' },
} as const;

type Config = typeof config;                       // 从值得到类型，单一数据源
type ConfigKey = keyof Config;                     // 'env' | 'retry' | 'endpoints'
type Endpoint = Config['endpoints'][keyof Config['endpoints']]; // '/api/user' | '/api/order'
type _e = Expect<Equal<Endpoint, '/api/user' | '/api/order'>>;

const ROLES = ['admin', 'editor', 'viewer'] as const;
type Role = (typeof ROLES)[number];                // 'admin' | 'editor' | 'viewer'
type _r = Expect<Equal<Role, 'admin' | 'editor' | 'viewer'>>;

// 索引签名下 keyof 是 string | number（因为 obj[1] 会被转成 obj['1']）
type Dict = { [k: string]: boolean };
type _k = Expect<Equal<keyof Dict, string | number>>;

// 函数：typeof + ReturnType 拿到返回值类型，不必手写重复类型
function createUser() { return { id: 1, tags: ['a'] }; }
type CreatedUser = ReturnType<typeof createUser>;
```

**面试答题要点**

1. `typeof` 把运行时值变成类型，配合 `as const` 实现「常量即类型」的单一数据源。
2. `keyof` 生成键联合，配泛型约束 `K extends keyof T` 做类型安全的访问。
3. `T[K]` 支持联合键分发：`T['a' | 'b']` = `T['a'] | T['b']`；`T[number]` 取元素类型。
4. 业务价值：常量数组/配置对象只写一份，类型自动派生，改常量类型自动同步。

**易错点 / 追问**

- 类型位置的 `typeof` 只能接标识符/属性访问，不能接表达式（`typeof fn()` 不行）。
- `keyof any` 是 `string | number | symbol`，常用作键约束（等同 `PropertyKey`）。
- 没有 `as const` 时 `typeof ROLES` 是 `string[]`，`[number]` 只能得到 `string`。

---

## 5. 条件类型与分布式条件类型 ★★★

**是什么 / 原理**

`T extends U ? X : Y` 是类型层的三元表达式。当 `T` 是**裸类型参数**且传入联合类型时，会对联合的每个成员**分别计算再合并**，称为分布式条件类型（distributive）。

**代码示例**

```ts
type IsString<T> = T extends string ? true : false;
type _a = Expect<Equal<IsString<'x'>, true>>;

// 分布式：string | number 被拆开分别计算
type ToArray<T> = T extends unknown ? T[] : never;
type _b = Expect<Equal<ToArray<string | number>, string[] | number[]>>;

// 用 [] 包裹阻止分布
type ToArrayNoDist<T> = [T] extends [unknown] ? T[] : never;
type _c = Expect<Equal<ToArrayNoDist<string | number>, (string | number)[]>>;

// never 是空联合，分布时直接得到 never；判断 never 必须包裹
type IsNeverWrong<T> = T extends never ? true : false;
type IsNever<T> = [T] extends [never] ? true : false;
type _d = Expect<Equal<IsNeverWrong<never>, never>>;
type _e = Expect<Equal<IsNever<never>, true>>;

// 业务用法：按入参类型决定返回类型
type Resp<T extends 'list' | 'detail'> = T extends 'list' ? { items: string[] } : { item: string };
declare function fetchData<T extends 'list' | 'detail'>(kind: T): Promise<Resp<T>>;
```

**面试答题要点**

1. 条件类型是类型层的 if/else，`extends` 表示「可赋值于」。
2. 裸类型参数遇联合会分布式计算，这是 `Exclude` / `Extract` 的实现基础。
3. 不想分布时用 `[T] extends [U]` 包裹。
4. `never` 作为空联合，分布后结果为 never，所以 `IsNever` 必须包裹。
5. 条件类型可递归，配合 `infer` 做类型提取与变换。

**易错点 /追问**

- 只有「裸」类型参数才分布：`T[] extends ...`、`Promise<T> extends ...` 都不分布。
- 条件类型里 `T` 未确定（泛型函数内部）时，结果是延迟的，不能直接赋值。
- `any extends X ? A : B` 结果是 `A | B`（两边都取）。

---

## 6. infer ★★★

**是什么 / 原理**

`infer X` 只能出现在条件类型的 `extends` 子句中，表示「在这里声明一个待推断的类型变量」，匹配成功后可在 true 分支使用。可以理解为类型层面的**模式匹配 + 解构**。

**代码示例**

```ts
type ElementOf<T> = T extends readonly (infer E)[] ? E : never;
type _a = Expect<Equal<ElementOf<string[]>, string>>;

type First<T extends readonly unknown[]> = T extends readonly [infer F, ...unknown[]] ? F : never;
type Last<T extends readonly unknown[]> = T extends readonly [...unknown[], infer L] ? L : never;
type _b = Expect<Equal<First<[1, 2, 3]>, 1>>;
type _c = Expect<Equal<Last<[1, 2, 3]>, 3>>;

// 解包 Promise（单层）
type UnPromise<T> = T extends Promise<infer V> ? V : T;
type _d = Expect<Equal<UnPromise<Promise<number>>, number>>;

// infer + extends 约束（4.7）：推断的同时限定类型
type NumericPrefix<S> = S extends `${infer N extends number}px` ? N : never;
type _e = Expect<Equal<NumericPrefix<'12px'>, 12>>;

// 同一 infer 出现在逆变位置（函数参数）时，联合会被推断为交叉
type UnionToIntersection<U> =
  (U extends unknown ? (x: U) => void : never) extends (x: infer I) => void ? I : never;
type _f = Expect<Equal<UnionToIntersection<{ a: 1 } | { b: 2 }>, { a: 1 } & { b: 2 }>>;
```

**面试答题要点**

1. `infer` 只能在条件类型 `extends` 右侧使用，用于从结构中「抠出」某部分类型。
2. 经典实现：`ReturnType`、`Parameters`、`Awaited`、元组首尾、字符串解析。
3. 4.7 起支持 `infer X extends C`，推断并约束，常用于把字符串字面量转数字。
4. 协变位置的多个候选推断为联合，逆变位置推断为交叉（`UnionToIntersection` 原理）。

**易错点 /追问**

- 函数有重载时，`infer` 只取**最后一个**重载签名。
- 匹配失败走 false 分支，记得给合理的兜底（`never` 还是原样返回 `T`，取决于语义）。

---

## 7. 映射类型 ★★

**是什么 / 原理**

`{ [K in Keys]: ... }` 遍历键联合生成新对象类型。`[K in keyof T]` 称为**同态映射**，会保留原属性的 `readonly` / `?` 修饰符，且对数组/元组映射后仍是数组/元组。修饰符可用 `+` / `-` 增删；4.1 起支持 `as` 重映射键名。

**代码示例**

```ts
interface Todo { readonly id: number; title: string; done?: boolean }

type Mutable<T> = { -readonly [K in keyof T]: T[K] };   // 去掉 readonly
type Concrete<T> = { [K in keyof T]-?: T[K] };          // 去掉 ?
type _a = Expect<Equal<Mutable<Todo>, { id: number; title: string; done?: boolean }>>;

// as 重映射：改键名 / 过滤键（映射成 never 即删除）
type Getters<T> = { [K in keyof T as `get${Capitalize<string & K>}`]: () => T[K] };
type PickByValue<T, V> = { [K in keyof T as T[K] extends V ? K : never]: T[K] };
type _b = Expect<Equal<PickByValue<{ a: string; b: number; c: string }, string>, { a: string; c: string }>>;

// 同态映射作用于元组，结果仍是元组
type Boxed<T> = { [K in keyof T]: { value: T[K] } };
type _c = Expect<Equal<Boxed<[1, 2]>, [{ value: 1 }, { value: 2 }]>>;

// 业务：表单状态由数据模型派生
type FormErrors<T> = { [K in keyof T]?: string };
type TodoErrors = FormErrors<Todo>;
```

**面试答题要点**

1. 映射类型是类型层的 for...in，所有对象变换类工具类型（Partial/Readonly/Pick/Record）都基于它。
2. 同态映射 `[K in keyof T]` 保留修饰符；`-readonly`、`-?` 可移除修饰符。
3. `as` 子句可以改名或过滤键（返回 never 即剔除）。
4. 业务里用于从一份模型派生表单、错误、校验规则、getter 等类型，避免重复定义。

**易错点 /追问**

- `as` 重映射后不再是同态映射，对数组不再保持数组结构。
- `keyof T` 可能含 `symbol`，模板字面量里用 `string & K` 过滤。

---

## 8. 模板字面量类型 ★★

**是什么 / 原理**

用反引号在类型层拼接字符串字面量；插槽内传联合会做**笛卡尔积**。配套内置 intrinsic 类型 `Uppercase / Lowercase / Capitalize / Uncapitalize`。配合 `infer` 可以做字符串解析。

**代码示例**

```ts
type Size = 'sm' | 'lg';
type Color = 'red' | 'blue';
type ClassName = `btn-${Size}-${Color}`;   // 4 种组合
type _a = Expect<Equal<ClassName, 'btn-sm-red' | 'btn-sm-blue' | 'btn-lg-red' | 'btn-lg-blue'>>;

// 事件名派生：onClick / onChange
type Handlers<E extends string> = { [K in E as `on${Capitalize<K>}`]: () => void };
type _b = Expect<Equal<Handlers<'click'>, { onClick: () => void }>>;

// 解析路由参数：'/users/:id/posts/:pid' -> 'id' | 'pid'
type PathParams<P extends string> =
  P extends `${string}:${infer Param}/${infer Rest}` ? Param | PathParams<Rest>
  : P extends `${string}:${infer Param}` ? Param
  : never;
type _c = Expect<Equal<PathParams<'/users/:id/posts/:pid'>, 'id' | 'pid'>>;

// 驼峰转换
type CamelCase<S extends string> =
  S extends `${infer H}_${infer T}` ? `${H}${CamelCase<Capitalize<T>>}` : S;
type _d = Expect<Equal<CamelCase<'user_first_name'>, 'userFirstName'>>;

// 宽泛约束：必须以 px 结尾
type Px = `${number}px`;
const w: Px = '12px';
// @ts-expect-error 不符合模板
const h: Px = '12rem';
```

**面试答题要点**

1. 模板字面量类型让字符串也能「有结构」，插入联合时自动展开笛卡尔积。
2. 结合映射类型 `as` 可以批量生成事件名、getter 名、CSS 类名。
3. 结合 `infer` 可以解析路由参数、点路径（`'a.b.c'`），是「API 路由类型安全」的基础。
4. 可用 `${number}`、`${string}` 做宽泛格式约束。

**易错点 /追问**

- 联合组合数量爆炸（超过约 10 万项）会报 “Expression produces a union type that is too complex”。
- 递归深度有上限（尾递归条件类型约 1000 层），解析超长字符串要注意。

---

## 9. 内置工具类型及手写实现 ★★★

> 面试常让手写 3-5 个。核心就三把刀：**映射类型**（对象变换）、**条件类型**（联合过滤）、**infer**（结构提取）。

### 9.1 对象变换类（映射类型）

```ts
type MyPartial<T> = { [K in keyof T]?: T[K] };                 // 全部可选
type MyRequired<T> = { [K in keyof T]-?: T[K] };               // 全部必填
type MyReadonly<T> = { readonly [K in keyof T]: T[K] };        // 全部只读
type MyPick<T, K extends keyof T> = { [P in K]: T[P] };        // 挑选部分键
type MyRecord<K extends keyof any, V> = { [P in K]: V };       // 键 -> 值 的对象
type MyOmit<T, K extends keyof any> = MyPick<T, MyExclude<keyof T, K>>; // 剔除部分键

interface User { id: number; name?: string; readonly email: string }
type _p = Expect<Equal<MyPartial<User>, Partial<User>>>;
type _r = Expect<Equal<MyRequired<User>, Required<User>>>;
type _ro = Expect<Equal<MyReadonly<User>, Readonly<User>>>;
type _pk = Expect<Equal<MyPick<User, 'id' | 'email'>, Pick<User, 'id' | 'email'>>>;
type _rc = Expect<Equal<MyRecord<'a' | 'b', number>, Record<'a' | 'b', number>>>;
type _o = Expect<Equal<MyOmit<User, 'email'>, Omit<User, 'email'>>>;

// 依赖的联合工具（见 9.2）
type MyExclude<T, U> = T extends U ? never : T;
```

### 9.2 联合过滤类（分布式条件类型）

```ts
type MyExclude<T, U> = T extends U ? never : T;         // 从 T 中剔除可赋值给 U 的成员
type MyExtract<T, U> = T extends U ? T : never;         // 从 T 中保留可赋值给 U 的成员
type MyNonNullable<T> = T & {};                         // 去掉 null | undefined（4.8 起官方实现）
type MyNonNullableOld<T> = T extends null | undefined ? never : T; // 旧实现

type U = 'a' | 'b' | 'c' | null | undefined;
type _ex = Expect<Equal<MyExclude<U, 'a' | null>, 'b' | 'c' | undefined>>;
type _et = Expect<Equal<MyExtract<U, string>, 'a' | 'b' | 'c'>>;
type _nn = Expect<Equal<MyNonNullable<U>, 'a' | 'b' | 'c'>>;
type _nn2 = Expect<Equal<MyNonNullableOld<U>, 'a' | 'b' | 'c'>>;
```

### 9.3 结构提取类（infer）

```ts
type MyReturnType<T extends (...args: any) => any> = T extends (...args: any) => infer R ? R : any;
type MyParameters<T extends (...args: any) => any> = T extends (...args: infer P) => any ? P : never;
type MyConstructorParameters<T extends abstract new (...args: any) => any> =
  T extends abstract new (...args: infer P) => any ? P : never;
type MyInstanceType<T extends abstract new (...args: any) => any> =
  T extends abstract new (...args: any) => infer R ? R : any;
type MyThisParameterType<T> = T extends (this: infer U, ...args: never) => any ? U : unknown;

// Awaited：递归解包所有 thenable（不只是 Promise），与官方实现思路一致
type MyAwaited<T> =
  T extends null | undefined ? T
  : T extends object & { then(onfulfilled: infer F, ...args: infer _): any }
    ? F extends (value: infer V, ...args: infer _) => any ? MyAwaited<V> : never
  : T;

function login(name: string, remember?: boolean) { return { token: 'x', name }; }
class Svc { constructor(public url: string, public timeout: number) {} }

type _rt = Expect<Equal<MyReturnType<typeof login>, { token: string; name: string }>>;
type _pa = Expect<Equal<MyParameters<typeof login>, [name: string, remember?: boolean]>>;
type _cp = Expect<Equal<MyConstructorParameters<typeof Svc>, [url: string, timeout: number]>>;
type _it = Expect<Equal<MyInstanceType<typeof Svc>, Svc>>;
type _aw = Expect<Equal<MyAwaited<Promise<Promise<number>>>, number>>;
type _aw2 = Expect<Equal<MyAwaited<PromiseLike<string>>, string>>;
type _aw3 = Expect<Equal<MyAwaited<Promise<number>>, Awaited<Promise<number>>>>;
```

### 9.4 一览表

| 工具类型 | 作用 | 核心手段 | 考频 |
|---|---|---|---|
| `Partial<T>` | 全部可选 | 映射 + `?` | ★★★ |
| `Required<T>` | 全部必填 | 映射 + `-?` | ★★ |
| `Readonly<T>` | 全部只读（浅） | 映射 + `readonly` | ★★★ |
| `Pick<T, K>` | 挑选键 | 映射 `[P in K]` | ★★★ |
| `Omit<T, K>` | 剔除键 | `Pick` + `Exclude` | ★★★ |
| `Record<K, V>` | 构造键值对象 | 映射 | ★★★ |
| `Exclude<T, U>` | 联合中剔除 | 分布式条件 | ★★★ |
| `Extract<T, U>` | 联合中保留 | 分布式条件 | ★★ |
| `NonNullable<T>` | 去 null/undefined | `T & {}` | ★★ |
| `ReturnType<F>` | 函数返回值 | infer | ★★★ |
| `Parameters<F>` | 函数参数元组 | infer | ★★★ |
| `Awaited<T>` | 递归解包 Promise | 递归 + infer | ★★ |
| `InstanceType / ConstructorParameters` | 类实例 / 构造参数 | infer + 构造签名 | ★ |
| `NoInfer<T>`（5.4） | 阻止推断 | intrinsic | ★ |

**面试答题要点**

1. 先说分类：对象变换（映射）、联合过滤（分布式条件）、结构提取（infer），再按类写。
2. `Omit = Pick<T, Exclude<keyof T, K>>`，注意官方 `Omit` 的 K 是 `keyof any`，不校验键是否存在。
3. `Exclude` 依赖分布式条件类型，被剔除的成员变成 never 后在联合中消失。
4. `Awaited` 是递归的，且按 thenable（有 `then` 方法）判断，而不只匹配 `Promise`。
5. 内置 `Partial/Readonly` 都是**浅层**的，需要深层要自己写（见第 17 节）。

**易错点 /追问**

- `ReturnType` 的约束是 `(...args: any) => any`，用 `unknown[]` 作为参数约束会因逆变导致部分函数不匹配。
- `Record<string, T>` 访问任意键都返回 `T`（不含 undefined），开 `noUncheckedIndexedAccess` 才会加上 `| undefined`。
- 追问「`Omit` 用在联合类型上会怎样？」——`keyof (A | B)` 只取公共键，结果会丢失各自的独有字段，需要分布式版本（17.3）。

---

## 10. 类型守卫与类型收窄 ★★★

**是什么 / 原理**

TS 通过**控制流分析**在分支中把宽类型收窄为窄类型。收窄手段：`typeof`、`instanceof`、`in`、相等判断、真值判断、可辨识属性，以及自定义类型谓词 `x is T` 和断言函数 `asserts x is T`。

**代码示例**

```ts
function format(v: string | number | Date | null) {
  if (v == null) return '';                     // 相等收窄：去掉 null/undefined
  if (typeof v === 'string') return v.trim();   // typeof 收窄
  if (v instanceof Date) return v.toISOString(); // instanceof 收窄
  return v.toFixed(2);                          // 剩下 number
}

interface Fish { swim(): void }
interface Bird { fly(): void }
function move(a: Fish | Bird) {
  if ('swim' in a) a.swim();                    // in 收窄
  else a.fly();
}

// 自定义类型谓词：把运行时校验结果告诉编译器
interface User { id: number; name: string }
function isUser(x: unknown): x is User {
  return typeof x === 'object' && x !== null
    && typeof (x as Record<string, unknown>).id === 'number'
    && typeof (x as Record<string, unknown>).name === 'string';
}

// 断言函数：不满足直接抛错，之后的代码都视为已收窄
function assertIsDefined<T>(v: T, msg = 'value is nullish'): asserts v is NonNullable<T> {
  if (v == null) throw new Error(msg);
}
function handle(input: unknown, el: HTMLElement | null) {
  if (isUser(input)) console.log(input.name);
  assertIsDefined(el);
  el.focus();                                   // el: HTMLElement
}

// 5.5 起：filter 回调可被自动推断为类型谓词
const list = [1, undefined, 2].filter(x => x !== undefined);
type _l = Expect<Equal<typeof list, number[]>>;
```

**面试答题要点**

1. 收窄基于控制流分析，常见手段：typeof / instanceof / in / 相等 / 真值 / 可辨识属性。
2. 自定义类型谓词 `x is T` 用于封装复杂校验，返回 boolean 但携带类型信息。
3. 断言函数 `asserts x is T` 不满足就抛错，适合前置校验。
4. 外部数据（接口、localStorage）应先 unknown 再通过守卫或 zod 等 schema 库校验，而不是直接 `as`。
5. 5.5 起简单的过滤箭头函数会自动推断类型谓词，`filter(Boolean)` 仍不行。

**易错点 /追问**

- 类型谓词是「你对编译器的承诺」，实现写错编译器不会发现，本质和 `as` 一样不安全。
- `typeof null === 'object'`，用 typeof 判断对象要排除 null。
- 回调函数里收窄会失效（闭包中变量可能被修改），`let` 变量尤其明显；5.4 起对闭包最后一次赋值之后的场景有改进。
- 断言函数必须用显式类型注解声明（`const assertX: AssertFn = ...`），否则调用处不生效。

---

## 11. 可辨识联合与穷尽检查 ★★★

**是什么 / 原理**

多个对象类型共享一个**字面量类型的公共字段**（辨识字段，如 `type` / `kind` / `status`），通过判断该字段即可收窄到具体成员。配合 `never` 做**穷尽检查**：新增成员忘记处理时编译报错。这是「用类型约束业务」的最典型手段。

**代码示例**

```ts
// 请求状态：用联合代替多个布尔字段，杜绝 loading=true 且 error 存在的非法状态
type RequestState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: Error };

function assertNever(x: never): never {
  throw new Error(`未处理的分支: ${JSON.stringify(x)}`);
}

function render(s: RequestState<string[]>): string {
  switch (s.status) {
    case 'idle': return '未开始';
    case 'loading': return '加载中';
    case 'success': return s.data.join(',');    // 这里 s 被收窄，可访问 data
    case 'error': return s.error.message;
    default: return assertNever(s);             // 新增 status 未处理时这里报错
  }
}

// 反例：漏掉一个分支
function renderBad(s: RequestState<string[]>): string {
  switch (s.status) {
    case 'idle': case 'loading': return '...';
    case 'success': return 'ok';
    // @ts-expect-error 'error' 分支未处理，s 不是 never
    default: return assertNever(s);
  }
}

// Redux / useReducer 的 action 也是同样模式
type Action = { type: 'add'; payload: number } | { type: 'reset' };
function reducer(state: number, action: Action): number {
  if (action.type === 'add') return state + action.payload;
  return 0;
}
```

**面试答题要点**

1. 可辨识联合 = 联合类型 + 公共字面量辨识字段 + 基于该字段的收窄。
2. 价值是**让非法状态不可表示**（make illegal states unrepresentable），比多个可选字段 / 布尔标记更安全。
3. `default` 分支赋值给 `never` 实现穷尽检查，联合新增成员时所有未处理处都会编译报错。
4. 典型场景：请求状态机、Redux action、表单字段配置、消息协议、权限模型。

**易错点 /追问**

- 辨识字段必须是字面量类型，写成 `string` 就无法收窄。
- 对辨识字段解构后再判断，4.6 起支持「解构后的可辨识联合收窄」，但前提是用 `const` 解构。
- 也可用 `satisfies never` 做穷尽检查：`default: s satisfies never`。

---

## 12. satisfies ★★

**是什么 / 原理**

4.9 引入。`expr satisfies T` **校验** expr 符合 T，但**保留 expr 自身推断出的更精确类型**。对比：类型注解 `const x: T` 会把类型拓宽成 T；`as T` 是断言，不做充分校验。

**代码示例**

```ts
type Route = { path: string; auth?: boolean };

// 注解：校验了，但具体键丢失，routes.home 可能不存在也不报错
const routesA: Record<string, Route> = { home: { path: '/' } };
routesA.whatever;                                  // 不报错

// satisfies：既校验每项结构，又保留具体的键
const routes = {
  home: { path: '/' },
  admin: { path: '/admin', auth: true },
} satisfies Record<string, Route>;
routes.admin.path;
// @ts-expect-error 不存在的键会报错
routes.whatever;

// 拼写错误也能被发现（多余属性检查）
const bad = {
  // @ts-expect-error 'pth' 不在 Route 中
  home: { pth: '/' },
} satisfies Record<string, Route>;

// 与 as const 组合：值是字面量且只读，同时校验结构
const theme = { primary: '#1677ff', danger: '#ff4d4f' } as const satisfies Record<string, `#${string}`>;
type _t = Expect<Equal<typeof theme.primary, '#1677ff'>>;
```

**面试答题要点**

1. 三者对比：注解「校验 + 拓宽」、`as`「不校验 + 强制」、`satisfies`「校验 + 保留推断」。
2. 适合配置对象、路由表、主题色、i18n 文案表：要约束结构又想保留具体键/字面量。
3. 常与 `as const` 组合：`as const satisfies T`。

**易错点 /追问**

- satisfies 不改变变量类型，所以不能用来「扩宽」类型以便后续赋值其他值。
- `as` 只要求两类型「有重叠」即可，`'a' as unknown as number` 这类双重断言能绕过一切检查。

---

## 13. as const 与 const 类型参数 ★★

**是什么 / 原理**

`as const`（const 断言）让字面量推断为**最窄类型**：字符串/数字保持字面量、对象属性变 `readonly`、数组变 `readonly` 元组。5.0 的 `const` 类型参数让泛型函数在调用处自动获得 `as const` 效果。

**代码示例**

```ts
const a = ['GET', 'POST'];                 // string[]
const b = ['GET', 'POST'] as const;        // readonly ['GET', 'POST']
type Method = (typeof b)[number];          // 'GET' | 'POST'
type _m = Expect<Equal<Method, 'GET' | 'POST'>>;

// 替代 enum：零运行时开销之外还能直接用字面量传参
const Status = { Active: 1, Disabled: 0 } as const;
type Status = (typeof Status)[keyof typeof Status]; // 1 | 0
function setStatus(s: Status) {}
setStatus(Status.Active);
setStatus(1);                              // 字面量也可以，数字 enum 做不到这么严格

// const 类型参数（5.0）：调用方不用写 as const
function defineRoutes<const T extends readonly string[]>(paths: T): T { return paths; }
const r = defineRoutes(['/home', '/about']);
type _r = Expect<Equal<typeof r, readonly ['/home', '/about']>>;
```

**面试答题要点**

1. `as const` 产生最窄字面量类型，并递归加 `readonly`。
2. 典型用途：常量数组派生联合类型、对象常量替代 enum、元组返回值（如自定义 hook 返回 `[state, setState] as const`）。
3. 5.0 起 `const T` 泛型参数，让库作者替调用方做 `as const`。
4. 用对象常量 + `as const` 替代 enum 是当前主流实践（enum 有运行时代码，且不兼容 `erasableSyntaxOnly`）。

**易错点 /追问**

- `as const` 只能用于字面量表达式，不能用于变量或函数调用结果。
- readonly 元组不能赋值给可变数组参数：`function f(x: string[])` 不接受 `readonly string[]`，参数要声明成 `readonly string[]`。

---

## 14. 协变 / 逆变与 strictFunctionTypes ★★

**是什么 / 原理**

设 `Dog` 是 `Animal` 的子类型（`Dog <: Animal`），对类型构造器 `F<T>`：

| 变型 | 关系 | TS 中的位置 |
|---|---|---|
| 协变 covariant | `F<Dog> <: F<Animal>`（方向一致） | 属性、返回值、数组元素 |
| 逆变 contravariant | `F<Animal> <: F<Dog>`（方向相反） | 函数参数（`strictFunctionTypes` 下） |
| 双变 bivariant | 两个方向都允许 | 方法简写的参数、关闭 strictFunctionTypes 时的函数参数 |
| 不变 invariant | 两个方向都不允许 | 既读又写的位置，如 `(x: T) => T` |

**为什么参数是逆变**：一个声明「能处理任意 Animal」的函数，当然可以放到「需要处理 Dog」的位置；反之，只能处理 Dog 的函数如果收到 Cat 就会出错。

**代码示例**

```ts
class Animal { name = 'a' }
class Dog extends Animal { bark() {} }

// 协变：返回值、数组
let getDog: () => Dog = () => new Dog();
let getAnimal: () => Animal = getDog;          // OK
const dogs: Dog[] = [];
const animals: Animal[] = dogs;                // OK（但不安全：animals.push(new Animal()) 不报错）

// 逆变：函数参数（strictFunctionTypes 开启时）
type Handler<T> = (x: T) => void;
let handleAnimal: Handler<Animal> = a => console.log(a.name);
let handleDog: Handler<Dog> = d => d.bark();
handleDog = handleAnimal;                      // OK：能处理 Animal 的一定能处理 Dog
// @ts-expect-error 只能处理 Dog 的函数不能当成能处理任意 Animal 的函数
handleAnimal = handleDog;

// 方法简写语法的参数仍是双变（为了兼容 Array<T> 等大量内置方法声明）
interface MethodStyle { handle(x: Animal): void }
interface PropStyle { handle: (x: Animal) => void }
const m: MethodStyle = { handle: (d: Dog) => d.bark() };   // 不报错（双变，有隐患）
// @ts-expect-error 属性写法受 strictFunctionTypes 约束
const p: PropStyle = { handle: (d: Dog) => d.bark() };

// 显式变型注解（4.7）：in = 逆变，out = 协变，in out = 不变
interface Producer<out T> { get(): T }
interface Consumer<in T> { accept(x: T): void }
declare let pd: Producer<Dog>;
declare let ca: Consumer<Animal>;
const pa: Producer<Animal> = pd;               // 协变
const cd: Consumer<Dog> = ca;                  // 逆变
```

**面试答题要点**

1. 协变：子类型关系保持方向，出现在「输出」位置（返回值、只读属性）。
2. 逆变：子类型关系反转，出现在「输入」位置（函数参数），开 `strictFunctionTypes`（strict 包含）后生效。
3. `strictFunctionTypes` 只对**函数类型写法**生效，**方法简写**仍是双变——所以回调类型推荐写成属性形式 `onChange: (v: T) => void`。
4. 数组在 TS 中是协变的，这是有意的不健全（soundness）取舍。
5. 4.7 支持 `in` / `out` 显式注解，主要用于提升复杂泛型的检查性能和明确意图。

**易错点 /追问**

- 追问「为什么方法要双变？」——`Array<T>` 等内置类型方法若严格逆变，`Dog[]` 就不能赋给 `Animal[]`，破坏大量现有代码。
- 逆变位置推断为交叉（见 `UnionToIntersection`），这是变型知识在类型体操中的应用。
- 函数参数个数：少参数的函数可以赋给多参数的函数类型（`arr.forEach(x => ...)` 能成立的原因），这和变型是两回事。

---

## 15. tsconfig 关键项 ★★

**是什么 / 原理**

tsconfig 控制「检查哪些文件、多严格、输出什么、模块怎么解析」。现代前端项目中 TS 常只做类型检查（`noEmit`），编译交给 Vite/esbuild/SWC，因此 `isolatedModules`、`verbatimModuleSyntax`、`moduleResolution: bundler` 变得重要。

**代码示例**（Vite + React 应用的典型配置）

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "verbatimModuleSyntax": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "noEmit": true,
    "resolveJsonModule": true,
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["src"]
}
```

**关键项说明**

| 选项 | 作用 | 说明 / 推荐 |
|---|---|---|
| `strict` | 一键开启严格家族 | 含 `noImplicitAny`、`strictNullChecks`、`strictFunctionTypes`、`strictBindCallApply`、`strictPropertyInitialization`、`noImplicitThis`、`alwaysStrict`、`useUnknownInCatchVariables`。新项目必开 |
| `strictNullChecks` | null/undefined 单独成类型 | 收益最大的一项，关掉后 `string` 隐含可为 null |
| `noUncheckedIndexedAccess` | 索引访问加 `\| undefined` | `arr[0]`、`record[key]` 更安全，不在 strict 内 |
| `exactOptionalPropertyTypes` | `a?: string` 不允许显式赋 undefined | 区分「没有」与「值为 undefined」，较严格 |
| `target` | 输出 JS 语法版本 | 决定是否降级语法，也影响默认 `lib` |
| `lib` | 可用的内置 API 类型 | 如 `DOM`、`ES2023`；Node 项目不要带 DOM |
| `module` | 输出模块格式 | `ESNext` / `NodeNext` / `Preserve`（5.4） |
| `moduleResolution` | 模块查找规则 | `bundler`：给 Vite/webpack 项目，支持 `exports` 且不强制扩展名；`nodenext`/`node16`：给 Node 运行的包，ESM 下强制写 `.js` 扩展名；`node`（node10）已过时 |
| `verbatimModuleSyntax` | 导入导出按字面保留 | 类型导入必须写 `import type`，替代旧的 `importsNotUsedAsValues` |
| `isolatedModules` | 保证单文件可独立转译 | esbuild/SWC/Babel 逐文件编译必须开 |
| `esModuleInterop` | CJS 默认导入兼容 | `import React from 'react'` 能用的原因 |
| `skipLibCheck` | 跳过 `.d.ts` 检查 | 加速编译，几乎都开 |
| `paths` / `baseUrl` | 路径别名 | 只影响类型解析，打包器需同步配置；新版已不需要 baseUrl |
| `declaration` / `declarationMap` | 生成 `.d.ts` 及映射 | 发布库时开启 |
| `noEmit` | 只检查不输出 | 由打包器负责产物时使用 |
| `composite` / `references` / `incremental` | 项目引用、增量编译 | monorepo 分包构建，`tsc -b` |
| `types` | 限定自动引入的 `@types` 包 | 防止全局类型污染（如 jest 与 vitest 冲突） |
| `allowJs` / `checkJs` | 允许 / 检查 JS | JS 迁移 TS 渐进使用 |
| `erasableSyntaxOnly`（5.8） | 禁止有运行时语义的 TS 语法 | 禁 enum、namespace、参数属性；配合 Node 原生类型擦除（`node file.ts`） |

**面试答题要点**

1. `strict` 是一组开关，最核心是 `strictNullChecks` 和 `noImplicitAny`；`noUncheckedIndexedAccess` 不在其中但强烈推荐。
2. `moduleResolution`：前端打包项目用 `bundler`，Node 直接运行的项目/库用 `nodenext`。
3. 现代工程中 tsc 常只做类型检查（`noEmit`），转译由 esbuild/SWC 完成，所以要开 `isolatedModules`、`verbatimModuleSyntax`。
4. `paths` 只是告诉 TS 怎么找类型，不会改写产物路径，打包器/运行时要同步配置。
5. 动向：TS 7 为 Go 原生重写（`tsgo`），编译速度提升约 10 倍；6.0 作为过渡版本收紧默认值并废弃一批旧选项（如 `moduleResolution: node10`、`baseUrl`）。

**易错点 /追问**

- `include`/`exclude` 只决定入口文件，被 import 的文件即使在 exclude 中也会被检查。
- `target` 不负责 polyfill：`target: ES5` 不会给你 `Promise` 实现。
- 追问「monorepo 如何配置？」——根 `tsconfig.base.json` 放公共选项，各包 `extends`；构建用 `composite` + `references`。

---

## 16. 声明文件 .d.ts ★★

**是什么 / 原理**

`.d.ts` 只包含类型声明、不含实现，用于给 JS 代码（或编译产物）提供类型。来源有三：库自带（`package.json` 的 `types` / `exports.types`）、DefinitelyTyped（`@types/xxx`）、项目内手写。

**代码示例**

```typescript
// src/types/global.d.ts —— 无 import/export 的文件是「全局脚本」，声明直接全局可见
declare const __APP_VERSION__: string;        // 构建时注入的常量（Vite define）

// 给非 JS 资源声明模块
declare module '*.svg' {
  const src: string;
  export default src;
}
declare module '*.module.css' {
  const classes: Readonly<Record<string, string>>;
  export default classes;
}
```

```typescript
// src/types/augment.d.ts —— 有 export 的文件是「模块」，用 declare global / declare module 做增强
export {};

declare global {
  interface Window {
    __INITIAL_STATE__?: { user: { id: string } };
  }
}

// 模块增强：给第三方库扩展类型（依赖声明合并）
declare module 'axios' {
  interface AxiosRequestConfig {
    skipErrorToast?: boolean;                  // 自定义配置项，拦截器中读取
  }
}

declare module 'vue' {
  interface ComponentCustomProperties {
    $t: (key: string) => string;               // 全局属性类型
  }
}
```

```typescript
// 给无类型的 JS 库写最小声明（legacy-sdk.d.ts）
declare module 'legacy-sdk' {
  export interface InitOptions { appId: string; debug?: boolean }
  export function init(options: InitOptions): void;
  export function track(event: string, props?: Record<string, string | number>): void;
}
```

**面试答题要点**

1. `.d.ts` 只有类型没有实现；`declare` 表示「这个东西运行时存在，我只描述它的类型」。
2. 文件是否含顶层 `import/export` 决定它是全局脚本还是模块；模块中要用 `declare global` 才能声明全局。
3. 模块增强（`declare module 'xxx'` + 声明合并）用于给 axios、vue、vue-router 等扩展类型。
4. 类型查找顺序：`package.json` 的 `exports` 中 `types` 条件 / `types` 字段 → 同名 `.d.ts` → `@types/xxx`。
5. 发布库：开 `declaration`，在 `exports` 中给每个入口配 `types`，并注意 ESM/CJS 双格式各自的声明文件。

**易错点 /追问**

- 在模块文件里写 `declare module '*.svg'` 会被当作增强而报错（找不到模块），通配声明要放在全局脚本文件中。
- 增强第三方模块时，文件必须是模块（有 `export {}`），且模块名与库的入口一致。
- 写了 `.d.ts` 不生效：检查是否在 `include` 范围内、`types` 选项是否限定了范围。
- `/// <reference types="vite/client" />` 三斜线指令用于引入某包的全局类型。

---

## 17. 高频题完整答案 ★★★

### 17.1 手写 DeepReadonly

```ts
// 思路：函数原样保留；对象/数组递归加 readonly；原始类型原样返回
type DeepReadonly<T> =
  T extends (...args: any[]) => any ? T
  : T extends Map<infer K, infer V> ? ReadonlyMap<DeepReadonly<K>, DeepReadonly<V>>
  : T extends Set<infer M> ? ReadonlySet<DeepReadonly<M>>
  : T extends object ? { readonly [P in keyof T]: DeepReadonly<T[P]> }
  : T;

interface State {
  user: { name: string; tags: string[] };
  ids: Map<string, { n: number }>;
  onChange: (v: string) => void;
}
type R = DeepReadonly<State>;
declare const s: R;
// @ts-expect-error 深层属性只读
s.user.name = 'x';
// @ts-expect-error 数组变成 readonly
s.user.tags.push('x');
// @ts-expect-error Map 变成 ReadonlyMap
s.ids.set('a', { n: 1 });
s.onChange('ok');                              // 函数保持可调用

type _dr = Expect<Equal<DeepReadonly<{ a: { b: [1, { c: 2 }] } }>,
  { readonly a: { readonly b: readonly [1, { readonly c: 2 }] } }>>;
```

**讲解要点**：
1. 递归映射类型 + 条件类型判断分支。
2. 函数也是 `object`，必须先单独放行，否则函数会被映射成只有属性的对象而失去调用签名。
3. 同态映射作用于数组/元组时结果仍是（只读）数组/元组，所以不需要单独处理数组。
4. Map/Set 的内容靠方法修改，映射属性无法让它只读，需要换成 `ReadonlyMap`/`ReadonlySet`。
5. 运行时对应物是递归 `Object.freeze`；类型层只读不影响运行时。

### 17.2 手写 DeepPartial

```ts
type DeepPartial<T> =
  T extends (...args: any[]) => any ? T
  : T extends readonly (infer E)[] ? DeepPartialArray<T, E>
  : T extends object ? { [P in keyof T]?: DeepPartial<T[P]> }
  : T;
// 数组：元素递归可选，但数组本身不变成稀疏元组（业务中 patch 数组通常是整体替换）
type DeepPartialArray<T, E> = T extends unknown[] ? DeepPartial<E>[] : readonly DeepPartial<E>[];

interface Settings {
  theme: { color: string; font: { size: number; family: string } };
  plugins: { name: string; enabled: boolean }[];
}

// 业务场景：配置合并，只传想改的字段
declare function updateSettings(patch: DeepPartial<Settings>): void;
updateSettings({ theme: { font: { size: 14 } } });
updateSettings({ plugins: [{ enabled: false }] });
// @ts-expect-error 类型仍被校验
updateSettings({ theme: { font: { size: '14' } } });
```

**讲解要点**：结构与 DeepReadonly 相同，只是把 `readonly` 换成 `?`；数组的处理要按业务语义取舍（元素可选 vs 数组整体可选）；函数放行；常用于配置合并、测试 mock 数据工厂。

### 17.3 手写 Omit（含严格版、分布式版）

```ts
// 写法一：Pick + Exclude（官方实现）
type MyOmit<T, K extends keyof any> = Pick<T, Exclude<keyof T, K>>;

// 写法二：映射类型 + as 过滤（4.1+）
type MyOmit2<T, K extends keyof any> = { [P in keyof T as P extends K ? never : P]: T[P] };

// 严格版：K 必须是 T 已有的键，防止拼写错误
type StrictOmit<T, K extends keyof T> = Pick<T, Exclude<keyof T, K>>;

// 分布式版：用于联合类型，逐个成员 Omit，保留各成员独有字段
type DistributiveOmit<T, K extends keyof any> = T extends unknown ? Omit<T, K> : never;

interface Todo { id: number; title: string; readonly createdAt: Date; done?: boolean }
type _o1 = Expect<Equal<MyOmit<Todo, 'id'>, { title: string; readonly createdAt: Date; done?: boolean }>>;
type _o2 = Expect<Equal<MyOmit2<Todo, 'id'>, { title: string; readonly createdAt: Date; done?: boolean }>>;
type _o3 = MyOmit<Todo, 'idd'>;                     // 官方风格：拼错不报错
// @ts-expect-error 严格版能发现拼写错误
type _o4 = StrictOmit<Todo, 'idd'>;

type Shape = { kind: 'circle'; r: number; id: string } | { kind: 'rect'; w: number; id: string };
type _o5 = Expect<Equal<keyof Omit<Shape, 'id'>, 'kind'>>; // 普通 Omit：r / w 全丢了
type _o6 = Expect<Equal<DistributiveOmit<Shape, 'id'>, { kind: 'circle'; r: number } | { kind: 'rect'; w: number }>>;
```

**讲解要点**：
1. 先说 `Exclude<keyof T, K>` 得到剩余键，再 `Pick`；Pick 是同态的，修饰符保留。
2. 官方 Omit 的 K 是 `keyof any` 而不是 `keyof T`，是为了允许「剔除可能不存在的键」，代价是不防拼写错误，可补一个 `StrictOmit`。
3. 作用于联合类型时 `keyof` 只取公共键，会丢字段，要用分布式条件类型包一层。

### 17.4 API 请求函数：入参出参都能推导

**目标**：调用 `request('GET /users/:id', { params: { id: '1' } })` 时，路由名有补全、`params/query/body` 按路由校验、返回值自动是对应的响应类型；没有必填参数的接口可以省略第二个参数。

```ts
interface User { id: string; name: string; age: number }

// 1. 路由表：唯一的类型数据源（可由 OpenAPI 自动生成）
interface ApiSchema {
  'GET /users': { query?: { page?: number; size?: number }; response: { list: User[]; total: number } };
  'GET /users/:id': { response: User };
  'POST /users': { body: Omit<User, 'id'>; response: User };
  'PUT /users/:id': { body: Partial<Omit<User, 'id'>>; response: User };
  'DELETE /users/:id': { response: { ok: boolean } };
}
type ApiKey = keyof ApiSchema;

// 2. 从路由字符串中解析路径参数名：'/users/:id' -> 'id'
type PathParams<P extends string> =
  P extends `${string}:${infer Param}/${infer Rest}` ? Param | PathParams<Rest>
  : P extends `${string}:${infer Param}` ? Param
  : never;

// 3. 有路径参数则要求 params，没有则不出现 params 字段
type ParamsOf<K extends string> =
  [PathParams<K>] extends [never] ? {} : { params: Record<PathParams<K>, string> };

// 4. 入参 = 路由定义中除 response 外的字段 + 路径参数
type RequestOptions<K extends ApiKey> = Omit<ApiSchema[K], 'response'> & ParamsOf<K>;

// 5. 没有必填字段时第二个参数可省略（{} 能赋给它 => 所有字段可选）
type RequestArgs<K extends ApiKey> =
  {} extends RequestOptions<K> ? [options?: RequestOptions<K>] : [options: RequestOptions<K>];

// 6. 出参：直接索引响应类型
type ResponseOf<K extends ApiKey> = ApiSchema[K]['response'];

/** 内部统一的入参形态，实现层用（外部类型已在签名上保证正确） */
interface RawOptions {
  params?: Record<string, string>;
  query?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
}

async function request<K extends ApiKey>(key: K, ...[options]: RequestArgs<K>): Promise<ResponseOf<K>> {
  const [method, rawPath] = key.split(' ') as [string, string];
  const opts: RawOptions = options ?? {};
  // 替换路径参数
  const path = rawPath.replace(/:(\w+)/g, (_, name: string) => encodeURIComponent(opts.params?.[name] ?? ''));
  // 拼接 query，过滤 undefined
  const search = new URLSearchParams();
  Object.entries(opts.query ?? {}).forEach(([k, v]) => { if (v !== undefined) search.set(k, String(v)); });
  const qs = search.size ? `?${search}` : '';
  const res = await fetch(path + qs, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  });
  if (!res.ok) throw new Error(`${res.status} ${key}`);
  return (await res.json()) as ResponseOf<K>;
}

// ---------- 使用效果 ----------
async function demo() {
  const page = await request('GET /users', { query: { page: 1 } });
  type _1 = Expect<Equal<typeof page, { list: User[]; total: number }>>;
  await request('GET /users');                             // 无必填参数，可省略

  const u = await request('GET /users/:id', { params: { id: '1' } });
  type _2 = Expect<Equal<typeof u, User>>;

  await request('PUT /users/:id', { params: { id: '1' }, body: { age: 18 } });

  // @ts-expect-error 缺少 params
  await request('GET /users/:id');
  // @ts-expect-error body 缺少 name / age
  await request('POST /users', { body: {} });
  // @ts-expect-error 路由不存在
  await request('GET /orders');
}
```

**讲解要点**：
1. **单一数据源**：所有接口的入参出参集中在 `ApiSchema`，实际项目可由 OpenAPI/Swagger 用 `openapi-typescript` 生成，前后端契约自动同步。
2. **泛型 K 约束为路由键**，所有入参出参类型都通过 `ApiSchema[K]` 索引得到，调用时 K 由第一个参数字面量推断。
3. **模板字面量 + infer** 从路径中解析参数名，自动要求 `params`。
4. **剩余参数元组**实现「有必填才必须传」：`{} extends Options` 判断是否全部可选，返回 `[options?: X]` 或 `[options: X]`。
5. 实现内部用一个宽松的 `RawOptions` 接住参数，**类型安全由函数签名保证**，实现内部的少量断言是合理的边界；响应体是否真的符合类型，生产中可再加 zod 运行时校验。

**追问**：

- 「如何和 axios 拦截器统一的 `{ code, data, msg }` 外壳配合？」——在 `ResponseOf` 外层包 `ApiResult<ResponseOf<K>>`，或在拦截器中解包后返回 data。
- 「和 tRPC / 生成 SDK 方案比？」——tRPC 直接复用后端 TS 类型，适合全栈 TS 团队；路由表方案适合后端非 TS、以 OpenAPI 为契约的团队。
- 简化版（不解析路径参数）：`function request<K extends keyof Api>(url: K, data: Api[K]['req']): Promise<Api[K]['res']>`，面试先写这个，再逐步增强。

---

## 18. 速记清单

| 问题 | 一句话答案 |
|---|---|
| interface vs type | type 能表达任意类型；interface 只描述对象，支持声明合并，extends 冲突报错 |
| any vs unknown | any 关闭检查且传染；unknown 接收一切但必须收窄后使用 |
| never 用途 | 抛错函数返回、穷尽检查、条件类型中过滤联合成员 |
| 分布式条件类型 | 裸类型参数遇联合逐个计算；`[T]` 包裹阻止 |
| infer | 条件类型中的模式匹配变量，逆变位置推断为交叉 |
| 同态映射 | `[K in keyof T]` 保留修饰符，数组映射后仍是数组 |
| Omit 实现 | `Pick<T, Exclude<keyof T, K>>`，联合类型用分布式版 |
| Awaited | 递归解包 thenable |
| satisfies | 校验结构但保留推断的精确类型 |
| as const | 最窄字面量 + 递归 readonly；5.0 有 `const T` 泛型参数 |
| 协变 / 逆变 | 返回值协变，参数逆变；方法简写参数双变，回调用属性写法 |
| strict | 一组开关，核心 strictNullChecks / noImplicitAny |
| moduleResolution | 打包项目 bundler，Node 包 nodenext |
| .d.ts | 有 export 是模块需 declare global；模块增强靠声明合并 |
| 用类型约束业务 | 可辨识联合消灭非法状态、路由表驱动的类型安全请求、常量派生类型 |
