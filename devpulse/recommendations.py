"""Библиотека рекомендаций Dev Pulse — «сигнал → конкретный совет».

Ключевая ценность продукта по итогам встречи: бот даёт не «что не так»,
а «что делать». Рекомендации ДЕТЕРМИНИРОВАННЫ и привязаны к реальным данным
команды (в отличие от общего чек-листа, который LLM выдаёт из головы).

Правило = условие на фактах + шаблон совета. Легко расширять (зона Паши):
добавляй правило в RULES. LLM затем формулирует по-человечески, но не выдумывает.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict

from . import sprints as sp


@dataclass
class Advice:
    signal: str        # что зафиксировано (по данным)
    advice: str        # что делать (практика)
    severity: str      # high | medium | low

    def as_dict(self):
        return asdict(self)


# --- правила по статусу спринта команды ---
def _rules_sprint(s: dict) -> list[Advice]:
    out = []
    if not s.get("found"):
        return out
    p = s.get("progress") or {}
    elapsed = p.get("pct_elapsed", 0)
    done = s.get("pct_done", 0)
    total, done_n, not_started = s.get("total", 0), s.get("done", 0), s.get("not_started", 0)

    # 1) перегруз / velocity-планирование
    if elapsed >= 60 and done < 60 and total:
        out.append(Advice(
            signal=f"спринт пройден на {elapsed}%, закрыто лишь {done}% ({done_n}/{total})",
            advice="Похоже, спринт перегружен. На следующий планируйте по velocity — "
                   "берите не больше, чем команда реально закрывает. Лучше меньше, но доводить до конца.",
            severity="high"))

    # 2) не начатые истории под конец спринта
    if not_started and elapsed >= 50:
        out.append(Advice(
            signal=f"{not_started} историй ещё не начаты, а спринт пройден на {elapsed}%",
            advice="Эти истории не доедут до конца спринта. Уберите их из спринта или разберитесь, "
                   "что мешает старту (блокер, зависимость, неясные требования).",
            severity="medium"))

    # 3) много под риском
    if s.get("at_risk_count", 0) and total and s["at_risk_count"] >= max(3, total // 3):
        out.append(Advice(
            signal=f"{s['at_risk_count']} элементов под риском не закрыться к концу спринта",
            advice="Сфокусируйте команду на доведении начатого (WIP-лимит), а не на старте нового. "
                   "Проверьте, нет ли историй, застрявших в одной стадии.",
            severity="high"))

    # 4) дефекты
    if s.get("defects", 0) >= 3:
        out.append(Advice(
            signal=f"{s['defects']} дефектов в спринте",
            advice="Выделите время на стабилизацию: пока дефекты копятся, velocity ложная, "
                   "а часть работы уйдёт в переделку.",
            severity="medium"))

    # 5) хорошая гигиена — тоже сигнал (положительная мотивация)
    if elapsed >= 60 and done >= 80:
        out.append(Advice(
            signal=f"закрыто {done}% при {elapsed}% времени — команда идёт с опережением",
            advice="Хороший темп. Зафиксируйте, что сработало, и вытащите практику в пример для других команд.",
            severity="low"))
    return out


def compose_digest(project: str, team: str) -> str:
    """Готовое утреннее сообщение тимлиду (чистый текст, без LLM).
    Используется и MCP-инструментом, и планировщиком digest_bot."""
    s = sp.team_sprint_status(project, team)
    if not s.get("found"):
        teams = sp.list_active_teams(project)
        return (f"Команда «{team}» ({project}): активный спринт не найден. "
                f"Команды проекта: {', '.join(teams) or 'нет'}")
    p = s.get("progress") or {}
    lines = [f"☀️ Доброе утро! Команда {team}, спринт «{s['sprint']}»"]
    if p:
        lines.append(f"День {p['day']}/{p['of']} ({p['pct_elapsed']}%) · "
                     f"закрыто {s['done']}/{s['total']} ({s['pct_done']}%) · "
                     f"в работе {s['active']} · дефектов {s['defects']}")
    r = recommend_for_team(project, team)
    if r["recommendations"]:
        lines.append("\nЧто стоит сделать:")
        for a in r["recommendations"][:3]:
            lines.append(f"• {a['advice']}")
    else:
        lines.append("\nОстрых сигналов нет — так держать 👍")
    if s.get("at_risk_count"):
        lines.append(f"\n⚠️ Под риском не закрыться: {s['at_risk_count']} (примеры):")
        for x in s["at_risk"][:5]:
            lines.append(f"  {x}")
    return "\n".join(lines)


def recommend_for_team(project: str, team: str) -> dict:
    """Собирает факты по команде и выдаёт привязанные к данным рекомендации."""
    s = sp.team_sprint_status(project, team)
    advices = _rules_sprint(s)
    order = {"high": 0, "medium": 1, "low": 2}
    advices.sort(key=lambda a: order.get(a.severity, 9))
    return {
        "project": project, "team": team,
        "sprint": s.get("sprint"),
        "based_on": {"total": s.get("total"), "done_pct": s.get("pct_done"),
                     "elapsed_pct": (s.get("progress") or {}).get("pct_elapsed"),
                     "at_risk": s.get("at_risk_count"), "defects": s.get("defects")},
        "recommendations": [a.as_dict() for a in advices],
        "note": "рекомендации привязаны к данным спринта; если правил не сработало — острых сигналов нет",
    }
