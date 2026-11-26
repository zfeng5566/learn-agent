# -*- coding: utf-8 -*-
"""Agent 抽象基类（教程 7.3.3）：所有智能体的统一接口。"""
from abc import ABC, abstractmethod
from typing import Optional

from hello_agents.core.config import Config
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.core.message import Message


class Agent(ABC):
    """Agent 基类：定义通用行为，强制子类实现 run 方法。"""

    def __init__(self, name: str, llm: HelloAgentsLLM,
                 system_prompt: Optional[str] = None, config: Optional[Config] = None):
        self.name = name
        self.llm = llm
        self.system_prompt = system_prompt
        self.config = config or Config()
        self._history: list[Message] = []

    @abstractmethod
    def run(self, input_text: str, **kwargs) -> str:
        """运行 Agent 的统一执行入口。"""
        ...

    def add_message(self, message: Message):
        """添加消息到历史记录。"""
        self._history.append(message)

    def clear_history(self):
        """清空历史记录。"""
        self._history.clear()

    def get_history(self) -> list[Message]:
        """获取历史记录副本。"""
        return self._history.copy()

    def __str__(self) -> str:
        return f"Agent(name={self.name}, provider={self.llm.provider})"
