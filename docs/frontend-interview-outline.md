# 前端面试大纲与侧重点

> 适用：初中高级前端 / 全栈偏前端岗位。每个模块标注 **侧重点**（面试官真正想考察什么）和 **高频题**。
> 星级：★★★ 必考 / ★★ 常考 / ★ 加分项

**分技术栈详解**（原理 / 代码 / 答题要点 / 追问）：

| 文档 | 对应大纲章节 |
|---|---|
| [01 HTML + CSS](frontend-interview/01-html-css.md) | 1、2 |
| [02 JavaScript](frontend-interview/02-javascript.md) | 3 |
| [03 TypeScript](frontend-interview/03-typescript.md) | 4 |
| [04 浏览器 + 网络 + 安全](frontend-interview/04-browser-network-security.md) | 5、6、10 |
| [05 React + Next.js](frontend-interview/05-react.md) | 7 |
| [06 Vue 生态](frontend-interview/06-vue.md) | 7' |
| [07 工程化 + 性能优化](frontend-interview/07-engineering-performance.md) | 8、9 |
| [08 Node + 系统设计 + AI](frontend-interview/08-node-system-design-ai.md) | 11、12、13 |

---

## 0. 不同级别的侧重差异

| 级别 | 核心考察 | 典型比重 |
|---|---|---|
| 初级（0–2 年） | JS/CSS 基础、框架 API 使用、手写简单题 | 基础 60% / 框架 30% / 项目 10% |
| 中级（2–5 年） | 原理（事件循环、响应式、diff）、性能优化、工程化 | 基础 30% / 原理 30% / 项目 40% |
| 高级 / 专家（5 年+） | 架构设计、前端系统设计、跨团队推动、技术选型取舍 | 原理 20% / 系统设计 40% / 项目与影响力 40% |

**通用准则**：答“是什么”只是及格，答“为什么 + 取舍 + 实际踩坑”才拿高分。

---

## 1. HTML ★★

**侧重点**：语义化、可访问性、浏览器如何解析文档。

- 语义化标签的意义（SEO、a11y、可维护性）
- `<script>` 的 `defer` / `async` / `type="module"` 区别
- `<link rel="preload | prefetch | preconnect | dns-prefetch">`
- 表单：原生校验、`<dialog>`、`<details>`、`inputmode`
- 可访问性：ARIA role、`alt`、焦点管理、键盘可操作
- Web Components：Custom Elements、Shadow DOM、`<template>` / `<slot>`

**高频题**：defer 和 async 的执行时机？如何让一个自定义下拉框可被读屏器识别？

---

## 2. CSS ★★★

**侧重点**：布局能力、层叠与优先级、渲染性能。

- 盒模型、`box-sizing`、BFC 的触发与用途（清浮动、防 margin 塌陷）
- 选择器优先级、`@layer` 层叠层、`:is()` / `:where()` / `:has()`
- 布局：Flex（`flex: 1` 拆解）、Grid（`fr`、`minmax`、`auto-fill` vs `auto-fit`）
- 定位：`position` 各值、`sticky` 失效原因、层叠上下文与 `z-index`
- 响应式：媒体查询、容器查询 `@container`、`clamp()`、视口单位 `dvh/svh`
- 现代特性：CSS 变量、嵌套、`color-mix()`、View Transitions、Scroll-driven Animations、Anchor Positioning
- 动画性能：`transform/opacity` 走合成层、`will-change`、重排 vs 重绘
- 工程方案：CSS Modules、Tailwind、CSS-in-JS 的取舍（运行时成本、RSC 兼容）

**高频题**：水平垂直居中 N 种方法；BFC 是什么；1px 问题；实现三栏/圣杯布局；`z-index` 为什么不生效。

---

## 3. JavaScript ★★★（重中之重）

**侧重点**：语言机制理解深度 + 手写能力。

### 3.1 语言核心
- 数据类型、类型判断（`typeof` / `instanceof` / `Object.prototype.toString`）
- 隐式转换、`==` vs `===`、`Object.is`
- 作用域、作用域链、闭包（用途 + 内存泄漏）
- `this` 绑定四规则 + 箭头函数
- 原型与原型链、继承方式、`class` 本质
- 执行上下文、变量提升、TDZ
- 深浅拷贝、`structuredClone`
- 垃圾回收（标记清除、分代）、`WeakMap/WeakRef`

### 3.2 异步 ★★★
- 事件循环：宏任务 / 微任务、浏览器 vs Node 差异
- Promise 状态机、链式调用、`all / allSettled / race / any`
- async/await 本质（Generator + 自动执行器）
- 输出顺序题（`setTimeout` + `Promise` + `async` 混合）

### 3.3 ES6+ 与新特性
- `let/const`、解构、展开、Symbol、Iterator/Generator
- Proxy / Reflect（Vue3 响应式基础）
- 模块化：ESM vs CommonJS（静态 vs 动态、值引用 vs 值拷贝、循环依赖）
- 新 API：`Array.prototype.at/findLast/toSorted/with`、`Object.groupBy`、`Promise.withResolvers`、`Set` 集合运算、`Iterator Helpers`

### 3.4 手写题清单 ★★★
| 类别 | 题目 |
|---|---|
| 函数 | `call/apply/bind`、`new`、`instanceof`、柯里化、compose |
| 控制 | 防抖、节流、并发控制（限制 N 个请求）、带重试的请求 |
| Promise | 手写 Promise（A+）、`Promise.all/race`、sleep、异步串行 |
| 数据 | 深拷贝（含循环引用）、数组扁平化、去重、LRU 缓存 |
| 模式 | EventEmitter（发布订阅）、简易响应式、虚拟 DOM 渲染 |
| 解析 | 模板字符串渲染、URL 参数解析、千分位格式化 |

---

## 4. TypeScript ★★★

**侧重点**：类型体操不是重点，**用类型约束业务**才是。

- `interface` vs `type`、`any` / `unknown` / `never`
- 泛型与约束、`keyof` / `typeof` / 索引访问类型
- 条件类型、`infer`、映射类型、模板字面量类型
- 内置工具类型：`Partial / Pick / Omit / Record / ReturnType / Awaited` 及手写实现
- 类型守卫、可辨识联合（discriminated union）
- `satisfies`、`as const`、协变 / 逆变
- 工程：`tsconfig` 关键项（`strict`、`moduleResolution`）、声明文件 `.d.ts`

**高频题**：手写 `DeepReadonly`、`Omit`；如何给一个 API 请求函数写出入参出参都能推导的类型。

---

## 5. 浏览器原理 ★★★

**侧重点**：从输入 URL 到页面显示的全链路。

- 输入 URL 到页面展示：DNS → TCP/TLS → HTTP → 解析 HTML → 构建 DOM/CSSOM → 布局 → 绘制 → 合成
- 渲染流水线：重排、重绘、合成层、GPU 加速
- 多进程架构（浏览器 / 渲染 / GPU / 网络进程）
- 存储：Cookie（`SameSite`、`HttpOnly`）、localStorage、sessionStorage、IndexedDB、Cache Storage
- 跨域：同源策略、CORS（简单请求 vs 预检）、代理、postMessage
- 事件机制：捕获 / 冒泡、事件委托
- Web Worker、Service Worker、SharedArrayBuffer

**高频题**：输入 URL 发生了什么（能讲 10 分钟是高分）；跨域解决方案；为什么 JS 会阻塞渲染。

---

## 6. 网络 ★★★

**侧重点**：HTTP 缓存与协议演进。

- HTTP 缓存：强缓存（`Cache-Control`、`Expires`）、协商缓存（`ETag`、`Last-Modified`）
- HTTP/1.1 → HTTP/2（多路复用、头部压缩）→ HTTP/3（QUIC、UDP）
- HTTPS 握手过程、证书校验
- TCP 三次握手 / 四次挥手、拥塞控制（了解）
- 常见状态码、请求方法、幂等性
- 实时通信：WebSocket、SSE（大模型流式输出常用）、长轮询
- CDN 原理

**高频题**：强缓存和协商缓存流程；HTTP/2 解决了什么问题，还剩什么问题。

---

## 7. 框架：React ★★★

**侧重点**：心智模型 + 渲染机制 + 新范式。

- 组件模型、JSX 本质、单向数据流
- Hooks：规则与原理（链表）、`useEffect` 依赖与清理、闭包陷阱
- `useMemo / useCallback / memo` 何时有用、何时多余
- 状态管理：Context 的性能问题、Redux Toolkit、Zustand、Jotai、TanStack Query（服务端状态）
- Fiber 架构、可中断渲染、Lane 优先级、调度
- Diff 算法（同层比较、key 的作用）
- 并发特性：`useTransition`、`useDeferredValue`、Suspense
- React 19：Actions、`useActionState`、`useOptimistic`、`use()`、ref 作为 prop
- React Compiler：自动记忆化，对手写 `useMemo` 的影响
- Server Components（RSC）、Server Actions、流式 SSR
- Next.js：App Router、缓存层级、SSR / SSG / ISR / PPR

**高频题**：Fiber 解决了什么问题；为什么不能在条件语句里写 Hook；RSC 和 SSR 的区别。

## 7'. 框架：Vue ★★★（Vue 技术栈岗位）

- 响应式原理：Vue2 `defineProperty` vs Vue3 `Proxy`，依赖收集与触发
- `ref` vs `reactive`、`computed` 缓存、`watch` vs `watchEffect`
- Composition API vs Options API
- 模板编译：静态提升、PatchFlag、Block Tree
- Diff：双端对比（Vue2）、最长递增子序列（Vue3）
- `nextTick` 原理、异步更新队列
- Pinia、Vue Router（导航守卫）
- Vapor Mode（无虚拟 DOM 编译模式）、Nuxt

**高频题**：Vue3 比 Vue2 快在哪；`v-if` 和 `v-for` 优先级；`key` 为什么不能用 index。

---

## 8. 工程化 ★★

**侧重点**：理解构建原理，能落地团队规范。

- 打包工具：Webpack（loader / plugin / 构建流程）、Vite（开发期 ESM + 生产 Rollup/Rolldown）、Rspack、esbuild
- Tree Shaking 条件、Code Splitting、动态 `import()`
- Babel / SWC 作用、AST 基本概念
- 包管理：npm / pnpm（硬链接、幽灵依赖）/ Monorepo（Turborepo、Nx）
- 代码规范：ESLint（flat config）、Prettier、Biome、Husky + lint-staged
- CI/CD、灰度发布、回滚策略
- 微前端：qiankun、Module Federation、iframe 方案取舍

**高频题**：Vite 为什么快；手写一个 Webpack loader/plugin 思路；pnpm 解决了什么问题。

---

## 9. 性能优化 ★★★

**侧重点**：**有数据、有方法论**——指标 → 定位 → 优化 → 验证。

- 核心指标 Core Web Vitals：**LCP、INP（已取代 FID）、CLS**，以及 FCP、TTFB
- 测量工具：Lighthouse、Chrome Performance 面板、`PerformanceObserver`、RUM 上报
- 加载优化：资源压缩、图片（WebP/AVIF、懒加载、`srcset`）、字体（`font-display`）、预加载、CDN、HTTP 缓存
- 渲染优化：减少重排、虚拟列表、`content-visibility`、骨架屏、长任务拆分（`scheduler.yield`）
- 框架层：避免无效渲染、按路由拆包、SSR / 流式渲染
- 内存泄漏排查（Heap Snapshot）

**高频题**：首屏从 4s 优化到 1s 你做了什么（要讲清楚数据）；长列表怎么优化；INP 差怎么排查。

---

## 10. 安全 ★★

- XSS（存储 / 反射 / DOM 型）及防御：转义、CSP、`HttpOnly`
- CSRF 及防御：`SameSite`、Token、Referer 校验
- 点击劫持（`X-Frame-Options`、`frame-ancestors`）
- 依赖供应链安全、`npm audit`、锁文件
- 前端敏感信息不落地、Token 存储方案取舍

---

## 11. Node.js / 全栈 ★（全栈岗 ★★★）

- 事件循环六阶段、`process.nextTick` vs `setImmediate`
- Stream、Buffer、cluster / worker_threads
- Express / Koa 中间件模型（洋葱模型手写）、NestJS
- BFF 层设计、SSR 服务稳定性（降级、缓存）
- Deno / Bun 了解

---

## 12. 前端系统设计 ★★★（高级岗核心）

**侧重点**：需求澄清 → 架构 → 数据模型 → 接口 → 性能/可用性 → 取舍。推荐 **RADIO** 框架：
Requirements（需求）→ Architecture（架构）→ Data model（数据模型）→ Interface（接口）→ Optimizations（优化）

**常见题目**：
- 设计信息流 / 无限滚动列表
- 设计自动补全搜索框（防抖、缓存、竞态处理、键盘导航）
- 设计图片轮播 / 富文本编辑器 / 在线协同文档（OT vs CRDT）
- 设计前端监控 SDK（错误、性能、行为采集与上报）
- 设计组件库（主题、按需加载、a11y、版本管理）
- 设计低代码平台（Schema 驱动、渲染器、物料体系）
- 设计 AI 聊天界面（流式渲染、Markdown 增量解析、中断与重试）

---

## 13. AI 时代新增考点 ★★（2025–2026 明显上升）

- 大模型流式响应：SSE / `fetch` + `ReadableStream`，增量渲染 Markdown 与代码高亮
- AI SDK（Vercel AI SDK 等）、Function Calling / Tool Use 在前端的落地
- Agent / MCP 基本概念，前端如何接入
- AI 辅助编程工作流（Cursor、Claude Code 等）：怎么用、怎么做代码审查和质量把关
- Prompt 设计、上下文管理、Token 成本意识
- 端侧推理：WebGPU、WebLLM、Transformers.js（加分项）

**高频题**：实现一个打字机效果的流式对话界面；用户中途取消生成怎么处理（`AbortController`）。

---

## 14. 算法与数据结构 ★★

**侧重点**：前端一般 LeetCode Easy–Medium，重思路和代码质量。

- 数组 / 字符串：双指针、滑动窗口、哈希表
- 链表：反转、环检测、合并
- 树：遍历（递归 + 迭代）、层序、最大深度、DOM 树遍历
- 栈 / 队列：括号匹配、单调栈
- 动态规划：爬楼梯、最长子序列、背包（了解）
- 排序：快排、归并（手写）
- 前端结合：树转列表 / 列表转树、虚拟 DOM diff、LRU

---

## 15. 项目经验 ★★★（决定级别的关键）

**侧重点**：你在项目里**解决了什么难题**、**为什么这么做**、**结果怎样**。

用 **STAR** 讲项目：Situation（背景）→ Task（目标）→ Action（方案与取舍）→ Result（量化结果）

准备清单：
- 1–2 个最有深度的项目，能被追问 5 层
- 每个项目准备：技术难点、方案对比、踩过的坑、量化指标（性能提升 X%、效率提升 Y%）
- 做过的基础建设：组件库、脚手架、监控、CI 流程、性能平台
- 跨团队协作 / 推动落地的经历

**常见追问**：为什么不用 X 方案？重新做一次会怎么改？最大的技术挑战是什么？

---

## 16. 软技能 / HR 面

- 职业规划、离职原因（正面表达）
- 冲突处理、需求变更应对
- 学习方式、技术关注点
- 反问环节：团队技术栈、业务方向、成长空间、评估方式

---

## 附：复习路线建议（4 周）

| 周 | 内容 |
|---|---|
| 第 1 周 | JS 核心 + 异步 + 手写题；CSS 布局 |
| 第 2 周 | 浏览器原理 + 网络 + 安全；TypeScript |
| 第 3 周 | 主框架原理（React 或 Vue）+ 工程化 + 性能优化 |
| 第 4 周 | 系统设计 + 项目梳理（STAR）+ 算法刷题 + 模拟面试 |

推荐资料：MDN、web.dev、React / Vue 官方文档、Front End Interview Handbook、GreatFrontEnd、JavaScript.info、LeetCode Hot 100。
