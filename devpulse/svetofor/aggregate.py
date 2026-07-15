"""Свод цветов нескольких метрик в один цвет светофора подразделения.

Правило берётся из config/aggregation.json.
"""
from __future__ import annotations
import os
import json

from .zones import GREEN, YELLOW, RED, GREY

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONFIG_DIR = os.path.join(_ROOT, "config")

_ORDER = {GREEN: 0, YELLOW: 1, RED: 2}


def load_aggregation() -> dict:
    with open(os.path.join(_CONFIG_DIR, "aggregation.json"), encoding="utf-8") as f:
        return json.load(f)


def overall(colored: list[dict], cfg: dict | None = None) -> dict:
    """colored — список результатов colorize(). Возвращает общий цвет + пояснение."""
    cfg = cfg or load_aggregation()
    grey_policy = cfg.get("grey_policy", "ignore")

    greys = [c for c in colored if c["color"] == GREY]
    if grey_policy == "strict" and greys:
        return {"color": GREY, "reason": "есть метрики без данных (grey_policy=strict)"}

    active = [c for c in colored if c["color"] != GREY]
    if not active:
        return {"color": GREY, "reason": "нет метрик с данными"}

    rule = cfg.get("rule", "worst")
    if rule == "worst":
        worst = max(active, key=lambda c: _ORDER.get(c["color"], 0))
        return {"color": worst["color"],
                "reason": f"по худшей метрике: {worst['label']} ({worst['color']})",
                "driver": worst["metric"]}
    # weighted и прочее — задел на будущее; пока фолбэк на worst
    worst = max(active, key=lambda c: _ORDER.get(c["color"], 0))
    return {"color": worst["color"], "reason": f"правило '{rule}' не реализовано, взято worst"}
