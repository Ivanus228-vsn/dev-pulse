"""Тонкий клиент Jira REST v2 на stdlib (без зависимостей).

Только чтение. Токен берётся из env JIRA_TOKEN (личный PAT, Bearer).
Отдаёт сырьё: issue с changelog и поиск по JQL. Никакой бизнес-логики —
расчёты живут в metrics.py.
"""
from __future__ import annotations
import os
import json
import urllib.parse
import urllib.request

from . import config


class JiraError(RuntimeError):
    pass


def _token() -> str:
    tok = os.environ.get("JIRA_TOKEN")
    if not tok:
        raise JiraError("JIRA_TOKEN не задан в окружении (source .env)")
    return tok


def _get(path: str, params: dict | None = None, timeout: int = 30) -> dict:
    url = config.JIRA_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + _token(),
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise JiraError(f"HTTP {e.code} на {path}: {e.read()[:200]!r}") from e


_AGILE_BASE = config.JIRA_BASE.replace("/rest/api/2", "/rest/agile/1.0")


def agile_get(path: str, params: dict | None = None, timeout: int = 30) -> dict:
    """Запрос к Jira Agile API (доски, спринты). Команда = имя доски."""
    url = _AGILE_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + _token(), "Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise JiraError(f"HTTP {e.code} на agile {path}") from e


def all_projects() -> list[dict]:
    """Все проекты Jira (key, name)."""
    return _get("/project")


def get_issue(key: str, fields: str = "status,issuetype,summary,assignee,labels") -> dict:
    """Issue с полной историей изменений (changelog)."""
    return _get(f"/issue/{key}", {"expand": "changelog", "fields": fields})


def search(jql: str, fields: str = "status,issuetype,summary", max_results: int = 50,
           expand_changelog: bool = False) -> list[dict]:
    """Поиск по JQL с пагинацией. Возвращает список issue."""
    out: list[dict] = []
    start = 0
    params = {"jql": jql, "fields": fields, "maxResults": min(max_results, 100)}
    if expand_changelog:
        params["expand"] = "changelog"
    while True:
        params["startAt"] = start
        data = _get("/search", params)
        issues = data.get("issues", [])
        out.extend(issues)
        total = data.get("total", 0)
        start += len(issues)
        if not issues or start >= total or len(out) >= max_results:
            break
    return out[:max_results]
