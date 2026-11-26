# -*- coding: utf-8 -*-
"""消息系统（教程 7.3.1）：框架内统一的消息格式。"""
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel

# 消息角色类型：直接对应 API 规范，保证类型安全
MessageRole = Literal["user", "assistant", "system", "tool"]


class Message(BaseModel):
    """消息类：对内携带时间戳与元数据，对外 via to_dict 保持 API 兼容。"""

    content: str
    role: MessageRole
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    def __init__(self, content: str, role: MessageRole, **kwargs):
        super().__init__(
            content=content,
            role=role,
            timestamp=kwargs.get("timestamp", datetime.now()),
            metadata=kwargs.get("metadata", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为 API 兼容的字典格式。"""
        return {"role": self.role, "content": self.content}

    def __str__(self) -> str:
        return f"[{self.role}] {self.content}"
