# -*- coding: utf-8 -*-
"""HelloAgentsLLM：框架的模型调用中枢（第七章 7.2 节）。

对应教程的多提供商 + 自动检测设计，本项目统一走 Anthropic 协议
（复用本机 Claude Code 网关配置），provider 保留扩展点。
"""
import os
import sys
from typing import Iterator, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.llm_client import AnthropicCompatibleClient, load_env


class HelloAgentsLLM:
    """统一 LLM 客户端：自动检测 provider，对外提供 think/invoke/stream_invoke。"""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None,
                 base_url: Optional[str] = None, provider: str = "auto", **kwargs):
        load_env()
        if provider == "auto":
            provider = self._auto_detect_provider(api_key, base_url)
        self.provider = provider

        if provider == "anthropic":
            # 解析凭证：显式参数 > 真实环境变量 > .env
            self.model = model or os.getenv("ANTHROPIC_MODEL")
            resolved_key = api_key or os.getenv("ANTHROPIC_AUTH_TOKEN")
            resolved_url = base_url or os.getenv("ANTHROPIC_BASE_URL")
            if not all([self.model, resolved_key, resolved_url]):
                raise ValueError("缺少模型配置，请设置 ANTHROPIC_MODEL / ANTHROPIC_AUTH_TOKEN / ANTHROPIC_BASE_URL。")
            self.temperature = kwargs.get("temperature", 0.7)
            self.max_tokens = kwargs.get("max_tokens")
            self._inner = AnthropicCompatibleClient(
                model=self.model, auth_token=resolved_key, base_url=resolved_url)
        else:
            # 预留扩展点：其他 provider 参考教程 7.2.1 以继承方式接入
            raise ValueError(f"暂不支持的 provider: {provider}（可继承本类扩展，见教程 7.2.1）")

        print(f"✅ HelloAgentsLLM 就绪（provider={self.provider}, model={self.model}）")

    @staticmethod
    def _auto_detect_provider(api_key: Optional[str], base_url: Optional[str]) -> str:
        """按教程 7.2.3 的优先级自动检测 provider。"""
        # 1. 特定服务商环境变量（最高优先级）
        if os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY"):
            return "anthropic"
        # 2. base_url 特征
        url = (base_url or os.getenv("LLM_BASE_URL") or "").lower()
        if "anthropic" in url:
            return "anthropic"
        # 3. 默认
        return "anthropic"

    def invoke(self, messages: list[dict], **kwargs) -> str:
        """调用 LLM 返回完整文本。messages 为 OpenAI 风格的 [{"role","content"}] 列表。"""
        # anthropic 协议的 system 是独立参数，这里从 messages 中拆出
        system = "".join(m["content"] for m in messages if m["role"] == "system") or None
        rest = [m for m in messages if m["role"] != "system"]
        try:
            response = self._inner.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens or 16000,
                system=system,
                messages=rest,
            )
            return "".join(b.text for b in response.content if b.type == "text")
        except Exception as e:
            print(f"❌ 调用LLM API时发生错误: {e}")
            return ""

    def stream_invoke(self, messages: list[dict], **kwargs) -> Iterator[str]:
        """流式调用：以单个分块的形式产出完整文本（网关稳定优先）。"""
        yield self.invoke(messages, **kwargs)

    def think(self, messages: list[dict], **kwargs) -> Iterator[str]:
        """教程兼容方法：与 stream_invoke 等价。"""
        return self.stream_invoke(messages, **kwargs)
