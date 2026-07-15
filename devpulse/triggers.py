"""Проактивные детекторы (триггеры) Dev Pulse.

Из раздела «Мониторинг гигиены» Базы знаний + список триггеров методологии.
В отличие от metrics.py (число по запросу), тут — сигналы проблем: то, что бот
может подсвечивать сам. Каждый детектор возвращает список находок с ключом,
типом сигнала, severity и пояснением. Ничего не выдумывает: если данных нет —
находки нет.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import date

from . import config, jira_client as jc


@dataclass
class Finding:
    key: str
    trigger: str
    severity: str          # high | medium | low
    detail: str

    def as_dict(self):
        return asdict(self)


def _date_only(s):
    return date.fromisoformat(s[:10]) if s else None


def _labels_set(s):
    """'Copilot КУБ26Q2' -> {'Copilot','КУБ26Q2'}."""
    return set((s or "").split())


# --- финальные / рабочие статусы эпика ---
_FINAL = set(config.DONE_STATES) | {config.ST_CANCELLED}
# работа началась = статус на уровне «Постановка задачи» и дальше
_WORK_STARTED_EPIC = set(config.EPIC_ACTIVE_STATES) | {config.ST_EFFECT_CONFIRM} | set(config.DONE_STATES)


def overdue_epics(issues: list[dict]) -> list[Finding]:
    """Прогнозная дата завершения в прошлом, а статус не финальный."""
    today = date.today()
    out = []
    for it in issues:
        f = it.get("fields", {})
        st = f.get("status", {}).get("name", "")
        if st in _FINAL:
            continue
        fc = _date_only(f.get(config.FIELD_FORECAST_DATE))
        if fc and fc < today:
            days = (today - fc).days
            out.append(Finding(it.get("key"), "overdue_epic", "high",
                               f"прогнозная дата {fc.isoformat()} в прошлом на {days} дн, статус '{st}'"))
    return out


def removed_kub_label(issues: list[dict]) -> list[Finding]:
    """Снятие метки КУБ (сигнал: пытаются убрать задачу из коммита).
    Требует issues, загруженные с changelog."""
    out = []
    for it in issues:
        for h in it.get("changelog", {}).get("histories", []):
            for item in h.get("items", []):
                if item.get("field") != "labels":
                    continue
                before = _labels_set(item.get("fromString"))
                after = _labels_set(item.get("toString"))
                removed = {l for l in (before - after) if l.startswith(config.KUB_LABEL_PREFIX)}
                for lab in removed:
                    out.append(Finding(it.get("key"), "removed_kub_label", "high",
                                       f"снята метка {lab} — {h.get('created','')[:10]}"))
    return out


def _story_counts_bulk(epic_keys: list[str]) -> dict:
    """Число дочерних элементов на каждый эпик — БЕЗ N+1.
    Одним запросом на чанк тянем истории с их Epic Link и считаем в Python."""
    counts = {k: 0 for k in epic_keys}
    for i in range(0, len(epic_keys), 50):
        chunk = epic_keys[i:i + 50]
        jql = '"Epic Link" in (' + ",".join(chunk) + ")"
        start = 0
        while True:
            data = jc._get("/search", {"jql": jql, "fields": "customfield_10102",
                                       "maxResults": 100, "startAt": start})
            issues = data.get("issues", [])
            for it in issues:
                link = it.get("fields", {}).get("customfield_10102")
                if link in counts:
                    counts[link] += 1
            start += len(issues)
            if not issues or start >= data.get("total", 0):
                break
    return counts


def undecomposed_epics(issues: list[dict]) -> list[Finding]:
    """Эпик со статусом ≥ 'Постановка задачи', но с 0-1 историй (красный флаг).
    Счёт историй — bulk (без N+1)."""
    candidates = [it for it in issues
                  if it.get("fields", {}).get("status", {}).get("name", "") in _WORK_STARTED_EPIC]
    keys = [it.get("key") for it in candidates]
    if not keys:
        return []
    counts = _story_counts_bulk(keys)
    out = []
    for it in candidates:
        key = it.get("key")
        st = it.get("fields", {}).get("status", {}).get("name", "")
        n = counts.get(key, 0)
        if n <= 1:
            out.append(Finding(key, "undecomposed_epic", "medium",
                               f"статус '{st}', но историй: {n} (нужна декомпозиция)"))
    return out


def portfolio_overview(base_jql: str = "issuetype = Epic", top: int = 15) -> dict:
    """Быстрая сводка по ВСЕМ командам/проектам сразу. Фильтрация — на стороне Jira
    (JQL), группировка по проекту — в Python. 2 запроса вместо перебора тысяч эпиков.
    Для кросс-командного взгляда: где просрочки и где перегруз WIP."""
    from collections import Counter
    done = "Готово, Done, Снят"
    active = '"Постановка задачи", Реализация, Разработка, Тестирование, Внедрение'

    def by_project(jql):
        out = Counter()
        start = 0
        while True:
            data = jc._get("/search", {"jql": jql, "fields": "project",
                                       "maxResults": 100, "startAt": start})
            issues = data.get("issues", [])
            for it in issues:
                pk = it.get("fields", {}).get("project", {}).get("key", "?")
                out[pk] += 1
            start += len(issues)
            if not issues or start >= data.get("total", 0):
                break
        return out

    overdue = by_project(f'{base_jql} AND "Прогнозная дата завершения" < now() AND status not in ({done})')
    wip = by_project(f'{base_jql} AND status in ({active})')

    projects = set(overdue) | set(wip)
    rows = [{"project": p, "overdue": overdue.get(p, 0), "wip": wip.get(p, 0)} for p in projects]
    rows.sort(key=lambda r: (-r["overdue"], -r["wip"]))
    return {
        "total_overdue": sum(overdue.values()),
        "total_wip": sum(wip.values()),
        "projects_scanned": len(projects),
        "top": rows[:top],
    }


DETECTORS = {
    "overdue_epic": overdue_epics,
    "removed_kub_label": removed_kub_label,
    "undecomposed_epic": undecomposed_epics,
}


def scan(jql: str, detectors: list[str] | None = None, max_results: int = 300) -> dict:
    """Прогнать детекторы по выборке эпиков из JQL. Возвращает находки."""
    names = detectors or list(DETECTORS)
    need_changelog = "removed_kub_label" in names
    fields = f"status,summary,labels,{config.FIELD_FORECAST_DATE}"
    issues = jc.search(jql, fields=fields, max_results=max_results, expand_changelog=need_changelog)
    findings: list[Finding] = []
    for name in names:
        fn = DETECTORS.get(name)
        if fn:
            findings.extend(fn(issues))
    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda x: order.get(x.severity, 9))
    return {
        "jql": jql,
        "scanned": len(issues),
        "findings_count": len(findings),
        "findings": [x.as_dict() for x in findings],
    }
