# -*- coding: utf-8 -*-
"""第四章 ReAct 范式智能体：Thought -> Action -> Observation 循环。

参考教程：https://hello-agents.datawhale.cc/#/./chapter4/第四章%20智能体经典范式构建
与教程的差异：
  - 搜索工具用 Tavily（已有 key）替代 SerpApi
  - LLM 客户端复用 common/llm_client.py（Anthropic 协议，Claude Code 同款网关）
运行:
  .venv/bin/python chapter4/react_agent.py "华为最新的手机是哪一款？它的主要卖点是什么？"
"""
import os
import re
import sys

from tavily import TavilyClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.llm_client import AnthropicCompatibleClient, load_env

load_env()

# ReAct 提示词模板：角色定义 + 工具清单 + 格式规约 + 动态上下文
REACT_PROMPT_TEMPLATE = """
请注意，你是一个有能力调用外部工具的智能助手。

可用工具如下:
{tools}

请严格按照以下格式进行回应:

Thought: 你的思考过程，用于分析问题、拆解任务和规划下一步行动。
Action: 你决定采取的行动，必须是以下格式之一:
- `{{tool_name}}[{{tool_input}}]`:调用一个可用工具。
- `Finish[最终答案]`:当你认为已经获得最终答案时。
- 当你收集到足够的信息，能够回答用户的最终问题时，你必须在Action:字段后使用 Finish[最终答案] 来输出最终答案。

重要约束:
- 上述工具都是真实可调用的：你发出 Action 后，系统会执行并把结果以 Observation 回填给你。
- 你没有内置的实时知识，涉及时事/事实的信息必须先通过 Action 调用工具获取；
  在没有获得任何 Observation 之前，禁止声称"无法使用工具/无法查询"并使用 Finish。

交互示例（仅演示格式，History: 中会有你之前的真实轨迹）:
Thought: 我需要最新的实时信息，先搜索一下。
Action: Search[相关关键词]
（系统会在这里返回 Observation，你基于它继续思考或 Finish）

现在，请开始解决以下问题:
Question: {question}
History: {history}
"""


# ---------------- 工具实现 ----------------

def search(query: str) -> str:
    """基于 Tavily 的网页搜索工具，query 为搜索关键词，返回搜索结果摘要。"""
    print(f"🔍 正在执行 [Tavily] 网页搜索: {query}")
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "错误:TAVILY_API_KEY 未在 .env 文件中配置。"
    try:
        response = TavilyClient(api_key=api_key).search(
            query=query, search_depth="basic", max_results=3)
        # 返回前三条结果的标题与摘要，供 LLM 归纳
        snippets = [
            f"[{i + 1}] {res.get('title', '')}\n{res.get('content', '')}"
            for i, res in enumerate(response.get("results", []))
        ]
        if not snippets:
            return f"对不起，没有找到关于 '{query}' 的信息。"
        return "\n\n".join(snippets)
    except Exception as e:
        return f"搜索时发生错误: {e}"


def calculator(expression: str) -> str:
    """四则运算计算器工具，expression 为纯算术表达式（如 3+4*2），返回计算结果。"""
    print(f"🧮 正在执行计算: {expression}")
    # 白名单校验：LLM 输出不可信，只放行数字与四则运算符，防代码注入
    if not re.fullmatch(r"[\d+\-*/().\s]+", expression):
        return f"错误: '{expression}' 不是合法的算术表达式（只支持数字和 + - * / ( )）。"
    try:
        return str(eval(expression))  # noqa: S307 已通过上面的白名单校验
    except ZeroDivisionError:
        return "错误:除数不能为零。"
    except Exception as e:
        return f"计算时发生错误: {e}"


class ToolExecutor:
    """工具执行器：注册、查找工具，并生成工具清单描述。"""

    def __init__(self):
        # key 为工具名，value 为 {"description": 描述, "func": 执行函数}
        self.tools: dict[str, dict] = {}

    def register_tool(self, name: str, description: str, func):
        """注册一个工具。description 是 LLM 判断何时使用该工具的唯一依据。"""
        if name in self.tools:
            print(f"警告:工具 '{name}' 已存在，将被覆盖。")
        self.tools[name] = {"description": description, "func": func}
        print(f"工具 '{name}' 已注册。")

    def get_tool(self, name: str):
        """按名称取工具执行函数，不存在返回 None。"""
        return self.tools.get(name, {}).get("func")

    def get_available_tools(self) -> str:
        """生成"- 名称: 描述"格式的工具清单，注入提示词。"""
        return "\n".join(
            f"- {name}: {info['description']}" for name, info in self.tools.items())


# ---------------- ReAct 智能体 ----------------

class ReActAgent:
    """ReAct 智能体：循环执行 格式化提示词 -> 调用LLM -> 执行Action -> 整合Observation。"""

    def __init__(self, llm_client, tool_executor: ToolExecutor, max_steps: int = 5):
        self.llm_client = llm_client
        self.tool_executor = tool_executor
        self.max_steps = max_steps
        self.history: list[str] = []

    def run(self, question: str) -> str | None:
        """入口：回答 question，返回最终答案；达到最大步数仍无答案则返回 None。"""
        self.history = []  # 每次运行重置历史
        for step in range(1, self.max_steps + 1):
            print(f"--- 第 {step} 步 ---")

            # 1. 格式化提示词（工具清单 + 问题 + 累积历史）
            prompt = REACT_PROMPT_TEMPLATE.format(
                tools=self.tool_executor.get_available_tools(),
                question=question,
                history="\n".join(self.history),
            )

            # 2. 调用 LLM 思考
            response_text = self.llm_client.think([{"role": "user", "content": prompt}])
            if not response_text:
                print("错误:LLM未能返回有效响应。")
                return None

            # 3. 解析 Thought 与 Action
            thought, action = self._parse_output(response_text)
            if thought:
                print(f"🤔 思考: {thought}")
            if not action:
                print("警告:未能解析出有效的Action，流程终止。")
                return None

            # 4. Finish 指令 -> 提取最终答案结束
            if action.startswith("Finish"):
                final_answer = re.match(r"Finish\[(.*)\]", action, re.DOTALL).group(1)
                print(f"🎉 最终答案: {final_answer}")
                return final_answer

            # 5. 工具调用
            tool_name, tool_input = self._parse_action(action)
            if not tool_name:
                self.history.append(f"Action: {action}")
                self.history.append("Observation: 错误:Action 格式不合法，应为 工具名[输入] 或 Finish[答案]。")
                continue

            print(f"🎬 行动: {tool_name}[{tool_input}]")
            tool_function = self.tool_executor.get_tool(tool_name)
            observation = (tool_function(tool_input) if tool_function
                           else f"错误:未找到名为 '{tool_name}' 的工具。")

            # 6. Observation 回填历史，形成下一轮的上下文闭环
            print(f"👀 观察: {observation}")
            self.history.append(f"Action: {action}")
            self.history.append(f"Observation: {observation}")

        print("已达到最大步数，流程终止。")
        return None

    def _parse_output(self, text: str) -> tuple[str | None, str | None]:
        """从 LLM 回复中提取 Thought（到 Action 为止）与 Action（到结尾）。"""
        thought_match = re.search(r"Thought:\s*(.*?)(?=\nAction:|$)", text, re.DOTALL)
        action_match = re.search(r"Action:\s*(.*?)$", text, re.DOTALL)
        thought = thought_match.group(1).strip() if thought_match else None
        action = action_match.group(1).strip() if action_match else None
        return thought, action

    def _parse_action(self, action_text: str) -> tuple[str | None, str | None]:
        """从 Action 字符串解析工具名与输入，如 Search[华为最新手机] -> (Search, 华为最新手机)。"""
        match = re.match(r"(\w+)\[(.*)\]", action_text, re.DOTALL)
        if match:
            return match.group(1), match.group(2)
        return None, None


def build_agent() -> ReActAgent:
    """组装 LLM 客户端并注册工具，返回可运行的 ReAct 智能体。"""
    llm_client = AnthropicCompatibleClient()
    tool_executor = ToolExecutor()
    tool_executor.register_tool(
        "Search", "一个网页搜索引擎。当你需要回答关于时事、事实以及在你的知识库中找不到的信息时，应使用此工具。", search)
    tool_executor.register_tool(
        "Calculator", "一个四则运算计算器。当需要精确的数学计算时使用，输入为算术表达式，如 (3+4)*2。", calculator)
    return ReActAgent(llm_client, tool_executor, max_steps=5)


def chat():
    """终端交互模式：连续输入问题，每个问题独立跑一轮 ReAct 循环；空行/Ctrl+C 退出。"""
    agent = build_agent()
    print("ReAct 交互模式。输入问题回车开始，直接回车退出。")
    while True:
        try:
            question = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            break
        print("-" * 40)
        agent.run(question)
    print("再见。")


def main():
    """无参数进入交互模式；带参数则回答单个问题后退出。"""
    if len(sys.argv) < 2 or sys.argv[1] == "chat":
        chat()
        return

    agent = build_agent()
    if agent.run(sys.argv[1]) is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
