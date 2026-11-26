# 前端面试知识点详解 · 02 JavaScript

> 对应总大纲：[`../frontend-interview-outline.md`](../frontend-interview-outline.md) 第 3 节。
> 侧重点：**语言机制的理解深度 + 手写能力**。JS 是前端面试必考模块，一面几乎都从这里开始。
> 考频标注：★★★ 必考 / ★★ 常考 / ★ 偶考。每个知识点按「是什么 / 原理 → 代码示例 → 面试答题要点 → 易错点 / 追问」组织。
> 手写题中标注「✅ 已用 Node 24 验证」的代码均实际运行过测试用例（Promise 实现还跑通了官方 Promises/A+ 872 条用例）。

---

## 目录

- [3.1 语言核心](#31-语言核心)
  - [3.1.1 数据类型与类型判断 ★★★](#311-数据类型与类型判断-)
  - [3.1.2 隐式转换、== vs ===、Object.is ★★](#312-隐式转换--vs-objectis-)
  - [3.1.3 作用域、作用域链、闭包 ★★★](#313-作用域作用域链闭包-)
  - [3.1.4 this 绑定四规则 + 箭头函数 ★★★](#314-this-绑定四规则--箭头函数-)
  - [3.1.5 原型与原型链、继承、class 本质 ★★★](#315-原型与原型链继承class-本质-)
  - [3.1.6 执行上下文、变量提升、TDZ ★★](#316-执行上下文变量提升tdz-)
  - [3.1.7 深浅拷贝、structuredClone ★★](#317-深浅拷贝structuredclone-)
  - [3.1.8 垃圾回收、WeakMap / WeakRef ★★](#318-垃圾回收weakmap--weakref-)
- [3.2 异步 ★★★](#32-异步-)
  - [3.2.1 事件循环：浏览器 vs Node ★★★](#321-事件循环浏览器-vs-node-)
  - [3.2.2 Promise 状态机与组合方法 ★★★](#322-promise-状态机与组合方法-)
  - [3.2.3 async/await 本质 ★★★](#323-asyncawait-本质-)
  - [3.2.4 输出顺序题（3 道由浅入深）★★★](#324-输出顺序题3-道由浅入深)
- [3.3 ES6+ 与新特性](#33-es6-与新特性)
  - [3.3.1 let/const、解构、展开 ★★](#331-letconst解构展开-)
  - [3.3.2 Symbol、Iterator / Generator ★★](#332-symboliterator--generator-)
  - [3.3.3 Proxy / Reflect ★★★](#333-proxy--reflect-)
  - [3.3.4 模块化：ESM vs CommonJS ★★★](#334-模块化esm-vs-commonjs-)
  - [3.3.5 新 API（ES2022–ES2025）★★](#335-新-apies2022es2025)
- [3.4 手写题清单 ★★★](#34-手写题清单-)
  - [函数类：call/apply/bind、new、instanceof、柯里化、compose](#341-函数类)
  - [控制类：防抖、节流、并发控制、带重试的请求](#342-控制类)
  - [Promise 类：Promise A+、all/race、sleep、异步串行](#343-promise-类)
  - [数据类：深拷贝、扁平化、去重、LRU](#344-数据类)
  - [模式类：EventEmitter、简易响应式、虚拟 DOM 渲染](#345-模式类)
  - [解析类：模板渲染、URL 参数解析、千分位](#346-解析类)
- [附：复习自检清单](#附复习自检清单)

---

## 3.1 语言核心

### 3.1.1 数据类型与类型判断 ★★★

**是什么 / 原理**

- 8 种类型：7 种原始类型 `undefined`、`null`、`boolean`、`number`、`string`、`symbol`、`bigint`，加 1 种引用类型 `object`（数组、函数、Date、Map 等都属于 object）。
- 原始值不可变、按值比较；对象按引用比较。原始值调用方法时会临时**装箱**（`'a'.length` → `new String('a').length`）。
- 三种判断方式：

| 方式 | 原理 | 适用 | 缺陷 |
|---|---|---|---|
| `typeof` | 读取值的内部类型标签 | 原始类型、function | `typeof null === 'object'`（历史 bug：早期 null 的类型标签为 0，与对象相同）；数组/对象/Date 都是 `'object'` |
| `instanceof` | 沿左值原型链查找右值的 `prototype` | 引用类型、自定义类 | 原始值永远 false；跨 iframe/realm 失效；`Symbol.hasInstance` 可篡改 |
| `Object.prototype.toString.call(x)` | 读取内部 `[[Class]]` / `Symbol.toStringTag` | 最通用 | 自定义 `Symbol.toStringTag` 可伪造 |

**代码示例**

```js
typeof undefined;     // 'undefined'
typeof null;          // 'object'  ← 经典坑
typeof function(){};  // 'function'
typeof 10n;           // 'bigint'
typeof Symbol();      // 'symbol'

[] instanceof Array;  // true
[] instanceof Object; // true（原型链上有 Object.prototype）

// 通用类型判断工具
const getType = (x) => Object.prototype.toString.call(x).slice(8, -1).toLowerCase();
getType(null);        // 'null'
getType([]);          // 'array'
getType(new Date());  // 'date'
getType(/a/);         // 'regexp'

Array.isArray([]);    // 判断数组首选，可跨 realm
Number.isNaN(NaN);    // true；全局 isNaN('abc') 也是 true（会先转数字），别用
```

**面试答题要点**

1. 7 种原始类型 + object，ES2020 新增 bigint，ES6 新增 symbol。
2. `typeof` 适合原始类型，但 null 返回 `'object'`，函数返回 `'function'`。
3. `instanceof` 基于原型链，不能判断原始值，跨 iframe 不可靠。
4. 最准确的是 `Object.prototype.toString.call`，数组优先 `Array.isArray`。

**易错点 / 追问**

- `typeof` 未声明的变量返回 `'undefined'` 不报错，但在 TDZ 中的 `let` 变量会报 ReferenceError。
- `0.1 + 0.2 !== 0.3`：IEEE 754 双精度浮点误差，比较用 `Math.abs(a - b) < Number.EPSILON`；大整数超过 `Number.MAX_SAFE_INTEGER (2^53-1)` 用 BigInt。
- 追问「null 和 undefined 区别」：undefined 是「未赋值」，null 是「有意的空对象」；`Number(null) === 0`，`Number(undefined)` 是 NaN。

---

### 3.1.2 隐式转换、== vs ===、Object.is ★★

**是什么 / 原理**

- **ToPrimitive**：对象参与运算时先转原始值。优先调用 `[Symbol.toPrimitive](hint)`；否则 hint 为 `number`/`default` 时先 `valueOf` 后 `toString`，hint 为 `string` 时反过来（Date 的 default 为 string）。
- `+` 运算：任一侧（转原始值后）是字符串则拼接，否则转数字相加。其他算术运算符一律转数字。
- `==` 规则（抽象相等）：
  1. 类型相同 → 同 `===`；
  2. `null == undefined` 为 true，它们与其他任何值都不等；
  3. 数字 vs 字符串 → 字符串转数字；
  4. 布尔参与 → 布尔先转数字；
  5. 对象 vs 原始值 → 对象 ToPrimitive。
- `===` 不转换类型，但 `NaN !== NaN`、`+0 === -0`。`Object.is` 修正了这两点（React 的 state 比较就用它）。

**代码示例**

```js
[] + {};          // '[object Object]'  ([] → '', {} → '[object Object]')
1 + '2' - 1;      // 11  ('12' - 1)
[] == ![];        // true：![] → false → 0；[] → '' → 0
null == 0;        // false（null 只等于 undefined）
null >= 0;        // true（关系运算会把 null 转成 0）
'b' + 'a' + +'a' + 'a'; // 'baNaNa'

Object.is(NaN, NaN); // true
Object.is(0, -0);    // false

// 让 a == 1 && a == 2 && a == 3 成立
const a = { i: 1, valueOf() { return this.i++; } };
a == 1 && a == 2 && a == 3; // true
```

**面试答题要点**

1. 对象转原始值走 `Symbol.toPrimitive` → `valueOf` → `toString`。
2. `==` 会类型转换，核心是「最终往数字比」，null/undefined 是特例。
3. 工程上一律用 `===`，唯一例外 `x == null` 同时判断 null 和 undefined。
4. `Object.is` 与 `===` 的区别只有 NaN 和 ±0 两处。

**易错点 / 追问**

- `if ([])`、`if ({})` 都是真：转布尔只看是否在 falsy 列表（`false 0 -0 0n '' null undefined NaN`），不走 ToPrimitive。
- 追问「`[1,2] + [3]` 结果」：`'1,23'`。

---

### 3.1.3 作用域、作用域链、闭包 ★★★

**是什么 / 原理**

- **作用域**：变量的可访问范围。JS 是**词法（静态）作用域**——函数的作用域在**定义时**确定，与调用位置无关。分全局、函数、块级（`let/const/class`）三种。
- **作用域链**：每个执行上下文的词法环境持有对外层环境的引用（`[[OuterEnv]]`），查找变量时逐层向外，直到全局，找不到就 ReferenceError。
- **闭包**：函数与其定义时词法环境的组合。函数在定义它的作用域之外执行时，仍能访问那个作用域里的变量。
- **用途**：数据私有化、函数工厂、柯里化、防抖节流里保存 timer、模块模式、React Hooks（依赖闭包存储渲染时的值）。
- **内存泄漏**：闭包引用的外层变量不会被回收。V8 中同一外层函数里的多个闭包**共享**一个上下文对象，只要其中一个闭包存活，所有被任何闭包捕获的变量都存活。

**代码示例**

```js
// 1. 私有变量
function createCounter() {
  let count = 0; // 外部无法直接访问
  return { inc: () => ++count, get: () => count };
}

// 2. 经典循环问题
for (var i = 0; i < 3; i++) setTimeout(() => console.log(i)); // 3 3 3
for (let i = 0; i < 3; i++) setTimeout(() => console.log(i)); // 0 1 2（每次迭代新绑定）
for (var i = 0; i < 3; i++) ((j) => setTimeout(() => console.log(j)))(i); // IIFE 闭包修复

// 3. 泄漏：bigData 被 unused 捕获，因共享上下文，handler 存活即 bigData 存活
function setup() {
  const bigData = new Array(1e6).fill('*');
  const unused = () => bigData.length;
  return function handler() { /* 不使用 bigData */ };
}
window.onresize = setup(); // bigData 无法回收
```

**面试答题要点**

1. JS 是词法作用域，作用域在定义时确定。
2. 闭包 = 函数 + 定义时的词法环境，本质是作用域链的保留。
3. 用途：私有变量、函数工厂、柯里化/防抖、模块化、React Hooks。
4. 风险：被捕获的变量常驻内存；用完要解除引用（移除监听器、置 null）。
5. 现代引擎会对未被任何闭包引用的变量做优化回收，但共享上下文仍可能导致意外持有。

**易错点 / 追问**

- 追问「React 中的闭包陷阱」：`useEffect` / `setInterval` 回调捕获的是旧渲染的 state，需用依赖数组、函数式更新 `setX(x => x + 1)` 或 `useRef`。
- 「所有函数都是闭包」在理论上成立（都捕获了词法环境），面试回答时说「通常指在外部作用域执行仍访问内部变量的函数」。

---

### 3.1.4 this 绑定四规则 + 箭头函数 ★★★

**是什么 / 原理**

`this` 在**调用时**确定（箭头函数除外），按优先级从高到低：

| 规则 | 形式 | this 指向 |
|---|---|---|
| new 绑定 | `new Foo()` | 新创建的实例 |
| 显式绑定 | `call / apply / bind` | 传入的对象（null/undefined 在非严格模式下变为全局对象） |
| 隐式绑定 | `obj.foo()` | 调用点前的对象 `obj` |
| 默认绑定 | `foo()` | 非严格模式 globalThis，严格模式 `undefined` |

- **箭头函数**没有自己的 `this`、`arguments`、`prototype`，不能 `new`；`this` 取定义时外层作用域的 `this`，且 `call/bind` 无法改变。
- 优先级：new > bind > 隐式 > 默认。`bind` 后的函数再 `new`，`this` 指向新实例（bind 的 this 被忽略，但预置参数保留）。

**代码示例**

```js
const obj = {
  name: 'obj',
  normal() { return this.name; },
  arrow: () => this?.name,          // 定义在对象字面量中，外层是模块/全局作用域
  delay() { setTimeout(() => console.log(this.name)); }, // 'obj'，箭头函数继承 delay 的 this
};
obj.normal();          // 'obj'
const fn = obj.normal;
fn();                  // undefined（严格模式下 this 为 undefined 会报错）——隐式丢失
obj.arrow();           // undefined

// 隐式丢失的典型场景：回调传参
setTimeout(obj.normal, 0); // this 不是 obj

// 优先级：new > bind
function Foo(v) { this.v = v; }
const Bound = Foo.bind({ v: 'bound' });
new Bound(1).v; // 1
```

**面试答题要点**

1. this 由调用方式决定，四条规则按 new > 显式 > 隐式 > 默认的优先级。
2. 箭头函数没有自己的 this，取外层词法作用域的 this，不可被 call/bind 修改。
3. 隐式丢失：方法赋值给变量或作为回调传递后，变成默认绑定。
4. class 内部默认严格模式，方法单独调用 this 为 undefined，所以 React class 组件要 bind 或用箭头属性。

**易错点 / 追问**

- 对象字面量里写箭头函数方法拿不到对象本身——对象字面量**不构成作用域**。
- DOM 事件监听中 `this` 指向 `currentTarget`；用箭头函数则不是。
- 追问「`bind` 多次」：只有第一次生效，`fn.bind(a).bind(b)` 的 this 仍是 a。

---

### 3.1.5 原型与原型链、继承、class 本质 ★★★

**是什么 / 原理**

- 每个函数（箭头函数、方法简写除外）都有 `prototype` 对象；每个对象都有内部 `[[Prototype]]`（通过 `Object.getPrototypeOf` 或 `__proto__` 访问），指向其构造函数的 `prototype`。
- 访问属性时，自身没有就沿 `[[Prototype]]` 向上找，直到 `Object.prototype`，再往上是 `null`——这条链就是**原型链**。
- 关键等式：`obj.__proto__ === Ctor.prototype`、`Ctor.prototype.constructor === Ctor`、`Function.__proto__ === Function.prototype`、`Object.__proto__ === Function.prototype`、`Function.prototype.__proto__ === Object.prototype`。

**继承方式演进**

| 方式 | 做法 | 问题 |
|---|---|---|
| 原型链继承 | `Child.prototype = new Parent()` | 引用属性被所有实例共享；不能向父构造传参 |
| 构造函数继承 | `Parent.call(this)` | 拿不到父原型上的方法 |
| 组合继承 | 上面两者结合 | 父构造调用两次 |
| **寄生组合继承** | `Parent.call(this)` + `Child.prototype = Object.create(Parent.prototype)` | 最优（ES5 时代标准答案） |
| class extends | 语法糖 + 额外语义 | ES6+ 首选 |

**代码示例**

```js
// 寄生组合继承
function Animal(name) { this.name = name; this.tags = []; }
Animal.prototype.say = function () { return `I am ${this.name}`; };

function Dog(name, breed) {
  Animal.call(this, name);          // 继承实例属性
  this.breed = breed;
}
Dog.prototype = Object.create(Animal.prototype); // 继承原型方法，且不调用父构造
Dog.prototype.constructor = Dog;                  // 修复 constructor 指向
Object.setPrototypeOf(Dog, Animal);               // 继承静态方法（class 也会这么做）

// class 写法
class Cat extends Animal {
  #secret = 'private';               // 真·私有字段
  static count = 0;                  // 静态字段
  constructor(name) {
    super(name);                     // 必须先调用 super 才能用 this
    Cat.count++;
  }
}
```

**class 不只是语法糖**：
- class 必须 `new` 调用，否则报错；内部默认严格模式；
- 类声明有 TDZ，不提升到可用；方法不可枚举；
- 子类 `this` 由父类构造创建（所以必须先 `super()`），这使得继承 `Array`、`Error` 等内置对象成为可能，ES5 写法做不到；
- 支持 `#private` 私有字段、`static` 块等新语义。

**面试答题要点**

1. 对象通过 `[[Prototype]]` 关联到构造函数的 `prototype`，属性查找沿原型链进行，终点 null。
2. 最优 ES5 继承是寄生组合继承：`call` 继承属性 + `Object.create` 继承方法。
3. class 本质是构造函数 + 原型的语法糖，但多了强制 new、严格模式、TDZ、方法不可枚举、内置对象可继承、私有字段等语义。
4. 原型链过长影响查找性能；不要修改内置原型（污染全局）。

**易错点 / 追问**

- `Object.create(null)` 创建的对象没有原型，适合做纯字典（没有 `toString` 等干扰属性），但 `instanceof Object` 为 false。
- 追问「原型污染」：`merge(target, JSON.parse('{"__proto__":{"isAdmin":true}}'))` 会污染 `Object.prototype`，合并时要过滤 `__proto__`、`constructor`、`prototype`。

---

### 3.1.6 执行上下文、变量提升、TDZ ★★

**是什么 / 原理**

- **执行上下文**：代码运行的环境，分全局、函数、eval 三种，由**调用栈**管理。每个上下文包含：词法环境（`let/const/class`/函数声明）、变量环境（`var`）、this 绑定。
- 创建分两阶段：
  1. **创建阶段**：扫描声明。`var` 绑定创建并初始化为 `undefined`；函数声明整体创建（可提前调用）；`let/const/class` 绑定创建但**未初始化**。
  2. **执行阶段**：逐行执行、赋值。
- **TDZ（暂时性死区）**：从块开始到 `let/const` 声明语句执行之前，访问该变量抛 ReferenceError。所以「let 不会提升」的说法不准确，准确的说法是「提升了但未初始化」。

**代码示例**

```js
console.log(a);   // undefined（var 提升并初始化）
var a = 1;

foo();            // 'foo'（函数声明整体提升）
function foo() { console.log('foo'); }

bar();            // TypeError: bar is not a function（只提升了 var bar）
var bar = function () {};

let x = 'outer';
{
  console.log(x); // ReferenceError：块内的 x 已提升，处于 TDZ，遮蔽了外层 x
  let x = 'inner';
}

// 函数声明优先级高于同名 var 声明（但会被后续赋值覆盖）
// 注意：仅限普通脚本；ESM 模块顶层的函数声明按词法声明处理，同名 var 会直接 SyntaxError
console.log(typeof f); // 'function'
var f = 1;
function f() {}
console.log(typeof f); // 'number'
```

**面试答题要点**

1. 执行上下文分创建和执行两阶段，提升发生在创建阶段。
2. var 提升并初始化为 undefined；函数声明整体提升；let/const/class 提升但未初始化，形成 TDZ。
3. 函数声明优先于变量声明。
4. 块级作用域 + TDZ 让「先用后声明」变成显式错误，更安全。

**易错点 / 追问**

- 块内的函数声明在非严格模式下行为因历史兼容很混乱，避免在 if 块内声明函数。
- `typeof` 一个 TDZ 中的变量也会报错。
- 默认参数也有 TDZ：`function f(a = b, b = 1) {}` 调用 `f()` 报错。

---

### 3.1.7 深浅拷贝、structuredClone ★★

**是什么 / 原理**

- **浅拷贝**：只复制第一层，嵌套对象仍共享引用。方式：`{...obj}`、`Object.assign`、`arr.slice()`、`Array.from`。
- **深拷贝**：递归复制所有层级。方式：
  - `JSON.parse(JSON.stringify(x))`：丢失 `undefined`/函数/Symbol，Date 变字符串，Map/Set/RegExp 变 `{}`，NaN/Infinity 变 null，**循环引用直接报错**。
  - `structuredClone(x)`（浏览器与 Node 17+ 原生）：基于结构化克隆算法（与 `postMessage` 同源），支持循环引用、Date、RegExp、Map、Set、ArrayBuffer、Blob 等；**不支持函数、DOM 节点、Symbol 键**，会丢失原型（class 实例变普通对象）、getter/setter 被求值。
  - 手写递归（见 [3.4 深拷贝](#344-数据类)）：可按需处理原型、Symbol 键、循环引用。

**代码示例**

```js
const src = { d: new Date(0), m: new Map([[1, 'a']]), n: { deep: 1 } };
src.self = src;

const shallow = { ...src };
shallow.n === src.n;            // true，共享

const deep = structuredClone(src);
deep.self === deep;             // true，循环引用保留
deep.d instanceof Date;         // true

structuredClone({ f() {} });    // DataCloneError：函数不可克隆
JSON.stringify(src);            // TypeError：循环引用
```

**面试答题要点**

1. 浅拷贝只复制一层，深拷贝递归复制。
2. JSON 方案简单但缺陷多：丢 undefined/函数/Symbol、Date 变字符串、循环引用报错。
3. 现代首选 `structuredClone`，支持循环引用和大部分内置类型，不支持函数和 DOM、丢失原型。
4. 手写深拷贝的关键：类型分支 + `WeakMap` 解决循环引用。

**易错点 / 追问**

- 追问「为什么用 WeakMap 而不是 Map 记录已拷贝对象」：键是弱引用，拷贝结束后不阻止源对象回收。
- 递归过深会栈溢出，极端场景可改为栈/队列迭代。

---

### 3.1.8 垃圾回收、WeakMap / WeakRef ★★

**是什么 / 原理**

- **可达性**：从根（全局对象、调用栈中的变量、活跃闭包）出发能访问到的对象是活的，其余回收。
- **引用计数**（早期 IE）：循环引用无法回收，已淘汰。
- **标记清除**：从根遍历标记可达对象，清除未标记的。可解决循环引用，现代引擎的基础。配合**标记整理**减少碎片。
- **V8 分代回收**（基于「大部分对象朝生夕死」的假说）：
  - **新生代**（小，1–16MB 级别）：Scavenge 算法，空间对半分 From/To，存活对象复制到 To 后互换；存活两次的对象**晋升**到老生代。
  - **老生代**：标记清除 + 标记整理。
  - 优化：**增量标记**（分片执行，减少停顿）、**并发标记/并行回收**（Orinoco，辅助线程工作）、**惰性清理**。
- **弱引用**：
  - `WeakMap/WeakSet`：键必须是对象（或非注册 Symbol），弱持有键，不可遍历、无 size。用于给对象挂元数据（DOM → 数据、Vue3 的 `targetMap`、深拷贝的 seen 表）。
  - `WeakRef`：对对象的弱引用，`deref()` 可能返回 undefined；`FinalizationRegistry`：对象被回收后的回调。时机不确定，只用于缓存等可选优化。

**代码示例**

```js
// WeakMap 关联私有数据：元素被移除后数据自动可回收
const meta = new WeakMap();
function bind(el) { meta.set(el, { clicks: 0 }); }

// WeakRef 缓存
const cache = new Map(); // key → WeakRef
function getCached(key, create) {
  const v = cache.get(key)?.deref();
  if (v) return v;
  const obj = create();
  cache.set(key, new WeakRef(obj));
  return obj;
}
const registry = new FinalizationRegistry((key) => cache.delete(key)); // 回收后清理 Map 中的空壳
```

**常见内存泄漏**：意外全局变量、未清理的定时器/事件监听、闭包持有大对象、脱离 DOM 但仍被 JS 引用的节点、无上限增长的 Map 缓存、未取消的订阅。排查：Chrome DevTools Memory 面板 → 堆快照对比（Comparison）、Allocation timeline，查找 Detached 节点。

**面试答题要点**

1. 现代引擎基于可达性 + 标记清除，引用计数因循环引用被淘汰。
2. V8 分代：新生代 Scavenge 复制算法，老生代标记清除/整理，存活对象会晋升。
3. 通过增量、并发、并行标记降低 GC 停顿。
4. WeakMap 键弱引用、不可遍历，适合挂元数据；WeakRef 适合可丢弃缓存，回收时机不确定。
5. 能说出常见泄漏场景和 DevTools 排查方法。

**易错点 / 追问**

- WeakMap 是**键**弱引用，值是强引用；若值反过来引用键，引擎通过 ephemeron 语义处理，不会泄漏。
- 追问「为什么 WeakMap 不能遍历」：因为 GC 时机不确定，遍历结果会不确定。

---

## 3.2 异步 ★★★

### 3.2.1 事件循环：浏览器 vs Node ★★★

**是什么 / 原理**

JS 主线程单线程，通过事件循环实现异步。

**浏览器模型**：
1. 执行一个**宏任务**（task）：script 整体、`setTimeout/setInterval`、I/O、UI 事件、`MessageChannel`；
2. 清空**微任务**队列（microtask）：`Promise.then/catch/finally`、`await` 之后的代码、`queueMicrotask`、`MutationObserver`。微任务执行中产生的新微任务也在本轮清空；
3. 视情况进行**渲染**：`requestAnimationFrame` 回调 → 样式计算 → 布局 → 绘制（约 16.6ms 一帧，不是每轮都渲染）；
4. 空闲时可执行 `requestIdleCallback`；回到 1。

> 新规范中「宏任务」已细分为多个任务队列（用户交互队列优先级更高），面试说「宏任务」即可，能提到优先级区分是加分项。

**Node 模型（libuv）**：每轮循环分 6 个阶段：

```
   ┌──> timers          setTimeout / setInterval 到期回调
   │    pending cbs     上一轮延迟的 I/O 错误回调
   │    idle, prepare   内部使用
   │    poll            获取新 I/O 事件，执行 I/O 回调；无事可做时在此阻塞等待
   │    check           setImmediate
   └─── close cbs       socket.on('close') 等
```

- Node 11+ 起与浏览器一致：**每执行完一个宏任务回调就清空微任务**（之前是每个阶段结束才清空）。
- `process.nextTick` 队列优先级**高于** Promise 微任务队列。
- `setTimeout(fn, 0)` vs `setImmediate`：在主模块中顺序不确定（取决于进入循环时 1ms 是否已到）；在 I/O 回调中 `setImmediate` 一定先执行（poll 之后紧接 check）。

**代码示例**

```js
// Node 中
setTimeout(() => console.log('timeout'));
setImmediate(() => console.log('immediate'));
Promise.resolve().then(() => console.log('promise'));
process.nextTick(() => console.log('nextTick'));
// 输出：nextTick → promise → timeout/immediate（这两者顺序不确定）

require('fs').readFile(__filename, () => {
  setTimeout(() => console.log('timeout'));
  setImmediate(() => console.log('immediate')); // I/O 回调中：immediate 一定先于 timeout
});
```

**面试答题要点**

1. 单线程 + 事件循环：执行一个宏任务 → 清空全部微任务 → 可能渲染 → 下一个宏任务。
2. 微任务：Promise 回调、await 后续、queueMicrotask、MutationObserver；宏任务：script、定时器、I/O、UI 事件、MessageChannel。
3. Node 分 timers/poll/check 等 6 阶段，nextTick 优先于 Promise；Node 11 起微任务执行时机与浏览器对齐。
4. rAF 在渲染前执行，适合动画；不要用 setTimeout 做动画。
5. 微任务无限递归会阻塞渲染（页面卡死），宏任务递归则不会。

**易错点 / 追问**

- `setTimeout(fn, 0)` 实际最小延迟约 1ms，嵌套超过 5 层后浏览器强制 ≥4ms；后台标签页会被节流到 ≥1s。
- 追问「Vue 的 nextTick 原理」：优先用 Promise.then（微任务），降级 MutationObserver → setImmediate → setTimeout，在同一 tick 内批量更新 DOM 后执行回调。
- 追问「React 调度为什么用 MessageChannel 而非 setTimeout」：避免 4ms 最小延迟，且是宏任务能让出主线程给渲染。

---

### 3.2.2 Promise 状态机与组合方法 ★★★

**是什么 / 原理**

- 三个状态：`pending` → `fulfilled` 或 `pending` → `rejected`，**一旦改变不可逆**。
- `then` 注册回调并**返回新 Promise**，实现链式调用：回调返回普通值 → 新 Promise 以该值 fulfilled；返回 Promise/thenable → 新 Promise **跟随**其状态；抛异常 → 新 Promise rejected。
- `then` 的回调总是**异步**执行（微任务），即使 Promise 已经 settled。
- 非函数参数会被忽略，产生**值穿透**：`Promise.resolve(1).then(2).then(console.log)` 输出 1。
- 组合方法对比：

| 方法 | fulfilled 条件 | rejected 条件 | 返回值 | 典型用途 |
|---|---|---|---|---|
| `all` | 全部成功 | 任一失败（立即） | 结果数组（按输入顺序） | 并行请求全部依赖 |
| `allSettled` | 全部 settled 后总是成功 | 不会 | `{status, value/reason}[]` | 批量操作出报告 |
| `race` | 第一个 settled 是成功 | 第一个 settled 是失败 | 首个结果 | 超时控制 |
| `any` | 任一成功 | 全部失败 | 首个成功值 / `AggregateError` | 多源择优（CDN 测速） |

**代码示例**

```js
// 超时控制
const withTimeout = (p, ms) =>
  Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), ms))]);

// 链式：返回 Promise 会被"展开"
Promise.resolve(1)
  .then((v) => new Promise((r) => setTimeout(() => r(v + 1), 100)))
  .then((v) => { throw new Error(`fail at ${v}`); })
  .catch((e) => e.message)   // 'fail at 2'，catch 之后链条恢复为 fulfilled
  .finally(() => console.log('cleanup')) // finally 不接收参数，不改变结果（除非抛错）
  .then(console.log);        // 'fail at 2'
```

**面试答题要点**

1. Promise 是状态机：三态、单向、不可逆。
2. then 返回新 Promise，回调返回值决定新 Promise 状态，返回 thenable 会被递归展开。
3. 回调在微任务中执行；未传函数会值穿透。
4. 能说清四个组合方法的区别和使用场景，尤其 all vs allSettled、race vs any。

**易错点 / 追问**

- `Promise.all` 失败后**其他请求不会被取消**，只是结果被忽略；真正取消需要 `AbortController`。
- `catch` 只能捕获它之前链路的错误；`try/catch` 无法捕获未 await 的 Promise 错误。未处理的 rejection 会触发 `unhandledrejection` 事件。
- 追问「then 第二个参数和 catch 的区别」：then 的 onRejected 捕获不到同一个 then 中 onFulfilled 抛的错，catch 可以。

---

### 3.2.3 async/await 本质 ★★★

**是什么 / 原理**

- `async` 函数**总是返回 Promise**：return 值被包装成 resolved Promise，抛错变 rejected。
- `await x` 相当于 `Promise.resolve(x).then(继续执行剩余代码)`：暂停函数执行并让出线程，后续代码作为微任务恢复。
- 本质是 **Generator + 自动执行器**：`async` ≈ `function*`，`await` ≈ `yield`，执行器自动调用 `next()` 并把 Promise 结果送回。这也是 Babel 转译 async 的方式（regenerator / co 库）。

**代码示例：用 Generator 实现 async**

```js
/**
 * 自动执行 Generator 函数，返回 Promise（co 库的核心思路）
 * @param {GeneratorFunction} genFn 内部用 yield 代替 await 的生成器函数
 * @returns {(...args) => Promise} 与 async 函数等价的函数
 */
function asyncToGenerator(genFn) {
  return function (...args) {
    const gen = genFn.apply(this, args);
    return new Promise((resolve, reject) => {
      // step：推进一步，把上一步的结果送回生成器
      function step(method, arg) {
        let result;
        try {
          result = gen[method](arg); // next(value) 或 throw(error)
        } catch (e) {
          return reject(e);          // 生成器内部未捕获的错误
        }
        const { value, done } = result;
        if (done) return resolve(value); // return 的值作为最终结果
        // 等待 yield 出的值，成功继续 next，失败把错误抛回生成器（让内部 try/catch 生效）
        Promise.resolve(value).then((v) => step('next', v), (e) => step('throw', e));
      }
      step('next');
    });
  };
}

const fetchUser = asyncToGenerator(function* (id) {
  const user = yield new Promise((r) => setTimeout(() => r({ id }), 100));
  return user.id;
});
fetchUser(7).then(console.log); // 7
```

**面试答题要点**

1. async 函数返回 Promise，await 暂停执行，后续代码进入微任务。
2. 本质是 Generator + 自动执行器：yield 暂停，执行器在 Promise 完成后调用 next 恢复。
3. 错误处理：用 try/catch 捕获 await 的 rejection，或在调用处 `.catch`。
4. 多个无依赖的 await 要并行：`await Promise.all([a(), b()])`，而非串行 await。

**易错点 / 追问**

- `forEach` 里写 `async` 回调不会等待（forEach 不处理返回的 Promise），用 `for...of` 串行或 `Promise.all(arr.map(...))` 并行。
- 顶层 await：仅 ESM 支持，会阻塞依赖该模块的模块执行。
- await 后跟非 Promise 值也会让出一次微任务。
- 追问「`return await` 有必要吗」：在 try/catch 内需要 `return await` 才能捕获错误；否则可省略。

---

### 3.2.4 输出顺序题（3 道由浅入深）

> 以下三题输出均已用 Node 24 实际运行确认（与现代 Chrome 一致）。

**解题通用步骤**：
1. 先执行所有同步代码（包括 `new Promise` 的执行器、async 函数里第一个 await 之前的代码、await 右侧的表达式）；
2. 记录微任务队列、宏任务队列的入队顺序；
3. 清空微任务（执行中新产生的微任务排到队尾，本轮继续执行）；
4. 取下一个宏任务，重复。

#### 题 1（基础）

```js
console.log('1');
setTimeout(() => console.log('2'), 0);
Promise.resolve().then(() => console.log('3'));
console.log('4');
```

**答案**：`1 4 3 2`

**解析**：同步输出 1、4；then 回调进微任务，setTimeout 回调进宏任务；同步结束后先清空微任务输出 3，再执行宏任务输出 2。

#### 题 2（async/await 经典题）

```js
async function async1() {
  console.log('A');
  await async2();
  console.log('B');
}
async function async2() { console.log('C'); }
console.log('D');
setTimeout(() => console.log('E'), 0);
async1();
new Promise((resolve) => {
  console.log('F');
  resolve();
}).then(() => console.log('G'))
  .then(() => console.log('H'));
console.log('I');
```

**答案**：`D A C F I B G H E`

**解析**：

| 步骤 | 动作 | 输出 | 微任务队列 | 宏任务队列 |
|---|---|---|---|---|
| 1 | 同步 log | D | | |
| 2 | setTimeout 入队 | | | E |
| 3 | 调用 async1，同步打印 A；await 右侧 async2() 同步执行打印 C；await 让出，"B 之后的代码" 入微任务 | A C | [B] | E |
| 4 | Promise 执行器同步执行，resolve 后 then(G) 入队 | F | [B, G] | E |
| 5 | 同步 log | I | [B, G] | E |
| 6 | 清空微任务：B；G，G 执行完 then(H) 入队；H | B G H | | E |
| 7 | 宏任务 | E | | |

关键点：`await` 右侧表达式是**同步**执行的；`new Promise` 执行器同步；`.then(H)` 要等 G 执行完才入队。

#### 题 3（进阶：async 函数返回 Promise + 多级 then + 宏任务中的微任务）

```js
async function a1() {
  console.log(1);
  await a2();
  console.log(2);
}
async function a2() {
  console.log(3);
  return Promise.resolve();   // 注意：async 函数显式返回一个 Promise
}
setTimeout(() => {
  console.log(4);
  Promise.resolve().then(() => console.log(5));
}, 0);
setTimeout(() => console.log(6), 0);
a1();
Promise.resolve()
  .then(() => console.log(7))
  .then(() => console.log(8))
  .then(() => console.log(9))
  .then(() => console.log(10));
queueMicrotask(() => console.log(11));
console.log(12);
```

**答案**：`1 3 12 7 11 8 2 9 10 4 5 6`

**解析**：

- **同步阶段**：两个 setTimeout 入宏任务队列 [T4, T6]；a1 打印 1，调用 a2 打印 3。a2 是 async 函数且 return 了一个 Promise——**async 函数的返回 Promise 用另一个 Promise 来 resolve 时，规范会安排一个 `NewPromiseResolveThenableJob`**，多花 2 个微任务 tick 才能完成。然后 a1 中 `await <a2的返回Promise>` 注册等待。打印 12。
  - 微任务队列：`[ThenableJob(a2), log7, log11]`
- **微任务 tick 1**：ThenableJob 调用内部 Promise 的 then → 因其已 resolved，入队 resolveA2；输出 7 → then(8) 入队；输出 11。队列：`[resolveA2, log8]`
- **tick 2**：resolveA2 把 a2 的返回 Promise 置为 fulfilled → a1 的 await 继续执行入队；输出 8 → then(9) 入队。队列：`[a1继续, log9]`
- **tick 3**：输出 2；输出 9 → then(10) 入队；输出 10。微任务清空。
- **宏任务 T4**：输出 4，产生微任务 log5，**该宏任务结束后立即清空微任务**输出 5。
- **宏任务 T6**：输出 6。

**关键点**：
1. `await` 一个原生 Promise 只需 1 个 tick（ES2019 优化后，旧版 V8 需要 3 个）；
2. `resolve(一个 thenable)` 或 async 函数 `return 一个 Promise` 需额外 2 个 tick；若 a2 改为 `return undefined`，2 会排在 7 前面，输出变为 `1 3 12 2 7 11 8 9 10 4 5 6`；
3. 每个宏任务结束都会清空微任务，所以 5 在 6 之前。

---

## 3.3 ES6+ 与新特性

### 3.3.1 let/const、解构、展开 ★★

**是什么 / 原理**

- `let/const`：块级作用域、TDZ、不可重复声明、全局声明不挂到 `window`。`const` 保证**绑定**不变，不保证对象内容不变（冻结用 `Object.freeze`，且只冻结一层）。
- 解构：按模式提取值，支持默认值（仅当值为 `undefined` 时生效，`null` 不触发）、重命名、嵌套、剩余。
- 展开 `...`：数组展开基于**迭代器**（可展开 Set、Map、字符串）；对象展开只复制**自身可枚举**属性（含 Symbol），是浅拷贝，会触发 getter。

**代码示例**

```js
const { a = 1, b: { c } = {}, ...rest } = { a: null, b: { c: 3 }, d: 4, e: 5 };
// a === null（null 不触发默认值），c === 3，rest = { d: 4, e: 5 }

const [x, , y = 10, ...others] = [1, 2, undefined, 4, 5]; // x=1, y=10, others=[4,5]
[x2, y2] = [y2, x2];                                       // 交换变量（需先声明）

function f({ url, method = 'GET' } = {}) {}                 // 参数解构 + 整体默认值，防止 f() 报错

[...'hi'];                    // ['h', 'i']
[...new Set([1, 1, 2])];      // [1, 2]
const merged = { ...defaults, ...options }; // 后者覆盖前者
```

**面试答题要点**

1. let/const 块级作用域、TDZ、不可重复声明；const 锁定绑定而非值。
2. 解构默认值只在严格等于 undefined 时生效。
3. 数组展开依赖迭代器协议，对象展开复制自身可枚举属性，都是浅拷贝。

**易错点 / 追问**

- 解构 `null`/`undefined` 直接报错：`const { a } = null` → TypeError。
- `Object.freeze` 是浅冻结，深冻结需递归。

---

### 3.3.2 Symbol、Iterator / Generator ★★

**是什么 / 原理**

- **Symbol**：唯一的原始值，用作对象键可避免命名冲突；`Symbol.for(key)` 全局注册可共享。Symbol 键不会出现在 `for...in`、`Object.keys`、`JSON.stringify` 中，用 `Object.getOwnPropertySymbols` 或 `Reflect.ownKeys` 获取。
- **内置 Symbol**（元编程钩子）：`Symbol.iterator`（for...of）、`Symbol.asyncIterator`（for await）、`Symbol.toPrimitive`、`Symbol.hasInstance`（instanceof）、`Symbol.toStringTag`。
- **迭代器协议**：对象有 `next()` 方法，返回 `{ value, done }`。**可迭代协议**：对象有 `[Symbol.iterator]()` 返回迭代器。`for...of`、展开、解构、`Array.from`、`Promise.all`、`new Map(iterable)` 都依赖它。
- **Generator**：`function*` 调用返回生成器对象（既是迭代器也是可迭代对象），`yield` 暂停并产出值，`next(v)` 恢复并把 v 作为 yield 表达式的值；支持 `return()`、`throw()`、`yield*` 委托。用于惰性序列、状态机、async 的底层实现、redux-saga。

**代码示例**

```js
// 让对象可迭代
const range = {
  from: 1, to: 3,
  *[Symbol.iterator]() {               // 用 Generator 实现迭代器最简洁
    for (let i = this.from; i <= this.to; i++) yield i;
  },
};
[...range]; // [1, 2, 3]

// 双向通信
function* gen() {
  const x = yield 1;    // 第一次 next() 停在这里，产出 1
  const y = yield x * 2;
  return x + y;
}
const g = gen();
g.next();    // { value: 1, done: false }（第一次 next 的参数会被忽略）
g.next(5);   // { value: 10, done: false }，x = 5
g.next(7);   // { value: 12, done: true }，y = 7

// 无限惰性序列
function* fib() { let [a, b] = [0, 1]; while (true) { yield a; [a, b] = [b, a + b]; } }
fib().take(5).toArray(); // [0, 1, 1, 2, 3]（Iterator Helpers，ES2025）
```

**面试答题要点**

1. Symbol 唯一、可做不冲突的属性键，内置 Symbol 用于定制语言行为。
2. 可迭代协议 = `[Symbol.iterator]` 返回带 `next()` 的迭代器；for...of / 展开 / 解构都基于它。
3. Generator 可暂停/恢复，`next(v)` 实现双向通信，是 async/await 的基础。
4. 普通对象默认不可迭代，Map/Set/Array/String/arguments/NodeList 可迭代。

**易错点 / 追问**

- `for...in` 遍历可枚举的字符串键（含原型链上的），`for...of` 遍历可迭代对象的值。
- `break` 退出 for...of 会调用迭代器的 `return()`，可用于清理资源。

---

### 3.3.3 Proxy / Reflect ★★★

**是什么 / 原理**

- **Proxy**：为目标对象创建代理，拦截 13 种基本操作（`get`、`set`、`has`、`deleteProperty`、`ownKeys`、`apply`、`construct`、`defineProperty`、`getPrototypeOf` 等）。
- **Reflect**：与 Proxy trap 一一对应的静态方法，提供操作的**默认行为**。在 trap 中用 `Reflect.get(target, key, receiver)` 可以正确传递 `receiver`，保证 getter 中的 `this` 指向代理对象（继承场景下尤其重要）；`Reflect.set` 返回布尔值而非抛错。
- **Vue3 用 Proxy 替代 `Object.defineProperty`** 的原因：

| | Object.defineProperty（Vue2） | Proxy（Vue3） |
|---|---|---|
| 新增/删除属性 | 检测不到，需 `$set/$delete` | 可拦截（`set`/`deleteProperty`） |
| 数组下标、length | 检测不到，需重写 7 个数组方法 | 原生支持 |
| 初始化 | 递归遍历所有属性，开销大 | 惰性：访问到嵌套对象时才代理 |
| Map/Set | 不支持 | 支持（拦截方法调用） |
| 兼容性 | IE9+ | 不支持 IE，无法 polyfill |

**代码示例**

```js
// 1. 校验 + 默认值 + 负索引数组
const user = new Proxy({}, {
  set(target, key, value, receiver) {
    if (key === 'age' && !Number.isInteger(value)) throw new TypeError('age must be integer');
    return Reflect.set(target, key, value, receiver);
  },
  get: (target, key, receiver) => (key in target ? Reflect.get(target, key, receiver) : 'N/A'),
});

const arr = new Proxy([1, 2, 3], {
  get: (t, k, r) => Reflect.get(t, typeof k === 'string' && k < 0 ? t.length + Number(k) : k, r),
});
arr[-1]; // 3

// 2. receiver 的作用
const parent = { _n: 'parent', get name() { return this._n; } };
const proxy = new Proxy(parent, {
  get: (t, k, receiver) => Reflect.get(t, k, receiver), // 若写成 t[k]，getter 的 this 永远是 parent
});
const child = Object.create(proxy, { _n: { value: 'child' } });
child.name; // 'child'
```

简易响应式完整实现见 [3.4 模式类](#345-模式类)。

**面试答题要点**

1. Proxy 拦截对象的基本操作，Reflect 提供对应默认行为，两者配合使用。
2. Reflect 的 receiver 参数保证 getter/setter 中 this 正确。
3. Vue3 换 Proxy：能拦截新增/删除属性和数组索引、惰性代理性能更好、支持 Map/Set；代价是不支持 IE。
4. 响应式核心：get 时 track 收集依赖，set 时 trigger 触发副作用。

**易错点 / 追问**

- Proxy 是**浅**代理，深层响应需在 get 中递归包装（Vue3 是惰性递归）。
- `proxy !== target`，对原对象的修改不会被拦截；Map/Set 内部槽（internal slot）问题需要在 get 中把方法 bind 到原对象。
- 追问「Vue3 ref 为什么需要 .value」：Proxy 只能代理对象，原始值需要包一层对象。

---

### 3.3.4 模块化：ESM vs CommonJS ★★★

**是什么 / 原理**

| 维度 | CommonJS | ESM |
|---|---|---|
| 语法 | `require` / `module.exports` | `import` / `export` |
| 加载时机 | **运行时**动态加载，可写在条件语句中 | **编译时**静态分析（`import()` 动态导入除外） |
| 导出值 | **值的拷贝**（导出对象的浅拷贝；原始值导出后不再变化） | **值的引用**（live binding，导出模块修改，导入方能看到；导入方只读） |
| 加载方式 | 同步（适合服务端本地文件） | 异步（浏览器网络加载），三阶段：构建 → 实例化 → 求值 |
| this | `module.exports` | `undefined` |
| Tree Shaking | 难（动态） | 支持（静态结构） |
| 顶层 await | 不支持 | 支持 |
| 循环依赖 | 返回**未执行完的部分导出**（可能拿到不完整对象） | 绑定已建立但可能处于 TDZ，访问未初始化的 `let/const` 会报错；函数声明已提升可用 |

**代码示例**

```js
// ---- CommonJS：值拷贝 ----
// counter.cjs
let count = 0;
module.exports = { count, inc: () => count++ };
// main.cjs
const c = require('./counter.cjs');
c.inc();
console.log(c.count); // 0 —— 导出时拷贝的是当时的值

// ---- ESM：live binding ----
// counter.mjs
export let count = 0;
export const inc = () => count++;
// main.mjs
import { count, inc } from './counter.mjs';
inc();
console.log(count); // 1
// count = 2;       // TypeError：导入绑定是只读的

// ---- CommonJS 循环依赖 ----
// a.js
exports.done = false;
const b = require('./b');   // 进入 b，此时 a 只执行到这里
console.log('in a, b.done =', b.done); // true
exports.done = true;
// b.js
const a = require('./a');   // 拿到 a 的"未完成"导出 { done: false }，不会死循环
console.log('in b, a.done =', a.done); // false
exports.done = true;
```

**互操作（2026 现状）**：Node 22.12+ / 20.19+ 默认支持 `require(esm)`（被 require 的 ESM 不能含顶层 await）；ESM 中 `import cjs from './x.cjs'` 拿到 `module.exports`。打包工具（Vite/Rollup/webpack）统一以 ESM 为标准。

**面试答题要点**

1. CJS 运行时同步加载，ESM 编译时静态分析、异步加载。
2. CJS 导出值的拷贝，ESM 导出活的只读引用。
3. ESM 静态结构使 Tree Shaking 成为可能，也支持顶层 await。
4. 循环依赖：CJS 返回已执行部分的导出；ESM 因绑定提前建立，函数声明可用，但 let/const 可能在 TDZ 报错。
5. 浏览器原生 `<script type="module">`，默认 defer、严格模式、跨域需 CORS。

**易错点 / 追问**

- CJS「值拷贝」是指 `module.exports` 对象属性被赋值的那一刻的值；如果导出的是对象，修改对象内部属性双方都能看到（浅拷贝语义）。
- `import()` 返回 Promise，可用于代码分割/懒加载，CJS 和 ESM 中都可用。
- 追问「为什么 ESM 能 Tree Shaking 而 CJS 不行」：import/export 只能出现在顶层、标识符是静态字符串，构建时即可确定依赖图；CJS 的 require 可以是动态表达式。

---

### 3.3.5 新 API（ES2022–ES2025）★★

**是什么 / 原理**：近几年的高频「新特性」题，重点是**不可变数组方法**（React 状态更新友好）和集合/迭代器能力。

| API | 版本 | 作用 | 说明 |
|---|---|---|---|
| `arr.at(i)` | ES2022 | 支持负索引取值 | `arr.at(-1)` 取最后一个，字符串也有 |
| `Object.hasOwn(o, k)` | ES2022 | 替代 `hasOwnProperty.call` | 对 `Object.create(null)` 也安全 |
| `findLast / findLastIndex` | ES2023 | 从后往前查找 | |
| `toSorted / toReversed / toSpliced / with` | ES2023 | **返回新数组**的不可变版本 | 原数组不变；`with(i, v)` 替换某项 |
| `Object.groupBy / Map.groupBy` | ES2024 | 分组 | 返回原型为 null 的对象 / Map |
| `Promise.withResolvers()` | ES2024 | 返回 `{promise, resolve, reject}` | 替代「把 resolve 存到外部变量」写法 |
| `Set` 集合运算 | ES2025 | `union / intersection / difference / symmetricDifference / isSubsetOf / isSupersetOf / isDisjointFrom` | |
| Iterator Helpers | ES2025 | 迭代器上的 `map/filter/take/drop/flatMap/reduce/toArray/some/every/find`，`Iterator.from` | **惰性**求值，适合大/无限序列 |
| `Promise.try` | ES2025 | 统一同步异常与异步异常 | |

**代码示例**

```js
const arr = [3, 1, 2];
arr.toSorted();          // [1, 2, 3]，arr 仍为 [3, 1, 2]
arr.with(0, 9);          // [9, 1, 2]
arr.at(-1);              // 2
[1, 2, 3, 4].findLast((x) => x % 2); // 3

Object.groupBy([1, 2, 3, 4], (x) => (x % 2 ? 'odd' : 'even'));
// { odd: [1, 3], even: [2, 4] }

const { promise, resolve, reject } = Promise.withResolvers();
setTimeout(() => resolve('done'), 100);

new Set([1, 2, 3]).intersection(new Set([2, 3, 4])); // Set {2, 3}
new Set([1, 2]).union(new Set([2, 3]));              // Set {1, 2, 3}

// Iterator Helpers：不会生成中间数组
[1, 2, 3, 4].values().filter((x) => x % 2).map((x) => x * 10).toArray(); // [10, 30]
```

**面试答题要点**

1. 不可变数组方法（toSorted/with 等）不修改原数组，适合 React/Redux 状态更新，替代 `[...arr].sort()`。
2. `Object.groupBy` 返回无原型对象；`Promise.withResolvers` 简化外部控制 Promise。
3. Set 运算和 Iterator Helpers 是 ES2025 标准，现代浏览器和 Node 22+ 均已支持。
4. Iterator Helpers 是惰性的，与数组方法的「立即生成新数组」不同。

**易错点 / 追问**

- `sort()` 默认按**字符串**排序：`[10, 9, 1].sort()` → `[1, 10, 9]`，数字排序要传比较函数。
- 新 API 在老环境需 core-js polyfill；Proxy、私有字段等语法特性无法完全 polyfill。

---

## 3.4 手写题清单 ★★★

> 写法约定：每题给出「思路 → 代码 → 边界情况 / 追问」。标注 ✅ 的代码已在 Node 24 下用断言测试通过。
> 手写题评分点通常是：**能跑 > 边界处理 > 代码整洁 > 能讲清思路**。先说思路再动手，写完主动说出边界。

### 3.4.1 函数类

#### call / apply / bind ★★★ ✅

**思路**：利用隐式绑定——把函数临时挂到 ctx 上，以 `ctx.fn()` 形式调用；用 Symbol 作键避免覆盖已有属性。bind 返回新函数，需处理「被 new 调用」的情况。

```js
Function.prototype.myCall = function (ctx, ...args) {
  if (typeof this !== 'function') throw new TypeError('not a function');
  // null/undefined → 全局对象（非严格模式语义）；原始值 → 装箱，否则无法挂属性
  ctx = ctx == null ? globalThis : Object(ctx);
  const key = Symbol('fn');          // 唯一键，不会覆盖 ctx 已有属性
  ctx[key] = this;                   // this 就是被调用的函数
  try {
    return ctx[key](...args);        // 隐式绑定：this 指向 ctx
  } finally {
    delete ctx[key];                 // 无论是否抛错都清理
  }
};

Function.prototype.myApply = function (ctx, args = []) {
  return this.myCall(ctx, ...(args ?? [])); // 第二个参数是数组（或类数组）
};

Function.prototype.myBind = function (ctx, ...preset) {
  const fn = this;
  function bound(...args) {
    // 被 new 调用时忽略绑定的 ctx，以 fn 为构造函数创建实例（new 优先级高于 bind）
    return new.target
      ? new fn(...preset, ...args)
      : fn.apply(ctx, [...preset, ...args]); // 支持分两次传参（偏函数）
  }
  // 维护原型链，使 new bound() instanceof fn 成立；箭头函数没有 prototype
  if (fn.prototype) bound.prototype = Object.create(fn.prototype);
  return bound;
};
```

**边界情况 / 追问**：ctx 为 null/undefined/原始值；函数抛错时也要删除临时属性；bind 后 new 调用；bind 的预置参数与调用参数合并；多次 bind 只有第一次生效。原生 bound 函数还有 `name = 'bound fn'`、`length` 变化，面试可口头提及。

#### new ★★★ ✅

**思路**：① 以构造函数的 prototype 为原型创建对象；② 以该对象为 this 执行构造函数；③ 构造函数返回对象/函数则用它，否则返回新对象。

```js
function myNew(Ctor, ...args) {
  if (typeof Ctor !== 'function') throw new TypeError('Ctor must be a function');
  const obj = Object.create(Ctor.prototype);   // 1. 链接原型
  const ret = Ctor.apply(obj, args);           // 2. 绑定 this 执行
  // 3. 显式返回引用类型时以返回值为准；返回原始值则忽略
  return ret !== null && (typeof ret === 'object' || typeof ret === 'function') ? ret : obj;
}
```

**边界情况 / 追问**：返回 `null` 视为原始值（仍返回 obj）；箭头函数、class 不能用此方式（箭头函数无 prototype 且不可 new；class 必须用 new 调用）。

#### instanceof ★★ ✅

```js
function myInstanceof(left, Right) {
  if (typeof Right !== 'function') throw new TypeError('Right-hand side is not callable');
  // 原始值直接 false
  if (left === null || (typeof left !== 'object' && typeof left !== 'function')) return false;
  let proto = Object.getPrototypeOf(left);
  while (proto !== null) {                     // 沿原型链向上，直到 null
    if (proto === Right.prototype) return true;
    proto = Object.getPrototypeOf(proto);
  }
  return false;
}
```

**边界情况 / 追问**：原始值返回 false；`Object.create(null)` 原型链为空；原生 instanceof 会先检查 `Right[Symbol.hasInstance]`。

#### 柯里化 ★★ ✅

```js
/**
 * 柯里化：参数凑够 arity 个时执行，否则返回继续收集参数的函数
 * @param {Function} fn 原函数
 * @param {number} arity 需要的参数个数，默认 fn.length（有默认值/剩余参数时 length 不准，需手动传）
 */
function curry(fn, arity = fn.length) {
  return function curried(...args) {
    if (args.length >= arity) return fn.apply(this, args);
    // 每次返回新函数并拼接参数，不修改闭包里的 args，保证中间函数可复用
    return (...rest) => curried.apply(this, [...args, ...rest]);
  };
}

const add3 = curry((a, b, c) => a + b + c);
add3(1)(2)(3); add3(1, 2)(3); add3(1)(2, 3); // 都是 6
```

**边界情况 / 追问**：`fn.length` 不统计默认参数和剩余参数；中间函数复用（`const a1 = add3(1)` 多次调用互不影响）。追问「实现 `add(1)(2)(3)` 无限累加」：返回的函数重写 `valueOf/toString`，或约定空调用 `add(1)(2)()` 时求值。

#### compose / pipe ★★ ✅

```js
// compose 从右往左执行（数学函数复合 f(g(x))），redux 中间件、koa 洋葱模型的基础
const compose = (...fns) => (x) => fns.reduceRight((acc, f) => f(acc), x);
// pipe 从左往右，可读性更好
const pipe = (...fns) => (x) => fns.reduce((acc, f) => f(acc), x);

compose((x) => x + 1, (x) => x * 2)(3); // 7：先 *2 再 +1
pipe((x) => x + 1, (x) => x * 2)(3);    // 8
```

**边界情况 / 追问**：空数组时返回恒等函数（reduce 初始值保证）；第一个执行的函数允许多参数可写成 `(...args) => rest.reduce(..., first(...args))`。追问「异步 compose」：`fns.reduce((p, f) => p.then(f), Promise.resolve(x))`。

---

### 3.4.2 控制类

#### 防抖 debounce ★★★ ✅

**思路**：每次触发都清除上一个定时器，停止触发 wait 毫秒后才执行。适用：搜索框联想、窗口 resize 结束后计算、表单校验。

```js
/**
 * 防抖
 * @param {Function} fn 目标函数
 * @param {number} wait 等待毫秒数
 * @param {{leading?: boolean}} options leading=true 时首次立即执行，之后冷却期内的调用忽略
 * @returns {Function & {cancel: Function}} 防抖后的函数，带 cancel 方法
 */
function debounce(fn, wait, { leading = false } = {}) {
  let timer = null;
  function debounced(...args) {
    const callNow = leading && !timer;  // 立即执行模式：没有定时器说明处于冷却期外
    clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;                      // 冷却结束
      if (!leading) fn.apply(this, args); // 尾部执行，用最后一次的 this 和参数
    }, wait);
    if (callNow) return fn.apply(this, args);
  }
  debounced.cancel = () => { clearTimeout(timer); timer = null; };
  return debounced;
}
```

**边界情况 / 追问**：保留 `this` 和参数（必须用普通函数 + apply，不能用箭头函数包装器丢 this）；leading 模式；cancel；组件卸载时需 cancel 防止内存泄漏/对已卸载组件 setState。React 中要用 `useMemo/useRef` 保持同一个防抖实例，否则每次渲染都是新函数。lodash 版本还有 `maxWait`（防抖 + 节流的结合）。

#### 节流 throttle ★★★ ✅

**思路**：固定频率执行，wait 内最多执行一次。适用：scroll、mousemove、拖拽。时间戳版首次立即执行但丢最后一次；定时器版有尾调用但首次延迟；下面是**两者结合**：首次立即执行，并保证最后一次也会执行。

```js
function throttle(fn, wait) {
  let last = 0, timer = null;
  return function (...args) {
    const now = Date.now();
    const remaining = wait - (now - last);  // 距离下次可执行还剩多久
    if (remaining <= 0) {
      // 已过冷却期：立即执行，并清掉可能残留的尾调用定时器
      clearTimeout(timer);
      timer = null;
      last = now;
      fn.apply(this, args);
    } else if (!timer) {
      // 冷却期内：安排一次尾调用，保证最后一次触发不丢失
      timer = setTimeout(() => {
        last = Date.now();
        timer = null;
        fn.apply(this, args);
      }, remaining);
    }
  };
}
```

**边界情况 / 追问**：尾调用使用的是**安排定时器时**的参数（lodash 用最新参数，可把 args 存到外部变量后定时器内读取）；系统时间被修改会影响 Date.now，可用 `performance.now()`。追问「防抖与节流区别」：防抖关注**停止后**执行一次，节流关注**过程中**按频率执行。动画类节流用 `requestAnimationFrame` 更合适。

#### 并发控制（限制同时 N 个请求）★★★ ✅

**思路**：先启动 limit 个「工人」，每完成一个就从队列取下一个，结果按原始索引存放。

```js
/**
 * 限制并发执行异步任务
 * @param {Array<() => Promise<any>>} tasks 任务工厂数组（必须是函数，传 Promise 本身就已经开始执行了）
 * @param {number} limit 最大并发数
 * @returns {Promise<any[]>} 按输入顺序排列的结果；任一失败则整体 reject（同 Promise.all 语义）
 */
function promisePool(tasks, limit) {
  return new Promise((resolve, reject) => {
    const results = new Array(tasks.length);
    let next = 0, finished = 0;            // next：下一个待启动的索引；finished：已完成数
    if (tasks.length === 0) return resolve(results);

    const runOne = () => {
      if (next >= tasks.length) return;     // 没有待启动任务了
      const i = next++;                     // 先占位索引，保证结果顺序
      Promise.resolve()
        .then(() => tasks[i]())             // 包一层，任务同步抛错也能被 reject 捕获
        .then((v) => {
          results[i] = v;
          if (++finished === tasks.length) resolve(results);
          else runOne();                    // 完成一个，补位一个
        }, reject);
    };
    for (let k = 0; k < Math.min(limit, tasks.length); k++) runOne();
  });
}
```

**边界情况 / 追问**：空数组；limit 大于任务数；任务同步抛错；结果顺序与完成顺序无关。追问「失败不中断，收集全部结果」：把 reject 改为记录 `{status:'rejected'}` 后继续 runOne。追问「动态添加任务的调度器（Scheduler.add）」：维护队列 + running 计数，add 返回 Promise，见下方变体。

```js
// 变体：经典 Scheduler 题——add 返回 Promise，最多同时运行 limit 个
class Scheduler {
  constructor(limit) { this.limit = limit; this.running = 0; this.queue = []; }
  add(task) {
    return new Promise((resolve, reject) => {
      this.queue.push({ task, resolve, reject });
      this.#run();
    });
  }
  #run() {
    while (this.running < this.limit && this.queue.length) {
      const { task, resolve, reject } = this.queue.shift();
      this.running++;
      Promise.resolve().then(task).then(resolve, reject).finally(() => { this.running--; this.#run(); });
    }
  }
}
```

#### 带重试的请求 ★★ ✅

```js
/**
 * 失败自动重试，支持指数退避
 * @param {(attempt: number) => Promise<any>} fn 请求函数，参数为当前第几次尝试（从 0 开始）
 * @param {{retries?: number, delay?: number, factor?: number}} options
 *   retries 最大重试次数（总尝试次数 = retries + 1）；delay 首次重试间隔 ms；factor 退避倍数
 */
async function retry(fn, { retries = 3, delay = 0, factor = 2 } = {}) {
  let lastErr;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await fn(attempt);          // 注意必须 return await，否则 catch 捕获不到
    } catch (e) {
      lastErr = e;
      if (attempt === retries) break;    // 最后一次失败不再等待
      await sleep(delay * factor ** attempt); // 指数退避：delay, 2*delay, 4*delay...
    }
  }
  throw lastErr;                         // 抛出最后一次的错误
}
```

**边界情况 / 追问**：区分可重试错误（网络错误、5xx、429）与不可重试错误（4xx 参数错误）——可加 `shouldRetry(err)` 参数；退避加随机抖动（jitter）避免惊群；配合超时（`AbortSignal.timeout(ms)`）；非幂等请求（POST 下单）谨慎重试。

---

### 3.4.3 Promise 类

#### 手写 Promise（Promises/A+）★★★ ✅（已通过官方 promises-aplus-tests 872 条用例）

**思路**：
1. 状态机：`state` + `value` + 回调队列，状态只能从 pending 改变一次；
2. `then` 返回新 Promise；回调用 `queueMicrotask` 异步执行；非函数参数做值穿透；
3. 核心是 **Promise 解决过程 `resolvePromise`**（A+ 规范 2.3）：处理返回值是自身（循环）、thenable（取一次 then、只调用一次）、普通值三种情况。

```js
const PENDING = 'pending', FULFILLED = 'fulfilled', REJECTED = 'rejected';

/**
 * Promise 解决过程（A+ 2.3）：用 x 决定 promise 的最终状态
 * @param promise 当前要被解决的 promise（用于循环引用检测）
 * @param x       回调返回值或 resolve 传入的值
 * @param fulfill 直接以某个值完成 promise
 * @param reject  以某个原因拒绝 promise
 */
function resolvePromise(promise, x, fulfill, reject) {
  // 2.3.1 返回自身会永远等待自己，直接 TypeError
  if (x === promise) return reject(new TypeError('Chaining cycle detected for promise'));
  if (x !== null && (typeof x === 'object' || typeof x === 'function')) {
    let called = false;                 // 2.3.3.3.3 resolve/reject 只能调用一次（防不规范的 thenable）
    let then;
    try {
      then = x.then;                    // 2.3.3.1 只读取一次 then（getter 可能有副作用或抛错）
    } catch (e) {
      return reject(e);
    }
    if (typeof then === 'function') {
      try {
        then.call(
          x,
          // thenable 完成时，值可能仍是 thenable，递归解决
          (y) => { if (called) return; called = true; resolvePromise(promise, y, fulfill, reject); },
          (r) => { if (called) return; called = true; reject(r); },
        );
      } catch (e) {
        if (!called) { called = true; reject(e); } // then 抛错，但已调用过 resolve/reject 则忽略
      }
      return;
    }
  }
  fulfill(x);                           // 普通值（含没有 then 方法的对象）
}

class MyPromise {
  constructor(executor) {
    this.state = PENDING;
    this.value = undefined;             // 成功值或失败原因
    this.callbacks = [];                // pending 期间注册的 then 回调
    let done = false;                   // resolve/reject 只生效一次（包括"锁定"跟随某个 thenable 之后）

    // 真正改变状态的唯一入口
    const settle = (state, value) => {
      if (this.state !== PENDING) return;
      this.state = state;
      this.value = value;
      this.callbacks.forEach((fn) => fn());
      this.callbacks = [];
    };
    const reject = (r) => { if (done) return; done = true; settle(REJECTED, r); };
    // resolve 传入 Promise/thenable 时要跟随其状态，而不是直接 fulfilled
    const resolve = (x) => {
      if (done) return;
      done = true;
      resolvePromise(this, x, (v) => settle(FULFILLED, v), (r) => settle(REJECTED, r));
    };
    try {
      executor(resolve, reject);
    } catch (e) {
      reject(e);                        // 执行器同步抛错 → rejected
    }
  }

  then(onFulfilled, onRejected) {
    // 值穿透：非函数时透传值 / 继续抛出原因
    onFulfilled = typeof onFulfilled === 'function' ? onFulfilled : (v) => v;
    onRejected = typeof onRejected === 'function' ? onRejected : (r) => { throw r; };
    return new MyPromise((resolve, reject) => {
      // 回调总在微任务中执行（A+ 2.2.4）
      const run = () => queueMicrotask(() => {
        try {
          const cb = this.state === FULFILLED ? onFulfilled : onRejected;
          resolve(cb(this.value));      // 回调返回值交给新 Promise 的 resolve（内部走 resolvePromise）
        } catch (e) {
          reject(e);                    // 回调抛错 → 新 Promise rejected
        }
      });
      this.state === PENDING ? this.callbacks.push(run) : run();
    });
  }

  catch(onRejected) { return this.then(undefined, onRejected); }

  // finally：回调不接收参数，不改变原结果；回调返回的 Promise 会被等待；回调抛错则以新错误拒绝
  finally(onFinally) {
    return this.then(
      (v) => MyPromise.resolve(onFinally()).then(() => v),
      (r) => MyPromise.resolve(onFinally()).then(() => { throw r; }),
    );
  }

  static resolve(v) { return v instanceof MyPromise ? v : new MyPromise((res) => res(v)); }
  static reject(r) { return new MyPromise((_, rej) => rej(r)); }
}
```

**如何验证**：安装 `promises-aplus-tests`，导出适配器后运行 `npx promises-aplus-tests adapter.js`：

```js
module.exports = {
  resolved: MyPromise.resolve,
  rejected: MyPromise.reject,
  deferred() {
    let resolve, reject;
    const promise = new MyPromise((a, b) => { resolve = a; reject = b; });
    return { promise, resolve, reject };
  },
};
```

**边界情况 / 追问**：
- 执行器同步抛错、多次调用 resolve/reject、resolve 一个 Promise（跟随状态）、then 返回自身（循环 TypeError）、thenable 的 then 是 getter 或抛错、thenable 同时调用两个回调。
- A+ 只规范 `then`；`catch/finally/静态方法` 是 ES 规范扩展。
- 原生 Promise 未处理的 rejection 会报 `unhandledrejection`，手写版一般不实现。
- 追问「为什么用 queueMicrotask 而不是 setTimeout」：规范要求异步即可，用 setTimeout 也能过 A+ 测试，但与原生执行顺序不一致（原生是微任务）。

#### Promise.all / race / allSettled / any ★★★ ✅

```js
// 作为 MyPromise 的静态方法（同样适用于替换成原生 Promise）
MyPromise.all = function (iterable) {
  return new MyPromise((resolve, reject) => {
    const items = Array.from(iterable);       // 支持任意可迭代对象
    const results = new Array(items.length);
    let count = 0;
    if (items.length === 0) return resolve(results); // 空数组立即成功
    items.forEach((item, i) => {
      // 用 resolve 包装：数组中可以是普通值
      MyPromise.resolve(item).then((v) => {
        results[i] = v;                       // 按索引存，保证顺序
        if (++count === items.length) resolve(results); // 不能用 results.length 判断（稀疏数组）
      }, reject);                             // 任一失败立即 reject（后续再 reject 无效）
    });
  });
};

MyPromise.race = function (iterable) {
  return new MyPromise((resolve, reject) => {
    // 谁先 settle 谁决定结果；空数组永远 pending
    for (const item of iterable) MyPromise.resolve(item).then(resolve, reject);
  });
};

MyPromise.allSettled = function (iterable) {
  // 把每一项都映射成"必定成功"的 Promise，再复用 all
  return MyPromise.all(Array.from(iterable, (item) =>
    MyPromise.resolve(item).then(
      (value) => ({ status: 'fulfilled', value }),
      (reason) => ({ status: 'rejected', reason }),
    )));
};

MyPromise.any = function (iterable) {
  return new MyPromise((resolve, reject) => {
    const items = Array.from(iterable);
    const errors = new Array(items.length);
    let count = 0;
    if (items.length === 0) return reject(new AggregateError([], 'All promises were rejected'));
    items.forEach((item, i) => {
      MyPromise.resolve(item).then(resolve, (e) => {
        errors[i] = e;
        if (++count === items.length) reject(new AggregateError(errors, 'All promises were rejected'));
      });
    });
  });
};
```

**边界情况 / 追问**：空数组（all → `[]`、race → 永远 pending、any → AggregateError）；非 Promise 值；结果顺序；用计数器而非 `results.length` 判断完成。

#### sleep ★ ✅

```js
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// 用法：await sleep(1000);
// 可取消版本：支持 AbortSignal
const sleepAbortable = (ms, signal) => new Promise((resolve, reject) => {
  if (signal?.aborted) return reject(signal.reason);
  const t = setTimeout(resolve, ms);
  signal?.addEventListener('abort', () => { clearTimeout(t); reject(signal.reason); }, { once: true });
});
```

**边界情况**：定时器精度不保证（最小延迟、后台节流）；Node 中可直接用 `import { setTimeout as sleep } from 'node:timers/promises'`。

#### 异步串行 ★★ ✅

```js
// 方式一：for...of + await（最直观）
async function serial(tasks) {
  const results = [];
  for (const task of tasks) results.push(await task()); // 上一个完成才开始下一个
  return results;
}

// 方式二：reduce 链式拼接 Promise（不使用 async 时的经典写法）
const serialReduce = (tasks) =>
  tasks.reduce((p, task) => p.then((acc) => task().then((v) => [...acc, v])), Promise.resolve([]));
```

**边界情况 / 追问**：tasks 必须是**返回 Promise 的函数**而不是 Promise（Promise 创建即开始执行，无法串行）；某一项失败则中断。追问「红绿灯循环（红 3s、绿 1s、黄 2s）」：`while (true) { await light('red', 3000); ... }`。

---

### 3.4.4 数据类

#### 深拷贝（含循环引用）★★★ ✅

```js
/**
 * 深拷贝
 * @param {any} value 要拷贝的值
 * @param {WeakMap<object, object>} seen key：源对象，value：已创建的拷贝；用于处理循环引用和重复引用
 * @returns {any} 拷贝结果
 */
function deepClone(value, seen = new WeakMap()) {
  if (value === null || typeof value !== 'object') return value; // 原始值、函数直接返回（函数通常共享）
  if (seen.has(value)) return seen.get(value);                   // 循环引用：返回已创建的拷贝
  if (value instanceof Date) return new Date(value);
  if (value instanceof RegExp) return new RegExp(value.source, value.flags);
  if (value instanceof Map) {
    const m = new Map();
    seen.set(value, m);                    // 先登记再递归，否则自引用会无限递归
    value.forEach((v, k) => m.set(deepClone(k, seen), deepClone(v, seen)));
    return m;
  }
  if (value instanceof Set) {
    const s = new Set();
    seen.set(value, s);
    value.forEach((v) => s.add(deepClone(v, seen)));
    return s;
  }
  // 数组 / 普通对象 / class 实例：保留原型
  const result = Array.isArray(value) ? [] : Object.create(Object.getPrototypeOf(value));
  seen.set(value, result);
  for (const key of Reflect.ownKeys(value)) { // 包含 Symbol 键和不可枚举键
    result[key] = deepClone(value[key], seen);
  }
  return result;
}
```

**边界情况 / 追问**：
- 循环引用（`obj.self = obj`）和重复引用（两个属性指向同一对象，拷贝后也应指向同一拷贝）——都靠 seen 表解决；
- Symbol 键、Date、RegExp、Map/Set、保留原型；
- 未处理：属性描述符（getter/setter 会被求值，可改用 `Object.getOwnPropertyDescriptors`）、ArrayBuffer/TypedArray、Error、DOM 节点；
- 递归层级过深会栈溢出，可改用显式栈迭代；
- 生产环境优先 `structuredClone` 或 lodash `cloneDeep`。

#### 数组扁平化 ★★ ✅

```js
// 递归 + 深度参数（对标 Array.prototype.flat(depth)）
function flatten(arr, depth = Infinity) {
  return depth > 0
    ? arr.reduce((acc, item) => acc.concat(Array.isArray(item) ? flatten(item, depth - 1) : [item]), [])
    : arr.slice();
}

// 迭代版：用栈避免递归栈溢出
function flattenIter(arr) {
  const stack = [...arr], res = [];
  while (stack.length) {
    const item = stack.pop();                 // 从尾部取
    Array.isArray(item) ? stack.push(...item) : res.push(item);
  }
  return res.reverse();                        // 因从尾部处理，最后反转恢复顺序
}

[1, [2, [3, [4]]]].flat(Infinity); // 原生 API
```

**边界情况**：`depth` 控制；空位（原生 flat 会跳过空位，reduce 也会跳过）；`toString().split(',')` 的取巧写法会把数字变成字符串，不推荐。

#### 数组去重 ★★ ✅

```js
const unique = (arr) => [...new Set(arr)];   // SameValueZero：NaN 能去重，+0/-0 视为相同

// 对象数组按 key 去重
function uniqueBy(arr, keyFn) {
  const seen = new Set();
  return arr.filter((item) => {
    const k = keyFn(item);
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}
uniqueBy([{ id: 1 }, { id: 2 }, { id: 1 }], (x) => x.id); // [{id:1},{id:2}]
```

**边界情况**：`indexOf` 去重无法处理 NaN（`[NaN].indexOf(NaN) === -1`），`includes` 可以；`1` 与 `'1'` 不同；对象按引用比较，按内容去重需指定 key 或序列化（`JSON.stringify` 受键顺序影响）。复杂度：Set O(n)，`filter + indexOf` O(n²)。

#### LRU 缓存 ★★★ ✅

**思路**：利用 **Map 按插入顺序迭代**的特性——访问时删除再插入，移到「最新」；超出容量时删除 `keys().next()`（最旧）。get/put 均 O(1)。

```js
class LRUCache {
  /** @param {number} capacity 最大容量 */
  constructor(capacity) {
    this.capacity = capacity;
    this.map = new Map();               // key：缓存键，value：缓存值；迭代顺序即使用顺序（旧 → 新）
  }
  /** 读取并刷新为最近使用，不存在返回 -1 */
  get(key) {
    if (!this.map.has(key)) return -1;
    const v = this.map.get(key);
    this.map.delete(key);               // 删除再插入 = 移到末尾（最新）
    this.map.set(key, v);
    return v;
  }
  /** 写入；已存在则更新并刷新；超出容量淘汰最久未使用的 */
  put(key, value) {
    if (this.map.has(key)) this.map.delete(key);
    this.map.set(key, value);
    if (this.map.size > this.capacity) {
      this.map.delete(this.map.keys().next().value); // 第一个键是最旧的
    }
  }
}
```

**边界情况 / 追问**：更新已存在的键也要刷新顺序；capacity 为 0。追问「不用 Map 怎么实现」：**哈希表 + 双向链表**——哈希表 O(1) 定位节点，双向链表 O(1) 移动/删除节点，头尾用哨兵节点简化边界。追问「带过期时间的 LRU」：value 存 `{ value, expireAt }`，get 时检查过期。

---

### 3.4.5 模式类

#### EventEmitter（发布订阅）★★★ ✅

```js
class EventEmitter {
  #events = new Map();                  // key：事件名，value：监听函数数组

  /** 订阅，返回取消订阅函数 */
  on(name, fn) {
    if (!this.#events.has(name)) this.#events.set(name, []);
    this.#events.get(name).push(fn);
    return () => this.off(name, fn);
  }
  /** 只触发一次：包装函数执行后自动移除；记录 origin 以便 off(原函数) 能移除 */
  once(name, fn) {
    const wrapper = (...args) => { this.off(name, wrapper); fn.apply(this, args); };
    wrapper.origin = fn;
    return this.on(name, wrapper);
  }
  /** 取消订阅；不传 fn 则移除该事件全部监听 */
  off(name, fn) {
    const list = this.#events.get(name);
    if (!list) return;
    if (!fn) return void this.#events.delete(name);
    this.#events.set(name, list.filter((f) => f !== fn && f.origin !== fn));
  }
  /** 触发事件，返回是否有监听者 */
  emit(name, ...args) {
    const list = this.#events.get(name);
    if (!list) return false;
    [...list].forEach((fn) => fn.apply(this, args)); // 复制一份：执行中 once 移除自身不影响本轮遍历
    return true;
  }
}
```

**边界情况 / 追问**：emit 过程中增删监听（遍历副本）；once 的监听用原函数 off；同一函数重复订阅。追问「发布订阅 vs 观察者模式」：观察者模式中目标直接持有并通知观察者（Vue 的 Dep/Watcher）；发布订阅有中间的事件中心，发布者和订阅者完全解耦。

#### 简易响应式（Vue3 reactive + effect）★★ ✅

```js
// 依赖存储结构：targetMap(WeakMap) → depsMap(Map: key → dep) → dep(Set<effect>)
const targetMap = new WeakMap();        // key：原始对象，value：该对象的 depsMap
let activeEffect = null;                // 当前正在执行的副作用函数

/** 收集依赖：记录"activeEffect 依赖 target[key]" */
function track(target, key) {
  if (!activeEffect) return;            // 不在 effect 中读取，无需收集
  let depsMap = targetMap.get(target);
  if (!depsMap) targetMap.set(target, (depsMap = new Map()));
  let dep = depsMap.get(key);
  if (!dep) depsMap.set(key, (dep = new Set()));
  dep.add(activeEffect);
}

/** 触发更新：重新执行依赖 target[key] 的所有 effect */
function trigger(target, key) {
  const dep = targetMap.get(target)?.get(key);
  dep && [...dep].forEach((fn) => fn()); // 复制一份，避免执行中再次 add 导致无限循环
}

function reactive(obj) {
  return new Proxy(obj, {
    get(target, key, receiver) {
      track(target, key);
      const v = Reflect.get(target, key, receiver);
      return v !== null && typeof v === 'object' ? reactive(v) : v; // 惰性深层代理
    },
    set(target, key, value, receiver) {
      const old = target[key];
      const ok = Reflect.set(target, key, value, receiver);
      if (!Object.is(old, value)) trigger(target, key);              // 值未变化不触发
      return ok;
    },
  });
}

/** 注册副作用：立即执行一次以收集依赖 */
function effect(fn) {
  const run = () => {
    const prev = activeEffect;          // 支持嵌套 effect：执行完恢复外层
    activeEffect = run;
    try { fn(); } finally { activeEffect = prev; }
  };
  run();
  return run;
}

const state = reactive({ count: 0 });
effect(() => console.log('count =', state.count)); // count = 0
state.count++;                                     // count = 1
```

**边界情况 / 追问**：未实现——依赖清理（分支切换 `ok ? a : b` 时旧依赖残留，Vue 每次执行前 cleanup）、调度器（批量异步更新）、重复代理缓存（同一对象多次 reactive 应返回同一 Proxy，用 WeakMap 缓存）、数组 length / `has` / `ownKeys` 拦截。

#### 虚拟 DOM 渲染 ★★（renderToString 部分 ✅）

**思路**：VNode 是描述 DOM 的普通对象 `{ type, props, children }`；`render` 递归把 VNode 转成真实 DOM 并挂载。

```js
/** 创建 VNode：children 统一拍平为数组，字符串/数字作为文本节点 */
function h(type, props = {}, ...children) {
  return { type, props: props ?? {}, children: children.flat() };
}

/** 把 VNode 渲染为真实 DOM 并挂载到 container（浏览器环境） */
function render(vnode, container) {
  container.appendChild(createDom(vnode));
}

function createDom(vnode) {
  // 文本节点
  if (typeof vnode === 'string' || typeof vnode === 'number') {
    return document.createTextNode(String(vnode));
  }
  // 函数组件：执行得到子树后继续渲染
  if (typeof vnode.type === 'function') return createDom(vnode.type(vnode.props));

  const el = document.createElement(vnode.type);
  for (const [key, value] of Object.entries(vnode.props)) {
    if (key.startsWith('on') && typeof value === 'function') {
      el.addEventListener(key.slice(2).toLowerCase(), value); // onClick → click
    } else if (key === 'style' && typeof value === 'object') {
      Object.assign(el.style, value);
    } else if (key === 'className') {
      el.setAttribute('class', value);
    } else {
      el.setAttribute(key, value);
    }
  }
  vnode.children.forEach((child) => el.appendChild(createDom(child)));
  return el;
}

/** 服务端渲染版：VNode → HTML 字符串（同样递归，注意转义防 XSS） */
const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
function renderToString(vnode) {
  if (typeof vnode === 'string' || typeof vnode === 'number') return escapeHtml(vnode);
  if (typeof vnode.type === 'function') return renderToString(vnode.type(vnode.props));
  const attrs = Object.entries(vnode.props)
    .filter(([k, v]) => !k.startsWith('on') && typeof v !== 'object')
    .map(([k, v]) => ` ${k === 'className' ? 'class' : k}="${escapeHtml(v)}"`)
    .join('');
  return `<${vnode.type}${attrs}>${vnode.children.map(renderToString).join('')}</${vnode.type}>`;
}

const App = ({ name }) => h('div', { className: 'app' }, h('p', null, 'Hello ', name));
renderToString(h(App, { name: '<Tom>' }));
// '<div class="app"><p>Hello &lt;Tom&gt;</p></div>'
```

**边界情况 / 追问**：文本节点、函数组件、事件绑定、style 对象、属性转义（XSS）；自闭合标签（`img/input`）在 renderToString 中需特殊处理。追问「diff 算法」：同层比较、type 不同直接替换、key 复用节点；Vue3 双端 + 最长递增子序列，React 单向遍历 + lastIndex（详见框架章节）。

---

### 3.4.6 解析类

#### 模板字符串渲染 ★★ ✅

```js
/**
 * 渲染 {{ path }} 模板，支持嵌套路径 user.name
 * @param {string} tpl 模板字符串
 * @param {Record<string, any>} data key：模板变量名，value：变量值（可嵌套对象）
 */
function render(tpl, data) {
  return tpl.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_, path) => {
    const v = path.split('.').reduce((o, k) => o?.[k], data); // 可选链：中间为空不报错
    return v ?? '';                                            // 未定义渲染为空串，0/false 保留
  });
}
render('Hi {{ name }}, {{user.age}}', { name: 'Tom', user: { age: 18 } }); // 'Hi Tom, 18'
```

**边界情况**：空格容忍、嵌套路径、缺失变量、`0`/`false` 不能被当作空（用 `??` 而非 `||`）、输出到 HTML 时需转义。追问「支持表达式」：`new Function('data', 'with(data){ return ' + expr + '}')`，有安全风险，需沙箱。

#### URL 参数解析 ★★ ✅

```js
/**
 * 解析 query 为对象：重复 key 合并为数组；无值的 key 为 true；自动解码
 * @returns {Record<string, string | true | Array<string | true>>} key：参数名，value：参数值
 */
function parseQuery(url) {
  const query = url.includes('?') ? url.slice(url.indexOf('?') + 1).split('#')[0] : url; // 去掉 hash
  const res = {};
  for (const part of query.split('&')) {
    if (!part) continue;                                   // 跳过 'a=1&&b=2' 中的空段
    const [rawK, ...rest] = part.split('=');               // 值中可能含 '='，只按第一个分割
    const k = decodeURIComponent(rawK.replace(/\+/g, ' ')); // 表单编码中 + 表示空格
    const v = rest.length ? decodeURIComponent(rest.join('=').replace(/\+/g, ' ')) : true;
    if (k in res) res[k] = [].concat(res[k], v);           // 重复 key 转数组
    else res[k] = v;
  }
  return res;
}
parseQuery('https://a.com/p?a=1&b=2&a=3&c&d=%E4%B8%AD&e=x%3Dy#hash');
// { a: ['1', '3'], b: '2', c: true, d: '中', e: 'x=y' }

// 原生方案（生产推荐）
Object.fromEntries(new URL('https://a.com/?a=1&b=2').searchParams); // { a: '1', b: '2' }，重复 key 只保留最后一个
new URLSearchParams('a=1&a=3').getAll('a');                        // ['1', '3']
```

**边界情况**：hash 部分、编码中文、`+` 号、值含 `=`、重复 key、无值 key、非法编码（`decodeURIComponent('%')` 抛 URIError，生产中可 try/catch 原样返回）、`__proto__` 作为 key（可用 `Object.create(null)` 存储结果防原型污染）。

#### 千分位格式化 ★★ ✅

```js
function formatThousands(num) {
  const [int, dec] = String(num).split('.');
  const sign = int.startsWith('-') ? '-' : '';
  const body = sign ? int.slice(1) : int;
  // \B：非单词边界（不在开头加逗号）；(?=(\d{3})+(?!\d))：后面紧跟 3 的倍数个数字直到结尾
  const withComma = body.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return sign + withComma + (dec ? '.' + dec : '');   // 小数部分不处理
}
formatThousands(1234567.891); // '1,234,567.891'
formatThousands(-1234);       // '-1,234'

// 原生方案
(1234567.891).toLocaleString('en-US');                          // '1,234,567.891'
new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(1234.5); // '¥1,234.50'
```

**边界情况**：负数、小数（小数部分不加逗号）、科学计数法（`1e21` 转字符串是 `'1e+21'`，需先处理）、超大数用 BigInt / 字符串。追问「不用正则」：从后往前每 3 位插入逗号的循环。

---

## 附：复习自检清单

能不看资料口述 / 手写以下内容，本章即算过关：

- [ ] 8 种数据类型，三种类型判断方式的原理与缺陷
- [ ] `[] == ![]` 为什么是 true
- [ ] 闭包定义、三个用途、一个泄漏场景
- [ ] this 四规则优先级 + 箭头函数特性
- [ ] 画出 `function Foo`、`foo = new Foo()`、`Object`、`Function` 之间的原型链关系图
- [ ] 寄生组合继承代码；class 比构造函数多了哪些语义
- [ ] var / let / const / function 的提升差异，TDZ
- [ ] structuredClone 的能力边界
- [ ] V8 分代回收；WeakMap 的使用场景
- [ ] 浏览器事件循环流程；Node 6 个阶段；nextTick 与 Promise 的先后
- [ ] 3 道输出顺序题能逐步讲出队列变化
- [ ] Promise 四个组合方法的区别
- [ ] 用 Generator 实现 async 自动执行器
- [ ] Vue3 为何用 Proxy；Reflect receiver 的作用
- [ ] ESM 与 CJS 的 5 点差异，含循环依赖行为
- [ ] 不可变数组方法、Object.groupBy、Promise.withResolvers、Set 运算
- [ ] 10 分钟内手写：Promise A+、深拷贝、并发控制、LRU、防抖节流、EventEmitter
