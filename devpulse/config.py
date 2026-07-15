"""Константы методологии Dev Pulse.

Имена статусов — как они приходят из Jira (русские toString в changelog).
Собраны из Базы знаний трансформации; проверяются на живых данных и правятся
здесь, если реальные строки статусов отличаются. Пороги (21/14) официально
НЕ подтверждены — см. THRESHOLDS.
"""

JIRA_BASE = "https://jira.corp.tander.ru/rest/api/2"

# --- Статусы (входные строки из Jira) ---
# История
ST_REGISTERED = "Зарегистрирован"
ST_ANALYSIS = "Анализ"
ST_DEV = "Разработка"
ST_TEST = "Тестирование"
ST_ROLLOUT = "Внедрение"
# Финальные / служебные
ST_CANCELLED = "Снят"
ST_PAUSED = "Приостановлен"

# Эпик
ST_ASSESS = "Оценка БЦ"
ST_SETTING = "Постановка задачи"
ST_EFFECT_CONFIRM = "Подтверждение эффекта"

# Множество строк, означающих "Готово/Done" (уточняется по живым данным).
DONE_STATES = {"Готово", "Done", "Закрыт", "Закрыто"}

# Активные статусы эпика (для WIP).
EPIC_ACTIVE_STATES = {ST_SETTING, "Реализация", ST_DEV, ST_TEST, ST_ROLLOUT}

# --- Правила исключения из расчёта метрик ---
LT_MIN_DAYS = 1     # истории с LT < 1 дня не учитываются
TTM_MIN_DAYS = 3    # эпики с TTM < 3 дней не учитываются

# --- Ориентировочные пороги (НЕ подтверждены официально) ---
THRESHOLDS = {
    "lead_time_norm_days": 21,      # ориентир, не подтверждён
    "lead_time_target_days": 14,    # цель = 1 спринт, не подтверждён
}

# --- Поля и метки для Predictability ---
FIELD_FORECAST_DATE = "customfield_20411"   # "Прогнозная дата завершения"
KUB_LABEL_PREFIX = "КУБ"                      # метка коммита: КУБ26Q2 и т.п.

# Границы кварталов (календарные). Добавлять по мере надобности.
QUARTER_BOUNDS = {
    "25Q4": ("2025-10-01", "2025-12-31"),
    "26Q1": ("2026-01-01", "2026-03-31"),
    "26Q2": ("2026-04-01", "2026-06-30"),
    "26Q3": ("2026-07-01", "2026-09-30"),
    "26Q4": ("2026-10-01", "2026-12-31"),
}


def quarter_bounds(quarter: str):
    """'26Q2' -> (date(2026,4,1), date(2026,6,30))."""
    from datetime import date
    if quarter not in QUARTER_BOUNDS:
        raise KeyError(f"неизвестный квартал {quarter}; добавь в QUARTER_BOUNDS")
    s, e = QUARTER_BOUNDS[quarter]
    return date.fromisoformat(s), date.fromisoformat(e)
