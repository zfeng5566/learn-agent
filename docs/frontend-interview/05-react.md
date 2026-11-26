# 05 · React 生态（含 Next.js）知识点详解

> 对应总大纲 [第 7 节 框架：React](../frontend-interview-outline.md)。
> 每个知识点按 **是什么 / 原理 → 代码示例 → 面试答题要点 → 易错点 / 追问** 组织。
> 考频：★★★ 必考 / ★★ 常考 / ★ 加分项。版本基线：React 19.x、Next.js 15/16（截至 2026）。
> 涉及版本演进的地方（尤其 Next.js 缓存）变化很快，**具体 API 以官方文档为准**。

**侧重点**：心智模型（UI = f(state)）+ 渲染机制（Fiber / 调度 / diff）+ 新范式（并发、RSC、Compiler）。

---

## 目录

- [1. 组件模型、JSX 本质、单向数据流 ★★](#1-组件模型jsx-本质单向数据流-)
- [2. Hooks 规则与原理（链表）★★★](#2-hooks-规则与原理链表)
- [3. useEffect 依赖、清理与闭包陷阱 ★★★](#3-useeffect-依赖清理与闭包陷阱)
- [4. useMemo / useCallback / memo 何时有用、何时多余 ★★★](#4-usememo--usecallback--memo-何时有用何时多余)
- [5. 状态更新与批处理（React 18 自动批处理）★★★](#5-状态更新与批处理react-18-自动批处理)
- [6. 合成事件系统（委托到 root）★★](#6-合成事件系统委托到-root)
- [7. Fiber 架构：双缓冲、render / commit 阶段 ★★★](#7-fiber-架构双缓冲render--commit-阶段)
- [8. Lane 优先级与 Scheduler 调度、时间切片 ★★★](#8-lane-优先级与-scheduler-调度时间切片)
- [9. Diff 算法：三个策略与 key ★★★](#9-diff-算法三个策略与-key)
- [10. 并发特性：useTransition / useDeferredValue / Suspense ★★★](#10-并发特性usetransition--usedeferredvalue--suspense)
- [11. React 19 新 API ★★★](#11-react-19-新-api)
- [12. React Compiler：自动记忆化 ★★](#12-react-compiler自动记忆化)
- [13. 状态管理：Context / RTK / Zustand / Jotai / TanStack Query ★★★](#13-状态管理context--rtk--zustand--jotai--tanstack-query)
- [14. Server Components、Server Actions、流式 SSR ★★★](#14-server-componentsserver-actions流式-ssr)
- [15. Next.js App Router：渲染模式与缓存层级 ★★★](#15-nextjs-app-router渲染模式与缓存层级)
- [16. 手写简易 useState / 简易 Hooks 实现 ★★](#16-手写简易-usestate--简易-hooks-实现)
- [17. 高频题速答清单](#17-高频题速答清单)

---

## 1. 组件模型、JSX 本质、单向数据流 ★★

### 是什么 / 原理

- **组件模型**：组件是一个「输入 props/state → 输出 UI 描述」的函数，核心心智模型 `UI = f(state)`。组件只**描述**界面，真正操作 DOM 的是 React 渲染器（react-dom / react-native）。
- **JSX 本质**：JSX 是语法糖，编译后是创建 **React Element**（普通 JS 对象）的函数调用。
  - React 17 之前：`React.createElement(type, props, ...children)`，所以文件里必须 `import React`。
  - React 17+ **新 JSX 转换**：编译为 `import { jsx as _jsx } from 'react/jsx-runtime'`，不再需要手动引入 React。
  - React Element 结构大致为 `{ $$typeof: Symbol(react.element), type, key, ref, props }`。`$$typeof` 是 Symbol，JSON 无法伪造，可防止服务端返回的 JSON 被当成元素注入（XSS 防护）。React 19 中 `ref` 变成普通 prop，`element.ref` 被弃用。
- **单向数据流**：数据只能从父组件通过 props 流向子组件；子组件想改父状态只能调用父传下来的回调。好处是数据来源唯一、变化可追踪、易调试。
- **受控 vs 非受控**：受控组件值由 state 驱动（`value + onChange`）；非受控组件由 DOM 自己保存值，用 `ref` 读取（`defaultValue`）。

### 代码示例

```jsx
// 源码
const el = <Button type="primary" onClick={go}>提交</Button>;

// React 17+ 编译结果（简化）
import { jsx as _jsx } from 'react/jsx-runtime';
const el = _jsx(Button, { type: 'primary', onClick: go, children: '提交' });

// 单向数据流：子组件通过回调"请求"父组件修改
function Parent() {
  const [count, setCount] = useState(0);
  return <Child count={count} onInc={() => setCount(c => c + 1)} />;
}
function Child({ count, onInc }) {
  return <button onClick={onInc}>{count}</button>; // 不能直接改 props.count
}
```

### 面试答题要点

1. JSX 是 `jsx()/createElement()` 的语法糖，产物是描述 UI 的普通对象（React Element），不是 DOM。
2. 17 起新 JSX 转换由编译器自动引入 `react/jsx-runtime`，所以不必 `import React`。
3. `$$typeof` 用 Symbol 标记，防止 JSON 注入伪造元素。
4. 单向数据流 + 不可变数据，使状态变化可预测，配合 DevTools 可回溯。
5. 组件分为函数组件（主流）和类组件（遗留），Hooks 让函数组件拥有状态和副作用能力。

### 易错点 / 追问

- **props 是只读的**，直接修改不会触发更新，且违反纯函数约定。
- **组件必须是纯的**：同样的输入渲染出同样的输出，渲染期间不能有副作用（StrictMode 开发环境会双调用渲染函数来暴露问题）。
- 追问：「JSX 里为什么组件名必须大写？」→ 小写被当作原生标签字符串 `'div'`，大写被当作变量引用。
- 追问：「`{cond && <A/>}` 当 cond 为 0 时？」→ 会渲染出 `0`，应写 `cond > 0 && ...` 或三元。

---

## 2. Hooks 规则与原理（链表）★★★

### 是什么 / 原理

**两条规则**：① 只在函数组件或自定义 Hook 的**顶层**调用；② 不能在条件、循环、嵌套函数、提前 return 之后调用。

**存储结构**：每个函数组件对应一个 Fiber 节点，`fiber.memoizedState` 指向一个 **Hook 单向链表**，每调用一个 Hook 就是链表上一个节点：

```ts
type Hook = {
  memoizedState: any;   // 该 Hook 当前保存的值：useState 是 state，useEffect 是 effect 对象，useMemo 是 [value, deps]
  baseState: any;       // 计算更新的基准 state（用于跳过低优先级更新后重算）
  baseQueue: Update | null;
  queue: UpdateQueue | null; // useState/useReducer 的更新环形链表（pending 指向最后一个 update）
  next: Hook | null;    // 指向下一个 Hook
};
```

**mount 与 update 两套实现**：React 通过 `ReactCurrentDispatcher`（19 中为 `ReactSharedInternals.H`）在不同阶段注入不同的 Hooks 实现：

- **首次渲染（mount）**：`HooksDispatcherOnMount`，`useState` 实际是 `mountState`，每调用一次就 `mountWorkInProgressHook()` **新建**一个节点追加到链表尾部。
- **更新渲染（update）**：`HooksDispatcherOnUpdate`，`useState` 实际是 `updateState`，每调用一次就 `updateWorkInProgressHook()` 沿着 **current 树上的旧链表按顺序**取下一个节点，复制出新节点。

**为何不能条件调用**：Hook 没有名字/ID，React **只靠调用顺序**把本次调用和链表上第 N 个节点对应起来。如果某次渲染跳过了一个 Hook，后面的所有 Hook 都会错位（第 3 个 `useState` 读到了第 2 个节点的值），轻则状态串位，重则类型不匹配（把 effect 对象当 state）。React 在 DEV 下会检测 Hook 数量/类型变化并报 `Rendered fewer hooks than expected`。

**setState 做了什么**：`dispatchSetState(fiber, queue, action)` → 创建 update 对象（带 lane）→ 挂入 `queue.pending` 环形链表 → **eager state 优化**（若当前 fiber 无待处理更新，立即计算新值，`Object.is` 相等则直接 bail out 不调度）→ 否则 `scheduleUpdateOnFiber` 标记 lane 并向上冒泡 `childLanes` 到 root，交给调度器。

### 代码示例

```jsx
// ❌ 条件调用：第一次 show=true 时链表为 [name, age, effect]
// 第二次 show=false 时只调用了 [name, effect]，effect 读到了 age 的节点
function Profile({ show }) {
  const [name, setName] = useState('a');
  if (show) {
    const [age, setAge] = useState(18);
  }
  useEffect(() => { document.title = name; });
}

// ✅ 把条件放进 Hook 内部 / 渲染结果里
function Profile({ show }) {
  const [name, setName] = useState('a');
  const [age, setAge] = useState(18);
  useEffect(() => {
    if (show) document.title = `${name}-${age}`;
  }, [show, name, age]);
}
```

### 面试答题要点

1. Hooks 状态存在 Fiber 的 `memoizedState` 上，是一条按调用顺序串起来的单向链表。
2. mount 时新建节点，update 时按顺序复用 current 树上的旧节点——**顺序就是身份**。
3. 条件调用会导致前后两次渲染链表长度/顺序不一致，状态错位，所以必须顶层调用。
4. 不同阶段用不同 dispatcher 实现同名 Hook，在组件外调用 Hook 时 dispatcher 为空，所以报 "Invalid hook call"。
5. `use()` 是唯一例外：可以在条件和循环中调用（它不占用 Hook 链表的固定槽位语义，见 §11）。

### 易错点 / 追问

- 追问：「类组件为什么没有这个限制？」→ 类组件状态挂在实例 `this.state` 上，有名字（key）。
- 追问：「为什么不用 Map 按 key 存？」→ React 团队的取舍：顺序调用让自定义 Hook 可自由组合、不会命名冲突（两个自定义 Hook 内部都叫 `count` 也没问题），代价是这条规则。
- 易错：早期 return 之后的 Hook 也算条件调用：`if (loading) return null; useEffect(...)` ❌。
- ESLint `react-hooks/rules-of-hooks` 可静态检查。

---

## 3. useEffect 依赖、清理与闭包陷阱 ★★★

### 是什么 / 原理

- `useEffect(setup, deps?)`：在 **commit 之后、浏览器绘制之后异步**执行（passive effect），用于和外部系统同步（订阅、请求、DOM 第三方库）。
- **依赖比较**：每次渲染用 `Object.is` 逐项比较新旧 deps；有变化才重新执行。不传 deps 每次渲染后都执行；`[]` 只在挂载后执行一次。
- **清理函数**：setup 返回的函数，在**下一次 effect 执行前**和**组件卸载时**执行。执行顺序：先跑所有旧 effect 的 cleanup，再跑所有新 effect 的 setup。
- `useLayoutEffect`：在 commit 的 layout 阶段**同步**执行（DOM 已更新、浏览器未绘制），适合测量布局、避免闪烁；会阻塞绘制。
- `useInsertionEffect`：在 DOM 变更前执行，给 CSS-in-JS 库插入样式用。
- **StrictMode 双调用**：开发环境下组件挂载后会立即 `setup → cleanup → setup` 一次，用来暴露缺失清理的 bug。

**闭包陷阱本质**：每次渲染都是一次独立的函数调用，有自己独立的 props/state 快照。effect 或回调里引用的是**创建它那次渲染**的变量。如果 deps 没写全导致 effect 不重新创建，它就永远看到旧值。

### 代码示例：错误示例

```jsx
function Counter() {
  const [count, setCount] = useState(0);
  useEffect(() => {
    const id = setInterval(() => {
      console.log(count);   // 永远打印 0
      setCount(count + 1);  // 永远是 0 + 1，页面卡在 1
    }, 1000);
    return () => clearInterval(id);
  }, []); // ❌ 依赖缺失：effect 只在首渲染创建，闭包锁死 count=0
  return <div>{count}</div>;
}
```

### 三种修复方式

```jsx
// 修复 1：函数式更新 —— 不读取外部 count，由 React 传入最新值（首选）
useEffect(() => {
  const id = setInterval(() => setCount(c => c + 1), 1000);
  return () => clearInterval(id);
}, []);

// 修复 2：补全依赖 —— 每次 count 变化重建定时器（逻辑正确，但会频繁清理/重建）
useEffect(() => {
  const id = setInterval(() => setCount(count + 1), 1000);
  return () => clearInterval(id);
}, [count]);

// 修复 3：useRef 保存最新值 —— ref 是跨渲染的同一个可变容器，读 .current 总是最新
const countRef = useRef(count);
countRef.current = count; // 每次渲染同步最新值（严格说应在 effect 中赋值，见下）
useEffect(() => {
  const id = setInterval(() => {
    console.log(countRef.current); // 最新值
    setCount(countRef.current + 1);
  }, 1000);
  return () => clearInterval(id);
}, []);
```

补充方式（React 19.2 起稳定）：**`useEffectEvent`**——把「需要读最新值、但不应作为依赖」的逻辑抽成 Effect Event：

```jsx
import { useEffect, useEffectEvent } from 'react';

function ChatRoom({ roomId, theme }) {
  // onConnected 总能读到最新 theme，但它不是响应式依赖
  const onConnected = useEffectEvent(() => showToast('已连接', theme));
  useEffect(() => {
    const conn = connect(roomId);
    conn.on('connected', onConnected);
    return () => conn.disconnect();
  }, [roomId]); // theme 变化不会重连
}
```

**清理竞态（请求竞态）**：

```jsx
useEffect(() => {
  let ignore = false;
  const ctrl = new AbortController();
  fetch(`/api/user/${id}`, { signal: ctrl.signal })
    .then(r => r.json())
    .then(data => { if (!ignore) setUser(data); }); // 过期请求不写入
  return () => { ignore = true; ctrl.abort(); };
}, [id]);
```

### 面试答题要点

1. useEffect 在绘制后异步执行，useLayoutEffect 在绘制前同步执行；能用 useEffect 就别用 layout。
2. deps 用 `Object.is` 浅比较，对象/数组/函数每次渲染都是新引用，会导致 effect 每次都跑。
3. 闭包陷阱根因是「每次渲染是独立快照」+「依赖不全导致 effect 未重建」。
4. 修复：函数式更新 / 补全依赖 / useRef 存最新值；19.2+ 可用 `useEffectEvent`。
5. 清理函数用于取消订阅、清定时器、处理请求竞态；StrictMode 双调用就是为了检查清理是否完备。

### 易错点 / 追问

- **你可能不需要 Effect**：根据 props 派生数据直接在渲染中计算；响应用户事件的逻辑写在事件处理函数里；请求数据优先用框架/TanStack Query。
- `useEffect(async () => {})` ❌：effect 必须返回 cleanup 或 undefined，async 返回 Promise。应在内部定义 async 函数再调用。
- 不要为了「消除警告」删依赖或加 `eslint-disable`，这正是闭包陷阱的来源。
- 追问：「为什么 ref 赋值写在渲染期间不够严谨？」→ 并发渲染下渲染可能被丢弃，写 ref 属副作用；严谨写法放在 `useLayoutEffect` 中同步，或直接用 `useEffectEvent`。
- 追问：「父子 effect 执行顺序？」→ 子先父后（commit 时按深度优先完成顺序）；卸载 cleanup 也是父组件触发后子树依次执行。

---

## 4. useMemo / useCallback / memo 何时有用、何时多余 ★★★

### 是什么 / 原理

- `React.memo(Comp, areEqual?)`：高阶组件，props 浅比较（`Object.is` 逐个 key）相等则跳过该组件渲染。
- `useMemo(fn, deps)`：缓存**计算结果**，deps 不变返回上次结果。存储在 Hook 节点 `memoizedState = [value, deps]`。
- `useCallback(fn, deps)`：缓存**函数引用**，等价于 `useMemo(() => fn, deps)`。
- **默认行为**：父组件渲染时，所有子组件**默认都会重新渲染**（不论 props 是否变化）。memo 系列就是用来打断这种级联。

**何时有用**：

1. 计算确实昂贵（大列表过滤排序、复杂计算，可用 `console.time` 量化，>1ms 值得考虑）。
2. 值/函数作为 props 传给 **`memo` 包裹**的子组件——引用稳定才能让 memo 生效。
3. 值/函数作为其他 Hook 的**依赖**（useEffect 依赖一个对象，不稳定会每次触发）。

**何时多余**：

1. 子组件没有被 `memo` 包裹 → 传稳定的 callback 毫无意义（子组件照样渲染）。
2. 计算很便宜（拼字符串、简单 map）→ 记忆化本身的开销（deps 比较、闭包创建、内存）可能更大。
3. 依赖每次都变 → 缓存永远命中不了。
4. 组件把 `{...props}` 或 children 传下去，children 是 JSX 每次都是新对象，memo 失效。
5. 启用 **React Compiler** 后，编译器自动做细粒度记忆化，绝大多数手写 memo 可删除（见 §12）。

### 代码示例

```jsx
const List = memo(function List({ items, onSelect }) { /* 渲染很重 */ });

function Page({ data, keyword }) {
  // ✅ 有用：结果传给 memo 组件 + 计算较重
  const filtered = useMemo(
    () => data.filter(d => d.name.includes(keyword)).sort(byScore),
    [data, keyword]
  );
  // ✅ 有用：保证 memo(List) 的 props 稳定
  const onSelect = useCallback(id => console.log(id), []);

  // ❌ 多余：便宜计算
  const title = useMemo(() => `共 ${filtered.length} 条`, [filtered.length]);

  return <List items={filtered} onSelect={onSelect} />;
}
```

**比 memo 更好的优化：调整组件结构**

```jsx
// 状态下沉：把频繁变化的 state 放进小组件，避免整个页面重渲染
function Page() {
  return (<><SearchInput /><ExpensiveTree /></>);
}
// 内容上提（children 模式）：ColorPicker 的 state 变化不会让 children 重新渲染
function ColorPicker({ children }) {
  const [color, setColor] = useState('red');
  return <div style={{ color }}>{children}</div>;
}
```

### 面试答题要点

1. 父组件渲染默认会让整棵子树重渲染，memo/useMemo/useCallback 是打断级联的手段。
2. useCallback 只有配合 `memo` 子组件或作为 Hook 依赖时才有意义。
3. 记忆化有成本（比较 + 内存），便宜计算不要包。
4. 优先用「状态下沉 / children 上提」改结构，比到处加 memo 更有效。
5. React Compiler 普及后手写 memo 会大幅减少，但理解原理仍然重要（排查 Compiler 跳过的组件）。

### 易错点 / 追问

- `memo` 对 Context 无效：组件内 `useContext` 的值变了，即使 props 没变也会重渲染。
- 传内联对象 `style={{...}}` / 内联箭头函数给 memo 组件，会让 memo 失效。
- `useMemo` 不是语义保证，React 可能在将来丢弃缓存（如离屏组件），不要依赖它保证「只执行一次」的副作用。
- 追问：「`memo` 第二个参数和 `shouldComponentUpdate` 的区别？」→ `areEqual` 返回 true 表示**相等、跳过渲染**，与 SCU 返回值语义相反。

---

## 5. 状态更新与批处理（React 18 自动批处理）★★★

### 是什么 / 原理

- **批处理（batching）**：把多次 setState 合并成一次重新渲染。
- **React 17 及以前**：只在 React 合成事件处理函数里批处理（靠 `isBatchingUpdates` 标志）；在 `setTimeout`、Promise、原生事件里每次 setState 都**同步**触发一次渲染。
- **React 18 `createRoot` 起：自动批处理（Automatic Batching）**。所有更新（无论在事件、timeout、Promise、原生事件里）都先进入更新队列并标记 lane，同一 lane 的更新在同一个任务里统一调度处理（同步 lane 在微任务里 flush）。旧的 `ReactDOM.render` 仍保持旧行为。
- **退出批处理**：`flushSync(() => setX(1))` 强制同步刷新。
- **setState 是「异步」的吗？** 更准确地说：setState 不立即修改当前渲染的变量（快照），新值在下一次渲染才可见；是否同步刷新取决于 lane 与上下文。

### 代码示例

```jsx
function Demo() {
  const [a, setA] = useState(0);
  const [b, setB] = useState(0);

  const onClick = () => {
    setTimeout(() => {
      setA(x => x + 1);
      setB(x => x + 1);
      // React 17（ReactDOM.render）：渲染 2 次
      // React 18（createRoot）：渲染 1 次
    }, 0);
  };

  const onClick2 = () => {
    setA(a + 1);
    setA(a + 1);
    setA(a + 1); // 最终 a+1：三次都基于同一个快照 a
    setB(b => b + 1);
    setB(b => b + 1); // 最终 b+2：函数式更新按队列依次计算
  };

  const measure = () => {
    flushSync(() => setA(100)); // 立即渲染并提交 DOM
    // 这里 DOM 已更新，可以测量
  };
}
```

### 面试答题要点

1. 18 之前只有合成事件内批处理；18 用 createRoot 后所有场景自动批处理。
2. 原理：更新先入队并标记 lane，调度器在一个任务（同步 lane 走微任务）里统一处理同一批 lane。
3. setState 后读取变量仍是旧值，因为当前渲染是快照；需要基于旧值累加用函数式更新。
4. `flushSync` 可强制同步刷新，代价是丧失批处理和并发能力。
5. 相同值 setState（`Object.is` 相等）会被 bail out，可能不触发渲染。

### 易错点 / 追问

- 追问：「setState 后立刻拿到最新 DOM？」→ 用 `flushSync`，或在 `useLayoutEffect` 里处理。
- 易错：以为 `setA(a+1)` 连写三次等于 +3。
- 追问：「类组件 `this.setState` 第二个参数？」→ 更新提交后回调，等价于函数组件的 effect。

---

## 6. 合成事件系统（委托到 root）★★

### 是什么 / 原理

- **合成事件（SyntheticEvent）**：React 对原生事件的跨浏览器包装，接口与 W3C 一致（`stopPropagation`、`preventDefault`），可通过 `e.nativeEvent` 拿原生事件。
- **事件委托**：React 并不在每个 DOM 节点上绑定监听器，而是在**根节点**统一监听。
  - React 16：委托到 `document`。
  - **React 17+：委托到 root 容器**（`createRoot(container)` 的 container）。原因：多个 React 版本共存/微前端时互不干扰；`e.stopPropagation()` 与外部 document 监听的行为更符合直觉。
- **派发流程**：root 上为几乎所有事件同时注册捕获和冒泡监听 → 原生事件到达 root → 通过 `event.target` 找到对应 DOM 节点上挂的 Fiber（`internalInstanceKey`）→ 沿 Fiber 树 `return` 向上收集该事件的 `onXxx` / `onXxxCapture` 处理函数 → 构造合成事件 → 按捕获/冒泡顺序依次调用，模拟传播。
- **事件优先级**：不同事件映射到不同 lane（click/keydown → `DiscreteEventPriority` 同步 lane；scroll/mousemove → `ContinuousEventPriority`；其它 → `DefaultEventPriority`），这是并发调度的入口之一。
- **事件池**：React 16 会复用合成事件对象（异步访问 e 会被清空，需 `e.persist()`）；**17 起移除事件池**。

### 代码示例

```jsx
function App() {
  useEffect(() => {
    // 原生监听在 document 上
    document.addEventListener('click', () => console.log('document'));
  }, []);
  return (
    <div onClick={() => console.log('div 冒泡')} onClickCapture={() => console.log('div 捕获')}>
      <button onClick={e => { e.stopPropagation(); console.log('button'); }}>点击</button>
    </div>
  );
}
// React 17+ 输出：div 捕获 → button（不再输出 div 冒泡；document 也不会收到，因为 root 处阻止了原生冒泡）
// React 16 下 document 监听仍会触发（合成事件本身就在 document 上处理）
```

### 面试答题要点

1. React 用合成事件抹平浏览器差异，并通过事件委托减少监听器数量。
2. 17 起委托从 document 改为 root 容器，便于多版本共存和微前端。
3. 派发时根据 target 找到 Fiber，沿 Fiber 树收集 handler，模拟捕获/冒泡。
4. 不同事件有不同优先级，离散事件（click）走同步 lane。
5. 17 起移除事件池，异步中访问事件对象不再需要 `persist()`。

### 易错点 / 追问

- 合成事件的 `stopPropagation` 阻止的是 React 树内传播，并在 root 处阻止原生冒泡；但**无法阻止已注册在子元素上的原生监听**（它们先于 root 执行）。
- `onScroll` 在 React 17 起不再冒泡（与浏览器一致）。
- `onChange` 在 React 中实际是 `input` 事件语义（每次输入触发），与原生 change 不同。
- Portal 中的事件会按 **React 树**冒泡到父组件，而不是 DOM 树。

---

## 7. Fiber 架构：双缓冲、render / commit 阶段 ★★★

### 是什么 / 原理

**Fiber 解决了什么问题**：React 15 的 Stack Reconciler 递归遍历虚拟 DOM，一旦开始就**不可中断**，组件树大时一次更新占用主线程几十上百毫秒，导致掉帧、输入卡顿。Fiber 把渲染拆成**可中断、可恢复、可分优先级**的小单元。

**Fiber 是什么**（三层含义）：

1. **架构**：Fiber Reconciler，取代 Stack Reconciler。
2. **数据结构**：每个组件/DOM 节点对应一个 Fiber 对象，用 `child / sibling / return` 三个指针串成链表树，可用循环代替递归遍历，随时暂停并记住当前位置。
3. **工作单元**：每个 Fiber 是一个最小的工作单元，处理完一个就可以检查是否需要让出主线程。

```ts
type Fiber = {
  tag: WorkTag;              // FunctionComponent / HostComponent / ...
  type: any; key: string | null;
  stateNode: any;            // 对应的真实 DOM 或类实例
  return: Fiber | null; child: Fiber | null; sibling: Fiber | null;
  pendingProps: any; memoizedProps: any;
  memoizedState: any;        // 函数组件：Hook 链表
  updateQueue: any;
  flags: Flags;              // 副作用标记：Placement / Update / ChildDeletion ...
  subtreeFlags: Flags;       // 子树副作用汇总（18 起替代 effectList）
  lanes: Lanes; childLanes: Lanes; // 优先级
  alternate: Fiber | null;   // 双缓冲：指向另一棵树上的对应节点
};
```

**双缓冲（Double Buffering）**：内存中同时存在两棵 Fiber 树：

- **current 树**：当前屏幕上显示内容对应的树。
- **workInProgress 树**：正在内存中构建的新树。
- 两棵树对应节点通过 `alternate` 互相指向，构建 WIP 时尽量**复用** current 节点（`createWorkInProgress`），避免重复分配内存。
- commit 完成后，`root.current = finishedWork`，指针一换，WIP 变 current——类似图形学的双缓冲交换帧，避免中间状态被用户看到。

**两大阶段**：

| | Render 阶段（协调） | Commit 阶段（提交） |
|---|---|---|
| 做什么 | 调用组件函数、diff、打 flags，构建 WIP 树 | 根据 flags 操作真实 DOM、执行生命周期/effects |
| 可中断 | **可中断**（并发模式下），可能被丢弃重来 | **不可中断**，同步一次完成 |
| 副作用 | 必须纯（可能执行多次） | 在这里执行副作用 |
| 核心函数 | `workLoop` → `performUnitOfWork` → `beginWork`（向下）/ `completeWork`（向上） | `commitRoot` |

- **beginWork**：从上往下，根据新 props/state 计算子节点，执行 diff（reconcileChildren），返回第一个 child。
- **completeWork**：从下往上，HostComponent 创建/更新真实 DOM 实例（但不插入页面），收集 `subtreeFlags`。
- **Commit 三个子阶段**：
  1. **BeforeMutation**：DOM 变更前，如类组件 `getSnapshotBeforeUpdate`。
  2. **Mutation**：执行 DOM 插入/更新/删除；执行 `useLayoutEffect` 的 cleanup；之后切换 `root.current`。
  3. **Layout**：DOM 已更新，同步执行 `useLayoutEffect` setup、`componentDidMount/Update`，ref 赋值。
  4. 之后**异步调度** passive effects（`useEffect`）。

### 代码示例：Fiber 遍历（简化版 workLoop）

```js
let workInProgress = null;

function workLoopConcurrent() {
  // 每处理完一个 Fiber 就检查是否该让出主线程
  while (workInProgress !== null && !shouldYield()) {
    performUnitOfWork(workInProgress);
  }
}

function performUnitOfWork(fiber) {
  const next = beginWork(fiber);          // 向下：处理当前节点，返回 child
  fiber.memoizedProps = fiber.pendingProps;
  if (next) { workInProgress = next; return; }
  // 没有 child：向上 complete，直到找到 sibling
  let node = fiber;
  while (node) {
    completeWork(node);
    if (node.sibling) { workInProgress = node.sibling; return; }
    node = node.return;
  }
  workInProgress = null; // 整棵树完成，进入 commit
}
```

### 面试答题要点

1. Fiber 解决的是 Stack Reconciler 递归不可中断导致的长任务卡顿问题。
2. Fiber 用 child/sibling/return 链表实现可暂停的循环遍历，每个节点是一个工作单元。
3. 双缓冲：current 与 workInProgress 两棵树通过 alternate 互指，commit 后切换指针，复用节点。
4. render 阶段可中断、可重来、必须纯；commit 阶段同步不可中断，执行 DOM 操作和副作用。
5. commit 分 before mutation / mutation / layout，useLayoutEffect 同步在 layout，useEffect 之后异步执行。

### 易错点 / 追问

- 误区：「Fiber 让渲染变快了」→ 总工作量没变甚至略增，提升的是**响应性**（不阻塞高优任务）。
- 追问：「为什么废弃 componentWillMount / WillReceiveProps / WillUpdate？」→ 它们在 render 阶段，可中断重来会被多次调用，副作用不安全，故加 `UNSAFE_` 前缀。
- 追问：「React 18 前 Fiber 就有了，为什么 18 才说并发？」→ 16 引入 Fiber 架构，但默认仍是同步 lane（legacy mode）；18 的 createRoot + transition 才真正开启可中断渲染。

---

## 8. Lane 优先级与 Scheduler 调度、时间切片 ★★★

### 是什么 / 原理

**两套优先级体系**：

1. **Lane 模型（React 内部，reconciler 层）**：用 31 位二进制位表示优先级，位越低优先级越高。
   - 常见 lane：`SyncLane`（离散事件如 click、flushSync）> `InputContinuousLane`（scroll、mousemove）> `DefaultLane`（普通 setState、网络回调）> `TransitionLanes`（startTransition，有多条）> `RetryLanes`（Suspense 重试）> `IdleLane` > `OffscreenLane`。
   - **为什么用位运算**：一个 Fiber 可能同时有多个待处理更新，用位掩码 `lanes` 表示**集合**，合并（`a | b`）、判断包含（`(set & lane) !== 0`）、取最高优（`lanes & -lanes`）都是 O(1)。React 17 前用 `expirationTime` 数值表示，无法表达「一批」优先级，处理 Suspense / transition 交错时有缺陷。
   - **饥饿问题**：每个 lane 有过期时间，低优任务过期后会被提升为同步执行，避免一直被插队。
2. **Scheduler 优先级（独立包 `scheduler`）**：`ImmediatePriority` / `UserBlockingPriority` / `NormalPriority` / `LowPriority` / `IdlePriority`，对应不同 timeout（-1ms / 250ms / 5000ms / 10000ms / 永不过期）。React 通过 `lanesToEventPriority` 把 lane 转成 Scheduler 优先级。

**调度流程**：

```
setState → 创建 update（requestUpdateLane 决定 lane）
  → scheduleUpdateOnFiber：标记 fiber.lanes，向上合并 childLanes，root.pendingLanes |= lane
  → ensureRootIsScheduled：取 root 上最高优先级 lane
      ├─ SyncLane → 放入同步队列，微任务中 performSyncWorkOnRoot（不可中断）
      └─ 其他 → Scheduler.scheduleCallback(priority, performConcurrentWorkOnRoot)
  → Scheduler：任务进入最小堆 taskQueue（按 expirationTime 排序），用 MessageChannel 宏任务驱动 workLoop
  → 渲染中高优更新插入：中断当前低优渲染，丢弃 WIP，先处理高优，之后低优从头重来
```

**Scheduler 关键实现**：

- **taskQueue / timerQueue**：两个最小堆，taskQueue 存已就绪任务（按过期时间），timerQueue 存延迟任务（按开始时间）。
- **为什么用 MessageChannel**：需要一个宏任务让出主线程给浏览器渲染/处理输入；`setTimeout(0)` 嵌套后有 4ms 最小延迟；`requestIdleCallback` 兼容性差且触发频率不稳定（最低 20fps 左右）；`requestAnimationFrame` 与帧绑定、后台标签页不执行。Node 等环境降级为 `setImmediate` / `setTimeout`。
- **时间切片**：每个切片默认约 **5ms**（`frameYieldMs`），`shouldYield()` 判断 `now - startTime >= 5ms` 就让出；若任务回调返回一个函数（continuation），说明没做完，下次接着做。

### 代码示例：简化版 Scheduler

```js
const taskQueue = []; // 实际是最小堆，这里用数组 + sort 简化
let startTime = 0;
const FRAME_YIELD_MS = 5;

const channel = new MessageChannel();
channel.port1.onmessage = workLoop;

function scheduleCallback(priorityTimeout, callback) {
  taskQueue.push({ callback, expirationTime: performance.now() + priorityTimeout });
  taskQueue.sort((a, b) => a.expirationTime - b.expirationTime);
  channel.port2.postMessage(null); // 触发一个宏任务
}

function shouldYield() {
  return performance.now() - startTime >= FRAME_YIELD_MS;
}

function workLoop() {
  startTime = performance.now();
  let task = taskQueue[0];
  while (task) {
    // 没过期且时间片用完 → 让出
    if (task.expirationTime > performance.now() && shouldYield()) break;
    const continuation = task.callback();
    if (typeof continuation === 'function') task.callback = continuation; // 未完成，保留
    else taskQueue.shift();
    task = taskQueue[0];
  }
  if (taskQueue.length) channel.port2.postMessage(null); // 还有任务，下个宏任务继续
}
```

### 面试答题要点

1. 优先级分两层：Lane（reconciler，位掩码表示更新优先级集合）与 Scheduler 优先级（任务调度）。
2. Lane 用位运算可以高效表达「一批更新」，并通过过期时间解决低优饥饿。
3. Scheduler 用最小堆管理任务，用 MessageChannel 产生宏任务，每 5ms 让出主线程，即时间切片。
4. 高优更新到来会打断低优渲染，丢弃 WIP 后先处理高优，再重做低优——这就是并发渲染。
5. SyncLane 不走时间切片，在微任务中同步完成，所以 click 里的更新依然很快。

### 易错点 / 追问

- 时间切片只发生在 **render 阶段**；commit 阶段不可切片。
- 默认 `setState` 是 DefaultLane，也是**不可中断**的（`includesBlockingLane`），只有 transition / 离屏等低优 lane 才会走 `workLoopConcurrent` 被切片。
- 追问：「为什么不用 Web Worker？」→ 渲染需要访问组件闭包和 DOM，跨线程通信与序列化成本高。
- 追问：「为什么不用 generator？」→ React 团队认为 generator 有传染性（整条调用链都要改），且难以在中途切换到更高优先级任务后复用已有结果。

---

## 9. Diff 算法：三个策略与 key ★★★

### 是什么 / 原理

传统树 diff 最优算法复杂度 O(n³)。React 基于三个**启发式假设**降到 O(n)：

1. **Tree 策略：只做同层比较**。跨层级移动 DOM 极少，因此只比较同一层级节点，节点跨层移动会被视为「删除 + 新建」。
2. **Component 策略：类型不同直接替换**。`type` 不同（`div → span`、`A → B`）视为完全不同的树，销毁旧子树（state 丢失）并新建；类型相同则复用并更新 props。
3. **Element 策略：同层子节点用 key 标识**。开发者通过 `key` 告诉 React 哪些子元素在多次渲染中是「同一个」，从而实现移动复用而非重建。

**reconcileChildren 实现**：

- **单节点 diff**（新 children 是单个元素）：遍历旧 children，找 key 相同且 type 相同的复用，其余删除。
- **多节点 diff**（新 children 是数组），因为 Fiber 是单链表无法双端遍历，React 采用**两轮遍历**：
  1. **第一轮**：新旧按索引同时遍历，key 和 type 都相同就复用；key 不同立即跳出；key 同 type 不同标记删除旧的、新建。
  2. 若新数组遍历完 → 删除剩余旧节点；若旧链表遍历完 → 剩余新节点全部插入。
  3. **第二轮**：剩余旧节点放进 `Map<key|index, Fiber>`，遍历剩余新节点从 Map 中找可复用的。用 `lastPlacedIndex`（最后一个可复用节点在旧数组中的位置）判断是否移动：复用节点的旧 index `< lastPlacedIndex` 则标记移动（Placement），否则不动并更新 `lastPlacedIndex`。
  4. Map 中剩下的旧节点标记删除。

**key 的作用**：

- 让 React 在同层识别节点身份，实现**移动而非重建**，保留组件 state 和 DOM。
- **用 index 当 key 的问题**：列表在头部插入/删除/排序时，index 和数据错位，导致不必要的更新，甚至**状态串位**（输入框内容、checkbox 选中状态跟着位置走而不是跟着数据走）。
- **主动改 key 重置组件**：`<Form key={userId} />`，key 变化即销毁重建，是重置状态的惯用手法。

### 代码示例

```jsx
// key 用 index 的状态串位问题
function TodoList() {
  const [todos, setTodos] = useState([{ id: 1, text: 'A' }, { id: 2, text: 'B' }]);
  const addFirst = () => setTodos([{ id: Date.now(), text: 'New' }, ...todos]);
  return (
    <>
      <button onClick={addFirst}>头部插入</button>
      {todos.map((t, i) => (
        // ❌ key={i}：在 A 的输入框里打字后头部插入，输入内容会留在第一行（New 那行）
        // ✅ key={t.id}：输入内容跟着 A 走
        <div key={t.id}>{t.text} <input /></div>
      ))}
    </>
  );
}

// 移动判断示例：旧 [A0 B1 C2 D3] → 新 [D A B C]
// 遍历新：D 旧 index=3 ≥ lastPlacedIndex(0) → 不动，lastPlacedIndex=3
//         A 旧 index=0 < 3 → 移动；B 1<3 → 移动；C 2<3 → 移动
// 结果移动了 3 个节点（而非只移动 D），这是 React diff 的已知局限
```

### 面试答题要点

1. 三个策略：同层比较、类型不同直接替换、同层用 key 识别，把 O(n³) 降到 O(n)。
2. Fiber 子节点是单链表，所以多节点 diff 用两轮遍历 + Map，而非 Vue 2/3 的双端/最长递增子序列。
3. 用 `lastPlacedIndex` 判断移动，只右移不左移，把尾部节点移到头部是最差情况。
4. key 用于标识身份，index 当 key 在增删排序场景会导致性能下降和状态错乱。
5. 改变 key 可以强制重置组件状态。

### 易错点 / 追问

- key 只需在**兄弟节点间唯一**，不需要全局唯一。
- `key={Math.random()}` 每次都重建，性能最差且丢状态。
- 条件渲染中 `{a ? <Input /> : <Input />}` 同位置同类型会复用 state；想区分要加不同 key。
- 追问：「和 Vue diff 的区别？」→ Vue 3 用双端比较 + 最长递增子序列求最少移动；React 受限于单链表用单向遍历 + lastPlacedIndex，移动不一定最少。

---

## 10. 并发特性：useTransition / useDeferredValue / Suspense ★★★

### 是什么 / 原理

**并发渲染（Concurrent Rendering）**：React 可以同时准备多个版本的 UI，渲染可被中断、暂停、丢弃。不是多线程，而是基于 Fiber + Lane + Scheduler 的**可中断渲染**。

- **`useTransition`**：`const [isPending, startTransition] = useTransition()`，把 `startTransition` 回调内的更新标记为 **TransitionLane（低优先级、可中断）**。紧急更新（输入）先响应，非紧急更新（大列表筛选）后台渲染；期间旧 UI 保持可交互，`isPending` 为 true。还有独立的 `startTransition` 函数（无 isPending）。React 19 起回调可以是 **async 函数**（即 Action）。
- **`useDeferredValue(value, initialValue?)`**：返回一个「延迟版本」的值。紧急渲染时先返回旧值，随后以 transition 优先级用新值再渲染一次。适合**拿不到 setState 的场景**（值来自 props）。19 新增 `initialValue` 参数用于首屏。
- **Suspense**：组件「挂起」（抛出 Promise / 使用 `use(promise)` / `lazy`）时显示最近的 `fallback`，数据就绪后重试渲染。
  - 与 transition 配合：在 transition 中触发挂起，**已显示的内容不会被替换成 fallback**，而是保持旧 UI + isPending，避免闪烁。
  - SSR 中配合流式渲染与选择性注水（见 §14）。

### 代码示例

```jsx
// useTransition：输入框紧急，列表非紧急
function Search() {
  const [text, setText] = useState('');
  const [query, setQuery] = useState('');
  const [isPending, startTransition] = useTransition();
  const onChange = e => {
    setText(e.target.value);                         // 紧急：输入立即响应
    startTransition(() => setQuery(e.target.value)); // 非紧急：可被下一次输入打断
  };
  return (
    <>
      <input value={text} onChange={onChange} />
      {isPending && <Spinner />}
      <HeavyList query={query} />
    </>
  );
}

// useDeferredValue：值来自 props 时使用
function Results({ query }) {
  const deferredQuery = useDeferredValue(query);
  const isStale = query !== deferredQuery;
  return (
    <div style={{ opacity: isStale ? 0.5 : 1 }}>
      <HeavyList query={deferredQuery} /> {/* HeavyList 需 memo 才能在紧急渲染中跳过 */}
    </div>
  );
}

// Suspense + lazy
const Chart = lazy(() => import('./Chart'));
<Suspense fallback={<Skeleton />}><Chart /></Suspense>;
```

### 面试答题要点

1. 并发 = 可中断渲染 + 优先级，不是多线程。
2. useTransition 把更新标为低优 TransitionLane，适合自己能控制 setState 的场景；useDeferredValue 适合只拿到值的场景。
3. 两者都不是防抖：没有固定延迟，设备快时几乎立即完成，且会被新的输入打断丢弃。
4. Suspense 声明式处理加载态；在 transition 中挂起会保留旧 UI 而不是回退到 fallback。
5. React 19 中 startTransition 支持 async 回调，即 Action 的基础。

### 易错点 / 追问

- transition 中**不能控制受控输入框的值**（`<input value>` 的 setState 必须是同步的，否则输入会卡）。
- `useDeferredValue` 想生效，渲染重的子组件必须 `memo`，否则紧急渲染依然会渲染它。
- 19 之前：async 函数中 `await` 之后的 setState 不在 transition 内，需要再包一层 `startTransition`（19 中仍有此限制，以官方文档为准）。
- 追问：「Suspense 怎么知道组件在加载？」→ 组件 throw 一个 Promise（或 `use` 内部同理），React 捕获后渲染 fallback，并在 Promise resolve 后以 RetryLane 重试。

---

## 11. React 19 新 API ★★★

### 是什么 / 原理

React 19（2024-12 稳定）的主线是 **Actions**：把「异步提交 + pending 状态 + 错误处理 + 乐观更新 + 表单」这套样板代码收敛到框架里。

| API | 作用 |
|---|---|
| Actions | `startTransition` 支持 async 函数，自动管理 pending、错误、乐观更新回滚 |
| `<form action={fn}>` | 表单 action 可以是函数，提交成功后自动重置非受控表单 |
| `useActionState` | 管理 Action 的返回状态 + pending（取代 Canary 时的 `useFormState`） |
| `useFormStatus` | （react-dom）子组件读取最近父 `<form>` 的提交状态 |
| `useOptimistic` | 乐观更新，Action 结束后自动回到真实状态 |
| `use()` | 渲染中读取 Promise 或 Context，**可条件调用** |
| ref 作为 prop | 函数组件直接接收 `ref`，`forwardRef` 将逐步废弃；ref 回调可返回清理函数 |
| 其它 | `<Context>` 直接作 Provider；文档元数据 `<title>/<meta>/<link>` 自动提升到 head；`preload/preinit` 资源预加载；更好的 hydration 错误信息 |

19.2（2025-10）新增：`<Activity mode="visible|hidden">`（隐藏但保留状态，取代手写显隐）、`useEffectEvent`、`cacheSignal`（RSC）等，**细节以官方文档为准**。

### 代码示例

**Actions + useTransition（async）**

```jsx
function UpdateName() {
  const [name, setName] = useState('');
  const [error, setError] = useState(null);
  const [isPending, startTransition] = useTransition();
  const submit = () => {
    startTransition(async () => {
      const err = await updateName(name); // pending 期间 isPending=true
      if (err) { setError(err); return; }
      redirect('/profile');
    });
  };
  return <button onClick={submit} disabled={isPending}>保存</button>;
}
```

**useActionState + form action**

```jsx
// action 签名：(prevState, formData) => newState
async function addToCart(prevState, formData) {
  const res = await api.add(formData.get('itemId'));
  return res.ok ? { msg: '已加入' } : { msg: '失败：' + res.error };
}

function AddButton({ itemId }) {
  const [state, formAction, isPending] = useActionState(addToCart, { msg: '' });
  return (
    <form action={formAction}>
      <input type="hidden" name="itemId" value={itemId} />
      <button disabled={isPending}>加入购物车</button>
      <p>{state.msg}</p>
    </form>
  );
}
```

**useFormStatus**

```jsx
import { useFormStatus } from 'react-dom';
function SubmitButton() {
  const { pending, data, method, action } = useFormStatus(); // 读的是父级 <form>
  return <button disabled={pending}>{pending ? '提交中…' : '提交'}</button>;
}
// 必须渲染在 <form> 内部的子组件中，和 form 写在同一组件里拿不到
```

**useOptimistic**

```jsx
function Thread({ messages, send }) {
  const [optimistic, addOptimistic] = useOptimistic(
    messages,
    (state, newMsg) => [...state, { text: newMsg, sending: true }] // 合并函数
  );
  async function action(formData) {
    const text = formData.get('text');
    addOptimistic(text);   // 立即显示
    await send(text);      // 完成后父组件 messages 更新，乐观值被真实值替换；失败则自动回滚
  }
  return (
    <form action={action}>
      {optimistic.map((m, i) => <p key={i}>{m.text}{m.sending && '（发送中）'}</p>)}
      <input name="text" />
    </form>
  );
}
```

**use()**

```jsx
import { use, Suspense } from 'react';

function Comments({ commentsPromise }) {
  const comments = use(commentsPromise); // 挂起直到 resolve，reject 交给 ErrorBoundary
  return comments.map(c => <p key={c.id}>{c.text}</p>);
}
function Heading({ show }) {
  if (!show) return null;
  const theme = use(ThemeContext); // ✅ 可以在条件之后调用
  return <h1 className={theme}>Hi</h1>;
}
// Promise 应来自 Server Component 或缓存层，不要在客户端组件渲染中新建（每次渲染都是新 Promise）
<Suspense fallback="加载中"><Comments commentsPromise={fetchComments()} /></Suspense>;
```

**ref 作为 prop + ref 清理函数 + Context 作 Provider + 元数据**

```jsx
function MyInput({ placeholder, ref }) {           // 19：不再需要 forwardRef
  return <input placeholder={placeholder} ref={ref} />;
}

<div ref={node => {
  const ob = new ResizeObserver(() => {}); ob.observe(node);
  return () => ob.disconnect();                    // 19：ref 回调可返回清理函数
}} />;

<ThemeContext value="dark"><App /></ThemeContext>;  // 19：替代 ThemeContext.Provider

function BlogPost({ post }) {
  return (<article>
    <title>{post.title}</title>                    {/* 自动提升到 <head> */}
    <meta name="author" content={post.author} />
  </article>);
}
```

### 面试答题要点

1. React 19 主线是 Actions：async transition 自动管理 pending / 错误 / 乐观更新。
2. `useActionState` 返回 `[state, formAction, isPending]`，action 签名 `(prev, formData)`。
3. `useFormStatus` 读父表单状态，免去 prop 层层传递 pending；`useOptimistic` 做乐观 UI，Action 结束自动收敛到真实值。
4. `use()` 能读 Promise/Context 且可条件调用，配合 Suspense 和 ErrorBoundary。
5. ref 成为普通 prop、ref 回调支持清理、`<Context>` 直接作 Provider、元数据原生支持。

### 易错点 / 追问

- 追问：「`use` 为什么能条件调用？」→ 它不依赖 Hook 链表槽位保存状态：读 Context 是沿 Fiber 向上查找，读 Promise 是检查 Promise 上的状态（React 会给 thenable 打 `status/value` 标记），未完成就抛出挂起。
- `use` 不能在 try/catch 中使用（挂起依赖抛出机制），错误交给 ErrorBoundary。
- 升级 19 的破坏性变更：移除 `propTypes`/函数组件 `defaultProps`、字符串 ref、`ReactDOM.render/hydrate`（改 `createRoot/hydrateRoot`）、legacy Context 等。

---

## 12. React Compiler：自动记忆化 ★★

### 是什么 / 原理

- **是什么**：React 团队的构建期编译器（Babel 插件 `babel-plugin-react-compiler`，2025-10 发布 1.0 稳定版），在编译阶段分析组件和 Hook，**自动插入细粒度记忆化**，效果相当于把 `useMemo / useCallback / memo` 自动写到每个合适的位置。
- **原理**：把组件编译成基于 HIR（高层中间表示）的数据流图，分析每个值依赖哪些响应式输入（props/state/context），按「响应式作用域」分组，生成带缓存槽的代码（运行时用 `react/compiler-runtime` 的 `_c(n)` 分配缓存数组，依赖不变就复用上次的 JSX/值）。粒度比手写更细，甚至能缓存 JSX 片段、支持条件分支后的记忆化（手写 useMemo 做不到）。
- **前提**：代码必须遵守 **Rules of React**（组件纯、props/state 不可变、Hook 规则）。编译器检测到违反规则的组件会**跳过优化**（不报错，保持原行为），可通过 ESLint（`eslint-plugin-react-hooks` 新版已内置编译器相关规则）发现。
- **兼容**：支持 React 17/18（需 `react-compiler-runtime` 包）与 19；Next.js、Vite、Expo 等已有集成配置。可用 `'use no memo'` 指令让单个组件/文件退出编译。

### 代码示例

```jsx
// 源码：无任何手写 memo
function TodoList({ todos, tab }) {
  const visible = filterTodos(todos, tab);
  const onClick = id => toggle(id);
  return <List items={visible} onClick={onClick} />;
}

// 编译后（示意，非真实产物）
import { c as _c } from 'react/compiler-runtime';
function TodoList({ todos, tab }) {
  const $ = _c(5);
  let visible;
  if ($[0] !== todos || $[1] !== tab) { visible = filterTodos(todos, tab); $[0] = todos; $[1] = tab; $[2] = visible; }
  else visible = $[2];
  let jsx;
  if ($[3] !== visible) { jsx = <List items={visible} onClick={id => toggle(id)} />; $[3] = visible; $[4] = jsx; }
  else jsx = $[4];
  return jsx;
}
```

### 面试答题要点

1. Compiler 在构建期自动记忆化，解决手写 memo 心智负担重、容易漏写/错写依赖的问题。
2. 粒度比手写更细，可缓存 JSX 片段和条件分支后的值，子组件无需 `memo` 也能跳过渲染（因为传入的 JSX 元素引用不变）。
3. 依赖代码遵守 Rules of React；违反规则的组件被跳过而不是报错。
4. 对手写 useMemo 的影响：新代码基本不必再写；已有手写的可以保留（编译器会兼容），但不要为了「配合编译器」而新增。
5. 仍需手动控制的场景：effect 依赖需要稳定引用时的精确语义、与第三方库的引用相等约定、`'use no memo'` 排查问题。

### 易错点 / 追问

- 误区：「有了 Compiler 就不会重渲染」→ 它减少的是**不必要的**重渲染和重计算；state 真的变了照样渲染，Context 变化仍会触发消费者渲染。
- 编译器不优化类组件。
- 渲染期间修改外部变量、直接 mutate props/state 的代码会被跳过优化，或在开启后暴露隐藏 bug。
- 追问：「如何渐进接入？」→ 先跑 ESLint 规则修复违规；用 `compilationMode: 'annotation'` 只编译带 `'use memo'` 的组件，或按目录启用。

---

## 13. 状态管理：Context / RTK / Zustand / Jotai / TanStack Query ★★★

### 是什么 / 原理

**先分类状态**：

- **UI / 客户端状态**：弹窗开关、表单草稿、主题——本地 state 或客户端状态库。
- **服务端状态**：来自接口的数据，有缓存、过期、重新验证、并发去重、分页等问题——**交给 TanStack Query / SWR / RSC**，不要放进 Redux。
- **URL 状态**：筛选、分页、tab——放 URL search params。

**Context 的性能问题**：

- Provider 的 `value` 变化（`Object.is` 比较）时，**所有**消费该 Context 的组件都会重渲染，且无法只订阅其中一个字段；`memo` 拦不住。
- `value={{ user, setUser }}` 内联对象每次 Provider 渲染都是新引用，导致全部消费者渲染。
- 缓解：`useMemo` 包 value；**拆分 Context**（state 与 dispatch 分开、按变化频率拆）；高频状态改用支持 selector 的外部 store。
- Context 本质是**依赖注入**工具，不是状态管理器，适合低频全局值（主题、语言、当前用户）。

**外部 store 原理**：Zustand/Redux 等把状态放在 React 外部，组件通过 `useSyncExternalStore(subscribe, getSnapshot)` 订阅，配合 **selector + 相等比较**，只有选中的切片变化才重渲染；`useSyncExternalStore` 还保证并发渲染下不出现「撕裂」（tearing，同一次渲染不同组件读到不同版本的数据）。

### 对比表

| 方案 | 定位 | 心智模型 | 订阅粒度 | 样板代码 | DevTools / 中间件 | 适合场景 |
|---|---|---|---|---|---|---|
| Context + useReducer | 内置依赖注入 | Provider 树 | 整个 value | 少 | 无 | 低频全局值：主题、语言、权限 |
| Redux Toolkit | 集中式 store | 单一 store + action/reducer（Immer） | selector | 中（RTK 已大幅减少） | 最强（时间旅行、中间件生态、RTK Query） | 大型团队、复杂业务流、强规范和可追溯 |
| Zustand | 轻量外部 store | hook 化的 store，直接 set | selector | 极少 | 有 devtools / persist 中间件 | 中小项目通用客户端状态，替代大部分 Redux 场景 |
| Jotai | 原子化 | atom 自底向上组合，派生 atom | 单个 atom | 少 | 有 | 状态碎片多、依赖关系复杂（编辑器、表单、画布） |
| TanStack Query | **服务端状态**缓存 | queryKey → 缓存 + 自动重新验证 | queryKey | 少 | 有 Query DevTools | 所有接口数据：缓存、去重、重试、分页、乐观更新 |

### 代码示例

```jsx
// Context 拆分：state 与 dispatch 分开，只用 dispatch 的组件不随 state 变化渲染
const StateCtx = createContext(null);
const DispatchCtx = createContext(null);
function Provider({ children }) {
  const [state, dispatch] = useReducer(reducer, init);
  return (
    <DispatchCtx value={dispatch}>
      <StateCtx value={state}>{children}</StateCtx>
    </DispatchCtx>
  );
}

// Zustand：selector 订阅，只有 count 变化才渲染
import { create } from 'zustand';
const useStore = create(set => ({
  count: 0, user: null,
  inc: () => set(s => ({ count: s.count + 1 })),
}));
function Counter() {
  const count = useStore(s => s.count);
  const inc = useStore(s => s.inc);
  return <button onClick={inc}>{count}</button>;
}

// Redux Toolkit
const counterSlice = createSlice({
  name: 'counter', initialState: { value: 0 },
  reducers: { inc: state => { state.value += 1; } }, // Immer：看起来可变，实际生成新对象
});

// Jotai：派生 atom
const priceAtom = atom(10);
const qtyAtom = atom(2);
const totalAtom = atom(get => get(priceAtom) * get(qtyAtom)); // 依赖变化自动更新

// TanStack Query：服务端状态
function Todos() {
  const qc = useQueryClient();
  const { data, isPending, error } = useQuery({
    queryKey: ['todos'], queryFn: fetchTodos, staleTime: 60_000,
  });
  const mutation = useMutation({
    mutationFn: addTodo,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['todos'] }), // 失效后自动重新请求
  });
}
```

### 选型建议

1. **先分类再选型**：服务端状态 → TanStack Query（Next.js App Router 下优先 RSC 取数 + 服务端缓存）；URL 状态 → search params；剩下的才是客户端状态。
2. 客户端状态少 → `useState` + 状态提升 + 少量 Context 就够。
3. 中小项目需要全局客户端状态 → **Zustand**（API 小、无 Provider、selector 性能好）。
4. 状态碎片化、派生关系复杂 → **Jotai**。
5. 大型团队、需要严格规范/中间件/时间旅行调试，或已有 Redux 存量 → **Redux Toolkit**（服务端数据可用 RTK Query）。

### 面试答题要点

1. 区分服务端状态和客户端状态是现代 React 状态管理的核心观点。
2. Context 变化会让所有消费者重渲染且不支持 selector，适合低频值；可通过拆分 Context、memo value 缓解。
3. 外部 store 基于 `useSyncExternalStore` + selector 实现精准订阅，并避免并发撕裂。
4. Zustand 轻量、Jotai 原子化自底向上、RTK 规范与生态最强。
5. TanStack Query 解决缓存、去重、过期重新验证、重试、分页，减少手写 loading/error 样板。

### 易错点 / 追问

- Zustand selector 返回新对象（`s => ({ a: s.a, b: s.b })`）会每次都触发渲染，需 `useShallow`。
- 把接口数据塞进 Redux 并手写 loading/error/缓存，是常见的过度设计。
- 追问：「什么是撕裂？」→ 并发渲染中途让出，外部 store 被修改，导致同一次渲染前后组件读到不同值；`useSyncExternalStore` 检测到快照变化会强制同步重渲染。

---

## 14. Server Components、Server Actions、流式 SSR ★★★

### 是什么 / 原理

**传统 SSR**：服务端把组件渲染成 HTML 字符串返回 → 浏览器先显示 HTML → 下载**全部**组件 JS → **hydration（注水）**绑定事件。问题：所有组件代码都要发到客户端；必须等全部数据就绪才能输出；必须等全部 JS 加载完才能交互。

**流式 SSR（React 18+）**：`renderToPipeableStream`（Node）/ `renderToReadableStream`（Web Stream）。配合 Suspense：

- 先输出 Suspense 边界外的 HTML 外壳（shell）和 fallback，数据就绪后把剩余 HTML 片段 + 一段内联 `<script>` 流式追加，替换 fallback——**不必等最慢的数据**。
- **选择性注水（Selective Hydration）**：各 Suspense 边界独立注水；用户点击了尚未注水的区域，React 会**优先注水该区域**。

**React Server Components（RSC）**：一种新的**组件类型**，只在服务端（或构建时）运行，**代码不会发送到客户端**。

- 可以 `async/await` 直接访问数据库、文件系统、密钥；可以使用大型依赖（markdown 解析等）而不增加 bundle。
- 不能用 state、effect、事件处理、浏览器 API。
- 输出不是 HTML，而是 **RSC Payload**（React 定义的流式序列化格式，描述组件树；Client Component 位置只是一个「引用」+ 序列化后的 props）。
- **`'use client'`** 标记客户端边界：该文件及其导入的模块进入客户端 bundle。Client Component 也会在服务端参与 SSR 生成 HTML，「client」指的是**会在客户端注水运行**。
- Server Component 可以把 Server Component 作为 `children` 传给 Client Component；但 Client Component 不能直接 import Server Component。
- props 跨边界必须可序列化（函数不行，Server Action 除外；Promise 可以，配合 `use`）。

**Server Actions / Server Functions**：`'use server'` 标记的异步函数，运行在服务端，客户端可以像调函数一样调用（底层是框架生成的 POST 请求）。可作为 `<form action>`，支持渐进增强（JS 未加载时表单也能提交）。

### RSC vs SSR 对比表

| 维度 | SSR（传统服务端渲染） | RSC（服务端组件） |
|---|---|---|
| 本质 | 一种**渲染时机/策略**：在服务端把组件树渲染成 HTML | 一种**组件类型**：只在服务端运行的组件 |
| 输出 | HTML 字符串/流 | RSC Payload（序列化的组件树），再由 SSR 转成 HTML 或客户端直接消费 |
| 客户端 JS | 所有组件代码都要下载并 hydrate | Server Component 代码**零 bundle**，只 hydrate Client Component |
| 运行时机 | 首次请求时运行一次，之后客户端接管 | 首次请求和**后续导航**都可以在服务端重新运行，刷新时客户端 state 保留 |
| 数据获取 | getServerSideProps 等框架 API，页面级 | 组件内直接 `await`，组件级就近取数 |
| 交互能力 | 注水后完整交互 | 无交互，交互放到 Client Component |
| 解决的问题 | 首屏速度、SEO | bundle 体积、数据获取瀑布、前后端边界 |
| 关系 | 二者**互补**：Next.js App Router 中 RSC 先产出 Payload，SSR 再用 Payload 渲染首屏 HTML | |

### 代码示例

```tsx
// app/posts/page.tsx —— Server Component（默认）
import { db } from '@/lib/db';
import LikeButton from './LikeButton';
import { Suspense } from 'react';

export default async function Posts() {
  const posts = await db.post.findMany(); // 直接访问数据库，代码不进客户端
  return posts.map(p => (
    <article key={p.id}>
      <h2>{p.title}</h2>
      <LikeButton postId={p.id} initial={p.likes} />  {/* 客户端边界 */}
      <Suspense fallback={<p>评论加载中…</p>}>
        <Comments postId={p.id} />                    {/* 流式输出 */}
      </Suspense>
    </article>
  ));
}

// app/posts/actions.ts —— Server Action
'use server';
import { revalidatePath } from 'next/cache';
export async function like(postId: string) {
  await db.post.update({ where: { id: postId }, data: { likes: { increment: 1 } } });
  revalidatePath('/posts');
}

// app/posts/LikeButton.tsx —— Client Component
'use client';
import { useOptimistic, startTransition } from 'react';
import { like } from './actions';
export default function LikeButton({ postId, initial }: { postId: string; initial: number }) {
  const [count, addOptimistic] = useOptimistic(initial, (c, n: number) => c + n);
  return (
    <button onClick={() => startTransition(async () => { addOptimistic(1); await like(postId); })}>
      赞 {count}
    </button>
  );
}
```

### 面试答题要点

1. SSR 是渲染策略（产出 HTML），RSC 是组件类型（产出 RSC Payload），二者互补而非替代。
2. RSC 代码不进 bundle，可直接访问后端资源；交互逻辑放在 `'use client'` 组件中。
3. 流式 SSR + Suspense 让页面分块输出，选择性注水按用户交互优先注水。
4. Server Actions 让客户端像调函数一样调用服务端逻辑，支持表单渐进增强。
5. 跨边界 props 必须可序列化；Client 不能 import Server，但可以通过 children 组合。

### 易错点 / 追问

- **安全**：Server Action 本质是公开的 HTTP 端点，必须在函数内做**鉴权和入参校验**，不能假设只有自己的 UI 会调用。
- `'use client'` 不是「只在客户端渲染」，它仍会 SSR；`'use server'` 标记的是 Server Action，不是 Server Component（Server Component 不需要任何指令）。
- 敏感模块可用 `import 'server-only'` 防止被误引入客户端。
- 追问：「RSC 的 hydration 怎么做？」→ 只对 Client Component 注水，Server Component 部分是静态的，不需要注水。

---

## 15. Next.js App Router：渲染模式与缓存层级 ★★★

> **注意**：Next.js 缓存语义在 14 → 15 → 16 之间变化很大，下文标注版本，**具体 API 和默认值以官方文档为准**。

### 是什么 / 原理

**App Router 基础（13.4+ 稳定）**：基于 `app/` 目录的文件系统路由，默认组件为 Server Component。约定文件：`page.tsx`（页面）、`layout.tsx`（嵌套布局，导航时保持状态不重渲染）、`loading.tsx`（自动包 Suspense）、`error.tsx`（自动包 ErrorBoundary，必须是 Client Component）、`not-found.tsx`、`route.ts`（Route Handler，API 接口）。支持路由组 `(group)`、动态段 `[id]`、并行路由 `@slot`、拦截路由 `(.)`。

**渲染模式**：

| 模式 | 含义 | App Router 中如何触发 |
|---|---|---|
| SSG（静态生成） | 构建时渲染成 HTML，CDN 分发 | 默认：没有使用动态 API 且数据可缓存的路由会被静态化；动态段用 `generateStaticParams` 预生成 |
| SSR（动态渲染） | 每次请求时在服务端渲染 | 使用 `cookies()`、`headers()`、`searchParams` 等请求时 API，或未缓存的数据请求，或 `export const dynamic = 'force-dynamic'` |
| ISR（增量静态再生） | 静态页面在后台按时间或按需重新生成 | 时间：`export const revalidate = 60` 或 `fetch(url, { next: { revalidate: 60 } })`；按需：`revalidatePath()` / `revalidateTag()` |
| PPR（部分预渲染） | 同一路由中静态外壳预渲染 + 动态部分在 Suspense 中流式填充 | 14/15 为实验特性（`experimental.ppr`）；16 起并入 **Cache Components**（`cacheComponents: true`），以官方文档为准 |
| CSR | 客户端渲染 | Client Component 内用 effect/TanStack Query 取数 |

**PPR 原理**：构建时渲染出路由的静态部分（含 Suspense fallback）作为 shell，请求到来时立即从 CDN/边缘返回 shell，同时在同一个 HTTP 响应中流式输出动态部分。打破了「整个路由要么静态要么动态」的二选一。

**缓存层级（以 Next.js 14 文档的四层模型为准）**：

| 缓存 | 位置 | 缓存什么 | 生命周期 | 失效方式 |
|---|---|---|---|---|
| Request Memoization | 服务端（单次请求内） | 同一渲染过程中相同 URL+参数的 `fetch` 返回值（React 的能力） | 单次请求渲染结束 | 自动；非 fetch 可用 React `cache()` |
| Data Cache | 服务端（持久） | `fetch` 结果，跨请求、跨部署 | 持久，直到重新验证 | `revalidate` 时间、`revalidateTag/Path` |
| Full Route Cache | 服务端（持久） | 静态路由的 HTML + RSC Payload | 持久，重新部署清空 | 重新验证 Data Cache 会连带失效 |
| Router Cache | 客户端（内存） | 访问过/预取的路由段 RSC Payload | 会话期间，按 staleTime | `router.refresh()`、Server Action 中 `revalidatePath/Tag`、`cookies.set` |

**版本差异要点**：

- **Next.js 14**：`fetch` 默认 `force-cache`（默认缓存），GET Route Handler 默认缓存，Router Cache 动态页面缓存 30s。「默认缓存太激进」是主要吐槽。
- **Next.js 15（2024-10）**：`fetch` **默认不缓存**（需显式 `cache: 'force-cache'`），GET Route Handler 默认不缓存，Router Cache 对页面段默认 `staleTime: 0`（可用 `experimental.staleTimes` 配置）；`cookies()`、`headers()`、`params`、`searchParams` 变为**异步 API**（需 `await`）；支持 React 19。
- **Next.js 16（2025-10）**：引入 **Cache Components**，用 **`'use cache'` 指令**显式声明缓存（可标在文件、组件、函数上），配合 `cacheLife()` 设定生命周期、`cacheTag()` 打标签；`revalidateTag` 增加缓存配置参数，并新增 `updateTag` 等 API；PPR 成为 Cache Components 下的默认渲染方式；Turbopack 成为默认打包器；`middleware` 更名为 `proxy`。这些 API 仍在演进，**以官方文档为准**。

### 代码示例

```tsx
// SSG + ISR：动态段预生成 + 每小时重新验证
// app/blog/[slug]/page.tsx
export const revalidate = 3600;
export async function generateStaticParams() {
  const posts = await fetch('https://api.example.com/posts').then(r => r.json());
  return posts.map((p: { slug: string }) => ({ slug: p.slug }));
}
export default async function Page({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params; // 15+：params 是 Promise
  const post = await fetch(`https://api.example.com/posts/${slug}`, {
    next: { tags: [`post-${slug}`] },
  }).then(r => r.json());
  return <article>{post.title}</article>;
}

// 按需重新验证（CMS webhook / Server Action）
'use server';
import { revalidateTag, revalidatePath } from 'next/cache';
export async function publish(slug: string) {
  revalidateTag(`post-${slug}`); // 16 中签名有调整（增加缓存配置参数），以官方文档为准
  revalidatePath('/blog');
}

// SSR：读取请求时数据 → 路由变为动态
import { cookies } from 'next/headers';
export default async function Dashboard() {
  const token = (await cookies()).get('token')?.value;
  const data = await fetch('https://api.example.com/me', {
    headers: { Authorization: `Bearer ${token}` }, cache: 'no-store',
  }).then(r => r.json());
  return <div>{data.name}</div>;
}

// PPR / Cache Components（16 风格，示意，以官方文档为准）
import { Suspense } from 'react';
import { cacheLife } from 'next/cache';
async function ProductInfo({ id }: { id: string }) {
  'use cache';             // 静态可缓存部分，进入预渲染外壳
  cacheLife('hours');
  const p = await getProduct(id);
  return <h1>{p.name}</h1>;
}
export default async function Product({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (<>
    <ProductInfo id={id} />
    <Suspense fallback={<p>库存加载中…</p>}>
      <Stock id={id} />    {/* 读 cookies / 实时数据的动态部分，请求时流式填充 */}
    </Suspense>
  </>);
}
```

### 面试答题要点

1. App Router 默认 Server Component，layout 嵌套且导航时保持状态，loading/error 文件自动包 Suspense/ErrorBoundary。
2. SSG/SSR 不再由页面级函数声明，而是由「是否使用动态 API + 数据是否缓存」自动推断；`dynamic`、`revalidate` 等段配置可覆盖。
3. ISR 有时间和按需（revalidatePath/Tag）两种方式；PPR 让一条路由同时拥有静态外壳和流式动态区域。
4. 四层缓存：请求记忆化、数据缓存、完整路由缓存（服务端），路由器缓存（客户端）。
5. 版本趋势：14 默认缓存 → 15 默认不缓存 → 16 用 `'use cache'` 显式声明缓存，从「隐式」走向「显式」。

### 易错点 / 追问

- 「改了数据页面不更新」→ 常见原因是 Data Cache / Full Route Cache / Router Cache 某一层没失效，排查要分层。
- 在 layout 里读 `cookies()` 会让其下所有路由变为动态。
- `generateStaticParams` 未覆盖的动态段，默认会在首次请求时按需生成并缓存（可用 `dynamicParams = false` 改为 404）。
- 追问：「Pages Router 对应关系？」→ `getStaticProps` ≈ 缓存的 fetch / SSG；`getServerSideProps` ≈ 动态渲染；`getStaticProps + revalidate` ≈ ISR。

---

## 16. 手写简易 useState / 简易 Hooks 实现 ★★

### 是什么 / 原理

面试手写的目标是体现两点：**① 状态存在组件外部，按调用顺序索引；② setState 触发重新渲染**。下面给两个版本：数组 + 游标版（最简），以及贴近 React 源码的 Fiber 链表 + 更新队列版。

### 代码示例 1：数组 + 游标版（含 useState / useEffect / useMemo / useRef）

```js
// 每个"组件实例"一个 hooks 数组；这里简化为单组件
let hooks = [];        // 存放每个 Hook 的状态，按调用顺序排列
let cursor = 0;        // 当前执行到第几个 Hook
let Component = null;  // 被渲染的组件
let pendingEffects = [];

function useState(initial) {
  const i = cursor++;                       // 捕获当前位置，setState 闭包里用它定位
  if (hooks.length <= i) hooks[i] = typeof initial === 'function' ? initial() : initial;
  const setState = action => {
    const next = typeof action === 'function' ? action(hooks[i]) : action;
    if (Object.is(next, hooks[i])) return;  // 相同值跳过渲染
    hooks[i] = next;
    scheduleRender();
  };
  return [hooks[i], setState];
}

function depsChanged(prev, next) {
  return !prev || !next || next.some((d, k) => !Object.is(d, prev[k]));
}

function useEffect(effect, deps) {
  const i = cursor++;
  const old = hooks[i];
  if (!old || depsChanged(old.deps, deps)) {
    pendingEffects.push(() => {
      old?.cleanup?.();                      // 先执行上一次的清理
      hooks[i] = { deps, cleanup: effect() };
    });
  }
}

function useMemo(factory, deps) {
  const i = cursor++;
  const old = hooks[i];
  if (!old || depsChanged(old.deps, deps)) hooks[i] = { value: factory(), deps };
  return hooks[i].value;
}
const useCallback = (fn, deps) => useMemo(() => fn, deps);
function useRef(initial) {
  const i = cursor++;
  if (!hooks[i]) hooks[i] = { current: initial };
  return hooks[i];
}

let scheduled = false;
function scheduleRender() {                  // 微任务合并多次 setState = 简易批处理
  if (scheduled) return;
  scheduled = true;
  queueMicrotask(() => { scheduled = false; render(); });
}

function render() {
  cursor = 0;                                // 每次渲染从头按顺序读取 Hook
  const output = Component();
  pendingEffects.forEach(run => run());      // 模拟 commit 后执行 effect
  pendingEffects = [];
  return output;
}

// 使用
Component = function Counter() {
  const [count, setCount] = useState(0);
  useEffect(() => { console.log('effect', count); return () => console.log('cleanup', count); }, [count]);
  return { count, inc: () => { setCount(c => c + 1); setCount(c => c + 1); } };
};
let app = render();   // effect 0
app.inc();            // 微任务后：cleanup 0 → effect 2（两次 setState 只渲染一次）
```

### 代码示例 2：Fiber 链表 + 更新队列版（贴近源码）

```js
let currentlyRenderingFiber = null; // 当前正在渲染的 fiber
let workInProgressHook = null;      // 当前处理到的 hook（新链表）
let currentHook = null;             // 对应的旧 hook（current 树上的链表）
let isMount = true;

function mountWorkInProgressHook() {
  const hook = { memoizedState: null, queue: null, next: null };
  if (!workInProgressHook) currentlyRenderingFiber.memoizedState = workInProgressHook = hook;
  else workInProgressHook = workInProgressHook.next = hook; // 追加到链表尾部
  return hook;
}

function updateWorkInProgressHook() {
  // 沿旧链表按顺序取下一个——"顺序即身份"
  currentHook = currentHook ? currentHook.next : currentlyRenderingFiber.memoizedState;
  workInProgressHook = currentHook;
  return currentHook;
}

function useState(initialState) {
  const hook = isMount ? mountWorkInProgressHook() : updateWorkInProgressHook();
  if (isMount) {
    hook.memoizedState = initialState;
    hook.queue = { pending: null };
  }
  // 依次应用环形链表中的所有 update
  let pending = hook.queue.pending;
  if (pending) {
    let update = pending.next;     // pending 指向最后一个，next 是第一个
    let state = hook.memoizedState;
    do {
      state = typeof update.action === 'function' ? update.action(state) : update.action;
      update = update.next;
    } while (update !== pending.next);
    hook.memoizedState = state;
    hook.queue.pending = null;
  }
  const dispatch = dispatchAction.bind(null, currentlyRenderingFiber, hook.queue);
  return [hook.memoizedState, dispatch];
}

function dispatchAction(fiber, queue, action) {
  const update = { action, next: null };
  // 构造环形链表：新 update 插到末尾，queue.pending 始终指向最后一个
  if (!queue.pending) update.next = update;
  else { update.next = queue.pending.next; queue.pending.next = update; }
  queue.pending = update;
  schedule(fiber);
}

let scheduled = false;
function schedule(fiber) {
  if (scheduled) return;
  scheduled = true;
  queueMicrotask(() => { scheduled = false; renderFiber(fiber); });
}

function renderFiber(fiber) {
  currentlyRenderingFiber = fiber;
  workInProgressHook = null;
  currentHook = null;
  const result = fiber.type();
  isMount = false;
  return result;
}

// 使用
const fiber = { type: App, memoizedState: null };
function App() {
  const [a, setA] = useState(1);
  const [b, setB] = useState('x');
  console.log(a, b);
  return { setA, setB };
}
const { setA } = renderFiber(fiber); // 1 'x'
setA(n => n + 1); setA(n => n * 10);  // 微任务后渲染一次：20 'x'
```

### 面试答题要点

1. 状态存在组件函数之外（数组或 Fiber 链表），每次渲染重置游标/指针按顺序读取。
2. setState 闭包捕获的是 Hook 的位置（或 queue），所以多次渲染后依然能更新正确的槽位。
3. 更新先入队（环形链表便于 O(1) 追加和找到头部），在下次渲染时按顺序计算，这就是函数式更新能累加的原因。
4. 用微任务合并调度 = 简易批处理；真实 React 用 lane + Scheduler。
5. 手写版本直观解释了「为什么 Hook 不能条件调用」。

### 易错点 / 追问

- 手写版没有区分 render/commit、没有优先级与中断、只支持单组件，面试时主动说明简化点。
- 追问：「为什么用环形链表？」→ 只需保存一个指针 `pending`（指向尾部），尾部 `next` 即头部，追加和遍历都是 O(1) 起点。
- 追问：「如何支持多个组件？」→ 每个组件实例（Fiber）各自持有 hooks 链表，渲染前设置 `currentlyRenderingFiber` 即可。

---

## 17. 高频题速答清单

| 问题 | 30 秒答案 |
|---|---|
| Fiber 解决了什么问题？ | Stack Reconciler 递归不可中断导致长任务卡顿；Fiber 用链表拆成工作单元，配合 Scheduler 时间切片与 Lane 优先级，实现可中断、可恢复、可插队的渲染，提升响应性。 |
| 为什么不能在条件语句里写 Hook？ | Hook 状态以链表形式存在 Fiber 上，React 只靠调用顺序匹配节点；条件调用会让前后两次渲染顺序错位，状态串位。 |
| RSC 和 SSR 的区别？ | SSR 是渲染策略（服务端产出 HTML，所有组件仍要下载并注水）；RSC 是组件类型（只在服务端运行、代码零 bundle、产出 RSC Payload），二者互补。 |
| key 的作用？为什么不用 index？ | 同层标识节点身份以复用移动；index 在增删排序时与数据错位，导致多余更新和状态串位。 |
| React 18 有什么变化？ | createRoot、并发渲染、自动批处理、useTransition/useDeferredValue、流式 SSR + 选择性注水、useSyncExternalStore/useId。 |
| React 19 有什么变化？ | Actions、useActionState、useFormStatus、useOptimistic、use()、ref 作为 prop、Context 作 Provider、元数据与资源加载、RSC/Server Actions 稳定。 |
| useEffect 和 useLayoutEffect？ | 前者绘制后异步执行，后者 DOM 更新后、绘制前同步执行（阻塞绘制），用于测量布局避免闪烁。 |
| Context 的性能问题？ | value 变化让所有消费者重渲染、无 selector、memo 拦不住；拆分 Context、memo value 或换外部 store。 |
| Next.js 缓存几层？ | Request Memoization、Data Cache、Full Route Cache（服务端），Router Cache（客户端）；15 起 fetch 默认不缓存，16 用 `'use cache'` 显式缓存。 |
