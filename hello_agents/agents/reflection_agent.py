# -*- coding: utf-8 -*-
"""ReflectionAgent（教程 7.4.3）：执行 -> 反思 -> 优化 的迭代自我改进。"""
from typing import Dict, Optional

from hello_agents.core.agent import Agent
from hello_agents.core.config import Config
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.core.message import Message

# 通用化提示词：适用于文本生成、分析、创作等多种场景
DEFAULT_PROMPTS = {
    "initial": """
请根据以下要求完成任务:

任务: {task}

请提供一个完整、准确的回答。
""",
    "reflect": """
请仔细审查以下回答，并找出可能的问题或改进空间:

# 原始任务:
{task}

# 当前回答:
{content}

请分析这个回答的质量，指出不足之处，并提出具体的改进建议。
如果回答已经很好，请回答"无需改进"。
""",
    "refine": """
请根据反馈意见改进你的回答:

# 原始任务:
{task}

# 上一轮回答:
{last_attempt}

# 反馈意见:
{feedback}

请提供一个改进后的回答。
""",
}


class ReflectionAgent(Agent):
    """Reflection 智能体：初稿 -> (评审 -> 无需改进则停 / 否则按反馈改进) 循环。"""

    def __init__(self, name: str, llm: HelloAgentsLLM, system_prompt: Optional[str] = None,
                 config: Optional[Config] = None, max_iterations: int = 3,
                 custom_prompts: Optional[Dict[str, str]] = None):
        super().__init__(name, llm, system_prompt, config)
        self.max_iterations = max_iterations
        self.prompts = {**DEFAULT_PROMPTS, **(custom_prompts or {})}
        print(f"✅ {name} 初始化完成，最大迭代轮数: {max_iterations}")

    def run(self, task: str, **kwargs) -> str:
        """运行：初始执行 -> 迭代反思与优化 -> 返回最终结果。"""
        print(f"\n🤖 {self.name} 开始处理任务: {task}")

        # 1. 初始执行
        answer = self.llm.invoke(
            [{"role": "user", "content": self.prompts["initial"].format(task=task)}], **kwargs)

        # 2. 迭代：反思 -> 终止 / 优化
        for i in range(1, self.max_iterations + 1):
            print(f"\n--- 第 {i}/{self.max_iterations} 轮迭代 ---")
            feedback = self.llm.invoke([{"role": "user", "content": self.prompts["reflect"].format(
                task=task, content=answer)}], **kwargs)

            if "无需改进" in feedback:
                print("✅ 反思认为回答已无需改进，任务完成。")
                break

            print("-> 正在根据反馈优化...")
            answer = self.llm.invoke([{"role": "user", "content": self.prompts["refine"].format(
                task=task, last_attempt=answer, feedback=feedback)}], **kwargs)

        self.add_message(Message(task, "user"))
        self.add_message(Message(answer, "assistant"))
        return answer
