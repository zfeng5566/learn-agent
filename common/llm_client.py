# -*- coding: utf-8 -*-
"""公共基础组件：.env 加载与 Anthropic 协议 LLM 客户端，供各章节智能体复用。"""
import os

import anthropic

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env():
    """从项目根目录的 .env 文件加载环境变量（已存在的环境变量优先）。"""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


class AnthropicCompatibleClient:
    """通过 Anthropic SDK 调用任意 Anthropic 协议兼容服务的客户端。"""

    def __init__(self, model: str = None, auth_token: str = None, base_url: str = None):
        # 未传参时回退到 Claude Code 同款网关配置（真实环境变量优先于 .env）
        load_env()
        self.model = model or os.environ["ANTHROPIC_MODEL"]
        auth_token = auth_token or os.environ["ANTHROPIC_AUTH_TOKEN"]
        base_url = base_url or os.environ["ANTHROPIC_BASE_URL"]
        # auth_token 走 Authorization: Bearer 头，与 ANTHROPIC_AUTH_TOKEN 语义一致
        self.client = anthropic.Anthropic(auth_token=auth_token, base_url=base_url)

    def think(self, messages: list[dict]) -> str | None:
        """调用 LLM。messages 为 [{"role": ..., "content": ...}] 列表；失败返回 None。"""
        print(f"🧠 正在调用 {self.model} 模型...")
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=16000,
                messages=messages,
            )
            # content 是内容块列表，拼接其中的 text 块
            answer = "".join(block.text for block in response.content if block.type == "text")
            print("✅ 大语言模型响应成功。")
            return answer
        except Exception as e:
            print(f"❌ 调用LLM API时发生错误: {e}")
            return None

    def generate(self, prompt: str, system_prompt: str) -> str | None:
        """单轮生成：system_prompt 为指令模板，prompt 为用户内容。"""
        return self.think([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ])
