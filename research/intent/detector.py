"""
科研意图检测器

用轻量 LLM 判断用户输入是否与论文/实验/方法相关，
从而决定是否自动注入科研上下文。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

INTENT_CLASSIFICATION_PROMPT = """你是一个分类器。判断用户输入是否与学术研究相关。

相关场景包括：
- 询问某篇论文的内容、方法、结果
- 询问某个方法/模型/数据集/指标
- 询问实验配置或结果对比
- 询问研究方向、技术概念
- 询问文献推荐或论文搜索
- 请求阅读/分析论文
- 询问主动学习/半监督/目标检测等技术问题

不相关场景包括：
- 日常问候（你好、再见等）
- 闲聊
- 请求做非研究类任务（天气、新闻、计算器等）

用户输入: {user_input}

只返回 JSON：{{"is_research": true/false, "confidence": 0.0-1.0, "reason": "简短原因"}}
"""


class IntentDetector:
    """科研意图检测器"""

    def __init__(self, llm_provider: Any):
        """
        Args:
            llm_provider: 轻量 LLM provider（Qwen-Flash 等）
        """
        self.llm = llm_provider

    async def is_research_query(self, user_input: str) -> tuple[bool, float]:
        """
        判断用户输入是否与研究相关。

        Returns:
            (is_research: bool, confidence: float)
        """
        if not user_input or len(user_input.strip()) < 3:
            return False, 0.0

        # 快速关键词预检（避免每句话都调 LLM）
        quick_result = self._quick_keyword_check(user_input)
        if quick_result is not None:
            return quick_result

        # LLM 分类
        try:
            prompt = INTENT_CLASSIFICATION_PROMPT.format(user_input=user_input[:500])
            response = await self.llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=100,
            )
            content = response["choices"][0]["message"]["content"]
            result = json.loads(content)
            is_research = bool(result.get("is_research", False))
            confidence = float(result.get("confidence", 0.0))
            logger.debug(
                "Intent: is_research=%s confidence=%.2f reason=%s",
                is_research, confidence, result.get("reason", ""),
            )
            return is_research, confidence
        except Exception as e:
            logger.warning("Intent detection failed: %s", e)
            return False, 0.0

    def _quick_keyword_check(self, text: str) -> Optional[tuple[bool, float]]:
        """关键词预检——高置信度直接返回，省一次 LLM 调用"""
        t = text.lower()

        # 强信号：明确的研究关键词
        strong_signals = [
            "paper", "论文", "method", "方法", "dataset", "数据集",
            "mAP", "实验结果", "experiment", "实验",
            "arxiv", "publication", "detection", "detect",
            "semi-supervised", "active learning", "remote sensing",
            "DOTA", "DIOR", "HRSC2016", "FAIR1M",
            "YOLO", "Faster R-CNN", "ResNet", "transformer",
            "模型", "训练", "检测", "识别", "分类",
            "对比", "指标", "精度", "召回", "F1",
            "代码", "github", "开源", "checkpoint", "权重",
        ]
        # 强排除：日常问候
        strong_negatives = [
            "你好", "hello", "hi", "hey", "再见", "bye",
            "天气", "weather", "新闻", "news",
        ]

        for kw in strong_signals:
            if kw in t:
                return True, 0.9

        for kw in strong_negatives:
            if kw in t:
                return False, 0.95

        return None  # 不确定，走 LLM
