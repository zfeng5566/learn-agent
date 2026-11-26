# 06 · Vue 生态面试知识点详解

> 对应总大纲 [`7'. 框架：Vue`](../frontend-interview-outline.md)。以 Vue3 为主，关键处对比 Vue2，覆盖 Pinia / Vue Router / Nuxt。
> 星级：★★★ 必考 / ★★ 常考 / ★ 加分项。
> 每个知识点结构：**是什么 / 原理** → **代码示例** → **面试答题要点** → **易错点 / 追问**。
> 版本基线：Vue 3.5、Pinia 3、Vue Router 4、Nuxt 4（截至 2026，新特性以官方文档为准）。

---

## 目录

- [1. 响应式原理 ★★★](#1-响应式原理-)
  - [1.1 Vue2：Object.defineProperty 及其缺陷](#11-vue2objectdefineproperty-及其缺陷)
  - [1.2 Vue3：Proxy + Reflect](#12-vue3proxy--reflect)
  - [1.3 依赖收集与触发：数据结构](#13-依赖收集与触发数据结构)
  - [1.4 手写最小响应式系统（reactive / effect / track / trigger / computed）](#14-手写最小响应式系统)
- [2. ref vs reactive ★★★](#2-ref-vs-reactive-)
- [3. computed 缓存 ★★★](#3-computed-缓存-)
- [4. watch vs watchEffect ★★★](#4-watch-vs-watcheffect-)
- [5. Composition API vs Options API ★★★](#5-composition-api-vs-options-api-)
- [6. 生命周期：Vue2 vs Vue3 ★★](#6-生命周期vue2-vs-vue3-)
- [7. 组件通信方式汇总 ★★★](#7-组件通信方式汇总-)
- [8. 模板编译与编译优化 ★★★](#8-模板编译与编译优化-)
- [9. Diff 算法 ★★★](#9-diff-算法-)
- [10. nextTick 与异步更新队列 ★★★](#10-nexttick-与异步更新队列-)
- [11. Pinia ★★★](#11-pinia-)
- [12. Vue Router 与导航守卫 ★★★](#12-vue-router-与导航守卫-)
- [13. Nuxt ★★](#13-nuxt-)
- [14. Vapor Mode ★](#14-vapor-mode-)
- [15. 高频题完整答案 ★★★](#15-高频题完整答案-)

---

## 1. 响应式原理 ★★★

### 1.1 Vue2：Object.defineProperty 及其缺陷

**是什么 / 原理**

Vue2 在 `initData` 阶段递归遍历 `data` 返回的对象，对每个属性用 `Object.defineProperty` 改写成 getter/setter：

- **getter**：把当前正在执行的 `Watcher`（`Dep.target`）收集到该属性的 `Dep` 里；
- **setter**：值变化时 `dep.notify()`，通知所有 Watcher 更新。

三个角色：`Observer`（把对象变成响应式）、`Dep`（每个属性一个依赖容器）、`Watcher`（渲染 Watcher / computed Watcher / user Watcher）。

**代码示例**

```js
// Vue2 响应式核心简化版
function defineReactive(obj, key, val) {
  const dep = new Dep()
  observe(val) // 递归：初始化时就把整棵对象树全部转换
  Object.defineProperty(obj, key, {
    enumerable: true,
    configurable: true,
    get() {
      if (Dep.target) dep.depend() // 收集当前 Watcher
      return val
    },
    set(newVal) {
      if (newVal === val) return
      val = newVal
      observe(newVal) // 新值是对象也要转换
      dep.notify()    // 通知更新
    }
  })
}

// 数组：无法拦截下标，改为以 arrayMethods 为原型，重写 7 个变异方法
const arrayMethods = Object.create(Array.prototype)
;['push', 'pop', 'shift', 'unshift', 'splice', 'sort', 'reverse'].forEach(m => {
  arrayMethods[m] = function (...args) {
    const result = Array.prototype[m].apply(this, args)
    // push/unshift/splice 插入的新元素同样 observeArray 转成响应式（略）
    this.__ob__.dep.notify()
    return result
  }
})
```

**defineProperty 的缺陷**

| 缺陷 | 表现 | Vue2 的补丁方案 |
|---|---|---|
| 无法检测属性新增 / 删除 | `this.obj.newKey = 1` 不更新视图 | `Vue.set` / `this.$set`、`Vue.delete` |
| 无法拦截数组下标与 length | `arr[0] = x`、`arr.length = 0` 不更新 | 重写 7 个数组方法；用 `splice` / `$set` |
| 初始化递归遍历 | 大对象初始化慢、内存占用高 | `Object.freeze` 冻结纯展示数据 |
| 不支持 Map / Set | 集合类型无响应式 | 无，只能转成对象 / 数组 |
| 每个属性一个闭包 + Dep | 内存开销大 | 无 |

**面试答题要点**

1. Vue2 用 `defineProperty` 劫持 **已有属性** 的 get/set，getter 收集依赖、setter 派发更新。
2. 它是"属性级"拦截，所以新增 / 删除属性、数组下标修改都感知不到，需要 `$set`。
3. 数组通过原型链拦截 7 个变异方法实现响应式，是性能权衡：遍历劫持数组下标代价太大。
4. 初始化时一次性深度递归，对象越大越慢。

**易错点 / 追问**

- 追问"defineProperty 能不能监听数组下标？"——**能**（数组本质是对象），但尤雨溪说过出于性能考虑没这么做（数组可能很长，且 length 无法劫持）。
- `this.$set(arr, index, val)` 内部其实就是调用 `arr.splice(index, 1, val)`。

### 1.2 Vue3：Proxy + Reflect

**是什么 / 原理**

Vue3 用 `Proxy` 代理 **整个对象**，拦截 `get / set / has / deleteProperty / ownKeys` 等 13 种操作中的常用几种，配合 `Reflect` 转发默认行为。

- 新增 / 删除属性、数组下标、`length`、`in`、`for...in` 全部能拦截；
- **懒代理**：只在 `get` 到嵌套对象时才对其 `reactive()`，不再初始化全量递归；
- 集合类型（Map / Set / WeakMap / WeakSet）通过 `collectionHandlers` 拦截其方法实现响应式。

**代码示例**

```js
const p = new Proxy(target, {
  get(target, key, receiver) {
    track(target, key)                        // 收集依赖
    const res = Reflect.get(target, key, receiver)
    return isObject(res) ? reactive(res) : res // 懒代理
  },
  set(target, key, value, receiver) {
    const hadKey = Object.prototype.hasOwnProperty.call(target, key)
    const oldValue = target[key]
    const result = Reflect.set(target, key, value, receiver)
    if (!hadKey) trigger(target, 'add', key)               // 新增：还要触发 ITERATE_KEY（影响 for...in / length）
    else if (!Object.is(value, oldValue)) trigger(target, 'set', key)
    return result
  },
  deleteProperty(target, key) { /* trigger(target, 'delete', key) */ },
  has(target, key) { /* track：拦截 key in obj */ },
  ownKeys(target) { /* track(target, ITERATE_KEY)：拦截 for...in / Object.keys */ }
})
```

**为什么要用 Reflect + receiver？**

```js
const obj = {
  _name: 'a',
  get name() { return this._name } // getter 内的 this
}
// 若 get 中直接 return target[key]，name getter 里的 this 指向原始对象，
// 读取 this._name 不经过代理 → _name 不会被收集依赖。
// Reflect.get(target, key, receiver) 让 this 指向代理对象，依赖才完整。
```

**面试答题要点**

1. Proxy 拦截的是对象整体的操作，天然支持新增 / 删除属性、数组下标和 length、Map/Set。
2. 嵌套对象改为访问时懒代理，初始化开销大幅降低。
3. 用 `Reflect` 保证 `this` 指向代理（receiver），并返回操作是否成功的布尔值。
4. 代价：Proxy 无法 polyfill，所以 Vue3 不支持 IE11。
5. 用 `WeakMap` 缓存 target → proxy，同一对象多次 `reactive()` 返回同一个代理。

**易错点 / 追问**

- `reactive(obj) !== obj`：只有通过代理访问才是响应式的，直接改原对象不触发更新。
- 数组 `includes / indexOf` 在代理上找原始对象会失败，Vue3 重写了这些方法（先在代理上找，找不到再用 `toRaw` 找）。
- `push` 会读 `length` 又写 `length`，若不处理会在两个 effect 间死循环——Vue3 在执行 `push/pop/shift/unshift/splice` 期间**暂停依赖收集**（`pauseTracking`）。

### 1.3 依赖收集与触发：数据结构

**是什么 / 原理**

```
targetMap: WeakMap<target, depsMap>
  └─ depsMap: Map<key, dep>
       └─ dep: Set<ReactiveEffect>   // 3.5 起改为双向链表 + 版本号实现
```

- `WeakMap` 以原始对象为 key，对象被回收时依赖自动释放；
- `track(target, key)`：在 `activeEffect` 存在时，把它加入 `targetMap[target][key]`，并在 effect 上反向记录 `deps`，用于下次执行前清理；
- `trigger(target, key)`：取出 dep，执行其中所有 effect（有 `scheduler` 就交给调度器，组件更新就是被调度到异步队列）。

> Vue 3.5 重构了响应式内部实现：依赖关系改用双向链表 + 版本计数，官方给出的数据是内存占用降低约 56%，computed 改为更彻底的惰性 / 按需重算。API 不变，面试说清 WeakMap → Map → Set 模型即可，能补一句 3.5 的优化是加分项。

**面试答题要点**

1. 三层结构：`WeakMap(target) → Map(key) → Set(effect)`。
2. 读属性时 `track`，写属性时 `trigger`；"当前在跑哪个 effect" 用全局 `activeEffect` 标记。
3. 每次 effect 执行前先 `cleanup` 旧依赖，解决"分支切换"导致的无效依赖。
4. 用 effect 栈处理嵌套 effect（组件嵌套渲染就是嵌套 effect）。
5. `scheduler` 让触发与执行解耦，是 `computed` 懒计算和组件异步更新的基础。

### 1.4 手写最小响应式系统

> 下面代码已在 Node 下用断言验证通过（基本响应、嵌套对象、分支切换、computed 缓存与惰性、effect 依赖 computed、effect 内自增、delete 触发）。

```js
// ===== 最小响应式系统：reactive / effect / track / trigger / computed =====
const targetMap = new WeakMap() // target -> Map(key -> Set<effect>)
let activeEffect = null
const effectStack = []

function effect(fn, options = {}) {
  const effectFn = () => {
    cleanup(effectFn)               // 每次执行前清空旧依赖（处理分支切换）
    activeEffect = effectFn
    effectStack.push(effectFn)
    try { return fn() }
    finally {
      effectStack.pop()
      activeEffect = effectStack[effectStack.length - 1] || null // 支持嵌套 effect
    }
  }
  effectFn.deps = []
  effectFn.scheduler = options.scheduler
  if (!options.lazy) effectFn()
  return effectFn
}

function cleanup(effectFn) {
  effectFn.deps.forEach(dep => dep.delete(effectFn))
  effectFn.deps.length = 0
}

function track(target, key) {
  if (!activeEffect) return
  let depsMap = targetMap.get(target)
  if (!depsMap) targetMap.set(target, (depsMap = new Map()))
  let dep = depsMap.get(key)
  if (!dep) depsMap.set(key, (dep = new Set()))
  dep.add(activeEffect)
  activeEffect.deps.push(dep)       // 反向记录，供 cleanup 使用
}

function trigger(target, key) {
  const dep = targetMap.get(target)?.get(key)
  if (!dep) return
  // 复制一份再遍历，避免 cleanup + 重新收集导致 Set 无限循环
  new Set(dep).forEach(fn => {
    if (fn === activeEffect) return  // 避免 effect 内自增导致无限递归
    fn.scheduler ? fn.scheduler(fn) : fn()
  })
}

const reactiveMap = new WeakMap()
function reactive(target) {
  if (reactiveMap.has(target)) return reactiveMap.get(target)
  const proxy = new Proxy(target, {
    get(t, key, receiver) {
      track(t, key)
      const res = Reflect.get(t, key, receiver)
      // 懒代理：访问到嵌套对象时才转成响应式
      return typeof res === 'object' && res !== null ? reactive(res) : res
    },
    set(t, key, value, receiver) {
      const old = t[key]
      const ok = Reflect.set(t, key, value, receiver)
      if (!Object.is(old, value)) trigger(t, key)
      return ok
    },
    deleteProperty(t, key) {
      const had = Object.prototype.hasOwnProperty.call(t, key)
      const ok = Reflect.deleteProperty(t, key)
      if (had && ok) trigger(t, key)
      return ok
    }
  })
  reactiveMap.set(target, proxy)
  return proxy
}

function computed(getter) {
  let value
  let dirty = true                  // 脏标记：依赖变了才重新计算
  const runner = effect(getter, {
    lazy: true,
    scheduler() {
      if (!dirty) {
        dirty = true
        trigger(obj, 'value')       // 通知依赖 computed 的 effect
      }
    }
  })
  const obj = {
    get value() {
      if (dirty) { value = runner(); dirty = false }
      track(obj, 'value')
      return value
    }
  }
  return obj
}

// ===== 验证 =====
const assert = require('assert')
const state = reactive({ count: 1, nested: { a: 1 }, ok: true, text: 'hi' })
let dummy, nestedVal, runs = 0, getterRuns = 0, seen, has
effect(() => { dummy = state.count }); state.count++; assert.strictEqual(dummy, 2)
effect(() => { nestedVal = state.nested.a }); state.nested.a = 10; assert.strictEqual(nestedVal, 10) // 嵌套懒代理
effect(() => { runs++; return state.ok ? state.text : 'no' })                                      // 分支切换
state.ok = false; const before = runs; state.text = 'x'; assert.strictEqual(runs, before)
const double = computed(() => { getterRuns++; return state.count * 2 })
assert.strictEqual(getterRuns, 0)                                   // 惰性：不读不算
assert.strictEqual(double.value, 4); double.value; assert.strictEqual(getterRuns, 1) // 缓存
state.count = 5; assert.strictEqual(double.value, 10); assert.strictEqual(getterRuns, 2)
effect(() => { seen = double.value }); state.count = 6; assert.strictEqual(seen, 12) // effect 依赖 computed
effect(() => { state.count++ })                                      // 自增不爆栈
effect(() => { has = state.text }); delete state.text; assert.strictEqual(has, undefined)
console.log('all passed')
```

**实现要点逐条说明（面试手写时边写边讲）**

| 设计点 | 解决的问题 |
|---|---|
| `cleanup` + `effectFn.deps` | 分支切换：`ok ? text : 'no'` 在 `ok=false` 后不应再依赖 `text` |
| `effectStack` | 嵌套 effect：内层执行完要把 `activeEffect` 恢复成外层 |
| `new Set(dep)` 再遍历 | 遍历中 cleanup 删除、重新执行又添加，原 Set 会无限循环 |
| `fn === activeEffect` 跳过 | `state.count++` 既读又写，自己触发自己导致栈溢出 |
| `lazy` + `scheduler` + `dirty` | computed 惰性计算、依赖变化只标脏不立即算 |
| computed 内 `track/trigger(obj,'value')` | 让外层 effect 能依赖 computed |
| `reactiveMap` 缓存 | 同一对象重复代理返回同一 proxy，避免 `reactive(a) !== reactive(a)` |

**易错点 / 追问**

- 真实 Vue 还要处理：`ITERATE_KEY`（`for...in`、新增属性影响 `Object.keys`）、数组 `length` 联动、`readonly / shallowReactive`、`ref`、集合类型、`effectScope`。
- 追问"组件更新为什么不是同步的？"——渲染 effect 的 scheduler 是 `queueJob(update)`，见第 10 节。

---

## 2. ref vs reactive ★★★

**是什么 / 原理**

- `reactive(obj)`：返回对象的 Proxy，只接受对象类型（对象、数组、Map、Set）。
- `ref(value)`：返回一个 `RefImpl` 实例，通过类的 `get value / set value` 访问器拦截 `.value`；值为对象时内部会调用 `reactive()` 转换。
- 模板与 `reactive` 对象中的 ref 会**自动解包**（模板顶层属性、reactive 对象属性），数组和 Map 元素中的 ref 不解包。

**代码示例**

```js
import { ref, reactive, toRefs, shallowRef, triggerRef } from 'vue'

const count = ref(0); count.value++
const state = reactive({ list: [], name: 'a' })

// ❌ 解构丢失响应式：基本类型拿到的是普通值
let { name } = state
name = 'b'                   // 只改了局部变量

// ✅ toRefs：把 reactive 每个属性转成 ref，保持与源的连接
const { list: listRef } = toRefs(state)
listRef.value = []           // 等同 state.list = []

// ❌ 整体替换 reactive 会断开：let s = reactive({}); s = reactive({ a: 2 })  模板仍绑旧代理
// ✅ 用 ref 包对象可整体替换
const s2 = ref({ a: 1 }); s2.value = { a: 2 }

// 大数据 / 外部实例：shallowRef 只追踪 .value 替换
const bigList = shallowRef([])
bigList.value.push(1)        // 不触发
triggerRef(bigList)          // 手动触发
```

**对比表**

| 维度 | ref | reactive |
|---|---|---|
| 接受类型 | 任意 | 仅对象类型 |
| 访问方式 | JS 中 `.value`，模板自动解包 | 直接访问属性 |
| 整体替换 | 支持 `x.value = 新对象` | 不支持（会丢失响应式） |
| 解构 | 本身就是一个值容器 | 解构丢响应式，需 `toRefs` |
| 实现 | 类的 getter/setter（对象值内部转 reactive） | Proxy |

**面试答题要点**

1. 基本类型无法被 Proxy 代理，所以需要 `ref` 用对象包一层，通过 `.value` 访问器实现拦截。
2. `reactive` 的局限：不能整体替换、解构丢响应式、只接受对象。
3. 官方推荐**默认使用 `ref`**，心智统一；表单等一组强相关字段可用 `reactive`。
4. 解构用 `toRefs / toRef`；组合式函数返回 ref 对象，调用方解构不丢响应式。
5. 大型不可变数据用 `shallowRef / markRaw` 避免深度代理开销。

**易错点 / 追问**

- `reactive` 中嵌套 ref 会自动解包，但 `reactive([ref(1)])[0]` 仍需 `.value`。
- `watch(state.count, ...)` 错：传的是值；应 `watch(() => state.count, ...)`。
- 第三方类实例（地图、编辑器）放进 `reactive` 会被深度代理导致性能问题甚至报错，用 `markRaw` 或 `shallowRef`。
- Vue 3.5 起 `defineProps` 解构保持响应式（编译器自动改写为 `props.xxx`），但传给 `watch` 时仍需写成 getter：`watch(() => count, ...)`。

---

## 3. computed 缓存 ★★★

**是什么 / 原理**

`computed` 是一个**惰性 + 带缓存**的 effect：

- 内部有 `dirty` 标记；首次读取 `.value` 才执行 getter；
- 依赖变化时 scheduler 只把 `dirty = true` 并通知下游，**不立即重算**；
- 下次读取时发现 dirty 才重算，否则返回缓存值。
- Vue 3.4 起：依赖变化后如果重算结果与旧值相同（`Object.is`），不会触发下游更新。

**代码示例**

```js
const firstName = ref('Zhang')
const lastName = ref('San')

// 只读
const fullName = computed(() => `${firstName.value} ${lastName.value}`)

// 可写
const fullName2 = computed({
  get: () => `${firstName.value} ${lastName.value}`,
  set: (v) => { [firstName.value, lastName.value] = v.split(' ') }
})

// 3.4+：getter 可拿到上一次的值
const maxSeen = computed((prev) => Math.max(prev ?? 0, count.value))
```

**computed vs methods vs watch**

| | computed | methods | watch |
|---|---|---|---|
| 缓存 | 有，依赖不变不重算 | 无，每次渲染都执行 | 不适用 |
| 返回值 | 必须有 | 可有可无 | 无 |
| 副作用 | 不应有 | 可以 | 用于副作用 |
| 异步 | 不支持 | 支持 | 支持 |

**面试答题要点**

1. computed 本质是 `lazy` 的 effect + `dirty` 脏标记 + scheduler。
2. 依赖变化只标脏、不重算，真正读取时才算——"惰性求值 + 缓存"。
3. computed 既是依赖的消费者，也是外层 effect 的依赖提供者（自己会 track/trigger）。
4. 适合派生状态；有副作用、异步就用 watch。
5. getter 要纯：不能在里面改其他状态、发请求。

**易错点 / 追问**

- 依赖非响应式数据（如 `Date.now()`、`localStorage`）不会更新。
- 返回新对象/数组的 computed，每次重算都是新引用，下游仍会更新（3.4 的"值相同不触发"对引用类型无效，可用 getter 的 `prev` 参数自行比较后返回旧引用）。
- Vue2 的 computed 是 `lazy Watcher`，原理相同。

---

## 4. watch vs watchEffect ★★★

**是什么 / 原理**

- `watch(source, cb, options)`：显式指定数据源，懒执行（默认不立即执行），能拿到新旧值。
- `watchEffect(fn)`：立即执行一次，自动收集 fn 中用到的依赖，拿不到旧值。
- 两者底层都是 `ReactiveEffect` + scheduler，`flush` 决定回调时机：
  - `'pre'`（默认）：组件更新**前**执行；
  - `'post'`：组件更新**后**执行，可访问更新后的 DOM（`watchPostEffect`）；
  - `'sync'`：同步执行（慎用，`watchSyncEffect`）。

**代码示例**

```js
import { watch, watchEffect, onWatcherCleanup } from 'vue'

// 1. 单个 ref
watch(count, (newVal, oldVal) => {})

// 2. getter（监听 reactive 的某个属性必须用 getter）
watch(() => state.user.id, (id) => fetchUser(id), { immediate: true })

// 3. 多个源
watch([a, () => state.b], ([na, nb], [oa, ob]) => {})

// 4. 直接传 reactive 对象：隐式 deep
watch(state, () => {})       // 新旧值是同一个对象引用！

// 5. 选项：deep 支持数字（3.5，限制遍历深度）、once（3.4）
watch(src, cb, { deep: 2, once: true, flush: 'post' })

// 6. 清理竞态请求
watch(id, async (newId) => {
  const controller = new AbortController()
  onWatcherCleanup(() => controller.abort()) // 3.5+；旧版用 cb 的第三个参数 onCleanup
  data.value = await fetch(`/api/${newId}`, { signal: controller.signal }).then(r => r.json())
})

// 7. watchEffect 自动收集
const stop = watchEffect(() => {
  console.log(state.user.name)   // 用到谁就依赖谁
})
stop()                            // 手动停止；3.5 还提供 pause()/resume()
```

**对比表**

| | watch | watchEffect |
|---|---|---|
| 依赖 | 显式指定 | 自动收集（仅同步执行阶段） |
| 首次执行 | 默认不执行，`immediate: true` 才执行 | 立即执行 |
| 新旧值 | 有 | 无 |
| 适用 | 需要精确控制触发源、对比新旧值 | 依赖多、只关心"相关数据变了就重跑" |

**面试答题要点**

1. watch 显式、懒执行、有新旧值；watchEffect 自动收集、立即执行、无旧值。
2. 监听 reactive 的属性要传 getter；直接传 reactive 对象是深度监听且新旧值相同。
3. `flush` 控制时机，需要操作更新后的 DOM 用 `'post'`。
4. 用 `onWatcherCleanup` / `onCleanup` 处理异步竞态。
5. 在 `setup` 同步阶段创建的 watcher 随组件卸载自动停止；异步创建（如 `setTimeout` 里）的需手动 `stop`，否则内存泄漏。

**易错点 / 追问**

- watchEffect 中 `await` 之后访问的响应式数据**不会被收集**（依赖收集只在同步阶段）。
- 深度监听大对象开销大，优先监听具体字段。
- Vue2 `this.$watch` / `watch` 选项对应 Vue3 的 `watch`；Vue2 没有 watchEffect。

---

## 5. Composition API vs Options API ★★★

**是什么 / 原理**

- Options API：按 `data / computed / methods / watch / 生命周期` 选项组织代码，`this` 指向组件实例。
- Composition API：在 `setup()`（或 `<script setup>`）中用函数组织逻辑，按**功能关注点**聚合，通过组合式函数（composable）复用。
- Options API 在 Vue3 中是基于 Composition API 实现的一层，两者可混用。

**代码示例**

```js
// composables/useMouse.js —— 逻辑复用单元
import { ref, onMounted, onUnmounted } from 'vue'
export function useMouse() {
  const x = ref(0)
  const y = ref(0)
  const update = (e) => { x.value = e.pageX; y.value = e.pageY }
  onMounted(() => window.addEventListener('mousemove', update))
  onUnmounted(() => window.removeEventListener('mousemove', update))
  return { x, y } // 返回 ref，调用方解构不丢响应式
}
```

```vue
<script setup lang="ts">
import { useMouse } from './composables/useMouse'
const { x, y } = useMouse()
const props = defineProps<{ title: string }>()
const emit = defineEmits<{ change: [value: number] }>()
const model = defineModel<string>()  // 3.4+ 双向绑定
</script>

<template>{{ title }}：{{ x }}, {{ y }}</template>
```

**对比 Vue2 的复用方案**

| 方案 | 问题 |
|---|---|
| mixin | 命名冲突、来源不清晰（模板里的变量不知道来自哪个 mixin）、隐式依赖 |
| HOC / 高阶组件 | 多一层组件实例，props 透传繁琐 |
| 作用域插槽 | 逻辑和模板耦合 |
| **composable** | 显式引入、来源清晰、可传参、无额外实例、TS 推导友好 |

**面试答题要点**

1. Options API 按选项类型拆分，大组件里一个功能散落在多个选项中；Composition API 按功能聚合。
2. 逻辑复用：composable 替代 mixin，解决命名冲突与来源不明。
3. 类型推导更好：不依赖 `this`，函数参数和返回值天然可推导。
4. `<script setup>` 编译期优化：顶层变量直接暴露给模板，编译成内联渲染函数，生产包更小、性能更好。
5. 不是必须二选一：简单组件 Options API 依然可读，团队可约定规范。

**易错点 / 追问**

- `setup` 中没有 `this`；`setup` 在 `beforeCreate` 之前执行。
- `<script setup>` 组件默认是**关闭**的：父组件通过 ref 拿不到内部变量，需 `defineExpose`。
- composable 必须在 `setup` 同步调用，否则 `onMounted` 等钩子找不到当前实例（`getCurrentInstance()` 为 null）。
- 追问"Composition API 和 React Hooks 区别？"——setup 只执行一次，没有闭包陈旧值问题，不需要依赖数组，不受调用顺序限制（可放在条件里），响应式自动追踪。

---

## 6. 生命周期：Vue2 vs Vue3 ★★

**对照表**

| Vue2（Options） | Vue3 Options API | Vue3 Composition API | 说明 |
|---|---|---|---|
| beforeCreate | beforeCreate | —（`setup` 本身） | 实例初始化，data 未就绪 |
| created | created | —（`setup` 本身） | data / computed 已就绪，无 DOM |
| beforeMount | beforeMount | onBeforeMount | 渲染函数首次调用前 |
| mounted | mounted | onMounted | DOM 已挂载（不保证子组件异步内容） |
| beforeUpdate | beforeUpdate | onBeforeUpdate | 数据变了、DOM 更新前 |
| updated | updated | onUpdated | DOM 更新后 |
| beforeDestroy | **beforeUnmount** | onBeforeUnmount | 改名 |
| destroyed | **unmounted** | onUnmounted | 改名 |
| activated | activated | onActivated | KeepAlive 缓存组件激活 |
| deactivated | deactivated | onDeactivated | KeepAlive 缓存组件失活 |
| errorCaptured | errorCaptured | onErrorCaptured | 捕获后代错误 |
| — | renderTracked | onRenderTracked | 开发调试：依赖被收集 |
| — | renderTriggered | onRenderTriggered | 开发调试：依赖触发重渲染 |
| — | serverPrefetch | onServerPrefetch | SSR 数据预取 |

**父子组件执行顺序**

```
挂载：父 setup/beforeCreate → 父 created → 父 beforeMount
     → 子 setup → 子 beforeMount → 子 mounted
     → 父 mounted
更新：父 beforeUpdate → 子 beforeUpdate → 子 updated → 父 updated
卸载：父 beforeUnmount → 子 beforeUnmount → 子 unmounted → 父 unmounted
```

**面试答题要点**

1. Vue3 用 `setup` 取代 `beforeCreate/created`，销毁钩子改名为 `unmount`。
2. 组合式钩子可多次注册、可在 composable 中注册。
3. 父子顺序：父先开始、子先完成（mounted 是子先父后）。
4. 请求放 `created`/`setup` 还是 `mounted`：都可以，`setup` 更早；SSR 下 `mounted` 不执行，需用 `onServerPrefetch` 或 Nuxt 的 `useFetch`。

**易错点 / 追问**

- 在 `updated` 里修改状态可能导致无限更新循环。
- 子组件是异步组件 / 在 Suspense 中时，父 mounted 不保证子组件已渲染。
- Vue3 在 `<KeepAlive>` 里首次挂载也会调用 `onActivated`。

---

## 7. 组件通信方式汇总 ★★★

**汇总表**

| 方式 | 方向 | Vue3 写法 | Vue2 差异 / 备注 |
|---|---|---|---|
| props | 父 → 子 | `defineProps` | 单向数据流，子不可直接改 |
| emit | 子 → 父 | `defineEmits` + `emit('x')` | Vue3 推荐声明 emits |
| v-model | 双向 | `defineModel()`（3.4+），或 `modelValue` + `update:modelValue` | Vue2 默认 `value` + `input`，`.sync` 修饰符在 Vue3 移除，改为 `v-model:title` |
| 透传 attrs | 父 → 子孙 | `useAttrs()` / `$attrs` | Vue3 `$attrs` 包含 class、style 和事件监听；`$listeners` 移除 |
| ref + expose | 父 → 子（调用方法） | `useTemplateRef`（3.5+）/ `ref` + 子 `defineExpose` | `<script setup>` 默认关闭，需 expose |
| provide / inject | 祖先 → 后代 | `provide(key, value)` / `inject(key, default)` | 传 ref 可保持响应式；用 `InjectionKey` 做类型 |
| 插槽 | 父 → 子（模板）/ 子 → 父（作用域数据） | `<slot :item="item">` + `v-slot="{ item }"` | Vue2.6 统一为 `v-slot` |
| 全局状态 | 任意 | Pinia | Vue2 时代用 Vuex |
| 事件总线 | 任意 | `mitt` 等第三方库 | Vue3 移除 `$on/$off/$once`，不能 `new Vue()` 当 bus |
| $parent / $root | 子 → 祖先 | 不推荐 | 强耦合 |
| 路由参数 / URL | 页面间 | `useRoute()` | 适合可分享状态 |

**代码示例**

```ts
// provide / inject 带类型与响应式
// keys.ts
import type { InjectionKey, Ref } from 'vue'
export const ThemeKey: InjectionKey<{ theme: Ref<string>; toggle: () => void }> = Symbol('theme')

// 祖先
const theme = ref('light')
provide(ThemeKey, { theme: readonly(theme), toggle: () => (theme.value = theme.value === 'light' ? 'dark' : 'light') })

// 后代
const { theme, toggle } = inject(ThemeKey)!
```

```vue
<!-- 子组件：defineModel 双向绑定（3.4+） -->
<script setup>
const title = defineModel('title', { required: true })
</script>
<template><input v-model="title" /></template>

<!-- 父组件 -->
<Child v-model:title="pageTitle" />
```

**面试答题要点**

1. 父子：props / emit / v-model / ref+expose；跨层：provide/inject；全局：Pinia。
2. 坚持单向数据流：子组件改数据通过 emit，provide 时推荐暴露 `readonly` 状态 + 修改方法。
3. Vue3 的变化：移除 `$on` 事件总线、`$listeners` 合并进 `$attrs`、`.sync` 改为 `v-model:xxx`、支持多个 v-model。
4. 选择原则：就近原则，能 props 就不全局，跨 3 层以上或兄弟复杂共享再上 provide/Pinia。

**易错点 / 追问**

- props 是对象时子组件改其内部属性"能生效"但违反单向数据流，难以追踪，应避免。
- `inject` 直接 provide 一个普通值不具备响应式。
- `inheritAttrs: false` 配合 `v-bind="$attrs"` 控制透传落点。

---

## 8. 模板编译与编译优化 ★★★

**编译流程**

```
template 字符串
  → parse：解析成模板 AST
  → transform：遍历 AST，做静态分析、打标记（PatchFlag、静态提升、v-if/v-for 转换等）
  → generate：生成 render 函数代码字符串
```

Vue3 的核心思想：**编译时尽量多地分析，把信息传给运行时，让 diff 只做必要的事**（"编译时 + 运行时"结合，React 则主要依靠运行时）。

可在 [Vue Template Explorer](https://template-explorer.vuejs.org/) 实时查看编译结果。

### 8.1 静态提升（hoistStatic）

**是什么**：纯静态节点 / 静态属性在 render 函数外创建一次，后续渲染直接复用，不再重新创建 VNode，diff 时也直接跳过。

```html
<div>
  <p class="title">静态标题</p>
  <span>{{ msg }}</span>
</div>
```

```js
// 编译后（示意，3.4 及以前形态）
const _hoisted_1 = /*#__PURE__*/ _createElementVNode("p", { class: "title" }, "静态标题", -1 /* HOISTED */)

export function render(_ctx) {
  return (_openBlock(), _createElementBlock("div", null, [
    _hoisted_1,                                                     // 复用，不重新创建
    _createElementVNode("span", null, _toDisplayString(_ctx.msg), 1 /* TEXT */)
  ]))
}
```

> 3.5 起编译器将静态 VNode 改为放入组件级 `_cache` 缓存（标记 `CACHED`），目的相同；面试按"静态提升"讲即可。
> 连续大量静态节点（默认 ≥ 20 个）会被合并成一个**静态字符串节点**（`createStaticVNode`），通过 `innerHTML` 一次性创建。

### 8.2 PatchFlag（补丁标记）

**是什么**：编译器给动态节点打上位掩码标记，说明它**哪部分是动态的**，运行时 patch 只比对这些部分。

| PatchFlag | 值 | 含义 |
|---|---|---|
| TEXT | 1 | 动态文本 |
| CLASS | 2 | 动态 class |
| STYLE | 4 | 动态 style |
| PROPS | 8 | 动态非 class/style 属性（配合 dynamicProps 列表） |
| FULL_PROPS | 16 | 有动态 key 的属性（如 `v-bind="obj"`），需全量 diff |
| NEED_HYDRATION | 32 | 需要 hydration 处理事件等（旧名 HYDRATE_EVENTS） |
| STABLE_FRAGMENT | 64 | 子节点顺序不变的 Fragment |
| KEYED_FRAGMENT | 128 | 带 key 的 v-for Fragment |
| UNKEYED_FRAGMENT | 256 | 不带 key 的 v-for Fragment |
| NEED_PATCH | 512 | 只需非 props 的 patch（如 ref、指令） |
| DYNAMIC_SLOTS | 1024 | 动态插槽 |
| HOISTED / CACHED | -1 | 静态节点，永不 diff |
| BAIL | -2 | 退出优化，全量 diff |

```html
<div :class="cls" :id="id">{{ text }}</div>
```

```js
_createElementVNode("div", { class: _normalizeClass(_ctx.cls), id: _ctx.id },
  _toDisplayString(_ctx.text),
  11 /* TEXT, CLASS, PROPS */,   // 1 | 2 | 8 = 11
  ["id"]                          // dynamicProps：只比对 id
)
```

运行时判断：`if (patchFlag & PatchFlags.CLASS) { 只更新 class }`，位运算组合与判断都极快。

### 8.3 Block Tree

**是什么**：带 `openBlock()` 的节点称为 Block，它会把内部**所有动态后代节点**（不论层级多深）平铺收集到 `dynamicChildren` 数组中。更新时只遍历 `dynamicChildren`，跳过静态结构，使 diff 复杂度从"与模板大小相关"变为"与动态节点数量相关"。

```html
<div>
  <section>
    <div>
      <p>静态</p>
      <span>{{ a }}</span>
    </div>
  </section>
  <b>{{ b }}</b>
</div>
```

```
Block(div)
  dynamicChildren: [ span(TEXT), b(TEXT) ]   ← 直接拍平，无需逐层递归
```

**结构不稳定的节点要单独成 Block**：`v-if / v-else`、`v-for` 会让节点结构变化，`dynamicChildren` 无法一一对应，所以它们各自成为新 Block，父 Block 把它们当作一个动态节点收集，形成 **Block Tree**。

```js
// v-if 分支单独 openBlock，用 key 区分分支
_ctx.ok
  ? (_openBlock(), _createElementBlock("div", { key: 0 }, ...))
  : (_openBlock(), _createElementBlock("p", { key: 1 }, ...))
```

### 8.4 事件缓存（cacheHandlers）

**是什么**：内联事件处理函数每次渲染都会生成新函数，导致子组件 props 变化。编译器把它缓存到 `_cache` 中，节点因此可以视为静态。

```html
<button @click="onClick">点我</button>
```

```js
// 未开启缓存：每次 render 都是新的箭头函数，且带 PROPS 标记
_createElementVNode("button", { onClick: _ctx.onClick }, "点我", 8 /* PROPS */, ["onClick"])

// 开启缓存后：节点无 PatchFlag，不参与 diff
_createElementVNode("button", {
  onClick: _cache[0] || (_cache[0] = (...args) => (_ctx.onClick && _ctx.onClick(...args)))
}, "点我")
```

缓存的是一个包装函数，内部每次调用都读取最新的 `_ctx.onClick`，因此即使 `onClick` 变了也能调用到最新函数。

### 8.5 其他编译期优化

`<script setup>` 内联模式（render 直接访问局部变量，省去 `_ctx` 代理）、SSR 静态内容直接拼字符串、内置组件按需引入支持 tree-shaking。

**面试答题要点**

1. Vue3 编译器做静态分析，把"哪些是动态的、动态在哪"告诉运行时——靶向更新。
2. 静态提升：静态节点只创建一次，diff 直接跳过。
3. PatchFlag：位掩码标记动态部分，patch 只比对标记的内容。
4. Block Tree：把动态节点拍平到 `dynamicChildren`，更新时跳过静态结构；`v-if/v-for` 单独成 Block 处理结构变化。
5. 事件缓存：避免内联函数每次新建导致的无效更新。

**易错点 / 追问**

- 手写 render 函数 / JSX 默认享受不到这些优化（没有编译期信息），会走全量 diff（Vue JSX 插件能做部分优化）。
- 追问"为什么 React 不这么做？"——JSX 是 JS 表达式，灵活性高难以静态分析；Vue 模板语法受限，换来可分析性。

---

## 9. Diff 算法 ★★★

**共同前提**

- 只做**同层比较**，不跨层移动，复杂度从 O(n³) 降到 O(n)；
- `sameVnode`：`key` 相同且 `type`（标签/组件）相同才视为同一节点，可复用并 patch；否则直接销毁重建；
- 只有在**新旧都有子节点数组**时才进入核心 diff。

### 9.1 Vue2：双端对比

**原理**：四个指针 `oldStart / oldEnd / newStart / newEnd`，每轮依次尝试 4 种比较：

1. 旧头 vs 新头 → 相同则 patch，两个头指针右移；
2. 旧尾 vs 新尾 → 相同则 patch，两个尾指针左移；
3. 旧头 vs 新尾 → 相同则 patch，并把旧头 DOM **移到旧尾之后**；
4. 旧尾 vs 新头 → 相同则 patch，并把旧尾 DOM **移到旧头之前**；
5. 都不命中 → 用新头的 key 在旧节点 key→index 映射中查找：找到则移动复用，找不到则新建。

循环结束后：旧的先遍历完 → 剩余新节点批量新增；新的先遍历完 → 剩余旧节点批量删除。

```js
// Vue2 updateChildren 简化
function updateChildren(parentElm, oldCh, newCh) {
  let oldStartIdx = 0, newStartIdx = 0
  let oldEndIdx = oldCh.length - 1, newEndIdx = newCh.length - 1
  let oldStartVnode = oldCh[0], oldEndVnode = oldCh[oldEndIdx]
  let newStartVnode = newCh[0], newEndVnode = newCh[newEndIdx]
  let oldKeyToIdx

  while (oldStartIdx <= oldEndIdx && newStartIdx <= newEndIdx) {
    if (!oldStartVnode) oldStartVnode = oldCh[++oldStartIdx]          // 已被移走的空位
    else if (!oldEndVnode) oldEndVnode = oldCh[--oldEndIdx]
    else if (sameVnode(oldStartVnode, newStartVnode)) {               // ① 头头
      patchVnode(oldStartVnode, newStartVnode)
      oldStartVnode = oldCh[++oldStartIdx]; newStartVnode = newCh[++newStartIdx]
    } else if (sameVnode(oldEndVnode, newEndVnode)) {                 // ② 尾尾
      patchVnode(oldEndVnode, newEndVnode)
      oldEndVnode = oldCh[--oldEndIdx]; newEndVnode = newCh[--newEndIdx]
    } else if (sameVnode(oldStartVnode, newEndVnode)) {               // ③ 旧头新尾
      patchVnode(oldStartVnode, newEndVnode)
      parentElm.insertBefore(oldStartVnode.elm, oldEndVnode.elm.nextSibling)
      oldStartVnode = oldCh[++oldStartIdx]; newEndVnode = newCh[--newEndIdx]
    } else if (sameVnode(oldEndVnode, newStartVnode)) {               // ④ 旧尾新头
      patchVnode(oldEndVnode, newStartVnode)
      parentElm.insertBefore(oldEndVnode.elm, oldStartVnode.elm)
      oldEndVnode = oldCh[--oldEndIdx]; newStartVnode = newCh[++newStartIdx]
    } else {                                                          // ⑤ key 映射查找
      oldKeyToIdx ??= createKeyToOldIdx(oldCh, oldStartIdx, oldEndIdx)
      const idxInOld = oldKeyToIdx[newStartVnode.key]
      if (idxInOld == null) {
        createElm(newStartVnode, parentElm, oldStartVnode.elm)        // 新建
      } else {
        const vnodeToMove = oldCh[idxInOld]
        patchVnode(vnodeToMove, newStartVnode)
        oldCh[idxInOld] = undefined                                    // 标记已处理
        parentElm.insertBefore(vnodeToMove.elm, oldStartVnode.elm)
      }
      newStartVnode = newCh[++newStartIdx]
    }
  }
  if (oldStartIdx > oldEndIdx) addVnodes(parentElm, newCh, newStartIdx, newEndIdx)
  else if (newStartIdx > newEndIdx) removeVnodes(oldCh, oldStartIdx, oldEndIdx)
}
```

### 9.2 Vue3：快速 Diff + 最长递增子序列

**原理**（`patchKeyedChildren`），分 5 步：

1. **前置预处理**：从头开始比，相同就 patch，直到遇到不同；
2. **后置预处理**：从尾开始比，相同就 patch；
3. **只剩新增**：旧节点处理完、新节点有剩余 → 挂载剩余新节点；
4. **只剩删除**：新节点处理完、旧节点有剩余 → 卸载剩余旧节点；
5. **乱序部分**：
   - 为剩余新节点建 `keyToNewIndexMap`（key → 新下标）；
   - 遍历剩余旧节点：在新节点中找不到的卸载；找到的 patch，并填 `newIndexToOldIndexMap[新位置] = 旧下标 + 1`（0 表示新节点）；
   - 遍历过程中若发现旧节点对应的新下标不是递增的，标记 `moved = true`；
   - 若需要移动，求 `newIndexToOldIndexMap` 的**最长递增子序列（LIS）**——这些节点在新旧中的相对顺序没变，**不用移动**；
   - **从后往前**遍历新节点：值为 0 → 新建挂载；不在 LIS 中 → 移动到下一个节点之前；在 LIS 中 → 跳过。

**示例**

```
旧：a b [c d e] f g
新：a b [e c d h] f g

1/2. 头尾预处理后，剩余：旧 [c d e]，新 [e c d h]
5. newIndexToOldIndexMap（按新顺序，值=旧下标+1）：
     e→5, c→3, d→4, h→0   =>  [5, 3, 4, 0]
   LIS（忽略 0）= 下标 [1, 2]，即 c、d 不动
   从后往前：h 值为 0 → 新建；d、c 在 LIS → 跳过；e 不在 → 移动到 c 前
   结果：只移动 1 次 DOM + 新建 1 个
```

**LIS 算法（Vue3 `getSequence`，贪心 + 二分 + 前驱回溯，O(n log n)）**

> 以下代码已在 Node 下验证：`[2,3,1,5,6,8,7,9,4]` → `[0,1,3,4,6,7]`；`[5,3,4,0]` → `[1,2]`。

```js
/**
 * 求最长递增子序列，返回的是"下标"数组
 * @param {number[]} arr newIndexToOldIndexMap，0 表示新节点，不参与
 * @returns {number[]} 构成 LIS 的元素下标
 */
function getSequence(arr) {
  const p = arr.slice()          // p[i]：arr[i] 在递增序列中的前驱下标
  const result = [0]             // 存下标，对应 arr 值严格递增
  for (let i = 0; i < arr.length; i++) {
    const cur = arr[i]
    if (cur === 0) continue      // 0 表示新节点，不参与
    const last = result[result.length - 1]
    if (arr[last] < cur) { p[i] = last; result.push(i); continue }
    let lo = 0, hi = result.length - 1   // 二分找第一个 >= cur 的位置
    while (lo < hi) {
      const mid = (lo + hi) >> 1
      if (arr[result[mid]] < cur) lo = mid + 1
      else hi = mid
    }
    if (cur < arr[result[lo]]) {
      if (lo > 0) p[i] = result[lo - 1]
      result[lo] = i
    }
  }
  // 回溯修正：贪心替换后 result 只保证"长度正确"，需用前驱数组还原真实序列
  let len = result.length, last = result[len - 1]
  while (len-- > 0) { result[len] = last; last = p[last] }
  return result
}
```

> 注：`result = [0]` 起步，若 `arr[0]` 恰为 0 它会留在结果里，但移动阶段先判断"值为 0 → 新建挂载"，不影响正确性。面试手写可概括为"贪心维护每个长度的最小结尾 + 二分替换 + 前驱数组回溯"。

**Vue2 vs Vue3 Diff 对比**

| | Vue2 双端 | Vue3 快速 Diff |
|---|---|---|
| 预处理 | 4 种端点比较交替进行 | 先头后尾剥离相同前后缀 |
| 乱序处理 | 逐个 key 查找并移动 | 建映射 + LIS，求最少移动 |
| 移动次数 | 不一定最少 | LIS 保证移动次数最少 |
| 配合编译 | 无 | 配合 Block Tree，只 diff 动态节点 |

**面试答题要点**

1. 都是同层比较 + key/type 判断复用。
2. Vue2 双端对比：四指针四种比较，覆盖头尾移动、反转等常见场景。
3. Vue3 先剥离相同前后缀（借鉴文本 diff），再处理新增/删除，最后乱序部分用 LIS 找"不需要移动"的最长子序列。
4. LIS 使 DOM 移动次数最少，时间复杂度 O(n log n)。
5. 从后往前遍历是为了以"后一个已就位节点"作为 `insertBefore` 的锚点。

**易错点 / 追问**

- Vue3 diff 只在"带 key 的子节点数组"走 `patchKeyedChildren`；无 key 走 `patchUnkeyedChildren`（按下标逐个 patch，多删少补）。
- 若乱序部分没检测到移动（`moved=false`），跳过 LIS 计算。
- 追问"React diff 是怎样的？"——React 单向从左遍历，用 `lastPlacedIndex` 判断是否右移，不做双端，也不求 LIS（Fiber 链表不便于反向遍历）。

---

## 10. nextTick 与异步更新队列 ★★★

**是什么 / 原理**

数据变化后 Vue 不会立刻更新 DOM，而是把组件更新任务 `queueJob` 进队列，在**同一轮事件循环的微任务**中统一 flush：

1. 同一组件多次修改数据，update job 按 id 去重，只入队一次；
2. `queueFlush` 用 `Promise.resolve().then(flushJobs)` 安排一次微任务；
3. `flushJobs`：先执行 `pre` 队列（`flush: 'pre'` 的 watcher），再按组件 id **从小到大排序**执行更新（保证父先于子，且父卸载后子更新可跳过），最后执行 `post` 队列（`mounted/updated` 钩子、`flush: 'post'` watcher、模板 ref 设置）。
4. `nextTick(fn)` 本质是 `currentFlushPromise.then(fn)`，即排在本轮 DOM 更新之后。

Vue2 的 `nextTick` 有降级策略：`Promise.then` → `MutationObserver` → `setImmediate` → `setTimeout(0)`。Vue3 只用 Promise。

**代码示例**

```js
// Vue3 调度器简化
const queue = []
let isFlushPending = false
const resolvedPromise = Promise.resolve()
let currentFlushPromise = null

function queueJob(job) {
  if (!queue.includes(job)) queue.push(job)   // 去重
  if (!isFlushPending) {
    isFlushPending = true
    currentFlushPromise = resolvedPromise.then(flushJobs)
  }
}

function flushJobs() {
  isFlushPending = false
  queue.sort((a, b) => a.id - b.id)           // 父组件先更新
  for (const job of queue) job()
  queue.length = 0
  // flushPostFlushCbs()  → mounted / updated / post watcher
}

function nextTick(fn) {
  const p = currentFlushPromise || resolvedPromise
  return fn ? p.then(fn) : p
}
```

```js
// 组件中使用：修改数据后等待 DOM 更新再滚动到底部
async function add() {
  list.value.push(Date.now())
  await nextTick()                                     // 此前读 DOM 拿到的是旧结构
  listEl.value.scrollTop = listEl.value.scrollHeight
}
```

**面试答题要点**

1. 异步批量更新：同一 tick 内多次修改只触发一次渲染，避免重复计算与 DOM 操作。
2. 更新 job 去重 + 按 id 排序（父先子后），在微任务中 flush。
3. `nextTick` 返回 Promise，回调排在本轮更新之后，用于读取更新后的 DOM。
4. Vue2 有微任务到宏任务的降级链；Vue3 直接用 `Promise.then`。
5. 与事件循环的关系：同步代码 → 微任务（DOM 更新 + nextTick 回调）→ 浏览器渲染。

**易错点 / 追问**

- 在数据修改**之前**调用的 `nextTick`，其回调可能先于 DOM 更新执行（Vue2 中明显；Vue3 若尚无 flush 排队则回调排在 `resolvedPromise` 上）。
- `nextTick` 后 DOM 已更新，但浏览器**还没绘制**；需要等绘制用 `requestAnimationFrame`。
- 递归更新保护：同一 job 在一次 flush 中执行超过 100 次会报警（`RECURSION_LIMIT`）。

---

## 11. Pinia ★★★

**是什么 / 原理**

Pinia 是 Vue 官方状态管理库（Vuex 的继任者）：

- 每个 store 本质是一个 `effectScope` 内的 `reactive` 对象，state 存在全局 `pinia.state`（便于 SSR 序列化与 devtools）；
- 去掉了 Vuex 的 `mutations`，`actions` 同步异步皆可；
- 无嵌套 module，store 扁平化、按需引入，天然支持代码分割与 tree-shaking；
- 完整 TS 推导；Pinia 3 起只支持 Vue 3。

**代码示例**

```ts
// stores/user.ts —— Setup Store（推荐，与 Composition API 一致）
import { defineStore } from 'pinia'
export const useUserStore = defineStore('user', () => {
  const token = ref('')                                  // state
  const profile = ref<{ name: string } | null>(null)
  const isLogin = computed(() => !!token.value)         // getter
  async function login(form: { u: string; p: string }) { // action
    token.value = await api.login(form)
    profile.value = await api.me()
  }
  function $reset() { token.value = ''; profile.value = null } // setup store 需自己实现 reset
  return { token, profile, isLogin, login, $reset }
})

// Options Store
export const useCounter = defineStore('counter', {
  state: () => ({ count: 0 }),
  getters: { double: (s) => s.count * 2 },
  actions: { inc() { this.count++ } }
})
```

```vue
<script setup>
import { storeToRefs } from 'pinia'
const user = useUserStore()
const { profile, isLogin } = storeToRefs(user) // ✅ state/getter 解构保持响应式
const { login } = user                         // action 直接解构即可

user.$patch({ token: 'x' })                    // 批量修改
user.$patch(s => { s.profile = null })
user.$subscribe((mutation, state) => localStorage.setItem('user', JSON.stringify(state)))
user.$onAction(({ name, after, onError }) => { after(() => console.log(name, 'done')) })
</script>
```

**Pinia vs Vuex**

| | Vuex 3/4 | Pinia |
|---|---|---|
| 修改方式 | 必须 commit mutation（同步），异步走 action | 直接改 / `$patch` / action |
| 模块 | 嵌套 modules + namespaced | 多个扁平 store，互相 import 使用 |
| TS | 支持差，需大量类型声明 | 自动推导 |
| 体积 | 较大 | 约 1KB 级 |
| Composition API | 一般 | 原生支持 Setup Store |

**面试答题要点**

1. Pinia 去掉 mutations，store 扁平化，TS 友好，是 Vue 官方推荐。
2. 解构 state/getter 要用 `storeToRefs`，否则丢响应式（store 本身是 reactive）。
3. Setup Store 中 `ref` → state、`computed` → getter、`function` → action；必须 return 所有 state 才能被 devtools/SSR 识别。
4. 插件机制可实现持久化、日志、重置等横切能力。
5. SSR 下每个请求创建独立 pinia 实例，防止跨请求状态污染。

**易错点 / 追问**

- 在组件外（路由守卫、axios 拦截器）使用 store，要确保 `app.use(pinia)` 之后再调用 `useXxxStore()`。
- Setup Store 没有内置 `$reset`。
- store 之间互相引用要在函数内部调用 `useOtherStore()`，避免循环依赖在模块顶层执行。

---

## 12. Vue Router 与导航守卫 ★★★

### 12.1 路由模式

| 模式 | API | 原理 | 注意 |
|---|---|---|---|
| Hash | `createWebHashHistory()` | URL `#` 后变化不发请求，监听 `hashchange`（实际也用 popstate） | 不利 SEO，无需服务端配置 |
| History | `createWebHistory()` | `history.pushState/replaceState` + 监听 `popstate` | 刷新会请求服务端，需配置回退到 `index.html` |
| Memory | `createMemoryHistory()` | 内存中维护历史栈 | SSR / 测试 |

```nginx
# History 模式 nginx 配置
location / {
  try_files $uri $uri/ /index.html;
}
```

### 12.2 导航守卫

| 类别 | 守卫 | 用途 |
|---|---|---|
| 全局 | `router.beforeEach` | 登录鉴权、权限校验 |
| 全局 | `router.beforeResolve` | 所有组件内守卫和异步组件解析后、确认导航前 |
| 全局 | `router.afterEach` | 埋点、修改 title、关闭进度条（不能改变导航） |
| 路由独享 | `beforeEnter` | 只在进入该路由时触发（params/query 变化不触发） |
| 组件内 | `beforeRouteEnter` | 进入前，**拿不到 this**，可通过 `next(vm => {})` 访问实例 |
| 组件内 | `beforeRouteUpdate` / `onBeforeRouteUpdate` | 同组件复用、参数变化（`/user/1 → /user/2`） |
| 组件内 | `beforeRouteLeave` / `onBeforeRouteLeave` | 离开前确认（表单未保存） |

**完整导航解析流程**

```
1. 导航被触发
2. 失活组件调用 beforeRouteLeave
3. 全局 beforeEach
4. 复用组件调用 beforeRouteUpdate
5. 路由配置 beforeEnter
6. 解析异步路由组件
7. 被激活组件调用 beforeRouteEnter
8. 全局 beforeResolve
9. 导航确认
10. 全局 afterEach
11. 触发 DOM 更新
12. beforeRouteEnter 中 next(vm => {}) 的回调执行
```

**代码示例**

```ts
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('./Login.vue') },          // 懒加载
    {
      path: '/admin',
      component: () => import('./Admin.vue'),
      meta: { requiresAuth: true, roles: ['admin'] },
      children: [{ path: 'users/:id(\\d+)', component: () => import('./User.vue'), props: true }]
    },
    { path: '/:pathMatch(.*)*', component: () => import('./NotFound.vue') } // 404，Vue Router 4 写法
  ],
  scrollBehavior: (to, from, saved) => saved ?? { top: 0 }
})

// Vue Router 4 推荐：返回值代替 next
router.beforeEach(async (to) => {
  const user = useUserStore()
  if (to.meta.requiresAuth && !user.isLogin) {
    return { path: '/login', query: { redirect: to.fullPath } } // 重定向
  }
  if (to.meta.roles && !to.meta.roles.includes(user.role)) return false // 取消导航
  // 不 return / return true → 放行
})

// 动态路由（权限菜单）
const removeRoute = router.addRoute('admin', { path: 'report', component: Report })
```

```vue
<script setup>
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
const route = useRoute()
const router = useRouter()
watch(() => route.params.id, (id) => load(id), { immediate: true }) // 参数变化重新请求
onBeforeRouteLeave(() => {
  if (dirty.value && !confirm('有未保存修改，确定离开？')) return false
})
</script>
```

**面试答题要点**

1. Hash 和 History 两种模式的原理与 History 需要服务端回退配置。
2. 守卫分全局、路由独享、组件内三类，能说出完整解析顺序。
3. Vue Router 4 推荐用返回值（`false` / 路由地址）控制导航，`next` 仍兼容但需保证只调用一次。
4. 权限方案：路由 meta + 全局 beforeEach 鉴权，或登录后根据权限 `addRoute` 动态注册。
5. 路由懒加载 `() => import()` 配合打包实现按页拆分。

**易错点 / 追问**

- 同一组件不同参数间跳转，组件被复用，`onMounted` 不再触发，需 `watch` 路由参数或 `onBeforeRouteUpdate`。
- 动态路由在刷新后丢失，需在 beforeEach 中判断并重新 `addRoute`，然后 `return to.fullPath` 重新导航。
- `$route` 是当前路由信息（响应式对象），`$router` 是路由实例（方法）。
- Vue Router 4 移除了 `*` 通配符，改为带正则的参数 `/:pathMatch(.*)*`。

---

## 13. Nuxt ★★

**是什么 / 原理**

Nuxt 是基于 Vue 的全栈元框架（对标 Next.js）：

- **约定式路由**：`pages/` 目录自动生成路由；`layouts/`、`components/`（自动导入）、`composables/`（自动导入）、`server/`（API 路由）；
- **服务端引擎 Nitro**：可部署到 Node、Serverless、Edge 等多种平台；
- **渲染模式**：SSR（默认，通用渲染）、CSR（`ssr: false`）、SSG（预渲染）、混合渲染（`routeRules` 按路由配置）；
- **Nuxt 4**（2025 年发布）：默认源码目录改为 `app/`，`useAsyncData/useFetch` 的数据共享与默认值行为有调整，类型拆分更清晰；Nuxt 3 进入维护期。具体细节以官方迁移指南为准。

**代码示例**

```vue
<!-- app/pages/posts/[id].vue -->
<script setup lang="ts">
const route = useRoute()
// useFetch：服务端请求并把数据序列化到 payload，客户端 hydration 时复用，不会二次请求
const { data: post, status, error, refresh } = await useFetch(`/api/posts/${route.params.id}`)
useSeoMeta({ title: () => post.value?.title })
</script>
```

```ts
// nuxt.config.ts —— 混合渲染
export default defineNuxtConfig({
  routeRules: {
    '/': { prerender: true },              // 构建时预渲染（SSG）
    '/blog/**': { isr: 3600 },             // 增量静态再生（平台支持时）
    '/products/**': { swr: 600 },          // stale-while-revalidate 缓存
    '/admin/**': { ssr: false },           // 纯客户端渲染
  }
})
```

**SSR 关键概念**

| 概念 | 说明 |
|---|---|
| 通用渲染 | 首屏服务端生成 HTML，客户端加载 JS 后 hydration 接管为 SPA |
| Hydration | 客户端复用服务端 DOM，绑定事件与响应式；服务端与客户端渲染结果不一致会报 hydration mismatch |
| payload | 服务端获取的数据序列化到页面，客户端直接复用 |
| `$fetch` vs `useFetch` | `$fetch` 是普通请求（在 setup 中直接用会服务端、客户端各请求一次）；`useFetch` 带去重和 payload 传递 |
| `<ClientOnly>` | 只在客户端渲染的组件（依赖 window 的库） |

**面试答题要点**

1. Nuxt 提供约定式路由、自动导入、SSR/SSG/混合渲染、服务端 API（Nitro）。
2. SSR 优势：首屏快、SEO 友好；代价：服务端压力、hydration 成本、需注意只在客户端可用的 API。
3. 数据获取用 `useFetch/useAsyncData`，避免服务端客户端重复请求。
4. `routeRules` 实现按路由选择渲染策略。
5. 跨请求状态污染：服务端不要用模块级单例保存用户状态，使用 `useState` 或 Pinia（每请求独立实例）。

**易错点 / 追问**

- 在 setup 顶层访问 `window/document` 会在服务端报错，放到 `onMounted` 或 `import.meta.client` 判断中。
- hydration mismatch 常见原因：渲染中使用随机数 / 时间、HTML 结构不合法（`<p>` 里套 `<div>`）、浏览器插件改 DOM。Vue 3.4+ 错误信息更详细，3.5 提供 `data-allow-mismatch` 属性压制预期内的不一致。
- Vue 3.5 的 `useId()` 用于生成 SSR 稳定的唯一 id。

---

## 14. Vapor Mode ★

**是什么 / 原理**

Vapor Mode 是 Vue 官方正在开发的**无虚拟 DOM 编译模式**（思路接近 Solid、Svelte）：

- 编译器把模板直接编译成"创建 DOM + 把响应式 effect 精确绑定到具体 DOM 操作"的代码，不再生成 VNode、不做 diff；
- 状态变化时由细粒度 effect 直接更新对应的 DOM 节点；
- 预期收益：更小的运行时体积、更低的内存占用、更快的更新；
- 设计为**组件级可选**：同一应用中 Vapor 组件与普通 VDOM 组件可以共存（例如 `<script setup vapor>` 的形式），只支持 Composition API 与 `<script setup>`。

**示意（概念对比，非真实产物）**

```js
// 传统 VDOM：每次更新重新执行 render 生成 VNode，再 diff
render() { return h('div', { class: cls.value }, text.value) }

// Vapor：只在创建时执行一次模板，effect 直接改 DOM
const el = template('<div></div>')()
renderEffect(() => setClass(el, cls.value))
renderEffect(() => setText(el, text.value))
```

**当前状态**

- Vue 3.6 的 alpha 阶段开始引入 Vapor Mode，同时响应式系统基于 alien-signals 做了重构（性能进一步提升）。
- 稳定性、发布时间、与第三方组件库 / SSR / Transition 等特性的兼容范围，**以官方进展为准**，生产使用前请查阅 Vue 官方博客与 release notes。

**面试答题要点**

1. Vapor Mode = 模板直接编译为细粒度 DOM 操作，去掉 VNode 与 diff。
2. 本质是 Vue 响应式系统本就是细粒度的，Vapor 让更新粒度从"组件"下沉到"DOM 节点"。
3. 渐进可选：可按组件启用，与现有 VDOM 组件共存。
4. 取舍：VDOM 仍有价值（render 函数灵活性、跨平台渲染），Vapor 主要面向性能敏感场景。

**易错点 / 追问**

- 不要把 Vapor 说成"Vue4"或"已全面替代 VDOM"——状态以官方为准。
- 追问"为什么 Vue 当初要用虚拟 DOM？"——声明式 + 跨平台抽象 + 组件级更新粒度减少 Watcher 数量（Vue2 正是从 1.x 的细粒度 Watcher 改为组件级 + VDOM，以降低内存开销）。

---

## 15. 高频题完整答案 ★★★

### 15.1 Vue3 比 Vue2 快在哪？

**可口述答案（按"响应式 → 编译 → 运行时 → 体积"组织）**

1. **响应式系统**：`Proxy` 替代 `defineProperty`，懒代理不再初始化全量递归；支持新增删除属性、数组下标、Map/Set；3.5 进一步重构依赖追踪，内存占用显著降低。
2. **编译优化**（最关键）：
   - 静态提升：静态节点只创建一次，diff 跳过；
   - PatchFlag：动态节点标记具体动态部分，靶向更新；
   - Block Tree：动态节点拍平到 `dynamicChildren`，diff 只遍历动态节点，复杂度与模板大小无关；
   - 事件缓存：内联事件不再导致无效更新；
   - SSR 静态内容直接输出字符串。
3. **Diff 算法**：快速 diff 先剥离相同前后缀，乱序部分用最长递增子序列求最少移动。
4. **体积**：全局 API 改为具名导出（`createApp`、`nextTick`），支持 tree-shaking，未用到的功能（Transition、KeepAlive 等）不打包。
5. **其他**：Fragment 减少无意义包裹元素；源码 TS 重写、模块化（`@vue/reactivity` 可独立使用）。

**追问应对**：如果手写 render 函数，编译优化就享受不到；"快"主要体现在更新阶段，首屏差异主要来自体积。

### 15.2 v-if 和 v-for 的优先级？

**结论**

| 版本 | 优先级 | 后果 |
|---|---|---|
| Vue2 | **v-for 高于 v-if** | 先遍历，每一项都执行 v-if 判断；即使只显示少数项，也要遍历全部，且每次重渲染都要遍历 |
| Vue3 | **v-if 高于 v-for** | v-if 先执行，此时 v-for 的迭代变量还不存在，`v-if="item.active"` 会报错（访问 undefined） |

**代码示例**

```html
<!-- ❌ 两个版本都不推荐 -->
<li v-for="user in users" v-if="user.active" :key="user.id">{{ user.name }}</li>

<!-- ✅ 场景 1：过滤列表 → 用 computed -->
<li v-for="user in activeUsers" :key="user.id">{{ user.name }}</li>
<!-- const activeUsers = computed(() => users.value.filter(u => u.active)) -->

<!-- ✅ 场景 2：整体条件显示 → v-if 放外层 template -->
<template v-if="showList">
  <li v-for="user in users" :key="user.id">{{ user.name }}</li>
</template>

<!-- ✅ 场景 3：逐项判断 → v-for 放 template，v-if 放内层 -->
<template v-for="user in users" :key="user.id">
  <li v-if="user.active">{{ user.name }}</li>
</template>
```

**可口述答案**：Vue2 中 v-for 优先，Vue3 中 v-if 优先。官方风格指南都禁止两者写在同一元素上：过滤用 computed，条件控制整体就把 v-if 提到外层 `<template>`。Vue3 改优先级是为了语义更清晰，避免"先遍历再过滤"的性能浪费被隐藏。

### 15.3 key 为什么不能用 index？

**原理**：key 是 diff 中判断"是不是同一个节点"的依据（`sameVnode`）。用 index 时，key 与数据项**没有稳定的对应关系**——在列表头部插入、删除、排序后，同一个 index 对应的已经是另一条数据。

**问题 1：性能浪费**

```
旧：[A(key=0), B(key=1), C(key=2)]
在头部插入 X 后：
新：[X(key=0), A(key=1), B(key=2), C(key=3)]

diff 认为 key 0/1/2 都是"同一节点"，于是：
  key0：A → X 内容 patch；key1：B → A patch；key2：C → B patch；key3：新建 C
本应只插入 1 个节点，变成了 3 次更新 + 1 次新建。
```

**问题 2：状态错乱（更严重）**

```vue
<!-- 每行有一个非受控 input 或子组件内部状态 -->
<div v-for="(item, index) in list" :key="index">
  {{ item.name }} <input />
</div>
```

在 input 中分别输入内容后删除第一项：key=0 的节点被复用来显示原第二项的数据，但 input 的 DOM（以及子组件内部 state）是"key=0 的那个"，于是**输入内容错位**——删除了第一行，看起来却是最后一行的输入框消失了。

**可口述答案**

1. key 是 vnode 的唯一标识，diff 靠它判断节点能否复用。
2. index 在增删、排序时会变，导致 key 与数据错位。
3. 后果一：本可移动复用的节点被逐个 patch 内容，性能下降。
4. 后果二：节点自身的状态（input 值、子组件内部 state、动画）跟着 index 留在原位置，出现错乱 bug。
5. 应使用数据唯一 id；只有列表纯静态展示、不会增删排序、无内部状态时，用 index 才无害。

**追问**：

- 不写 key 会怎样？Vue3 走 `patchUnkeyedChildren`，按位置就地复用，等同于 index 的效果。
- 用随机数 / `Math.random()` 做 key？每次渲染 key 都变，所有节点销毁重建，更糟。
- key 的另一个用途：在同一组件上改变 key 强制重新创建组件（如 `<router-view :key="route.fullPath">`）。

