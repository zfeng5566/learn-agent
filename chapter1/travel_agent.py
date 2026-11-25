# -*- coding: utf-8 -*-
"""第一章动手体验：Thought-Action-Observation 范式的智能旅行助手。

参考教程：https://hello-agents.datawhale.cc/#/./chapter1/第一章%20初识智能体
LLM 客户端复用 common/llm_client.py（Anthropic 协议，与本机 Claude Code 配置一致）。
"""
import os
import re
import sys

import requests
from tavily import TavilyClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.llm_client import AnthropicCompatibleClient, load_env

load_env()

# 指令模板：告诉 LLM 它的角色、可用工具和输出格式（智能体的"说明书"）
AGENT_SYSTEM_PROMPT = """
你是一个智能旅行助手。你的任务是分析用户的请求，并使用可用工具一步步地解决问题。

# 可用工具:
- `get_weather(city: str)`: 查询指定城市的实时天气。
- `get_attraction(city: str, weather: str)`: 根据城市和天气搜索推荐的旅游景点。

# 输出格式要求:
你的每次回复必须严格遵循以下格式，包含一对Thought和Action：

Thought: [你的思考过程和下一步计划]
Action: [你要执行的具体行动]

Action的格式必须是以下之一：
1. 调用工具：function_name(arg_name="arg_value")
2. 结束任务：Finish[最终答案]

# 重要提示:
- 每次只输出一对Thought-Action
- Action必须在同一行，不要换行
- 当收集到足够信息可以回答用户问题时，必须使用 Action: Finish[最终答案] 格式结束
- 你不具备任何内置的实时数据，所有实时信息（天气、景点等）必须通过工具获取；
  在调用工具获得 Observation 之前，禁止以"无法查询/没有实时数据"为由使用 Finish

请开始吧！
"""


def get_weather(city: str) -> str:
    """查询指定城市的实时天气（wttr.in 免费 API）。

    入参: city 城市名；返回: 中文天气描述字符串。
    """
    url = f"https://wttr.in/{city}?format=j1"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        # current_condition 是列表，取第一个元素即当前实况
        current_condition = data['current_condition'][0]
        weather_desc = current_condition['weatherDesc'][0]['value']
        temp_c = current_condition['temp_C']
        return f"{city}当前天气:{weather_desc}，气温{temp_c}摄氏度"
    except requests.exceptions.RequestException as e:
        return f"错误:查询天气时遇到网络问题 - {e}"
    except (KeyError, IndexError) as e:
        return f"错误:解析天气数据失败，可能是城市名称无效 - {e}"


def get_attraction(city: str, weather: str) -> str:
    """根据城市和天气，用 Tavily 搜索并返回景点推荐。

    入参: city 城市名、weather 天气描述；返回: 推荐文本。
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return "错误:未配置TAVILY_API_KEY环境变量。"

    tavily = TavilyClient(api_key=api_key)
    query = f"'{city}' 在'{weather}'天气下最值得去的旅游景点推荐及理由"

    try:
        # include_answer=True 让 Tavily 基于搜索结果直接返回综合性回答
        response = tavily.search(query=query, search_depth="basic", include_answer=True)

        if response.get("answer"):
            return response["answer"]

        # 没有综合回答时退化为逐条格式化原始结果
        formatted_results = []
        for result in response.get("results", []):
            formatted_results.append(f"- {result['title']}: {result['content']}")

        if not formatted_results:
            return "抱歉，没有找到相关的旅游景点推荐。"

        return "根据搜索，为您找到以下信息:\n" + "\n".join(formatted_results)
    except Exception as e:
        return f"错误:执行Tavily搜索时出现问题 - {e}"


# 所有工具放入字典，主循环按名称调用
available_tools = {
    "get_weather": get_weather,
    "get_attraction": get_attraction,
}


def truncate_llm_output(llm_output: str) -> str:
    """模型可能输出多余的 Thought-Action 对，截断保留第一对。"""
    match = re.search(
        r'(Thought:.*?Action:.*?)(?=\n\s*(?:Thought:|Action:|Observation:)|\Z)',
        llm_output, re.DOTALL)
    if match and match.group(1).strip() != llm_output.strip():
        print("已截断多余的 Thought-Action 对")
        return match.group(1).strip()
    return llm_output


def execute_action(action_str: str) -> str | None:
    """解析并执行 Action。

    入参: action_str Action 行内容；返回: 观察结果文本，Finish 时返回 None。
    """
    if action_str.startswith("Finish"):
        return None  # 由调用方处理最终答案

    tool_name = re.search(r"(\w+)\(", action_str).group(1)
    args_str = re.search(r"\((.*)\)", action_str).group(1)
    # 只解析 key="value" 形式的字符串参数
    kwargs = dict(re.findall(r'(\w+)="([^"]*)"', args_str))

    if tool_name in available_tools:
        return available_tools[tool_name](**kwargs)
    return f"错误:未定义的工具 '{tool_name}'"


def main():
    """主入口：初始化 LLM 客户端并运行 Thought-Action-Observation 主循环。"""
    llm = AnthropicCompatibleClient()

    user_prompt = "你好，请帮我查询一下今天北京的天气，然后根据天气推荐一个合适的旅游景点。"
    prompt_history = [f"用户请求: {user_prompt}"]

    print(f"用户输入: {user_prompt}\n" + "=" * 40)

    for i in range(5):  # 最大循环次数，防止无限循环
        print(f"--- 循环 {i + 1} ---\n")

        # 1. 累积历史作为 prompt，调用 LLM 思考
        llm_output = llm.generate("\n".join(prompt_history), system_prompt=AGENT_SYSTEM_PROMPT)
        llm_output = truncate_llm_output(llm_output)
        print(f"模型输出:\n{llm_output}\n")
        prompt_history.append(llm_output)

        # 2. 解析 Action 行
        action_match = re.search(r"Action: (.*)", llm_output, re.DOTALL)
        if not action_match:
            observation_str = "Observation: 错误: 未能解析到 Action 字段。请确保你的回复严格遵循 'Thought: ... Action: ...' 的格式。"
            print(f"{observation_str}\n" + "=" * 40)
            prompt_history.append(observation_str)
            continue
        action_str = action_match.group(1).strip()

        # 3. Finish 表示任务完成，提取最终答案
        if action_str.startswith("Finish"):
            final_answer = re.match(r"Finish\[(.*)\]", action_str, re.DOTALL).group(1)
            print(f"任务完成，最终答案: {final_answer}")
            break

        # 4. 调用工具，记录 Observation 回历史供下一轮思考
        observation = execute_action(action_str)
        observation_str = f"Observation: {observation}"
        print(f"{observation_str}\n" + "=" * 40)
        prompt_history.append(observation_str)


if __name__ == '__main__':
    main()
