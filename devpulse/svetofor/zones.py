"""Раскраска: значение метрики → цвет зоны (🟢/🟡/🔴/⚪).

Пороги берутся из config/zones.json — их правит НЕтехническая команда,
код не трогая. Здесь только логика применения порогов.
"""
from __future__ import annotations
import os
import json

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONFIG_DIR = os.path.join(_ROOT, "config")

GREEN, YELLOW, RED, GREY = "green", "yellow", "red", "grey"


def _load(name: str) -> dict:
    with open(os.path.join(_CONFIG_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def load_zones() -> dict:
    return _load("zones.json")


def _metric_conf(cfg: dict, metric: str, scope: str | None) -> dict:
    base = dict(cfg["metrics"].get(metric, {}))
    # перебивка порогов по подразделению
    ov = (cfg.get("overrides_by_scope", {}) or {}).get(scope or "", {})
    if isinstance(ov, dict):
        base.update({k: v for k, v in ov.get(metric, {}).items()})
    return base


def colorize(metric: str, value, scope: str | None = None, cfg: dict | None = None) -> dict:
    """Вернуть цвет метрики по её значению. value=None → серый (нет данных)."""
    cfg = cfg or load_zones()
    conf = _metric_conf(cfg, metric, scope)
    label = conf.get("label", metric)
    if not conf or not conf.get("enabled", False):
        return {"metric": metric, "label": label, "color": GREY, "value": value,
                "reason": "метрика выключена (enabled=false)" if conf else "нет в конфиге"}
    if value is None:
        return {"metric": metric, "label": label, "color": GREY, "value": None,
                "reason": "нет данных"}

    direction = conf.get("direction", "lower_better")
    if direction == "lower_better":
        if value <= conf["green_max"]:
            c = GREEN
        elif value <= conf["yellow_max"]:
            c = YELLOW
        else:
            c = RED
        thr = f"🟢≤{conf['green_max']} 🟡≤{conf['yellow_max']}"
    else:  # higher_better
        if value >= conf["green_min"]:
            c = GREEN
        elif value >= conf["yellow_min"]:
            c = YELLOW
        else:
            c = RED
        thr = f"🟢≥{conf['green_min']} 🟡≥{conf['yellow_min']}"

    return {"metric": metric, "label": label, "color": c, "value": value,
            "reason": f"{value} при порогах {thr}", "note": conf.get("note")}
