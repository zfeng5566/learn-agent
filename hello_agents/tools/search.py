# -*- coding: utf-8 -*-
"""多源搜索工具（教程 7.5.3）：Tavily/SerpApi 智能选择与降级。"""
import os
from typing import Any, Dict, List

from hello_agents.tools.base import Tool, ToolParameter


class SearchTool(Tool):
    """智能混合搜索工具：hybrid 模式自动选择最佳搜索源，失败自动降级。"""

    def __init__(self, backend: str = "hybrid", tavily_key: str | None = None,
                 serpapi_key: str | None = None):
        super().__init__(
            name="search",
            description="一个智能网页搜索引擎。支持混合搜索模式，自动选择最佳搜索源。",
        )
        self.backend = backend
        self.tavily_key = tavily_key or os.getenv("TAVILY_API_KEY")
        self.serpapi_key = serpapi_key or os.getenv("SERPAPI_API_KEY")
        self.available_backends: list[str] = []
        self._setup_backends()

    def _setup_backends(self):
        """按可用密钥与依赖探测可用的搜索后端。"""
        if self.tavily_key:
            try:
                from tavily import TavilyClient
                self.tavily_client = TavilyClient(api_key=self.tavily_key)
                self.available_backends.append("tavily")
                print("✅ Tavily搜索源已启用")
            except ImportError:
                print("⚠️ Tavily库未安装")
        if self.serpapi_key:
            self.available_backends.append("serpapi")

    def run(self, parameters: Dict[str, Any]) -> str:
        """执行搜索：query 或 input 参数均可。"""
        query = parameters.get("query") or parameters.get("input") or ""
        if self.backend == "hybrid":
            return self._search_hybrid(query)
        if self.backend == "tavily":
            return self._search_tavily(query)
        return self._search_serpapi(query)

    def get_parameters(self) -> List[ToolParameter]:
        """工具参数：query 搜索关键词。"""
        return [ToolParameter(name="query", type="string", description="搜索关键词")]

    def _search_hybrid(self, query: str) -> str:
        """混合搜索：优先 Tavily，失败降级 SerpApi，全部不可用则提示配置。"""
        if "tavily" in self.available_backends:
            try:
                return self._search_tavily(query)
            except Exception as e:
                print(f"⚠️ Tavily搜索失败: {e}")
                if "serpapi" in self.available_backends:
                    print("🔄 切换到SerpApi搜索")
                    return self._search_serpapi(query)
        elif "serpapi" in self.available_backends:
            try:
                return self._search_serpapi(query)
            except Exception as e:
                print(f"⚠️ SerpApi搜索失败: {e}")
        return "❌ 没有可用的搜索源，请配置TAVILY_API_KEY或SERPAPI_API_KEY环境变量"

    def _search_tavily(self, query: str) -> str:
        """Tavily 搜索：AI 综合答案 + 前三条结果。"""
        response = self.tavily_client.search(
            query=query, search_depth="basic", include_answer=True, max_results=3)
        result = f"🎯 Tavily AI搜索结果:{response.get('answer', '未找到直接答案')}\n\n"
        for i, item in enumerate(response.get("results", [])[:3], 1):
            result += f"[{i}] {item.get('title', '')}\n"
            result += f"    {item.get('content', '')[:200]}...\n"
            result += f"    来源: {item.get('url', '')}\n\n"
        return result

    def _search_serpapi(self, query: str) -> str:
        """SerpApi 搜索：返回前三条有机结果摘要（需配置 SERPAPI_API_KEY）。"""
        try:
            from serpapi import SerpApiClient
        except ImportError:
            return "❌ SerpApi库未安装，请运行 pip install google-search-results"
        results = SerpApiClient({
            "engine": "google", "q": query, "api_key": self.serpapi_key,
            "gl": "cn", "hl": "zh-cn",
        }).get_dict()
        snippets = [
            f"[{i + 1}] {res.get('title', '')}\n{res.get('snippet', '')}"
            for i, res in enumerate(results.get("organic_results", [])[:3])
        ]
        return "\n\n".join(snippets) if snippets else f"没有找到关于 '{query}' 的信息。"
