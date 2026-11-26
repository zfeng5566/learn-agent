# 05 工程化：Maven、日志、Lombok 与单元测试

> [← 总纲](./00-outline.md) | [上一章：并发编程](./04-concurrency.md) | [下一章：Spring 核心](./06-spring-core.md)

---

## 1. 本章地图

前四章讲的是「一段 Java 代码怎么写、怎么跑」。但真实项目从来不是一个 `.java` 文件，而是：

- 几十个三方依赖，版本互相打架；
- 几百个类，要编译、测试、打包成一个可部署产物；
- 跑在服务器上，出了问题只能靠日志定位；
- 多人协作，要有统一规范、要有单测兜底。

这些就是**工程化**。它在全景图中的位置是「JVM 进程的外壳」：

```
          ┌───────────────────── 开发期 ─────────────────────┐
 SDKMAN ─▶ JDK 21 ─▶ IDEA 编写/调试 ─▶ Maven 编译·测试·打包 ─▶ mini-mall.jar
          └──────────────────────────────────────────────────┘
                                                                │ java -jar
          ┌───────────────────── 运行期 ─────────────────────┐ ▼
          │  JVM 进程 ── SLF4J ─▶ Logback ─▶ 控制台 / 滚动日志文件 ─▶ ELK(12 章) │
          └──────────────────────────────────────────────────┘
```

| 小节 | 解决的问题 | 前端对应物 |
|---|---|---|
| 开发环境 | JDK 版本管理、IDE 与调试 | nvm、VS Code、Chrome DevTools |
| Maven | 依赖、构建、打包、多模块 | npm/pnpm、package.json、webpack/vite build |
| 规范 | 目录、包名、代码风格 | ESLint、Prettier |
| Lombok | 消灭样板代码 | TS 的简写语法、装饰器 |
| 日志 | 线上可观测 | console.log + Sentry |
| 单元测试 | 质量兜底 | Jest / Vitest |

本章结束时，你会得到一个**能编译、能打包、有日志、有单测**的 mini-mall 骨架。

---

## 2. 前端类比

先用一张表把你脑子里已有的东西挂上钩，后面逐个拆差异：

| 前端 | Java | 一句话差异 |
|---|---|---|
| `nvm use 20` / `.nvmrc` | `sdk use java 21.0.5-tem` / `.sdkmanrc` | 几乎一样 |
| npm registry / 淘宝镜像 | Maven Central / 阿里云镜像 | 一样是「中央仓 + 镜像」 |
| Verdaccio 私有 npm | Nexus 私服 | 公司内部包发到私服 |
| `node_modules`（每个项目一份） | `~/.m2/repository`（全机器共享一份） | Java 不会在项目里复制依赖 |
| `package.json` | `pom.xml` | XML，且有坐标 GAV |
| `package-lock.json` | **没有** | 靠「固定版本 + dependencyManagement/BOM」 |
| `dependencies` / `devDependencies` | scope：`compile` / `test` / `provided` / `runtime` | 粒度更细 |
| `peerDependencies` | `provided` + BOM 对齐 | 不完全等价 |
| `npm run build` | `mvn clean package` | 阶段固定，不能随便起名 |
| `npm publish` | `mvn deploy` | 发布到私服 |
| `npm link` | `mvn install` | 装到本地仓库供其他项目引用 |
| pnpm workspace | Maven 多模块 | parent + modules |
| `dist/` | `target/` | 构建输出目录 |
| `console.log` | `log.info(...)`（SLF4J） | 有级别、有格式、可落盘滚动 |
| Jest：`describe` / `it` / `jest.mock` | JUnit5：`@Nested` / `@Test`；Mockito：`@Mock` | 几乎一一对应 |
| ESLint / Prettier | Checkstyle、阿里 P3C / Spotless | 一样在 CI 卡口 |

> 关键心态转变：前端工程化的痛点多在「构建产物体积、兼容性」；Java 工程化的痛点多在「**依赖冲突**」和「**线上没日志**」。前者靠工具链，后者靠规范。

---

## 3. 核心概念

### 3.1 开发环境

#### 3.1.1 SDKMAN 管理 JDK（≈ nvm）

```bash
# 安装 SDKMAN
curl -s "https://get.sdkman.io" | bash
source "$HOME/.sdkman/bin/sdkman-init.sh"

sdk list java                     # 列出可装的 JDK（多个发行版）≈ nvm ls-remote
sdk install java 21.0.5-tem       # 装 Temurin 21           ≈ nvm install 20
sdk install java 8.0.422-tem      # 维护老项目也要 Java 8
sdk use java 8.0.422-tem          # 当前 shell 临时切换      ≈ nvm use
sdk default java 21.0.5-tem       # 设为默认                ≈ nvm alias default
sdk current java                  # 查看当前版本
sdk install maven                 # Maven 也能用它装
```

项目级固定版本（≈ `.nvmrc`）：

```bash
# 在项目根目录生成 .sdkmanrc，内容如：java=21.0.5-tem
sdk env init
# 进入目录后执行，切换到该项目声明的版本
sdk env
# 想要「cd 进目录自动切换」：在 ~/.sdkman/etc/config 里设 sdkman_auto_env=true
```

JDK 发行版怎么选？它们都来自 OpenJDK 源码，差别在构建与支持方：

| 发行版 | 标识 | 说明 |
|---|---|---|
| Eclipse Temurin | `-tem` | 社区首选，默认选它 |
| Amazon Corretto | `-amzn` | AWS 环境常用 |
| Alibaba Dragonwell | `-albba` | 阿里内部优化版 |
| GraalVM | `-graal` | 支持 Native Image（AOT 编译） |
| Oracle JDK | `-oracle` | 注意商用许可条款 |

> `JAVA_HOME` 是 Java 世界的「Node 路径」：Maven、IDEA、各种脚本都靠它找 JDK。SDKMAN 切换时会自动改它，`echo $JAVA_HOME` 确认。

#### 3.1.2 IntelliJ IDEA（≈ VS Code + 很多插件）

Java 项目强烈建议用 IDEA（社区版免费够用）。它的价值是**静态类型带来的重构能力**——VS Code 写 TS 也有，但 IDEA 对 Java 的深度远超。

| 操作 | IDEA（macOS） | VS Code 对应 |
|---|---|---|
| 全局搜索任何东西 | 双击 `Shift` | `Cmd+P` |
| 跳转定义 / 找实现 | `Cmd+B` / `Cmd+Opt+B` | `F12` / `Cmd+F12` |
| 查找所有调用方 | `Opt+F7` | `Shift+F12` |
| 重命名（跨文件安全） | `Shift+F6` | `F2` |
| 自动修复/导入 | `Opt+Enter` | `Cmd+.` |
| 生成 getter/构造器/测试 | `Cmd+N` | — |
| 抽取方法/变量 | `Cmd+Opt+M` / `Cmd+Opt+V` | 重构菜单 |
| 格式化 | `Cmd+Opt+L` | `Shift+Opt+F` |
| 查看类结构 | `Cmd+F12` | 大纲视图 |
| 类继承关系 | `Ctrl+H` | — |

必装/必开：

- **Lombok 插件**（新版已内置）+ `Settings → Build → Compiler → Annotation Processors → Enable`；
- **Maven 面板**（右侧边栏）：点一下就能跑生命周期阶段，看依赖树；
- **Alibaba Java Coding Guidelines** 插件（P3C 规约实时提示）。

#### 3.1.3 调试：对照 Chrome DevTools

| 能力 | Chrome DevTools | IDEA Debugger |
|---|---|---|
| 行断点 | 点行号 | 点行号 |
| 条件断点 | 右键 → Add conditional breakpoint | 右键断点 → Condition：`orderNo.equals("A001")` |
| 日志断点（不暂停） | Logpoint | 断点取消 Suspend，勾选 Evaluate and log |
| 异常时暂停 | Pause on exceptions | `Cmd+Shift+F8` → Java Exception Breakpoints |
| 控制台求值 | Console | `Opt+F8` Evaluate Expression（可调方法、改变量） |
| 单步 / 进入 / 跳出 | F10 / F11 / Shift+F11 | F8 / F7 / Shift+F8 |
| 回退栈帧 | Restart frame | Reset Frame（Drop Frame） |
| 远程调试 | `node --inspect=9229` | JVM 加 `-agentlib:jdwp=...`，IDEA 建 Remote JVM Debug |

远程调试（测试环境排查神器，**生产禁用**）：

```bash
# ≈ node --inspect=0.0.0.0:9229 app.js
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005 -jar mini-mall.jar
# suspend=y 会等调试器连上才启动，适合调启动过程
```

> 多线程调试小技巧：断点右键把 Suspend 从 `All` 改为 `Thread`，只暂停命中线程，其他请求照常处理——这是单线程 JS 里不需要考虑的事。

---

### 3.2 Maven 核心

#### 3.2.1 坐标 GAV

npm 包靠「名字」唯一定位（`lodash`、`@scope/pkg`）；Maven 靠三元组 **GAV**：

```
groupId     : com.baomidou                    ← 组织，反向域名      ≈ npm 的 @scope
artifactId  : mybatis-plus-spring-boot3-starter ← 包名              ≈ 包名
version     : 3.5.9                           ← 版本                ≈ version
```

写成一行：`com.baomidou:mybatis-plus-spring-boot3-starter:3.5.9`。在本地仓库里就对应路径：

```
~/.m2/repository/com/baomidou/mybatis-plus-spring-boot3-starter/3.5.9/
    ├── mybatis-plus-spring-boot3-starter-3.5.9.jar   ← 字节码
    ├── mybatis-plus-spring-boot3-starter-3.5.9.pom   ← 它自己的依赖声明
    └── ...-sources.jar                               ← 源码（IDEA 可下载）
```

另外两个可选维度：`packaging`（jar / war / pom）与 `classifier`（同一版本的变体，如 `sources`、`jdk8`）。

#### 3.2.2 pom.xml 逐段对照 package.json

```jsonc
// package.json
{
  "name": "mini-mall",                       // ≈ artifactId
  "version": "0.0.1",                        // ≈ version
  "description": "简易电商",                  // ≈ description
  "engines": { "node": ">=20" },             // ≈ <java.version>
  "scripts": { "build": "vite build" },      // ≈ 生命周期 + <build><plugins>
  "dependencies": { "axios": "^1.7.0" },     // ≈ <dependencies> scope=compile
  "devDependencies": { "jest": "^29.0.0" },  // ≈ scope=test
  "workspaces": ["packages/*"]               // ≈ <modules>
}
```

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <!-- 继承：≈ tsconfig 的 extends，复用父 pom 的版本管理和插件配置 -->
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.1</version>
    </parent>

    <!-- 坐标：≈ name + version（groupId 为 npm 没有的「组织」维度） -->
    <groupId>com.example</groupId>
    <artifactId>mini-mall</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <description>简易电商</description>

    <!-- 属性：≈ 在 package.json 里放变量（npm 没有这能力），在下文用 ${java.version} 引用 -->
    <properties>
        <java.version>21</java.version>
    </properties>

    <!-- 依赖：≈ dependencies + devDependencies（靠 scope 区分） -->
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
            <!-- 没写 version：由 parent 的 dependencyManagement 统一给出 -->
        </dependency>
    </dependencies>

    <!-- 构建：≈ scripts + 打包工具配置 -->
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

几个**和 npm 不同的地方**：

1. **版本没有 `^`/`~`**。Maven 虽然支持范围语法 `[1.0,2.0)`，但业界**一律写死版本**——这也是没有 lockfile 也能复现构建的原因。
2. **不写 version 是常态**。版本统一交给 parent/BOM 管理，子依赖只写 GA。
3. **XML 冗长但结构固定**，IDEA 里 `Cmd+N → Add dependency` 搜索补全即可，不必手敲。

#### 3.2.3 仓库体系：本地 / 中央 / 私服 / 镜像

```
            mvn compile 需要 jackson-databind:2.18.2
                         │
                         ▼
     ① 本地仓库 ~/.m2/repository  ──有──▶ 直接用（全机器共享，不像 node_modules 每项目一份）
                         │ 没有
                         ▼
     ② settings.xml 里的 mirror（如阿里云 / 公司 Nexus）
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
   Nexus 私服 group 仓库         Maven Central（repo.maven.apache.org）
   ├─ hosted-releases  公司正式包
   ├─ hosted-snapshots 公司快照包
   └─ proxy-central    代理中央仓（带缓存）
                         │
                         ▼
                下载后存入本地仓库
```

| npm | Maven | 配置位置 |
|---|---|---|
| `~/.npmrc` 的 `registry=` | `~/.m2/settings.xml` 的 `<mirrors>` | 用户级 |
| 项目 `.npmrc` | pom 中 `<repositories>`（不推荐，统一走 settings） | 项目级 |
| `npm login` 的 token | `settings.xml` 的 `<servers>` | 用户级，**不要进 git** |
| `publishConfig.registry` | pom 中 `<distributionManagement>` | 项目级 |

`~/.m2/settings.xml` 示例：

```xml
<settings>
    <!-- 私服账号：id 要与 mirror / distributionManagement 中的 id 对应 -->
    <servers>
        <server>
            <id>company-nexus</id>
            <username>${env.NEXUS_USER}</username>
            <password>${env.NEXUS_PASSWORD}</password>
        </server>
    </servers>

    <mirrors>
        <!-- 所有仓库请求都转到公司 Nexus；个人环境可换成阿里云：
             https://maven.aliyun.com/repository/public -->
        <mirror>
            <id>company-nexus</id>
            <mirrorOf>*</mirrorOf>
            <url>https://nexus.example.com/repository/maven-public/</url>
        </mirror>
    </mirrors>
</settings>
```

#### 3.2.4 依赖 scope

| scope | 编译主代码 | 编译/运行测试 | 打进产物 | 典型例子 | 前端类比 |
|---|---|---|---|---|---|
| `compile`（默认） | ✅ | ✅ | ✅ | spring-boot-starter-web | `dependencies` |
| `provided` | ✅ | ✅ | ❌ | Lombok、Servlet API（war 部署到 Tomcat） | 「运行环境会提供」≈ peerDeps 的部分语义 |
| `runtime` | ❌ | ✅ | ✅ | `mysql-connector-j`（代码只依赖 JDBC 接口） | 无直接对应 |
| `test` | ❌ | ✅ | ❌ | JUnit、Mockito | `devDependencies` |
| `import` | — | — | — | 仅用于 `dependencyManagement` 引入 BOM | 无 |

另有 `<optional>true</optional>`：「我用到了，但别传递给依赖我的人」。Lombok 常同时标 `optional`。

> 为什么 MySQL 驱动是 `runtime`？因为业务代码只面向 `java.sql.*` 接口编程，编译期不该直接引用 `com.mysql.cj.*` 的类——scope 在帮你**强制面向接口**。

#### 3.2.5 生命周期与插件（≈ npm scripts，但阶段固定）

npm scripts 名字随便起；Maven 的**生命周期阶段（phase）是固定的有序列表**，执行某阶段会**先执行它之前的所有阶段**：

```
default 生命周期（核心阶段）：
validate → compile → test-compile → test → package → verify → install → deploy
   │          │           │          │        │          │        │         │
 校验pom   编译主代码   编译测试    跑单测   打jar     集成检查  装到~/.m2  发到私服

clean 生命周期：clean           （删除 target/）
site  生命周期：site            （生成项目站点，很少用）
```

| 命令 | 做什么 | 前端对应 |
|---|---|---|
| `mvn clean` | 删 `target/` | `rm -rf dist` |
| `mvn compile` | 编译到 `target/classes` | `tsc` |
| `mvn test` | compile + 跑单测 | `npm test` |
| `mvn package` | test + 打包成 jar | `npm run build` |
| `mvn install` | package + 装到本地仓库 | `npm link`（供本机其他项目用） |
| `mvn deploy` | install + 上传私服 | `npm publish` |
| `mvn clean package -DskipTests` | 跳过测试执行（仍编译测试） | — |
| `mvn package -Dmaven.test.skip=true` | 连测试编译都跳过 | — |
| `mvn -pl mall-app -am package` | 只构建某模块及其依赖模块 | `pnpm --filter app... build` |
| `mvn -U` | 强制检查更新 SNAPSHOT | `npm update` 部分语义 |
| `mvn -o` | 离线模式 | `--offline` |

**阶段本身不干活，干活的是插件的目标（goal）**。阶段只是「挂钩点」：

```
phase:   compile          test              package
           │               │                   │
goal:  compiler:compile  surefire:test     jar:jar → spring-boot:repackage
```

也可以直接调用插件目标：`mvn dependency:tree`、`mvn spring-boot:run`（≈ `npm run dev`）。

#### 3.2.6 依赖传递与冲突

npm 用嵌套 `node_modules` 允许**同一个包多个版本共存**；Java 的 classpath 上**同一个类只能有一份**（准确说：只有第一个被加载到的生效），所以 Maven 必须**选出唯一版本**。裁决规则：

```
规则 1：最短路径优先（nearest wins）
  mini-mall ─▶ A ─▶ B ─▶ C:1.0      路径长度 3
  mini-mall ─▶ D ─▶ C:2.0           路径长度 2   ← 选中 C:2.0

规则 2：路径一样长，pom 中先声明者优先（first declaration wins）
  mini-mall ─▶ A ─▶ C:1.0   （A 先声明）  ← 选中 C:1.0
  mini-mall ─▶ D ─▶ C:2.0

规则 0（最高优先级）：dependencyManagement 中声明的版本，直接覆盖上述裁决
规则 0'：自己在 <dependencies> 中直接声明，路径长度为 1，自然最近
```

冲突的典型症状（运行期才爆）：

| 异常 | 含义 |
|---|---|
| `NoSuchMethodError` | 编译时用的版本有这个方法，运行时被裁决成了没有这个方法的版本 |
| `NoClassDefFoundError` / `ClassNotFoundException` | 类被裁掉了或者 scope 不对 |
| `AbstractMethodError` | 接口和实现来自不兼容的两个版本 |

排查三板斧：

```bash
# ① 打印依赖树（≈ npm ls）
mvn dependency:tree
# ② 只看某个包，-Dverbose 显示被裁掉的版本及原因（omitted for conflict with 2.0）
mvn dependency:tree -Dverbose -Dincludes=com.fasterxml.jackson.core:jackson-databind
# ③ IDEA：pom.xml 右键 → Maven → Show Diagram（或装 Maven Helper 插件看 Conflicts）
```

两种解决手段：

```xml
<!-- 手段一：exclusions，把某依赖带进来的传递依赖砍掉 -->
<dependency>
    <groupId>com.example.legacy</groupId>
    <artifactId>legacy-sdk</artifactId>
    <version>1.2.0</version>
    <exclusions>
        <exclusion>
            <!-- legacy-sdk 自带 log4j 绑定，会与 Logback 冲突 -->
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-log4j12</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<!-- 手段二：dependencyManagement，只「定版本」不「引依赖」 -->
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.18.2</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

#### 3.2.7 dependencyManagement 与 BOM（≈ 没有 lockfile 时如何锁版本）

- `<dependencies>`：**真正引入**依赖。
- `<dependencyManagement>`：**只声明版本**，谁引入了这个 GA，就用这里的版本（包括传递依赖）。

BOM（Bill of Materials）是一个 `packaging=pom` 的特殊 pom，里面只有一大段 `dependencyManagement`，把一整套「互相兼容的版本」打包好。用 `scope=import` 引入：

```xml
<dependencyManagement>
    <dependencies>
        <!-- 引入 Spring Cloud Alibaba 的版本全家桶（11 章使用） -->
        <dependency>
            <groupId>com.alibaba.cloud</groupId>
            <artifactId>spring-cloud-alibaba-dependencies</artifactId>
            <version>2023.0.3.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

和前端对照：

| 前端 | Maven | 差异 |
|---|---|---|
| `package-lock.json` | 无 | Maven 版本本来就写死，裁决规则确定，同一 pom 构建结果确定 |
| `overrides` / `resolutions` | `dependencyManagement` | 强制传递依赖的版本 |
| `peerDependencies` | BOM + `provided` | 「我和 Spring 6.x 一起用」靠 BOM 对齐，而不是声明约束 |
| 「React 全家桶版本搭配表」 | BOM | 官方维护好的兼容版本组合 |

> `spring-boot-starter-parent` 本质上就是「BOM + 插件默认配置」。不能继承它时（比如公司有自己的 parent），用 `spring-boot-dependencies` 这个 BOM `import` 进来，效果相同。

#### 3.2.8 多模块项目（≈ pnpm workspace）

```
mini-mall/                         ≈ monorepo 根
├── pom.xml                        packaging=pom，声明 <modules>，统一版本   ≈ pnpm-workspace.yaml + 根 package.json
├── mall-common/                   公共模块：Result、BizException、工具类   ≈ packages/shared
│   └── pom.xml
├── mall-order/                    订单业务
│   └── pom.xml                    依赖 mall-common                         ≈ "shared": "workspace:*"
└── mall-app/                      启动模块，打 fat jar                      ≈ apps/web
    └── pom.xml
```

根 pom 关键段：

```xml
<groupId>com.example</groupId>
<artifactId>mini-mall</artifactId>
<version>0.0.1-SNAPSHOT</version>
<packaging>pom</packaging>

<modules>
    <module>mall-common</module>
    <module>mall-order</module>
    <module>mall-app</module>
</modules>

<dependencyManagement>
    <dependencies>
        <!-- 内部模块版本也在这里统一，子模块引用时不写版本 -->
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>mall-common</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

子模块 pom：

```xml
<parent>
    <groupId>com.example</groupId>
    <artifactId>mini-mall</artifactId>
    <version>0.0.1-SNAPSHOT</version>
</parent>
<artifactId>mall-order</artifactId>

<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>mall-common</artifactId>
    </dependency>
</dependencies>
```

两个容易混的概念：

| 概念 | 作用 | 方向 |
|---|---|---|
| **继承**（`<parent>`） | 子模块复用父 pom 的配置、版本管理 | 子 → 父 |
| **聚合**（`<modules>`） | 在根目录一条命令构建所有模块（Reactor 自动按依赖排序） | 父 → 子 |

二者通常同时用在同一个根 pom 上，但可以分开。

> 本系列单体阶段（05～10 章）用**单模块 + 包分层**即可；11 章拆微服务时再转为多模块。不要为了「看起来专业」过早拆模块。

#### 3.2.9 SNAPSHOT 与 RELEASE

| | SNAPSHOT（如 `1.0.0-SNAPSHOT`） | RELEASE（如 `1.0.0`） |
|---|---|---|
| 含义 | 开发中的快照，可反复覆盖发布 | 正式版，**发布后不可变** |
| 私服存储 | 每次 deploy 生成带时间戳的版本 `1.0.0-20261126.083015-3` | 唯一 |
| 拉取行为 | 默认每天检查一次更新，`-U` 强制更新 | 本地有就不再拉 |
| 前端类比 | `npm i pkg@next` / git 依赖 | 普通 semver 版本 |
| 使用约束 | 联调期使用；**生产发布禁止依赖 SNAPSHOT** | 生产使用 |

典型坑：「我本地好好的，CI 上报 NoSuchMethodError」——多半是对方又发了一版 SNAPSHOT，你本地是旧缓存。`mvn -U` 重拉。

#### 3.2.10 fat jar 与 `java -jar`

前端 build 产物是一堆静态文件，扔给 Nginx。Spring Boot 的产物是一个**可执行 jar**，自带 Web 容器（Tomcat），`java -jar` 就能起服务：

```bash
mvn clean package
java -jar target/mini-mall-0.0.1-SNAPSHOT.jar --spring.profiles.active=dev
# 常见 JVM 参数（03 章讲过）放在 -jar 前面
java -Xms1g -Xmx1g -XX:+UseG1GC -jar target/mini-mall-0.0.1-SNAPSHOT.jar
```

`target/` 下会有两个文件：

```
mini-mall-0.0.1-SNAPSHOT.jar           ← repackage 后的 fat jar（几十 MB），用来部署
mini-mall-0.0.1-SNAPSHOT.jar.original  ← 只含自己代码的普通 jar（几十 KB）
```

内部结构见 4.3 节原理。

#### 3.2.11 Gradle 简介与对比

| 维度 | Maven | Gradle |
|---|---|---|
| 配置语言 | XML（声明式） | Groovy / Kotlin DSL（可编程） |
| 构建速度 | 一般 | 快（增量构建、构建缓存、守护进程） |
| 灵活性 | 低（约定死） | 高（任意写逻辑） |
| 国内后端占比 | **主流** | Android 主流，后端少量 |
| 前端类比 | 「配置型」的 webpack.config | 「代码型」的 gulpfile |

同样的依赖在 Gradle（Kotlin DSL）里：

```kotlin
// build.gradle.kts
plugins {
    java
    id("org.springframework.boot") version "3.4.1"
    id("io.spring.dependency-management") version "1.1.7"
}

java { toolchain { languageVersion = JavaLanguageVersion.of(21) } }

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web") // ≈ compile
    compileOnly("org.projectlombok:lombok")                            // ≈ provided
    annotationProcessor("org.projectlombok:lombok")                    // 注解处理器单独声明
    runtimeOnly("com.mysql:mysql-connector-j")                         // ≈ runtime
    testImplementation("org.springframework.boot:spring-boot-starter-test") // ≈ test
}
```

> 建议：先把 Maven 学透（公司项目大概率是 Maven），Gradle 遇到再学，概念相通。

#### 3.2.12 Maven Wrapper（≈ `packageManager` 字段 + corepack）

```bash
mvn wrapper:wrapper        # 生成 mvnw / mvnw.cmd / .mvn/wrapper/
./mvnw clean package       # 用项目固定的 Maven 版本，CI 与本地一致
```

`mvnw` 和 `.mvn/` 要提交进 git。

---

### 3.3 项目目录约定

Maven 的「约定优于配置」：放对位置，就不需要写任何配置。

```
mini-mall/
├── pom.xml
├── mvnw, .mvn/
├── src/
│   ├── main/
│   │   ├── java/                       主代码（按包名分目录）  ≈ src/
│   │   │   └── com/example/mall/
│   │   │       ├── MiniMallApplication.java
│   │   │       ├── controller/ biz/ domain/ dao/ client/ convert/ util/ model/ common/
│   │   └── resources/                  非代码资源，打包进 classpath 根  ≈ public/ + 配置
│   │       ├── application.yml
│   │       ├── application-dev.yml
│   │       ├── logback-spring.xml
│   │       └── mapper/*.xml            MyBatis XML（08 章）
│   └── test/
│       ├── java/                       测试代码，包结构与 main 一一对应
│       │   └── com/example/mall/...
│       └── resources/                  测试专用配置（覆盖 main 中同名文件）
└── target/                             构建输出，不进 git      ≈ dist/
    ├── classes/                        编译结果 + resources 拷贝
    ├── test-classes/
    ├── surefire-reports/               单测报告
    └── site/jacoco/                    覆盖率报告
```

与前端最大的不同：**测试不是和源文件放一起（`Foo.test.ts`），而是放在平行的 `src/test/java` 同名包下**。同包的好处是测试可以访问包级私有（default）成员。

---

### 3.4 包命名与代码规范

#### 3.4.1 命名规范（阿里 Java 开发手册要点）

| 对象 | 规则 | 例子 | 前端习惯对比 |
|---|---|---|---|
| 包名 | 全小写，反向域名，单数 | `com.example.mall.util` | 目录常用 kebab-case |
| 类名 | UpperCamelCase；DO/DTO/VO/PO 等后缀保持大写 | `OrderVO`、`CreateOrderDTO` | 组件 PascalCase 一致 |
| 方法/变量 | lowerCamelCase | `calcTotalAmount` | 一致 |
| 常量 | 全大写下划线 | `MAX_ITEM_COUNT` | 一致 |
| 抽象类 | `Abstract` / `Base` 开头 | `AbstractOrderHandler` | — |
| 异常类 | `Exception` 结尾 | `BizException` | — |
| 测试类 | 被测类名 + `Test` | `OrderCheckUnitTest` | `xxx.test.ts` |
| 布尔字段 | **POJO 中不要以 `is` 开头** | `deleted` 而非 `isDeleted` | 前端常用 `isXxx` |
| 枚举 | 类名带 `Enum` 后缀，成员全大写 | `OrderStatusEnum.PAID` | TS 联合类型字面量 |

手册中其他高频条款（各章会再遇到）：

- 所有 POJO 属性用**包装类型**（`Integer` 而非 `int`），因为数据库字段可能为 null；
- 金额用 `BigDecimal`，比较用 `compareTo`，**禁止用 `equals`**（`1.0` 与 `1.00` 不 equals）；
- 线程池不允许用 `Executors` 创建（04 章）；
- `SimpleDateFormat` 线程不安全（02 章）；
- 日志使用 SLF4J 门面，不直接用 Logback API（本章 3.6）；
- 注释：类、方法写 Javadoc（`/** */`），而不是 `//`。

#### 3.4.2 格式化与静态检查工具

| 工具 | 作用 | 前端类比 |
|---|---|---|
| **Spotless**（+ google-java-format / palantir-java-format） | 自动格式化，`mvn spotless:apply` | Prettier |
| **Checkstyle** | 风格检查（命名、行长、import），CI 卡口 | ESLint（风格类规则） |
| **阿里 P3C**（IDEA 插件 / PMD 规则） | 手册规约检查 | eslint-config-airbnb |
| **SpotBugs** / **SonarQube** | 字节码级 bug 模式检测、质量门禁 | SonarJS |
| `.editorconfig` | 编辑器缩进/换行 | 一样 |

Spotless 示例（`mvn spotless:check` 可挂在 CI）：

```xml
<plugin>
    <groupId>com.diffplug.spotless</groupId>
    <artifactId>spotless-maven-plugin</artifactId>
    <version>2.43.0</version>
    <configuration>
        <java>
            <palantirJavaFormat/>      <!-- 4 空格缩进，适合国内习惯 -->
            <removeUnusedImports/>
        </java>
    </configuration>
    <executions>
        <execution>
            <goals><goal>check</goal></goals>
            <phase>verify</phase>      <!-- mvn verify 时检查，不合规则构建失败 -->
        </execution>
    </executions>
</plugin>
```

> 团队真正落地的顺序：先统一 IDEA 格式化配置（导出 xml 共享）→ 再上 Spotless 自动格式化 → 最后才是 Checkstyle 卡口。上来就卡口只会让所有人绕过它。

---

### 3.5 Lombok：消灭样板代码

Java 的 POJO 需要大量 getter/setter/equals/hashCode/toString/构造器。TS 里一行 `type Order = {...}` 就够了，Java 要写几十行。Lombok 用注解在**编译期**生成这些代码。

```ts
// TS：天然简洁
class OrderVO {
  constructor(public orderNo: string, public totalAmount: number) {}
}
```

```java
// Java + Lombok
@Data                 // getter + setter + toString + equals/hashCode + 必需参数构造器
@Builder              // 链式构造：OrderVO.builder().orderNo("A1").build()
@NoArgsConstructor    // 无参构造（Jackson 反序列化、MyBatis 映射需要）
@AllArgsConstructor   // 全参构造（@Builder 与 @NoArgsConstructor 同时用时需要）
public class OrderVO {
    /** 订单号 */
    private String orderNo;
    /** 订单总额 */
    private BigDecimal totalAmount;
}
```

常用注解速查：

| 注解 | 生成内容 | 使用场景 |
|---|---|---|
| `@Getter` / `@Setter` | getter / setter | 精细控制 |
| `@Data` | 上面全套 + `toString` + `equals/hashCode` + `@RequiredArgsConstructor` | DTO / VO / PO |
| `@Value` | 不可变类：字段 `private final`、只有 getter | 值对象（Java 16+ 优先用 `record`） |
| `@Builder` | Builder 模式 | 字段多的对象构造 |
| `@NoArgsConstructor` / `@AllArgsConstructor` | 构造器 | 框架反射需要无参构造 |
| `@RequiredArgsConstructor` | 为 `final` 字段生成构造器 | **Spring 构造器注入标配** |
| `@Slf4j` | `private static final Logger log = LoggerFactory.getLogger(当前类.class);` | 所有要打日志的类 |
| `@EqualsAndHashCode(callSuper = true)` | 包含父类字段 | 有继承时 |
| `@ToString(exclude = "password")` | 排除敏感字段 | 日志脱敏 |

Spring 构造器注入（06 章详讲）：

```java
@Component
@RequiredArgsConstructor   // 为 final 字段生成构造器，Spring 通过构造器注入依赖
public class OrderCheckUnit {
    private final ProductDao productDao;
}
```

`record` vs Lombok：Java 16+ 的 `record` 原生支持不可变数据类，但**不能有 setter、不能继承**，且 MyBatis-Plus 实体需要无参构造 + setter。经验：**PO 用 Lombok `@Data`，纯只读 VO / 方法内的中间结果用 `record`**。

---

### 3.6 日志体系：从 console.log 到 SLF4J + Logback

#### 3.6.1 门面 + 实现

```
业务代码 ──只依赖──▶ SLF4J API（门面 / 接口）          ≈ 一套统一的 logger 接口
                         │ 运行时绑定一个实现
       ┌─────────────────┼──────────────────┐
       ▼                 ▼                  ▼
    Logback          Log4j2           JUL(java.util.logging)
  （Spring Boot 默认）  （高性能异步）      （JDK 自带，少用）

三方库用 log4j / commons-logging / JUL 打的日志 ──桥接包──▶ SLF4J ──▶ Logback
（jcl-over-slf4j、log4j-over-slf4j、jul-to-slf4j，Spring Boot starter 已内置）
```

前端类比：像 `debug` / `winston` 这样的 logger 抽象层 + 不同 transport。门面的意义：**三方库与业务代码都面向 SLF4J，最终统一由一个实现输出到同一处**。

#### 3.6.2 TS ↔ Java 对照

```ts
// Node：console 或 pino
console.log('创建订单', orderNo, userId);
console.error('扣库存失败', err);
logger.info({ orderNo, userId }, '创建订单');
```

```java
@Slf4j
@Component
public class OrderBizComponent {

    /**
     * 演示日志写法：创建订单时打印关键信息
     *
     * @param orderNo 订单号
     * @param userId  用户 ID
     */
    public void logDemo(String orderNo, Long userId) {
        // 占位符 {}：只有在该级别开启时才拼接字符串，性能好
        log.info("创建订单, orderNo={}, userId={}", orderNo, userId);

        // 错误：字符串拼接，即使 debug 关闭也会先拼接（以及调用 toString）
        // log.debug("订单详情: " + order);

        try {
            deductStock(orderNo);
        } catch (RuntimeException e) {
            // 异常对象放在最后一个参数，且不要占位：SLF4J 会打印完整堆栈
            log.error("扣库存失败, orderNo={}", orderNo, e);
        }
    }

    /**
     * 模拟扣库存
     *
     * @param orderNo 订单号
     */
    private void deductStock(String orderNo) {
        throw new IllegalStateException("库存不足: " + orderNo);
    }
}
```

#### 3.6.3 日志级别

| 级别 | 用途 | 生产是否输出 | 前端对应 |
|---|---|---|---|
| `TRACE` | 极细粒度追踪 | 否 | — |
| `DEBUG` | 调试信息、SQL | 否（按需临时打开某个包） | `console.debug` |
| `INFO` | 关键业务节点：下单成功、状态变化、外部调用结果 | **是** | `console.info` |
| `WARN` | 可恢复的异常：重试、降级、参数非法 | 是 | `console.warn` |
| `ERROR` | 需要人介入：未预期异常、数据不一致 | 是，**要接告警** | `console.error` + Sentry |

打日志的原则：

1. **能用日志复现现场**：带上业务主键（orderNo、userId），不要只写「失败了」；
2. **不打敏感信息**：手机号、身份证、token 脱敏；
3. **不在循环里打 INFO**：一次导出 10 万单就是 10 万行；
4. **ERROR 要克制**：业务校验失败（库存不足）是 WARN 甚至 INFO，不是 ERROR，否则告警被淹没；
5. **异常只打一次**：要么 catch 后打日志并处理，要么往上抛，不要「打一次再抛」导致每层都打一遍堆栈。

#### 3.6.4 MDC 与 TraceId

服务端是多线程并发处理请求，日志文件里同一时刻交错着几百个请求的日志。**如何把一个请求的日志串起来？** 给每个请求分配一个 TraceId，放进 MDC（Mapped Diagnostic Context），在日志格式里输出。

```
2026-11-26 10:00:01.123 [http-nio-8080-exec-3] [traceId=a1b2c3] INFO  OrderBizComponent - 创建订单, orderNo=A001
2026-11-26 10:00:01.124 [http-nio-8080-exec-7] [traceId=d4e5f6] INFO  OrderBizComponent - 创建订单, orderNo=A002
2026-11-26 10:00:01.130 [http-nio-8080-exec-3] [traceId=a1b2c3] WARN  OrderCheckUnit    - 库存不足, productId=10
                                               ^^^^^^^^^^^^^^ grep a1b2c3 即可拿到一个请求的完整日志
```

前端类比：像在 axios 拦截器里给每个请求加 `X-Request-Id`，并在 Sentry 里打 tag。MDC 本质是一个 **ThreadLocal<Map<String, String>>**（04 章讲过 ThreadLocal），key 是你在格式中引用的名字（如 `traceId`）。代码见 5.3 节。

---

### 3.7 单元测试：JUnit 5 + Mockito + AssertJ

#### 3.7.1 三件套分工

| 库 | 职责 | Jest 对应 |
|---|---|---|
| **JUnit 5**（Jupiter） | 测试框架：组织、生命周期、运行 | `describe` / `it` / `beforeEach` / runner |
| **Mockito** | 模拟依赖、校验调用 | `jest.fn()` / `jest.mock()` / `toHaveBeenCalledWith` |
| **AssertJ** | 流式断言 | `expect(x).toBe(y)` |

`spring-boot-starter-test` 已经全部包含，无需单独引入。

#### 3.7.2 Jest ↔ JUnit 5 对照

```ts
// Jest
describe('PriceUtil', () => {
  beforeEach(() => { /* 每个用例前 */ });

  describe('discount', () => {
    it('满 100 减 10', () => {
      expect(discount(120)).toBe(110);
    });

    it.each([[0, 0], [99, 99]])('未满 100 不减: %i', (input, expected) => {
      expect(discount(input)).toBe(expected);
    });

    it.skip('待实现', () => {});
  });

  it('负数抛错', () => {
    expect(() => discount(-1)).toThrow('金额不能为负');
  });
});
```

```java
@DisplayName("PriceUtil")                                   // ≈ describe 的标题
class PriceUtilTest {

    /** 每个用例前执行 ≈ beforeEach */
    @BeforeEach
    void setUp() {
    }

    @Nested                                                  // ≈ 嵌套 describe
    @DisplayName("discount")
    class Discount {

        /** 满 100 减 10 */
        @Test                                                // ≈ it
        @DisplayName("满 100 减 10")
        void over100() {
            assertThat(PriceUtil.discount(120)).isEqualTo(110);  // ≈ expect().toBe()
        }

        /**
         * 未满 100 不减
         *
         * @param input    原价
         * @param expected 期望价
         */
        @ParameterizedTest(name = "未满 100 不减: {0}")       // ≈ it.each
        @CsvSource({"0, 0", "99, 99"})
        void under100(int input, int expected) {
            assertThat(PriceUtil.discount(input)).isEqualTo(expected);
        }

        /** 待实现 */
        @Test
        @Disabled("待实现")                                  // ≈ it.skip
        void todo() {
        }
    }

    /** 负数抛错 */
    @Test
    void negative() {
        assertThatThrownBy(() -> PriceUtil.discount(-1))     // ≈ expect(fn).toThrow()
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("金额不能为负");
    }
}
```

（`PriceUtil.discount(int)` 是演示用的假想方法。）

| Jest | JUnit 5 |
|---|---|
| `describe` | 测试类 / `@Nested` 内部类 |
| `it` / `test` | `@Test` |
| `it.each` | `@ParameterizedTest` + `@CsvSource` / `@ValueSource` / `@MethodSource` |
| `beforeEach` / `afterEach` | `@BeforeEach` / `@AfterEach` |
| `beforeAll` / `afterAll` | `@BeforeAll` / `@AfterAll`（须 static） |
| `it.skip` / `it.only` | `@Disabled` / IDEA 里单独运行该方法 |
| 测试超时 | `@Timeout(2)` |

#### 3.7.3 jest.mock ↔ Mockito

```ts
// Jest
jest.mock('./productApi');
const mockedApi = productApi as jest.Mocked<typeof productApi>;
mockedApi.listByIds.mockResolvedValue([{ id: 1, stock: 5 }]);
await check(order);
expect(mockedApi.listByIds).toHaveBeenCalledWith([1]);
expect(mockedApi.listByIds).toHaveBeenCalledTimes(1);
```

```java
@ExtendWith(MockitoExtension.class)       // 启用 Mockito 注解
class OrderCheckUnitTest {
    @Mock                                  // ≈ jest.mock：生成一个假的 ProductDao
    private ProductDao productDao;
    @InjectMocks                           // 创建被测对象，并把 @Mock 注入进去（走构造器）
    private OrderCheckUnit orderCheckUnit;

    /** 演示桩与校验 */
    @Test
    void demo() {
        // 打桩 ≈ mockResolvedValue
        when(productDao.listByIds(anyCollection())).thenReturn(List.of(product(1L, 5)));
        // 执行 ...
        // 校验调用 ≈ toHaveBeenCalledTimes(1)
        verify(productDao, times(1)).listByIds(anyCollection());
    }
}
```

| Jest | Mockito |
|---|---|
| `jest.fn()` / `jest.mock()` | `@Mock` / `mock(X.class)` |
| `mockReturnValue(v)` | `when(m.f()).thenReturn(v)` |
| `mockImplementation(fn)` | `thenAnswer(inv -> ...)` |
| `mockRejectedValue(err)` | `thenThrow(new XxxException())` |
| `toHaveBeenCalledWith(a)` | `verify(m).f(a)` |
| `toHaveBeenCalledTimes(n)` | `verify(m, times(n)).f(...)` |
| `not.toHaveBeenCalled()` | `verify(m, never()).f(...)` / `verifyNoInteractions(m)` |
| `expect.any(Number)` | `anyLong()` / `any()` |
| `mock.calls[0][0]` | `ArgumentCaptor` |
| `jest.spyOn(obj, 'f')` | `@Spy` / `spy(obj)`（部分 mock） |

#### 3.7.4 Spring Boot Test 与切片测试

| 方式 | 启动什么 | 速度 | 用途 |
|---|---|---|---|
| 纯 JUnit + Mockito | 什么都不启动 | 毫秒级 | **业务逻辑单测（主力）** |
| `@WebMvcTest(XxxController.class)` | 只启动 MVC 层（Controller、Filter、Jackson） | 秒级 | 测参数绑定、校验、序列化、全局异常 |
| `@MybatisPlusTest`（mybatis-plus 提供） | 只启动数据源 + Mapper | 秒级 | 测 SQL（配合 H2 或 Testcontainers） |
| `@DataRedisTest` / `@JsonTest` | 对应切片 | 秒级 | 测 Redis 访问 / JSON 序列化 |
| `@SpringBootTest` | 完整容器 | 十秒级 | 集成测试，少而精 |

切片测试中，不在切片里的 Bean 需要用 `@MockitoBean`（Spring Boot 3.4+；更早版本是 `@MockBean`）替换成 mock，示例见 5.5.3。

测试金字塔：大量纯单测（毫秒） > 适量切片测试 > 少量 `@SpringBootTest`。前端类比：大量纯函数单测 > 组件测试（Testing Library） > 少量 E2E（Playwright）。

#### 3.7.5 覆盖率：JaCoCo（≈ jest --coverage / istanbul）

`mvn test` 后生成 `target/site/jacoco/index.html`，看行覆盖、分支覆盖。配置见 5.2 pom。

> 覆盖率是**下限指标**不是目标：80% 覆盖率里如果全是 getter/setter，毫无意义。重点覆盖：金额计算、状态流转、校验分支、边界条件。

---

### 3.8 git 与 Java 项目 `.gitignore`

```gitignore
# 构建输出 ≈ dist/、node_modules/
target/
build/
!.mvn/wrapper/maven-wrapper.jar

# IDE
.idea/
*.iml
.vscode/
.classpath
.project
.settings/

# 日志与本地运行产物
logs/
*.log

# 本地敏感配置（只提交模板 application-local.yml.example）
application-local.yml

# 系统文件
.DS_Store
```

要点：

- **`target/` 必须忽略**（≈ `node_modules` + `dist`），但 **`mvnw` 和 `.mvn/wrapper/` 要提交**；
- `.idea/` 一般整体忽略；需要共享代码风格时，导出 `codeStyle` 配置或用 `.editorconfig`；
- 没有 lockfile 需要提交，pom.xml 就是全部依赖声明；
- 数据库密码、AK/SK 不进仓库：用环境变量或配置中心（11 章 Nacos）。

---

## 4. 原理深挖

### 4.1 Maven 是怎么把依赖变成 classpath 的

```
解析 pom（含所有 parent 继承链）
   │ 合并得到 Effective POM（mvn help:effective-pom 可查看）
   ▼
构建依赖图：读取每个依赖自己的 .pom，递归展开传递依赖
   │ 按 scope 传递规则过滤（test/provided 不传递；runtime 传递为 runtime）
   │ 应用 exclusions
   ▼
冲突裁决：dependencyManagement 优先 → 最短路径 → 先声明
   │ 每个 groupId:artifactId 只保留一个版本
   ▼
按 scope 生成多条 classpath：
   compile classpath   ─▶ javac 编译 src/main/java
   test classpath      ─▶ javac 编译 src/test/java、surefire 跑测试
   runtime classpath   ─▶ 打进 fat jar 的 BOOT-INF/lib
```

**为什么 Java 不能像 npm 一样多版本共存？**

npm 的 `require` 按文件路径解析，`a/node_modules/lodash` 和 `b/node_modules/lodash` 是两个不同模块对象。而 JVM 的类由「**类全限定名 + 类加载器**」唯一确定（03 章类加载）。普通应用里所有 jar 由同一个 AppClassLoader 加载，`com.fasterxml.jackson.databind.ObjectMapper` 只能有一个。想多版本共存，要么用隔离类加载器（OSGi、阿里 Pandora/SOFAArk），要么用 shade 插件把依赖**重命名包路径**后打进自己的 jar（很多 SDK 这么做，如 `shaded.com.google...`）。

这也解释了 Maven 的设计取舍：

| 取舍 | 好处 | 代价 |
|---|---|---|
| 全局共享本地仓库 | 省磁盘、无需每项目安装 | 本地仓库损坏会影响所有项目 |
| 单版本裁决 | classpath 简单确定，无重复类 | 冲突在运行期暴露（NoSuchMethodError） |
| 版本写死、不支持 `^` | 无 lockfile 也可复现 | 升级需要手动改，靠 BOM 批量对齐 |

> 高级排查：同一个类出现在两个**不同 GA** 的 jar 中（比如 `javax.servlet` 被不同 groupId 重复打包），Maven 不会裁决，因为它只按 GA 去重。此时用 `maven-enforcer-plugin` 的 `banDuplicateClasses` 规则（extra-enforcer-rules）在构建期拦截。

### 4.2 生命周期、阶段与插件绑定

Maven 核心本身几乎不做事，**一切都是插件**。`packaging=jar` 时默认绑定：

| 阶段 | 默认绑定的插件目标 |
|---|---|
| process-resources | `maven-resources-plugin:resources`（拷贝 resources，可做占位符替换） |
| compile | `maven-compiler-plugin:compile`（调用 javac，**注解处理器在此运行**） |
| process-test-resources | `maven-resources-plugin:testResources` |
| test-compile | `maven-compiler-plugin:testCompile` |
| test | `maven-surefire-plugin:test`（跑 `*Test.java`） |
| package | `maven-jar-plugin:jar`；Spring Boot 再追加 `spring-boot-maven-plugin:repackage` |
| install | `maven-install-plugin:install` |
| deploy | `maven-deploy-plugin:deploy` |

自定义插件执行就是「把某个 goal 挂到某个 phase 上」，如 JaCoCo 把 `prepare-agent` 挂在 test 之前（给 surefire 的 JVM 加 `-javaagent`，用字节码插桩统计覆盖），`report` 挂在 test 之后。

与 npm scripts 对比：npm 的 `pre`/`post` 钩子只有一层；Maven 是**有序阶段 + 多插件绑定**，跨项目行为一致——任何 Maven 项目 `mvn package` 的语义都一样，这是「约定优于配置」的价值。

### 4.3 fat jar 的结构与启动过程

```
mini-mall-0.0.1-SNAPSHOT.jar
├── META-INF/
│   └── MANIFEST.MF
│         Main-Class: org.springframework.boot.loader.launch.JarLauncher   ← JVM 入口
│         Start-Class: com.example.mall.MiniMallApplication                ← 你的 main
├── org/springframework/boot/loader/...     Spring Boot 自己的加载器类
└── BOOT-INF/
    ├── classes/                            你的代码 + resources
    ├── lib/                                所有 runtime 依赖 jar（jar 套 jar）
    ├── classpath.idx                       lib 加载顺序
    └── layers.idx                          分层信息（Docker 分层镜像用，12 章）
```

启动流程：

```
java -jar app.jar
  → JVM 读 MANIFEST 的 Main-Class → JarLauncher.main()
  → 构造自定义类加载器：能直接读取「jar 里嵌套的 jar」（标准 URLClassLoader 做不到）
  → 用该加载器加载 Start-Class，反射调用其 main()
  → SpringApplication.run() 启动容器与内嵌 Tomcat
```

> Java 8 / Spring Boot 2.x 时代入口类是 `org.springframework.boot.loader.JarLauncher`（无 `launch` 子包），Boot 3.2 起改为新包名。老项目自定义启动脚本若写死了类名，升级时会踩坑。

### 4.4 Lombok 原理：注解处理器 + 修改 AST

Java 注解处理器（JSR 269，Annotation Processing）本来只允许**生成新文件**（如 MapStruct 生成 `XxxConverterImpl.java`），不允许修改已有类。Lombok 是个「hack」：

```
javac 编译流程：
  源码 ─▶ 解析为 AST ─▶ 注解处理（多轮） ─▶ 语义分析 ─▶ 生成字节码
                          │
                 Lombok 处理器在此介入：
                 通过 javac 内部 API（com.sun.tools.javac.tree.*）
                 直接往 OrderVO 的 AST 上插入 getter/setter 方法节点
                          ▼
              后续阶段「以为」源码里本来就有这些方法
```

所以：

- **生成的代码只在 `.class` 里，源码里看不到**：IDEA 需要插件才能理解；`delombok` 可以还原出源码；
- **依赖 javac 内部 API**：每次 JDK 大版本升级都可能不兼容，必须升级 Lombok（Java 21 需 Lombok ≥ 1.18.30）；
- **只在编译期需要**：所以 scope 是 `provided`（Spring Boot 中常写 `optional=true`），不会进入运行时；
- **JDK 23+ 默认不再自动发现 classpath 上的注解处理器**：需要在 `maven-compiler-plugin` 里显式配置 `annotationProcessorPaths`（5.2 pom 已配置），否则 getter 全部「消失」、编译报 `cannot find symbol`。

与前端的对照：TS 装饰器是**运行时**的函数调用；Lombok 注解是**编译期**的代码生成，更像 Babel 插件改 AST。

### 4.5 SLF4J 绑定机制与 Logback 性能要点

- **绑定**：SLF4J 2.x 通过 `ServiceLoader` 在 classpath 中查找 `SLF4JServiceProvider` 实现（1.x 是查找 `StaticLoggerBinder` 类）。classpath 上有**多个实现**时会打印 `Multiple bindings` 警告并任选其一——这就是 3.2.6 中要 exclude `slf4j-log4j12` 的原因。**一个都没有**则日志静默丢弃（NOP）。
- **占位符为何快**：`log.debug("x={}", obj)` 先判断级别，级别不够直接返回，`obj.toString()` 都不会调用。参数本身的求值仍会发生，如 `log.debug("x={}", expensive())` 中 `expensive()` 仍执行——此时用 `if (log.isDebugEnabled())` 或 SLF4J 2 的 `log.atDebug().addArgument(() -> expensive()).log("x={}")`。
- **同步 vs 异步**：默认 Appender 同步写磁盘，磁盘慢时阻塞业务线程。高并发场景用 `AsyncAppender`（内部阻塞队列 + 后台线程），注意 `discardingThreshold`（队列剩 20% 时默认丢弃 INFO 及以下）与 `neverBlock`。
- **滚动**：`SizeAndTimeBasedRollingPolicy` 按天 + 按大小切分，`maxHistory` 和 `totalSizeCap` 防止撑爆磁盘——前端不会遇到「日志写满磁盘导致服务挂掉」，服务端会。

### 4.6 MDC 的线程传递问题

MDC 基于 ThreadLocal，**换线程就丢**：

```
请求线程 http-exec-3   MDC{traceId=a1b2c3}
   │ executor.submit(task)
   ▼
线程池 order-pool-1    MDC{}               ← 异步任务的日志没有 traceId
```

解决：提交任务时把父线程 MDC 拷贝过去，任务结束清理（线程池会复用线程，不清理会串号）：

```java
/**
 * 包装任务，使其在线程池中执行时继承提交线程的 MDC 上下文
 *
 * @param task 原始任务
 * @return 带 MDC 传递能力的任务
 */
public static Runnable wrapWithMdc(Runnable task) {
    // key 为 MDC 键（如 traceId），value 为对应值；在提交线程中捕获
    Map<String, String> context = MDC.getCopyOfContextMap();
    return () -> {
        if (context != null) {
            MDC.setContextMap(context);
        }
        try {
            task.run();
        } finally {
            // 线程池复用线程，必须清理，否则下一个任务会带上错误的 traceId
            MDC.clear();
        }
    };
}
```

Spring 的 `ThreadPoolTaskExecutor` 可以通过 `setTaskDecorator(MdcUtil::wrapWithMdc)` 统一生效。跨服务（HTTP、MQ）传递则要在 Header / 消息属性中携带 traceId，这正是 SkyWalking、Micrometer Tracing 的工作（12 章）。

### 4.7 Mockito 是怎么「造假」的

- `@Mock` 在运行时用 **ByteBuddy** 动态生成被 mock 类型的实现；所有方法默认返回「空值」：`null`、`0`、`false`、空集合、空 Optional。
- Mockito 5 起默认使用 **inline mock maker**：借助 Java Agent（Instrumentation API）在类加载后**改写字节码**，因此连 `final` 类、`static` 方法（`mockStatic`）都能 mock。代价是启动稍慢；JDK 21 会对动态加载 agent 打印警告，可在 surefire 中加 `-javaagent` 显式加载 Mockito。
- `when(productDao.listByIds(x)).thenReturn(...)` 这行代码之所以能工作：`productDao.listByIds(x)` 先被真实调用一次（作用在 mock 上），Mockito 记下「最后一次调用」，`when()` 再给它绑定返回值——这也是「**参数匹配器要么全用、要么全不用**」这条规则的由来：匹配器是按调用顺序压栈记录的。

与 Jest 对比：`jest.mock` 是**模块级**替换（劫持 `require`）；Mockito 是**对象级**替换，依赖注入天然让它好用——被测对象通过构造器拿依赖，测试时传 mock 进去即可。**这就是为什么要用构造器注入：可测性。**

---

## 5. mini-mall 实战

目标：

```
① Spring Initializr 生成骨架
② 完善 pom.xml（MyBatis-Plus、Lombok、JaCoCo、注解处理器）
③ logback-spring.xml + TraceIdFilter
④ 计算订单总额 OrderAmountUtil + 单测
⑤ 下单校验 OrderCheckUnit + 单测（Mockito mock 掉 ProductDao）
⑥ 预览：OrderController 切片测试
```

### 5.1 用 Spring Initializr 搭建骨架

方式一：网页 <https://start.spring.io>，选择：

| 选项 | 值 |
|---|---|
| Project | Maven |
| Language | Java |
| Spring Boot | 最新 3.x 稳定版 |
| Group / Artifact | `com.example` / `mini-mall` |
| Package name | `com.example.mall` |
| Packaging / Java | Jar / 21 |
| Dependencies | Spring Web、Validation、Lombok、MySQL Driver |

方式二：命令行（≈ `npm create vite@latest`）：

```bash
curl https://start.spring.io/starter.zip \
  -d type=maven-project -d language=java -d javaVersion=21 \
  -d groupId=com.example -d artifactId=mini-mall -d packageName=com.example.mall \
  -d dependencies=web,validation,lombok,mysql \
  -o mini-mall.zip && unzip mini-mall.zip -d mini-mall && cd mini-mall
./mvnw spring-boot:run          # ≈ npm run dev
```

方式三：IDEA → New Project → Spring Boot（内置 Initializr）。

生成后按总纲 4.1 建好分层包：

```bash
cd src/main/java/com/example/mall
mkdir -p controller biz domain dao/mapper client convert util \
         model/dto model/vo model/po model/enums common
```

### 5.2 完整 pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <!-- 继承 Spring Boot：获得依赖版本管理（BOM）+ 插件默认配置 + UTF-8 等默认属性 -->
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.1</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mini-mall</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>mini-mall</name>
    <description>简易电商订单系统（前端转 Java 系列贯穿项目）</description>

    <properties>
        <!-- 被 parent 读取，设置 javac 的 release=21 -->
        <java.version>21</java.version>
        <!-- 不在 Spring Boot BOM 中的依赖，版本集中放这里 -->
        <mybatis-plus.version>3.5.9</mybatis-plus.version>
        <jacoco.version>0.8.12</jacoco.version>
    </properties>

    <dependencies>
        <!-- Web：Spring MVC + 内嵌 Tomcat + Jackson + Logback（starter 默认带 logging） -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <!-- 参数校验：Hibernate Validator（07 章） -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <!-- MyBatis-Plus：注意 Boot 3 要用 spring-boot3-starter（08 章） -->
        <dependency>
            <groupId>com.baomidou</groupId>
            <artifactId>mybatis-plus-spring-boot3-starter</artifactId>
            <version>${mybatis-plus.version}</version>
        </dependency>
        <!-- MySQL 驱动：代码只依赖 JDBC 接口，所以是 runtime -->
        <dependency>
            <groupId>com.mysql</groupId>
            <artifactId>mysql-connector-j</artifactId>
            <scope>runtime</scope>
        </dependency>
        <!-- Lombok：只在编译期生效，不传递、不进产物 -->
        <dependency>
            <groupId>org.projectlombok</groupId>
            <artifactId>lombok</artifactId>
            <optional>true</optional>
        </dependency>
        <!-- 测试三件套：JUnit 5 + Mockito + AssertJ + Spring Test + JsonPath -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <!-- 编译插件：显式声明注解处理器路径（JDK 23+ 必须，21 上也建议） -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.projectlombok</groupId>
                            <artifactId>lombok</artifactId>
                            <version>${lombok.version}</version>
                        </path>
                    </annotationProcessorPaths>
                    <!-- 保留方法参数名，供 Spring MVC 绑定 @PathVariable 等使用 -->
                    <parameters>true</parameters>
                </configuration>
            </plugin>

            <!-- 覆盖率：test 前挂 agent 插桩，test 后出报告，verify 阶段卡最低覆盖率 -->
            <plugin>
                <groupId>org.jacoco</groupId>
                <artifactId>jacoco-maven-plugin</artifactId>
                <version>${jacoco.version}</version>
                <executions>
                    <execution>
                        <id>prepare-agent</id>
                        <goals><goal>prepare-agent</goal></goals>
                    </execution>
                    <execution>
                        <id>report</id>
                        <phase>test</phase>
                        <goals><goal>report</goal></goals>
                    </execution>
                    <execution>
                        <id>check</id>
                        <phase>verify</phase>
                        <goals><goal>check</goal></goals>
                        <configuration>
                            <rules>
                                <rule>
                                    <!-- 只对核心业务包设门槛，避免被 PO/DTO 拉低或拉高 -->
                                    <element>PACKAGE</element>
                                    <includes>
                                        <include>com.example.mall.domain</include>
                                        <include>com.example.mall.util</include>
                                    </includes>
                                    <limits>
                                        <limit>
                                            <counter>LINE</counter>
                                            <value>COVEREDRATIO</value>
                                            <minimum>0.80</minimum>
                                        </limit>
                                    </limits>
                                </rule>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <!-- 打 fat jar：package 阶段执行 repackage；排除 lombok 不进产物 -->
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <excludes>
                        <exclude>
                            <groupId>org.projectlombok</groupId>
                            <artifactId>lombok</artifactId>
                        </exclude>
                    </excludes>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

说明：

- `${lombok.version}` 来自 Spring Boot parent 的版本属性，保证注解处理器与依赖版本一致；
- 没有数据库时启动会因数据源自动配置失败，08 章接入 MySQL 前可在 `application.yml` 临时排除 `DataSourceAutoConfiguration`，**单测不受影响**（本章单测不启动 Spring）；
- 常用命令：`./mvnw test`（跑单测 + 覆盖率报告）、`./mvnw verify`（再加覆盖率门禁）、`./mvnw clean package`（出 jar）。

### 5.3 日志配置

#### 5.3.1 application.yml 中的日志基础项

```yaml
spring:
  application:
    name: mini-mall
logging:
  level:
    root: INFO
    com.example.mall: DEBUG          # 开发期本项目包打开 DEBUG
    com.example.mall.dao.mapper: DEBUG # 打印 SQL（08 章）
  file:
    path: ./logs                     # 被 logback-spring.xml 中的 LOG_PATH 读取
```

#### 5.3.2 logback-spring.xml

命名为 `logback-spring.xml`（而非 `logback.xml`）才能使用 `<springProfile>`、`<springProperty>` 等 Spring 扩展，因为它由 Spring Boot 在容器环境准备好之后再加载。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration scan="false">
    <!-- 读取 Spring 配置：应用名、日志目录（logging.file.path 会被 Spring Boot 映射为 LOG_PATH） -->
    <springProperty scope="context" name="APP_NAME" source="spring.application.name" defaultValue="mini-mall"/>
    <property name="LOG_DIR" value="${LOG_PATH:-./logs}"/>

    <!-- 统一格式：时间 线程 traceId 级别 类名(缩写) 行号 - 消息
         %X{traceId} 从 MDC 中取 key=traceId 的值 -->
    <property name="PATTERN"
              value="%d{yyyy-MM-dd HH:mm:ss.SSS} [%thread] [traceId=%X{traceId:-}] %-5level %logger{36}:%line - %msg%n"/>

    <!-- 控制台输出（开发用，≈ console.log） -->
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>${PATTERN}</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <!-- 全量日志文件：按天 + 按大小滚动 -->
    <appender name="FILE_ALL" class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>${LOG_DIR}/${APP_NAME}.log</file>
        <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <!-- 归档文件名：每天一个目录序号，单文件超 100MB 切下一个 %i，旧文件 gzip 压缩 -->
            <fileNamePattern>${LOG_DIR}/archive/${APP_NAME}.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>100MB</maxFileSize>
            <!-- 保留 15 天 -->
            <maxHistory>15</maxHistory>
            <!-- 归档总大小上限，防止撑爆磁盘 -->
            <totalSizeCap>10GB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <pattern>${PATTERN}</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <!-- 错误日志单独一份：只收 ERROR，便于快速定位和接告警 -->
    <appender name="FILE_ERROR" class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>${LOG_DIR}/${APP_NAME}-error.log</file>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>ERROR</level>
            <onMatch>ACCEPT</onMatch>
            <onMismatch>DENY</onMismatch>
        </filter>
        <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>${LOG_DIR}/archive/${APP_NAME}-error.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>100MB</maxFileSize>
            <maxHistory>30</maxHistory>
            <totalSizeCap>2GB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <pattern>${PATTERN}</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <!-- 异步包装：业务线程只入队，后台线程写盘 -->
    <appender name="ASYNC_FILE_ALL" class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>2048</queueSize>
        <!-- 0 表示队列快满时也不丢弃 INFO 日志（默认剩 20% 时丢弃 INFO 及以下） -->
        <discardingThreshold>0</discardingThreshold>
        <!-- 队列满时不阻塞业务线程（宁可丢日志也不拖慢请求） -->
        <neverBlock>true</neverBlock>
        <!-- 异步时要打印 %line 需开启调用者信息，有性能开销；生产可去掉 %line 并关掉它 -->
        <includeCallerData>true</includeCallerData>
        <appender-ref ref="FILE_ALL"/>
    </appender>

    <!-- 本地开发：只输出控制台 -->
    <springProfile name="local,dev">
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>

    <!-- 测试/生产：输出到文件，不打控制台（容器场景可改为只打控制台，由采集器收集，见 12 章） -->
    <springProfile name="test,prod">
        <root level="INFO">
            <appender-ref ref="ASYNC_FILE_ALL"/>
            <appender-ref ref="FILE_ERROR"/>
        </root>
    </springProfile>

    <!-- 未指定 profile 时的兜底 -->
    <springProfile name="default">
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>
</configuration>
```

> 包级别（`com.example.mall: DEBUG`）既可以写在 `application.yml` 的 `logging.level` 中，也可以在 xml 中写 `<logger name="..." level="..."/>`。推荐放 yml：可以按 profile 覆盖，接入 Nacos 后还能**线上动态调级别**排查问题。

#### 5.3.3 TraceIdFilter：给每个请求分配 TraceId

放在 `common` 包。Filter 是 Servlet 层的「中间件」，07 章会详讲它和 Interceptor 的区别。

```java
package com.example.mall.common;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;

/**
 * TraceId 过滤器：为每个 HTTP 请求生成（或透传）TraceId，写入 MDC 与响应头。
 * 日志格式中的 %X{traceId} 即从这里取值。
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceIdFilter extends OncePerRequestFilter {

    /** MDC 键名，与 logback-spring.xml 中 %X{traceId} 对应 */
    public static final String TRACE_ID_KEY = "traceId";
    /** 请求/响应头名，上游（网关、前端）可通过它透传 TraceId */
    public static final String TRACE_ID_HEADER = "X-Trace-Id";

    /**
     * 过滤逻辑：设置 TraceId → 执行后续链路 → 清理 MDC
     *
     * @param request  HTTP 请求
     * @param response HTTP 响应
     * @param chain    过滤器链
     * @throws ServletException Servlet 异常
     * @throws IOException      IO 异常
     */
    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        // 1. 优先使用上游传入的 TraceId，保证跨服务链路可串联
        String traceId = resolveTraceId(request);
        // 2. 放入 MDC，本线程后续所有日志都会带上
        MDC.put(TRACE_ID_KEY, traceId);
        // 3. 回写响应头，前端/测试可凭此 ID 找后端日志
        response.setHeader(TRACE_ID_HEADER, traceId);
        try {
            chain.doFilter(request, response);
        } finally {
            // 4. Tomcat 线程会被复用，必须清理，否则下个请求会串号
            MDC.remove(TRACE_ID_KEY);
        }
    }

    /**
     * 从请求头读取 TraceId，没有则生成新的
     *
     * @param request HTTP 请求
     * @return TraceId（32 位无横线 UUID 或上游传入值）
     */
    private String resolveTraceId(HttpServletRequest request) {
        String fromHeader = request.getHeader(TRACE_ID_HEADER);
        // 上游值做长度限制，防止恶意超长头污染日志
        if (StringUtils.hasText(fromHeader) && fromHeader.length() <= 64) {
            return fromHeader;
        }
        return UUID.randomUUID().toString().replace("-", "");
    }
}
```

前端配合：axios 响应拦截器里把 `X-Trace-Id` 带进错误上报（Sentry），出问题时前后端日志一键对齐。

### 5.4 计算订单总额 + 单测

#### 5.4.1 被测代码

依赖的领域类（01 章定义，此处用 Lombok 简化；`OrderItemPO` 字段与 `t_order_item` 表一致）：

```java
package com.example.mall.model.po;

import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 订单明细表实体，对应 t_order_item
 */
@Data
public class OrderItemPO {
    /** 主键 */
    private Long id;
    /** 订单 ID */
    private Long orderId;
    /** 商品 ID */
    private Long productId;
    /** 商品名称（下单时快照） */
    private String productName;
    /** 商品单价（下单时快照） */
    private BigDecimal price;
    /** 购买数量 */
    private Integer quantity;
    /** 创建时间 */
    private LocalDateTime createTime;
}
```

工具方法放在第五层 `util`：

```java
package com.example.mall.util;

import com.example.mall.model.po.OrderItemPO;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

/**
 * 订单金额计算工具（第五层：最小能力单元，纯函数、无依赖）
 */
public final class OrderAmountUtil {

    /** 金额小数位数，与表字段 DECIMAL(10,2) 对齐 */
    private static final int AMOUNT_SCALE = 2;

    private OrderAmountUtil() {
    }

    /**
     * 计算订单总额：Σ(单价 × 数量)，结果保留 2 位小数（四舍五入）
     *
     * @param items 订单明细列表；为 null 或空时视为 0
     * @return 订单总额，scale 固定为 2
     * @throws IllegalArgumentException 任一明细单价为空/为负，或数量为空/小于等于 0
     */
    public static BigDecimal calcTotalAmount(List<OrderItemPO> items) {
        if (items == null || items.isEmpty()) {
            return BigDecimal.ZERO.setScale(AMOUNT_SCALE, RoundingMode.HALF_UP);
        }
        return items.stream()
                .map(OrderAmountUtil::calculateLineAmount)
                .reduce(BigDecimal.ZERO, BigDecimal::add)
                // 只在最终结果处做一次舍入，避免每行舍入导致误差累积
                .setScale(AMOUNT_SCALE, RoundingMode.HALF_UP);
    }

    /**
     * 计算单行金额：单价 × 数量
     *
     * @param item 订单明细
     * @return 单行金额（未舍入）
     * @throws IllegalArgumentException 单价或数量非法
     */
    private static BigDecimal calculateLineAmount(OrderItemPO item) {
        checkItem(item);
        return item.getPrice().multiply(BigDecimal.valueOf(item.getQuantity()));
    }

    /**
     * 校验单行明细的单价与数量
     *
     * @param item 订单明细
     * @throws IllegalArgumentException 单价为空/为负，或数量为空/小于等于 0
     */
    private static void checkItem(OrderItemPO item) {
        if (item.getPrice() == null || item.getPrice().signum() < 0) {
            throw new IllegalArgumentException("商品单价非法, productId=" + item.getProductId());
        }
        if (item.getQuantity() == null || item.getQuantity() <= 0) {
            throw new IllegalArgumentException("购买数量非法, productId=" + item.getProductId());
        }
    }
}
```

#### 5.4.2 单测

路径：`src/test/java/com/example/mall/util/OrderAmountUtilTest.java`

```java
package com.example.mall.util;

import com.example.mall.model.po.OrderItemPO;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.NullAndEmptySource;

import java.math.BigDecimal;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DisplayName("OrderAmountUtil 计算订单总额")
class OrderAmountUtilTest {

    /**
     * 构造订单明细
     *
     * @param productId 商品 ID
     * @param price     单价字符串（用字符串构造 BigDecimal，避免 double 精度问题）
     * @param quantity  数量
     * @return 订单明细
     */
    private static OrderItemPO item(Long productId, String price, Integer quantity) {
        OrderItemPO item = new OrderItemPO();
        item.setProductId(productId);
        item.setPrice(price == null ? null : new BigDecimal(price));
        item.setQuantity(quantity);
        return item;
    }

    @Nested
    @DisplayName("正常计算")
    class Normal {

        /** 多行明细求和 */
        @Test
        @DisplayName("多行明细：Σ 单价 × 数量")
        void multiLines() {
            List<OrderItemPO> items = List.of(
                    item(1L, "19.90", 2),   // 39.80
                    item(2L, "5.05", 3));   // 15.15

            BigDecimal total = OrderAmountUtil.calcTotalAmount(items);

            // BigDecimal 比较数值用 isEqualByComparingTo，等价于 compareTo == 0
            assertThat(total).isEqualByComparingTo("54.95");
            // 同时约束 scale=2，保证入库格式稳定
            assertThat(total.scale()).isEqualTo(2);
        }

        /** 浮点陷阱：0.1 + 0.2 */
        @Test
        @DisplayName("没有浮点误差：0.1 + 0.2 = 0.30")
        void noFloatingError() {
            List<OrderItemPO> items = List.of(item(1L, "0.1", 1), item(2L, "0.2", 1));

            assertThat(OrderAmountUtil.calcTotalAmount(items)).isEqualTo(new BigDecimal("0.30"));
        }

        /**
         * 舍入规则：只在最终结果四舍五入
         *
         * @param price    单价
         * @param quantity 数量
         * @param expected 期望总额
         */
        @ParameterizedTest(name = "{0} × {1} = {2}")
        @CsvSource({
                "0.005, 1, 0.01",    // 半值进位
                "0.004, 1, 0.00",    // 不足半值舍去
                "0.333, 3, 1.00",    // 先乘后舍入：0.999 → 1.00
                "0.00, 5, 0.00"      // 0 元商品（赠品）
        })
        void rounding(String price, int quantity, String expected) {
            BigDecimal total = OrderAmountUtil.calcTotalAmount(List.of(item(1L, price, quantity)));

            assertThat(total).isEqualTo(new BigDecimal(expected));
        }

        /**
         * 空明细返回 0.00
         *
         * @param items null 或空列表
         */
        @ParameterizedTest
        @NullAndEmptySource
        @DisplayName("null 或空列表返回 0.00")
        void emptyItems(List<OrderItemPO> items) {
            assertThat(OrderAmountUtil.calcTotalAmount(items)).isEqualTo(new BigDecimal("0.00"));
        }
    }

    @Nested
    @DisplayName("非法明细")
    class Illegal {

        /** 单价为负 */
        @Test
        void negativePrice() {
            List<OrderItemPO> items = List.of(item(9L, "-1.00", 1));

            assertThatThrownBy(() -> OrderAmountUtil.calcTotalAmount(items))
                    .isInstanceOf(IllegalArgumentException.class)
                    .hasMessageContaining("单价非法")
                    .hasMessageContaining("productId=9");
        }

        /** 单价为空 */
        @Test
        void nullPrice() {
            List<OrderItemPO> items = List.of(item(9L, null, 1));

            assertThatThrownBy(() -> OrderAmountUtil.calcTotalAmount(items))
                    .isInstanceOf(IllegalArgumentException.class)
                    .hasMessageContaining("单价非法");
        }

        /**
         * 数量为 0 或负数
         *
         * @param quantity 非法数量
         */
        @ParameterizedTest
        @CsvSource({"0", "-2"})
        void illegalQuantity(int quantity) {
            List<OrderItemPO> items = List.of(item(9L, "10.00", quantity));

            assertThatThrownBy(() -> OrderAmountUtil.calcTotalAmount(items))
                    .isInstanceOf(IllegalArgumentException.class)
                    .hasMessageContaining("数量非法");
        }
    }
}
```

注意 `isEqualTo` 与 `isEqualByComparingTo` 的区别：`new BigDecimal("0.30").equals(new BigDecimal("0.3"))` 为 **false**（scale 不同）。上面刻意两种都用——`isEqualTo` 同时验证了 scale 必须是 2。

### 5.5 下单校验 + 单测（Mockito mock 掉 DAO）

#### 5.5.1 涉及的类

下单校验是「下单」功能单元的一部分：检查明细非空、商品存在、库存充足。它依赖 DAO 查商品，所以单测需要 mock DAO。

公共类（`common` 包；07 章会补充全局异常处理）：

```java
package com.example.mall.common;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * 业务错误码
 */
@Getter
@AllArgsConstructor
public enum ErrorCode {
    /** 参数错误 */
    PARAM_ERROR(10001, "参数错误"),
    /** 商品不存在 */
    PRODUCT_NOT_FOUND(20001, "商品不存在"),
    /** 库存不足 */
    STOCK_NOT_ENOUGH(20002, "库存不足");
    // 完整错误码清单见 07 章（号段：1xxxx 通用 / 2xxxx 商品 / 3xxxx 订单 / 9xxxx 系统）

    /** 错误码，返回给前端 Result.code */
    private final int code;
    /** 默认错误信息 */
    private final String message;
}
```

```java
package com.example.mall.common;

import lombok.Getter;

/**
 * 业务异常：可预期的业务失败（如库存不足），由全局异常处理器翻译为 Result
 */
@Getter
public class BizException extends RuntimeException {

    /** 错误码 */
    private final ErrorCode errorCode;

    /**
     * 构造业务异常
     *
     * @param errorCode 错误码
     * @param detail    详细信息（拼在默认信息之后，便于日志定位）
     */
    public BizException(ErrorCode errorCode, String detail) {
        super(errorCode.getMessage() + ": " + detail);
        this.errorCode = errorCode;
    }
}
```

入参 DTO（07 章会加上校验注解）：

```java
package com.example.mall.model.dto;

import lombok.Data;

import java.util.List;

/**
 * 创建订单入参
 */
@Data
public class CreateOrderDTO {
    /** 下单明细 */
    private List<OrderItemDTO> items;
}
```

```java
package com.example.mall.model.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 创建订单的单行明细入参
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class OrderItemDTO {
    /** 商品 ID */
    private Long productId;
    /** 购买数量 */
    private Integer quantity;
}
```

`ProductPO` 字段对应 `t_product`（id、name、price、stock、version、createTime、updateTime），`ProductDao`（08 章用 MyBatis-Plus 实现）本章只需要这个方法签名：

```java
/**
 * 按 ID 批量查询商品
 *
 * @param ids 商品 ID 集合
 * @return 存在的商品列表（不存在的 ID 不返回，不保证顺序）
 */
public List<ProductPO> listByIds(Collection<Long> ids)
```

#### 5.5.2 被测代码：OrderCheckUnit

放在第三层 `domain`，被 `OrderCreateUnit` 在写库前调用（06/08 章组装）。

```java
package com.example.mall.domain;

import com.example.mall.common.BizException;
import com.example.mall.common.ErrorCode;
import com.example.mall.dao.ProductDao;
import com.example.mall.model.dto.CreateOrderDTO;
import com.example.mall.model.dto.OrderItemDTO;
import com.example.mall.model.po.ProductPO;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * 下单校验单元：校验明细合法、商品存在、库存充足，并返回本次下单涉及的商品
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class OrderCheckUnit {

    private final ProductDao productDao;

    /**
     * 下单前置校验并加载商品
     *
     * @param dto 创建订单入参
     * @return 商品映射，key 为商品 ID，value 为商品实体（供后续计算金额、写明细快照使用）
     * @throws BizException PARAM_ERROR / PRODUCT_NOT_FOUND / STOCK_NOT_ENOUGH
     */
    public Map<Long, ProductPO> checkAndLoadProducts(CreateOrderDTO dto) {
        // 1. 明细基础校验（不访问数据库，失败快速返回）
        checkItems(dto.getItems());
        // 2. 合并同一商品的购买数量：key 为商品 ID，value 为合计数量
        Map<Long, Integer> quantityMap = mergeQuantity(dto.getItems());
        // 3. 一次批量查询，避免循环里逐个查库（N+1 问题）
        Map<Long, ProductPO> productMap = productDao.listByIds(quantityMap.keySet()).stream()
                .collect(Collectors.toMap(ProductPO::getId, Function.identity()));
        // 4. 逐个商品校验存在性与库存
        quantityMap.forEach((productId, quantity) -> checkStock(productId, quantity, productMap.get(productId)));
        return productMap;
    }

    /**
     * 校验明细列表：非空，且每行商品 ID 非空、数量大于 0
     *
     * @param items 下单明细
     * @throws BizException PARAM_ERROR
     */
    private void checkItems(List<OrderItemDTO> items) {
        if (items == null || items.isEmpty()) {
            throw new BizException(ErrorCode.PARAM_ERROR, "下单明细不能为空");
        }
        for (OrderItemDTO item : items) {
            if (item.getProductId() == null || item.getQuantity() == null || item.getQuantity() <= 0) {
                throw new BizException(ErrorCode.PARAM_ERROR, "明细非法, productId=" + item.getProductId());
            }
        }
    }

    /**
     * 合并同一商品的数量。前端可能传入重复商品行，若逐行校验，
     * 两行各买 3 件、库存 5 件时每行都能通过，合计 6 件却会超卖，所以必须先合并。
     *
     * @param items 下单明细（已校验）
     * @return key 为商品 ID，value 为该商品合计购买数量
     */
    private Map<Long, Integer> mergeQuantity(List<OrderItemDTO> items) {
        return items.stream().collect(Collectors.groupingBy(
                OrderItemDTO::getProductId,
                Collectors.summingInt(OrderItemDTO::getQuantity)));
    }

    /**
     * 校验单个商品存在且库存充足
     *
     * @param productId 商品 ID
     * @param quantity  合计购买数量
     * @param product   查询到的商品，不存在时为 null
     * @throws BizException PRODUCT_NOT_FOUND / STOCK_NOT_ENOUGH
     */
    private void checkStock(Long productId, Integer quantity, ProductPO product) {
        if (product == null) {
            throw new BizException(ErrorCode.PRODUCT_NOT_FOUND, "productId=" + productId);
        }
        if (product.getStock() < quantity) {
            // 业务可预期失败，用 WARN 而非 ERROR
            log.warn("库存不足, productId={}, stock={}, need={}", productId, product.getStock(), quantity);
            throw new BizException(ErrorCode.STOCK_NOT_ENOUGH, "productId=" + productId);
        }
    }
}
```

> 这里的库存校验只是「快速失败」的预检查，**不能防并发超卖**：校验通过到真正扣减之间，别的请求可能已经扣了库存。真正的防线是 08 章的乐观锁 `UPDATE ... SET stock = stock - ? WHERE id = ? AND stock >= ?` 与 09 章的 Redis 预扣。

#### 5.5.3 单测

路径：`src/test/java/com/example/mall/domain/OrderCheckUnitTest.java`

```java
package com.example.mall.domain;

import com.example.mall.common.BizException;
import com.example.mall.common.ErrorCode;
import com.example.mall.dao.ProductDao;
import com.example.mall.model.dto.CreateOrderDTO;
import com.example.mall.model.dto.OrderItemDTO;
import com.example.mall.model.po.ProductPO;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.util.Collection;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
@DisplayName("OrderCheckUnit 下单校验")
class OrderCheckUnitTest {

    /** 被 mock 的 DAO：不连数据库，返回值由每个用例打桩决定 */
    @Mock
    private ProductDao productDao;

    /** 被测对象：Mockito 通过 @RequiredArgsConstructor 生成的构造器注入 productDao */
    @InjectMocks
    private OrderCheckUnit orderCheckUnit;

    /** 捕获传给 listByIds 的参数，用于断言查询了哪些商品 ID */
    @Captor
    private ArgumentCaptor<Collection<Long>> idsCaptor;

    /**
     * 构造商品
     *
     * @param id    商品 ID
     * @param stock 库存
     * @return 商品实体
     */
    private static ProductPO product(Long id, int stock) {
        ProductPO product = new ProductPO();
        product.setId(id);
        product.setName("商品" + id);
        product.setPrice(new BigDecimal("10.00"));
        product.setStock(stock);
        return product;
    }

    /**
     * 构造下单入参
     *
     * @param items 下单明细
     * @return 创建订单入参
     */
    private static CreateOrderDTO order(OrderItemDTO... items) {
        CreateOrderDTO dto = new CreateOrderDTO();
        dto.setItems(List.of(items));
        return dto;
    }

    @Nested
    @DisplayName("校验通过")
    class Pass {

        /** 库存充足时返回商品 Map，且只查一次库 */
        @Test
        @DisplayName("库存充足：返回商品映射，批量查询一次")
        void stockEnough() {
            // given：打桩，DAO 返回两个库存充足的商品
            when(productDao.listByIds(anyCollection())).thenReturn(List.of(product(1L, 10), product(2L, 1)));

            // when
            Map<Long, ProductPO> result = orderCheckUnit.checkAndLoadProducts(
                    order(new OrderItemDTO(1L, 2), new OrderItemDTO(2L, 1)));

            // then：返回值正确
            assertThat(result).containsOnlyKeys(1L, 2L);
            // then：只批量查询一次，没有 N+1
            verify(productDao, times(1)).listByIds(anyCollection());
        }

        /** 重复商品行：合并后去重查询 */
        @Test
        @DisplayName("重复商品行：查询 ID 去重")
        void duplicateLinesQueryOnce() {
            when(productDao.listByIds(anyCollection())).thenReturn(List.of(product(1L, 10)));

            orderCheckUnit.checkAndLoadProducts(order(new OrderItemDTO(1L, 2), new OrderItemDTO(1L, 3)));

            // 捕获实际入参，断言只传了一个 ID
            verify(productDao).listByIds(idsCaptor.capture());
            assertThat(idsCaptor.getValue()).containsExactly(1L);
        }
    }

    @Nested
    @DisplayName("校验失败")
    class Fail {

        /** 明细为空：直接失败，不访问数据库 */
        @Test
        @DisplayName("明细为空：PARAM_ERROR，且不查库")
        void emptyItems() {
            CreateOrderDTO dto = order();

            BizException ex = assertThrows(BizException.class, () -> orderCheckUnit.checkAndLoadProducts(dto));

            assertThat(ex.getErrorCode()).isEqualTo(ErrorCode.PARAM_ERROR);
            // 参数错误应在访问 DAO 之前拦截
            verifyNoInteractions(productDao);
        }

        /** 数量非法 */
        @Test
        @DisplayName("数量为 0：PARAM_ERROR")
        void zeroQuantity() {
            CreateOrderDTO dto = order(new OrderItemDTO(1L, 0));

            BizException ex = assertThrows(BizException.class, () -> orderCheckUnit.checkAndLoadProducts(dto));

            assertThat(ex.getErrorCode()).isEqualTo(ErrorCode.PARAM_ERROR);
            verifyNoInteractions(productDao);
        }

        /** 商品不存在：DAO 返回空 */
        @Test
        @DisplayName("商品不存在：PRODUCT_NOT_FOUND")
        void productNotFound() {
            when(productDao.listByIds(anyCollection())).thenReturn(List.of());
            CreateOrderDTO dto = order(new OrderItemDTO(99L, 1));

            BizException ex = assertThrows(BizException.class, () -> orderCheckUnit.checkAndLoadProducts(dto));

            assertThat(ex.getErrorCode()).isEqualTo(ErrorCode.PRODUCT_NOT_FOUND);
            assertThat(ex.getMessage()).contains("productId=99");
        }

        /** 单行库存不足 */
        @Test
        @DisplayName("库存不足：STOCK_NOT_ENOUGH")
        void stockNotEnough() {
            when(productDao.listByIds(anyCollection())).thenReturn(List.of(product(1L, 1)));
            CreateOrderDTO dto = order(new OrderItemDTO(1L, 2));

            BizException ex = assertThrows(BizException.class, () -> orderCheckUnit.checkAndLoadProducts(dto));

            assertThat(ex.getErrorCode()).isEqualTo(ErrorCode.STOCK_NOT_ENOUGH);
        }

        /** 重复行合并后超库存：单行看都够，合计不够 */
        @Test
        @DisplayName("重复商品行合计超库存：STOCK_NOT_ENOUGH")
        void duplicateLinesExceedStock() {
            when(productDao.listByIds(anyCollection())).thenReturn(List.of(product(1L, 5)));
            // 两行各 3 件，单行都 <= 5，合计 6 > 5
            CreateOrderDTO dto = order(new OrderItemDTO(1L, 3), new OrderItemDTO(1L, 3));

            BizException ex = assertThrows(BizException.class, () -> orderCheckUnit.checkAndLoadProducts(dto));

            assertThat(ex.getErrorCode()).isEqualTo(ErrorCode.STOCK_NOT_ENOUGH);
        }
    }
}
```

用例设计思路（Given-When-Then，≈ Jest 的 Arrange-Act-Assert）：

```
checkAndLoadProducts
├── 明细为空           → PARAM_ERROR       + 不查库（verifyNoInteractions）
├── 数量 ≤ 0           → PARAM_ERROR       + 不查库
├── 商品不存在         → PRODUCT_NOT_FOUND
├── 单行库存不足       → STOCK_NOT_ENOUGH
├── 重复行合计超库存   → STOCK_NOT_ENOUGH  ← 最容易漏的边界
├── 正常               → 返回 Map + 只查一次（verify times(1)）
└── 重复行             → 查询 ID 去重（ArgumentCaptor）
```

运行：

```bash
./mvnw test                                  # 全部单测 + JaCoCo 报告
./mvnw test -Dtest=OrderCheckUnitTest        # 只跑一个类 ≈ jest OrderCheck
./mvnw test -Dtest='OrderCheckUnitTest$Fail' # 只跑一个 @Nested 分组
open target/site/jacoco/index.html           # 看覆盖率
```

#### 5.5.4 预览：Controller 切片测试

07 章会实现 `OrderController`。这里先展示切片测试的形态：只启动 MVC 层，把编排层 mock 掉，验证「URL → 参数绑定 → JSON 出参」这一段。

```java
package com.example.mall.controller;

import com.example.mall.biz.OrderBizComponent;
import com.example.mall.model.vo.OrderVO;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * OrderController 切片测试：只加载 Web 层，不连数据库
 */
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    /** 模拟 HTTP 请求的客户端 ≈ supertest */
    @Autowired
    private MockMvc mockMvc;

    /** 编排层不在 Web 切片中，用 mock 替换到 Spring 容器里（Boot 3.4 之前用 @MockBean） */
    @MockitoBean
    private OrderBizComponent orderBizComponent;

    /**
     * 查询订单详情：验证路由、路径参数绑定与 JSON 字段
     *
     * @throws Exception MockMvc 调用异常
     */
    @Test
    void getOrderDetail() throws Exception {
        OrderVO vo = new OrderVO();
        vo.setOrderNo("A001");
        vo.setTotalAmount(new BigDecimal("54.95"));
        when(orderBizComponent.getOrderDetail(1L, "A001")).thenReturn(vo);

        mockMvc.perform(get("/api/orders/{orderNo}", "A001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.orderNo").value("A001"))
                .andExpect(jsonPath("$.data.totalAmount").value(54.95));
    }
}
```

（`OrderBizComponent.getOrderDetail(Long userId, String orderNo)` 与 `GET /api/orders/{orderNo}` 以 07 章的定义为准。）

---

## 6. 常见坑

| # | 坑 | 现象 | 正解 |
|---|---|---|---|
| 1 | 照搬 npm 思维，以为「装了就能用」 | IDEA 里红一片 | pom 改动后要点 Maven 面板的 Reload（或开启自动导入） |
| 2 | 本地仓库下载中断 | `xxx.lastUpdated` 文件残留，之后一直报找不到依赖 | 删除对应目录后 `mvn -U` 重试 |
| 3 | 依赖冲突运行期才暴露 | 启动时 `NoSuchMethodError` | `mvn dependency:tree -Dverbose` 查，`dependencyManagement` 锁版本 |
| 4 | 自己乱写 Spring 组件版本 | Boot 3 项目引入了 Boot 2 时代的 starter，`javax.*` 与 `jakarta.*` 混用 | Spring 家族组件**不写版本**，交给 parent；三方 starter 认准 Boot 3 版本（如 `mybatis-plus-spring-boot3-starter`） |
| 5 | 生产依赖 SNAPSHOT | 同一版本号前后行为不一致 | 发布前全部切 RELEASE，可用 enforcer 插件 `requireReleaseDeps` 拦截 |
| 6 | `@Data` 用在有继承的实体上 | `equals` 忽略父类字段，两个不同对象相等 | 加 `@EqualsAndHashCode(callSuper = true)` 或不用 `@Data` |
| 7 | `@Data` 用于 JPA/双向关联实体 | `toString`/`hashCode` 互相递归 → `StackOverflowError` | 排除关联字段，或只用 `@Getter @Setter` |
| 8 | `@Builder` 后没有无参构造 | Jackson 反序列化失败、MyBatis 映射失败 | 加 `@NoArgsConstructor` + `@AllArgsConstructor` |
| 9 | `@Builder` 字段默认值丢失 | `private Integer status = 0;` 用 builder 构造后为 null | 字段加 `@Builder.Default` |
| 10 | 布尔字段用 `isDeleted` | Lombok 生成 `isDeleted()`，框架推断属性名为 `deleted`，序列化字段名错乱 | POJO 布尔字段不加 `is` 前缀 |
| 11 | 日志字符串拼接 | 关掉 DEBUG 仍有性能开销 | 用 `{}` 占位符 |
| 12 | `log.error("失败: {}", e)` / `log.error(e.getMessage())` | 前者把异常当占位参数可能丢堆栈语义，后者完全丢堆栈 | `log.error("失败, orderNo={}", orderNo, e)`，异常作为**最后一个、无对应占位**的参数 |
| 13 | 同时引入多个日志实现 | 启动打印 `SLF4J: Class path contains multiple bindings`，配置不生效 | exclusions 掉多余实现 |
| 14 | MDC 不清理 | 线程复用导致别的请求带上错误 traceId | `finally` 中 `MDC.remove` / `MDC.clear` |
| 15 | 单测里启动整个 Spring | 一个测试跑 20 秒，没人愿意写 | 业务逻辑用纯 Mockito 单测；必要时切片测试 |
| 16 | Mockito `UnnecessaryStubbingException` | 打了桩没用上，MockitoExtension 严格模式报错 | 删掉多余桩；确需宽松用 `lenient().when(...)` |
| 17 | 参数匹配器与原始值混用 | `when(dao.f(anyLong(), 1))` 报 `InvalidUseOfMatchersException` | 要么全用匹配器：`eq(1)` |
| 18 | 测试类/方法不被执行 | 类名不以 `Test` 结尾，或 import 了 JUnit 4 的 `org.junit.Test` | 命名 `XxxTest`；只用 `org.junit.jupiter.api.*` |
| 19 | BigDecimal 断言用 `isEqualTo` 失败 | `0.3` vs `0.30` scale 不同 | 比较数值用 `isEqualByComparingTo` |
| 20 | `.idea`、`target` 提交进 git | 仓库臃肿、冲突不断 | 按 3.8 配置 `.gitignore` |

---

## 7. 高级视角

### 7.1 依赖治理是团队级工程

- **公司级 BOM**：架构组维护 `company-dependencies`，统一 Spring Boot、中间件 SDK、工具库版本，业务项目只 import，不自己定版本；升级一次 BOM，全公司对齐。
- **构建期拦截**：`maven-enforcer-plugin` 规则：`requireJavaVersion`、`dependencyConvergence`（传递依赖版本必须收敛）、`banDuplicateClasses`、`requireReleaseDeps`、`bannedDependencies`（禁止 log4j 1.x、commons-logging 等）。
- **安全漏洞**：Log4Shell（CVE-2021-44228）事件教训——要能在分钟级回答「我们有哪些服务用了 log4j-core 2.x」。工具：OWASP Dependency-Check、Dependabot / Renovate、私服的漏洞扫描。
- **SDK 设计原则**（当你给别人提供二方包时）：依赖越少越好；能 `provided`/`optional` 的不要 `compile`；不要传递日志实现（只依赖 `slf4j-api`）；不要在二方包里带 `application.yml`；必要时 shade 重命名内部依赖。

### 7.2 构建效率

- 大型多模块项目：`mvn -T 1C`（每核一线程并行构建）、`-pl/-am` 增量构建、Maven Build Cache Extension；
- CI 缓存 `~/.m2/repository`（≈ 缓存 pnpm store）；
- 镜像分层：利用 fat jar 的 `layers.idx` 把依赖层与业务代码层分开，依赖不变时 Docker 层复用，推镜像只推几十 KB（12 章）。

### 7.3 日志体系的演进路线

```
阶段 1：单机文件日志 + grep           ← 本章
阶段 2：Filebeat 采集 → Kafka → Logstash → Elasticsearch → Kibana（ELK）
阶段 3：结构化日志（JSON 格式，logstash-logback-encoder），字段可检索
阶段 4：日志 + 指标 + 链路三者关联（TraceId 贯穿 SkyWalking/OpenTelemetry）  ← 12 章
```

高级工程师对日志的判断力：

- **日志是给半夜被叫醒的人看的**：每条关键日志问自己「只看这一行能定位问题吗？」；
- 日志量就是成本：ES 存储按 GB 计费，DEBUG 级别全开一天能打出 TB 级数据；
- 关键链路埋「业务日志」，例如订单状态每次流转一条，格式固定，便于对账与统计；
- 生产动态调级别：Spring Boot Actuator `POST /actuator/loggers/{包名}` 或 Nacos 配置，排查完再调回。

### 7.4 测试策略

- **可测性是设计问题**：难写单测的代码，通常是职责混杂、依赖隐式（`new` 出来的依赖、静态调用、直接读系统时间）。五层架构中，第五层纯函数最好测，第三层通过构造器注入 DAO 也好测——分层本身就在服务可测性。
- **时间可测**：注入 `java.time.Clock` 而不是直接 `LocalDateTime.now()`，测「30 分钟超时取消」时可以固定时间。
- **集成测试用真实中间件**：Testcontainers 在单测中拉起真实 MySQL/Redis/RocketMQ Docker 容器，比 H2 这种「方言不一致的替身」可靠得多。
- **测试的边界**：不要 mock 你不拥有的类型（如直接 mock `RedisTemplate` 的链式调用），而是 mock 你自己封装的 DAO/Client——这也是第四层「能力单元」存在的原因之一。
- **变异测试**（PIT）：故意修改代码（`<` 改 `<=`），看测试能否发现，衡量测试有效性，比覆盖率更诚实。

### 7.5 Java 8 存量项目差异速查

| 项 | Java 8 / Spring Boot 2.x | Java 21 / Spring Boot 3.x |
|---|---|---|
| 包名 | `javax.servlet`、`javax.validation` | `jakarta.servlet`、`jakarta.validation` |
| 测试 | JUnit 4（`@RunWith`、`@Before`）与 JUnit 5 混用 | 只用 JUnit 5（`@ExtendWith`、`@BeforeEach`） |
| Mock Bean | `@MockBean` | `@MockitoBean`（3.4+） |
| MyBatis-Plus | `mybatis-plus-boot-starter` | `mybatis-plus-spring-boot3-starter` |
| MySQL 驱动 | `mysql:mysql-connector-java` | `com.mysql:mysql-connector-j` |
| 编译配置 | `<source>1.8</source><target>1.8</target>` | `<release>21</release>`（parent 用 `java.version` 设置） |
| Mockito final 类 | 需手动开启 inline | 默认支持 |

---

## 8. 小练习

1. **环境**：用 SDKMAN 同时安装 JDK 8 与 21，在 mini-mall 目录下生成 `.sdkmanrc`，验证 `sdk env` 后 `java -version` 与 `./mvnw -v` 中的 JDK 一致。
2. **依赖冲突复现**：在 pom 中给 `jackson-databind` 加 `dependencyManagement` 强制降到一个很老的版本（如 2.9.0），启动项目观察报错；用 `mvn dependency:tree -Dverbose -Dincludes=com.fasterxml.jackson.core` 解释裁决结果，再恢复。
3. **生命周期**：分别执行 `mvn compile`、`mvn test`、`mvn package`，对比 `target/` 目录变化；解压 fat jar（`unzip -l`），找到 `MANIFEST.MF` 中的 `Main-Class` 与 `Start-Class`。
4. **Lombok 反编译**：对 `OrderItemPO.class` 执行 `javap -p target/classes/com/example/mall/model/po/OrderItemPO.class`，列出 Lombok 生成的方法；再把 `quantity` 改为 `isGift` 布尔字段，观察 getter 名。
5. **日志**：以 `--spring.profiles.active=prod` 启动，请求一个接口，确认 `logs/mini-mall.log` 中每行都有 traceId，且与响应头 `X-Trace-Id` 一致；用 `@Async` 或线程池打一条日志，观察 traceId 丢失，再用 4.6 节的 `TaskDecorator` 修复。
6. **单测补全**：为 `OrderCheckUnit` 增加用例「明细中 productId 为 null」；运行 `./mvnw verify`，查看 JaCoCo 报告中 `OrderCheckUnit` 的分支覆盖率，补齐未覆盖的分支直到 100%。
7. **思考题**：`OrderCheckUnit` 为什么返回 `Map<Long, ProductPO>` 而不是 `boolean`？如果下单流程再增加「商品已下架不可购买」校验，你会把它放在哪个方法、需要新增哪个 `ErrorCode`、补哪几条单测？
