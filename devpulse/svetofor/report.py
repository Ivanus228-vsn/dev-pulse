"""Сборка светофора подразделения: тянет реальные метрики из готовых модулей,
красит по порогам (zones), сводит в один цвет (aggregate).

Уровни (scope): пока стрим = проект Jira. Уровень команды — следующий шаг
(«провалиться на команду»), там метрики берутся из sprints.py.
"""
from __future__ import annotations
from datetime import date

from .. import jira_client as jc, metrics as m, sprints as sprints_mod
from . import zones as Z
from . import aggregate as A
from . import placeholders as P

# какую трактовку predictability берём — по ключу из конфига
_PRED_VARIANTS = {
    "done_total_over_label": "done_total / label",
    "done_in_quarter_over_label": "done_in_quarter / label",
    "done_total_over_forecast": "done_total / forecast_in_quarter",
    "done_in_quarter_over_forecast": "done_in_quarter / forecast_in_quarter",
}


def _current_quarter() -> str:
    d = date.today()
    return f"{d.year % 100}Q{(d.month - 1) // 3 + 1}"


def _avg_metric(jql: str, fn) -> float | None:
    vals = []
    for it in jc.search(jql, fields="status", max_results=150, expand_changelog=True):
        r = fn(it)
        if r.included and r.value is not None:
            vals.append(r.value)
    return round(sum(vals) / len(vals), 1) if vals else None


def _predictability_value(project: str, quarter: str, interpretation: str) -> float | None:
    epics = jc.search(f'project={project} AND issuetype=Epic',
                      fields="status,labels,resolutiondate,customfield_20411", max_results=300)
    try:
        r = m.predictability(epics, quarter)
    except Exception:
        return None
    key = _PRED_VARIANTS.get(interpretation, "done_total / label")
    ratio = r["variants"].get(key, {}).get("ratio")
    return round(ratio * 100, 1) if ratio is not None else None


def svetofor_stream(project: str, quarter: str | None = None) -> dict:
    """Светофор одного стрима (проекта Jira)."""
    quarter = quarter or _current_quarter()
    cfg = Z.load_zones()
    pred_interp = cfg["metrics"].get("predictability", {}).get("interpretation", "done_total_over_label")

    # реальные значения метрик
    values = {
        "lead_time": _avg_metric(f'project={project} AND issuetype="История"', m.lead_time),
        "ttm": _avg_metric(f'project={project} AND issuetype=Epic', m.ttm),
        "predictability": _predictability_value(project, quarter, pred_interp),
        "data_quality": P.data_quality_score(project),  # заглушка → None
    }

    colored = [Z.colorize(name, val, scope=project, cfg=cfg) for name, val in values.items()]
    total = A.overall(colored)

    return {
        "scope": "stream", "project": project, "quarter": quarter,
        "color": total["color"], "reason": total["reason"],
        "metrics": colored,
    }


def svetofor_team(project: str, team: str) -> dict:
    """Светофор команды (drill-down). Цвет по темпу спринта: закрыто% / прошло%.
    Порог темпа — в config/zones.json → team_health."""
    s = sprints_mod.team_sprint_status(project, team)
    cfg = Z.load_zones().get("team_health", {})
    if not s.get("found"):
        return {"scope": "team", "project": project, "team": team,
                "found": False, "color": Z.GREY, "reason": s.get("reason", "нет активного спринта")}
    p = s.get("progress") or {}
    done, elapsed = s.get("pct_done", 0), p.get("pct_elapsed", 0)
    ratio = round(done / elapsed, 2) if elapsed else None
    if ratio is None:
        color, reason = Z.GREY, "спринт только начался"
    elif ratio >= cfg.get("green_ratio", 0.9):
        color, reason = Z.GREEN, f"идёт по плану (темп {ratio})"
    elif ratio >= cfg.get("yellow_ratio", 0.7):
        color, reason = Z.YELLOW, f"отстаёт (темп {ratio})"
    else:
        color, reason = Z.RED, f"сильно отстаёт (темп {ratio})"
    return {
        "scope": "team", "project": project, "team": team, "found": True,
        "color": color, "reason": reason,
        "sprint": s["sprint"], "day": p.get("day"), "of": p.get("of"),
        "pct_elapsed": elapsed, "pct_done": done,
        "total": s["total"], "done": s["done"], "active": s["active"],
        "at_risk": s["at_risk_count"], "defects": s["defects"],
        "at_risk_items": s["at_risk"][:6],
    }

