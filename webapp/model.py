"""Слой модели веб-сервиса: собирает богатый снимок данных из движка.

Три уровня:
  build_overview()             — лёгкий обзор всех стримов (для фонового кэша)
  build_stream_detail(project) — детально по стриму (сигналы, стадии) — по запросу
  build_team_detail(proj,team) — детально по команде (рекомендации) — по запросу

Всё считается детерминированно из готовых модулей devpulse.
"""
from __future__ import annotations
import os
import sys
import json
from datetime import date
from collections import Counter

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from devpulse import (jira_client as jc, metrics as m, triggers as tg,  # noqa: E402
                      sprints as sp, recommendations as rec, config as C)
from devpulse.svetofor import report as svetofor  # noqa: E402

CONFIG = os.path.join(_ROOT, "config", "dashboard.json")


def _cfg() -> dict:
    return json.load(open(CONFIG, encoding="utf-8"))


def _current_quarter() -> str:
    d = date.today()
    return f"{d.year % 100}Q{(d.month - 1) // 3 + 1}"


def _count(jql: str) -> int:
    try:
        return jc._get("/search", {"jql": jql, "maxResults": 0}).get("total", 0)
    except Exception:
        return 0


def _stream_extra(project: str, quarter: str) -> dict:
    """Дешёвые доп-показатели стрима через JQL-пушдаун."""
    done = "Готово, Done, Снят"
    active = '"Постановка задачи", Реализация, Разработка, Тестирование, Внедрение'
    wip = _count(f'project={project} AND issuetype=Epic AND status in ({active})')
    overdue = _count(f'project={project} AND issuetype=Epic AND '
                     f'"Прогнозная дата завершения" < now() AND status not in ({done})')
    # закрытые (доставленные) эпики — надёжно через statusCategory, исключая Снят
    thr = _count(f'project={project} AND issuetype=Epic AND statusCategory=Done AND status not in (Снят)')
    return {"wip": wip, "overdue": overdue, "closed_epics": thr}


def build_stream_row(project: str, label: str, quarter: str | None = None) -> dict:
    """Одна строка обзора: светофор стрима + доп-показатели + команды."""
    quarter = quarter or _current_quarter()
    st = svetofor.svetofor_stream(project, quarter)
    metrics_by = {c["metric"]: c for c in st["metrics"]}
    extra = _stream_extra(project, quarter)

    teams = []
    try:
        for t in sp.list_active_teams(project):
            tr = svetofor.svetofor_team(project, t)
            if tr.get("found"):
                teams.append(tr)
    except Exception:
        pass
    teams.sort(key=lambda t: {"red": 0, "yellow": 1, "green": 2, "grey": 3}.get(t["color"], 9))

    return {
        "project": project, "label": label, "quarter": quarter,
        "overall": st["color"], "reason": st["reason"],
        "metrics": metrics_by, "extra": extra,
        "teams_count": len(teams), "teams": teams,
    }


def discover_streams() -> list[dict]:
    """Лёгкий список ВСЕХ стримов (проектов с эпиками) + дешёвые счётчики.
    Быстро (только JQL-счётчики), питает боковую панель выбора."""
    labels = {s["project"]: s.get("label") for s in _cfg().get("streams", [])}
    done = "Готово, Done, Снят"
    active = '"Постановка задачи", Реализация, Разработка, Тестирование, Внедрение'
    out = []
    for p in jc.all_projects():
        proj = p["key"]
        epics = _count(f'project={proj} AND issuetype=Epic')
        if epics == 0:
            continue
        overdue = _count(f'project={proj} AND issuetype=Epic AND '
                         f'"Прогнозная дата завершения" < now() AND status not in ({done})')
        wip = _count(f'project={proj} AND issuetype=Epic AND status in ({active})')
        out.append({"project": proj, "label": labels.get(proj) or p["name"],
                    "epics": epics, "overdue": overdue, "wip": wip})
    out.sort(key=lambda s: -s["overdue"])
    return out


def build_stream_full(project: str, label: str) -> dict:
    """ПОЛНАЯ детализация одного стрима (для тяжёлого фонового кэша)."""
    q = _current_quarter()
    row = build_stream_row(project, label, q)
    try:
        row["detail"] = build_stream_detail(project)
    except Exception as e:
        row["detail"] = {"error": str(e), "signals": {"total": 0, "by_type": {}, "findings": []},
                         "stages_avg": {}, "bottleneck": None}
    for t in row.get("teams", []):
        try:
            t["recommendations"] = rec.recommend_for_team(project, t["team"]).get("recommendations", [])
        except Exception:
            t["recommendations"] = []
    return row


def build_stream_detail(project: str) -> dict:
    """Тяжёлая детализация стрима: сигналы + распределение времени по стадиям."""
    # сигналы (детекторы) — ограничиваем выборку для скорости фонового расчёта
    scan = tg.scan(f'project={project} AND issuetype=Epic', max_results=150)
    by_type = Counter(f["trigger"] for f in scan["findings"])

    # bottleneck: среднее время по стадиям среди закрытых эпиков
    epics = jc.search(f'project={project} AND issuetype=Epic AND statusCategory=Done AND status not in (Снят)',
                      fields="status,created,resolutiondate", max_results=35, expand_changelog=True)
    stage_tot = Counter()
    stage_n = 0
    for it in epics:
        r = m.cycle_time_by_stage(it)
        for stname, dd in r["stages_days"].items():
            stage_tot[stname] += dd
        stage_n += 1
    # только канонические стадии эпика (мешанина workflow-ов: игнор Backlog/In Progress и англ.)
    STAGE_DISPLAY = ["Зарегистрирован", "Оценка БЦ", "Постановка задачи", "Разработка",
                     "Реализация", "Тестирование", "Внедрение", "Подтверждение эффекта"]
    stages_avg = {k: round(stage_tot[k] / stage_n, 1) for k in STAGE_DISPLAY
                  if stage_n and stage_tot.get(k, 0) > 0}
    # узкое место — среди активных рабочих стадий (без ожидания старта и финалов)
    active = {"Постановка задачи", "Разработка", "Реализация", "Тестирование", "Внедрение"}
    work_stages = {k: v for k, v in stages_avg.items() if k in active}
    bottleneck = max(work_stages, key=work_stages.get) if work_stages else None

    return {
        "project": project,
        "signals": {"total": scan["findings_count"], "by_type": dict(by_type),
                    "findings": scan["findings"][:20]},
        "stages_avg": stages_avg, "bottleneck": bottleneck,
    }


