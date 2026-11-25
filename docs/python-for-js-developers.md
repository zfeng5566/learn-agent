# 写给前端工程师的 Python 快速入门

> 读者背景：熟悉 JS / TS / React / Node.js，目标是转型 Agent 工程师。
> 目标：用「JS 对照」的方式，1～2 小时内建立 Python 的全局认识，能读懂、能写 Agent 相关代码。

---

## 0. 一句话定位

| 维度 | JavaScript / Node.js | Python |
|---|---|---|
| 设计哲学 | 灵活、多范式、浏览器起家 | 「只有一种显而易见的写法」，可读性第一 |
| 主战场 | Web 前端、BFF、全栈 | AI / 数据科学 / 脚本 / 后端 / **Agent** |
| 运行时 | V8（Node、Deno、Bun） | CPython（官方），另有 PyPy 等 |
| 类型 | 动态 + TS 静态检查 | 动态 + Type Hints（mypy / pyright 检查） |
| 并发模型 | 单线程事件循环，天生异步 | 默认同步；`asyncio` 显式开启异步 |
| 包管理 | npm / pnpm / yarn | pip / **uv**（推荐）/ poetry |

**为什么 Agent 工程师必须会 Python**：OpenAI / Anthropic SDK、LangChain、LangGraph、LlamaIndex、CrewAI、AutoGen、MCP SDK、向量数据库客户端、模型微调与评估工具……生态首发几乎都是 Python。JS 版本通常是跟进版，功能会滞后。

---

## 1. 环境与工程化：对照 Node 生态

| Node 概念 | Python 对应 | 说明 |
|---|---|---|
| `node` | `python` / `python3` | 解释器 |
| `nvm` | `pyenv` / `uv python` | 多版本管理 |
| `npm install` | `pip install` / `uv add` | 安装依赖 |
| `package.json` | `pyproject.toml` | 项目元信息 + 依赖（现代标准） |
| `package-lock.json` | `uv.lock` / `poetry.lock` | 锁版本 |
| `requirements.txt` | — | 老式依赖清单，仍很常见（本仓库就在用） |
| `node_modules`（项目内） | **虚拟环境 `.venv`** | ⚠️ 关键差异，见下 |
| `npx xxx` | `uvx xxx` / `pipx run xxx` | 临时运行 CLI |
| `npm run dev` | 无内置，用 `Makefile` / shell 脚本 / `uv run` | |
| ESLint + Prettier | **Ruff**（一个工具全包） | |
| Jest / Vitest | **pytest** | |
| TypeScript `tsc` | mypy / pyright | |
| `.env` + dotenv | `python-dotenv` | 用法几乎一样 |

### 虚拟环境：最容易踩的坑

Node 的依赖天然装在项目的 `node_modules` 里；**Python 的 `pip install` 默认装到全局**。所以每个项目都要先建一个虚拟环境：

```bash
# 传统方式
python3 -m venv .venv
source .venv/bin/activate      # 激活后，python / pip 都指向 .venv
pip install -r requirements.txt

# 推荐方式：uv（Rust 写的，速度和体验类似 pnpm）
uv init my-agent && cd my-agent
uv add anthropic python-dotenv  # 自动建 .venv、写 pyproject.toml、生成锁文件
uv run main.py                  # 无需手动 activate
```

> 判断是否激活成功：`which python` 应指向 `.venv/bin/python`。

---

## 2. 语法速览：JS → Python 对照

### 2.1 基础写法

```python
# 注释用 #，没有分号，没有花括号 —— 用「缩进」表示代码块（4 个空格）
name = "Alice"              # 没有 let/const/var，直接赋值
MAX_RETRY = 3               # 常量只是命名约定（全大写），语言不强制
age: int = 18               # 可选的类型注解

if age >= 18 and name != "":    # && → and，|| → or，! → not
    print(f"Hi {name}")         # 模板字符串：`Hi ${name}` → f"Hi {name}"
elif age > 10:                  # else if → elif
    pass                        # 空块必须写 pass
else:
    print("kid")
```

| JS | Python | 备注 |
|---|---|---|
| `null` / `undefined` | `None` | 只有一个「空」 |
| `true` / `false` | `True` / `False` | 首字母大写 |
| `===` | `==` | Python 没有隐式类型转换，`1 == "1"` 是 `False` |
| 引用比较 `===`（对象） | `is` | `x is None` 是判空惯用写法 |
| `a ?? b` | `a if a is not None else b` | 无 `??` 运算符 |
| `a \|\| b` | `a or b` | 行为相同（返回第一个真值） |
| `cond ? a : b` | `a if cond else b` | 三元表达式顺序不同 |
| `typeof x` | `type(x)` / `isinstance(x, str)` | 推荐 `isinstance` |
| `console.log` | `print` | |
| `JSON.stringify / parse` | `json.dumps / json.loads` | 需 `import json` |
| `a?.b` | 无，用 `getattr(a, "b", None)` 或 `d.get("b")` | |

**真值差异**：Python 里**空列表 `[]`、空字典 `{}`、空字符串、`0`、`None` 都是假值**。JS 里 `[]` 和 `{}` 是真值——这一点很容易写出 bug。

```python
if not items:   # 判断列表为空的惯用写法
    ...
```

### 2.2 数据结构

| JS | Python | 示例 |
|---|---|---|
| `Array` | `list` | `nums = [1, 2, 3]` |
| 普通对象 / `Map` | `dict` | `user = {"name": "a", "age": 1}` |
| `Set` | `set` | `s = {1, 2, 3}` |
| —— | `tuple`（不可变列表） | `point = (1, 2)` |

```python
user = {"name": "Alice"}
user["name"]            # ✅ 必须用中括号 + 字符串 key，没有 user.name
user["email"]           # ❌ KeyError！不会返回 undefined
user.get("email")       # ✅ 不存在返回 None
user.get("email", "")   # ✅ 带默认值

# 解构
a, b = [1, 2]                     # const [a, b] = [1, 2]
first, *rest = [1, 2, 3]          # const [first, ...rest] = ...
merged = {**obj1, **obj2}         # { ...obj1, ...obj2 }
combined = [*arr1, *arr2]         # [...arr1, ...arr2]
# ⚠️ 没有对象解构 const { name } = user，需写 name = user["name"]

# 切片（JS 没有，非常常用）
nums[1:3]    # slice(1, 3)
nums[-1]     # 最后一个元素（at(-1)）
nums[::-1]   # 反转
```

### 2.3 循环与推导式

```python
for item in items:                    # for...of
    ...
for i, item in enumerate(items):      # items.forEach((item, i) => ...)
    ...
for key, value in user.items():       # Object.entries(user)
    ...
for i in range(5):                    # for (let i = 0; i < 5; i++)
    ...

# 推导式：Python 的 map/filter，更地道
squares = [x * x for x in nums]                 # nums.map(x => x * x)
evens   = [x for x in nums if x % 2 == 0]       # nums.filter(...)
index   = {u["id"]: u for u in users}           # Object.fromEntries(users.map(...))

total = sum(nums)                               # reduce 求和
any(x > 10 for x in nums)                       # nums.some(...)
all(x > 0 for x in nums)                        # nums.every(...)
sorted(users, key=lambda u: u["age"])           # [...users].sort((a,b)=>a.age-b.age)
```

### 2.4 函数

```python
# lambda 只能写一个表达式，复杂逻辑请用 def
add = lambda a, b: a + b

def greet(name: str, greeting: str = "Hello", *args, **kwargs) -> str:
    """文档字符串（docstring）：相当于 JSDoc。"""
    return f"{greeting}, {name}"

greet("Alice", greeting="Hi")   # ✅ 关键字参数：Python 一大特色，代替 JS 的 options 对象
```

| JS | Python |
|---|---|
| `(...args)` | `*args`（位置参数元组） |
| `({ a, b, ...opts })` | `**kwargs`（关键字参数字典） |
| `fn(...arr)` | `fn(*arr)` |
| `fn({ ...obj })` | `fn(**obj)` |

⚠️ **经典坑：可变默认参数**

```python
def add_item(item, items=[]):    # ❌ 这个 [] 只在定义时创建一次，所有调用共享！
    items.append(item)
    return items

def add_item(item, items=None):  # ✅ 正确写法
    items = items if items is not None else []
    ...
```

### 2.5 类

```python
class Agent:
    def __init__(self, name: str):      # constructor
        self.name = name                # this.name → self.name，且 self 必须显式写在参数里
        self._history = []              # 单下划线 = 约定私有（没有真正的 #private）

    def run(self, task: str) -> str:    # 每个实例方法第一个参数都是 self
        return f"{self.name} doing {task}"

    def __repr__(self):                 # 类似 toString()，「魔术方法」以双下划线包围
        return f"Agent({self.name})"

class CodingAgent(Agent):               # extends
    def run(self, task):
        return super().run(task) + " with code"

agent = CodingAgent("bob")              # 没有 new
```

**更常用的：数据类**（类似 TS interface + 自动构造函数）

```python
from dataclasses import dataclass

@dataclass
class Message:
    role: str
    content: str

msg = Message(role="user", content="hi")
```

Agent 开发里更常见的是 **Pydantic**（相当于 Zod：运行时校验 + 类型），工具调用参数、结构化输出几乎都用它：

```python
from pydantic import BaseModel

class WeatherArgs(BaseModel):
    city: str
    unit: str = "celsius"

args = WeatherArgs.model_validate({"city": "Beijing"})   # zod.parse()
WeatherArgs.model_json_schema()                          # 直接生成 JSON Schema 给 LLM 用
```

### 2.6 模块与导入

```python
import json                              # import json from 'json'（标准库，无需安装）
from pathlib import Path                 # import { Path } from 'pathlib'
from .utils import helper                # 相对导入 './utils'
import numpy as np                       # import * as np from 'numpy'
```

- **一个 `.py` 文件就是一个模块**，没有 `export`，文件中所有顶层名字都可以被导入。
- 文件夹作为包时，通常放一个 `__init__.py`（类似 `index.js`）。
- 入口惯用写法（相当于「只在直接执行时运行」）：

```python
if __name__ == "__main__":
    main()
```

### 2.7 异常处理

```python
try:
    data = json.loads(text)
except json.JSONDecodeError as e:   # catch (e)，可按类型分别捕获
    print(f"解析失败: {e}")
except Exception:
    raise                           # throw，向上重新抛出
else:
    print("没异常时执行")            # JS 没有
finally:
    cleanup()

raise ValueError("参数错误")         # throw new Error(...)
```

### 2.8 上下文管理器 `with`（JS 没有直接等价物）

自动管理资源的打开/关闭，类似 `try...finally` 的语法糖：

```python
with open("data.txt", encoding="utf-8") as f:   # 离开代码块自动关闭文件
    content = f.read()
```

---

## 3. 关键差异深度对比（重点）

### 3.1 异步：最大的思维转换

| | Node.js | Python |
|---|---|---|
| 默认模式 | 一切 I/O 都是异步 | **默认同步阻塞**，`requests.get()` 会卡住整个程序 |
| 事件循环 | 自动存在 | 需要 `asyncio.run()` 手动启动 |
| 生态 | 所有库都是异步的 | 同步/异步两套 API 并存（如 `requests` vs `httpx`、`Anthropic` vs `AsyncAnthropic`） |
| `Promise.all` | ✅ | `asyncio.gather()` |
| 不 await 直接调用 | 返回 Promise，仍会执行 | 返回协程对象，**根本不会执行** ⚠️ |

```python
import asyncio
import httpx

async def fetch(url: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        return resp.text

async def main():
    results = await asyncio.gather(fetch("https://a.com"), fetch("https://b.com"))
    print(len(results))

asyncio.run(main())   # 顶层入口，相当于启动事件循环
```

**实践建议**：入门和写脚本时，**先用同步写法**，代码更简单；需要并发调用多个 LLM / 工具、或写 Web 服务时，再切换到 async。

### 3.2 并发与 GIL

- Python 有 **GIL（全局解释器锁）**：同一时刻只有一个线程执行 Python 字节码。
- 对 Agent 开发影响不大：Agent 主要是 **I/O 密集**（等 LLM、等 HTTP），用 `asyncio` 或线程即可。
- CPU 密集任务用 `multiprocessing`（多进程）。Python 3.13+ 提供实验性的 free-threaded（无 GIL）版本。

### 3.3 类型系统：Type Hints ≠ TypeScript

```python
def call(messages: list[dict[str, str]], model: str | None = None) -> str: ...
```

- 类型注解**运行时不生效**，传错类型也照样运行（与 TS 编译后擦除类似，但 Python 没有编译步骤去拦截）。
- 需要 IDE（Pylance / PyCharm）或 `mypy` 做静态检查。
- 需要运行时校验时用 **Pydantic**。

| TS | Python |
|---|---|
| `string \| null` | `str \| None` |
| `string[]` | `list[str]` |
| `Record<string, number>` | `dict[str, int]` |
| `interface` | `TypedDict` / `Protocol` / `dataclass` / Pydantic `BaseModel` |
| `type A = 'a' \| 'b'` | `Literal["a", "b"]` |
| `any` | `Any` |
| 泛型 `<T>` | `def f[T](x: T) -> T`（3.12+）或 `TypeVar` |

### 3.4 作用域

```python
count = 0
def inc():
    global count     # ⚠️ 要修改外部变量必须声明 global / nonlocal，否则报错
    count += 1
```

- Python **只有函数级作用域**，`if` / `for` 块里定义的变量在块外依然可以访问（类似 `var`）。
- 没有 `this` 绑定问题，`self` 是显式传入的，告别 `bind` / 箭头函数之争。

### 3.5 字符串

- 单引号、双引号完全等价；三引号 `"""..."""` 是多行字符串（写 Prompt 时很常用）。
- 字符串不可变，常用方法：`s.strip()`（trim）、`s.split(",")`、`",".join(list)`（⚠️ 与 JS 的 `arr.join(",")` 顺序相反）、`s.startswith()`、`s.replace()`。

```python
SYSTEM_PROMPT = f"""
你是一个旅行助手。
当前用户：{user_name}
"""
```

---

## 4. 心智模型速记表

| 我想要…（JS 思维） | Python 怎么做 |
|---|---|
| `arr.length` | `len(arr)` |
| `arr.push(x)` | `arr.append(x)` |
| `arr.includes(x)` | `x in arr` |
| `obj.hasOwnProperty(k)` | `k in d` |
| `Object.keys(obj)` | `d.keys()` / `list(d)` |
| `arr.map(fn)` | `[fn(x) for x in arr]` |
| `str.includes(sub)` | `sub in s` |
| `parseInt("1")` | `int("1")` |
| `String(1)` | `str(1)` |
| `Math.floor(7/2)` | `7 // 2` |
| `2 ** 10` | `2 ** 10` |
| `setTimeout` | `time.sleep()` / `await asyncio.sleep()` |
| `process.env.KEY` | `os.environ["KEY"]` / `os.getenv("KEY")` |
| `fetch` | `httpx` / `requests` |
| `fs.readFileSync` | `Path("a.txt").read_text()` |
| `express` / `koa` | **FastAPI**（类型驱动，自动生成接口文档） |
| `zod` | **Pydantic** |
| 装饰器（TS 实验特性） | `@decorator`，原生且极其常用 |

---

## 5. 装饰器：Python 框架的灵魂

装饰器就是「接收函数、返回新函数」的高阶函数，用 `@` 语法糖挂载。Agent 框架大量用它来**注册工具**：

```python
# MCP Server 注册工具
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("weather")

@mcp.tool()
def get_weather(city: str) -> str:
    """查询城市天气"""          # docstring 会被当作工具描述发给 LLM
    return f"{city}: 晴 25°C"

# FastAPI 注册路由
@app.post("/chat")
async def chat(req: ChatRequest): ...
```

注意：框架会直接读取**函数签名的类型注解 + docstring** 来生成工具的 JSON Schema，所以在 Python 中，类型注解和注释本身就是「接口定义」。

---

## 6. Agent 工程师的 Python 技术栈地图

```
语言基础 ─┬─ 类型注解 + Pydantic（结构化数据、工具参数）
          ├─ asyncio（并发调用 LLM / 工具）
          └─ 装饰器 / 生成器 yield（流式输出）

模型调用 ─── anthropic / openai SDK（流式、tool use、prompt caching）

Agent 框架 ─┬─ 轻量：手写 ReAct 循环（强烈建议先手写一遍，理解本质）
            ├─ LangGraph（状态机式编排，生产常用）
            ├─ Claude Agent SDK / OpenAI Agents SDK
            └─ CrewAI / AutoGen（多 Agent 协作）

工具协议 ─── MCP（Model Context Protocol）Python SDK

RAG ─────┬─ 向量库：Chroma / Qdrant / pgvector / Milvus
         └─ 文档处理：LlamaIndex、unstructured

服务化 ──── FastAPI + uvicorn（SSE 流式输出给前端）

评估观测 ── pytest、LangSmith / Langfuse
```

**前端背景是优势**：Agent 产品最终需要 UI（流式渲染、工具调用可视化、Human-in-the-loop 交互）。Python 写后端 Agent + React 写交互，这是非常有竞争力的组合。

---

## 7. 一个最小 Agent 示例（综合上述语法）

```python
import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()                                  # 读取 .env
client = Anthropic()                           # 自动读取 ANTHROPIC_API_KEY


def get_weather(city: str) -> str:
    """模拟天气工具。"""
    return f"{city}：晴，25°C"


TOOLS = [{
    "name": "get_weather",
    "description": "查询城市天气",
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
}]


def run(question: str) -> str:
    """ReAct 循环：模型思考 → 调用工具 → 观察结果 → 直到给出最终答案。"""
    messages = [{"role": "user", "content": question}]
    while True:
        resp = client.messages.create(
            model="claude-sonnet-5-5", max_tokens=1024,
            tools=TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":     # 没有工具调用 → 结束
            return "".join(b.text for b in resp.content if b.type == "text")

        # 执行所有工具调用，并将结果回传给模型
        results = [
            {"type": "tool_result", "tool_use_id": b.id, "content": get_weather(**b.input)}
            for b in resp.content if b.type == "tool_use"
        ]
        messages.append({"role": "user", "content": results})


if __name__ == "__main__":
    print(run("北京今天天气怎么样？"))
```

这段代码用到了：import、函数、类型注解、docstring、字典 / 列表、推导式、`**` 解包、`while` 循环、`__main__` 入口——基本覆盖了日常 80% 的语法。

---

## 8. 常见坑清单（JS 开发者专属）

1. **缩进就是语法**：混用 Tab 和空格会报错，统一用 4 个空格。
2. **忘记激活虚拟环境**，导致包装到全局，或提示 `ModuleNotFoundError`。
3. `dict["key"]` 在 key 不存在时**直接抛异常**，不会返回 `undefined`，用 `.get()`。
4. **空列表 / 空字典是假值**。
5. **可变默认参数** `def f(x=[])`。
6. 调用 async 函数**忘了 `await`**，代码静默不执行（只有一个 warning）。
7. 在 async 函数中调用同步阻塞库（如 `requests`、`time.sleep`），会卡死事件循环。
8. 整数除法：`7 / 2 == 3.5`，`7 // 2 == 3`。
9. 没有 `++` / `--`，用 `+= 1`。
10. 文件名不要和标准库或三方库重名（如 `json.py`、`anthropic.py`），否则会被优先导入，引发诡异报错。
11. 字符串拼接数字要显式转换：`"a" + str(1)`，Python 不会自动转换类型。

---

## 9. 学习路径建议

| 阶段 | 内容 | 时间 |
|---|---|---|
| 1 | 本文 + 官方 Tutorial 前 9 章（docs.python.org/zh-cn/3/tutorial） | 2–3 天 |
| 2 | 用 uv 建项目，手写 ReAct Agent（不使用框架） | 2–3 天 |
| 3 | Pydantic + asyncio + FastAPI，把 Agent 包装成 SSE 流式接口，用 React 对接 | 1 周 |
| 4 | MCP Server 开发 + RAG（向量库） | 1 周 |
| 5 | LangGraph / Claude Agent SDK，多 Agent、记忆、评估 | 持续 |

**核心心法**：不用把 Python 当成新语言从头学，而是把它看作「**语法更严格、默认同步、AI 生态更强的 JS**」。先能读懂、能改代码，再逐步掌握地道写法（Pythonic）。
