# 前端面试知识点详解 01：HTML + CSS

> 对应总大纲 [第 1 节 HTML ★★ / 第 2 节 CSS ★★★](../frontend-interview-outline.md)。
> 星级：★★★ 必考 / ★★ 常考 / ★ 加分项。
> 每个知识点结构：**是什么 / 原理** → **代码示例** → **面试答题要点** → **易错点 / 追问**。
> 浏览器支持状态截至 2026 年，只是大致情况，上线前以 [caniuse](https://caniuse.com) 和 MDN Baseline 为准。

---

## 目录

- [一、HTML ★★](#一html-)
  - [1.1 语义化 ★★](#11-语义化-)
  - [1.2 文档解析与 script 的 defer / async / module ★★★](#12-文档解析与-script-的-defer--async--module-)
  - [1.3 资源提示：preload / prefetch / preconnect / dns-prefetch ★★](#13-资源提示preload--prefetch--preconnect--dns-prefetch-)
  - [1.4 表单与原生交互组件：校验、dialog、details、inputmode、popover ★★](#14-表单与原生交互组件校验dialogdetailsinputmodepopover-)
  - [1.5 可访问性（a11y） ★★](#15-可访问性a11y-)
  - [1.6 Web Components ★](#16-web-components-)
  - [1.7 补充考点：DOCTYPE、viewport、响应式图片 ★](#17-补充考点doctypeviewport响应式图片-)
- [二、CSS ★★★](#二css-)
  - [2.1 盒模型与 box-sizing ★★★](#21-盒模型与-box-sizing-)
  - [2.2 BFC 与 margin 塌陷 ★★★](#22-bfc-与-margin-塌陷-)
  - [2.3 选择器优先级与层叠：@layer、:is / :where / :has ★★★](#23-选择器优先级与层叠layeriswherehas-)
  - [2.4 Flex 布局 ★★★](#24-flex-布局-)
  - [2.5 Grid 布局 ★★](#25-grid-布局-)
  - [2.6 定位：position 与 sticky 失效 ★★★](#26-定位position-与-sticky-失效-)
  - [2.7 层叠上下文与 z-index ★★★](#27-层叠上下文与-z-index-)
  - [2.8 响应式：媒体查询、容器查询、clamp、视口单位 ★★](#28-响应式媒体查询容器查询clamp视口单位-)
  - [2.9 现代 CSS 特性 ★](#29-现代-css-特性-)
  - [2.10 渲染与动画性能 ★★★](#210-渲染与动画性能-)
  - [2.11 工程方案：CSS Modules / Tailwind / CSS-in-JS ★★](#211-工程方案css-modules--tailwind--css-in-js-)
- [三、高频题完整参考答案](#三高频题完整参考答案)
  - [3.1 水平垂直居中 N 种方法 ★★★](#31-水平垂直居中-n-种方法-)
  - [3.2 1px 问题 ★★](#32-1px-问题-)
  - [3.3 三栏布局 / 圣杯 / 双飞翼 ★★](#33-三栏布局--圣杯--双飞翼-)
  - [3.4 z-index 为什么不生效 ★★★](#34-z-index-为什么不生效-)
  - [3.5 其他常见小题 ★★](#35-其他常见小题-)
- [附：现代特性浏览器支持速查](#附现代特性浏览器支持速查)

---

## 一、HTML ★★

**侧重点**：语义化、可访问性、浏览器如何解析文档。

### 1.1 语义化 ★★

**是什么 / 原理**

用表达"内容是什么"的标签，而不是只用 `div`/`span` 加 class。常用的有：`header`、`nav`、`main`（每页一个）、`article`（能独立分发的内容）、`section`（有标题的主题分组）、`aside`、`footer`、`figure/figcaption`、`time`、`mark`、`address`。

语义有三个用处：
- **a11y**：读屏器根据标签生成"地标（landmark）"和大纲，用户可以直接跳到 `main`、`nav`。
- **SEO**：爬虫靠结构判断正文、标题层级和发布时间。
- **可维护性**：结构自己就能说明含义，减少 class 命名负担，代码也更好读。

```html
<body>
  <header>
    <nav aria-label="主导航"><a href="/">首页</a></nav>
  </header>
  <main>
    <article>
      <h1>文章标题</h1>
      <p>发布于 <time datetime="2026-11-26">11 月 26 日</time></p>
      <section><h2>第一节</h2>...</section>
    </article>
    <aside>相关推荐</aside>
  </main>
  <footer>© 2026</footer>
</body>
```

**面试答题要点**
1. 语义化就是"用正确的标签表达内容结构"，受益的是机器（读屏器、爬虫）和人（维护者）两方。
2. 读屏器把 `header/nav/main/footer` 映射成 banner/navigation/main/contentinfo 地标，可以快速跳转。
3. 标题层级 `h1~h6` 不要跳级，它决定文档大纲。
4. 能用原生元素就用原生：`<button>` 自带焦点、键盘 Enter/Space 和 role，`<div onclick>` 这些都没有。
5. `strong/em` 表示强调语义，`b/i` 只是样式。

**易错点 / 追问**
- `section` 和 `div` 的区别：`section` 应该有标题，表示一个主题分组；只是为了加样式就用 `div`。
- `article` 和 `section`：`article` 拿出来单独看也成立（博客、评论、卡片），`section` 是整体的一部分。
- 追问"语义化对 SEO 的作用到底多大"：现代搜索引擎会渲染 JS，影响已经变小，但 `title`、`meta description`、标题层级、`alt` 依然有用。

---

### 1.2 文档解析与 script 的 defer / async / module ★★★

**是什么 / 原理**

浏览器边下载 HTML 边构建 DOM。碰到普通 `<script>` 时，**HTML 解析会暂停**，先下载并执行脚本，因为脚本可能调用 `document.write` 或读取 DOM。CSS 不阻塞 DOM 解析，但会**阻塞渲染**，也会**阻塞它后面脚本的执行**，因为脚本可能读样式。预加载扫描器（preload scanner）会提前发现后续资源并开始下载，所以"下载"往往是并行的，阻塞的主要是"执行"。

| 写法 | 下载 | 执行时机 | 是否按顺序 | 阻塞解析 |
|---|---|---|---|---|
| `<script>` | 阻塞解析去下载 | 下载完立即执行 | 按文档顺序 | 是 |
| `<script defer>` | 并行 | HTML 解析完成后、`DOMContentLoaded` **之前** | 按文档顺序 | 否 |
| `<script async>` | 并行 | 下载完**立刻**执行（这时可能打断解析） | 不保证，谁先下载完谁先执行 | 执行时会暂停解析 |
| `<script type="module">` | 并行（连同依赖图） | 默认相当于 defer | 按顺序 | 否 |
| `<script type="module" async>` | 并行 | 模块图就绪后立即执行 | 不保证 | 执行时会暂停解析 |

```html
<!-- 依赖 DOM、相互有依赖：defer -->
<script defer src="vendor.js"></script>
<script defer src="app.js"></script>  <!-- 一定在 vendor.js 之后执行 -->

<!-- 独立的统计/广告脚本：async -->
<script async src="analytics.js"></script>

<!-- ESM：默认 defer、严格模式、模块作用域、跨域需要 CORS -->
<script type="module" src="main.js"></script>
<script nomodule src="legacy.js"></script> <!-- 旧浏览器回退 -->
```

**面试答题要点**
1. 普通脚本会阻塞 HTML 解析；`defer` 和 `async` 都是并行下载，区别在**执行时机和顺序**。
2. `defer`：解析完成后按顺序执行，在 `DOMContentLoaded` 之前，适合依赖 DOM 或彼此有依赖的业务脚本。
3. `async`：下载完立即执行，顺序不保证，可能早于也可能晚于 `DOMContentLoaded`，适合埋点这类独立脚本。
4. `type="module"` 默认按 defer 处理，自带严格模式和独立作用域，同一模块只执行一次，跨域加载需要 CORS。
5. CSS 阻塞渲染和后续脚本执行，所以通常 CSS 放 head、脚本加 defer。

**易错点 / 追问**
- 两个都写（`defer async`）时 async 优先，defer 只是给不支持 async 的旧浏览器兜底。
- 内联脚本（没有 `src`）加 `defer/async` **无效**；但内联 `type="module"` 依然是延迟执行的。
- 动态插入的 `<script>`（`document.createElement('script')`）默认就是 async，要设 `s.async = false` 才保证顺序。
- `DOMContentLoaded` 和 `load` 的区别：前者在 DOM 解析完、defer 脚本执行完后触发；后者还要等图片、样式等所有子资源加载完。
- 追问"script 放 body 底部和用 defer 有什么区别"：放底部时，下载要等解析到那里才开始；defer 能更早被发现、并行下载，通常更快。

---

### 1.3 资源提示：preload / prefetch / preconnect / dns-prefetch ★★

**是什么 / 原理**

都是通过 `<link rel>` 告诉浏览器"提前做某件事"：

| rel | 作用 | 优先级 / 场景 |
|---|---|---|
| `dns-prefetch` | 只提前做 DNS 解析 | 开销最小，适合多个第三方域名 |
| `preconnect` | DNS + TCP + TLS 握手全部提前 | 确定马上要用的关键跨域源（CDN、字体），别超过 3~4 个 |
| `preload` | **当前页面**一定会用的资源，高优先级提前下载，但不执行 | 首屏字体、首屏大图（LCP）、CSS 里才引用到的关键资源 |
| `prefetch` | **未来导航**可能用到的资源，空闲时低优先级下载 | 下一页的 chunk |
| `modulepreload` | 预加载 ESM 并解析依赖 | 关键模块 |

```html
<link rel="preconnect" href="https://cdn.example.com" crossorigin>
<link rel="dns-prefetch" href="https://stats.example.com">
<!-- 字体 preload 必须带 crossorigin，否则会下载两次 -->
<link rel="preload" href="/font.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/hero.webp" as="image" fetchpriority="high">
<link rel="prefetch" href="/next-page.js">
```

**面试答题要点**
1. 按"做得多少"递进：dns-prefetch < preconnect < preload（真正下载）。
2. preload 管当前页、优先级高；prefetch 管未来页、优先级低，下载结果放进 HTTP 缓存。
3. preload 必须写 `as`，否则优先级和 CSP 判断会出错，还可能重复下载；字体还必须加 `crossorigin`。
4. 滥用 preload 会抢占带宽，反而拖慢 LCP；页面加载后约 3 秒内没用到的 preload，Chrome 控制台会给警告。
5. 配合 `fetchpriority="high|low"` 微调优先级，常见用法是给 LCP 图片加 high。

**易错点 / 追问**
- 跨域资源 preconnect 时要不要带 `crossorigin`，取决于后续请求的 CORS 模式（字体、ESM 需要带），模式不一致就会再建一条连接。
- 追问 Speculation Rules API（`<script type="speculationrules">`）：用来预取或**预渲染**整页，Chromium 支持，其他浏览器以 caniuse 为准。

---

### 1.4 表单与原生交互组件：校验、dialog、details、inputmode、popover ★★

**是什么 / 原理**

**原生校验**：`required`、`pattern`、`min/max`、`minlength`、`type="email|url|number"`。提交时由浏览器校验，未通过会触发 `invalid` 事件。JS 侧可用 Constraint Validation API：`checkValidity()`、`reportValidity()`、`setCustomValidity(msg)`、`el.validity.valueMissing` 等。

```html
<form id="f">
  <input name="email" type="email" required>
  <input name="code" inputmode="numeric" pattern="\d{6}" autocomplete="one-time-code">
  <button>提交</button>
</form>
<style>
  /* :invalid 页面一打开就会命中；:user-invalid 要等用户交互后才命中，体验更好 */
  input:user-invalid { border-color: red; }
</style>
<script>
  const pwd2 = document.querySelector('#pwd2');
  pwd2.addEventListener('input', () => {
    pwd2.setCustomValidity(pwd2.value === pwd1.value ? '' : '两次密码不一致'); // 空串表示校验通过
  });
</script>
```

**`<dialog>`**：原生对话框。`showModal()` 打开模态框，自动进入顶层（top layer），不受 z-index 和父级 overflow 影响，自带 `::backdrop`、Esc 关闭、焦点困在对话框内、背景 inert；`show()` 打开非模态。`<form method="dialog">` 提交后会关闭对话框，`returnValue` 是被点击按钮的 value。

```html
<dialog id="dlg">
  <form method="dialog">
    <p>确认删除？</p>
    <button value="cancel">取消</button>
    <button value="ok">确定</button>
  </form>
</dialog>
<script>
  dlg.showModal();
  dlg.addEventListener('close', () => console.log(dlg.returnValue)); // 'ok' | 'cancel'
</script>
```

**`<details>/<summary>`**：原生折叠面板，不写 JS 就能展开收起，键盘和读屏器都支持。多个 `details` 写同一个 `name` 属性就成了互斥手风琴（较新特性，主流浏览器均已支持，以 caniuse 为准）。

**`inputmode`**：只决定移动端弹出**哪种虚拟键盘**（`numeric`、`decimal`、`tel`、`email`、`url`、`search`），不做校验。和 `type="number"` 的区别是后者会带来步进按钮、滚轮改值、前导 0 丢失等副作用，所以验证码、卡号更适合用 `type="text" inputmode="numeric"`。

**Popover API**（补充）：`<div popover id="p">` 加 `<button popovertarget="p">`，零 JS 实现浮层，进入顶层，点外部或按 Esc 会轻关闭（light dismiss）。2024 年起主流浏览器都已支持。

**面试答题要点**
1. 原生校验 + Constraint Validation API 已经能覆盖大部分场景，自定义规则用 `setCustomValidity`。
2. `:user-invalid` 解决了 `:invalid` 一进页面就标红的问题。
3. `dialog.showModal()` 直接带来顶层、遮罩、焦点管理、Esc 关闭，比自己写 Modal 更完整、无障碍更好。
4. `inputmode` 只管键盘类型，`type` 管语义和校验，两者可以组合使用。
5. 原生组件（dialog、details、popover）的价值在于免费获得键盘交互和 a11y。

**易错点 / 追问**
- `novalidate` 能关掉浏览器自带校验，交给 JS 处理，但 API 仍然可用。
- 用 `display` 控制 dialog 显示会破坏它的状态，应该用 `open` 属性或方法来控制。
- dialog 的打开/关闭动画需要 `@starting-style` 配合 `transition-behavior: allow-discrete`（较新，以 caniuse 为准）。

---

### 1.5 可访问性（a11y） ★★

**是什么 / 原理**

浏览器根据 DOM 生成**无障碍树（Accessibility Tree）**，每个节点有 role（角色）、name（可访问名称）、state（状态，比如 expanded、checked），读屏器读的是这棵树。ARIA 的作用是**补充或修正**这棵树上的语义，它**不改变行为**：加上 `role="button"` 不会让元素自动响应键盘。

ARIA 第一原则：**能用原生元素就不要用 ARIA**（No ARIA is better than bad ARIA）。

关键点：
- **alt**：内容图片写描述，装饰图片写 `alt=""`（读屏器会跳过），不能省略 alt 属性（否则会读出文件名）。
- **可访问名称**：`<label for>`、`aria-label`、`aria-labelledby`；只有图标的按钮必须提供名称。
- **焦点管理**：`tabindex="0"` 让元素进入 Tab 序列，`tabindex="-1"` 表示只能通过 JS 聚焦，**避免使用正数 tabindex**；打开弹窗时焦点移进去，关闭后还给触发按钮；用 `:focus-visible` 给键盘用户显示焦点环。
- **键盘可操作**：所有鼠标能做的操作，键盘也要能做。
- `inert` 属性：让一整块区域不可聚焦、不可交互（2023 年起已是 Baseline）。
- 颜色对比度：WCAG AA 要求正文至少 4.5:1。

**高频题：如何让一个自定义下拉框可被读屏器识别？**

参考答案：
1. **首选原生**：`<select>` 本身就是无障碍的；新的可定制 select（`appearance: base-select`）可以完全自定义样式，目前主要是 Chromium 支持，以 caniuse 为准。
2. 必须自定义时，按 WAI-ARIA APG 的 **Combobox / Listbox 模式**来做：
   - 触发器：`role="combobox"`（或一个 `<button>`），加上 `aria-haspopup="listbox"`、`aria-expanded`、`aria-controls` 指向列表。
   - 列表：`role="listbox"`，选项用 `role="option"` 加 `aria-selected`。
   - 当前高亮项：焦点留在触发器上，用 `aria-activedescendant` 指向高亮选项的 id；或者用 roving tabindex 让焦点真正移动。
   - 名称：`aria-labelledby` 关联 label。
3. **键盘交互**：↑/↓ 移动，Enter/Space 选中，Esc 关闭并把焦点还给触发器，Home/End 跳到首尾，输入字符跳到匹配项。
4. **状态同步**：展开/收起时更新 `aria-expanded`，选中时更新 `aria-selected` 和触发器显示的文本。
5. **验证**：用 VoiceOver、NVDA 实际读一遍，再用 Chrome DevTools 的 Accessibility 面板和 axe 检查。

```html
<label id="lb">城市</label>
<button role="combobox" aria-labelledby="lb" aria-haspopup="listbox"
        aria-expanded="true" aria-controls="lst" aria-activedescendant="opt-2">上海</button>
<ul role="listbox" id="lst" aria-labelledby="lb">
  <li role="option" id="opt-1" aria-selected="false">北京</li>
  <li role="option" id="opt-2" aria-selected="true">上海</li>
</ul>
```

**面试答题要点**
1. 读屏器读的是无障碍树，三要素是 role、name、state。
2. ARIA 只改语义、不改行为，键盘交互必须自己实现；优先使用原生元素。
3. 焦点管理：弹层打开时移入焦点，关闭时归还，模态框内锁住焦点（或者直接用 `dialog`、`inert`）。
4. 只有图标的按钮要给 `aria-label`，装饰图片写 `alt=""`。
5. 动态内容通知用 `aria-live="polite"`（比如 toast、表单错误）。

**易错点 / 追问**
- `aria-hidden="true"` 放在可聚焦元素上，会出现"能聚焦但读不出来"的问题。
- 用 `display:none` 或 `visibility:hidden` 隐藏的内容读屏器读不到；"视觉隐藏但能读"要用 `.sr-only`（clip + 1px 尺寸）。
- `outline: none` 去掉焦点环却不提供替代样式，是常见的无障碍违规。

---

### 1.6 Web Components ★

**是什么 / 原理**

一组浏览器原生的组件化标准：
- **Custom Elements**：`customElements.define('my-el', class extends HTMLElement {})`，标签名必须带连字符。生命周期有 `connectedCallback`、`disconnectedCallback`、`attributeChangedCallback`（需要配合 `static observedAttributes`）、`adoptedCallback`。
- **Shadow DOM**：`attachShadow({ mode: 'open' })` 创建封装的 DOM 子树，**样式双向隔离**（外部选择器进不来，内部样式出不去）。
- **`<template>`**：不渲染的惰性 DOM 片段，克隆后使用。
- **`<slot>`**：把宿主元素的子节点（light DOM）投影到 shadow 树里，支持具名插槽。

```js
const tpl = document.createElement('template');
tpl.innerHTML = `
  <style>:host{display:inline-block} ::slotted(span){color:red} .t{font-weight:bold}</style>
  <div class="t"><slot name="title">默认标题</slot></div>
  <slot></slot>`;

class MyCard extends HTMLElement {
  static observedAttributes = ['theme'];
  constructor() {
    super();
    this.attachShadow({ mode: 'open' }).appendChild(tpl.content.cloneNode(true));
  }
  attributeChangedCallback(name, oldV, newV) { /* theme 变化时更新样式 */ }
}
customElements.define('my-card', MyCard);
// 使用：<my-card theme="dark"><span slot="title">标题</span>正文</my-card>
```

**面试答题要点**
1. 四件套：Custom Elements（定义标签）、Shadow DOM（封装）、template（模板）、slot（内容分发）。
2. Shadow DOM 隔离样式，但 **CSS 变量和可继承属性（color、font）能穿透**，所以主题定制一般通过 CSS 变量 + `::part()` 暴露。
3. 适合跨框架的设计系统、微前端、嵌入第三方页面的组件。
4. 缺点：SSR 需要 Declarative Shadow DOM（`<template shadowrootmode="open">`，2024 年起主流浏览器已支持）；表单参与需要 `ElementInternals`；属性只能传字符串，复杂数据要靠 property。
5. React 19 已经能正确处理 custom element 的 property 和事件。

**易错点 / 追问**
- 事件冒泡跨越 shadow 边界时会被 **retarget**（外面看到的 target 是宿主元素），自定义事件要设 `composed: true` 才能穿出 shadow。
- `mode: 'closed'` 只是不暴露 `shadowRoot` 引用，并不是真正的安全边界。

---

### 1.7 补充考点：DOCTYPE、viewport、响应式图片 ★

- **DOCTYPE**：`<!DOCTYPE html>` 让浏览器进入**标准模式**；缺了它会进入怪异模式（Quirks），盒模型等行为按旧 IE 处理。
- **viewport**：`<meta name="viewport" content="width=device-width, initial-scale=1">`，没有它的话移动端会按 980px 宽渲染再缩小。可加 `viewport-fit=cover` 配合 `env(safe-area-inset-*)` 适配刘海屏。
- **响应式图片**：`srcset` + `sizes` 让浏览器按 DPR 和布局宽度挑图；`<picture><source type="image/avif">` 做格式回退和艺术指导；`loading="lazy"` 原生懒加载（**首屏 LCP 图不要加**）；写上 `width/height` 或用 `aspect-ratio` 预留空间，避免 CLS。
- **src 与 href**：`src` 是把资源嵌入当前位置（script、img 会阻塞或替换内容）；`href` 是建立与外部资源的关系（link、a）。

---

## 二、CSS ★★★

**侧重点**：布局能力、层叠与优先级、渲染性能。

### 2.1 盒模型与 box-sizing ★★★

**是什么 / 原理**

每个元素都是一个矩形盒子，从内到外依次是 content → padding → border → margin。

- `box-sizing: content-box`（默认，标准盒模型）：`width` 只算 content。总宽 = width + padding + border。
- `box-sizing: border-box`（IE / 怪异盒模型）：`width` 包含 content + padding + border，padding 变大时内容区会被压缩。

```css
/* 业界通用重置：让 padding 和 border 不再把盒子撑大 */
*, *::before, *::after { box-sizing: border-box; }

.a { width: 100px; padding: 10px; border: 5px solid; }
/* content-box: 占 130px；border-box: 占 100px，content 只有 70px */
```

**面试答题要点**
1. 盒模型四层：content、padding、border、margin；margin 不算进 box-sizing 的范围。
2. 标准盒模型 width 只算内容；border-box 的 width 包含 padding 和 border，布局更直观，是项目的默认首选。
3. JS 读取尺寸：`offsetWidth` = content + padding + border；`clientWidth` = content + padding（不含滚动条）；`getBoundingClientRect()` 返回包含 transform 后的实际渲染尺寸，可能是小数。
4. 行内非替换元素（span）的 width/height 无效，垂直方向的 padding/margin 不影响行高布局（padding 有视觉效果但不占位）。

**易错点 / 追问**
- `margin/padding` 写百分比时，**上下方向也是相对包含块的宽度**计算的，这是 padding-top 实现等比例盒子的经典技巧，现在可以直接用 `aspect-ratio`。
- 追问"怎么让 width:100% 的 input 加 padding 后不溢出"：用 border-box。

---

### 2.2 BFC 与 margin 塌陷 ★★★

**是什么 / 原理**

**BFC（Block Formatting Context，块级格式化上下文）**是一块独立的渲染区域：内部元素的布局不影响外部，外部也不影响内部。

**BFC 的规则**
1. 内部块级盒子在垂直方向上依次排列；
2. **同一个 BFC 内**相邻块级盒子的垂直 margin 会合并（塌陷）；
3. BFC 区域**不会和浮动元素重叠**；
4. 计算 BFC 高度时，**浮动子元素也参与计算**。

**触发方式**
- 根元素 `<html>`；
- `float` 不为 none；
- `position: absolute | fixed`；
- `display: inline-block | table-cell | flex/grid 的子项 | flow-root`；
- `overflow` 不为 visible / clip（hidden、auto、scroll）；
- `contain: layout | content | paint`；多列容器 `column-count`。

**推荐 `display: flow-root`**：专门用来创建 BFC，没有任何副作用（overflow:hidden 会裁剪阴影和下拉菜单）。

**用途与代码**

```css
/* 1. 清除浮动（解决父元素高度塌陷） */
.parent { display: flow-root; }   /* 或 overflow: hidden */
/* 传统写法：clearfix */
.clearfix::after { content: ''; display: block; clear: both; }

/* 2. 防止 margin 合并：把其中一个包进新的 BFC */
.wrap { display: flow-root; }     /* <div class="wrap"><p>...</p></div> */

/* 3. 两栏自适应：左侧浮动，右侧 BFC 不与浮动重叠 */
.left  { float: left; width: 200px; }
.right { overflow: hidden; }      /* 右侧自动占满剩余宽度 */
```

**margin 塌陷的三种情况**
1. **相邻兄弟**：上 20px、下 30px，实际间距 30px（取较大值；一正一负时相加；都是负值取绝对值大的）。
2. **父子**：父元素没有 border、padding、inline 内容、BFC 来隔开时，子元素的 margin-top 会"穿出"父元素，变成父元素的 margin。
3. **空块元素**：自身的上下 margin 合并。

解决父子塌陷：父元素加 `padding/border`、父元素创建 BFC（`flow-root`）、或者改用 flex/grid（**flex/grid 子项之间不发生 margin 合并**）。

**面试答题要点**
1. 定义：BFC 是独立的块级渲染区域，内外布局互不影响。
2. 规则：垂直排列、同一 BFC 内 margin 合并、不与浮动重叠、高度计算包含浮动。
3. 触发：float、absolute/fixed、overflow 非 visible、inline-block、flex/grid 子项、`display: flow-root`（推荐）。
4. 三大用途：清浮动、防止 margin 塌陷、配合浮动做自适应两栏。
5. 还可以顺带提 IFC（行内格式化上下文）、FFC/GFC（flex/grid 格式化上下文）。

**易错点 / 追问**
- 只有**垂直方向**会发生 margin 合并，水平方向不会；flex/grid 容器里也不会。
- 同一 BFC 内才合并，所以"创建新 BFC"必须**包住**其中一个元素。很多人答错的一点：给兄弟元素各自设 overflow:hidden 只是让它们**内部**成为 BFC，它们本身仍然在父级的同一个 BFC 里，彼此之间的 margin 照样合并。
- `overflow: clip` 不创建 BFC，这是它和 hidden 的区别之一。

---

### 2.3 选择器优先级与层叠：@layer、:is / :where / :has ★★★

**是什么 / 原理**

**层叠（Cascade）的判定顺序**（从高到低，前一项决胜就不再往下比）：
1. **来源与重要性**：transition 声明 > 用户代理 `!important` > 用户 `!important` > 作者 `!important` > 动画声明（@keyframes）> 作者普通声明 > 用户普通声明 > 用户代理普通声明；
2. **上下文**（Shadow DOM 内外）；
3. **元素内联 style**；
4. **层（@layer）**；
5. **优先级（Specificity）**；
6. **出现顺序**：后写的覆盖先写的。

**优先级计算**：用 (a, b, c) 三元组比较，逐位比较、**不进位**：
- a：ID 选择器个数；
- b：类、属性、伪类个数；
- c：元素、伪元素个数；
- 通配符 `*`、组合符（`>` `+` `~` 空格）、`:where()` 都记 0；
- 内联样式高于任何选择器，`!important` 高于内联样式。

```css
#nav .item a:hover   /* (1, 2, 1) */
.list > li.active    /* (0, 2, 1) */
:is(#a, .b) span     /* (1, 0, 1)：:is 取参数中最高的优先级 */
:where(#a, .b) span  /* (0, 0, 1)：:where 优先级恒为 0 */
:not(.x) / :has(.x)  /* 和 :is 一样，取参数中最高的优先级 */
```

**@layer 层叠层**（2022 年起主流浏览器已支持，Baseline）：
- 层的先后顺序由**第一次声明**决定，**后声明的层优先级更高**；
- **不在任何层里的样式优先级最高**（普通声明的情况下）；
- 对 `!important` 来说层序**反转**：越早声明的层，其 important 越强。
- 用途：让第三方库或 reset 样式进低层，业务样式不用再拼优先级、堆 `!important`。

```css
@layer reset, vendor, components, utilities;  /* 先定好顺序 */
@import url('antd.css') layer(vendor);
@layer reset { * { margin: 0 } }
@layer components { .btn { color: blue } }
@layer utilities { .text-red { color: red } } /* 选择器再弱，也能盖过 components 层 */
.btn { color: green }  /* 未分层的样式，覆盖所有层里的普通声明 */
```

**`:is()` / `:where()`**：都是把选择器列表合并起来写，区别只在优先级：`:is` 取参数中最高的，`:where` 恒为 0，适合写**易于覆盖的基础样式**。两者都是**宽容的选择器列表**，其中某一项无效不会导致整条规则失效。

**`:has()` 关系伪类**（"父选择器"，2023 年起主流浏览器均已支持）：根据后代或后续兄弟的状态选中元素本身。

```css
.card:has(img) { padding: 0; }                    /* 包含图片的卡片 */
form:has(input:user-invalid) .submit { opacity: .5; }  /* 表单有错误时把按钮变淡 */
h2:has(+ p) { margin-bottom: 0; }                 /* 后面紧跟 p 的 h2 */
html:has(dialog[open]) { overflow: hidden; }      /* 弹窗打开时锁定滚动 */
```

**面试答题要点**
1. 层叠判定顺序：重要性/来源 → 内联 → 层 → 优先级 → 出现顺序。
2. 优先级按 ID / 类 / 元素三元组逐位比较、不进位，11 个类也比不过 1 个 ID。
3. `@layer` 把"靠优先级打架"变成"靠层序管理"，未分层的样式最高，important 层序反转。
4. `:is` 取最高优先级，`:where` 为 0；`:has` 实现父选择器和前置兄弟选择。
5. 继承来的样式没有优先级，任何直接作用在元素上的规则都会覆盖继承值。

**易错点 / 追问**
- `:has()` 的性能：浏览器做了失效优化，但避免写 `*:has(...)` 这类大范围匹配；`:has` 里面不能嵌套 `:has`。
- `!important` 无法被普通的高优先级规则覆盖，只能用另一个 `!important`（并且优先级更高或层序合适）。
- 追问"选择器为什么从右往左匹配"：先用最右边的关键选择器筛掉大部分元素，再向上验证祖先，比从左往右遍历子树更高效。

---

### 2.4 Flex 布局 ★★★

**是什么 / 原理**

一维布局模型，沿主轴（`flex-direction` 决定）排列子项。

- **容器属性**：`flex-direction`、`flex-wrap`、`justify-content`（主轴对齐）、`align-items`（交叉轴单行对齐）、`align-content`（多行之间的分布）、`gap`。
- **子项属性**：`flex-grow`、`flex-shrink`、`flex-basis`、`order`、`align-self`。

**`flex` 简写拆解（必考）**

| 写法 | 等价于 | 含义 |
|---|---|---|
| `flex: initial`（默认） | `0 1 auto` | 不放大，可缩小，按内容/width 定基础尺寸 |
| `flex: 1` | `1 1 0%` | 等分剩余空间（基础尺寸为 0） |
| `flex: auto` | `1 1 auto` | 在内容尺寸基础上再分配剩余空间，不严格等分 |
| `flex: none` | `0 0 auto` | 不伸不缩 |
| `flex: 2 200px` | `2 1 200px` | |

**剩余空间分配算法**
- 放大：剩余空间 = 容器尺寸 − 所有子项 basis 之和，按 grow 比例分配；
- 缩小：溢出量按 **shrink × basis** 的加权比例分摊（basis 越大，缩得越多）。

```css
/* 例：容器 600px，A basis 300 shrink 1，B basis 500 shrink 1 → 溢出 200 */
/* A 缩 200 × 300/(300+500) = 75 → 225px；B 缩 125 → 375px */
.layout { display: flex; gap: 16px; }
.side { flex: 0 0 200px; }
.main { flex: 1; min-width: 0; } /* min-width:0 防止长内容撑破布局 */
```

**面试答题要点**
1. `flex: 1` 是 `1 1 0%`，`flex: auto` 是 `1 1 auto`；前者按比例等分，后者先保留内容尺寸再分剩余空间。
2. 放大按 grow 比例分；缩小按 shrink × basis 加权分摊。
3. flex 子项的 `min-width` 默认是 `auto`（不小于内容最小宽度），所以长文本或长单词会撑破容器，需要设 `min-width: 0` 或 `overflow: hidden`。
4. `basis` 优先于 `width`，`auto` 时才去读 width。
5. 子项的 `float`、`vertical-align` 失效，子项之间 margin 不合并；`margin: auto` 能吃掉剩余空间，常用来把某一项推到最右边。

**易错点 / 追问**
- `align-items` 和 `align-content` 的区别：后者只在多行（`flex-wrap: wrap`）时生效。
- `flex-basis: 0` 和 `0%` 在某些嵌套场景表现不同（百分比依赖父级尺寸是否确定）。
- 追问"最后一行左对齐的网格怎么做"：flex 很麻烦（要补占位元素），直接用 Grid。

---

### 2.5 Grid 布局 ★★

**是什么 / 原理**

二维布局，同时控制行和列。

- `grid-template-columns/rows`：轨道定义；`fr` 表示按比例分配**剩余空间**；
- `minmax(min, max)`：轨道尺寸区间；
- `repeat(auto-fill | auto-fit, minmax(200px, 1fr))`：自动计算能放下多少列；
- `grid-template-areas`：用命名区域画布局；
- `grid-column: 1 / -1`：横跨所有列；`gap`；`grid-auto-flow: dense` 用来填补空洞；
- `subgrid`：子网格继承父网格的轨道（2023 年起已是 Baseline）。

**`auto-fill` vs `auto-fit`（必考）**：两者都会尽量多地创建列。区别只在**子项数量不够填满一行时**：
- `auto-fill`：保留空轨道，子项保持 max 尺寸，右边留空；
- `auto-fit`：把空轨道折叠为 0，现有子项被拉伸占满整行。

```css
.cards { display: grid; gap: 16px;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); } /* 不写媒体查询的响应式卡片 */

.page { display: grid; min-height: 100dvh;
  grid-template: "header header" auto
                 "side   main"   1fr
                 "footer footer" auto / 200px 1fr; }
.header { grid-area: header; }
```

**面试答题要点**
1. Flex 是一维、内容驱动；Grid 是二维、布局驱动，页面骨架用 Grid，组件内部排列用 Flex。
2. `fr` 分配的是去掉固定轨道和 gap 之后的剩余空间；`1fr` 实际上是 `minmax(auto, 1fr)`，会被长内容撑大，需要严格等分时写 `minmax(0, 1fr)`。
3. auto-fill 保留空列，auto-fit 折叠空列并拉伸现有项；只有子项少于一行时才看得出区别。
4. `grid-template-areas` 直观，配合媒体查询改 areas 就能完成响应式重排。
5. subgrid 解决"卡片之间标题、按钮对齐"这类跨组件对齐问题。

**易错点 / 追问**
- 用 `order` 或 grid 位置做视觉重排后，DOM 顺序和视觉顺序不一致，会影响键盘 Tab 顺序（a11y 问题）。
- 新兴的 Masonry（瀑布流）布局规范尚在演进中，语法和支持情况以 caniuse 为准。

---

### 2.6 定位：position 与 sticky 失效 ★★★

**是什么 / 原理**

| 值 | 是否脱离文档流 | 相对谁定位 |
|---|---|---|
| `static` | 否 | 不定位，top/left/z-index 无效 |
| `relative` | 否（原位置保留） | 自身原来的位置 |
| `absolute` | 是 | 最近的**非 static 祖先**的 padding box；找不到就相对初始包含块 |
| `fixed` | 是 | 视口；但祖先有 `transform/filter/perspective/contain/will-change: transform` 时改为相对该祖先 |
| `sticky` | 否 | 在最近的**滚动祖先**内，未达到阈值时表现为 relative，达到阈值后像 fixed 一样被"粘住"，且不会超出父元素范围 |

**sticky 失效的常见原因（高频）**
1. 没有设置阈值 `top/bottom/left/right` 中的任意一个；
2. **祖先元素有 `overflow: hidden/auto/scroll`**，sticky 被绑定到这个祖先上，而它本身并不滚动；
3. **父元素高度等于 sticky 元素本身**（或者太矮），没有可"粘"的空间。sticky 只在父容器范围内生效；
4. 在 flex/grid 容器里被拉伸（`align-items: stretch` 让它和父元素一样高），需要设 `align-self: flex-start`；
5. 祖先设置了 `overflow` 但没有固定高度，看起来不滚动，实际滚动的是外层容器。

```css
.table-head { position: sticky; top: 0; z-index: 1; background: #fff; }
.sidebar { position: sticky; top: 64px; align-self: flex-start; } /* 在 flex 布局中 */
```

**面试答题要点**
1. relative 不脱离文档流，用于微调或作为 absolute 的定位参照；absolute 找最近的非 static 祖先。
2. fixed 并不总是相对视口：祖先有 transform、filter 等属性时会失效，弹窗被包在动画容器里经常因此出问题。
3. sticky 等于 relative + fixed 的混合，作用范围限定在父元素内，参照最近的滚动祖先。
4. sticky 失效的排查顺序：阈值 → 祖先 overflow → 父元素高度 → flex 拉伸。
5. absolute 元素的 width 为 auto 时会"收缩包裹"内容；同时设置 left 和 right 可以撑满。

**易错点 / 追问**
- 解决 fixed 被 transform 祖先影响的方法：用 Portal 挂到 body，或者用 `dialog`/`popover` 进入顶层。
- `overflow: clip` 不会创建滚动容器，因此不会让 sticky 失效，可用来替代 `overflow: hidden`。

---

### 2.7 层叠上下文与 z-index ★★★

**是什么 / 原理**

**层叠上下文（Stacking Context）**是 z 轴上的一个独立"图层组"。z-index 只在**同一个层叠上下文内**比较；子元素无论 z-index 多大，都不能越过父级层叠上下文和它的兄弟比较。

**创建层叠上下文的条件**
- 根元素；
- `position: relative/absolute` + `z-index` 不为 auto；
- `position: fixed/sticky`（不需要 z-index）；
- flex/grid 子项 + `z-index` 不为 auto；
- `opacity < 1`、`transform`、`filter`、`backdrop-filter`、`perspective`、`clip-path`、`mask`、`mix-blend-mode` 不为 normal；
- `isolation: isolate`（专门用来创建层叠上下文，无副作用）；
- `will-change` 指定了上述属性、`contain: layout/paint`、`container-type`（size/inline-size）。

**同一层叠上下文内的绘制顺序（7 层，从下到上）**
1. 层叠上下文自身的背景和边框；
2. z-index 为负的子上下文；
3. 普通流中的块级盒子；
4. 浮动盒子；
5. 行内盒子（文字、inline-block）；
6. `z-index: auto/0` 的定位元素；
7. z-index 为正的子上下文。

（口诀：背景 → 负 z → 块 → 浮动 → 行内 → z0/auto → 正 z）

```html
<div style="position:relative; z-index:1">          <!-- 上下文 A(1) -->
  <div style="position:absolute; z-index:9999">弹窗</div>
</div>
<div style="position:relative; z-index:2">遮挡物</div> <!-- 上下文 B(2) -->
<!-- 弹窗的 9999 只在 A 内部生效，A(1) < B(2)，所以弹窗依然被遮挡 -->
```

**面试答题要点**
1. z-index 只在同一个层叠上下文中比较，"拼爹"：父级层叠上下文的层级决定子元素的上限。
2. 除了定位 + z-index，opacity、transform、filter、will-change、isolation 等也会创建层叠上下文。
3. 能背出 7 层绘制顺序，特别是"行内元素在浮动之上"、"负 z-index 在块级元素之下、在父上下文背景之上"。
4. `isolation: isolate` 是隔离组件内部层级的推荐做法，弹窗类组件最好用 Portal 或者顶层（dialog/popover）。
5. 工程上统一维护 z-index 分级表（如 dropdown 1000、modal 2000、toast 3000），避免各处随意写 9999。

**易错点 / 追问**：完整排查见 [3.4 z-index 为什么不生效](#34-z-index-为什么不生效-)。

---

### 2.8 响应式：媒体查询、容器查询、clamp、视口单位 ★★

**媒体查询**：根据**视口或设备特性**应用样式。除了宽度，还可以查询 `prefers-color-scheme`（深色模式）、`prefers-reduced-motion`（减少动画）、`hover: hover`/`pointer: coarse`（区分触屏和鼠标）、`orientation`。新的范围语法：`@media (400px <= width <= 800px)`。

**容器查询 `@container`**（尺寸查询 2023 年起主流浏览器均已支持，Baseline）：根据**父容器尺寸**而不是视口来决定样式，让组件放在侧栏或主区都能自适应，是真正的"组件级响应式"。

```css
.card-wrap { container: card / inline-size; }   /* container-name / container-type */
@container card (width > 400px) {
  .card { display: grid; grid-template-columns: 120px 1fr; }
}
.title { font-size: clamp(14px, 4cqi, 20px); }  /* cqi：容器内联尺寸的 1% */

/* 样式查询：根据容器的自定义属性值来匹配，支持度不如尺寸查询，以 caniuse 为准 */
@container style(--theme: dark) { .card { background: #222; } }
```

**`clamp(min, preferred, max)`**：值随视口线性变化，但不超出上下限。流式字体：`font-size: clamp(1rem, 0.8rem + 1vw, 1.5rem)`（中间值带上 rem，可以响应用户的字号缩放设置）。

**视口单位**
- `vh`：在移动端等于**地址栏收起时**的大视口，导致 `100vh` 的元素底部被工具栏遮挡；
- `svh`（small）：工具栏全部显示时的视口；`lvh`（large）：工具栏收起时的视口；
- `dvh`（dynamic）：随工具栏的显隐实时变化；
- 2022 年底起主流浏览器均已支持。全屏首屏推荐 `min-height: 100svh`（稳定），`100dvh` 在滚动时会变化，可能触发重排和跳动。

**rem / vw 移动端适配**：老方案是 lib-flexible（根据屏宽动态设置 html 的 font-size）加 px→rem；现在更推荐 `postcss-px-to-viewport` 直接转 vw，或者 rem + clamp 限制大屏上的最大值。

**面试答题要点**
1. 媒体查询看视口，容器查询看父容器，组件库更适合用容器查询。
2. 容器查询需要先声明 `container-type`（会创建尺寸包含，即容器自身尺寸不再由子元素决定）；`cqw/cqi` 是容器单位。
3. `clamp` 实现流式排版并限制边界，把 rem 混进中间值保证可访问性。
4. `100vh` 在移动端的问题和 `svh/lvh/dvh` 的区别。
5. 移动优先（min-width 从小写到大）比桌面优先更容易维护。

**易错点 / 追问**
- `container-type: size` 要求容器有明确高度，否则高度会塌成 0；通常用 `inline-size` 就够了。
- 容器无法查询自身，只能查询祖先容器。

---

### 2.9 现代 CSS 特性 ★

**CSS 变量（自定义属性）**：`--x: 10px; width: var(--x, 0)`。和 Sass 变量的本质区别：CSS 变量是**运行时**的，**会继承**，可以被 JS 读写（`el.style.setProperty('--x', ...)`），可以在媒体查询里重新赋值，因此适合做主题切换。`@property` 可以为变量注册类型，让它**可以做过渡动画**（2024 年起主流浏览器均已支持）。

```css
:root { --brand: #3b82f6; }
[data-theme="dark"] { --brand: #60a5fa; }
@property --angle { syntax: '<angle>'; inherits: false; initial-value: 0deg; }
.spin { background: conic-gradient(from var(--angle), red, blue); transition: --angle 1s; }
```

**原生嵌套**（2023 年起主流浏览器均已支持）：

```css
.card {
  color: #333;
  &:hover { color: red; }    /* & 代表父选择器 */
  .title { font-weight: 700; }  /* 新版规范已允许直接写元素或类选择器 */
  @media (width > 600px) { padding: 24px; }
}
```

和 Sass 的区别：原生嵌套的 `&` 相当于 `:is(父选择器)`，因此优先级按 `:is` 规则计算；**不支持** `&-suffix` 这种字符串拼接 BEM 写法。

**`color-mix()`**（2023 年起主流浏览器均已支持）：`color-mix(in oklch, var(--brand) 80%, white)`，可以用一个主色派生出 hover、浅色等色阶；配合相对颜色语法 `oklch(from var(--brand) calc(l + .1) c h)`（较新，以 caniuse 为准）。

**View Transitions（视图过渡）**：浏览器先给新旧两个状态拍快照，再在它们之间做动画。
- 同文档（SPA）：`document.startViewTransition(() => updateDOM())`。Chrome、Safari 已支持，Firefox 在 2025 年跟进，可看作已进入 Baseline 新近可用，以 caniuse 为准。
- 跨文档（MPA）：`@view-transition { navigation: auto; }`，Chromium 和 Safari 已支持，Firefox 以 caniuse 为准。
- 给元素写 `view-transition-name: hero` 可以做"共享元素"过渡；用 `::view-transition-old/new(hero)` 自定义动画。

```js
// 渐进增强：不支持时直接更新 DOM
if (!document.startViewTransition) update();
else document.startViewTransition(update);
```

**Scroll-driven Animations（滚动驱动动画）**：把动画的时间线从"时间"换成"滚动进度"，不写 JS 就能做阅读进度条、元素进入视口时的动画，而且可以在合成线程运行。

```css
.progress { animation: grow linear; animation-timeline: scroll(root); }
.reveal   { animation: fade-in linear both; animation-timeline: view(); animation-range: entry 0% cover 40%; }
@keyframes grow { from { transform: scaleX(0) } to { transform: scaleX(1) } }
```

支持情况：Chromium 已支持，Safari 在较新版本加入，Firefox 仍未默认开启，以 caniuse 为准。使用时用 `@supports (animation-timeline: scroll())` 做渐进增强。

**Anchor Positioning（锚点定位）**：用纯 CSS 把 tooltip 或下拉框"锚定"到另一个元素，并在空间不足时自动翻转，替代 Popper / Floating UI 的计算。

```css
.btn { anchor-name: --trigger; }
.tip {
  position: absolute; position-anchor: --trigger;
  position-area: top;                         /* 放在锚点上方 */
  position-try-fallbacks: flip-block;         /* 空间不够时翻到下方 */
}
```

支持情况：Chromium 已支持，Safari 新版本已跟进，Firefox 以 caniuse 为准；生产环境需要保留降级方案（如 Floating UI）。

**面试答题要点**
1. CSS 变量是运行时、可继承、能被 JS 操作的，Sass 变量编译后就消失了；主题切换首选 CSS 变量。
2. 原生嵌套基本能替代预处理器的嵌套，但没有字符串拼接，`&` 的优先级按 `:is` 计算。
3. View Transitions 用快照加伪元素树实现状态切换动画，SPA 和 MPA 都能用，务必做特性检测，并尊重 `prefers-reduced-motion`。
4. 滚动驱动动画和锚点定位都是"用 CSS 取代 JS 计算"，性能更好，但支持度要用 `@supports` 兜底。
5. 回答新特性时说明"支持度 + 降级方案"，比只会背语法更加分。

**易错点 / 追问**
- `var()` 失效时并不是回退到上一条声明，而是变成"计算时无效"，取继承值或初始值。
- 同一时刻页面上 `view-transition-name` 必须唯一，重复会导致整个过渡被跳过。

---

### 2.10 渲染与动画性能 ★★★

**是什么 / 原理**

渲染流水线：**DOM + CSSOM → 样式计算 → 布局（Layout / Reflow）→ 分层 → 绘制（Paint）→ 合成（Composite）**。

- **重排（回流）**：几何信息变化（尺寸、位置、显隐、字体、窗口大小），需要重新布局，代价最大，并且会引起后续的重绘和合成。
- **重绘**：外观变化但几何不变（color、background、visibility、box-shadow），跳过布局。
- **只合成**：`transform`、`opacity`（以及 filter 的部分情况）在已经提升为独立合成层时，只需要在合成线程（GPU）里变换图层，**不走主线程的布局和绘制**，主线程被 JS 卡住时动画依然流畅。

**强制同步布局（Layout Thrashing）**：先写样式再读取 `offsetHeight`、`getBoundingClientRect()`、`scrollTop`、`getComputedStyle` 等属性时，浏览器为了返回准确值，必须立即执行布局；在循环里读写交替会导致多次重排。

```js
// 不好：每次循环都读写交替，触发 N 次布局
items.forEach(el => { el.style.width = box.offsetWidth + 'px'; });
// 好：先统一读，再统一写
const w = box.offsetWidth;
items.forEach(el => { el.style.width = w + 'px'; });
```

**`will-change`**：提前告诉浏览器某个属性将要变化，浏览器会把元素提升为合成层。
- 不要滥用：每个层都占用显存，层太多（层爆炸）反而更慢；
- 动画开始前加上，结束后移除；
- 副作用：会创建层叠上下文和包含块（影响 fixed 子元素）。

**面试答题要点**
1. 流水线：样式 → 布局 → 绘制 → 合成；能跳过的步骤越多越快。
2. 动画只改 `transform/opacity`，用 translate 代替 top/left，用 scale 代替 width。
3. 避免强制同步布局：批量读写、用 `requestAnimationFrame` 安排写操作，或者使用 FastDOM 的思路。
4. `will-change` 按需使用，用完就移除，注意层爆炸和它对层叠上下文的副作用。
5. 其他手段：`contain: layout paint` / `content-visibility: auto` 跳过屏幕外内容的渲染；让动画元素脱离文档流（absolute）以缩小重排范围；用 DevTools 的 Performance 面板、Rendering 面板的 Paint flashing 和 Layers 定位问题。

**易错点 / 追问**
- `visibility: hidden` 只触发重绘；`display: none` 会触发重排。
- 现代浏览器会把样式修改**排队批处理**，问题不在于"改了几次"，而在于中间有没有强制读取布局属性。
- 追问"为什么 transform 动画会更流畅"：它在合成线程运行，不依赖主线程，也不需要重新布局和绘制。
- 追问"`translateZ(0)` 黑科技"：作用是强制提升为合成层，现在应该用 `will-change: transform` 表达意图。

---

### 2.11 工程方案：CSS Modules / Tailwind / CSS-in-JS ★★

| 方案 | 原理 | 优点 | 缺点 |
|---|---|---|---|
| BEM / 命名约定 | 靠人遵守规范 | 零成本 | 依赖自觉，名字长 |
| CSS Modules | 构建时把类名哈希化，形成局部作用域 | 零运行时、与 RSC 兼容、仍是写原生 CSS | 动态样式要靠 CSS 变量或 class 组合 |
| Tailwind（原子化） | 工具类 + 按需扫描生成，v4 由 Rust 引擎驱动、CSS 优先配置 | 产物小且增长慢、不用起名、约束设计规范（design tokens）、零运行时 | HTML 冗长、需要学习成本，复杂变体可读性差 |
| 运行时 CSS-in-JS（styled-components、Emotion） | 运行时生成样式并插入 `<style>` | 可以基于 props 动态生成样式、和组件同处一个文件 | **运行时开销**（序列化、插入规则、影响 INP），**和 React Server Components 不兼容**（依赖 Context 和客户端运行时），SSR 需要额外处理 |
| 零运行时 CSS-in-JS（vanilla-extract、Linaria、Panda、StyleX） | 编译期提取成静态 CSS | 类型安全、零运行时、兼容 RSC | 构建配置较复杂，动态能力受限 |

**面试答题要点**
1. 核心要解决的问题：作用域隔离、死代码清理、动态样式、主题、性能。
2. 运行时 CSS-in-JS 的两大问题：运行时成本，以及与 RSC/流式 SSR 不兼容；styled-components 已进入维护模式，社区在向零运行时方案迁移。
3. Tailwind 适合快速迭代且有设计规范约束的团队；CSS Modules 适合重视原生 CSS 能力的团队；两者都零运行时。
4. 动态样式的通用解法：CSS 变量 + 静态类名，不必每次生成新的 CSS 规则。
5. 选型要说清取舍：团队习惯、SSR/RSC 架构、组件库的主题需求、包体积。

**易错点 / 追问**
- CSS Modules 里修改第三方组件样式要用 `:global(.ant-btn)`。
- Tailwind 动态拼接类名（`bg-${color}-500`）不会被扫描到、不会生成样式，要写完整类名或使用 safelist。

---

## 三、高频题完整参考答案

### 3.1 水平垂直居中 N 种方法 ★★★

**回答策略**：先按"是否已知子元素宽高"分类，再给出现代首选方案，最后简单提一下各方案的适用场景。

```html
<div class="parent"><div class="child">内容</div></div>
```

```css
/* 方案 1：Flex（首选，宽高未知也可以） */
.parent { display: flex; justify-content: center; align-items: center; }

/* 方案 2：Grid（代码最短） */
.parent { display: grid; place-items: center; }
/* 或者：.parent{display:grid} .child{margin:auto} */

/* 方案 3：absolute + transform（宽高未知；注意可能出现半像素模糊） */
.parent { position: relative; }
.child  { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); }

/* 方案 4：absolute + inset:0 + margin:auto（子元素需要有宽高，或者是 fit-content） */
.child { position: absolute; inset: 0; margin: auto; width: 200px; height: 100px; }

/* 方案 5：absolute + 负 margin（必须已知宽高，属于老写法） */
.child { position: absolute; top: 50%; left: 50%; width: 200px; height: 100px;
         margin: -50px 0 0 -100px; }

/* 方案 6：absolute + calc（必须已知宽高） */
.child { position: absolute; top: calc(50% - 50px); left: calc(50% - 100px); }

/* 方案 7：Flex/Grid 子项 margin:auto */
.parent { display: flex; } .child { margin: auto; }

/* 方案 8：table-cell（兼容老浏览器） */
.parent { display: table-cell; text-align: center; vertical-align: middle; }
.child  { display: inline-block; }

/* 方案 9：单行文本 */
.parent { height: 40px; line-height: 40px; text-align: center; }

/* 方案 10：align-content 直接作用于块容器（2024 年起主流浏览器支持，以 caniuse 为准） */
.parent { align-content: center; }  /* 垂直居中，不需要 flex/grid */
.child  { margin-inline: auto; width: fit-content; }
```

**面试答题要点**
1. 宽高未知：flex、grid、absolute + transform；宽高已知：负 margin、calc、inset + margin:auto。
2. 现代项目首选 `display: grid; place-items: center` 或 flex，语义清晰，不脱离文档流。
3. transform 方案在宽高为奇数时可能出现半像素模糊；absolute 方案脱离文档流，父元素需要有高度。
4. 只有水平居中：行内元素用 `text-align: center`，定宽块元素用 `margin: 0 auto`。
5. 能提到 `align-content` 作用于普通块容器这一新变化是加分项。

---

### 3.2 1px 问题 ★★

**问题本质**：CSS 像素不等于物理像素。在 `devicePixelRatio = 2/3` 的屏幕上，`border: 1px` 实际渲染为 2 或 3 个物理像素，设计稿上的"一根细线"看起来就偏粗。

**方案对比**

```css
/* 方案 1：伪元素 + transform: scale（最通用，推荐） */
.hairline { position: relative; }
.hairline::after {
  content: ''; position: absolute; left: 0; top: 0;
  width: 200%; height: 200%;
  border: 1px solid #ddd; border-radius: 8px;  /* 圆角也要乘以 2 */
  transform: scale(.5); transform-origin: 0 0;
  pointer-events: none; box-sizing: border-box;
}
@media (min-resolution: 3dppx) {
  .hairline::after { width: 300%; height: 300%; border-radius: 12px; transform: scale(.333); }
}

/* 方案 2：只要单边线：伪元素高 1px + scaleY */
.line::after { content: ''; position: absolute; left: 0; right: 0; bottom: 0;
  height: 1px; background: #ddd; transform: scaleY(.5); transform-origin: 0 100%; }

/* 方案 3：0.5px 边框（iOS 8+ 支持；部分老安卓会渲染成 0 或 1px） */
@media (min-resolution: 2dppx) { .b { border-width: .5px; } }

/* 方案 4：box-shadow 模拟（颜色偏淡、不够锐利） */
.b { box-shadow: 0 0 0 .5px #ddd; }

/* 方案 5：viewport 缩放：initial-scale = 1/dpr，再配合 rem（如老版 lib-flexible）
   会影响整页布局，已不推荐 */

/* 方案 6：border-image / 背景渐变 linear-gradient 画一半透明的线（不支持圆角） */
.b { background: linear-gradient(#ddd, #ddd 50%, transparent 50%) bottom / 100% 1px no-repeat; }
```

**面试答题要点**
1. 原因：DPR 大于 1 时，1 个 CSS 像素对应多个物理像素。
2. 首选伪元素放大到 200% 后 `scale(0.5)`，能支持四条边和圆角；只需要单边时用 `scaleY`。
3. `0.5px` 最简单，但老安卓兼容性差，需要通过媒体查询或 JS 检测降级。
4. viewport 缩放方案影响全局，现在基本不再使用。
5. 注意 `pointer-events: none`，避免伪元素挡住点击；圆角要同步放大。

---

### 3.3 三栏布局 / 圣杯 / 双飞翼 ★★

**需求**：左右两栏定宽，中间自适应；**中间栏在 DOM 中排在最前面，优先渲染**（这是圣杯和双飞翼的核心诉求）。

**现代写法（实际项目推荐）**

```css
/* Flex：DOM 顺序可以是 main、left、right，用 order 调整视觉顺序 */
.container { display: flex; }
.left  { flex: 0 0 200px; order: -1; }
.right { flex: 0 0 150px; }
.main  { flex: 1; min-width: 0; }

/* Grid */
.container { display: grid; grid-template-columns: 200px 1fr 150px; }
```

**圣杯布局（float + 负 margin + 父元素 padding + relative）**

```html
<div class="container">
  <div class="main">中间</div>
  <div class="left">左</div>
  <div class="right">右</div>
</div>
```

```css
.container { padding: 0 150px 0 200px; overflow: hidden; } /* 1. 给左右两栏留出位置 */
.main, .left, .right { float: left; }
.main  { width: 100%; }
.left  { width: 200px; margin-left: -100%;               /* 2. 拉回上一行的最左边 */
         position: relative; left: -200px; }              /* 3. 再移进 padding 区 */
.right { width: 150px; margin-left: -150px;              /* 2. 拉回上一行的最右边 */
         position: relative; right: -150px; }             /* 3. 移进右侧 padding 区 */
/* 缺陷：中间栏宽度小于左栏时布局会错乱，所以要给 container 设 min-width */
```

**双飞翼布局（中间栏多包一层，用内层 margin 让位）**

```html
<div class="main-wrap"><div class="main">中间</div></div>
<div class="left">左</div>
<div class="right">右</div>
```

```css
.main-wrap, .left, .right { float: left; }
.main-wrap { width: 100%; }
.main  { margin: 0 150px 0 200px; }          /* 用内层 margin 给左右栏让位 */
.left  { width: 200px; margin-left: -100%; }
.right { width: 150px; margin-left: -150px; } /* 不需要 relative */
/* 父元素记得清浮动 */
```

**面试答题要点**
1. 共同点：都用 float + 负 margin 把左右栏拉到中间栏所在的行，并让中间栏在 DOM 中排第一，优先加载。
2. 负 margin 原理：`margin-left: -100%`（相对父元素宽度）让左栏回到上一行的开头；`margin-left: -自身宽度` 让右栏回到上一行的末尾。
3. 圣杯用父元素 padding + 相对定位让位；双飞翼给中间多套一层，用内层 margin 让位，不需要定位，更稳定。
4. 现代项目直接用 Flex 或 Grid，DOM 顺序和视觉顺序可以通过 order 或 grid-area 解耦。
5. 还可以提绝对定位方案（左右 absolute，中间 margin）和 BFC 方案（左右浮动，中间 overflow:hidden，但这样中间栏必须写在 DOM 的最后面）。

---

### 3.4 z-index 为什么不生效 ★★★

**完整排查清单**

1. **元素是 `position: static`**：非定位元素设置 z-index 无效。例外：flex/grid 子项即使是 static，z-index 也生效。
2. **父级层叠上下文的层级太低（最常见）**：z-index 只在同一个层叠上下文中比较。祖先 A 的 z-index 为 1，它的兄弟 B 的 z-index 为 2，那么 A 里的子元素 z-index 设成 9999 也盖不住 B。
3. **祖先"意外"创建了层叠上下文**：`transform`、`opacity < 1`、`filter`、`will-change`、`backdrop-filter`、`isolation`、`contain`、`container-type`、`mix-blend-mode` 等，把子元素困在里面。动画库给元素加的 transform 是常见的元凶。
4. **比较对象不对**：对方没有在同一层级参与比较，或者对方是层叠顺序中更高的一层（比如 z-index:auto 的定位元素会盖在浮动、行内内容之上）。
5. **被 `overflow: hidden` 裁剪**：看起来像是被盖住了，实际是超出部分被祖先裁掉，和 z-index 无关。
6. **顶层（Top Layer）元素**：`dialog.showModal()`、popover、全屏元素位于顶层之上，任何 z-index 都盖不过它们。
7. **其他**：z-index 写在 iframe、视频等原生控件（老浏览器）上；拼写或优先级问题导致声明本身被覆盖（在 DevTools 里看是否被划掉）。

**解决方案**
- 找到产生层叠上下文的祖先，调整**祖先**的 z-index，而不是子元素的；
- 把弹窗用 Portal 挂到 body 下；或者直接用 `<dialog>`/popover 进入顶层；
- 组件内部使用 `isolation: isolate` 做隔离，防止组件内部的层级泄漏到外部；
- 团队维护统一的 z-index 分级常量。

**面试答题要点**
1. 第一步检查是否是定位元素（或 flex/grid 子项）。
2. 核心原因是层叠上下文"拼爹"：子元素的层级上限由父级上下文决定。
3. 能列出 transform、opacity、filter、will-change 等会隐式创建层叠上下文的属性。
4. 解决：调整祖先的层级、Portal、顶层 API、isolation。
5. 排查工具：DevTools 的 Layers 面板，或者 Edge 的 3D View 能直接看到层叠关系。

---

### 3.5 其他常见小题 ★★

**隐藏元素的方式对比**

| 方式 | 占位 | 可交互 | 读屏器 | 重排/重绘 | 可过渡 |
|---|---|---|---|---|---|
| `display: none` | 否 | 否 | 不读 | 重排 | 否（新特性 `transition-behavior: allow-discrete` 可以） |
| `visibility: hidden` | 是 | 否 | 不读 | 重绘 | 是（离散切换） |
| `opacity: 0` | 是 | **是** | 读 | 合成 | 是 |
| `hidden` 属性 | 否 | 否 | 不读 | 等价于 display:none，会被 CSS 覆盖 | 否 |
| `.sr-only`（clip） | 否 | 可聚焦 | 读 | — | — |
| `content-visibility: hidden` | 保留尺寸 | 否 | 不读 | 跳过渲染并保留渲染状态 | — |

补充：`visibility: hidden` 的子元素设 `visibility: visible` 还能显示出来，`display: none` 则不行。

**文本溢出省略**

```css
/* 单行 */
.ellipsis { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
/* 多行（-webkit-line-clamp 各主流浏览器都已支持） */
.clamp-2 { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
```

在 flex 子项里单行省略不生效，要给该子项加 `min-width: 0`。

**CSS 画三角形**

```css
.triangle { width: 0; height: 0; border: 10px solid transparent; border-bottom-color: red; } /* 朝上 */
/* 现代写法：clip-path */
.tri { width: 20px; height: 20px; background: red; clip-path: polygon(50% 0, 0 100%, 100% 100%); }
```

**px / em / rem / vw / %**：`em` 相对于自身的 font-size（用于 font-size 时相对父元素），`rem` 相对于根元素，`%` 的参照因属性而异（width 相对包含块宽度，line-height 相对自身字号，transform 相对自身尺寸），`vw` 相对于视口宽度。

**line-height 写数字和写百分比的区别**：写数字（如 `1.5`）时，子元素继承的是"系数"，按子元素自己的字号重新计算；写百分比或 em 时，继承的是父元素**计算好的固定值**，子元素字号变大后可能出现文字重叠。

**CSS 加载会阻塞吗？**：不阻塞 DOM 解析；阻塞渲染；阻塞它之后的 JS 执行。所以 CSS 要尽早加载，可以内联关键 CSS，非关键 CSS 用 `media="print" onload="this.media='all'"` 等方式异步加载。

---

## 附：现代特性浏览器支持速查

> 大致状态（截至 2026 年），**一律以 caniuse / MDN Baseline 为准**。"Baseline" 指 Chrome、Edge、Firefox、Safari 当前版本均已支持。

| 特性 | 大致状态 |
|---|---|
| `<dialog>`、`inert`、`:focus-visible` | Baseline，可放心使用 |
| Popover API | 2024 年进入 Baseline |
| Declarative Shadow DOM | 2024 年进入 Baseline |
| `<details name>` 互斥手风琴 | 主流浏览器已支持，以 caniuse 为准 |
| 可定制 select（`appearance: base-select`） | 主要是 Chromium，其他以 caniuse 为准 |
| `@layer` | 2022 年进入 Baseline |
| `:is()` / `:where()` | Baseline |
| `:has()` | 2023 年进入 Baseline |
| `@container` 尺寸查询、`cq*` 单位 | 2023 年进入 Baseline |
| `@container style()` 样式查询 | Chromium、Safari 已支持，Firefox 以 caniuse 为准 |
| `svh / lvh / dvh` | 2022 年底进入 Baseline |
| CSS 原生嵌套 | 2023 年进入 Baseline（宽松语法在之后的版本中支持） |
| `color-mix()` | 2023 年进入 Baseline |
| 相对颜色语法 `from` | 较新，以 caniuse 为准 |
| `@property` | 2024 年进入 Baseline |
| `subgrid` | 2023 年进入 Baseline |
| View Transitions（同文档） | Chrome、Safari 已支持，Firefox 2025 年跟进，以 caniuse 为准 |
| View Transitions（跨文档） | Chromium、Safari 已支持，Firefox 以 caniuse 为准 |
| Scroll-driven Animations | Chromium 已支持，Safari 新版本跟进，Firefox 以 caniuse 为准 |
| Anchor Positioning | Chromium 已支持，Safari 新版本跟进，Firefox 以 caniuse 为准 |
| `@starting-style`、`transition-behavior` | 较新，以 caniuse 为准 |
| 块容器 `align-content` 居中 | 2024 年起主流浏览器支持，以 caniuse 为准 |
| Speculation Rules | 主要是 Chromium，以 caniuse 为准 |

**落地原则**：渐进增强。用 `@supports (selector(:has(a)))`、`@supports (animation-timeline: scroll())` 或 JS 特性检测（`'startViewTransition' in document`）做兜底，不支持时功能可用、只是少了效果。
