# 08 Node.js、前端系统设计与 AI 新考点 知识点详解

> 对应总大纲第 11 节（Node.js / 全栈 ★，全栈岗 ★★★）、第 12 节（前端系统设计 ★★★）、第 13 节（AI 时代新增考点 ★★）。
> 星级表示考频：★★★ 必考 / ★★ 常考 / ★ 加分项。
> 每节结构：**是什么 / 原理** → **代码示例** → **面试答题要点**（可以直接口述）→ **易错点 / 追问**。
> 内容按 2026 年的情况整理。AI 相关库的 API 变化很快，文中凡是标注「以官方文档为准」的地方，请以对应项目的最新文档为准。
> 文中 `compose` 和 SSE 流式读取解析代码已在 Node 24 下实际运行验证（含断言）。

## 目录

- [第一部分 Node.js](#第一部分-nodejs)
  - [1. 事件循环六阶段 ★★★](#1-事件循环六阶段-)
  - [2. nextTick / setImmediate / Promise 顺序题 ★★★](#2-nexttick--setimmediate--promise-顺序题-)
  - [3. Stream 与背压 ★★](#3-stream-与背压-)
  - [4. Buffer、cluster 与 worker_threads ★](#4-buffercluster-与-worker_threads-)
  - [5. Koa 洋葱模型与手写 compose ★★★](#5-koa-洋葱模型与手写-compose-)
  - [6. BFF 与 SSR 服务稳定性、Deno / Bun ★](#6-bff-与-ssr-服务稳定性deno--bun-)
- [第二部分 前端系统设计](#第二部分-前端系统设计)
  - [7. RADIO 框架 ★★★](#7-radio-框架-)
  - [8. 设计信息流 / 无限滚动列表 ★★★](#8-设计信息流--无限滚动列表-)
  - [9. 设计自动补全搜索框 ★★★](#9-设计自动补全搜索框-)
  - [10. 设计图片轮播 / 富文本编辑器 / 在线协同文档 ★★](#10-设计图片轮播--富文本编辑器--在线协同文档-)
  - [11. 设计前端监控 SDK ★★★](#11-设计前端监控-sdk-)
  - [12. 设计组件库 ★★](#12-设计组件库-)
  - [13. 设计低代码平台 ★★](#13-设计低代码平台-)
  - [14. 设计 AI 聊天界面 ★★★](#14-设计-ai-聊天界面-)
- [第三部分 AI 时代新增考点](#第三部分-ai-时代新增考点)
  - [15. 流式响应：fetch + ReadableStream 读取 SSE ★★★](#15-流式响应fetch--readablestream-读取-sse-)
  - [16. AbortController 取消与重试 ★★★](#16-abortcontroller-取消与重试-)
  - [17. Markdown 增量渲染 ★★](#17-markdown-增量渲染-)
  - [18. Function Calling / Tool Use ★★](#18-function-calling--tool-use-)
  - [19. Agent 与 MCP ★★](#19-agent-与-mcp-)
  - [20. AI SDK、AI 辅助编程与 Token 成本 ★★](#20-ai-sdkai-辅助编程与-token-成本-)
  - [21. 端侧推理（加分项）★](#21-端侧推理加分项)

---

# 第一部分 Node.js

## 1. 事件循环六阶段 ★★★

### 是什么 / 原理

Node 的事件循环由 **libuv** 实现。JS 代码在主线程单线程执行，文件 I/O、DNS、压缩等交给 libuv 线程池，网络 I/O 用操作系统的多路复用（epoll / kqueue / IOCP）。每轮循环依次经过六个阶段，每个阶段有自己的回调队列：

```text
   ┌───────────────────────────┐
┌─>│ 1. timers                 │  执行到期的 setTimeout / setInterval 回调
│  └─────────────┬─────────────┘
│  ┌─────────────┴─────────────┐
│  │ 2. pending callbacks      │  上一轮推迟的部分系统级 I/O 回调（如 TCP 错误）
│  └─────────────┬─────────────┘
│  ┌─────────────┴─────────────┐
│  │ 3. idle, prepare          │  libuv 内部使用
│  └─────────────┬─────────────┘
│  ┌─────────────┴─────────────┐
│  │ 4. poll                   │  取出新的 I/O 事件并执行回调（fs 读完、socket 数据到达等）；
│  │                           │  队列空时：有 setImmediate 就去 check，否则在这里阻塞等待 I/O 或最近的定时器
│  └─────────────┬─────────────┘
│  ┌─────────────┴─────────────┐
│  │ 5. check                  │  执行 setImmediate 回调
│  └─────────────┬─────────────┘
│  ┌─────────────┴─────────────┐
└──┤ 6. close callbacks        │  执行 socket.on('close') 等关闭回调
   └───────────────────────────┘
```

**微任务**不属于六个阶段。Node 11 起，**每执行完一个宏任务回调**，就会清空微任务：先清空 `process.nextTick` 队列，再清空 Promise 微任务队列（和浏览器行为对齐）。Node 11 之前是每个阶段结束才清空，这是一个经典的版本差异追问。

### 代码示例

```js
const fs = require('fs');
// 在 I/O 回调里：poll 阶段之后紧接着是 check，所以 setImmediate 一定先于 setTimeout
fs.readFile(__filename, () => {
  setTimeout(() => console.log('timeout'), 0);
  setImmediate(() => console.log('immediate'));
});
// 输出固定为：immediate → timeout
```

### 面试答题要点

1. 六阶段：timers → pending callbacks → idle/prepare → poll → check → close callbacks，常考的是 timers、poll、check 三个。
2. poll 阶段负责 I/O 回调，并且会在没有其他任务时阻塞等待 I/O，这是 Node 不空转的原因。
3. 微任务在每个宏任务回调之后清空，nextTick 队列优先于 Promise 队列（CommonJS 下）。
4. 和浏览器的区别：浏览器没有阶段划分，是“一个宏任务 → 清空微任务 → 可能渲染”；Node 有多个阶段和 `setImmediate`、`nextTick`。

### 易错点 / 追问

- **追问：libuv 线程池默认几个线程？** 4 个，可以用环境变量 `UV_THREADPOOL_SIZE` 调整。网络 I/O 不走线程池。
- **易错：** 以为 Node 是“单线程”所以不能并行。JS 执行是单线程，I/O 由 libuv 和操作系统并行处理；CPU 密集型任务才需要 `worker_threads`。
- **易错：** 递归调用 `process.nextTick` 会饿死 I/O，因为 nextTick 队列清空前事件循环无法进入下一阶段。

---

## 2. nextTick / setImmediate / Promise 顺序题 ★★★

### 是什么 / 原理

| API | 所属队列 | 执行时机 |
|---|---|---|
| `process.nextTick` | nextTick 队列 | 当前操作结束后立即执行，优先于 Promise 微任务 |
| `Promise.then` / `queueMicrotask` | 微任务队列 | nextTick 队列清空后 |
| `setTimeout(fn, 0)` | timers 阶段 | 至少 1ms 后（Node 会把 0 视为 1） |
| `setImmediate` | check 阶段 | 当前轮 poll 之后 |

### 代码示例（以下输出在 Node 24 实测）

```js
// order.cjs（CommonJS）
setTimeout(() => console.log('timeout'), 0);
setImmediate(() => console.log('immediate'));
Promise.resolve().then(() => console.log('promise'));
process.nextTick(() => console.log('nextTick'));
console.log('sync');
require('fs').readFile(__filename, () => {
  setTimeout(() => console.log('io-timeout'), 0);
  setImmediate(() => console.log('io-immediate'));
  process.nextTick(() => console.log('io-nextTick'));
});
```

```text
sync
nextTick
promise
timeout        ← 主模块中 timeout 和 immediate 的先后不确定，这次是 timeout 先
immediate
io-nextTick
io-immediate   ← I/O 回调中 immediate 一定先于 timeout
io-timeout
```

为什么主模块中 `timeout` 和 `immediate` 顺序不确定：进入事件循环时，如果距离 `setTimeout` 调用已经过了 1ms，timers 阶段就会执行它（timeout 先）；如果还不到 1ms，timers 阶段跳过，先到 check 执行 immediate。这取决于进程启动的性能，所以不确定。

**ESM 下的差异：** 同样的代码写成 `.mjs`，实测输出是 `sync → promise → nextTick → ...`。原因是 ES 模块的执行本身发生在一个 Promise 任务中，模块代码执行完时正处于微任务清空过程，新加入的 Promise 回调会在同一轮被执行，nextTick 要等这一轮微任务结束后才执行。

### 面试答题要点

1. 同步代码 → nextTick → Promise 微任务 → timers → check（CommonJS 主模块中）。
2. 主模块中 `setTimeout(0)` 和 `setImmediate` 顺序不确定；I/O 回调中 `setImmediate` 一定先执行。
3. nextTick 不是事件循环的一部分，它在当前操作完成后、进入下一阶段之前执行，所以滥用会饿死 I/O。
4. 官方建议优先用 `setImmediate` 或 `queueMicrotask`，`nextTick` 只用在需要“在当前操作结束后、任何 I/O 之前”执行的场景（如让 EventEmitter 用户先注册监听再触发事件）。

### 易错点 / 追问

- **易错：** 断言“`setTimeout(0)` 一定先于 `setImmediate`”。
- **追问：await 后面的代码是什么时机？** 相当于 Promise 微任务，`await x` 之后的代码在 x resolve 后作为微任务执行。
- **追问：ESM 和 CJS 顺序为什么不同？** 见上文，ES 模块代码在 Promise 任务里执行。面试时能讲出这一点是加分项。

---

## 3. Stream 与背压 ★★

### 是什么 / 原理

Stream 把数据分块处理，不需要一次把整个文件读进内存。四种类型：

| 类型 | 例子 |
|---|---|
| Readable | `fs.createReadStream`、HTTP 请求（服务端的 `req`） |
| Writable | `fs.createWriteStream`、HTTP 响应（`res`） |
| Duplex | TCP socket（可读可写，两个方向独立） |
| Transform | `zlib.createGzip()`（写入的数据经过转换后可读） |

**背压（Backpressure）**：生产速度大于消费速度时，数据会在内存中堆积。Writable 内部有缓冲区，阈值是 `highWaterMark`（字节流默认 16KB，Node 22 起调整为 64KB，以官方文档为准）：

- `writable.write(chunk)` 返回 `false` 表示缓冲区已满，生产方应该**暂停写入**；
- 缓冲区排空后触发 `'drain'` 事件，再继续写。

`pipe()` 和 `stream.pipeline()` 自动处理背压。`pipeline` 还会在任意一环出错时销毁所有流并回调错误，比 `pipe` 更安全（`pipe` 出错时不会自动销毁其他流，可能泄漏文件句柄）。

### 代码示例

```js
const fs = require('fs');
const zlib = require('zlib');
const { pipeline } = require('stream/promises');

// 推荐写法：pipeline 自动处理背压和错误
async function gzipFile(src, dest) {
  await pipeline(fs.createReadStream(src), zlib.createGzip(), fs.createWriteStream(dest));
}

/**
 * 手动处理背压：写入大量行数据，缓冲区满时等待 drain。
 * @param {import('stream').Writable} writable 目标可写流
 * @param {number} total 要写入的行数
 */
async function writeMany(writable, total) {
  for (let i = 0; i < total; i++) {
    const ok = writable.write(`line ${i}\n`);
    // 返回 false 说明缓冲区超过 highWaterMark，等排空再写，避免内存暴涨
    if (!ok) await new Promise((resolve) => writable.once('drain', resolve));
  }
  writable.end();
}
```

```js
// HTTP 服务中返回大文件：不要 readFile 整个读入内存
http.createServer((req, res) => {
  pipeline(fs.createReadStream('./big.mp4'), res).catch((err) => console.error(err));
});
```

### 面试答题要点

1. Stream 分块处理数据，内存占用和数据总量无关，适合大文件、网络传输、实时处理。
2. 背压：`write()` 返回 false 要暂停，等 `drain` 再继续；否则数据在内存里无限堆积。
3. 用 `pipeline` 替代 `pipe`，自动处理背压、错误传播和资源销毁。
4. 可读流可以用 `for await...of` 消费，代码更直观，也会自动处理背压。

### 易错点 / 追问

- **追问：浏览器的 Web Streams 和 Node Stream 关系？** 两套 API。Web Streams（`ReadableStream`）是 WHATWG 标准，Node 18 起全局可用，`fetch` 的 `res.body` 就是 Web Stream；两者可以用 `Readable.fromWeb()` / `Readable.toWeb()` 转换。
- **易错：** 忽略 `write()` 的返回值，在循环里狂写导致内存溢出。

---

## 4. Buffer、cluster 与 worker_threads ★

### 是什么 / 原理

- **Buffer**：处理二进制数据的固定长度字节序列，内存分配在 V8 堆外。`Buffer.from('中')` 长度是 3（UTF-8 三个字节）。拼接分块数据时要先 `Buffer.concat` 再 `toString`，否则多字节字符会在块边界被切断变成乱码（或者用 `StringDecoder` / `TextDecoder` 的流式解码）。
- **cluster**：多**进程**模型。主进程 fork 多个 worker 进程，共享同一个端口，充分利用多核。进程之间内存隔离，一个崩溃不影响其他。生产中常用 PM2 管理。
- **worker_threads**：多**线程**模型。同一进程内多个 JS 线程，每个线程有独立的 V8 实例和事件循环，可以通过 `SharedArrayBuffer` 共享内存。适合 CPU 密集型计算（图片处理、加密、解析）。

| 维度 | cluster | worker_threads |
|---|---|---|
| 单位 | 进程 | 线程 |
| 内存 | 完全隔离 | 默认隔离，可通过 SharedArrayBuffer 共享 |
| 通信 | IPC | `postMessage`，可传递 Transferable |
| 适用 | 提高 HTTP 服务吞吐、多核扩展 | CPU 密集计算，不阻塞主线程 |

### 代码示例

```js
// worker_threads：把计算放到子线程
const { Worker, isMainThread, parentPort, workerData } = require('worker_threads');

if (isMainThread) {
  const worker = new Worker(__filename, { workerData: 40 });
  worker.on('message', (result) => console.log('fib(40) =', result));
} else {
  const fib = (n) => (n < 2 ? n : fib(n - 1) + fib(n - 2));
  parentPort.postMessage(fib(workerData));
}
```

### 面试答题要点

1. Buffer 是堆外二进制数据，处理分块数据时注意多字节字符边界。
2. cluster 是多进程，用来利用多核提高吞吐；worker_threads 是多线程，用来跑 CPU 密集任务。
3. 容器化部署（K8s）时，常见做法是一个容器跑一个进程，靠多副本扩容，而不是在容器里用 cluster。

### 易错点 / 追问

- **追问：为什么不用 child_process？** child_process 适合执行外部命令或独立脚本，开销比 worker_threads 大，通信也更麻烦。
- **易错：** 用 worker_threads 去处理 I/O 密集任务，I/O 本来就是异步的，多线程没有收益。

---

## 5. Koa 洋葱模型与手写 compose ★★★

### 是什么 / 原理

Koa 的中间件按注册顺序执行，每个中间件调用 `await next()` 把控制权交给下一个，下游全部执行完后再回到当前中间件 `next()` 之后的代码。执行路径像穿过洋葱：

```text
请求 →  ┌ mw1 前半 ─────────────────────────────── mw1 后半 ┐ → 响应
        │   ┌ mw2 前半 ─────────────────── mw2 后半 ┐       │
        │   │   ┌ mw3（路由处理）───────────┐       │       │
        │   │   └──────────────────────────┘       │       │
        │   └──────────────────────────────────────┘       │
        └──────────────────────────────────────────────────┘
```

好处：中间件可以在“请求进入”和“响应返回”两个时机都处理逻辑，比如统计耗时、统一错误捕获、响应包装。Express 的 `next()` 不返回 Promise，无法自然地在下游异步完成后执行后置逻辑。

`compose` 的核心：`dispatch(i)` 执行第 i 个中间件，并把 `() => dispatch(i + 1)` 作为 `next` 传进去；每次都返回 Promise，于是 `await next()` 会等整个下游完成。

### 代码示例（已运行验证）

```js
/**
 * Koa 风格的中间件组合函数。
 * @param {Array<(ctx: object, next: () => Promise<void>) => any>} middlewares 中间件数组
 * @returns {(ctx: object, next?: () => Promise<void>) => Promise<void>} 组合后的函数
 */
function compose(middlewares) {
  if (!Array.isArray(middlewares)) throw new TypeError('middlewares 必须是数组');
  return function (ctx, finalNext) {
    let lastIndex = -1; // 记录已经执行到的中间件下标，用于检测重复调用 next
    function dispatch(i) {
      if (i <= lastIndex) return Promise.reject(new Error('next() 被调用了多次'));
      lastIndex = i;
      const fn = i === middlewares.length ? finalNext : middlewares[i];
      if (!fn) return Promise.resolve(); // 走到最后一个之后，next 什么都不做
      try {
        // 把 dispatch(i + 1) 作为 next 传给当前中间件；用 Promise.resolve 兼容同步中间件
        return Promise.resolve(fn(ctx, () => dispatch(i + 1)));
      } catch (err) {
        return Promise.reject(err); // 同步抛错也转成 rejected Promise
      }
    }
    return dispatch(0);
  };
}

// ---- 验证 ----
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = [];
const app = compose([
  async (ctx, next) => { log.push(1); await next(); log.push(6); },
  async (ctx, next) => { log.push(2); await sleep(10); await next(); log.push(5); },
  (ctx, next) => { log.push(3); return next().then(() => log.push(4)); },
]);
app({}).then(() => {
  console.log(log.join(' ')); // 1 2 3 4 5 6
});

compose([async (ctx, next) => { await next(); await next(); }])({})
  .catch((e) => console.log('捕获错误:', e.message)); // next() 被调用了多次
compose([() => { throw new Error('同步错误'); }])({})
  .catch((e) => console.log('捕获错误:', e.message)); // 同步错误
```

```js
// 典型应用：统一错误处理 + 耗时统计
app.use(async (ctx, next) => {
  const start = Date.now();
  try {
    await next();
  } catch (err) {
    ctx.status = err.status || 500;
    ctx.body = { code: ctx.status, message: err.expose ? err.message : '服务异常' };
  } finally {
    ctx.set('X-Response-Time', `${Date.now() - start}ms`);
  }
});
```

### 面试答题要点

1. 洋葱模型：`await next()` 之前是请求阶段，之后是响应阶段，执行顺序是 1→2→3→3 后→2 后→1 后。
2. `compose` 核心是递归的 `dispatch(i)`，把 `dispatch(i+1)` 作为 next 传入，每层都返回 Promise。
3. 用 `Promise.resolve` 包装兼容同步中间件；`try/catch` 把同步异常转成 rejected Promise；用下标检测 next 多次调用。
4. 最外层中间件用 `try/catch` 包住 `await next()`，就能捕获所有下游的异步错误，这是洋葱模型最实用的地方。

### 易错点 / 追问

- **易错：** 中间件里调用 `next()` 但不 `await` 也不 `return`，下游的异步逻辑还没完成，上游就继续执行了，后置逻辑顺序错乱，错误也捕获不到。
- **追问：Express 和 Koa 中间件区别？** Express 基于回调，`next()` 不返回 Promise，错误要通过 `next(err)` 传给四参数错误中间件（Express 5 开始支持 async 中间件抛出的 rejected Promise 自动传给错误处理）；Koa 基于 async/await，天然支持洋葱模型。
- **追问：Redux 中间件的 compose 有什么不同？** Redux 的 `compose(f, g, h)` 是函数组合 `(...args) => f(g(h(...args)))`，用 `reduce` 实现，本质也是洋葱形态但是同步的。

---

## 6. BFF 与 SSR 服务稳定性、Deno / Bun ★

### 是什么 / 原理

**BFF（Backend For Frontend）**：在前端和后端微服务之间加一层由前端团队维护的 Node 服务，负责：

- **接口聚合**：一个页面要调 5 个微服务，BFF 并行调用后合并成一个接口，减少前端请求数；
- **数据裁剪**：只返回前端需要的字段，不同端（Web / App / 小程序）返回不同结构；
- **协议转换**：后端 gRPC/Thrift → 前端 HTTP/JSON；
- 鉴权、限流、日志等横切逻辑。

代价：多一跳网络延迟、多一个需要运维的服务，前端团队要承担服务端稳定性责任。

**SSR 服务稳定性**：

| 风险 | 措施 |
|---|---|
| 渲染耗时高、CPU 打满 | 页面级缓存 / 组件级缓存（按 URL + 关键参数）；CDN 缓存公共页面；静态化（SSG/ISR） |
| 下游接口慢或挂掉 | 超时控制、熔断、降级为默认数据 |
| 流量突增 | 限流；超过阈值时**降级为 CSR**（返回空壳 HTML，由客户端渲染） |
| 内存泄漏 | 避免模块级别的全局状态（多个请求共享会串数据），监控内存，定期重启 |
| 单进程崩溃 | 多进程 / 多副本、健康检查、优雅退出 |

**Deno / Bun**：

- **Deno**：Node 作者的新项目，默认安全（文件、网络权限需要显式授予），原生 TypeScript，Deno 2 起大幅兼容 npm 和 Node API。
- **Bun**：用 Zig 写、基于 JavaScriptCore 的运行时，主打速度，集成包管理器、打包器、测试框架，大部分兼容 Node API。
- Node 本身也在吸收这些特性：内置 test runner、`--watch`、原生运行 TypeScript（类型剥离，较新版本默认开启，具体以 Node 官方文档为准）。

### 代码示例：BFF 聚合 + 超时降级

```js
/**
 * 给 Promise 加超时，超时后返回降级值而不是报错。
 * @template T
 * @param {Promise<T>} promise 原始请求
 * @param {number} ms 超时时间
 * @param {T} fallback 超时或出错时的降级值
 * @returns {Promise<T>}
 */
function withTimeout(promise, ms, fallback) {
  const timer = new Promise((resolve) => setTimeout(() => resolve(fallback), ms));
  return Promise.race([promise.catch(() => fallback), timer]);
}

// 首页聚合接口：核心数据失败要报错，非核心数据失败降级
router.get('/api/home', async (ctx) => {
  const [user, banners, recommends] = await Promise.all([
    userService.get(ctx.state.uid),                               // 核心，失败直接抛错
    withTimeout(cmsService.banners(), 300, []),                    // 非核心，300ms 超时降级为空
    withTimeout(recoService.list(ctx.state.uid), 500, []),
  ]);
  ctx.body = { user: { name: user.name, avatar: user.avatar }, banners, recommends };
});
```

### 面试答题要点

1. BFF 做聚合、裁剪、协议转换，让前端按页面需求拿数据；代价是多一跳和运维成本。
2. SSR 稳定性三板斧：缓存、超时降级、流量高峰降级为 CSR。
3. 区分核心依赖和非核心依赖：核心失败报错，非核心超时就降级。
4. SSR 中避免模块级全局状态，否则不同用户请求之间会串数据。

### 易错点 / 追问

- **追问：BFF 和 API 网关的区别？** 网关是通用的流量入口（路由、鉴权、限流），不关心具体页面；BFF 面向具体前端，包含业务聚合逻辑。
- **追问：GraphQL 能替代 BFF 吗？** GraphQL 解决了字段裁剪和聚合，可以作为 BFF 的一种实现方式，但会带来缓存复杂、N+1 查询等问题。

---

# 第二部分 前端系统设计

## 7. RADIO 框架 ★★★

### 是什么 / 原理

前端系统设计题通常 45–60 分钟，没有标准答案，考察的是**结构化思考、取舍能力和深度**。RADIO 框架帮你按顺序推进，避免一上来就写代码或者遗漏关键点：

| 步骤 | 含义 | 要做的事 | 建议时间 |
|---|---|---|---|
| **R** Requirements | 需求澄清 | 功能需求（核心功能 2–3 个）、非功能需求（性能、设备、离线、国际化、a11y）、规模（数据量、并发） | 约 10% |
| **A** Architecture | 架构 | 画出组件/模块及关系：视图层、状态管理、数据层、服务端 | 约 20% |
| **D** Data model | 数据模型 | 客户端状态有哪些、放在哪里（服务端数据缓存 vs UI 状态）、数据结构 | 约 15% |
| **I** Interface | 接口 | 前后端 API（参数、返回、分页方式）、组件对外 props / 事件 | 约 15% |
| **O** Optimizations | 优化与深入 | 性能、网络、体验、可访问性、安全、国际化；**讲清楚取舍** | 约 40% |

**答题技巧：**

1. 开头主动澄清需求，列出假设（“我假设主要是移动端、单页数据 20 条、需要支持离线”），让面试官确认。
2. 先给一个能工作的整体方案，再深入面试官感兴趣的部分。
3. 每个选择都说出取舍：“A 方案简单但……，B 方案复杂但……，在这个场景我选 A，因为……”。
4. 优化部分是区分级别的关键，高级岗要主动讲监控、降级、可扩展性。

### 代码示例：架构图的文字画法

```text
┌─────────────── 客户端 ───────────────┐
│  View（组件树）                       │
│     ↑ 订阅          ↓ 用户操作         │
│  Store（客户端状态 / 服务端数据缓存）   │
│     ↑                ↓                │
│  Data Layer（请求、缓存、重试、取消）    │
└──────────────────│───────────────────┘
                   ↓ HTTP / WebSocket / SSE
                 Server
```

### 面试答题要点

1. RADIO：需求 → 架构 → 数据模型 → 接口 → 优化，按顺序推进，时间重点放在优化和取舍。
2. 先澄清需求和规模，列出假设，不要直接开始设计。
3. 架构图要分层：视图、状态、数据访问层、服务端。
4. 每个技术选择都讲取舍，并结合场景给出结论。

### 易错点 / 追问

- **易错：** 花大量时间写组件代码或者陷入某个细节，没有覆盖完整设计。
- **易错：** 只讲功能不讲非功能需求（性能、可访问性、错误处理、监控）。

---

## 8. 设计信息流 / 无限滚动列表 ★★★

### 是什么 / 原理

类似微博、朋友圈、抖音网页版的信息流：用户向下滚动不断加载新内容，可以点赞、评论，并且有新内容提示。

### RADIO 参考答案

**R 需求**

- 功能：展示信息流（文字、图片、视频）；滚动到底自动加载更多；点赞/评论；顶部提示“有 N 条新内容”。
- 非功能：长时间滚动不卡顿（上千条）；首屏快；弱网可用；支持键盘和屏幕阅读器。

**A 架构**

```text
FeedPage
 ├── NewPostsBanner（轮询 / 推送：有新内容提示）
 ├── VirtualFeedList（虚拟列表，只渲染可视区域）
 │     └── FeedItem × N（图片懒加载、视频进入视口才播放）
 │           └── ActionBar（点赞：乐观更新）
 └── Sentinel（列表底部哨兵元素，IntersectionObserver 触发加载）

FeedStore：posts 归一化存储 + 分页游标
DataLayer：fetchFeed(cursor)、likePost(id)，请求去重、失败重试
```

**D 数据模型**

```ts
/** 单条帖子 */
interface Post {
  id: string;
  author: { id: string; name: string; avatar: string };
  content: string;
  media: Array<{ type: 'image' | 'video'; url: string; width: number; height: number }>; // 带宽高，防 CLS
  likeCount: number;
  liked: boolean;
  createdAt: number;
}

/** 信息流客户端状态 */
interface FeedState {
  postsById: Record<string, Post>; // key 是帖子 id，归一化存储，点赞时只更新一处
  order: string[];                 // 帖子 id 的展示顺序
  nextCursor: string | null;       // 下一页游标，null 表示没有更多
  status: 'idle' | 'loading' | 'error';
}
```

**I 接口**

```text
GET /api/feed?cursor=xxx&limit=20
  → { items: Post[], nextCursor: string | null }

GET /api/feed/new-count?since=<第一条的 id 或时间>
  → { count: number }

POST /api/posts/:id/like   body: { liked: boolean }
  → { likeCount: number }
```

分页方式选 **游标分页（cursor）** 而不是页码分页（offset）：信息流顶部不断有新内容插入，offset 分页会导致重复或漏掉数据；游标基于最后一条的 id/时间，稳定可靠。

**O 优化与取舍**

| 方面 | 做法 | 取舍 |
|---|---|---|
| 渲染 | 虚拟列表（不定高：预估高度 + ResizeObserver 测量）；或者 `content-visibility: auto` | 虚拟列表性能最好但实现复杂、页面内搜索失效；`content-visibility` 简单但节点数仍增长 |
| 加载触发 | IntersectionObserver 监听底部哨兵，提前一屏触发 | 比 scroll 事件性能好 |
| 图片视频 | 懒加载、按尺寸请求 CDN 图片、视频进入视口才加载和自动播放 | |
| 交互 | 点赞乐观更新，失败回滚并提示 | 体验好但要处理回滚 |
| 新内容 | 不自动插入顶部（会打断阅读并产生布局偏移），显示提示条，用户点击才插入并滚到顶部 | |
| 状态恢复 | 进入详情页再返回，恢复滚动位置和已加载数据（缓存列表数据 + 记录锚点帖子 id） | |
| 弱网 | 请求失败显示“重试”按钮；缓存上次的信息流离线展示 | |
| a11y | 使用 `role="feed"`、`aria-busy`，每条帖子 `role="article"`；提供“加载更多”按钮作为无限滚动的替代 | |
| 内存 | 超过一定数量后丢弃远离视口的数据，需要时重新请求 | |

### 面试答题要点

1. 分页用游标而不是 offset，避免新内容插入导致的重复和遗漏。
2. 渲染用虚拟列表，加载用 IntersectionObserver 哨兵，媒体懒加载并预留尺寸。
3. 数据归一化存储，点赞乐观更新，失败回滚。
4. 新内容用提示条而不是自动插入；返回列表时恢复滚动位置。
5. 兼顾 a11y：无限滚动对键盘用户不友好，提供替代方式。

### 易错点 / 追问

- **追问：不定高虚拟列表滚动条跳动？** 预估高度接近真实值，测量修正时保持视口锚点元素位置不变。
- **追问：怎么防止快速滚动时重复请求？** 请求中状态加锁；按 cursor 去重。

---

## 9. 设计自动补全搜索框 ★★★

### 是什么 / 原理

类似 Google 搜索框：输入时实时展示建议列表，支持键盘上下选择、回车确认。

### RADIO 参考答案

**R 需求**

- 功能：输入时展示建议；高亮匹配部分；键盘上下选择、回车确认、Esc 关闭；点击选择。
- 非功能：响应快（输入到出现建议 < 200ms 感知）；减少无效请求；可复用为组件（支持自定义请求函数和渲染项）；可访问。

**A 架构**

```text
<Autocomplete fetchSuggestions renderItem onSelect>
 ├── Input（受控；监听 input / keydown / focus / blur）
 ├── SuggestionList（role="listbox"，位置跟随输入框，超出时滚动）
 │     └── SuggestionItem × N（role="option"，高亮匹配文字）
 └── 内部控制器
       ├── debounce（300ms 内只发最后一次）
       ├── cache（LRU，key 是查询词）
       └── 竞态处理（AbortController 取消旧请求）
```

**D 数据模型**

```ts
interface Suggestion {
  id: string;
  text: string;
  type?: 'history' | 'hot' | 'normal'; // 历史记录 / 热搜 / 普通建议
}

interface AutocompleteState {
  query: string;
  results: Suggestion[];
  activeIndex: number;           // 键盘选中项下标，-1 表示无
  status: 'idle' | 'loading' | 'error';
  open: boolean;
}

// 结果缓存：key 是查询词（去首尾空格、转小写），value 是建议列表；用 Map 实现 LRU，上限 50 条
type SuggestionCache = Map<string, Suggestion[]>;
```

**I 接口**

```text
GET /api/suggest?q=rea&limit=10
  → { items: Suggestion[] }
```

组件接口：

```ts
interface AutocompleteProps {
  fetchSuggestions: (query: string, signal: AbortSignal) => Promise<Suggestion[]>;
  onSelect: (item: Suggestion) => void;
  renderItem?: (item: Suggestion, query: string) => React.ReactNode;
  debounceMs?: number;   // 默认 300
  minChars?: number;     // 最少输入几个字符才请求，默认 1
}
```

**O 优化与取舍**

```ts
// 核心请求逻辑：防抖 + 缓存 + 竞态处理
let controller: AbortController | null = null;
const cache = new Map<string, Suggestion[]>(); // key 是规范化后的查询词

const search = debounce(async (raw: string) => {
  const q = raw.trim().toLowerCase();
  if (cache.has(q)) return setResults(cache.get(q)!);
  controller?.abort();                 // 取消上一个还没返回的请求，避免旧结果覆盖新结果
  controller = new AbortController();
  try {
    const items = await props.fetchSuggestions(q, controller.signal);
    cache.set(q, items);
    if (cache.size > 50) cache.delete(cache.keys().next().value!); // Map 按插入顺序，删最早的
    setResults(items);
  } catch (e) {
    if ((e as Error).name !== 'AbortError') setStatus('error');
  }
}, 300);
```

| 方面 | 做法 | 取舍 |
|---|---|---|
| 请求频率 | 防抖 300ms | 时间短更实时但请求多；也可以用节流保证输入过程中持续有反馈 |
| 竞态 | AbortController 取消旧请求，或者给每个请求编号只接受最新的 | 取消还能节省带宽 |
| 缓存 | 内存 LRU；热门词可以预加载 | 结果有时效性时给缓存设过期时间 |
| 中文输入法 | `compositionstart` 时暂停搜索，`compositionend` 后再触发 | 否则拼音字母会触发大量无意义请求 |
| 键盘导航 | 上下键移动 activeIndex（循环），回车选择，Esc 关闭，选中项自动滚动到可见 | |
| a11y | 输入框 `role="combobox"`、`aria-expanded`、`aria-controls`、`aria-activedescendant` 指向当前选中项 | 焦点保持在输入框，屏幕阅读器读出选中项 |
| 安全 | 高亮匹配时不要用 `innerHTML` 拼接，用文本拆分渲染，防 XSS | |
| 失焦关闭 | blur 时延迟关闭或者用 `mousedown` + `preventDefault`，否则点击选项前列表就关闭了 | |

### 面试答题要点

1. 三个核心：防抖减少请求、缓存复用结果、竞态处理保证结果对应最新输入。
2. 竞态用 AbortController 取消旧请求，或者请求编号只接受最新响应。
3. 中文输入法要处理 composition 事件。
4. 键盘导航和 ARIA combobox 模式是高级岗的加分点。
5. 高亮匹配不要用 innerHTML，防 XSS。

### 易错点 / 追问

- **易错：** 只做了防抖没做竞态处理，网络慢时旧请求后返回覆盖新结果。
- **追问：数据量小（如城市列表）怎么做？** 一次性拉全量数据在前端过滤，不需要请求后端；数据很大时可以放在 Web Worker 里过滤。

---

## 10. 设计图片轮播 / 富文本编辑器 / 在线协同文档 ★★

### 是什么 / 原理

这道题通常三选一。轮播考组件 API 设计和细节，富文本考编辑器架构，协同文档考冲突解决（OT vs CRDT）。下面重点展开协同文档，前两者给出要点。

**图片轮播要点：** 无缝循环（首尾各克隆一张，滑到克隆项后无动画跳回真实位置）；`transform: translateX` 做动画；自动播放在悬停、页面隐藏（`visibilitychange`）、用户开启“减少动态效果”（`prefers-reduced-motion`）时暂停；只预加载当前和相邻图片；支持触摸滑动和键盘；a11y：`aria-roledescription="carousel"`，自动播放必须提供暂停按钮。现在也可以用 CSS `scroll-snap` 实现基础滑动，JS 只负责指示器和自动播放。

**富文本编辑器要点：** 不要直接依赖 `contenteditable` 的默认行为（不同浏览器生成的 HTML 不一致，`document.execCommand` 已废弃）。主流架构是 **数据模型驱动**：文档用结构化模型表示（ProseMirror、Slate、Lexical 都是这样），用户操作转换成对模型的事务（transaction），再由模型渲染出 DOM，实现撤销重做、协同、序列化都基于模型。

### 协同文档 RADIO 参考答案

**R 需求**

- 功能：多人同时编辑同一文档，实时看到别人的修改和光标；离线编辑后重新上线能合并；历史版本。
- 非功能：编辑延迟低（本地操作立即生效）；最终一致；支持几十人同时编辑。

**A 架构**

```text
客户端 A ─┐                                ┌─ 客户端 B
  Editor（ProseMirror/Lexical 等）            Editor
    ↕ 本地事务转为操作                          ↕
  协同层（OT 客户端 或 CRDT 文档，如 Yjs）      协同层
    ↕ WebSocket                                ↕
  ┌───────────── 协同服务 ─────────────┐
  │ 房间管理（按文档 id）                 │
  │ OT：中心化转换和排序 / CRDT：转发与合并 │
  │ Awareness：光标、选区、在线用户          │
  └────────────────┬───────────────────┘
                   ↓
         持久化（快照 + 增量操作日志）
```

**OT vs CRDT（核心考点）**

| 维度 | OT（Operational Transformation） | CRDT（Conflict-free Replicated Data Type） |
|---|---|---|
| 原理 | 操作基于位置（在第 5 位插入 “a”）。并发操作到达时，用 transform 函数根据对方操作调整位置 | 每个字符有全局唯一 id（客户端 id + 逻辑时钟），插入基于“在某个 id 之后”，合并满足交换律，任意顺序合并结果一致 |
| 服务端 | 通常需要中心服务器确定操作顺序 | 可以去中心化，服务器只需转发和存储，支持 P2P |
| 离线 | 离线越久，需要转换的操作越多，较复杂 | 天然支持，上线后合并即可 |
| 复杂度 | transform 函数正确性难保证，操作类型越多越复杂 | 算法本身复杂，但有成熟库 |
| 开销 | 文档数据小 | 需要保存元数据（id、删除标记），内存和体积更大（现代实现已大幅优化） |
| 代表 | Google Docs、早期的 ShareDB | Yjs、Automerge；Figma 采用类似 CRDT 的中心化方案 |

**D 数据模型**

```ts
/** OT 中的操作 */
type Op =
  | { type: 'insert'; pos: number; text: string }
  | { type: 'delete'; pos: number; len: number };

/** 提交给服务端的变更 */
interface ChangeSet {
  docId: string;
  baseVersion: number; // 基于哪个服务端版本做的修改，服务端据此决定要和哪些操作做 transform
  ops: Op[];
  clientId: string;
}

/** 协同感知信息（光标等），不持久化 */
interface Awareness {
  clientId: string;
  user: { name: string; color: string };
  cursor: { anchor: number; head: number } | null;
}
```

```ts
// OT 最简单的 transform：两个并发插入
// a 已经被服务端先应用，b 需要根据 a 调整位置
function transformInsert(a: { pos: number; text: string }, b: { pos: number; text: string }) {
  // 位置相同时需要确定性的平局规则（例如按 clientId 排序），这里简化为 a 优先
  return a.pos <= b.pos ? { ...b, pos: b.pos + a.text.length } : b;
}
```

**I 接口**

```text
WebSocket /collab/:docId
  客户端 → 服务端：{ type: 'change', baseVersion, ops }      （OT）
                   { type: 'update', update: Uint8Array }       （CRDT，Yjs 的二进制增量）
                   { type: 'awareness', cursor }
  服务端 → 客户端：{ type: 'ack', version }                  （确认自己的操作）
                   { type: 'remote', version, ops }            （其他人的操作）
GET /api/docs/:id/snapshot?version=  → 快照（打开文档、历史版本）
```

**O 优化与取舍**

- **本地优先**：本地操作立即应用到编辑器，再异步同步（乐观更新）；OT 中客户端维护“已发送未确认”和“未发送”两个缓冲区。
- **持久化**：定期生成快照 + 增量操作日志，打开文档时加载快照再回放少量增量。
- **离线**：操作存 IndexedDB，上线后同步；CRDT 方案更简单。
- **光标同步**：Awareness 信息高频但可丢失，单独通道、节流发送、不持久化。
- **权限**：服务端校验每个操作的权限，只读用户的操作直接拒绝。
- **选型**：自研 OT 成本很高；现在多数团队用 **Yjs + 编辑器绑定**（y-prosemirror 等）+ y-websocket 或自建服务，快速落地。

### 面试答题要点

1. 轮播：无缝循环靠克隆首尾，transform 动画，悬停 / 页面隐藏 / 减少动效偏好时暂停，相邻预加载，a11y。
2. 富文本：数据模型驱动，不依赖 contenteditable 默认行为，操作转成事务。
3. 协同核心是冲突解决：OT 基于位置变换、依赖中心服务器；CRDT 基于唯一 id、可交换合并、天然支持离线。
4. 本地操作先应用再同步；快照 + 操作日志持久化；光标信息走单独的轻量通道。
5. 实际选型多用 Yjs 等成熟 CRDT 库，讲清楚“为什么不自研”。

### 易错点 / 追问

- **追问：CRDT 删除的字符为什么不能直接删掉？** 其他客户端可能还有基于这个字符 id 的插入操作没到达，需要保留“墓碑”（tombstone），之后通过垃圾回收清理。
- **易错：** 说 CRDT 不需要服务器。CRDT 可以不依赖中心服务器做冲突解决，但实际产品仍需要服务器做转发、持久化和权限。

---

## 11. 设计前端监控 SDK ★★★

### 是什么 / 原理

前端监控 SDK 负责采集**错误、性能、用户行为**数据并上报，服务端做聚合分析、告警。代表产品：Sentry、各大厂自研。

### RADIO 参考答案

**R 需求**

- 功能：JS 错误、Promise 未处理拒绝、资源加载失败、接口错误采集；性能指标（Web Vitals、资源耗时）；用户行为（PV、点击、路由变化）；错误发生前的用户操作轨迹（面包屑）。
- 非功能：SDK 本身不能影响业务（体积小、不阻塞、自身出错不能导致页面崩溃）；数据不丢；可配置采样；插件化。

**A 架构**

```text
┌──────────────── SDK ────────────────┐
│ Core：init(config)、上下文（用户、版本、设备）
│  ├── 插件：ErrorPlugin / PerfPlugin / BehaviorPlugin / HttpPlugin
│  │       （每个插件负责采集一类数据，产生统一格式的事件）
│  ├── 处理管线：过滤（黑名单、去重）→ 采样 → 补充公共字段 → beforeSend 钩子
│  └── Transport：内存队列 → 批量合并 → sendBeacon / fetch keepalive / 图片打点
│                  失败写 IndexedDB / localStorage，下次启动重发
└──────────────────────────────────────┘
          ↓
  采集服务 → 消息队列 → 清洗 / SourceMap 还原 → 存储 → 看板 / 告警
```

**D 数据模型**

```ts
/** 统一的上报事件 */
interface MonitorEvent {
  type: 'error' | 'resource' | 'http' | 'perf' | 'pv' | 'click';
  timestamp: number;
  sessionId: string;
  traceId?: string;            // 和后端链路追踪关联
  context: {
    appId: string;
    release: string;           // 版本号，用于匹配 SourceMap
    url: string;
    userId?: string;
    ua: string;
  };
  payload: ErrorPayload | PerfPayload | HttpPayload | BehaviorPayload;
  breadcrumbs?: Breadcrumb[];  // 只有错误事件带上最近的操作轨迹
}

interface ErrorPayload { message: string; stack?: string; fingerprint: string } // fingerprint 用于聚合同类错误
interface PerfPayload { name: 'LCP' | 'INP' | 'CLS' | 'TTFB' | 'FCP'; value: number; rating: 'good' | 'needs-improvement' | 'poor' }
interface HttpPayload { method: string; url: string; status: number; duration: number }
interface BehaviorPayload { selector?: string; from?: string; to?: string }
interface Breadcrumb { category: 'click' | 'route' | 'http' | 'console'; message: string; timestamp: number }
```

**I 接口**

```ts
// SDK 对外 API
Monitor.init({
  dsn: 'https://collect.example.com/api/report',
  appId: 'web-shop',
  release: '1.4.2',
  sampleRate: 0.1,            // 性能和行为数据采样 10%，错误一般全量
  beforeSend: (event) => event, // 返回 null 丢弃，可用于脱敏
});
Monitor.setUser({ id: 'u_123' });
Monitor.captureException(err, { extra: { orderId } }); // 手动上报
```

```text
POST /api/report   body: MonitorEvent[]（批量）  → 204
```

**O 优化与取舍**

```js
// 错误采集核心
window.addEventListener('error', (e) => {
  // 资源加载错误不冒泡，只能在捕获阶段拿到；target 是 img/script/link 元素
  if (e.target && e.target !== window) {
    report({ type: 'resource', payload: { url: e.target.src || e.target.href, tag: e.target.tagName } });
  } else {
    report({ type: 'error', payload: { message: e.message, stack: e.error?.stack } });
  }
}, true);
window.addEventListener('unhandledrejection', (e) => {
  report({ type: 'error', payload: { message: String(e.reason?.message || e.reason), stack: e.reason?.stack } });
});
```

| 方面 | 做法 |
|---|---|
| 跨域脚本错误 | 只能拿到 `Script error.`：给 script 加 `crossorigin` 属性，CDN 返回 `Access-Control-Allow-Origin` |
| 堆栈还原 | 构建时生成 SourceMap 上传到监控服务（**不部署到线上**），服务端按 release 版本还原 |
| 接口监控 | 劫持（monkey patch）`fetch` 和 `XMLHttpRequest`，记录耗时、状态码；排除 SDK 自己的上报请求，避免死循环 |
| 上报可靠性 | 页面隐藏时 `sendBeacon`；批量 + 定时发送；失败持久化重发 |
| 不影响业务 | SDK 异步加载、所有采集代码 try/catch 包裹、空闲时处理（`requestIdleCallback`）、体积控制在几十 KB 内、插件按需引入 |
| 数据量控制 | 采样；同一错误短时间内去重（按 fingerprint）；限制每个会话最大上报数 |
| 隐私 | 不采集输入框内容；URL 和请求参数脱敏；遵守数据合规要求 |
| 框架错误 | React ErrorBoundary、Vue `app.config.errorHandler` 接入 |
| 白屏检测 | 页面加载后在若干采样点用 `elementsFromPoint` 检查是否只有容器元素 |

### 面试答题要点

1. 三类数据：错误（JS、Promise、资源、接口）、性能（Web Vitals）、行为（PV、点击、路由），错误附带面包屑。
2. 插件化架构：采集插件 → 处理管线（过滤、采样、脱敏）→ 传输层（批量、sendBeacon、失败重发）。
3. 资源错误要在捕获阶段监听；跨域脚本错误需要 crossorigin + CORS；堆栈靠 SourceMap 在服务端还原。
4. SDK 自身不能影响业务：异步加载、try/catch、体积小、采样和去重。
5. 用 release 版本号关联 SourceMap，用 traceId 关联后端链路。

### 易错点 / 追问

- **易错：** 劫持 fetch 后把 SDK 自己的上报请求也监控了，导致无限循环。
- **追问：为什么以前常用 1x1 的 gif 图片上报？** 无跨域限制、不阻塞页面、兼容性好；但 URL 长度有限。现在优先 `sendBeacon`，数据大时用 `fetch` + `keepalive`。

---

## 12. 设计组件库 ★★

### 是什么 / 原理

为公司多个业务线提供统一的 UI 组件，代表：Ant Design、MUI、Element Plus；新一代是“无样式组件 + 样式方案”，如 Radix UI、shadcn/ui（复制源码到项目里）。

### RADIO 参考答案

**R 需求**

- 功能：基础组件（按钮、表单、弹窗、表格等）；主题定制（品牌色、暗色模式）；国际化。
- 非功能：按需加载；a11y 达到 WCAG 2.x AA；TS 类型完整；SSR 兼容；版本升级平滑；文档完善。

**A 架构**

```text
monorepo
 ├── packages/tokens      设计令牌（颜色、间距、圆角、字号），输出 CSS 变量和 TS 常量
 ├── packages/hooks       无 UI 的逻辑 hooks（useControllableState、useFocusTrap）
 ├── packages/components  组件（每个组件一个目录：实现、样式、测试、文档示例）
 ├── packages/icons       图标（SVG 转组件，单独包）
 ├── docs                 文档站（Storybook / VitePress / Dumi），示例即测试
 └── 工具链：构建（ESM + CJS + 类型）、视觉回归测试、Changesets 发版
```

**D 数据模型（主题）**

```ts
/** 设计令牌：key 是语义化名称，value 是具体值 */
interface ThemeTokens {
  colorPrimary: string;
  colorBgBase: string;
  colorText: string;
  radiusBase: number;
  fontSizeBase: number;
}
```

```css
/* 主题用 CSS 变量实现，切换暗色只需切换类名，不需要重新加载 CSS */
:root { --color-primary: #1677ff; --color-bg: #fff; }
[data-theme='dark'] { --color-primary: #4096ff; --color-bg: #141414; }
.btn-primary { background: var(--color-primary); }
```

**I 接口（组件 API 设计原则）**

```ts
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'default' | 'text'; // 默认 default
  size?: 'small' | 'middle' | 'large';      // 默认 middle
  loading?: boolean;
  icon?: React.ReactNode;
}
// 原则：
// 1. 透传原生属性（...rest）并支持 ref 转发
// 2. 受控和非受控都支持（value + defaultValue + onChange）
// 3. 复杂组件提供组合式 API（<Select><Select.Option/></Select>）或插槽，而不是无限加 props
// 4. 命名在整个组件库保持一致（open/onOpenChange、size 取值统一）
```

**O 优化与取舍**

| 方面 | 做法 | 取舍 |
|---|---|---|
| 按需加载 | 输出 ESM、每个组件独立文件、`sideEffects` 声明 CSS，依靠 Tree Shaking；不再需要 babel-plugin-import | |
| 样式方案 | CSS 变量 + 预编译 CSS；或 CSS-in-JS | CSS-in-JS 动态主题方便，但有运行时开销和 SSR 复杂度；零运行时方案（编译期生成 CSS）是趋势 |
| a11y | 正确的语义和 ARIA、键盘交互、焦点管理（弹窗焦点陷阱和关闭后焦点返回）、对比度 | 参考 WAI-ARIA Authoring Practices |
| 质量 | 单测（Testing Library）、视觉回归测试（截图对比）、a11y 自动检查（axe） | |
| 版本管理 | 语义化版本；破坏性变更只在大版本；废弃 API 先打警告再移除；提供 codemod 自动迁移 | |
| 多框架 | 逻辑层与 UI 解耦（headless），或用 Web Components | headless 灵活但使用方要自己写样式 |

### 面试答题要点

1. 分层：设计令牌 → 逻辑 hooks → 组件 → 文档，monorepo 管理。
2. 主题用 CSS 变量，暗色模式切换类名即可；令牌语义化命名。
3. API 设计：透传原生属性、受控/非受控、组合式 API、命名一致。
4. 按需加载靠 ESM + sideEffects；a11y 和视觉回归测试保证质量。
5. 语义化版本 + 废弃警告 + codemod 保证升级平滑。

### 易错点 / 追问

- **追问：shadcn/ui 为什么流行？** 组件源码直接复制进项目，业务可以随意修改，不受组件库版本升级约束；代价是失去统一升级能力。
- **易错：** 只讲组件实现，不讲文档、测试、发版和升级策略。

---

## 13. 设计低代码平台 ★★

### 是什么 / 原理

通过拖拽组件、配置属性生成页面，核心是 **Schema 驱动**：编辑器产出一份描述页面的 JSON（Schema），渲染器根据 Schema 渲染出页面。

### RADIO 参考答案

**R 需求**

- 功能：物料面板拖拽组件到画布；属性面板配置组件属性、样式、事件；数据源绑定接口；预览、发布；撤销重做。
- 非功能：物料可扩展（业务方开发自定义组件）；渲染性能；Schema 版本兼容。

**A 架构**

```text
┌──────────── 设计器（Editor）────────────┐
│ 物料面板 │      画布（iframe 隔离）      │ 属性面板（根据物料的 props 描述自动生成表单）
│          │  拖拽、选中、辅助线、嵌套      │
└───────────┴───────────┬────────────────┘
                        ↓ 所有操作修改 Schema（命令模式，支持撤销重做）
                     Schema（JSON）
                        ↓
              渲染器（Renderer）：递归遍历 Schema → 查找组件 → 渲染
                        ↑
         物料体系：组件实现 + 物料描述（meta：名称、图标、可配置属性、是否容器）
```

**D 数据模型**

```ts
/** 页面 Schema 中的一个节点 */
interface ComponentNode {
  id: string;
  componentName: string;              // 对应物料注册名，如 'Button'
  props: Record<string, PropValue>;   // key 是属性名
  style?: Record<string, string>;     // key 是 CSS 属性名
  events?: Record<string, ActionConfig[]>; // key 是事件名，如 onClick
  children?: ComponentNode[];
  condition?: Expression;             // 条件渲染表达式
}

/** 属性值：静态值或表达式（绑定数据源、变量） */
type PropValue = string | number | boolean | null | { type: 'expression'; value: string };

interface Expression { type: 'expression'; value: string } // 如 "state.user.name"

/** 事件动作 */
interface ActionConfig {
  type: 'request' | 'navigate' | 'setState' | 'openModal' | 'customCode';
  params: Record<string, PropValue>; // key 是动作参数名
}

/** 物料描述 */
interface MaterialMeta {
  componentName: string;
  title: string;
  isContainer: boolean;
  props: Array<{ name: string; title: string; setter: 'input' | 'number' | 'select' | 'color' | 'json'; default?: PropValue }>;
}

/** 整个页面 */
interface PageSchema {
  version: string;                     // Schema 版本，用于升级迁移
  dataSources: Array<{ id: string; url: string; method: 'GET' | 'POST'; autoLoad: boolean }>;
  state: Record<string, PropValue>;    // key 是页面变量名
  root: ComponentNode;
}
```

**I 接口**

```tsx
// 渲染器核心：递归渲染
/**
 * 根据 Schema 节点渲染组件。
 * @param node 当前节点
 * @param registry 物料注册表，key 是 componentName，value 是组件实现
 * @param ctx 运行时上下文（页面状态、数据源结果），用于计算表达式
 */
function renderNode(node: ComponentNode, registry: Record<string, React.ComponentType<any>>, ctx: RuntimeContext) {
  if (node.condition && !evaluate(node.condition, ctx)) return null;
  const Comp = registry[node.componentName];
  if (!Comp) return <div key={node.id}>未知组件：{node.componentName}</div>; // 物料缺失时降级展示
  const props = resolveProps(node.props, ctx); // 把表达式计算成真实值
  return (
    <Comp key={node.id} {...props} style={node.style}>
      {node.children?.map((child) => renderNode(child, registry, ctx))}
    </Comp>
  );
}
```

```text
GET  /api/pages/:id        → PageSchema
PUT  /api/pages/:id        body: PageSchema（带版本号做乐观锁，防多人覆盖）
POST /api/pages/:id/publish → { url }
GET  /api/materials        → MaterialMeta[] + 组件资源地址
```

**O 优化与取舍**

| 方面 | 做法 | 取舍 |
|---|---|---|
| 画布隔离 | 画布放 iframe，物料样式和脚本不污染设计器 | 跨 iframe 拖拽和通信更复杂 |
| 撤销重做 | 命令模式记录操作；或 Schema 不可变数据 + 快照栈（Immer 的 patches） | 快照简单但占内存 |
| 表达式安全 | 表达式不用 `eval`，用沙箱（`new Function` + 白名单变量、或自定义解析器） | 自定义代码能力越强，安全风险越大 |
| 物料扩展 | 物料作为独立 npm 包 / 远程模块动态加载，带 meta 描述 | |
| 性能 | 大页面只重渲染修改的节点（节点级订阅）；发布时可以把 Schema 编译成代码（出码）提升运行性能 | 运行时渲染灵活，出码性能好但失去动态性 |
| 兼容 | Schema 带版本号，升级时写迁移函数 | |
| 边界 | 承认低代码的天花板：复杂交互提供自定义代码 / 自定义组件的逃生通道 | |

### 面试答题要点

1. 核心是 Schema 驱动：设计器产出 Schema，渲染器递归渲染，物料体系提供组件和元数据。
2. 属性面板根据物料 meta 自动生成；所有编辑操作都是对 Schema 的修改，支持撤销重做。
3. 数据绑定用表达式，表达式执行要沙箱化。
4. 画布 iframe 隔离；物料动态加载；Schema 版本化。
5. 运行时渲染 vs 出码的取舍；低代码要有逃生通道。

### 易错点 / 追问

- **追问：拖拽怎么实现？** HTML5 Drag and Drop API 或者基于 pointer 事件自己实现（更可控，支持触摸）；计算落点时根据鼠标位置和目标容器的子元素位置决定插入下标，并显示辅助线。
- **易错：** 表达式直接用 `eval` 执行，存在 XSS 和越权风险。

---

## 14. 设计 AI 聊天界面 ★★★

### 是什么 / 原理

类似 ChatGPT / Claude 的网页聊天界面。考点集中在流式渲染、Markdown 增量解析、中断和重试，具体代码见第 15–17 节。

### RADIO 参考答案

**R 需求**

- 功能：多轮对话；回复流式输出（打字机效果）；Markdown 和代码高亮渲染；停止生成；重新生成 / 编辑后重发；会话列表和历史；复制代码。
- 非功能：首字延迟低；长回复渲染不卡；网络中断可恢复；安全（模型输出不可信，防 XSS）。

**A 架构**

```text
ChatPage
 ├── ConversationList（会话列表，左侧边栏）
 ├── MessageList（消息列表，自动滚动到底部；用户向上滚动时暂停自动滚动）
 │     └── MessageItem
 │           ├── MarkdownRenderer（增量渲染：已完成块 memo，仅最后一块重渲染）
 │           └── 操作栏（复制、重新生成、点赞点踩）
 └── Composer（输入框：Enter 发送、Shift+Enter 换行、发送中显示“停止”按钮）

ChatStore：conversations、messages、当前流式消息
StreamClient：fetch + ReadableStream 解析 SSE；AbortController 取消；断线重试
      ↓
BFF（鉴权、限流、拼装上下文、隐藏 API Key、内容安全）→ 大模型 API
```

**D 数据模型**

```ts
interface Message {
  id: string;
  conversationId: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;                  // 流式过程中不断追加
  status: 'pending' | 'streaming' | 'done' | 'aborted' | 'error';
  parentId?: string;                // 重新生成时形成分支，支持切换不同回复版本
  createdAt: number;
}

interface Conversation {
  id: string;
  title: string;
  updatedAt: number;
}
```

**I 接口**

```text
POST /api/chat   body: { conversationId, messages | parentMessageId, model }
  响应：text/event-stream
    event: delta   data: {"content":"你"}
    event: delta   data: {"content":"好"}
    event: done    data: {"messageId":"m_2","usage":{"input":120,"output":350}}
    event: error   data: {"code":"rate_limited","message":"..."}
GET  /api/conversations                 → Conversation[]
GET  /api/conversations/:id/messages    → Message[]
POST /api/chat/:messageId/stop          （可选）通知服务端停止生成，节省 Token
```

**O 优化与取舍**

| 方面 | 做法 | 取舍 |
|---|---|---|
| 传输 | SSE（fetch + ReadableStream，能用 POST、带自定义请求头） | 原生 `EventSource` 只支持 GET 且不能自定义请求头；WebSocket 双向但要自己管理连接，流式回复场景 SSE 足够 |
| 渲染频率 | 收到的增量先放缓冲区，每帧（rAF）合并一次 setState | 每个 token 都 setState 会导致过多渲染 |
| Markdown | 按块切分，已完成的块缓存不再重新解析；未闭合的代码块临时补全；代码高亮在代码块闭合后再做 | 见第 17 节 |
| 打字机效果 | 网络到达节奏不均匀时，用匀速输出平滑显示（缓冲区按固定速率吐字），流结束时一次性追上 | 平滑但会增加感知延迟，不要人为放慢太多 |
| 滚动 | 在底部时自动跟随；用户主动上滑后停止跟随并显示“回到底部”按钮 | |
| 停止 | AbortController 取消请求，保留已生成内容并标记 aborted；服务端感知连接断开后停止生成 | |
| 重试 | 网络错误自动重试（指数退避）；用户“重新生成”创建新的分支消息 | 已经输出一部分时自动重试会重复内容，要么从头重新生成，要么服务端支持断点续传 |
| 安全 | Markdown 渲染禁用原始 HTML 或用 DOMPurify 净化；链接加 `rel="noopener noreferrer"` | 模型输出可能被提示注入攻击 |
| 长会话 | 消息列表虚拟化；历史分页加载 | |
| a11y | 流式区域用 `aria-live="polite"`，但不要逐字播报，完成后再整体通知 | |

### 面试答题要点

1. 传输选 fetch + ReadableStream 读 SSE，因为要 POST 和自定义鉴权头；讲清楚和 EventSource、WebSocket 的取舍。
2. 渲染性能：缓冲 + rAF 合并更新；Markdown 分块增量解析，已完成块缓存。
3. 停止生成用 AbortController，保留已生成内容；服务端检测连接断开后停止生成节省 Token。
4. 消息带状态（streaming / done / aborted / error）和父 id，支持重新生成形成分支。
5. 模型输出不可信，Markdown 渲染要防 XSS；API Key 只放在服务端。

### 易错点 / 追问

- **易错：** 在前端直接调用模型 API 并把 API Key 放在前端代码里。
- **追问：怎么做首字延迟优化？** 服务端尽早 flush 响应头；关闭代理层缓冲（如 Nginx `X-Accel-Buffering: no`）；前端先展示“思考中”状态。

---

# 第三部分 AI 时代新增考点

## 15. 流式响应：fetch + ReadableStream 读取 SSE ★★★

### 是什么 / 原理

大模型生成一段回复可能要十几秒，流式输出让用户在第一个 token 生成后就开始看到内容。主流 API 用 **SSE（Server-Sent Events）** 格式：

```text
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: message            ← 可选，事件类型，默认 message
data: {"delta":"你"}       ← 数据，一个事件可以有多行 data，用 \n 拼接
id: 1                     ← 可选
                          ← 空行表示一个事件结束
data: {"delta":"好"}

: ping                    ← 冒号开头是注释，常用作心跳
```

前端读取的两种方式：

1. **`EventSource`**：浏览器原生，自动重连，但只支持 GET、不能设置自定义请求头（如 `Authorization`）。
2. **`fetch` + `ReadableStream`**：可以 POST、自定义请求头、配合 AbortController，需要自己解析 SSE 格式。AI 聊天场景基本都用这种。

解析的难点：**网络分块和事件边界不对齐**。一次 `reader.read()` 拿到的数据可能是半个事件、半行，甚至半个中文字符（UTF-8 多字节被切断）。所以要：

- 用 `TextDecoderStream`（或 `TextDecoder` 的 `{ stream: true }` 选项）做流式解码，处理被切断的多字节字符；
- 维护一个缓冲区，只处理完整的行，残留部分留到下一次。

### 代码示例（已运行验证）

```js
/**
 * 创建一个 SSE 增量解析器：可以多次喂入文本片段，片段可能在任意位置被切断。
 * @param {(event: {event: string, data: string, id?: string}) => void} onEvent 每解析出一个完整事件时回调
 * @returns {{ feed: (chunk: string) => void, flush: () => void }}
 */
export function createSSEParser(onEvent) {
  let buffer = '';       // 还没凑成完整一行的残留文本
  let dataLines = [];    // 当前事件累积的 data 行（一个事件可以有多行 data）
  let eventName = '';    // 当前事件的 event 字段，默认 message
  let lastId;            // 当前事件的 id 字段

  // 遇到空行：派发当前事件
  function dispatch() {
    if (dataLines.length > 0) {
      onEvent({ event: eventName || 'message', data: dataLines.join('\n'), id: lastId });
    }
    dataLines = [];
    eventName = '';
  }

  // 处理一行完整的文本
  function processLine(line) {
    if (line === '') return dispatch();
    if (line.startsWith(':')) return; // 冒号开头是注释（常用作心跳）
    const idx = line.indexOf(':');
    const field = idx === -1 ? line : line.slice(0, idx);
    let value = idx === -1 ? '' : line.slice(idx + 1);
    if (value.startsWith(' ')) value = value.slice(1); // 规范：冒号后的一个空格要去掉
    if (field === 'data') dataLines.push(value);
    else if (field === 'event') eventName = value;
    else if (field === 'id') lastId = value;
    // retry 等其他字段这里忽略
  }

  return {
    feed(chunk) {
      buffer += chunk;
      // 兼容 \r\n、\n、\r 三种换行；最后一段可能不完整，留在 buffer 里等下一个片段。
      // 末尾的单独 \r 先不当换行：它可能是被切断的 \r\n，否则下个片段开头的 \n 会被误判成空行，提前派发事件
      const lines = buffer.split(/\r\n|\n|\r(?!$)/);
      buffer = lines.pop();
      lines.forEach(processLine);
    },
    flush() {
      if (buffer) processLine(buffer.replace(/\r$/, ''));
      buffer = '';
      dispatch();
    },
  };
}

/**
 * 用 fetch + ReadableStream 读取 OpenAI 风格的 SSE 流式接口。
 * @param {object} options
 * @param {string} options.url 接口地址
 * @param {object} options.body 请求体
 * @param {AbortSignal} [options.signal] 用于取消请求
 * @param {(delta: string) => void} options.onDelta 每收到一段增量文本时回调
 * @returns {Promise<string>} 完整的回复文本
 */
export async function streamChat({ url, body, signal, onDelta }) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`请求失败：HTTP ${res.status}`);

  let fullText = '';
  let done = false;
  const parser = createSSEParser(({ data }) => {
    if (data === '[DONE]') { done = true; return; } // OpenAI 风格的结束标记
    const delta = JSON.parse(data).choices?.[0]?.delta?.content ?? '';
    if (delta) { fullText += delta; onDelta(delta); }
  });

  // TextDecoderStream 负责处理被切断的多字节 UTF-8 字符（如中文）
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  try {
    while (!done) {
      const { value, done: streamDone } = await reader.read();
      if (streamDone) break;
      parser.feed(value);
    }
    parser.flush();
  } finally {
    reader.releaseLock();
  }
  return fullText;
}
```

验证方式：在 Node 24 中起一个本地 HTTP 服务，把 SSE 响应**每 5 个字节**切一块发送（会切断中文字符和行），断言拼出的文本是 `你好，世界！`；解析器单独用每 3 个字符一块喂入包含 `\r\n`、多行 data、注释、无空格 data 的样本，断言事件完全正确；再用 AbortController 在 50ms 后取消一个不结束的流，断言抛出 `AbortError`。三项全部通过。

> 实际踩坑：第一版解析器用 `/\r\n|\n|\r/` 切行，测试时 `\r\n` 恰好被切在两块之间，`\r` 被当作换行，下一块开头的 `\n` 被当作空行，事件被提前派发、`event` 字段丢失。修正方法就是上面代码里“末尾单独的 `\r` 先不当换行”。这是一个很好的面试追问素材。

```js
// 在 React 中使用：缓冲 + rAF 合并更新，避免每个 token 都触发渲染
function useStreamingMessage() {
  const [text, setText] = useState('');
  const bufferRef = useRef('');
  const rafRef = useRef(0);

  const append = useCallback((delta) => {
    bufferRef.current += delta;
    if (!rafRef.current) {
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = 0;
        const chunk = bufferRef.current;
        bufferRef.current = '';
        setText((prev) => prev + chunk);
      });
    }
  }, []);
  return { text, append, reset: () => setText('') };
}
```

### 面试答题要点

1. SSE 是基于 HTTP 的单向流，格式是 `field: value` 行，空行分隔事件；AI 场景用 fetch + ReadableStream 而不是 EventSource，因为要 POST 和自定义鉴权头。
2. 解析难点是分块边界：用 `TextDecoderStream` 处理多字节字符，用缓冲区只处理完整行。
3. 识别结束：OpenAI 风格是 `data: [DONE]`，其他厂商可能是特定的事件类型，以各自官方文档为准。
4. 渲染层用缓冲 + rAF 合并更新，避免高频 setState。
5. 服务端/代理要关闭响应缓冲，否则流式变成一次性返回。

### 易错点 / 追问

- **易错：** 每次 `read()` 直接 `JSON.parse`，没有处理半行，偶发 JSON 解析报错。
- **易错：** 用 `new TextDecoder().decode(value)` 却不传 `{ stream: true }`，中文偶发乱码。
- **追问：流式响应为什么要 HTTP/2？** HTTP/1.1 下浏览器对同一域名有约 6 个连接上限，多个长连接 SSE 会占满连接；HTTP/2 多路复用没有这个问题。

---

## 16. AbortController 取消与重试 ★★★

### 是什么 / 原理

`AbortController` 是取消异步操作的标准机制：

- `controller.signal` 传给 `fetch`、`addEventListener`、Node 的很多 API；
- 调用 `controller.abort(reason)` 后，`fetch` 返回的 Promise 以 `AbortError` 拒绝；**正在读的流**（`reader.read()`）也会拒绝；
- `AbortSignal.timeout(ms)` 创建一个超时自动取消的 signal；`AbortSignal.any([s1, s2])` 合并多个 signal（任意一个取消就取消），较新的浏览器和 Node 都已支持，兼容性以 MDN 为准。

**取消生成的完整流程：**

```text
用户点击“停止”
 → controller.abort()
 → fetch / reader.read() 抛出 AbortError
 → 前端：捕获后保留已生成内容，消息状态标记为 aborted，不提示错误
 → 网络连接断开 → 服务端检测到客户端断开（req.on('close')）→ 停止调用模型，节省 Token
```

### 代码示例

```js
/**
 * 带取消、超时和指数退避重试的流式请求。
 * @param {object} options 透传给 streamChat 的参数（url、body、onDelta）
 * @param {AbortSignal} userSignal 用户点击“停止”对应的 signal
 * @param {number} [maxRetries=2] 最大重试次数
 */
async function streamWithRetry(options, userSignal, maxRetries = 2) {
  let received = false; // 是否已经收到过内容
  for (let attempt = 0; ; attempt++) {
    // 用户取消 或 60s 超时，任一触发都取消本次请求
    const signal = AbortSignal.any([userSignal, AbortSignal.timeout(60_000)]);
    try {
      return await streamChat({ ...options, signal, onDelta: (d) => { received = true; options.onDelta(d); } });
    } catch (err) {
      if (userSignal.aborted) throw err;           // 用户主动取消：不重试
      // 已经输出过内容就不自动重试，否则内容会重复；交给用户点“重新生成”
      if (received || attempt >= maxRetries) throw err;
      await new Promise((r) => setTimeout(r, 1000 * 2 ** attempt)); // 1s、2s 指数退避
    }
  }
}

// 组件中
const controllerRef = useRef(null);
async function send(body) {
  controllerRef.current?.abort();              // 发新消息前取消上一个还在生成的
  const controller = (controllerRef.current = new AbortController());
  try {
    await streamWithRetry({ url: '/api/chat', body, onDelta: append }, controller.signal);
    setStatus('done');
  } catch (err) {
    setStatus(err.name === 'AbortError' && controller.signal.aborted ? 'aborted' : 'error');
  }
}
const stop = () => controllerRef.current?.abort();
```

```js
// Node 服务端：客户端断开时停止生成
app.post('/api/chat', async (req, res) => {
  const controller = new AbortController();
  res.on('close', () => controller.abort()); // 连接关闭（包括用户点停止）
  res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no' });
  // 以具体模型 SDK 的官方文档为准：大多数 SDK 支持传入 signal 来取消上游请求
  for await (const chunk of callModelStream(req.body, { signal: controller.signal })) {
    res.write(`data: ${JSON.stringify(chunk)}\n\n`);
  }
  res.end();
});
```

### 面试答题要点

1. `AbortController` 是统一取消机制，abort 后 fetch 和正在读的流都会抛出 `AbortError`。
2. 用户取消要和真实错误区分：取消时保留已有内容、标记 aborted，不弹错误。
3. 服务端监听连接关闭，停止上游模型调用，节省 Token 成本。
4. 重试：只对网络错误、5xx、限流重试，指数退避；已经输出内容后不自动重试，避免内容重复。
5. `AbortSignal.timeout` 做超时，`AbortSignal.any` 合并用户取消和超时。

### 易错点 / 追问

- **易错：** abort 后把 AbortError 当普通错误提示“请求失败”。
- **追问：竞态问题？** 用户快速连发两条消息，先取消旧请求再发新请求；或者给每次请求一个 id，只接受当前 id 的数据。
- **追问：429 限流怎么处理？** 读取 `Retry-After` 响应头决定等待时间，并在界面提示。

---

## 17. Markdown 增量渲染 ★★

### 是什么 / 原理

模型输出的是 Markdown 文本，并且是逐步到达的。朴素做法是每次收到增量后把**全部文本**重新解析成 HTML 并渲染，问题：

1. **性能**：回复越长，每次全量解析越慢，复杂度接近 O(n²)，代码高亮尤其耗时；
2. **闪烁**：未闭合的语法导致中间态渲染错误，比如代码块只有开头的 ```，后面所有文本都被当成代码；`**加粗` 还没闭合时显示星号；
3. **状态丢失**：整体替换 DOM 会导致选中文本、展开状态丢失。

**增量渲染思路：**

```text
完整文本 = 已稳定的块 + 正在生成的最后一块

1. 按块切分：用 Markdown 词法分析（如 marked 的 lexer）把文本切成块级 token（段落、标题、列表、代码块、表格）
2. 除最后一块外的块都已经稳定：每块用内容 hash 做 key，React.memo 缓存，不再重新解析和渲染
3. 只重新解析和渲染最后一块
4. 最后一块的不完整语法做“临时补全”：
     - 代码块围栏数量为奇数 → 末尾临时补一个 ```
     - 行内未闭合的 ** / ` → 暂时按普通文本处理，或临时补全
5. 代码高亮：代码块闭合（不再是最后一块）后再做高亮，生成中只显示纯文本或轻量高亮
6. 安全：禁用原始 HTML 或者用 DOMPurify 净化后再插入
```

### 代码示例

```jsx
import { marked } from 'marked'; // 具体 API 以 marked 官方文档为准
import DOMPurify from 'dompurify';
import { memo, useMemo } from 'react';

/**
 * 补全未闭合的代码块围栏，避免后续文本全被当成代码。
 * @param {string} text 最后一块的原始文本
 * @returns {string} 补全后的文本
 */
function closeOpenFence(text) {
  const fenceCount = (text.match(/^```/gm) || []).length;
  return fenceCount % 2 === 1 ? text + '\n```' : text;
}

/** 单个块：内容不变就不重新渲染 */
const Block = memo(function Block({ raw }) {
  const html = useMemo(() => DOMPurify.sanitize(marked.parse(raw)), [raw]);
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
});

/**
 * 流式 Markdown 渲染：前面的块缓存，只有最后一块随内容变化重新渲染。
 * @param {{ content: string, streaming: boolean }} props
 */
export function StreamingMarkdown({ content, streaming }) {
  // 词法分析切出块级 token，每个 token 的 raw 是这一块的原始文本
  const blocks = useMemo(() => marked.lexer(content).map((t) => t.raw), [content]);
  return blocks.map((raw, i) => {
    const isLast = i === blocks.length - 1;
    const text = isLast && streaming ? closeOpenFence(raw) : raw;
    // 稳定块用 下标 作 key 即可（块只会追加，不会插入到中间）
    return <Block key={i} raw={text} />;
  });
}
```

说明：上面每次仍会对全文做一次 lexer（词法分析很快），但昂贵的 HTML 生成、净化、高亮和 DOM 更新只发生在最后一块。更极致的做法是只对“最后一个稳定块之后”的文本做增量词法分析。社区也有专门的流式 Markdown 渲染库，具体选型以各库官方文档为准。

### 面试答题要点

1. 全量重新解析的问题：性能 O(n²)、未闭合语法导致闪烁、DOM 状态丢失。
2. 分块：已完成块缓存（memo），只重渲染最后一块。
3. 最后一块对未闭合语法做临时补全，尤其是代码块围栏。
4. 代码高亮延迟到块完成后，或放到 Web Worker。
5. 模型输出不可信，渲染前必须净化 HTML。

### 易错点 / 追问

- **追问：为什么不直接用 react-markdown？** 可以用，它生成 React 元素不需要 `dangerouslySetInnerHTML`，更安全；但默认每次全量解析，长文本流式时要配合分块 memo。
- **易错：** 用 `dangerouslySetInnerHTML` 渲染模型输出但没做净化。

---

## 18. Function Calling / Tool Use ★★

### 是什么 / 原理

大模型本身只能生成文本，**Function Calling（也叫 Tool Use）** 让模型可以“调用工具”：

```text
1. 开发者在请求中声明可用工具：名称、描述、参数的 JSON Schema
2. 模型根据用户问题判断是否需要工具，需要时返回“工具调用请求”（工具名 + 参数 JSON），而不是最终回答
3. 应用方（不是模型）真正执行工具：调接口、查数据库、操作页面
4. 把工具执行结果作为一条新消息发回给模型
5. 模型根据结果继续推理，可能再次调用工具，最终给出自然语言回答
```

关键认知：**模型只负责决定调用什么、参数是什么，执行永远在你的代码里**，因此权限控制、参数校验、危险操作确认都由应用负责。

**前端落地场景：**

- **服务端工具**：查订单、搜索知识库，在 BFF 执行；
- **客户端工具**：操作当前页面，比如“帮我把表格按日期排序”，模型返回 `sortTable({ column: 'date' })`，前端执行；
- **生成式 UI**：工具调用的结果渲染成组件（天气卡片、订单卡片），而不是纯文本；
- **人在回路**：敏感操作（下单、删除）前展示确认按钮，用户确认后再执行。

### 代码示例

```js
// 工具定义：结构是各家通用的思路，具体字段名以所用模型 API 官方文档为准
const tools = [
  {
    name: 'get_order_status',
    description: '根据订单号查询订单状态',
    input_schema: {
      type: 'object',
      properties: { orderId: { type: 'string', description: '订单号，如 SO20260101001' } },
      required: ['orderId'],
    },
  },
];

// 工具实现表：key 是工具名，value 是执行函数
const toolImpls = {
  get_order_status: async ({ orderId }) => {
    if (!/^SO\d+$/.test(orderId)) throw new Error('订单号格式错误'); // 模型给的参数不可信，必须校验
    return orderService.getStatus(orderId, currentUser);              // 用当前用户权限执行，不能越权
  },
};

/**
 * 工具调用循环：直到模型不再请求工具为止。
 * callModel 是对具体模型 API 的封装，返回 { text, toolCalls: [{ id, name, args }] }。
 */
async function runAgent(messages, maxSteps = 5) {
  for (let step = 0; step < maxSteps; step++) {          // 限制最大轮数，防止死循环和成本失控
    const reply = await callModel({ messages, tools });
    messages.push(reply.assistantMessage);
    if (!reply.toolCalls.length) return reply.text;      // 没有工具调用，得到最终回答
    for (const call of reply.toolCalls) {
      let result;
      try {
        result = await toolImpls[call.name](call.args);
      } catch (e) {
        result = { error: e.message };                   // 错误也回传给模型，让它自行调整
      }
      messages.push({ role: 'tool', toolCallId: call.id, content: JSON.stringify(result) });
    }
  }
  throw new Error('超过最大工具调用轮数');
}
```

### 面试答题要点

1. Function Calling 是模型返回结构化的“调用请求”，由应用执行并把结果回传，模型基于结果继续回答。
2. 工具用 JSON Schema 描述参数，描述写清楚有助于模型正确选择工具。
3. 安全：模型给的参数不可信，要校验；用当前用户权限执行；敏感操作需要用户确认。
4. 循环要有最大轮数限制，工具错误回传给模型。
5. 前端落地：客户端工具操作页面、生成式 UI、人在回路确认。

### 易错点 / 追问

- **易错：** 以为模型会自己执行函数或者访问你的数据库。
- **追问：流式输出时怎么处理工具调用？** 工具调用的参数 JSON 也是分片到达的，要累积到完整后再解析执行；界面上可以显示“正在查询订单……”的状态。

---

## 19. Agent 与 MCP ★★

### 是什么 / 原理

**Agent**：让模型在循环中自主规划和执行多步任务：观察 → 思考 → 调用工具 → 观察结果 → ……，直到完成目标。上一节的工具调用循环就是最简单的 Agent。常见范式：ReAct（推理和行动交替）、Plan-and-Execute（先规划再执行）、Reflection（自我检查和修正）。

**MCP（Model Context Protocol）**：Anthropic 在 2024 年 11 月发布的开放协议，目的是**标准化 AI 应用和外部工具/数据源的连接方式**。可以类比成“AI 应用的 USB-C 接口”：

- 以前每个 AI 应用要为每个工具单独写集成（M 个应用 × N 个工具）；
- 有了 MCP，工具方实现一次 MCP Server，所有支持 MCP 的客户端（Claude Desktop、Claude Code、Cursor、VS Code 等）都能使用（M + N）。

核心概念：

| 概念 | 说明 |
|---|---|
| Host | 用户使用的 AI 应用（如 IDE、聊天客户端） |
| Client | Host 内部负责和某个 Server 保持连接的组件，一对一 |
| Server | 对外提供能力的服务 |
| Tools | Server 暴露的可调用函数（模型决定调用） |
| Resources | Server 暴露的数据（文件、数据库记录），供应用读取作为上下文 |
| Prompts | Server 提供的提示词模板（通常由用户选择使用） |
| 传输 | 基于 JSON-RPC 2.0；本地用 stdio，远程用 Streamable HTTP（早期版本是 HTTP + SSE） |

### 代码示例：最小 MCP Server（TypeScript SDK）

```ts
// 以 @modelcontextprotocol/sdk 官方文档为准，不同版本 API 可能有调整
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';

const server = new McpServer({ name: 'design-tokens', version: '1.0.0' });

// 暴露一个工具：查询设计令牌，前端团队可以让 AI 编程助手按规范写样式
server.tool('get_token', { name: z.string().describe('令牌名，如 colorPrimary') }, async ({ name }) => ({
  content: [{ type: 'text', text: JSON.stringify({ name, value: tokens[name] ?? null }) }],
}));

await server.connect(new StdioServerTransport());
```

**前端如何接入 MCP：**

1. **作为 Server 提供方**：把团队的组件库文档、设计令牌、接口文档、埋点规范做成 MCP Server，让 AI 编程助手生成符合规范的代码。
2. **在自己的 AI 产品中做 Client**：BFF 作为 MCP Client 连接各种 MCP Server，把它们的工具交给模型使用；浏览器通常不直接连接 MCP Server（凭证安全、跨域）。
3. **浏览器自动化**：通过 Playwright MCP 等让 Agent 操作浏览器做测试。

### 面试答题要点

1. Agent = 模型 + 工具 + 循环（观察、思考、行动），需要最大步数、成本控制和人在回路。
2. MCP 标准化 AI 应用与工具/数据源的连接，把 M×N 的集成变成 M+N。
3. 三类能力：Tools（模型调用）、Resources（数据上下文）、Prompts（模板）；基于 JSON-RPC，本地 stdio、远程 Streamable HTTP。
4. MCP 和 Function Calling 的关系：Function Calling 是模型层“如何调用工具”的能力；MCP 是应用层“工具如何被发现和连接”的协议，MCP 的工具最终也通过 Function Calling 交给模型。
5. 安全：MCP Server 能执行真实操作，要做权限最小化，警惕第三方 Server 和提示注入。

### 易错点 / 追问

- **追问：什么是提示注入（Prompt Injection）？** 工具返回的内容（网页、文档、邮件）里藏着指令，诱导模型执行非预期操作。防御：工具结果当作数据而非指令、敏感操作需人工确认、权限最小化。
- **易错：** 把 MCP 说成某个模型独有的功能。它是开放协议，多家厂商和工具都已支持。

---

## 20. AI SDK、AI 辅助编程与 Token 成本 ★★

### 是什么 / 原理

**AI SDK（以 Vercel AI SDK 为例）**：TypeScript 工具包，统一封装多个模型厂商的接口，提供：

- 服务端：`streamText`、`generateText`、`generateObject`（结构化输出）、工具调用等；
- 前端：React/Vue/Svelte 的 hooks（如 `useChat`），处理消息状态、流式更新、停止生成；
- 好处：切换模型厂商只需换 provider，不用重写流式解析。

AI SDK 的大版本之间 API 变化较大（例如 `useChat` 的参数和消息结构在新版本中有调整），**具体用法以官方文档为准**，面试中讲清楚它解决什么问题即可。

**AI 辅助编程工作流（Cursor、Claude Code、Copilot 等）**：面试官想听的是你如何**保证质量**：

1. **明确任务和上下文**：给清楚需求、约束、相关文件；项目里维护规则文件（如 `CLAUDE.md`、`.cursor/rules`）沉淀规范；
2. **小步迭代**：先让 AI 给方案再写代码，大任务拆成可验证的小步；
3. **验证**：AI 生成的代码必须跑测试、类型检查、lint，关键逻辑先写测试；
4. **审查**：像审查同事代码一样逐行看 diff，重点关注边界条件、错误处理、安全（注入、越权）、是否引入不必要的依赖、是否编造了不存在的 API；
5. **责任归属**：代码由提交者负责，不能以“AI 写的”为理由。

**Prompt 与上下文管理：**

- 清晰的角色、任务、约束、输出格式；给示例（few-shot）；
- 结构化输出用 JSON Schema 约束，前端再用 zod 等校验；
- 上下文窗口有限：长对话要做截断、摘要或检索（RAG），只放相关内容。

**Token 成本意识：**

- 成本 = 输入 Token × 单价 + 输出 Token × 单价，输出单价通常高于输入；
- 多轮对话每次都要带上历史，输入 Token 随轮数增长；
- 优化：截断/摘要历史、利用模型厂商的提示缓存（Prompt Caching，具体规则以厂商文档为准）、按任务难度选择模型（简单任务用小模型）、限制最大输出长度、用户停止时服务端及时中止；
- 产品层面：按用户限流、展示用量、监控成本异常。

### 代码示例

```ts
// 结构化输出的前端校验：模型返回的 JSON 不可信，必须校验
import { z } from 'zod';

const ProductSummary = z.object({
  title: z.string().max(50),
  tags: z.array(z.string()).max(5),
  sentiment: z.enum(['positive', 'neutral', 'negative']),
});

function parseModelOutput(text: string) {
  const result = ProductSummary.safeParse(JSON.parse(text));
  if (!result.success) throw new Error('模型输出不符合预期结构'); // 可以选择重试或降级
  return result.data;
}
```

### 面试答题要点

1. AI SDK 统一多厂商接口并提供流式 hooks，具体 API 以官方文档为准。
2. AI 辅助编程：给好上下文、小步迭代、必须测试和审查、提交者负责。
3. 审查 AI 代码的重点：边界、错误处理、安全、编造的 API、多余依赖。
4. Token 成本：历史截断/摘要、提示缓存、模型分级、限制输出、及时中止。
5. 模型结构化输出要用 schema 校验。

### 易错点 / 追问

- **追问：你怎么用 AI 提效？** 要有具体例子和数据：比如用 AI 生成单测覆盖率从 X 提升到 Y、用规则文件让生成代码符合团队规范、哪些场景你不用 AI（核心安全逻辑）。
- **易错：** 只说“AI 很好用”，说不出质量把关方法。

---

## 21. 端侧推理（加分项）★

### 是什么 / 原理

在浏览器里直接运行模型，不经过服务器。

| 方案 | 说明 |
|---|---|
| WebGPU | 浏览器的新一代 GPU API，支持通用计算（compute shader），是浏览器端运行大模型的基础。Chrome 113 起默认开启，其他浏览器支持情况以 MDN / caniuse 为准 |
| WebAssembly（+ SIMD、多线程） | 没有 WebGPU 时的 CPU 方案，速度较慢 |
| Transformers.js | Hugging Face 的 JS 库，在浏览器运行 Transformers 模型（文本分类、翻译、嵌入、语音识别等），底层用 ONNX Runtime Web，支持 WebGPU / Wasm 后端 |
| WebLLM（MLC） | 在浏览器中用 WebGPU 运行量化后的大语言模型，提供类 OpenAI 的接口 |
| 浏览器内置 AI | Chrome 在实验内置模型 API（如 Prompt API、Summarizer API 等），可用性和 API 形态以 Chrome 官方文档为准 |

**优点**：隐私（数据不出设备）、离线可用、无服务端推理成本、低延迟（无网络往返）。
**缺点**：模型文件大（几百 MB 到几 GB）、首次下载慢、设备性能差异大、只能跑小模型、移动端发热耗电。

**适用场景**：隐私敏感的文本处理、实时语音转文字、图片背景移除、语义搜索（本地嵌入）、离线翻译；复杂推理仍然走云端。常见方案是**端云结合**：简单任务端侧处理，复杂任务降级到云端。

### 代码示例

```js
// Transformers.js 示例：以官方文档为准，包名和参数在不同版本可能有变化
import { pipeline } from '@huggingface/transformers';

// 首次调用会下载模型并缓存（浏览器 Cache Storage），之后离线可用
const classifier = await pipeline('sentiment-analysis', 'Xenova/distilbert-base-uncased-finetuned-sst-2-english', {
  device: 'webgpu', // 不支持 WebGPU 时可去掉，使用默认 Wasm 后端
});
const result = await classifier('I love this product!');
// 结果形如 [{ label: 'POSITIVE', score: 0.99 }]
```

```js
// 能力检测与降级
async function pickBackend() {
  if ('gpu' in navigator) {
    const adapter = await navigator.gpu.requestAdapter();
    if (adapter) return 'webgpu';
  }
  return 'wasm'; // 或者直接降级为调用云端接口
}
```

工程化要点：模型推理放在 **Web Worker** 中，避免阻塞主线程；模型文件用 Cache Storage / OPFS 缓存；显示下载进度；先做能力检测再决定端侧还是云端。

### 面试答题要点

1. 端侧推理基于 WebGPU（GPU 计算）或 Wasm（CPU），代表库 Transformers.js、WebLLM。
2. 优点：隐私、离线、零服务端成本、低延迟；缺点：模型大、设备差异、只能跑小模型。
3. 工程上：Worker 中推理、缓存模型文件、能力检测、端云结合降级。
4. 典型场景：嵌入向量、分类、语音识别、图像处理等小模型任务。

### 易错点 / 追问

- **追问：WebGPU 和 WebGL 的区别？** WebGL 主要为图形渲染设计，做通用计算要“伪装成”纹理绘制；WebGPU 原生支持计算着色器，更适合机器学习，性能和易用性更好。
- **易错：** 声称浏览器能流畅运行几十 B 参数的大模型。受显存和下载体积限制，浏览器端实际一般用几 B 以内的量化模型。
