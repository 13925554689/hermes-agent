"""
Model Router — task-aware automatic model selection for Hermes Agent.

Analyzes the user's task and routes it to the best model from a
configurable pool. Supports rule-based (fast, free) and LLM-based
(more accurate but costs one cheap API call) classification.

Architecture:
  User message → classify task → pick best model from pool → switch if needed

Config (config.yaml):
  model_router:
    enabled: true
    mode: "rule"          # "rule" (fast/free) or "llm" (accurate)
    router_provider: "zai"
    router_model: "glm-5.2"
    pools:
      coding:
        - {provider: "aifast", model: "claude-opus-4-8"}
      analysis:
        - {provider: "aifast", model: "gpt-5.5"}
      dialog:
        - {provider: "zai", model: "glm-5.2"}
      default:
        - {provider: "zai", model: "glm-5.2"}
    cost_optimize: true
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Task categories ──────────────────────────────────────────────────

@dataclass
class TaskCategory:
    """A task category with keyword patterns for rule-based matching."""
    name: str
    description: str
    keywords: List[str] = field(default_factory=list)
    patterns: List[re.Pattern] = field(default_factory=list)
    priority: int = 0  # Higher = checked first

    def __post_init__(self):
        self._compiled = [re.compile(kw, re.IGNORECASE) for kw in self.keywords]
        self._compiled.extend(self.patterns)


# ── Built-in task categories ─────────────────────────────────────────

TASK_CATEGORIES: List[TaskCategory] = [
    TaskCategory(
        name="dialog",
        description="日常对话、问答、帮助",
        keywords=[
            # Simple questions — highest priority, catch before specialized categories
            r"^(what|who|where|when|why|how|which|whose|whom)\b",
            r"^(你?|请?)(什么是|怎么|如何|为什么|是什么|是谁|哪里|哪个|什么时候)",
            r"你好|早上好|下午好|晚上好|再见|谢谢|哈哈|嗯|哦|好的|ok|OK",
            r"介绍一下|解释|说明",
            r"帮助|help|指南|教程|tutorial",
            r"有什么|有哪些|推荐.*(书|电影|音乐|工具|软件)|给.*建议|提.*建议",
            r"\bwhat\b.*\b(is|are|does|do)\b",
            r"\bhow\b.*\b(to|do|does|can|should)\b",
            r"\bwho\b|\bwhere\b|\bwhen\b|\bwhy\b|\bwhich\b",
            r"\bhelp\b|\bexplain\b|\btell\b.*\b(me|about)\b",
            r"你叫什么|你是谁|你能做什么|你会什么",
        ],
        priority=15,
    ),
    TaskCategory(
        name="coding",
        description="代码编写、调试、审查、架构设计、重构",
        keywords=[
            # Chinese
            r"写.*代码|代码.*写|编写|编程|实现.*功能|开发",
            r"修.*bug|bug.*修|修复|调试|debug|报错|错误|异常|出错",
            r"代码审查|review|审查.*代码",
            r"重构|refactor|优化.*代码|代码.*优化",
            r"架构|设计模式|design pattern",
            r"\b(接口|API|路由|route|endpoint|REST|GraphQL)\b",
            r"数据库|database|\bSQL\b|\bsql\b|查询|\bquery\b",
            r"前端|frontend|后端|backend|全栈|fullstack",
            r"性能|performance|优化|并发",
            # English — use word boundaries to avoid false positives
            r"\bcode\b|\bfunction\b|\bclass\b|\bmodule\b|\bimport\b",
            r"\bimplement\b|\bbuild\b\s+\b(app|tool|cli|server|api)\b",
            r"\bfix\b|\bdebug\b|\bpatch\b|\brefactor\b|\boptimize\b",
            r"\b(typescript|javascript|python|rust|golang)\b",
            r"\bCLI\b|\bcommand.line\b|\bterminal\b",
            r"\bgit\b|\bcommit\b|\bpush\b|\bmerge\b|\bPR\b|\bpull.request\b",
            r"\bDocker\b|\bcontainer\b|\bdeploy\b|\bCI\b|\bCD\b",
                   r"测试|单元测试|\btest(s|ing)?\b|\bpytest\b|\bunit.test\b",
        ],
        priority=10,
    ),
    TaskCategory(
        name="vision",
        description="图片/视频分析、OCR",
        keywords=[
            r"图片|图像|照片|看图|截图|图片.*分析",
            r"识别|OCR|文字.*识别|提取.*文字",
            r"视频|video|录像",
            r"\bimage\b|\bpicture\b|\bphoto\b|\bscreenshot\b",
            r"\bvision\b|\bocr\b|\bvisual\b",
        ],
        priority=9,
    ),
    TaskCategory(
        name="analysis",
        description="数据分析、研究、深度推理、报告",
        keywords=[
            # Chinese
            r"分析|数据|统计|报表|报告|研究|调研",
            r"对比|比较|评估|审计|审查|检查",
            r"总结|摘要|概括|归纳",
            r"计算|推算|预测|预估",
            r"财务|会计|账目|凭证",
            r"指标|KPI|比率|占比|百分比",
            r"趋势|走向|变化|波动",
            # English
            r"\banaly(sis|ze)\b|\bdata\b.*\b(analysis|science)\b",
            r"\bresearch\b|\binvestigate\b|\bevaluate\b",
            r"\bsummarize\b|\bsummary\b|\breport\b",
            r"\bcalculate\b|\bcompute\b|\bestimate\b",
            r"\bcompare\b|\bversus\b|\bvs\b.*\b(compare|difference)\b",
        ],
        priority=8,
    ),
    TaskCategory(
        name="creative",
        description="创意写作、内容生成、设计",
        keywords=[
            r"写.*文章|文章.*写|创作|写作|文案",
            r"生成.*内容|内容.*生成|设计|美化",
            r"翻译|translate|本地化|localize",
            r"文档|documentation|readme|说明",
            r"\bwrite\b.*\b(blog|article|post|story|essay)\b",
            r"\bcreate\b.*\b(content|design|image)\b",
            r"\btranslate\b|\blocalize\b",
        ],
        priority=5,
    ),
]

# ── Model pool entry ──────────────────────────────────────────────────

@dataclass
class ModelPoolEntry:
    """A model in a routing pool."""
    provider: str
    model: str
    base_url: str = ""
    api_key: str = ""
    cost_tier: int = 1  # 1=cheapest, 5=most expensive

    def to_dict(self) -> Dict[str, str]:
        d = {"provider": self.provider, "model": self.model}
        if self.base_url:
            d["base_url"] = self.base_url
        if self.api_key:
            d["api_key"] = self.api_key
        return d


# Default cost tiers (lower = cheaper)
_COST_TIERS: Dict[str, int] = {
    "zai": 1,          # 智谱 GLM (cheap)
    "deepseek": 1,     # DeepSeek (cheap/free)
    "aifast": 3,       # AIFast (mid,中转)
    "openrouter": 3,   # OpenRouter (mid)
    "anthropic": 5,    # Anthropic direct (expensive)
    "openai": 5,       # OpenAI direct (expensive)
}


def _estimate_cost_tier(provider: str) -> int:
    """Estimate cost tier for a provider."""
    return _COST_TIERS.get(provider.lower(), 3)


# ── Model Router ──────────────────────────────────────────────────────

class ModelRouter:
    """Task-aware model selector.

    Usage:
        router = ModelRouter(config)
        category = router.classify("写一个Python脚本来分析数据")
        model = router.select(category)  # → {"provider": "aifast", "model": "gpt-5.5"}
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize router from config dict.

        Args:
            config: The 'model_router' section of config.yaml, or None for defaults.
        """
        self._config = config or {}
        self.enabled = self._config.get("enabled", False)
        self.mode = self._config.get("mode", "rule")  # "rule" or "llm"
        self.cost_optimize = self._config.get("cost_optimize", True)
        self.router_provider = self._config.get("router_provider", "")
        self.router_model = self._config.get("router_model", "")

        # Parse pools
        self._pools: Dict[str, List[ModelPoolEntry]] = {}
        raw_pools = self._config.get("pools", {})
        if isinstance(raw_pools, dict):
            for cat_name, entries in raw_pools.items():
                pool = []
                if isinstance(entries, list):
                    for entry in entries:
                        if isinstance(entry, dict):
                            provider = str(entry.get("provider", "")).strip()
                            model = str(entry.get("model", "")).strip()
                            if provider and model:
                                pool.append(ModelPoolEntry(
                                    provider=provider,
                                    model=model,
                                    base_url=str(entry.get("base_url", "")).strip(),
                                    api_key=str(entry.get("api_key", "")).strip(),
                                    cost_tier=_estimate_cost_tier(provider),
                                ))
                if pool:
                    self._pools[cat_name] = pool

        # Ensure default pool exists
        if "default" not in self._pools:
            self._pools["default"] = []

        # Copy and sort categories by priority (higher first)
        self._categories = list(TASK_CATEGORIES)
        self._categories.sort(key=lambda c: c.priority, reverse=True)

    @property
    def has_pools(self) -> bool:
        """Whether any model pools are configured."""
        return any(len(pool) > 0 for pool in self._pools.values())

    def classify(self, message: str) -> str:
        """Classify a user message into a task category.

        Args:
            message: The user's message text.

        Returns:
            Category name (e.g. "coding", "analysis", "dialog", "default").
        """
        if not message or not message.strip():
            return "default"

        # Try each category in priority order
        for cat in self._categories:
            for pattern in cat._compiled:
                if pattern.search(message):
                    logger.debug(f"ModelRouter: classified as '{cat.name}' via pattern: {pattern.pattern[:60]}")
                    return cat.name

        return "default"

    def select(self, category: str) -> Optional[Dict[str, str]]:
        """Select the best model for a task category.

        Args:
            category: Task category name.

        Returns:
            {"provider": "...", "model": "..."} or None if no model available.
        """
        pool = self._pools.get(category, self._pools.get("default", []))

        if not pool:
            pool = self._pools.get("default", [])
        if not pool:
            return None

        if self.cost_optimize and len(pool) > 1:
            sorted_pool = sorted(pool, key=lambda e: e.cost_tier)
        else:
            sorted_pool = pool

        entry = sorted_pool[0]
        result = {"provider": entry.provider, "model": entry.model}
        if entry.base_url:
            result["base_url"] = entry.base_url
        if entry.api_key:
            result["api_key"] = entry.api_key

        logger.info(
            f"ModelRouter: task='{category}' → {entry.provider}/{entry.model}"
            + (f" (cost_tier={entry.cost_tier})" if self.cost_optimize else "")
        )
        return result

    def route(self, message: str) -> Optional[Dict[str, str]]:
        """Full routing pipeline: classify → select.

        Args:
            message: The user's message text.

        Returns:
            Selected model dict, or None if routing is disabled or no model found.
        """
        if not self.enabled or not self.has_pools:
            return None

        category = self.classify(message)
        return self.select(category)

    def get_pool_for_category(self, category: str) -> List[Dict[str, str]]:
        """Get all models in a category's pool as dicts."""
        pool = self._pools.get(category, self._pools.get("default", []))
        return [e.to_dict() for e in pool]

    def get_all_categories(self) -> List[str]:
        """Get all configured category names."""
        return list(self._pools.keys())


# ── Convenience: build router from full config ────────────────────────

def build_router(config: Optional[Dict[str, Any]] = None) -> ModelRouter:
    """Build a ModelRouter from a full Hermes config dict.

    Args:
        config: Full config.yaml dict (not just model_router section).

    Returns:
        Configured ModelRouter.
    """
    router_config = (config or {}).get("model_router", {})
    return ModelRouter(router_config)


def route_message(message: str, config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, str]]:
    """One-shot: route a message through the model router.

    Args:
        message: User message to classify.
        config: Full config.yaml dict.

    Returns:
        Selected model dict or None.
    """
    router = build_router(config)
    return router.route(message)
