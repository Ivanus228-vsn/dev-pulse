"""Ядро вычислительного слоя: таймлайн статусных переходов из changelog Jira.

Все метрики длительности (LT, TTM, aging, cycle time) строятся поверх этого
примитива. По методологии паузы ("Приостановлен") ВКЛЮЧАЮТСЯ в длительность,
поэтому длительность = разница календарных таймстампов входов в статусы,
ничего не вычитаем.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime


def parse_dt(s: str) -> datetime:
    """Парсит Jira-таймстамп вида 2026-07-06T13:59:03.000+0300."""
    # нормализуем таймзону +0300 -> +03:00 для fromisoformat (py3.9-совместимо частично)
    s = s.strip()
    if len(s) >= 5 and (s[-5] in "+-") and s[-3] != ":":
        s = s[:-2] + ":" + s[-2:]
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        # запасной разбор без долей секунды
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")


@dataclass(frozen=True)
class Transition:
    at: datetime
    from_status: str | None
    to_status: str


class Timeline:
    """Отсортированный по времени список переходов статусов одной issue."""

    def __init__(self, transitions: list[Transition]):
        self.transitions = sorted(transitions, key=lambda t: t.at)

    @classmethod
    def from_changelog(cls, issue: dict) -> "Timeline":
        trans: list[Transition] = []
        for h in issue.get("changelog", {}).get("histories", []):
            created = h.get("created")
            if not created:
                continue
            for it in h.get("items", []):
                if it.get("field") == "status":
                    trans.append(Transition(
                        at=parse_dt(created),
                        from_status=it.get("fromString"),
                        to_status=it.get("toString"),
                    ))
        return cls(trans)

    def first_entry(self, status: str) -> datetime | None:
        for t in self.transitions:
            if t.to_status == status:
                return t.at
        return None

    def last_entry(self, status: str) -> datetime | None:
        for t in reversed(self.transitions):
            if t.to_status == status:
                return t.at
        return None

    def first_entry_any(self, statuses) -> datetime | None:
        """Первый вход в любой из статусов множества (напр. любые Done-строки)."""
        for t in self.transitions:
            if t.to_status in statuses:
                return t.at
        return None

    def entered_statuses(self) -> set[str]:
        return {t.to_status for t in self.transitions}
