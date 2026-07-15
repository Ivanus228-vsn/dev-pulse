"""Спринт-уровень (Team Lead): статус текущего спринта команды.

КОМАНДА = ДОСКА (board). У каждого спринта есть rapidViewId (доска), у доски —
имя. Это 100% детерминированная команда из Jira (а не парсинг текста имени
спринта, который у каждого стрима свой). Поле спринта = customfield_10101.
"""
from __future__ import annotations
import re
from datetime import datetime
from collections import Counter

from . import config, jira_client as jc

SPRINT_FIELD = "customfield_10101"
_ACTIVE = {"Анализ", "Разработка", "Реализация", "Тестирование", "Внедрение",
           "В работе", "В ожидании тестирования", "В ожидании разработки"}
_NOT_STARTED = {"Зарегистрирован"}
_BOARD_CACHE: dict[str, str] = {}


def _parse_one(raw: str) -> dict:
    def g(k):
        m = re.search(rf"{k}=([^,\]]*)", raw)
        return m.group(1) if m else None
    return {"name": g("name"), "state": g("state"), "start": g("startDate"),
            "end": g("endDate"), "rvid": g("rapidViewId")}


def parse_active_sprint(field):
    """Из поля спринта (список строк greenhopper) берём АКТИВНЫЙ спринт."""
    if not field:
        return None
    items = field if isinstance(field, list) else [field]
    parsed = [_parse_one(x) for x in items if isinstance(x, str)]
    active = [p for p in parsed if p.get("state") == "ACTIVE"]
    return active[-1] if active else (parsed[-1] if parsed else None)


def board_name(rvid: str | None) -> str | None:
    """Имя доски по rapidViewId (с кэшем). Доска = команда."""
    if not rvid:
        return None
    if rvid in _BOARD_CACHE:
        return _BOARD_CACHE[rvid]
    try:
        name = jc.agile_get(f"/board/{rvid}").get("name")
    except Exception:
        name = None
    _BOARD_CACHE[rvid] = name
    return name


def _parse_dt(s):
    if not s or s == "<null>":
        return None
    try:
        return datetime.fromisoformat(s[:19])
    except ValueError:
        return None


def list_active_teams(project: str) -> list[str]:
    """Команды (доски) с активными спринтами в проекте — имена досок."""
    issues = jc.search(f'project = {project} AND sprint in openSprints()',
                       fields=SPRINT_FIELD, max_results=400)
    rvids = set()
    for it in issues:
        sp = parse_active_sprint(it["fields"].get(SPRINT_FIELD))
        if sp and sp.get("rvid"):
            rvids.add(sp["rvid"])
    names = [board_name(r) for r in rvids]
    return sorted({n for n in names if n})


def team_sprint_status(project: str, team: str) -> dict:
    """Статус текущего спринта команды. team = имя доски (или её id)."""
    issues = jc.search(f'project = {project} AND issuetype in (История, Дефект, Задача) '
                       f'AND sprint in openSprints()',
                       fields=f"status,issuetype,summary,assignee,{SPRINT_FIELD}", max_results=500)
    done = set(config.DONE_STATES)
    by_status = Counter()
    total = defects = done_cnt = active_cnt = not_started = cancelled = 0
    sprint = None
    items = []
    for it in issues:
        sp = parse_active_sprint(it["fields"].get(SPRINT_FIELD))
        if not sp:
            continue
        bn = board_name(sp.get("rvid"))
        if not (bn == team or sp.get("rvid") == str(team)):
            continue
        sprint = sp
        st = it["fields"]["status"]["name"]
        ty = it["fields"]["issuetype"]["name"]
        total += 1
        by_status[st] += 1
        if ty == "Дефект":
            defects += 1
        if st in done:
            done_cnt += 1
        elif st == config.ST_CANCELLED:
            cancelled += 1
        elif st in _NOT_STARTED:
            not_started += 1
        elif st in _ACTIVE:
            active_cnt += 1
        assignee = (it["fields"].get("assignee") or {}).get("displayName")
        items.append({"key": it["key"], "status": st, "type": ty,
                      "summary": it["fields"].get("summary", "")[:60], "assignee": assignee})

    if sprint is None:
        return {"found": False, "team": team, "project": project,
                "reason": "нет активного спринта у этой команды"}

    s, e = _parse_dt(sprint["start"]), _parse_dt(sprint["end"])
    progress = None
    if s and e:
        total_days = max((e - s).days, 1)
        elapsed = (datetime.now() - s).days
        progress = {"day": elapsed, "of": total_days,
                    "pct_elapsed": round(100 * elapsed / total_days),
                    "ends": e.date().isoformat()}
    considered = total - cancelled
    pct_done = round(100 * done_cnt / considered) if considered else 0
    at_risk = []
    if progress and progress["pct_elapsed"] >= 60:
        at_risk = [i for i in items if i["status"] not in done and i["status"] != config.ST_CANCELLED]

    return {
        "found": True, "project": project, "team": team,
        "sprint": sprint["name"], "state": sprint["state"], "progress": progress,
        "total": total, "done": done_cnt, "active": active_cnt,
        "not_started": not_started, "cancelled": cancelled, "defects": defects,
        "pct_done": pct_done, "by_status": dict(by_status),
        "at_risk_count": len(at_risk),
        "at_risk": [f'{i["key"]} [{i["status"]}] {i["summary"]}' for i in at_risk[:12]],
    }
