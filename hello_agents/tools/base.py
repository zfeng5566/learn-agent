# -*- coding: utf-8 -*-
"""工具系统基础（教程 7.5.1）：Tool 基类、参数定义与注册表。"""
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List

from pydantic import BaseModel


class ToolParameter(BaseModel):
    """工具参数定义：支持类型检查、默认值与文档生成。"""
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None


class Tool(ABC):
    """工具基类：统一 run 接口 + 自描述能力。"""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def run(self, parameters: Dict[str, Any]) -> str:
        """执行工具，接受字典参数，返回字符串结果。"""
        ...

    @abstractmethod
    def get_parameters(self) -> List[ToolParameter]:
        """获取工具参数定义。"""
        ...

    def to_openai_schema(self) -> Dict[str, Any]:
        """转换为 OpenAI function calling schema（供 FunctionCall 类 Agent 使用）。"""
        properties: Dict[str, Any] = {}
        required = []
        for param in self.get_parameters():
            prop: Dict[str, Any] = {"type": param.type, "description": param.description}
            if param.default is not None:
                prop["description"] = f"{param.description} (默认: {param.default})"
            if param.type == "array":
                prop["items"] = {"type": "string"}
            properties[param.name] = prop
            if param.required:
                required.append(param.name)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": properties, "required": required},
            },
        }


class ToolRegistry:
    """工具注册表：注册、发现、执行工具的管理中枢。"""

    def __init__(self):
        # key 为工具名；Tool 对象与注册函数分开存储
        self._tools: dict[str, Tool] = {}
        self._functions: dict[str, dict[str, Any]] = {}

    def register_tool(self, tool: Tool):
        """注册 Tool 对象（适合复杂工具）。"""
        if tool.name in self._tools:
            print(f"⚠️ 警告:工具 '{tool.name}' 已存在，将被覆盖。")
        self._tools[tool.name] = tool
        print(f"✅ 工具 '{tool.name}' 已注册。")

    def register_function(self, name: str, description: str, func: Callable[[str], str]):
        """直接注册函数作为工具（适合简单工具）。"""
        if name in self._functions:
            print(f"⚠️ 警告:工具 '{name}' 已存在，将被覆盖。")
        self._functions[name] = {"description": description, "func": func}
        print(f"✅ 工具 '{name}' 已注册。")

    def get_tool(self, name: str):
        """按名称获取工具（Tool 对象或 {"description","func"} 字典）。"""
        if name in self._tools:
            return self._tools[name]
        return self._functions.get(name)

    def execute_tool(self, name: str, tool_input: str) -> str:
        """统一执行入口：函数工具直接传字符串；Tool 对象包装为 {"input": ...}。"""
        if name in self._functions:
            return self._functions[name]["func"](tool_input)
        if name in self._tools:
            return self._tools[name].run({"input": tool_input, "query": tool_input})
        return f"❌ 错误:未找到工具 '{name}'"

    def get_tools_description(self) -> str:
        """生成"- 名称: 描述"格式的清单，可直接注入提示词。"""
        descriptions = [f"- {t.name}: {t.description}" for t in self._tools.values()]
        descriptions += [f"- {n}: {i['description']}" for n, i in self._functions.items()]
        return "\n".join(descriptions) if descriptions else "暂无可用工具"

    def list_tools(self) -> list[str]:
        """列出全部工具名。"""
        return list(self._tools) + list(self._functions)
