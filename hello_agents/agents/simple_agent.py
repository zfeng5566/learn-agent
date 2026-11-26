# -*- coding: utf-8 -*-
"""SimpleAgent（教程 7.4.1）：基础对话 Agent，支持可选的工具调用与流式响应。"""
import re
from typing import Iterator, Optional

from hello_agents.core.agent import Agent
from hello_agents.core.config import Config
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.core.message import Message
from hello_agents.tools.base import ToolRegistry


class SimpleAgent(Agent):
    """基础对话智能体：无工具时纯对话；有工具时支持多轮 [TOOL_CALL:...] 调用。"""

    def __init__(self, name: str, llm: HelloAgentsLLM,
                 system_prompt: Optional[str] = None, config: Optional[Config] = None,
                 tool_registry: Optional[ToolRegistry] = None, enable_tool_calling: bool = True):
        super().__init__(name, llm, system_prompt, config)
        self.tool_registry = tool_registry
        self.enable_tool_calling = enable_tool_calling and tool_registry is not None
        print(f"✅ {name} 初始化完成，工具调用: {'启用' if self.enable_tool_calling else '禁用'}")

    def run(self, input_text: str, max_tool_iterations: int = 3, **kwargs) -> str:
        """运行：构建消息 -> 无工具直接对话 / 有工具进入多轮工具循环。"""
        print(f"🤖 {self.name} 正在处理: {input_text}")
        messages = [{"role": "system", "content": self._get_enhanced_system_prompt()}]
        messages += [{"role": m.role, "content": m.content} for m in self._history]
        messages.append({"role": "user", "content": input_text})

        if not self.enable_tool_calling:
            response = self.llm.invoke(messages, **kwargs)
            self.add_message(Message(input_text, "user"))
            self.add_message(Message(response, "assistant"))
            print(f"✅ {self.name} 响应完成")
            return response
        return self._run_with_tools(messages, input_text, max_tool_iterations, **kwargs)

    def stream_run(self, input_text: str, **kwargs) -> Iterator[str]:
        """流式运行：逐块产出响应。"""
        print(f"🌊 {self.name} 开始流式处理: {input_text}")
        messages = [{"role": "system", "content": self.system_prompt or "你是一个有用的AI助手。"}]
        messages += [{"role": m.role, "content": m.content} for m in self._history]
        messages.append({"role": "user", "content": input_text})

        full_response = ""
        for chunk in self.llm.stream_invoke(messages, **kwargs):
            full_response += chunk
            yield chunk
        self.add_message(Message(input_text, "user"))
        self.add_message(Message(full_response, "assistant"))
        print(f"\n✅ {self.name} 流式响应完成")

    # --- 工具调用核心逻辑 ---

    def _get_enhanced_system_prompt(self) -> str:
        """构建带工具说明的系统提示词，教模型用 [TOOL_CALL:名称:参数] 格式调用。"""
        base_prompt = self.system_prompt or "你是一个有用的AI助手。"
        if not self.enable_tool_calling or not self.tool_registry:
            return base_prompt
        tools_description = self.tool_registry.get_tools_description()
        if not tools_description or tools_description == "暂无可用工具":
            return base_prompt
        return (base_prompt
                + "\n\n## 可用工具\n你可以使用以下工具来帮助回答问题:\n" + tools_description
                + "\n\n## 工具调用格式\n当需要使用工具时，请使用以下格式:\n"
                + "`[TOOL_CALL:{tool_name}:{parameters}]`\n"
                + "例如:`[TOOL_CALL:search:Python编程]` 或 `[TOOL_CALL:my_calculator:sqrt(16)+2*3]`\n\n"
                + "工具调用结果会自动插入到对话中，然后你可以基于结果继续回答。\n")

    def _run_with_tools(self, messages: list, input_text: str,
                        max_tool_iterations: int, **kwargs) -> str:
        """多轮工具循环：检测并执行工具调用，把结果回填对话直到产出最终回答。"""
        current_iteration = 0
        final_response = ""

        while current_iteration < max_tool_iterations:
            response = self.llm.invoke(messages, **kwargs)
            tool_calls = self._parse_tool_calls(response)

            if not tool_calls:
                final_response = response  # 没有工具调用，即最终回答
                break

            print(f"🔧 检测到 {len(tool_calls)} 个工具调用")
            tool_results = []
            clean_response = response
            for call in tool_calls:
                tool_results.append(self._execute_tool_call(call["tool_name"], call["parameters"]))
                clean_response = clean_response.replace(call["original"], "")

            messages.append({"role": "assistant", "content": clean_response})
            results_text = "\n\n".join(tool_results)
            messages.append({"role": "user",
                             "content": f"工具执行结果:\n{results_text}\n\n请基于这些结果给出完整的回答。"})
            current_iteration += 1

        if not final_response:
            final_response = self.llm.invoke(messages, **kwargs)

        self.add_message(Message(input_text, "user"))
        self.add_message(Message(final_response, "assistant"))
        print(f"✅ {self.name} 响应完成")
        return final_response

    @staticmethod
    def _parse_tool_calls(text: str) -> list[dict]:
        """解析文本中的 [TOOL_CALL:名称:参数] 标记。"""
        matches = re.findall(r"\[TOOL_CALL:([^:]+):([^\]]+)\]", text)
        return [{"tool_name": n.strip(), "parameters": p.strip(),
                 "original": f"[TOOL_CALL:{n}:{p}]"} for n, p in matches]

    def _execute_tool_call(self, tool_name: str, parameters: str) -> str:
        """执行单个工具调用并格式化结果。"""
        if not self.tool_registry:
            return "❌ 错误:未配置工具注册表"
        try:
            result = self.tool_registry.execute_tool(tool_name, parameters)
            return f"🔧 工具 {tool_name} 执行结果:\n{result}"
        except Exception as e:
            return f"❌ 工具调用失败:{e}"

    # --- 工具管理便利方法 ---

    def add_tool(self, tool) -> None:
        """添加工具（无注册表时自动创建并启用工具调用）。"""
        if not self.tool_registry:
            self.tool_registry = ToolRegistry()
            self.enable_tool_calling = True
        if hasattr(tool, "name") and hasattr(tool, "run") and hasattr(tool, "get_parameters"):
            self.tool_registry.register_tool(tool)
        else:
            self.tool_registry.register_function(tool.name, tool.description, tool.run)
        print(f"🔧 工具 '{tool.name}' 已添加")

    def has_tools(self) -> bool:
        """是否有可用工具。"""
        return self.enable_tool_calling and self.tool_registry is not None

    def remove_tool(self, tool_name: str) -> bool:
        """移除工具（从注册表删除）。"""
        if self.tool_registry and tool_name in self.tool_registry.list_tools():
            self.tool_registry._tools.pop(tool_name, None)
            self.tool_registry._functions.pop(tool_name, None)
            return True
        return False

    def list_tools(self) -> list:
        """列出所有可用工具名。"""
        return self.tool_registry.list_tools() if self.tool_registry else []
