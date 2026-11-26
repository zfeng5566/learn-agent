# -*- coding: utf-8 -*-
"""工具链高级特性（教程 7.5.4）：多工具的模板化顺序执行。"""
from typing import Any, Dict, List, Optional

from hello_agents.tools.base import ToolRegistry


class ToolChain:
    """工具链：按步骤顺序执行多个工具，支持模板变量引用前序结果。"""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        # 元素为 {"tool_name","input_template","output_key"}
        self.steps: List[Dict[str, Any]] = []

    def add_step(self, tool_name: str, input_template: str, output_key: str = None):
        """添加执行步骤。input_template 支持 {变量} 引用 context 与前序 output_key。"""
        self.steps.append({
            "tool_name": tool_name,
            "input_template": input_template,
            "output_key": output_key or f"step_{len(self.steps)}_result",
        })

    def execute(self, registry: ToolRegistry, initial_input: str,
                context: Dict[str, Any] = None) -> str:
        """执行工具链，返回最后一步的结果。"""
        context = context or {}
        context["input"] = initial_input
        print(f"🔗 开始执行工具链: {self.name}")

        for i, step in enumerate(self.steps, 1):
            try:
                tool_input = step["input_template"].format(**context)
            except KeyError as e:
                return f"❌ 工具链执行失败:模板变量 {e} 未找到"
            print(f"  步骤 {i}: 使用 {step['tool_name']} 处理 '{tool_input[:50]}...'")
            context[step["output_key"]] = registry.execute_tool(step["tool_name"], tool_input)
            print(f"  ✅ 步骤 {i} 完成，结果长度: {len(context[step['output_key']])} 字符")

        print(f"🎉 工具链 '{self.name}' 执行完成")
        return context[self.steps[-1]["output_key"]]


class ToolChainManager:
    """工具链管理器：注册与调度多条工具链。"""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self.chains: Dict[str, ToolChain] = {}

    def register_chain(self, chain: ToolChain):
        """注册工具链。"""
        self.chains[chain.name] = chain
        print(f"✅ 工具链 '{chain.name}' 已注册")

    def execute_chain(self, chain_name: str, input_data: str,
                      context: Dict[str, Any] = None) -> str:
        """执行指定工具链。"""
        if chain_name not in self.chains:
            return f"❌ 工具链 '{chain_name}' 不存在"
        return self.chains[chain_name].execute(self.registry, input_data, context)

    def list_chains(self) -> List[str]:
        """列出所有工具链名。"""
        return list(self.chains.keys())
