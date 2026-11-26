# -*- coding: utf-8 -*-
"""ReActAgent（教程 7.4.2）：推理与行动结合，接入框架工具系统。"""
import re
from typing import List, Optional

from hello_agents.core.agent import Agent
from hello_agents.core.config import Config
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.core.message import Message
from hello_agents.tools.base import ToolRegistry

MY_REACT_PROMPT = """你是一个具备推理和行动能力的AI助手。你可以通过思考分析问题，然后调用合适的工具来获取信息，最终给出准确的答案。

## 可用工具
{tools}

## 工作流程
请严格按照以下格式进行回应，每次只能执行一个步骤:

Thought: 分析当前问题，思考需要什么信息或采取什么行动。
Action: 选择一个行动，格式必须是以下之一:
- `{{tool_name}}[{{tool_input}}]` - 调用指定工具
- `Finish[最终答案]` - 当你有足够信息给出最终答案时

## 重要提醒
1. 每次回应必须包含Thought和Action两部分
2. 工具调用的格式必须严格遵循:工具名[参数]
3. 只有当你确信有足够信息回答问题时，才使用Finish
4. 如果工具返回的信息不够，继续使用其他工具或相同工具的不同参数
5. 工具都是真实可调用的：你发出 Action 后，系统会执行并把结果以 Observation 回填给你；
   在没有获得任何 Observation 前，禁止声称无法调用工具并以 Finish 结束

## 交互示例（仅演示格式，不要照抄内容）
Thought: 我需要查询实时信息，先使用搜索工具。
Action: search[相关关键词]
（系统会在此处返回 Observation，你基于它继续思考或 Finish）

## 当前任务
**Question:** {question}

## 执行历史
{history}

现在开始你的推理和行动:
"""


class ReActAgent(Agent):
    """ReAct 智能体：Thought -> Action -> Observation 循环。"""

    def __init__(self, name: str, llm: HelloAgentsLLM, tool_registry: ToolRegistry,
                 system_prompt: Optional[str] = None, config: Optional[Config] = None,
                 max_steps: int = 5, custom_prompt: Optional[str] = None):
        super().__init__(name, llm, system_prompt, config)
        self.tool_registry = tool_registry
        self.max_steps = max_steps
        self.current_history: List[str] = []
        self.prompt_template = custom_prompt if custom_prompt else MY_REACT_PROMPT
        print(f"✅ {name} 初始化完成，最大步数: {max_steps}")

    def run(self, input_text: str, **kwargs) -> str:
        """运行 ReAct 循环：构建提示词 -> 调用LLM -> 解析 -> 执行 -> 回填历史。"""
        self.current_history = []
        current_step = 0

        print(f"\n🤖 {self.name} 开始处理问题: {input_text}")

        while current_step < self.max_steps:
            current_step += 1
            print(f"\n--- 第 {current_step} 步 ---")

            # 1. 构建提示词（工具清单 + 问题 + 累积历史）
            prompt = self.prompt_template.format(
                tools=self.tool_registry.get_tools_description(),
                question=input_text,
                history="\n".join(self.current_history),
            )

            # 2. 调用 LLM
            response_text = self.llm.invoke([{"role": "user", "content": prompt}], **kwargs)

            # 3. 解析输出
            thought, action = self._parse_output(response_text)
            if thought:
                print(f"🤔 Thought: {thought}")

            # 4. 检查完成条件
            if action and action.startswith("Finish"):
                final_answer = self._parse_action_input(action)
                self.add_message(Message(input_text, "user"))
                self.add_message(Message(final_answer, "assistant"))
                print(f"🎉 最终答案: {final_answer}")
                return final_answer

            # 5. 执行工具调用并回填观察
            if action:
                tool_name, tool_input = self._parse_action(action)
                observation = self.tool_registry.execute_tool(tool_name, tool_input)
                print(f"🎬 Action: {tool_name}[{tool_input}]\n👀 Observation: {observation}")
                self.current_history.append(f"Action: {action}")
                self.current_history.append(f"Observation: {observation}")
            else:
                self.current_history.append("Observation: 错误:未能解析出Action，请严格遵循格式。")

        final_answer = "抱歉，我无法在限定步数内完成这个任务。"
        self.add_message(Message(input_text, "user"))
        self.add_message(Message(final_answer, "assistant"))
        return final_answer

    @staticmethod
    def _parse_output(text: str) -> tuple[Optional[str], Optional[str]]:
        """分离 Thought（到 Action 为止）与 Action（到结尾）。"""
        thought_match = re.search(r"Thought:\s*(.*?)(?=\nAction:|$)", text, re.DOTALL)
        action_match = re.search(r"Action:\s*(.*?)$", text, re.DOTALL)
        thought = thought_match.group(1).strip() if thought_match else None
        action = action_match.group(1).strip() if action_match else None
        return thought, action

    @staticmethod
    def _parse_action(action_text: str) -> tuple[Optional[str], str]:
        """解析 工具名[参数] 格式，未知工具返回原名交由注册表报错。"""
        match = re.match(r"(\w+)\[(.*)\]", action_text, re.DOTALL)
        if match:
            return match.group(1), match.group(2)
        return None, ""

    @staticmethod
    def _parse_action_input(action: str) -> str:
        """从 Finish[答案] 中提取最终答案。"""
        match = re.match(r"Finish\[(.*)\]", action, re.DOTALL)
        return match.group(1) if match else action
