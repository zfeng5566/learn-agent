# 07 工程化与性能优化 知识点详解

> 对应总大纲第 8 节（工程化 ★★）和第 9 节（性能优化 ★★★）。
> 星级表示考频：★★★ 必考 / ★★ 常考 / ★ 加分项。
> 每节结构：**是什么 / 原理** → **代码示例** → **面试答题要点**（可以直接口述）→ **易错点 / 追问**。
> 内容按 2026 年的情况整理。工具版本变化很快，具体版本号和默认行为以各工具官方文档为准。

## 目录

- [第一部分 工程化](#第一部分-工程化)
  - [1. Webpack 构建流程 ★★★](#1-webpack-构建流程-)
  - [2. 手写 Webpack Loader ★★★](#2-手写-webpack-loader-)
  - [3. 手写 Webpack Plugin ★★★](#3-手写-webpack-plugin-)
  - [4. Vite 为什么快 ★★★](#4-vite-为什么快-)
  - [5. Rspack / esbuild / SWC / Babel 定位对比 ★★](#5-rspack--esbuild--swc--babel-定位对比-)
  - [6. Tree Shaking 与 sideEffects ★★★](#6-tree-shaking-与-sideeffects-)
  - [7. Code Splitting 策略 ★★](#7-code-splitting-策略-)
  - [8. 包管理：pnpm 与幽灵依赖 ★★★](#8-包管理pnpm-与幽灵依赖-)
  - [9. Monorepo ★★](#9-monorepo-)
  - [10. 代码规范与 CI/CD ★★](#10-代码规范与-cicd-)
  - [11. 微前端方案对比 ★★](#11-微前端方案对比-)
- [第二部分 性能优化](#第二部分-性能优化)
  - [12. 性能方法论与指标体系 ★★★](#12-性能方法论与指标体系-)
  - [13. LCP：成因与优化 ★★★](#13-lcp成因与优化-)
  - [14. INP：成因与优化 ★★★](#14-inp成因与优化-)
  - [15. CLS：成因与优化 ★★★](#15-cls成因与优化-)
  - [16. 用 PerformanceObserver 采集指标 ★★](#16-用-performanceobserver-采集指标-)
  - [17. 虚拟列表手写 ★★★](#17-虚拟列表手写-)
  - [18. 长任务拆分 ★★★](#18-长任务拆分-)
  - [19. 图片与字体优化 ★★](#19-图片与字体优化-)
  - [20. 缓存、预加载与渲染优化补充 ★★](#20-缓存预加载与渲染优化补充-)
  - [21. 内存泄漏排查 ★★](#21-内存泄漏排查-)
  - [22. 「首屏优化」STAR 示范回答 ★★★](#22-首屏优化star-示范回答-)

---

# 第一部分 工程化

## 1. Webpack 构建流程 ★★★

### 是什么 / 原理

Webpack 是一个**静态模块打包器**：从入口出发，递归分析依赖，把所有模块（JS、CSS、图片等）打包成浏览器能运行的 bundle。核心流程可以分成三个阶段：

```text
初始化阶段
  读取配置（webpack.config.js + CLI 参数）合并成 options
  → 创建 Compiler 对象（全局唯一，贯穿整个生命周期）
  → 注册所有 plugin（调用 plugin.apply(compiler)）
  → 调用 compiler.run() / compiler.watch()

构建（Make）阶段
  创建 Compilation 对象（每次构建一份，watch 模式下每次变更都会新建）
  → 从 entry 开始，对每个模块：
      1. resolve：解析模块路径（resolve.alias / extensions / modules）
      2. 匹配 module.rules，用 loader 链把源文件转成 JS
      3. 用解析器（acorn）把 JS 转成 AST，找出 import / require
      4. 对每个依赖递归执行 1-3
  → 得到完整的模块依赖图（ModuleGraph）

生成（Seal / Emit）阶段
  根据 entry 和动态 import() 把模块分成 Chunk
  → SplitChunksPlugin 做公共代码提取
  → 优化：Tree Shaking 标记、Scope Hoisting、压缩（Terser）
  → 用模板生成最终代码（runtime + 模块包装函数）
  → emit：写入 output.path
```

两个核心对象：

| 对象 | 生命周期 | 作用 |
|---|---|---|
| `Compiler` | 整个进程只有一个 | 保存完整配置，暴露 `run`、`emit`、`done` 等全局钩子 |
| `Compilation` | 每次构建一个 | 保存本次构建的模块、chunk、产物，暴露 `buildModule`、`seal`、`processAssets` 等钩子 |

插件机制基于 **Tapable**：Webpack 在各个阶段定义了钩子（`SyncHook`、`AsyncSeriesHook` 等），插件通过 `tap` / `tapAsync` / `tapPromise` 注册回调，Webpack 在对应时机 `call` 这些钩子。

### 代码示例：产物大致长什么样

```js
// Webpack 5 产物的简化结构（开发模式）
(() => {
  // key 是模块 id（通常是相对路径），value 是模块包装函数
  var __webpack_modules__ = {
    './src/a.js': (module, exports, require) => {
      exports.add = (x, y) => x + y;
    },
    './src/index.js': (module, exports, require) => {
      const { add } = require('./src/a.js');
      console.log(add(1, 2));
    },
  };
  // 模块缓存，key 是模块 id
  var __webpack_module_cache__ = {};
  function __webpack_require__(id) {
    if (__webpack_module_cache__[id]) return __webpack_module_cache__[id].exports;
    const module = (__webpack_module_cache__[id] = { exports: {} });
    __webpack_modules__[id](module, module.exports, __webpack_require__);
    return module.exports;
  }
  __webpack_require__('./src/index.js');
})();
```

### 面试答题要点

1. 三个阶段：**初始化**（合并配置、创建 Compiler、注册插件）→ **构建**（从 entry 递归 resolve + loader 转换 + AST 解析依赖，生成模块图）→ **生成**（分 chunk、优化、生成代码、写盘）。
2. `Compiler` 全局唯一，`Compilation` 每次构建一份；watch 模式下增量构建只重建变更的模块。
3. loader 负责**单个文件的转换**，plugin 通过 Tapable 钩子**介入整个构建生命周期**。
4. 产物本质是一个模块表加一个 `__webpack_require__` 运行时，异步 chunk 通过 JSONP（`self.webpackChunk.push`）加载。

### 易错点 / 追问

- **追问：HMR 原理？** dev server 和浏览器之间建 WebSocket；文件变更后 Webpack 增量编译，推送新的 hash；浏览器拉取 `[hash].hot-update.json` 和对应的 chunk，由 `module.hot.accept` 链决定替换哪些模块，找不到 accept 边界就整页刷新。
- **追问：hash / chunkhash / contenthash 区别？** hash 是整个构建级别的，任何改动都会变；chunkhash 是 chunk 级别；contenthash 只跟文件内容相关，长期缓存应该用 contenthash。
- **易错：** 把 loader 和 plugin 的职责说反；或者说 loader 是从左往右执行（实际是从右往左 / 从下往上）。

---

## 2. 手写 Webpack Loader ★★★

### 是什么 / 原理

loader 本质是一个**导出函数的 Node 模块**：接收源文件内容（字符串或 Buffer），返回转换后的内容。

- **执行顺序**：`use: ['style-loader', 'css-loader', 'less-loader']` 实际执行顺序是 less → css → style，从右往左（类似函数组合 `compose`）。
- **pitch 阶段**：每个 loader 可以导出 `pitch` 方法，pitch 先从左往右执行；如果某个 pitch 返回了值，会跳过后面的 loader，直接掉头执行前面 loader 的 normal 阶段。`style-loader` 就是利用 pitch 实现的。
- **同步 / 异步**：直接 `return` 是同步；调用 `this.async()` 拿到 callback 是异步。
- **raw loader**：`module.exports.raw = true` 时入参是 Buffer，处理图片等二进制文件时用。
- **上下文 `this`**：`this.getOptions()` 取配置、`this.resourcePath` 当前文件路径、`this.addDependency()` 添加额外的监听文件、`this.cacheable()` 标记可缓存（Webpack 5 默认可缓存）。

### 代码示例：移除 console 并加文件头注释的 loader

```js
// loaders/strip-console-loader.js
/**
 * 把源码中的 console.log 调用去掉，并在文件头加一段注释。
 * @param {string} source 上一个 loader（或原始文件）传进来的源码
 * @returns {string} 转换后的源码
 */
module.exports = function stripConsoleLoader(source) {
  // 读取 loader 配置，例如 { banner: 'built by xxx' }
  const { banner = '' } = this.getOptions() || {};
  // 简化实现：用正则去掉 console.log(...)，生产中应该用 AST（Babel 插件）避免误删字符串里的内容
  const result = source.replace(/console\.log\(.*?\);?/g, '');
  return `/* ${banner} | ${this.resourcePath} */\n${result}`;
};
```

```js
// 异步 loader 写法
module.exports = function asyncLoader(source) {
  const callback = this.async();
  someAsyncTransform(source)
    .then((code) => callback(null, code /* , sourceMap */))
    .catch((err) => callback(err));
};
```

```js
// webpack.config.js 中使用
module.exports = {
  module: {
    rules: [
      {
        test: /\.js$/,
        exclude: /node_modules/,
        use: [{ loader: require.resolve('./loaders/strip-console-loader'), options: { banner: 'demo' } }],
      },
    ],
  },
};
```

### 面试答题要点

1. loader 是一个函数，输入源码输出源码，只负责**单文件转换**，要保持单一职责、可链式组合。
2. 执行顺序从右往左；pitch 从左往右，pitch 有返回值时会熔断后续 loader。
3. 异步用 `this.async()`，二进制用 `raw = true`，配置用 `this.getOptions()`。
4. 正式项目里做代码改写应该基于 AST（Babel / SWC 插件），正则只适合演示。

### 易错点 / 追问

- **追问：style-loader 为什么要用 pitch？** css-loader 的输出是一段 JS 模块代码（导出 CSS 字符串），style-loader 在 normal 阶段拿到的是 JS 代码不是 CSS。所以它在 pitch 阶段直接生成 `require('!!css-loader!./a.css')` 的代码，在运行时拿到 CSS 字符串再插入 `<style>`。
- **追问：怎么调试 loader？** 用 `loader-runner` 单独跑，或者 `node --inspect-brk node_modules/webpack/bin/webpack.js`。
- **易错：** 在 loader 里用箭头函数导出，导致 `this` 不是 loader 上下文。

---

## 3. 手写 Webpack Plugin ★★★

### 是什么 / 原理

plugin 是一个**带 `apply(compiler)` 方法的类**。Webpack 初始化时调用 `apply`，插件在里面通过 `compiler.hooks.xxx.tap(...)` 注册回调，从而在构建的任意阶段读取或修改数据。

常用钩子：

| 钩子 | 所属 | 类型 | 用途 |
|---|---|---|---|
| `compiler.hooks.compilation` | Compiler | Sync | 拿到每次新建的 compilation，再挂 compilation 钩子 |
| `compiler.hooks.emit` | Compiler | AsyncSeries | 写盘前，Webpack 5 推荐改用 `processAssets` |
| `compilation.hooks.processAssets` | Compilation | AsyncSeries | 增删改产物（Webpack 5 推荐） |
| `compiler.hooks.done` | Compiler | AsyncSeries | 构建完成，做通知、上报 |

### 代码示例：生成产物清单（文件名 + 大小）的插件

```js
// plugins/manifest-plugin.js
const { Compilation, sources } = require('webpack');

/**
 * 构建结束前生成一个 manifest.json，列出每个产物的文件名和大小（字节）。
 */
class ManifestPlugin {
  /**
   * @param {{ filename?: string }} options filename 是输出的清单文件名
   */
  constructor(options = {}) {
    this.filename = options.filename || 'manifest.json';
  }

  /**
   * Webpack 初始化时调用，在这里注册钩子。
   * @param {import('webpack').Compiler} compiler 全局唯一的 Compiler 实例
   */
  apply(compiler) {
    const pluginName = 'ManifestPlugin';
    compiler.hooks.thisCompilation.tap(pluginName, (compilation) => {
      compilation.hooks.processAssets.tap(
        // SUMMARIZE 阶段：所有优化完成后，适合做汇总类操作
        { name: pluginName, stage: Compilation.PROCESS_ASSETS_STAGE_SUMMARIZE },
        (assets) => {
          // assets 的 key 是产物文件名，value 是 Source 对象
          const list = Object.entries(assets).map(([name, source]) => ({ name, size: source.size() }));
          compilation.emitAsset(this.filename, new sources.RawSource(JSON.stringify(list, null, 2)));
        },
      );
    });
    // 构建完成后打印耗时
    compiler.hooks.done.tap(pluginName, (stats) => {
      console.log(`[${pluginName}] 构建耗时 ${stats.endTime - stats.startTime}ms`);
    });
  }
}

module.exports = ManifestPlugin;
```

### 面试答题要点

1. plugin 是带 `apply` 方法的类，通过 Tapable 钩子介入构建生命周期，能力比 loader 大得多：改产物、改模块图、注入运行时、上报等。
2. 先区分 Compiler 钩子（全局）和 Compilation 钩子（单次构建）；改产物在 Webpack 5 用 `processAssets` 并指定 stage。
3. 异步钩子用 `tapAsync`（callback）或 `tapPromise`（返回 Promise），否则构建不会等待。
4. 常见插件举例：HtmlWebpackPlugin（生成 HTML 并注入脚本）、MiniCssExtractPlugin（抽 CSS）、DefinePlugin（编译期常量替换）。

### 易错点 / 追问

- **追问：Tapable 有哪些钩子类型？** Sync / SyncBail（返回非 undefined 熔断）/ SyncWaterfall（上一个返回值传给下一个）/ SyncLoop，以及 AsyncSeries / AsyncParallel 对应变体。
- **易错：** 在 `emit` 里直接改 `compilation.assets[name] = ...`，Webpack 5 会给出弃用警告，应该用 `emitAsset` / `updateAsset`。
- **追问：Rspack 能用 Webpack 插件吗？** Rspack 兼容大部分 Webpack 插件 API，但不是全部，依赖内部细节的插件可能不兼容，以 Rspack 官方兼容列表为准。

---

## 4. Vite 为什么快 ★★★

### 是什么 / 原理

Webpack 开发模式的慢，根本原因是**启动前要把整个应用打包一遍**，项目越大启动越慢；HMR 也要重新构建受影响的 chunk。

Vite 的思路：

**开发阶段：No-Bundle + 原生 ESM**

```text
浏览器请求 /src/main.ts
  → Vite dev server 拦截
  → 用 esbuild 把 TS/JSX 转成 JS（只转译，不做类型检查），Vue/Svelte 用对应插件编译
  → 改写裸模块导入：import 'vue' → import '/node_modules/.vite/deps/vue.js?v=xxx'
  → 返回给浏览器，浏览器按 import 语句继续请求其他模块
```

- **按需编译**：只编译当前页面真正请求到的模块，冷启动时间和项目规模基本无关。
- **依赖预构建（Dependency Pre-Bundling）**：首次启动时用 esbuild 把 `node_modules` 里的依赖打包到 `node_modules/.vite/deps`。目的有两个：
  1. **CommonJS / UMD 转 ESM**，因为浏览器只认 ESM；
  2. **合并大量小文件**，比如 `lodash-es` 有几百个内部模块，不合并的话浏览器会发几百个请求。
- **强缓存**：预构建的依赖用 `Cache-Control: max-age=31536000, immutable`，源码用 304 协商缓存。
- **HMR 精确**：基于 ESM 模块图，只让修改的模块和它的 HMR 边界失效，速度和项目规模无关。

**生产阶段：仍然打包**

生产环境如果也不打包，大量嵌套 import 会造成请求瀑布，所以 Vite 生产构建仍然打包，以前用 **Rollup**（Tree Shaking 和产物质量好，但 JS 实现偏慢）。

**Rolldown**：Vite 团队用 Rust 写的 Rollup 兼容打包器，目标是统一开发和生产两套工具（替代 esbuild + Rollup 的组合），同时提升生产构建速度。截至 2025 年下半年，已经有 `rolldown-vite` 可选包，Vite 8 测试版开始默认使用 Rolldown。**它在你所用 Vite 版本里是否默认、是否稳定，以 Vite 官方文档和发布说明为准。**

### 代码示例：常用配置

```ts
// vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    // 动态引入导致扫描不到的依赖，手动加入预构建，避免首次访问时重新预构建并刷新页面
    include: ['lodash-es', 'dayjs'],
  },
  build: {
    rollupOptions: {
      output: {
        // 手动分包：key 是 chunk 名，value 是要放进去的依赖
        manualChunks: { react: ['react', 'react-dom'], chart: ['echarts'] },
      },
    },
  },
});
```

```ts
// 一个最小 Vite 插件：把 import 'virtual:build-info' 解析成构建时间
export default function buildInfoPlugin() {
  const id = 'virtual:build-info';
  const resolvedId = '\0' + id; // \0 前缀表示虚拟模块，其他插件不要处理
  return {
    name: 'build-info',
    resolveId(source: string) {
      return source === id ? resolvedId : null;
    },
    load(loadId: string) {
      if (loadId === resolvedId) return `export const buildTime = ${JSON.stringify(new Date().toISOString())};`;
      return null;
    },
  };
}
```

### 面试答题要点

1. 开发阶段不打包，利用浏览器原生 ESM 按需请求、按需编译，冷启动和项目规模基本无关。
2. 依赖预构建用 esbuild（Go 写的，比 JS 工具快几十倍）把 CJS 转 ESM 并合并小文件，减少请求数，并用强缓存。
3. HMR 基于 ESM 模块图精确失效，不需要重新打包 chunk。
4. 生产环境仍然打包（避免请求瀑布），以前是 Rollup，正在迁移到 Rust 写的 Rolldown，以统一开发和生产行为（状态以官方为准）。
5. Vite 插件兼容 Rollup 插件接口，并额外有 `configureServer`、`transformIndexHtml`、`handleHotUpdate` 等 Vite 专属钩子。

### 易错点 / 追问

- **追问：Vite 开发和生产不一致会有什么问题？** 开发用 esbuild + 原生 ESM，生产用 Rollup，偶尔出现“开发正常、上线报错”（比如 CJS 互操作、CSS 顺序）。这也是 Rolldown 要解决的问题之一。
- **追问：项目很大时 Vite 开发也慢？** 页面首次加载可能要请求上千个模块，请求瀑布会变慢。可以用 `server.warmup` 预热常用文件，减少过深的 barrel 文件（`index.ts` 统一导出）。
- **易错：** 说 Vite 开发时用 Rollup 编译源码（实际是 esbuild 转译 + 插件管线），或者说 esbuild 会做类型检查（不会，类型检查要单独跑 `tsc --noEmit` 或 `vite-plugin-checker`）。

---

## 5. Rspack / esbuild / SWC / Babel 定位对比 ★★

### 是什么 / 原理

| 工具 | 语言 | 定位 | 优势 | 局限 | 典型使用 |
|---|---|---|---|---|---|
| Webpack | JS | 全功能打包器 | 生态最大，配置最灵活 | 大项目构建慢 | 存量项目 |
| Rspack | Rust | **兼容 Webpack 的打包器** | 兼容大部分 Webpack 配置、loader、插件，构建快很多倍，迁移成本低 | 少数插件不兼容 | Webpack 存量项目提速，Rsbuild 上层封装 |
| esbuild | Go | 极快的转译器 + 打包器 | 非常快，API 简单 | 代码分割、CSS 处理、插件生态相对弱，不降级到 ES5 | Vite 开发期转译与依赖预构建、库打包、tsup |
| SWC | Rust | **转译器**（Babel 替代） | 比 Babel 快很多，支持 TS/JSX/压缩 | 插件需要用 Rust/Wasm 写，生态小于 Babel | Next.js 编译器、`@vitejs/plugin-react-swc`、Rspack 内置 |
| Babel | JS | 转译器 | 插件生态最丰富，定制性强 | 慢 | 需要特殊语法插件的场景 |
| Rollup | JS | 打包器，偏库 | Tree Shaking 好，ESM 产物干净 | 大型应用构建慢 | 库打包、Vite 生产（旧） |
| Rolldown | Rust | Rollup 兼容打包器 | 快，目标统一 Vite 开发和生产 | 仍在演进，以官方为准 | Vite 新版本 |
| Turbopack | Rust | Next.js 的增量打包器 | 和 Next.js 深度集成 | 主要服务 Next.js 生态 | Next.js |

关键区分：**转译器（Transpiler）** 只把一个文件从一种语法转成另一种语法（TS→JS、ES2022→ES2015），**打包器（Bundler）** 要处理模块依赖图、分包、产物生成。esbuild 两者都能做，SWC 和 Babel 主要是转译器。

### 代码示例：Babel 插件（展示 AST 基本概念）

```js
// 把所有 var 声明改成 let 的 Babel 插件
module.exports = function varToLet() {
  return {
    visitor: {
      // 访问者模式：遍历 AST 时遇到 VariableDeclaration 节点就调用
      VariableDeclaration(path) {
        if (path.node.kind === 'var') path.node.kind = 'let';
      },
    },
  };
};
// Babel 三步：parse（源码 → AST）→ transform（遍历修改 AST）→ generate（AST → 源码 + sourcemap）
```

### 面试答题要点

1. 先分清转译器和打包器：Babel / SWC 是转译器，Webpack / Rspack / Rollup / Rolldown 是打包器，esbuild 两者兼有。
2. Rust/Go 工具快的原因：编译型语言、多线程并行、尽量减少 AST 重复解析和序列化。
3. 选型：存量 Webpack 项目想提速优先 Rspack（迁移成本低）；新项目用 Vite；库打包用 tsup（esbuild）或 Rollup/Rolldown。
4. AST 处理三步：parse → transform → generate，Babel 插件用访问者模式。

### 易错点 / 追问

- **追问：为什么不全用 esbuild？** esbuild 对代码分割、CSS、HMR 的支持不如成熟打包器，作者也明确不打算做大而全；它适合当底层引擎。
- **易错：** 说 SWC 是打包器（它有实验性的 bundling 功能，但主要定位是转译）。

---

## 6. Tree Shaking 与 sideEffects ★★★

### 是什么 / 原理

Tree Shaking 指**删除没被用到的导出代码**。依赖 ES Module 的静态结构：`import/export` 只能出现在顶层、模块名是字符串常量，所以打包器在编译期就能知道谁用了谁。

**生效条件：**

1. 使用 **ESM**（`import/export`）。CommonJS 的 `require` 是动态的，一般无法摇树（Webpack 5 对部分 CJS 写法有有限支持）。
2. Babel 等转译器**不能把 ESM 转成 CJS**：`@babel/preset-env` 要设置 `modules: false`（现代工具链默认就是保留 ESM）。
3. 生产模式：Webpack 中 `mode: 'production'` 会开启 `usedExports`（标记未使用导出）+ Terser（真正删除）。
4. 代码没有副作用，或者通过 `sideEffects` 声明没有副作用。
5. 第三方库提供 ESM 产物（`package.json` 中有 `module` 或 `exports` 字段指向 ESM），例如用 `lodash-es` 而不是 `lodash`。

**两层机制：**

- **usedExports（导出级别）**：标记模块里哪些导出没被用到，交给压缩器删除。但压缩器只能删“确定没副作用”的代码。
- **sideEffects（模块级别）**：`package.json` 里 `"sideEffects": false` 告诉打包器“这个包的模块都没有副作用”，如果一个模块的导出都没被用到，**整个模块可以直接跳过**，连它的 import 都不用分析。

**什么是副作用：** 模块被导入时，除了导出之外还会做的事：修改全局变量、往原型上加方法、引入 CSS、执行 polyfill 等。

### 代码示例

```json
// 组件库的 package.json
{
  "name": "my-ui",
  "module": "./es/index.js",
  "sideEffects": ["**/*.css", "./es/polyfill.js"]
}
```

```js
// 会阻碍 Tree Shaking 的写法
export default { add, sub };             // 导出一个对象，打包器很难判断对象属性是否被用到
export const util = createUtil();          // 顶层函数调用，压缩器不确定 createUtil 有没有副作用

// 改进：具名导出 + 纯函数标注
export function add() {}
export const util = /*#__PURE__*/ createUtil(); // 告诉压缩器：没用到就可以删
```

### 面试答题要点

1. Tree Shaking 依赖 ESM 的静态结构，编译期确定依赖关系，CJS 基本不行。
2. Webpack 里是两步：`usedExports` 标记 + Terser 删除；`sideEffects` 可以跳过整个模块，效果更明显。
3. `sideEffects: false` 要谨慎，CSS 和 polyfill 要放进白名单数组，否则会被误删导致样式丢失。
4. 写库时：具名导出、提供 ESM 产物、声明 sideEffects、给顶层调用加 `/*#__PURE__*/`。

### 易错点 / 追问

- **易错：** 配了 `sideEffects: false` 后 `import './global.css'` 被删，线上样式丢失。
- **追问：class 的方法能摇掉吗？** 一般不能，打包器不追踪对象属性和方法级别的使用。
- **追问：`import * as utils` 还能摇树吗？** 只要用 `utils.add` 这种静态属性访问，现代打包器可以摇掉；如果是 `utils[key]` 动态访问就不行。
- **追问：barrel 文件（index.ts 统一 re-export）有什么问题？** 配合 sideEffects 可以摇掉，但开发期仍要加载和解析所有模块，影响 Vite 开发速度和测试速度。

---

## 7. Code Splitting 策略 ★★

### 是什么 / 原理

把一个大 bundle 拆成多个 chunk，按需加载，目的：**减小首屏 JS 体积**、**提高缓存命中率**（业务代码改了，第三方依赖 chunk 的 hash 不变）。

三种方式：

1. **多入口**：`entry` 配置多个，适合多页应用。
2. **动态 `import()`**：返回 Promise，打包器自动拆出异步 chunk。路由懒加载、弹窗、大型组件（编辑器、图表）的标准做法。
3. **SplitChunks**：自动提取公共依赖。

常见拆分策略：

| chunk | 内容 | 变化频率 | 缓存策略 |
|---|---|---|---|
| runtime | Webpack 运行时与 chunk 映射表 | 每次发版 | 单独抽出，避免影响其他 chunk 的 hash |
| framework | react、react-dom、vue | 很低 | 长期缓存 |
| vendor | 其他稳定的第三方依赖 | 低 | 长期缓存 |
| 大依赖单独拆 | echarts、monaco、xlsx | 低 | 只在用到的页面异步加载 |
| 路由 chunk | 每个页面 | 高 | 按需加载 |

### 代码示例

```js
// React 路由懒加载
import { lazy, Suspense } from 'react';
const Editor = lazy(() => import(/* webpackChunkName: "editor" */ './pages/Editor'));

function App() {
  return (
    <Suspense fallback={<Skeleton />}>
      <Editor />
    </Suspense>
  );
}

// 鼠标悬停时预加载，点击时就不用等待
const preloadEditor = () => import('./pages/Editor');
<Link to="/editor" onMouseEnter={preloadEditor}>编辑器</Link>;
```

```js
// webpack.config.js
module.exports = {
  optimization: {
    runtimeChunk: 'single',
    splitChunks: {
      chunks: 'all',
      cacheGroups: {
        // key 是缓存组名称，value 是匹配规则
        framework: { test: /[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/, name: 'framework', priority: 40 },
        vendor: { test: /[\\/]node_modules[\\/]/, name: 'vendor', priority: 10, minSize: 30 * 1024 },
      },
    },
  },
};
```

### 面试答题要点

1. 目标是减少首屏 JS 和提高缓存命中率，两者有时冲突：拆得太碎请求多，拆得太粗缓存失效面大。
2. 路由级懒加载是最基本的；大依赖（编辑器、图表、Excel 解析）一定要异步加载。
3. 稳定的框架代码单独拆 chunk 长期缓存；runtime 单独抽出。
4. 懒加载配合预加载（hover 预取、`<link rel="prefetch">`、空闲时预加载）避免点击时白屏等待。

### 易错点 / 追问

- **追问：拆得越细越好吗？** 不是。HTTP/2 虽然支持多路复用，但每个请求仍有开销，压缩率也会下降（小文件压缩效果差）。一般看构建分析报告（`webpack-bundle-analyzer`、`rollup-plugin-visualizer`）决定。
- **易错：** 懒加载组件没有包 `Suspense`，或者没有处理 chunk 加载失败（发版后旧 chunk 被删除）。应该在 `import()` 失败时提示刷新或自动重试。

---

## 8. 包管理：pnpm 与幽灵依赖 ★★★

### 是什么 / 原理

**npm/yarn v1 的问题：**

- npm v3+ 采用**扁平化**安装：依赖的依赖也被提升到 `node_modules` 根目录。
- **幽灵依赖（Phantom Dependency）**：你没有在 `package.json` 声明 `debug`，但因为 `express` 依赖它被提升到根目录，你的代码 `require('debug')` 也能用。某天 express 升级不再依赖 debug，你的代码就挂了。
- **依赖分身（Doppelganger）**：同一个包的不同版本无法都提升，会在不同子目录各装一份，体积膨胀，还可能出现两个单例实例。
- 每个项目都完整拷贝一份依赖，磁盘占用大。

**pnpm 的方案：内容寻址存储 + 硬链接 + 符号链接**

```text
~/.pnpm-store（全局内容寻址仓库，每个文件按内容 hash 只存一份）
        │ 硬链接（hard link，指向同一份磁盘数据，不占额外空间）
        ▼
项目/node_modules/.pnpm/
  ├── express@4.21.0/node_modules/
  │     ├── express/          ← 硬链接到 store 的真实文件
  │     └── debug  ──────────→ 符号链接到 ../../debug@2.6.9/node_modules/debug
  └── debug@2.6.9/node_modules/debug/

项目/node_modules/
  └── express ──────────────→ 符号链接到 .pnpm/express@4.21.0/node_modules/express
  （根目录只有 package.json 里声明的直接依赖，没有 debug）
```

- **硬链接**：多个项目共享 store 中同一份文件，安装快、省磁盘。
- **符号链接**：构建出严格的嵌套依赖结构，根目录只有直接依赖，**从根本上杜绝幽灵依赖**。
- Node 解析模块时会沿符号链接找到真实路径（`.pnpm/express@.../node_modules/express`），从这里往上找 `node_modules`，正好能找到 express 自己的依赖。

### 代码示例：常用命令与配置

```bash
pnpm add lodash -w                 # monorepo 根目录安装
pnpm --filter @app/web add axios   # 给某个子包安装
pnpm -r run build                  # 所有子包执行 build
pnpm why debug                     # 查为什么装了这个包
```

```yaml
# pnpm-workspace.yaml
packages:
  - 'apps/*'
  - 'packages/*'
```

```ini
# .npmrc：某些老工具依赖扁平结构时的兜底方案
# public-hoist-pattern[]=*eslint*
# shamefully-hoist=true   # 完全扁平化，会重新引入幽灵依赖问题，尽量不用
```

### 面试答题要点

1. npm 扁平化带来幽灵依赖和依赖分身问题。
2. pnpm 用全局内容寻址 store + 硬链接共享文件，安装快、省磁盘。
3. 用符号链接构建严格的依赖树，`node_modules` 根目录只有直接依赖，杜绝幽灵依赖。
4. 原生支持 workspace，是 Monorepo 的主流选择；锁文件 `pnpm-lock.yaml` 保证可复现安装。

### 易错点 / 追问

- **易错：** 把硬链接和符号链接的作用说反。硬链接是“store → 项目”共享文件内容；符号链接是“包与包之间”的依赖关系。
- **追问：硬链接为什么不能跨磁盘？** 硬链接指向同一个 inode，只能在同一文件系统内。store 和项目不在同一分区时，pnpm 会退回复制（或 reflink）。
- **追问：yarn berry 的 PnP 呢？** 不生成 `node_modules`，用 `.pnp.cjs` 映射表解析模块，同样能杜绝幽灵依赖，但对工具链兼容性要求高。

---

## 9. Monorepo ★★

### 是什么 / 原理

Monorepo 是**多个项目/包放在同一个仓库**管理。

| 维度 | Monorepo | Multirepo |
|---|---|---|
| 代码共享 | 直接引用 workspace 包，改动即时生效 | 发 npm 包，升级要发版 |
| 原子提交 | 跨包改动一次提交、一次 review | 多仓库多次提交，难以同步 |
| 统一规范 | 一套 ESLint/TS/CI 配置 | 每个仓库各自维护 |
| 缺点 | 仓库大、CI 慢、权限难以细分 | 依赖版本碎片化 |

工具分层：

- **包管理层**：pnpm workspace / yarn workspace / npm workspace，负责安装和链接。
- **任务编排层**：Turborepo、Nx。核心能力是**依赖拓扑排序**（先构建被依赖的包）、**增量构建**（只构建受影响的包，`--filter=...[origin/main]`）、**任务缓存**（输入 hash 不变就直接复用产物，支持远程缓存）。
- **发版层**：Changesets，管理各包版本号和 CHANGELOG。

### 代码示例

```json
// turbo.json（Turborepo 2.x 使用 tasks 字段，旧版是 pipeline）
{
  "tasks": {
    "build": { "dependsOn": ["^build"], "outputs": ["dist/**"] },
    "test": { "dependsOn": ["build"] },
    "dev": { "cache": false, "persistent": true }
  }
}
```

`"^build"` 表示先执行依赖包的 build。

### 面试答题要点

1. Monorepo 解决代码共享、原子提交、规范统一的问题，代价是仓库体积和 CI 复杂度。
2. 分层：pnpm workspace 管安装，Turborepo/Nx 管任务编排和缓存，Changesets 管发版。
3. 提升 CI 速度的关键：只构建受影响的包 + 任务缓存（本地 + 远程）。
4. 内部包可以直接导出 TS 源码（由使用方编译），省掉内部包的构建步骤。

### 易错点 / 追问

- **追问：Turborepo 和 Nx 的区别？** Turborepo 轻量，专注任务编排和缓存；Nx 功能更全（代码生成器、依赖图可视化、模块边界约束），学习成本更高。
- **易错：** 子包之间互相依赖形成环，拓扑排序失败。

---

## 10. 代码规范与 CI/CD ★★

### 是什么 / 原理

- **ESLint**：代码质量检查。ESLint 9 起默认使用 **flat config**（`eslint.config.js`，数组形式，不再使用 `.eslintrc` 的层叠和 `extends` 字符串）。
- **Prettier**：只管格式。和 ESLint 冲突的格式规则用 `eslint-config-prettier` 关闭。
- **Biome**：Rust 写的格式化 + lint 一体化工具，速度快，规则覆盖逐步接近 ESLint + Prettier，但插件生态较少。
- **Husky + lint-staged**：Git hook 中只检查暂存区的文件；配合 commitlint 规范提交信息。
- **CI/CD**：提交触发 lint → 类型检查 → 单测 → 构建 → 部署。
- **灰度发布**：按用户比例、白名单、地区逐步放量，观察错误率和核心指标。
- **回滚**：静态资源带 contenthash 且不删除旧版本，HTML 入口指向新版本；回滚就是把 HTML 指回旧版本（秒级），不需要重新构建。

### 代码示例

```js
// eslint.config.js（flat config）
import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import prettier from 'eslint-config-prettier';

export default [
  { ignores: ['dist/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  prettier, // 放最后，关闭和 Prettier 冲突的规则
  { rules: { 'no-console': ['warn', { allow: ['error'] }] } },
];
```

```json
// package.json
{
  "lint-staged": {
    "*.{ts,tsx}": ["eslint --fix", "prettier --write"]
  }
}
```

### 面试答题要点

1. ESLint 管质量，Prettier 管格式，用 `eslint-config-prettier` 避免冲突；ESLint 9 起是 flat config。
2. Husky + lint-staged 只检查改动文件，提交前就拦截问题；CI 里再全量检查一次兜底。
3. 前端发布的关键：HTML 不缓存（或协商缓存），静态资源 contenthash + 长期缓存 + 保留旧版本，回滚只需切 HTML。
4. 灰度：网关按 cookie/用户 ID 分流到不同版本 HTML，配合监控指标决定放量或回滚。

### 易错点 / 追问

- **追问：发版后用户报“页面白屏 / chunk 加载失败”？** 用户手里是旧 HTML，引用的旧 chunk 被删了。解法：保留旧资源一段时间；监听 chunk 加载错误后提示刷新。
- **易错：** 把 HTML 也设置成长期强缓存，导致用户拿不到新版本。

---

## 11. 微前端方案对比 ★★

### 是什么 / 原理

微前端把一个大型前端应用拆成多个**可独立开发、独立部署**的子应用，由主应用（基座）组合。适用场景：多团队协作的大型平台、技术栈迁移（老 jQuery/Angular 项目逐步迁移到 React）、整合多个已有系统。

核心问题：**应用加载**、**JS 隔离**、**CSS 隔离**、**应用通信**、**路由同步**。

| 方案 | 原理 | JS 隔离 | CSS 隔离 | 优点 | 缺点 | 适用场景 |
|---|---|---|---|---|---|---|
| iframe | 浏览器原生隔离 | 天然完全隔离 | 天然完全隔离 | 最简单、最彻底 | 弹窗无法覆盖全屏、URL 不同步、通信靠 postMessage、每次加载慢、SEO 差 | 第三方系统嵌入、对隔离要求极高 |
| qiankun（基于 single-spa） | 按 URL 加载子应用 HTML，解析出 JS/CSS 执行；子应用导出 bootstrap/mount/unmount 生命周期 | Proxy 沙箱（快照沙箱兜底） | 严格样式隔离（Shadow DOM）或 scoped CSS（加前缀） | 接入成本低，技术栈无关，国内生态成熟 | 沙箱有性能损耗和边界问题（如全局事件、部分第三方库），对 Vite 子应用的 ESM 支持需要额外插件 | 中后台整合多个已有系统 |
| Module Federation | 构建时声明 exposes/remotes，运行时动态加载远程模块并共享依赖（shared） | 无（共用一个全局环境） | 无，需要自己约定 | 模块级共享，依赖可共享（只加载一份 React），性能好 | 构建工具耦合（Webpack/Rspack，Vite 需要插件），依赖版本要协调，没有隔离 | 同技术栈团队间共享组件/页面 |
| Web Components | Custom Elements + Shadow DOM 封装子应用 | 无（同一全局） | Shadow DOM 天然隔离 | 浏览器原生标准，框架无关 | Shadow DOM 对全局样式（主题、弹窗挂 body）、事件冒泡有影响，React 18 及以前对自定义元素属性支持不完善（React 19 已改进） | 跨框架组件复用、轻量子应用 |

补充：无界（wujie）用 iframe 运行 JS + Web Components 渲染 DOM，兼顾隔离和体验；micro-app 用 Web Components 风格接入，也都是国内常见选择。Module Federation 2.0 已经独立为 `@module-federation` 系列工具，支持 Webpack、Rspack 等多种构建工具，细节以官方文档为准。

### 代码示例

```js
// qiankun 主应用
import { registerMicroApps, start } from 'qiankun';

registerMicroApps([
  { name: 'order', entry: '//localhost:7100', container: '#subapp', activeRule: '/order', props: { token } },
]);
start({ sandbox: { experimentalStyleIsolation: true } });

// 子应用入口：导出生命周期
export async function bootstrap() {}
export async function mount(props) { render(props.container); }
export async function unmount(props) { root.unmount(); }
```

```js
// Module Federation（Webpack 5）
// 远程应用：暴露组件
new ModuleFederationPlugin({
  name: 'remoteApp',
  filename: 'remoteEntry.js',
  exposes: { './Button': './src/Button' },
  shared: { react: { singleton: true }, 'react-dom': { singleton: true } },
});
// 宿主应用：引用远程
new ModuleFederationPlugin({
  name: 'host',
  remotes: { remoteApp: 'remoteApp@https://cdn.example.com/remoteEntry.js' },
  shared: { react: { singleton: true }, 'react-dom': { singleton: true } },
});
// 使用：const Button = lazy(() => import('remoteApp/Button'));
```

```js
// qiankun Proxy 沙箱的核心思路（简化）
function createSandbox() {
  const fakeWindow = {}; // 子应用对 window 的写入都落在这里
  return new Proxy(window, {
    set(target, key, value) { fakeWindow[key] = value; return true; },
    get(target, key) {
      if (key in fakeWindow) return fakeWindow[key];
      const value = target[key];
      // 原生方法需要绑定真正的 window，否则 fetch 等会报 Illegal invocation
      return typeof value === 'function' && !value.prototype ? value.bind(target) : value;
    },
  });
}
// 子应用代码被包成 (function(window){ ... })(sandboxProxy) 执行
```

### 面试答题要点

1. 先问是否真的需要微前端：多团队独立部署、技术栈迁移、整合已有系统才值得；否则 Monorepo + 组件库更简单。
2. 四大问题：加载、JS 隔离、CSS 隔离、通信。
3. iframe 隔离最彻底但体验差；qiankun 适合整合异构系统；Module Federation 适合同技术栈的模块共享；Web Components 是原生标准但对弹窗和全局样式不友好。
4. 通信建议：主应用通过 props 下发数据和方法，或者用轻量的全局事件总线，避免子应用之间直接耦合。

### 易错点 / 追问

- **追问：Proxy 沙箱和快照沙箱区别？** 快照沙箱在激活时记录 window 快照、失活时恢复，只能同时运行一个子应用；Proxy 沙箱给每个子应用一个代理对象，可以同时运行多个。
- **追问：子应用的弹窗挂到 body 上，样式隔离失效怎么办？** 组件库配置弹窗挂载容器（如 `getPopupContainer`）挂到子应用容器内。
- **易错：** 说 Module Federation 提供了沙箱隔离（它没有）。

---

# 第二部分 性能优化

## 12. 性能方法论与指标体系 ★★★

### 是什么 / 原理

性能优化回答要有闭环：**指标 → 测量 → 定位 → 优化 → 验证 → 防劣化**。

指标体系：

| 指标 | 含义 | 良好阈值 | 备注 |
|---|---|---|---|
| TTFB | 首字节时间 | ≤ 0.8s | 服务端 + 网络 |
| FCP | 首次内容绘制 | ≤ 1.8s | 第一个文本/图片出现 |
| **LCP** | 最大内容绘制 | **≤ 2.5s** | Core Web Vitals，加载体验 |
| **INP** | 交互到下一次绘制 | **≤ 200ms** | Core Web Vitals，交互响应，2024 年 3 月取代 FID |
| **CLS** | 累计布局偏移 | **≤ 0.1** | Core Web Vitals，视觉稳定性 |
| TBT | 总阻塞时间 | ≤ 200ms（Lighthouse） | 实验室指标，INP 的近似替代 |

Core Web Vitals 的阈值分三档：良好 / 需要改进 / 差。LCP：≤2.5s / ≤4s / >4s；INP：≤200ms / ≤500ms / >500ms；CLS：≤0.1 / ≤0.25 / >0.25。评估口径是**第 75 百分位（P75）**的真实用户数据。

两类数据：

- **实验室数据（Lab）**：Lighthouse、Chrome DevTools Performance 面板、WebPageTest。环境可控、可复现，适合定位问题。
- **真实用户数据（Field / RUM）**：`PerformanceObserver` + `web-vitals` 库上报、CrUX（Chrome 用户体验报告）。反映真实情况，适合评估效果。

### 代码示例

```bash
# 命令行跑 Lighthouse，模拟移动端
npx lighthouse https://example.com --preset=perf --output=html --output-path=./report.html
```

### 面试答题要点

1. 性能优化要讲方法论：先定指标和目标，再测量定位，再优化，最后用数据验证并加防劣化机制（CI 里的性能预算、监控告警）。
2. Core Web Vitals 三个指标：LCP ≤2.5s、INP ≤200ms、CLS ≤0.1，按 P75 评估。
3. 实验室数据用来定位，真实用户数据用来衡量效果，两者都要。
4. INP 在 2024 年 3 月正式取代 FID，FID 只看首次交互的输入延迟，INP 看整个页面生命周期所有交互的完整延迟。

### 易错点 / 追问

- **易错：** 把 INP 阈值说成 100ms（那是 FID 的阈值），或者说 CLS 单位是毫秒（CLS 是无单位的分数）。
- **追问：Lighthouse 分数高但用户反馈卡？** Lighthouse 是单次、模拟设备、无用户交互，测不出真实交互卡顿和低端机情况，要看 RUM 的 INP P75。

---

## 13. LCP：成因与优化 ★★★

### 是什么 / 原理

LCP（Largest Contentful Paint）是视口内**最大的图片或文本块**完成渲染的时间。候选元素：`<img>`、`<svg>` 内的 `<image>`、`<video>` 封面、带 `background-image: url()` 的元素、包含文本的块级元素。

LCP 可以拆成四段，定位问题时逐段看：

```text
LCP = TTFB                 服务端响应慢、重定向、无 CDN
    + 资源加载延迟          LCP 图片发现得太晚（被 JS 渲染、CSS 背景图、懒加载）
    + 资源加载耗时          图片太大、格式落后、带宽争抢
    + 元素渲染延迟          阻塞渲染的 CSS/JS、客户端渲染要等 JS 执行完
```

### 优化清单

| 阶段 | 优化手段 |
|---|---|
| TTFB | CDN、边缘缓存、SSR/SSG 结果缓存、减少重定向、HTTP/2/3、`103 Early Hints` |
| 加载延迟 | LCP 图片直接写在 HTML 里，不要靠 JS 插入；首屏图片**不要**加 `loading="lazy"`；加 `fetchpriority="high"`；`<link rel="preload">` 提前发现 CSS 背景图或字体 |
| 加载耗时 | 图片用 AVIF/WebP，`srcset` 按设备给尺寸，压缩；关键资源 `preconnect` 到图片 CDN |
| 渲染延迟 | 内联关键 CSS、非关键 CSS 异步加载；脚本 `defer`；SSR/流式 SSR 替代纯 CSR；减少首屏 JS 体积（拆包）；文本 LCP 注意字体阻塞（`font-display`） |

### 代码示例

```html
<head>
  <link rel="preconnect" href="https://img.example.com" crossorigin />
  <!-- 首屏大图：提前、高优先级加载 -->
  <link rel="preload" as="image" href="/hero.avif" fetchpriority="high" />
</head>
<body>
  <img src="/hero.avif" width="1200" height="600" fetchpriority="high" alt="banner" />
  <!-- 首屏以下的图片才懒加载 -->
  <img src="/item.webp" loading="lazy" width="300" height="200" alt="" />
</body>
```

### 面试答题要点

1. LCP 拆成 TTFB、加载延迟、加载耗时、渲染延迟四段，先用 DevTools 找出 LCP 元素和瓶颈段，再对症优化。
2. 最常见的问题：LCP 图片被懒加载、由 JS 渲染出来、是 CSS 背景图导致发现晚。
3. 关键手段：`fetchpriority="high"`、preload、现代图片格式、CDN、SSR、减少阻塞渲染的资源。
4. 纯客户端渲染的 SPA，LCP 要等 JS 下载 + 执行 + 请求数据后才出现，SSR 或预渲染是根本解法。

### 易错点 / 追问

- **易错：** 给所有图片都加 `loading="lazy"`，包括首屏大图，导致 LCP 变差。
- **追问：LCP 元素会变吗？** 加载过程中会不断上报更大的候选，用户首次交互（点击、按键）或页面隐藏后停止，取最后一个。

---

## 14. INP：成因与优化 ★★★

### 是什么 / 原理

INP（Interaction to Next Paint）衡量页面整个生命周期内**点击、触摸、键盘交互**到**下一帧绘制**的延迟，取最差的一次（交互次数多时会排除少量极端值，近似取第 98 百分位）。滚动和悬停不计入。

一次交互的延迟拆成三段：

```text
INP = 输入延迟（Input Delay）     主线程正忙（其他长任务在跑），事件回调要排队
    + 处理耗时（Processing Time） 事件回调本身执行慢
    + 呈现延迟（Presentation）    回调后的样式计算、布局、绘制耗时（DOM 太大、强制同步布局）
```

### 优化清单

| 阶段 | 原因 | 优化手段 |
|---|---|---|
| 输入延迟 | 首屏大量 JS 执行、定时器任务、第三方脚本占用主线程 | 拆分长任务；延后非关键脚本；第三方脚本 `defer`/延迟加载；移到 Web Worker |
| 处理耗时 | 回调里同步做大量计算、同步存储、React 大范围重渲染 | 先更新 UI 再 `yield` 做剩余工作；`useTransition`/`useDeferredValue` 降低非紧急更新优先级；`memo` 减少无效渲染；防抖节流 |
| 呈现延迟 | DOM 节点过多、布局抖动、复杂 CSS | 虚拟列表；`content-visibility: auto`；避免读写布局属性交替；减少 DOM 规模 |

### 代码示例

```js
// 反例：点击后同步做完所有事情，用户要等很久才看到反馈
button.addEventListener('click', () => {
  heavyCompute();   // 300ms
  sendAnalytics();  // 50ms
  updateUI();
});

// 正例：先给反馈，再让出主线程做剩下的工作
button.addEventListener('click', async () => {
  updateUI();             // 立即更新，下一帧就能绘制
  await yieldToMain();    // 见第 18 节
  heavyCompute();
  requestIdleCallback(() => sendAnalytics());
});
```

```jsx
// React：输入框保持响应，列表过滤作为低优先级更新
function Search({ list }) {
  const [text, setText] = useState('');
  const deferredText = useDeferredValue(text);
  const filtered = useMemo(() => list.filter((i) => i.includes(deferredText)), [list, deferredText]);
  return <><input value={text} onChange={(e) => setText(e.target.value)} /><List items={filtered} /></>;
}
```

### 面试答题要点

1. INP 衡量所有交互的完整延迟，拆成输入延迟、处理耗时、呈现延迟三段。
2. 排查：RUM 上报 INP 时带上交互目标元素和分段耗时（`web-vitals` 的 attribution 构建版本提供），找到最差交互；再在 Performance 面板复现，看长任务火焰图。
3. 核心思路是**不要长时间占用主线程**：拆长任务、先反馈后计算、重计算放 Worker、降低非紧急更新优先级。
4. 呈现阶段问题看 DOM 规模和布局抖动，用虚拟列表和 `content-visibility`。

### 易错点 / 追问

- **追问：INP 和 FID 区别？** FID 只算首次交互的输入延迟；INP 算所有交互，且包含处理和渲染时间，更全面也更难优化。
- **追问：什么是长任务？** 主线程上超过 50ms 的任务。超过 50ms 时，用户交互可能要等待超过 100ms 才被处理。

---

## 15. CLS：成因与优化 ★★★

### 是什么 / 原理

CLS（Cumulative Layout Shift）衡量**意外的布局偏移**。单次偏移分数 = **影响比例（impact fraction）× 距离比例（distance fraction）**。偏移按“会话窗口”分组：偏移之间间隔小于 1s、窗口总长不超过 5s，CLS 取**分数最大的会话窗口**的总和。

用户交互后 500ms 内发生的偏移（`hadRecentInput`）不计入，因为是用户预期中的变化。

### 常见成因与优化

| 成因 | 优化 |
|---|---|
| 图片/视频没有尺寸 | 写 `width`/`height` 属性或 CSS `aspect-ratio`，浏览器会预留空间 |
| 广告、嵌入内容、动态插入的横幅 | 预留固定尺寸的占位容器；新内容插在视口下方，或者由用户操作触发 |
| Web 字体加载导致文字重排（FOUT） | `font-display: optional`；`size-adjust`、`ascent-override` 让后备字体尺寸接近目标字体；preload 字体 |
| 异步数据加载后撑开布局 | 骨架屏尺寸与真实内容一致；`min-height` 占位 |
| 动画修改 `top`/`height` 等布局属性 | 改用 `transform` |

### 代码示例

```css
/* 不知道图片具体尺寸时，用 aspect-ratio 预留空间 */
.cover { width: 100%; aspect-ratio: 16 / 9; object-fit: cover; }

/* 后备字体尺寸贴近 Web 字体，减少字体替换时的偏移 */
@font-face {
  font-family: 'Fallback';
  src: local('Arial');
  size-adjust: 105%;
  ascent-override: 90%;
}
body { font-family: 'MyFont', 'Fallback', sans-serif; }
```

### 面试答题要点

1. CLS 是无单位分数，= 影响比例 × 距离比例，取最大会话窗口，良好阈值 ≤0.1。
2. 最常见的原因：图片没尺寸、动态插入内容、字体切换、异步内容撑开布局。
3. 核心原则：**提前预留空间**，动画只用 `transform`/`opacity`。
4. 用户交互后 500ms 内的偏移不计入，所以点击“展开”导致的布局变化不算。

### 易错点 / 追问

- **追问：SPA 路由切换会算 CLS 吗？** CLS 统计整个页面生命周期，软导航之后的偏移也会累积进来。Chrome 有软导航（Soft Navigation）相关的实验性 API，最新状态以 Chrome 官方文档为准。
- **易错：** 以为 `transform` 动画会产生 CLS（不会，它不影响布局）。

---

## 16. 用 PerformanceObserver 采集指标 ★★

### 是什么 / 原理

`PerformanceObserver` 可以订阅浏览器的性能条目（entry），常用 entryType：

| entryType | 用途 |
|---|---|
| `navigation` | 页面导航耗时（DNS、TCP、TTFB、DOMContentLoaded、load） |
| `resource` | 每个资源的加载耗时 |
| `paint` | FP、FCP |
| `largest-contentful-paint` | LCP 候选 |
| `layout-shift` | 每次布局偏移 |
| `event` | 事件耗时，用于计算 INP |
| `longtask` | 超过 50ms 的长任务 |
| `long-animation-frame` | 长动画帧（LoAF），比 longtask 提供更多归因信息（如脚本来源） |

`buffered: true` 可以拿到 observer 注册之前已经产生的条目，监控脚本加载晚也不会丢数据。

**生产环境推荐直接用 Google 的 `web-vitals` 库**（`onLCP`、`onINP`、`onCLS`），它处理了很多边界情况（bfcache 恢复、页面隐藏、INP 百分位等）。面试时手写下面的简化版，说明原理即可。

### 代码示例

```js
/**
 * 简化版 Web Vitals 采集，页面隐藏时统一上报。
 * 生产环境请使用 web-vitals 库，这里只演示原理。
 */
// 上报数据：key 是指标名，value 是数值（LCP/INP 单位 ms，CLS 无单位）
const metrics = {};

// 1. LCP：取最后一个候选
new PerformanceObserver((list) => {
  const entries = list.getEntries();
  const last = entries[entries.length - 1];
  metrics.LCP = last.startTime; // renderTime 为 0（跨域图片无 TAO 头）时 startTime 会回退到 loadTime
}).observe({ type: 'largest-contentful-paint', buffered: true });

// 2. CLS：按会话窗口累加，取最大窗口
let sessionValue = 0;
let sessionEntries = [];
new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) {
    if (entry.hadRecentInput) continue; // 用户交互后 500ms 内的偏移不计入
    const first = sessionEntries[0];
    const last = sessionEntries[sessionEntries.length - 1];
    // 与上一次偏移间隔 < 1s 且窗口总长 < 5s，归入当前窗口，否则开新窗口
    if (last && entry.startTime - last.startTime < 1000 && entry.startTime - first.startTime < 5000) {
      sessionValue += entry.value;
      sessionEntries.push(entry);
    } else {
      sessionValue = entry.value;
      sessionEntries = [entry];
    }
    metrics.CLS = Math.max(metrics.CLS || 0, sessionValue);
  }
}).observe({ type: 'layout-shift', buffered: true });

// 3. INP（简化）：同一次交互的多个事件共享 interactionId，取每次交互的最大 duration，再取最差值
// key 是 interactionId，value 是这次交互的最大耗时 ms
const interactions = new Map();
new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) {
    if (!entry.interactionId) continue; // 没有 interactionId 的不是离散交互（如 mousemove）
    const prev = interactions.get(entry.interactionId) || 0;
    interactions.set(entry.interactionId, Math.max(prev, entry.duration));
  }
  // 简化：直接取最大值；真实 INP 在交互次数多时每 50 次交互排除一次最高值
  metrics.INP = Math.max(...interactions.values());
}).observe({ type: 'event', durationThreshold: 40, buffered: true });

// 4. 长任务：记录数量和总阻塞时间
new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) {
    metrics.longTaskCount = (metrics.longTaskCount || 0) + 1;
    metrics.TBT = (metrics.TBT || 0) + (entry.duration - 50);
  }
}).observe({ type: 'longtask', buffered: true });

// 5. TTFB
const [nav] = performance.getEntriesByType('navigation');
if (nav) metrics.TTFB = nav.responseStart;

// 上报：页面切到后台时用 sendBeacon，比 unload 可靠，也不会阻塞页面关闭
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') {
    navigator.sendBeacon('/api/perf', JSON.stringify({ url: location.href, ...metrics }));
  }
});
```

```js
// 生产写法：web-vitals 库
import { onLCP, onINP, onCLS } from 'web-vitals';
const report = (metric) => navigator.sendBeacon('/api/perf', JSON.stringify(metric));
onLCP(report);
onINP(report);
onCLS(report);
```

### 面试答题要点

1. 用 `PerformanceObserver` 订阅 `largest-contentful-paint`、`layout-shift`、`event` 等条目，`buffered: true` 防止漏掉早期数据。
2. LCP 取最后一个候选；CLS 按会话窗口取最大；INP 按 `interactionId` 聚合后取接近最差的值。
3. 上报时机用 `visibilitychange` 的 hidden + `sendBeacon`，不要依赖 `unload`（移动端不可靠，还会阻止 bfcache）。
4. 生产环境用 `web-vitals` 库，上报时带上页面、设备、网络类型、版本号等维度，方便分析 P75。

### 易错点 / 追问

- **易错：** 用 `performance.timing`（已废弃），应该用 `PerformanceNavigationTiming`。
- **追问：跨域资源的详细耗时拿不到？** 需要资源服务器返回 `Timing-Allow-Origin` 响应头。
- **追问：`longtask` 和 LoAF 的区别？** longtask 只告诉你“有个长任务”，LoAF 能告诉你这一帧里哪些脚本（URL、函数名）占了多久，更适合定位 INP 问题。

---

## 17. 虚拟列表手写 ★★★

### 是什么 / 原理

长列表（上万条）全部渲染会导致 DOM 节点过多，首次渲染慢、滚动卡、内存高。**虚拟列表**只渲染可视区域（加上下缓冲区）内的元素：

```text
容器（固定高度，overflow: auto，监听 scroll）
 ├── 占位层（高度 = 总条数 × 单项高度，撑出滚动条）
 └── 内容层（绝对定位，translateY(startIndex × 单项高度)）
       └── 只渲染 [startIndex, endIndex) 区间的元素

startIndex = floor(scrollTop / itemHeight) - buffer
endIndex   = startIndex + ceil(容器高度 / itemHeight) + 2 × buffer
```

### 代码示例：定高虚拟列表（React）

```jsx
import { useState, useRef } from 'react';

/**
 * 定高虚拟列表。
 * @param {object} props
 * @param {Array<{id: string|number, text: string}>} props.items 全部数据
 * @param {number} props.itemHeight 每一项的固定高度（px）
 * @param {number} props.height 可视容器高度（px）
 * @param {number} [props.buffer=5] 上下各多渲染几项，避免快速滚动时出现空白
 */
export function VirtualList({ items, itemHeight, height, buffer = 5 }) {
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef(null);

  // 根据滚动位置计算需要渲染的区间
  const visibleCount = Math.ceil(height / itemHeight);
  const start = Math.max(0, Math.floor(scrollTop / itemHeight) - buffer);
  const end = Math.min(items.length, start + visibleCount + buffer * 2);
  const visibleItems = items.slice(start, end);

  return (
    <div
      ref={containerRef}
      style={{ height, overflowY: 'auto', position: 'relative' }}
      onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
    >
      {/* 占位层：撑出完整滚动高度 */}
      <div style={{ height: items.length * itemHeight }} />
      {/* 内容层：整体平移到 start 所在位置 */}
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, transform: `translateY(${start * itemHeight}px)` }}>
        {visibleItems.map((item) => (
          <div key={item.id} style={{ height: itemHeight, boxSizing: 'border-box' }}>{item.text}</div>
        ))}
      </div>
    </div>
  );
}
```

### 不定高虚拟列表思路

```js
/**
 * 不定高：先用预估高度，渲染后用 ResizeObserver 测量真实高度并修正位置表。
 * positions[i] = { top, height, bottom }，scrollTop 对应的起始索引用二分查找。
 */
function findStartIndex(positions, scrollTop) {
  let lo = 0;
  let hi = positions.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (positions[mid].bottom <= scrollTop) lo = mid + 1;
    else hi = mid;
  }
  return lo; // 第一个 bottom > scrollTop 的元素
}
// 某一项真实高度测出来后：更新它的 height，并把后面所有项的 top/bottom 加上差值，再更新占位层总高度
```

### 面试答题要点

1. 原理：只渲染可视区域 + 缓冲区，用占位元素撑开滚动高度，用 `transform` 把内容层移到正确位置。
2. 定高时用除法算索引；不定高时用预估高度 + 渲染后测量（ResizeObserver）+ 位置表 + 二分查找。
3. 优化点：上下缓冲区防白屏；scroll 回调用 `requestAnimationFrame` 节流；`key` 用稳定 id；滚动时可以暂停图片加载。
4. 生产中用成熟库：`@tanstack/react-virtual`、`react-window`、`vue-virtual-scroller`，不需要重复造轮子。
5. 替代方案：`content-visibility: auto` 让浏览器跳过屏幕外元素的渲染，实现简单，但 DOM 节点仍然存在。

### 易错点 / 追问

- **追问：不定高时滚动条跳动怎么办？** 预估高度尽量接近真实平均值；测量后修正时，如果修正的项在视口上方，要同步调整 scrollTop 保持锚点不动。
- **追问：Ctrl+F 搜索不到未渲染的内容？** 这是虚拟列表的固有缺点，`content-visibility: auto` 可以被页面内搜索找到。
- **易错：** 用 index 当 key，滚动时组件复用错乱。

---

## 18. 长任务拆分 ★★★

### 是什么 / 原理

主线程上超过 50ms 的任务就是长任务。长任务执行期间浏览器无法响应用户输入和渲染，直接导致 INP 变差和卡顿。

拆分方式：

| 方式 | 说明 |
|---|---|
| `setTimeout(fn, 0)` | 让出主线程，兼容性最好；但新任务排到队尾，且嵌套多层后有 4ms 最小延迟 |
| `scheduler.yield()` | 让出主线程，并且**继续执行的任务优先级更高**（排在队首附近），不会被其他任务插队太久。Chrome 129 起支持，其他浏览器支持情况以 MDN 为准，需要降级 |
| `scheduler.postTask(fn, { priority })` | 按优先级（`user-blocking` / `user-visible` / `background`）调度任务 |
| `requestIdleCallback` | 浏览器空闲时执行，适合上报、预加载等低优先级工作 |
| Web Worker | 把纯计算（解析大文件、加密、图像处理）移出主线程 |
| 时间切片 | 每处理一批检查已用时间，超过约 5ms 就让出（React Scheduler 的思路） |

### 代码示例

```js
/**
 * 让出主线程：优先使用 scheduler.yield，不支持时降级到 setTimeout。
 * @returns {Promise<void>}
 */
function yieldToMain() {
  if (globalThis.scheduler?.yield) return scheduler.yield();
  return new Promise((resolve) => setTimeout(resolve, 0));
}

/**
 * 分批处理大量数据，每批执行超过 deadlineMs 就让出主线程。
 * @template T
 * @param {T[]} items 待处理数据
 * @param {(item: T) => void} handler 单条处理函数
 * @param {number} [deadlineMs=5] 每段连续执行的最长时间
 */
async function processInChunks(items, handler, deadlineMs = 5) {
  let lastYield = performance.now();
  for (const item of items) {
    handler(item);
    // 超过时间预算就让出，给渲染和用户输入机会
    if (performance.now() - lastYield > deadlineMs) {
      await yieldToMain();
      lastYield = performance.now();
    }
  }
}
```

```js
// Web Worker：把 CSV 解析移出主线程
// main.js
const worker = new Worker(new URL('./parse.worker.js', import.meta.url), { type: 'module' });
worker.postMessage(file);
worker.onmessage = (e) => renderTable(e.data);

// parse.worker.js
self.onmessage = async (e) => {
  const text = await e.data.text();
  self.postMessage(text.split('\n').map((line) => line.split(',')));
};
```

### 面试答题要点

1. 长任务是主线程上超过 50ms 的任务，会阻塞交互和渲染，是 INP 差的主要原因。
2. 拆分：时间切片 + 让出主线程；`scheduler.yield()` 比 `setTimeout` 好在继续执行的任务优先级更高，需要降级处理。
3. 纯计算放 Web Worker；低优先级任务用 `requestIdleCallback`。
4. React 的并发渲染（`useTransition`）本质也是时间切片，框架层已经帮你拆分了渲染任务。

### 易错点 / 追问

- **追问：为什么不用 `Promise.resolve().then()` 让出？** 微任务会在当前任务结束前全部执行完，**不会**让出给渲染和输入，起不到拆分作用。
- **追问：Worker 传大数据慢怎么办？** 用 Transferable（`postMessage(buf, [buf])`）转移 ArrayBuffer 所有权，零拷贝。
- **易错：** 以为 `requestAnimationFrame` 能拆分长任务。它只是在下一帧渲染前执行，回调里的工作仍然会阻塞那一帧。

---

## 19. 图片与字体优化 ★★

### 是什么 / 原理

**图片**通常是页面最大的资源，也最常是 LCP 元素。

| 手段 | 说明 |
|---|---|
| 现代格式 | AVIF（压缩率最高，编码慢）> WebP > JPEG/PNG；用 `<picture>` 按支持情况降级 |
| 响应式尺寸 | `srcset` + `sizes` 让浏览器按屏幕宽度和 DPR 选合适尺寸 |
| 懒加载 | 首屏以下图片用 `loading="lazy"`，首屏图片不要用 |
| 优先级 | LCP 图片 `fetchpriority="high"` |
| 尺寸占位 | `width`/`height` 或 `aspect-ratio`，防 CLS |
| 解码 | `decoding="async"` 避免同步解码阻塞 |
| CDN 处理 | 图片 CDN 按参数实时裁剪、转码、压缩 |
| 小图标 | SVG 或 icon font，减少请求；极小图片可以内联 base64（会增大 HTML/CSS 体积，要权衡） |

**字体**问题：字体下载完之前文字可能不可见（FOIT）或者先用后备字体显示再替换（FOUT，可能造成 CLS）。

| 手段 | 说明 |
|---|---|
| `font-display` | `swap`：先显示后备字体，下载完替换（FCP 快，可能偏移）；`optional`：很短时间内没下载完就本次不用（无偏移，适合正文）；`block`：短时间隐藏文字 |
| 子集化 | 中文字体动辄几 MB，按页面实际用字裁剪（`fonttools`、`glyphhanger`），或用 `unicode-range` 分片加载 |
| WOFF2 | 压缩率最好的字体格式 |
| preload | 关键字体 `<link rel="preload" as="font" type="font/woff2" crossorigin>` |
| 后备字体匹配 | `size-adjust` 等描述符减少替换时的布局偏移 |

### 代码示例

```html
<picture>
  <source type="image/avif" srcset="/a-480.avif 480w, /a-960.avif 960w" sizes="(max-width: 600px) 100vw, 50vw" />
  <source type="image/webp" srcset="/a-480.webp 480w, /a-960.webp 960w" sizes="(max-width: 600px) 100vw, 50vw" />
  <img src="/a-960.jpg" width="960" height="540" alt="商品图" loading="lazy" decoding="async" />
</picture>

<!-- 字体 preload 必须带 crossorigin，否则会下载两次 -->
<link rel="preload" href="/fonts/brand.woff2" as="font" type="font/woff2" crossorigin />
```

```css
@font-face {
  font-family: 'Brand';
  src: url('/fonts/brand.woff2') format('woff2');
  font-display: swap;
  unicode-range: U+0000-00FF; /* 只有页面出现这个范围的字符才下载 */
}
```

### 面试答题要点

1. 图片：现代格式（AVIF/WebP）+ 响应式尺寸（srcset/sizes）+ 首屏以下懒加载 + 首屏大图高优先级 + 预留尺寸。
2. 字体：WOFF2 + 子集化（中文尤其重要）+ preload 关键字体 + 合适的 `font-display`。
3. `font-display: swap` 有利于 FCP 但可能带来 CLS，用后备字体尺寸匹配缓解；`optional` 无偏移但可能本次不显示 Web 字体。
4. 量化：优化前后对比图片总字节数和 LCP 变化。

### 易错点 / 追问

- **易错：** 字体 preload 漏了 `crossorigin`，导致浏览器下载两次。
- **追问：`srcset` 的 `w` 和 `x` 描述符区别？** `w` 描述图片本身宽度，配合 `sizes` 让浏览器计算；`x` 描述像素密度，适合固定显示尺寸的图片。

---

## 20. 缓存、预加载与渲染优化补充 ★★

### 是什么 / 原理

**HTTP 缓存策略：**

| 资源 | 策略 |
|---|---|
| HTML | `Cache-Control: no-cache`（每次协商）或很短的 max-age |
| 带 contenthash 的 JS/CSS/图片 | `Cache-Control: public, max-age=31536000, immutable` |
| 接口 | 按业务，多数 `no-store`；可缓存的配置类接口用 ETag |

**资源提示：**

| 提示 | 作用 | 使用场景 |
|---|---|---|
| `dns-prefetch` | 提前 DNS 解析 | 第三方域名 |
| `preconnect` | 提前 DNS + TCP + TLS | 首屏马上要用的关键域名（不要太多，会占连接） |
| `preload` | 当前页面马上要用的资源，高优先级 | LCP 图片、关键字体、关键 CSS |
| `prefetch` | 下一个页面可能用的资源，空闲时低优先级 | 下一步路由的 chunk |
| `modulepreload` | 预加载 ES 模块并解析 | Vite 产物自动注入 |
| Speculation Rules | 浏览器预取/预渲染整个下一页 | 多页应用的高概率跳转（Chromium 支持，以官方为准） |

**渲染优化：**

- 避免**强制同步布局**：在同一帧里先写样式再读 `offsetHeight` 等布局属性，浏览器被迫立即重排。应该先批量读、再批量写。
- 动画用 `transform`/`opacity`，只触发合成，不触发布局和绘制；`will-change` 只给确实要动画的元素用。
- `content-visibility: auto` + `contain-intrinsic-size`：屏幕外区域跳过渲染。
- 骨架屏：提升感知速度，尺寸要与真实内容一致，避免 CLS。
- SSR / 流式渲染：服务端先发送 HTML 外壳，数据就绪的部分逐步流式输出（React 18+ `renderToPipeableStream` + Suspense）。

### 代码示例

```js
// 反例：读写交替，每次循环都触发重排（布局抖动）
items.forEach((el) => { el.style.width = el.parentNode.offsetWidth / 2 + 'px'; });

// 正例：先批量读，再批量写
const widths = items.map((el) => el.parentNode.offsetWidth);
items.forEach((el, i) => { el.style.width = widths[i] / 2 + 'px'; });
```

```css
.feed-section { content-visibility: auto; contain-intrinsic-size: auto 800px; }
```

### 面试答题要点

1. 缓存：HTML 协商缓存，带 hash 的静态资源一年强缓存 + immutable。
2. preload 用于当前页面关键资源，prefetch 用于未来页面，preconnect 用于关键第三方域名；滥用 preload 会和真正关键的资源抢带宽。
3. 渲染：批量读写避免布局抖动，动画只用 transform/opacity，`content-visibility` 跳过屏外渲染。
4. SSR/流式渲染改善 FCP/LCP，但要关注 TTFB 和水合（hydration）成本，水合期间页面可能不可交互。

### 易错点 / 追问

- **追问：重排和重绘区别？** 重排（Reflow/Layout）是几何信息变化，需要重新计算布局；重绘（Repaint）是只有颜色等外观变化。重排一定导致重绘，反之不一定。
- **易错：** 给大量元素加 `will-change`，导致图层过多、内存暴涨。

---

## 21. 内存泄漏排查 ★★

### 是什么 / 原理

常见泄漏来源：

1. 未清理的定时器、事件监听（尤其是 `window`/`document` 上的）、`ResizeObserver`/`IntersectionObserver`。
2. 闭包长期持有大对象。
3. 脱离 DOM 树但仍被 JS 引用的节点（Detached DOM）。
4. 全局变量、无限增长的缓存 Map。
5. 未取消的请求、WebSocket、订阅（RxJS、EventEmitter）。

排查步骤：

```text
1. Performance 面板勾选 Memory，录制反复操作（如打开关闭弹窗 10 次），看 JS Heap 是否阶梯上涨不回落
2. Memory 面板：操作前拍 Heap Snapshot → 反复操作 → 手动 GC → 再拍快照
3. 用 Comparison 视图看新增对象；搜索 "Detached" 找脱离文档的 DOM
4. 看 Retainers（引用链）找到是谁持有了对象 → 定位代码
```

### 代码示例

```jsx
// React 中清理副作用
useEffect(() => {
  const onResize = () => setWidth(window.innerWidth);
  window.addEventListener('resize', onResize);
  const controller = new AbortController();
  fetch('/api/data', { signal: controller.signal }).then(/* ... */);
  return () => {
    window.removeEventListener('resize', onResize);
    controller.abort(); // 组件卸载时取消请求
  };
}, []);

// 缓存用 WeakMap：key 被回收后条目自动消失（key 是 DOM 节点，value 是其附加数据）
const nodeData = new WeakMap();
```

### 面试答题要点

1. 常见来源：定时器和监听未清理、闭包、Detached DOM、全局缓存无限增长。
2. 排查：Performance 面板看内存趋势，Heap Snapshot 对比两次快照，看 Retainers 引用链。
3. 预防：组件卸载时清理副作用；缓存设置上限（LRU）或用 WeakMap/WeakRef。
4. Node 服务端泄漏同理，用 `--inspect` 连 DevTools 拍快照，或 `heapdump`。

### 易错点 / 追问

- **追问：WeakMap 为什么不能遍历？** key 随时可能被 GC 回收，遍历结果不确定，所以规范不提供遍历方法。
- **易错：** 以为 `console.log` 打印的对象不会泄漏。DevTools 打开时控制台会持有引用。

---

## 22. 「首屏优化」STAR 示范回答 ★★★

> 题目：“讲一个你做过的性能优化，首屏从 4s 优化到 1s 你做了什么？”
> 面试官想听的是：有基线数据、有定位过程、有优先级判断、有量化结果、有防劣化机制。以下是示范，**数据要换成你项目里真实的数据**，不要背虚构数字。

**S（背景）**
我们是一个 B 端电商运营后台，React 单页应用。随着功能增多，首屏 JS 涨到了 2.3MB（gzip 后约 700KB）。RUM 数据显示移动端 4G 用户 LCP 的 P75 是 4.2s，业务反馈首页跳出率比较高。

**T（目标）**
两个月内把 LCP P75 降到 2.5s 以内（达到 Core Web Vitals 良好标准），并且建立防劣化机制。

**A（行动）**

1. **测量与定位**：用 Lighthouse 和 Performance 面板分析 LCP 四段耗时：TTFB 约 600ms，主要瓶颈在渲染延迟：要等 700KB JS 下载、解析执行完，再请求首页数据，LCP 的 banner 图才开始加载。用 bundle analyzer 发现 echarts、富文本编辑器、moment 全量语言包都打进了首屏包。
2. **减少首屏 JS**（收益最大，先做）：
   - 路由级懒加载，echarts 和编辑器改为动态 `import()`；
   - moment 换 dayjs，lodash 换 lodash-es 按需引入，修复组件库的 sideEffects 配置让 Tree Shaking 生效；
   - 首屏 JS 从 700KB 降到 220KB（gzip）。
3. **LCP 资源提前**：banner 图原来是 JS 渲染的 CSS 背景图，改成 HTML 中的 `<img>` + `fetchpriority="high"` + preload；图片转 AVIF/WebP 并按屏幕宽度出尺寸，体积从 380KB 降到 60KB。
4. **数据请求并行化**：首页接口原来在组件 mount 后才发，改成在入口文件里尽早发出（和 JS chunk 加载并行），页面渲染时直接用；结果写入本地缓存，二次访问先展示缓存再刷新。
5. **网络与缓存**：静态资源上 CDN、contenthash + 一年强缓存，HTML 协商缓存；对图片 CDN 加 preconnect。
6. **体验兜底**：首屏骨架屏和真实布局尺寸一致，同时修复了图片无尺寸导致的 CLS。

**R（结果）**

- LCP P75 从 4.2s 降到 1.6s，CLS 从 0.18 降到 0.03，首屏 JS 减少约 70%；
- 首页跳出率下降约 X 个百分点（用你真实的业务数据）；
- **防劣化**：CI 中加入 bundle size 预算（超过阈值阻断合入），RUM 看板按版本对比 LCP/INP，P75 超阈值自动告警；整理成团队的性能检查清单。

**可能的追问与回答思路**

- “为什么先做 JS 拆分？” —— 从 LCP 分段看渲染延迟占比最大，而且根本原因是 CSR 要等 JS，拆包投入小收益大。
- “为什么没上 SSR？” —— 后台系统 SEO 需求低，SSR 需要 Node 服务和运维成本；优化后已经达标，SSR 作为后续备选。如果是 C 端首页，SSR/SSG 会是优先方案。
- “怎么确认优化是有效的而不是波动？” —— 按发版前后对比 RUM 的 P75，并分设备、网络维度看；同时用 Lighthouse 在固定环境多次测量取中位数。

### 面试答题要点

1. 先给基线数据和业务影响，再给目标，目标最好对标行业标准（Core Web Vitals）。
2. 行动要体现**定位过程**（LCP 分段、bundle 分析）和**优先级判断**（先做收益最大的）。
3. 结果要量化，并且有防劣化机制（性能预算、监控告警）。
4. 准备好“为什么这么做 / 为什么没做 X”的取舍回答。

### 易错点 / 追问

- **易错：** 只罗列优化手段（“我用了懒加载、压缩、CDN……”），没有数据、没有定位过程、没有优先级，听起来像背书。
- **易错：** 数字前后矛盾，或者说不清楚是 P75 还是平均值、是实验室还是线上数据。面试官很容易追问到细节。
