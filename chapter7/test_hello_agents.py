# -*- coding: utf-8 -*-
"""HelloAgents 框架综合测试（对应教程 7.4/7.5 的多个 test 文件，合并为一个）。

运行:
  ANTHROPIC_MODEL='gpt-6.1-terra[1m]' .venv/bin/python chapter7/test_hello_agents.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hello_agents import (HelloAgentsLLM, SimpleAgent, ReActAgent, ReflectionAgent,
                          PlanAndSolveAgent, ToolRegistry, SearchTool,
                          create_calculator_registry, ToolChain, ToolChainManager)


def test_calculator_tool():
    """教程 7.5.2：计算器工具基础测试。"""
    print("\n=== 测试0:计算器工具 ===")
    registry = create_calculator_registry()
    for expr in ["2 + 3", "10 - 4", "5 * 6", "15 / 3", "sqrt(16)"]:
        print(f"  {expr} = {registry.execute_tool('my_calculator', expr)}")


def test_simple_agent(llm):
    """教程 7.4.1：基础对话 / 工具增强 / 流式 / 动态工具管理。"""
    print("\n=== 测试1:SimpleAgent 基础对话 ===")
    basic_agent = SimpleAgent(
        name="基础助手", llm=llm,
        system_prompt="你是一个友好的AI助手，请用简洁明了的方式回答问题。")
    print(f"  响应: {basic_agent.run('你好，一句话介绍自己')}\n")

    print("=== 测试2:SimpleAgent 工具增强 ===")
    registry = create_calculator_registry()
    enhanced_agent = SimpleAgent(
        name="增强助手", llm=llm,
        system_prompt="你是一个智能助手，可以使用工具来帮助用户。",
        tool_registry=registry, enable_tool_calling=True)
    print(f"  响应: {enhanced_agent.run('请帮我计算 15 * 8 + 32')}\n")

    print("=== 测试3:SimpleAgent 流式响应 ===")
    for chunk in basic_agent.stream_run("用一句话解释什么是智能体"):
        print(f"  [流式块] {chunk}")

    print("\n=== 测试4:动态工具管理 ===")
    print(f"  添加工具前: {basic_agent.has_tools()}")
    basic_agent.add_tool(SearchTool())
    print(f"  添加工具后: {basic_agent.has_tools()}，可用工具: {basic_agent.list_tools()}")
    print(f"  对话历史: {len(basic_agent.get_history())} 条消息")


def test_react_agent(llm):
    """教程 7.4.2：ReAct 循环 + 工具系统。"""
    print("\n=== 测试5:ReActAgent ===")
    registry = ToolRegistry()
    registry.register_tool(SearchTool())
    calc = create_calculator_registry()
    for name in calc.list_tools():
        registry._functions[name] = calc._functions[name]
    agent = ReActAgent(name="ReAct助手", llm=llm, tool_registry=registry, max_steps=5)
    answer = agent.run("帮我搜索一下2026年世界杯在哪里举办，简单总结。")
    print(f"  ReAct 最终答案: {answer[:200]}")


def test_reflection_agent(llm):
    """教程 7.4.3：Reflection 迭代改进。"""
    print("\n=== 测试6:ReflectionAgent ===")
    agent = ReflectionAgent(name="反思助手", llm=llm, max_iterations=2)
    result = agent.run("写一句关于秋天的诗")
    print(f"  最终结果: {result}")


def test_plan_solve_agent(llm):
    """教程 7.4.4：Plan-and-Solve 规划执行。"""
    print("\n=== 测试7:PlanAndSolveAgent ===")
    agent = PlanAndSolveAgent(name="规划执行助手", llm=llm)
    question = ("一个水果店周一卖出了15个苹果。周二卖出的苹果数量是周一的两倍。"
                "周三卖出的数量比周二少了5个。请问这三天总共卖出了多少个苹果？")
    result = agent.run(question)
    print(f"  汇总: {result[-200:]}")


def test_tool_chain(llm):
    """教程 7.5.4：工具链顺序执行。"""
    print("\n=== 测试8:工具链 ===")
    registry = create_calculator_registry()
    chain = ToolChain(name="two_step_calc", description="两步计算")
    chain.add_step(tool_name="my_calculator", input_template="{input}", output_key="first")
    chain.add_step(tool_name="my_calculator",
                   input_template="({first}) * 2", output_key="final")
    manager = ToolChainManager(registry)
    manager.register_chain(chain)
    print(f"  (12+8)*2 = {manager.execute_chain('two_step_calc', '12+8')}")


if __name__ == "__main__":
    test_calculator_tool()
    llm = HelloAgentsLLM()
    test_simple_agent(llm)
    test_react_agent(llm)
    test_reflection_agent(llm)
    test_plan_solve_agent(llm)
    test_tool_chain(llm)
    print("\n✅ 全部测试执行完毕")
