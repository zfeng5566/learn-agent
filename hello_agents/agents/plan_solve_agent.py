# -*- coding: utf-8 -*-
"""PlanAndSolveAgent（教程 7.4.4）：先规划（强制列表格式）后逐步执行。"""
import ast
import re
from typing import Dict, Optional

from hello_agents.core.agent import Agent
from hello_agents.core.config import Config
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.core.message import Message

DEFAULT_PLANNER_PROMPT = """
你是一个顶级的AI规划专家。你的任务是将用户提出的复杂问题分解成一个由多个简单步骤组成的行动计划。
请确保计划中的每个步骤都是一个独立的、可执行的子任务，并且严格按照逻辑顺序排列。
你的输出必须是一个Python列表，其中每个元素都是一个描述子任务的字符串。

问题: {question}

请严格按照以下格式输出你的计划:
```python
["步骤1", "步骤2", "步骤3", ...]
```
"""

DEFAULT_EXECUTOR_PROMPT = """
你是一位顶级的AI执行专家。你的任务是严格按照给定的计划，一步步地解决问题。
你将收到原始问题、完整的计划、以及到目前为止已经完成的步骤和结果。
请你专注于解决"当前步骤"，并仅输出该步骤的最终答案，不要输出任何额外的解释或对话。

# 原始问题:
{question}

# 完整计划:
{plan}

# 历史步骤与结果:
{history}

# 当前步骤:
{current_step}

请仅输出针对"当前步骤"的回答:
"""


class PlanAndSolveAgent(Agent):
    """Plan-and-Solve 智能体：规划器输出步骤列表，执行器逐步求解。"""

    def __init__(self, name: str, llm: HelloAgentsLLM, system_prompt: Optional[str] = None,
                 config: Optional[Config] = None, custom_prompts: Optional[Dict[str, str]] = None):
        super().__init__(name, llm, system_prompt, config)
        self.planner_prompt = (custom_prompts or {}).get("planner", DEFAULT_PLANNER_PROMPT)
        self.executor_prompt = (custom_prompts or {}).get("executor", DEFAULT_EXECUTOR_PROMPT)
        print(f"✅ {name} 初始化完成")

    def run(self, input_text: str, **kwargs) -> str:
        """运行：规划 -> 逐步执行 -> 汇总最终结果。"""
        print(f"\n🤖 {self.name} 开始处理问题: {input_text}")

        # 1. 规划阶段：强制 Python 列表格式输出
        plan_response = self.llm.invoke(
            [{"role": "user", "content": self.planner_prompt.format(question=input_text)}], **kwargs)
        plan = self._parse_plan(plan_response)
        print(f"📋 计划（{len(plan)} 步）:")
        for i, step in enumerate(plan, 1):
            print(f"   {i}. {step}")

        # 2. 执行阶段：逐步求解并累积历史
        history = ""
        for i, step in enumerate(plan, 1):
            print(f"\n--- 执行步骤 {i}/{len(plan)}: {step} ---")
            result = self.llm.invoke([{"role": "user", "content": self.executor_prompt.format(
                question=input_text, plan=plan, history=history or "（无）",
                current_step=step)}], **kwargs)
            print(f"   ✅ {result[:100]}{'...' if len(result) > 100 else ''}")
            history += f"步骤{i} [{step}]: {result}\n"

        final_answer = history.strip()
        self.add_message(Message(input_text, "user"))
        self.add_message(Message(final_answer, "assistant"))
        print(f"\n🎉 最终结果:\n{final_answer}")
        return final_answer

    @staticmethod
    def _parse_plan(text: str) -> list[str]:
        """从规划器输出解析步骤列表：优先取代码块，异常时按行兜底。"""
        match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
        plan_text = match.group(1) if match else text
        try:
            parsed = ast.literal_eval(plan_text.strip())
            if isinstance(parsed, list):
                return [str(s) for s in parsed]
        except Exception:
            pass
        # 兜底：把非空行当作步骤
        return [line.strip() for line in plan_text.splitlines() if line.strip()]
