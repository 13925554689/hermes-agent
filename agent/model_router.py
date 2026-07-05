# -*- coding: utf-8 -*-
"""Hermes Model Router — 按任务类型自动切换模型

在每轮对话开始时，根据用户消息内容自动分类任务类型，
从配置的模型池中选择最佳模型，然后通过 switch_model 切换。

架构:
  user_message → classify() → select() → switch_model()
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from hermes_cli.config import load_config as _load_config

logger = logging.getLogger(__name__)

# ── 任务分类规则 ──────────────────────────────────────
# 按优先级降序排列，匹配到第一个就停止
# 每个规则: (类别名, 优先级, [关键词模式列表])
CLASSIFICATION_RULES: List[Tuple[str, int, List[str]]] = [
    ("dialog", 15, [
        # 闲聊、问候、简单问答
        r"(你好|嗨|哈[喽啰]|早上好|下午好|晚上好|晚安|再见|谢谢|不客气)",
        r"\b(hello|hi|hey|thanks|thx|good.?morning|good.?night)\b",
        r"(聊天|闲聊|随便聊聊|说说话)",
        r"(怎么样|如何|是什么|为什么|什么意思|能不能|可不可以)",
        r"\b(what|why|when|where|who|can you|could you)\b",
    ]),
    ("coding", 10, [
        # 编程、代码相关 — 中文不用\b
        r"(代码|编程|开发|实现|构建|创建|debug|bug|报错|错误|异常|修复|重构|优化)",
        r"\b(error|crash|crashing|traceback|stack.?trace|exception|fix|bug.?fix|patch|hotfix)\b",
        r"(python|javascript|typescript|java|rust|golang|go语言|c\+\+|react|vue|flask|django)",
        r"\b(function|class|import|\bdef\b|\basync\b|\bawait\b)",
        r"(refactor|测试|test|单元测试|unit.?test)",
        r"(commit|push|pull.request|PR|merge|branch|git)",
        r"(API|接口|endpoint|路由|route|数据库|database|SQL|mysql|postgres)",
        r"(写个|帮我写|生成代码|代码生成|程序|脚本|skill|技能|工具|tool|插件|plugin)",
        r"(配置|设置|安装|升级|更新|改)",
        r"(前端|后端|服务器|server|部署|deploy|docker|容器)",
        r"(审查代码|code.review|代码审查)",
        r"(自主|驱动|新建|创建模块|实现功能)",
    ]),
    ("vision", 9, [
        # 图片/视觉分析
        r"(看图|图片|照片|截图|screenshot|图像|视觉|vision|识别|看看这张|图中|这张图|上面这)",
        r"(OCR|文字识别)",
        r"(桌面.*图标|图标.*桌面|快捷方式.*图标)",
    ]),
    ("analysis", 8, [
        # 数据分析、报告、系统检查
        r"(分析|analy[sz]e|审计|audit|报告|report|统计|数据|检查|扫描|诊断)",
        r"\b(doctor|diagnose|diagnostic|health.?check|websocket|troubleshoot)\b",
        r"(评估|evaluat|审查|review)",
        r"(汇总|汇总表|报表|dashboard|仪表板)",
        r"(csv|excel|表格|数据表|dataset|\.xlsx|\.csv)",
        r"(C盘|磁盘|空间|内存|清理|删除|释放)",
    ]),
    ("creative", 5, [
        # 写作、翻译、创意
        r"(写一[篇段]|写文章|写作|写作文|写报告|写总结|写邮件|写个|写一首|写诗)",
        r"(翻译|translate|中译|英译|汉译|改写|润色|润饰|简化|扩写|缩写|总结|概括)",
        r"(故事|小说|诗歌|文案|广告语)",
        r"(ASCII|艺术字|绘图|draw|sketch|design)",
        r"(信息图|infographic|可视化)",
    ]),
    ("default", 0, [
        # 兜底
        r".",
    ]),
]

# ── 分类函数 ──────────────────────────────────────────

def classify(user_message: str) -> Tuple[str, int]:
    """根据用户消息分类任务类型。

    Returns:
        (category, priority) 元组
    """
    if not user_message:
        return ("default", 0)

    text = user_message.strip()
    if not text:
        return ("default", 0)

    for category, priority, patterns in CLASSIFICATION_RULES:
        for pattern in patterns:
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    logger.debug(
                        "Model router classified as '%s' (priority %d) → pattern: %s",
                        category, priority, pattern,
                    )
                    return (category, priority)
            except re.error:
                continue

    return ("default", 0)


# ── 模型选择 ──────────────────────────────────────────

def select(category: str, pools: Dict[str, List[Dict[str, str]]]) -> Optional[Dict[str, str]]:
    """从模型池中选择最佳模型。

    优先使用精确匹配的池，然后回退到 default 池。
    """
    # 精确匹配
    if category in pools and pools[category]:
        return pools[category][0]

    # 回退到 default
    if "default" in pools and pools["default"]:
        return pools["default"][0]

    return None


# ── 路由入口 ──────────────────────────────────────────

def route(agent, user_message: str, original_user_message: str = "") -> bool:
    """执行模型路由：分类 → 选择 → 切换。

    在每轮对话开始时调用。如果路由器未启用或配置不完整，静默跳过。

    Args:
        agent: AIAgent 实例
        user_message: 用户消息（可能已被预处理）
        original_user_message: 原始用户消息（用于分类）

    Returns:
        True 如果成功切换了模型，False 如果跳过
    """
    # 检查是否启用
    _cfg = _load_config()
    enabled = _cfg.get("model_router", {}).get("enabled", False)
    if not enabled:
        return False

    # 读取模型池配置
    pools = _cfg.get("model_router", {}).get("pools", None)
    if not pools or not isinstance(pools, dict):
        logger.debug("Model router disabled: no pools configured")
        return False

    # 获取当前模型信息，用于判断是否需要切换
    current_provider = getattr(agent, "provider", "") or ""
    current_model = getattr(agent, "model", "") or ""

    # 分类
    msg = original_user_message or user_message
    category, priority = classify(msg)

    # 选择目标模型
    selected = select(category, pools)
    if not selected:
        logger.debug("Model router: no model selected for category '%s'", category)
        return False

    target_provider = selected.get("provider", "")
    target_model = selected.get("model", "")

    if not target_provider or not target_model:
        return False

    # ── smart 模式：指定类别走 MoA（Fable 5 分析 + DeepSeek 动手）──
    smart_categories = _cfg.get("model_router", {}).get("smart_categories", [])
    if category in smart_categories:
        try:
            from hermes_cli.config import cfg_set
            cfg_set("moa.active_preset", "smart")
            logger.info(
                "Model router: activated MoA smart for category '%s' (Fable 5→DeepSeek)",
                category,
            )
            return True
        except Exception as exc:
            logger.debug("Model router: MoA smart activation failed: %s", exc)
    else:
        # 非 smart 类别 → 清除 MoA，走普通模型切换
        try:
            from hermes_cli.config import cfg_set
            cfg_set("moa.active_preset", "")
        except Exception:
            pass

    # 如果当前已经是目标模型，跳过（provider可能被解析为custom，只比较model名）
    if current_model == target_model:
        logger.debug(
            "Model router: already on target model '%s', skipping switch",
            target_model,
        )
        return False

    # 执行切换
    try:
        from agent.agent_runtime_helpers import switch_model

        logger.info(
            "Model router: switching %s/%s → %s/%s (category=%s, priority=%d)",
            current_provider, current_model,
            target_provider, target_model,
            category, priority,
        )

        switch_model(
            agent,
            new_model=target_model,
            new_provider=target_provider,
            base_url=selected.get("base_url", ""),
        )
        return True
    except Exception as exc:
        logger.warning(
            "Model router: switch to %s/%s failed: %s",
            target_provider, target_model, exc,
        )
        return False


# ── 调试工具 ──────────────────────────────────────────

def test_classify(text: str) -> str:
    """测试分类结果（用于调试）。"""
    category, priority = classify(text)
    return f"{category} (priority={priority})"
