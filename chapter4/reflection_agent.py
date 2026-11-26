# -*- coding: utf-8 -*-
"""第四章 Reflection 范式智能体：执行 -> 反思 -> 优化 的自我校正循环。

参考教程：https://hello-agents.datawhale.cc/#/./chapter4/第四章%20智能体经典范式构建
案例：让 LLM 写"求 1~n 素数"函数，由"评审员"角色批判算法效率并驱动迭代优化，
直到反思输出"无需改进"或达到最大迭代轮数。
运行:
  .venv/bin/python chapter4/reflection_agent.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.llm_client import AnthropicCompatibleClient, load_env

load_env()

# 初始执行提示词：直接要求完成任务
INITIAL_PROMPT_TEMPLATE = """
你是一位资深的Python程序员。请根据以下要求，编写一个Python函数。
你的代码必须包含完整的函数签名、文档字符串，并遵循PEP 8编码规范。

要求: {task}

请直接输出代码，不要包含任何额外的解释。
"""

# 反思提示词：扮演"极其严格的评审员"，专注批判算法效率
REFLECT_PROMPT_TEMPLATE = """
你是一位极其严格的代码评审专家和资深算法工程师，对代码的性能有极致的要求。
你的任务是审查以下Python代码，并专注于找出其在算法效率上的主要瓶颈。

# 原始任务:
{task}

# 待审查的代码:
```python
{code}
```

请分析该代码的时间复杂度，并思考是否存在一种算法上更优的解决方案来显著提升性能。
如果存在，请清晰地指出当前算法的不足，并提出具体的、可行的改进算法建议（例如，使用筛法替代试除法）。
如果代码在算法层面已经达到最优，才能回答"无需改进"。

请直接输出你的反馈，不要包含任何额外的解释。
"""

# 优化提示词：根据评审反馈修正代码
REFINE_PROMPT_TEMPLATE = """
你是一位资深的Python程序员。你正在根据一位代码评审专家的反馈来优化你的代码。

# 原始任务:
{task}

# 你上一轮尝试的代码:
{last_code_attempt}
评审员的反馈：
{feedback}

请根据评审员的反馈，生成一个优化后的新版本代码。
你的代码必须包含完整的函数签名、文档字符串，并遵循PEP 8编码规范。
请直接输出优化后的代码，不要包含任何额外的解释。
"""


class Memory:
    """短期记忆模块：按序存储每次"执行-反思"循环的轨迹。"""

    def __init__(self):
        # 元素为 {"type": 'execution'|'reflection', "content": 代码或反馈}
        self.records: list[dict] = []

    def add_record(self, record_type: str, content: str):
        """追加一条记录。record_type 取 'execution'（代码）或 'reflection'（反馈）。"""
        self.records.append({"type": record_type, "content": content})
        print(f"📝 记忆已更新，新增一条 '{record_type}' 记录。")

    def get_trajectory(self) -> str:
        """把记忆序列化为文本，可整体注入提示词提供完整上下文。"""
        parts = []
        for record in self.records:
            if record["type"] == "execution":
                parts.append(f"--- 上一轮尝试 (代码) ---\n{record['content']}")
            elif record["type"] == "reflection":
                parts.append(f"--- 评审员反馈 ---\n{record['content']}")
        return "\n\n".join(parts)

    def get_last_execution(self) -> str | None:
        """取最近一次执行结果（最新代码），没有则返回 None。"""
        for record in reversed(self.records):
            if record["type"] == "execution":
                return record["content"]
        return None


def extract_code(text: str) -> str:
    """从 LLM 回复中提取代码：优先取 ```python 代码块，无块则原样返回。"""
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


class ReflectionAgent:
    """Reflection 智能体：初始执行 -> (反思 -> 达标则停 / 否则优化) 循环。"""

    def __init__(self, llm_client, max_iterations: int = 3):
        self.llm_client = llm_client
        self.memory = Memory()
        self.max_iterations = max_iterations

    def run(self, task: str) -> str | None:
        """入口：完成 task 并迭代优化，返回最终代码。"""
        print(f"\n--- 开始处理任务 ---\n任务: {task}")

        # 1. 初始执行：生成初稿
        print("\n--- 正在进行初始尝试 ---")
        initial_prompt = INITIAL_PROMPT_TEMPLATE.format(task=task)
        initial_code = extract_code(self._think(initial_prompt))
        self.memory.add_record("execution", initial_code)

        # 2. 迭代循环：反思 -> 无需改进则停，否则优化
        for i in range(1, self.max_iterations + 1):
            print(f"\n--- 第 {i}/{self.max_iterations} 轮迭代 ---")

            print("\n-> 正在进行反思...")
            last_code = self.memory.get_last_execution()
            feedback = self._think(REFLECT_PROMPT_TEMPLATE.format(task=task, code=last_code))
            self.memory.add_record("reflection", feedback)

            # 终止条件：评审员认为算法已最优
            if "无需改进" in feedback:
                print("\n✅ 反思认为代码已无需改进，任务完成。")
                break

            print("\n-> 正在进行优化...")
            refined_code = extract_code(self._think(REFINE_PROMPT_TEMPLATE.format(
                task=task, last_code_attempt=last_code, feedback=feedback)))
            self.memory.add_record("execution", refined_code)

        final_code = self.memory.get_last_execution()
        print(f"\n--- 任务完成 ---\n最终生成的代码:\n```python\n{final_code}\n```")
        return final_code

    def _think(self, prompt: str) -> str:
        """调用 LLM 获取回复；失败返回空串并终止（由调用方判空）。"""
        response = self.llm_client.think([{"role": "user", "content": prompt}])
        if not response:
            sys.exit("错误:LLM未能返回有效响应。")
        return response


def main():
    """组装并运行：默认任务为素数函数，可从命令行传入其他编码任务。"""
    task = sys.argv[1] if len(sys.argv) > 1 else "编写一个Python函数，找出1到n之间所有的素数 (prime numbers)。"
    agent = ReflectionAgent(AnthropicCompatibleClient(), max_iterations=3)
    agent.run(task)


if __name__ == "__main__":
    main()
