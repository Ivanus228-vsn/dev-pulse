"""Метрики Dev Pulse. Чистые детерминированные функции поверх Timeline.

Каждая метрика возвращает не только число, но и исходные даты, которые в него
легли — чтобы результат можно было проверить (критичное правило: LLM не считает,
человек может свериться). Определения — из Базы знаний трансформации.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from . import config
from .timeline import Timeline


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _days(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 86400.0


def _status_name(issue: dict) -> str:
    return issue.get("fields", {}).get("status", {}).get("name", "")


@dataclass
class MetricResult:
    key: str                # ключ issue
    metric: str             # имя метрики
    value: float | None     # значение (дни) или None если неприменимо
    included: bool          # входит ли в агрегат (после правил исключения)
    reason: str             # пояснение (почему None / почему исключён)
    dates: dict             # исходные даты, легшие в расчёт

    def as_dict(self) -> dict:
        d = asdict(self)
        d["dates"] = {k: (v.isoformat() if isinstance(v, datetime) else v)
                      for k, v in self.dates.items()}
        return d


def lead_time(issue: dict) -> MetricResult:
    """LT истории: от входа в 'Анализ' до входа в Done. Паузы включены.
    Исключаются: статус 'Снят', LT < 1 дня."""
    key = issue.get("key", "?")
    tl = Timeline.from_changelog(issue)
    status = _status_name(issue)

    if status == config.ST_CANCELLED:
        return MetricResult(key, "lead_time", None, False, "статус 'Снят' — исключён", {})

    start = tl.first_entry(config.ST_ANALYSIS)
    end = tl.first_entry_any(config.DONE_STATES)
    dates = {"analysis_at": start, "done_at": end}

    if start is None:
        return MetricResult(key, "lead_time", None, False, "не было входа в 'Анализ'", dates)
    if end is None:
        return MetricResult(key, "lead_time", None, False, "ещё не в Done (не завершена)", dates)

    val = _days(start, end)
    if val < config.LT_MIN_DAYS:
        return MetricResult(key, "lead_time", round(val, 2), False,
                            f"LT < {config.LT_MIN_DAYS} дн — исключён из агрегата", dates)
    return MetricResult(key, "lead_time", round(val, 2), True, "ок", dates)


def ttm(issue: dict) -> MetricResult:
    """TTM эпика: от входа в 'Постановка задачи' до входа в 'Подтверждение эффекта'.
    Паузы включены. Возврат из 'Подтверждение эффекта' → последнее вхождение.
    Исключаются: статус 'Снят', TTM < 3 дней."""
    key = issue.get("key", "?")
    tl = Timeline.from_changelog(issue)
    status = _status_name(issue)

    if status == config.ST_CANCELLED:
        return MetricResult(key, "ttm", None, False, "статус 'Снят' — исключён", {})

    start = tl.first_entry(config.ST_SETTING)
    end = tl.last_entry(config.ST_EFFECT_CONFIRM)   # последнее вхождение
    dates = {"setting_at": start, "effect_confirm_at": end}

    if start is None:
        return MetricResult(key, "ttm", None, False, "не было входа в 'Постановка задачи'", dates)
    if end is None:
        return MetricResult(key, "ttm", None, False, "ещё не в 'Подтверждение эффекта'", dates)

    val = _days(start, end)
    if val < config.TTM_MIN_DAYS:
        return MetricResult(key, "ttm", round(val, 2), False,
                            f"TTM < {config.TTM_MIN_DAYS} дн — исключён из агрегата", dates)
    return MetricResult(key, "ttm", round(val, 2), True, "ок", dates)


def epic_aging(issue: dict) -> MetricResult:
    """Возраст незавершённого эпика: от 'Постановка задачи' до сейчас."""
    key = issue.get("key", "?")
    tl = Timeline.from_changelog(issue)
    status = _status_name(issue)
    start = tl.first_entry(config.ST_SETTING)
    dates = {"setting_at": start, "as_of": _now()}
    if start is None:
        return MetricResult(key, "epic_aging", None, False, "не входил в 'Постановка задачи'", dates)
    if status in config.DONE_STATES or status == config.ST_CANCELLED:
        return MetricResult(key, "epic_aging", None, False, f"уже финальный ('{status}')", dates)
    return MetricResult(key, "epic_aging", round(_days(start, _now()), 2), True, "ок", dates)


def cycle_time_by_stage(issue: dict) -> dict:
    """Сколько времени (дней) эпик/история провёл в каждом статусе.
    Строится из timeline: интервалы между последовательными переходами.
    Начальный статус учитывается от даты создания (если поле created есть),
    текущий (незакрытый) статус — до 'сейчас'."""
    from .timeline import Timeline, parse_dt
    key = issue.get("key", "?")
    f = issue.get("fields", {})
    tl = Timeline.from_changelog(issue)
    trans = tl.transitions

    # точки времени со статусом, который держался ПОСЛЕ этой точки
    points = []  # (datetime, status_that_starts_here)
    created = f.get("created")
    if trans:
        initial = trans[0].from_status
        if created and initial:
            points.append((parse_dt(created), initial))
        for t in trans:
            points.append((t.at, t.to_status))
    else:
        # переходов нет — весь срок в текущем статусе от создания
        if created:
            points.append((parse_dt(created), _status_name(issue)))

    stages: dict[str, float] = {}
    for i, (t0, st) in enumerate(points):
        t1 = points[i + 1][0] if i + 1 < len(points) else _now()
        # приводим к aware при необходимости
        try:
            dur = _days(t0, t1)
        except TypeError:
            continue
        if dur > 0 and st:
            stages[st] = round(stages.get(st, 0.0) + dur, 2)

    current = _status_name(issue)
    ongoing = current not in config.DONE_STATES and current != config.ST_CANCELLED
    return {"key": key, "current_status": current, "ongoing": ongoing, "stages_days": stages}


def wip_epics(issues: list[dict]) -> dict:
    """WIP эпиков: сколько сейчас в активных статусах (Постановка задачи, Реализация/
    Разработка, Тестирование, Внедрение). Точечный счёт по текущему статусу."""
    active = []
    from collections import Counter
    by_status = Counter()
    for it in issues:
        st = _status_name(it)
        if st in config.EPIC_ACTIVE_STATES:
            active.append(it.get("key"))
            by_status[st] += 1
    return {
        "wip": len(active),
        "by_status": dict(by_status),
        "keys": active,
        "active_statuses": sorted(config.EPIC_ACTIVE_STATES),
    }


def throughput(issues: list[dict], quarter: str | None = None) -> dict:
    """Throughput/Velocity: сколько эпиков завершено. Если задан quarter — только
    закрытые с датой закрытия внутри квартала; иначе — все закрытые (Done)."""
    window = None
    if quarter:
        window = config.quarter_bounds(quarter)
    done_total = 0
    done_in_window = 0
    keys = []
    for it in issues:
        st = _status_name(it)
        if st not in config.DONE_STATES:
            continue
        done_total += 1
        resolved = _date_only(it.get("fields", {}).get("resolutiondate"))
        if window and resolved and window[0] <= resolved <= window[1]:
            done_in_window += 1
            keys.append(it.get("key"))
        elif not window:
            keys.append(it.get("key"))
    out = {"done_total": done_total, "keys": keys}
    if window:
        out["quarter"] = quarter
        out["quarter_window"] = [window[0].isoformat(), window[1].isoformat()]
        out["done_in_quarter"] = done_in_window
    return out


def _date_only(s):
    """'2026-07-08T10:42:...' или '2026-06-30' -> date | None."""
    if not s:
        return None
    from datetime import date
    return date.fromisoformat(s[:10])


def predictability(issues: list[dict], quarter: str) -> dict:
    """Предсказуемость квартальных планов для набора эпиков.

    ВНИМАНИЕ: определение неоднозначно и НЕ сверено с эталоном (дашбордом/Димой).
    Поэтому считаем прозрачно и отдаём ОБЕ трактовки + полную разбивку.

    Знаменатель — эпики, «заявленные на КУБе с датой завершения внутри квартала»:
      den_label    — все с меткой КУБ<quarter>;
      den_forecast — из них с прогнозной датой (customfield) внутри квартала.
    Числитель — «сделанные в квартале»:
      num_done_total — завершены вообще (финальный статус), из знаменателя;
      num_done_in_q  — завершены С ДАТОЙ закрытия внутри квартала.
    Ставит 4 варианта отношения; какой «правильный» — решается методологией.
    """
    q_start, q_end = config.quarter_bounds(quarter)
    kub = config.KUB_LABEL_PREFIX + quarter

    committed = [it for it in issues if kub in (it.get("fields", {}).get("labels") or [])]

    breakdown = []
    den_forecast = 0
    num_done_total = 0
    num_done_in_q = 0
    num_done_total_fc = 0   # завершён вообще И прогноз в квартале
    num_done_in_q_fc = 0    # завершён в квартале И прогноз в квартале
    for it in committed:
        f = it.get("fields", {})
        st = f.get("status", {}).get("name", "")
        resolved = _date_only(f.get("resolutiondate"))
        forecast = _date_only(f.get(config.FIELD_FORECAST_DATE))
        is_done = st in config.DONE_STATES
        forecast_in_q = bool(forecast and q_start <= forecast <= q_end)
        done_in_q = bool(is_done and resolved and q_start <= resolved <= q_end)
        if forecast_in_q:
            den_forecast += 1
        if is_done:
            num_done_total += 1
            if forecast_in_q:
                num_done_total_fc += 1
        if done_in_q:
            num_done_in_q += 1
            if forecast_in_q:
                num_done_in_q_fc += 1
        breakdown.append({
            "key": it.get("key"), "status": st,
            "forecast": forecast.isoformat() if forecast else None,
            "resolved": resolved.isoformat() if resolved else None,
            "forecast_in_quarter": forecast_in_q, "done_in_quarter": done_in_q,
        })

    den_label = len(committed)

    def ratio(n, d):
        return round(n / d, 4) if d else None

    variants = {
        "done_total / label": {"num": num_done_total, "den": den_label,
                               "ratio": ratio(num_done_total, den_label)},
        "done_in_quarter / label": {"num": num_done_in_q, "den": den_label,
                                    "ratio": ratio(num_done_in_q, den_label)},
        "done_total / forecast_in_quarter": {"num": num_done_total_fc, "den": den_forecast,
                                             "ratio": ratio(num_done_total_fc, den_forecast)},
        "done_in_quarter / forecast_in_quarter": {"num": num_done_in_q_fc, "den": den_forecast,
                                                  "ratio": ratio(num_done_in_q_fc, den_forecast)},
    }
    return {
        "quarter": quarter, "kub_label": kub,
        "quarter_window": [q_start.isoformat(), q_end.isoformat()],
        "committed_by_label": den_label,
        "committed_with_forecast_in_quarter": den_forecast,
        "variants": variants,
        "breakdown": breakdown,
        "note": "определение НЕ сверено с эталоном; варианты даны для выбора методологии",
    }


def aggregate(results: list[MetricResult]) -> dict:
    """Среднее по метрике только среди included=True."""
    vals = [r.value for r in results if r.included and r.value is not None]
    return {
        "n_total": len(results),
        "n_included": len(vals),
        "avg_days": round(sum(vals) / len(vals), 2) if vals else None,
        "min_days": min(vals) if vals else None,
        "max_days": max(vals) if vals else None,
    }
