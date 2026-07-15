"""Локальный MCP-сервер Dev Pulse (stdio, чистый stdlib).

Даёт агенту детерминированные инструменты расчёта метрик, чтобы LLM НЕ считал
сам, а получал число + исходные даты из Python. Транспорт — newline-delimited
JSON-RPC 2.0 по stdin/stdout (stdio-транспорт MCP). Логи — только в stderr.

Запускается opencode как local MCP (см. opencode.json → mcp.devpulse).
JIRA_TOKEN берётся из окружения; если его нет — подхватывается из .env проекта.
"""
from __future__ import annotations
import json
import os
import sys
import traceback

# --- гарантируем, что пакет devpulse импортируется, и .env загружен ---
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_HERE)
if _PROJECT not in sys.path:
    sys.path.insert(0, _PROJECT)


def _load_dotenv():
    path = os.path.join(_PROJECT, ".env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

from devpulse import (jira_client as jc, metrics as m, config, triggers as tg,  # noqa: E402
                      sprints as sp, recommendations as rec)
from devpulse.svetofor import report as svetofor  # noqa: E402

SERVER_INFO = {"name": "devpulse", "version": "0.1.0"}
DEFAULT_PROTOCOL = "2025-06-18"


def log(*a):
    print("[devpulse-mcp]", *a, file=sys.stderr, flush=True)


# ---------- реализация инструментов ----------

def _fmt(r: m.MetricResult) -> str:
    lines = [f"{r.key} — {r.metric}: " + (f"{r.value} дн" if r.value is not None else "нет значения")]
    lines.append(f"учитывается в агрегате: {'да' if r.included else 'нет'} ({r.reason})")
    if r.dates:
        for k, v in r.dates.items():
            if v:
                vs = v.isoformat() if hasattr(v, "isoformat") else v
                lines.append(f"  {k}: {vs}")
    return "\n".join(lines)


def tool_ttm_epic(args: dict) -> str:
    key = args["key"]
    return _fmt(m.ttm(jc.get_issue(key)))


def tool_lead_time_story(args: dict) -> str:
    key = args["key"]
    return _fmt(m.lead_time(jc.get_issue(key)))


def tool_epic_aging(args: dict) -> str:
    key = args["key"]
    return _fmt(m.epic_aging(jc.get_issue(key)))


def tool_metric_by_jql(args: dict) -> str:
    jql = args["jql"]
    metric = args.get("metric", "lead_time")
    fn = {"lead_time": m.lead_time, "ttm": m.ttm, "epic_aging": m.epic_aging}[metric]
    issues = jc.search(jql, fields="status,issuetype,summary", max_results=200, expand_changelog=True)
    results = [fn(it) for it in issues]
    agg = m.aggregate(results)
    lines = [f"Метрика '{metric}' по JQL: {jql}",
             f"issue выбрано: {agg['n_total']}, в агрегате: {agg['n_included']}",
             f"среднее: {agg['avg_days']} дн (мин {agg['min_days']}, макс {agg['max_days']})",
             "",
             "детали (учтённые):"]
    for r in results:
        if r.included:
            lines.append(f"  {r.key}: {r.value} дн")
    return "\n".join(lines)


def tool_recommend_team(args: dict) -> str:
    r = rec.recommend_for_team(args["project"], args["team"])
    if not r["recommendations"]:
        return f"Команда {args['team']} ({r.get('sprint')}): острых сигналов нет, рекомендаций не требуется."
    lines = [f"Рекомендации команде {args['team']} (спринт {r.get('sprint')}, на основе данных):"]
    for a in r["recommendations"]:
        lines.append(f"[{a['severity']}] {a['signal']}\n  → {a['advice']}")
    return "\n".join(lines)


def tool_team_digest(args: dict) -> str:
    """Готовый утренний дайджест тимлиду: статус спринта + топ-рекомендации."""
    return rec.compose_digest(args["project"], args["team"])


def tool_team_sprint_status(args: dict) -> str:
    project = args["project"]
    team = args["team"]
    r = sp.team_sprint_status(project, team)
    if not r.get("found"):
        teams = sp.list_active_teams(project)
        return (f"Активный спринт команды '{team}' в {project} не найден ({r.get('reason')}). "
                f"Доступные команды проекта: {', '.join(teams) or 'нет'}")
    p = r["progress"]
    lines = [f"Спринт «{r['sprint']}» ({r['state']})"]
    if p:
        lines.append(f"Прогресс: день {p['day']} из {p['of']} ({p['pct_elapsed']}% времени), конец {p['ends']}")
    lines.append(f"Всего {r['total']} | Готово {r['done']} ({r['pct_done']}%) | в работе {r['active']} | "
                 f"не начато {r['not_started']} | снято {r['cancelled']} | дефектов {r['defects']}")
    lines.append(f"по статусам: {r['by_status']}")
    if r["at_risk_count"]:
        lines.append(f"⚠️ под риском не закрыться к концу спринта: {r['at_risk_count']}")
        for x in r["at_risk"]:
            lines.append(f"  {x}")
    return "\n".join(lines)


def tool_list_teams(args: dict) -> str:
    project = args["project"]
    teams = sp.list_active_teams(project)
    return f"Команды проекта {project} (по активным спринтам): {', '.join(teams) or 'нет активных спринтов'}"


def tool_svetofor_stream(args: dict) -> str:
    r = svetofor.svetofor_stream(args["project"], args.get("quarter"))
    col = {"green": "🟢", "yellow": "🟡", "red": "🔴", "grey": "⚪"}
    lines = [f"Светофор стрима {r['project']} (квартал {r['quarter']}): "
             f"{col[r['color']]} {r['color'].upper()} — {r['reason']}", "по метрикам:"]
    for c in r["metrics"]:
        lines.append(f"  {col[c['color']]} {c['label']}: {c.get('reason')}")
    lines.append("(пороги настраиваются в config/zones.json; провизорные значения помечены)")
    return "\n".join(lines)


def tool_portfolio_overview(args: dict) -> str:
    base = args.get("base_jql") or "issuetype = Epic"
    r = tg.portfolio_overview(base)
    lines = [f"Портфельный обзор ({r['projects_scanned']} проектов). "
             f"Всего просрочек: {r['total_overdue']}, всего WIP: {r['total_wip']}.",
             "Топ по просрочкам (проект | просрочено | WIP):"]
    for row in r["top"]:
        lines.append(f"  {row['project']}: {row['overdue']} / {row['wip']}")
    lines.append("Для детального разбора одного проекта используй scan_triggers с jql=project=<KEY> AND issuetype=Epic.")
    return "\n".join(lines)


def tool_scan_triggers(args: dict) -> str:
    jql = args["jql"]
    detectors = args.get("detectors")
    r = tg.scan(jql, detectors)
    lines = [f"Скан триггеров по JQL: {jql}",
             f"эпиков просканировано: {r['scanned']}, находок: {r['findings_count']}", ""]
    if not r["findings"]:
        lines.append("сигналов не найдено")
    for f in r["findings"]:
        lines.append(f"[{f['severity']}] {f['key']} — {f['trigger']}: {f['detail']}")
    return "\n".join(lines)


def tool_cycle_time(args: dict) -> str:
    key = args["key"]
    it = jc.get_issue(key, fields="status,issuetype,summary,created,resolutiondate")
    r = m.cycle_time_by_stage(it)
    total = sum(r["stages_days"].values()) or 1
    lines = [f"{r['key']} [{r['current_status']}], в работе: {'да' if r['ongoing'] else 'нет'}",
             "время по стадиям (дней, % от суммы):"]
    for st, d in sorted(r["stages_days"].items(), key=lambda x: -x[1]):
        lines.append(f"  {st}: {d} ({d/total*100:.0f}%)")
    return "\n".join(lines)


def tool_wip_epics(args: dict) -> str:
    jql = args.get("jql") or "issuetype=Epic"
    issues = jc.search(jql, fields="status", max_results=500)
    r = m.wip_epics(issues)
    lines = [f"WIP эпиков (в активных статусах) по JQL: {jql}",
             f"WIP = {r['wip']}",
             f"по статусам: {r['by_status']}",
             f"активные статусы: {', '.join(r['active_statuses'])}"]
    return "\n".join(lines)


def tool_throughput(args: dict) -> str:
    jql = args.get("jql") or "issuetype=Epic"
    quarter = args.get("quarter")
    issues = jc.search(jql, fields="status,resolutiondate", max_results=500)
    r = m.throughput(issues, quarter)
    if quarter:
        return (f"Throughput по JQL: {jql}\n"
                f"закрыто эпиков в квартале {r['quarter']} ({r['quarter_window'][0]}..{r['quarter_window'][1]}): "
                f"{r['done_in_quarter']}\nвсего закрытых (Done) в выборке: {r['done_total']}")
    return f"Throughput по JQL: {jql}\nвсего закрытых эпиков (Done): {r['done_total']}"


def tool_predictability(args: dict) -> str:
    quarter = args["quarter"]
    jql = args.get("jql") or "issuetype=Epic"
    issues = jc.search(jql, fields=f"status,summary,labels,resolutiondate,{config.FIELD_FORECAST_DATE}",
                       max_results=300)
    r = m.predictability(issues, quarter)
    lines = [f"Predictability {r['quarter']} (окно {r['quarter_window'][0]}..{r['quarter_window'][1]}, метка {r['kub_label']})",
             "⚠️ определение НЕ сверено с эталоном — приведены ВСЕ трактовки, выбор за методологией:",
             f"эпиков с меткой: {r['committed_by_label']}, из них с прогнозной датой в квартале: {r['committed_with_forecast_in_quarter']}",
             ""]
    for name, v in r["variants"].items():
        pct = f"{v['ratio']:.0%}" if v["ratio"] is not None else "—"
        lines.append(f"  {name}: {v['num']}/{v['den']} = {pct}")
    return "\n".join(lines)


TOOLS = [
    {
        "name": "svetofor_stream",
        "description": "Светофор стрима (🟢🟡🔴) по метрикам: LT, TTM, предсказуемость, чистота данных. "
                       "Красит каждую метрику по порогам и сводит в один цвет. Пороги провизорные (config/zones.json). "
                       "Аргументы: project (напр. AIHUB), quarter (опц., напр. 26Q3).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Ключ проекта Jira"},
                "quarter": {"type": "string", "description": "Квартал, опц."},
            },
            "required": ["project"],
        },
        "handler": tool_svetofor_stream,
    },
    {
        "name": "team_digest",
        "description": "Готовый УТРЕННИЙ ДАЙДЖЕСТ тимлиду по команде: статус спринта + топ-рекомендации + что под риском. "
                       "Используй для запросов вида «сводка/дайджест по команде», «что у команды и что делать». "
                       "Аргументы: project (напр. AIHUB), team (префикс, напр. Copilot).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Ключ проекта Jira"},
                "team": {"type": "string", "description": "Префикс команды (Copilot / NLP / OPS / CV)"},
            },
            "required": ["project", "team"],
        },
        "handler": tool_team_digest,
    },
    {
        "name": "recommend_team",
        "description": "Практические рекомендации команде на основе её РЕАЛЬНЫХ данных спринта (сигнал → что делать). "
                       "Не общий чек-лист, а привязка к фактам. Аргументы: project, team.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Ключ проекта Jira"},
                "team": {"type": "string", "description": "Префикс команды"},
            },
            "required": ["project", "team"],
        },
        "handler": tool_recommend_team,
    },
    {
        "name": "team_sprint_status",
        "description": "Статус ТЕКУЩЕГО спринта команды (уровень Team Lead): сколько историй всего/закрыто/в работе, "
                       "прогресс спринта по дням, дефекты и элементы под риском не закрыться. Команда определяется "
                       "префиксом спринта (Team-поле в Jira пустое!). Аргументы: project (напр. AIHUB), team (префикс, напр. Copilot). "
                       "ВСЕГДА используй этот инструмент для вопросов про спринт команды — не считай вручную.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Ключ проекта Jira, напр. AIHUB"},
                "team": {"type": "string", "description": "Префикс команды из имени спринта, напр. Copilot / NLP / OPS / CV"},
            },
            "required": ["project", "team"],
        },
        "handler": tool_team_sprint_status,
    },
    {
        "name": "list_teams",
        "description": "Список команд проекта (по префиксам активных спринтов). Используй, если не знаешь, какие команды есть.",
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string", "description": "Ключ проекта Jira"}},
            "required": ["project"],
        },
        "handler": tool_list_teams,
    },
    {
        "name": "portfolio_overview",
        "description": "БЫСТРАЯ сводка по ВСЕМ командам/проектам сразу (для вопросов вида «проанализируй все команды»). "
                       "Возвращает по проектам: число просроченных эпиков и WIP, топ проблемных. Работает за секунды "
                       "(фильтрация на стороне Jira). Используй ЭТОТ инструмент для кросс-командного взгляда, а не перебор "
                       "scan_triggers по каждому проекту. Затем можно углубиться в конкретный проект через scan_triggers.",
        "inputSchema": {
            "type": "object",
            "properties": {"base_jql": {"type": "string", "description": "База выборки, по умолчанию 'issuetype = Epic'"}},
        },
        "handler": tool_portfolio_overview,
    },
    {
        "name": "scan_triggers",
        "description": "Проактивный скан проблем-сигналов по эпикам стрима: просроченные эпики "
                       "(overdue_epic), снятые метки КУБ (removed_kub_label — пытаются убрать из коммита), "
                       "недекомпозированные эпики (undecomposed_epic — 0-1 историй). Возвращает находки с severity. "
                       "Аргумент jql — выборка эпиков, напр. project=AIHUB AND issuetype=Epic. "
                       "detectors — опц. список нужных детекторов.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "jql": {"type": "string", "description": "JQL для эпиков стрима"},
                "detectors": {"type": "array", "items": {"type": "string"},
                              "description": "опц.: overdue_epic|removed_kub_label|undecomposed_epic"},
            },
            "required": ["jql"],
        },
        "handler": tool_scan_triggers,
    },
    {
        "name": "cycle_time_by_stage",
        "description": "Сколько времени (дней) эпик/история провёл в каждом статусе — для поиска bottleneck "
                       "(длинная Разработка/Тестирование = нехватка ресурсов или слабая декомпозиция). Аргумент key.",
        "inputSchema": {
            "type": "object",
            "properties": {"key": {"type": "string", "description": "Ключ эпика/истории"}},
            "required": ["key"],
        },
        "handler": tool_cycle_time,
    },
    {
        "name": "wip_epics",
        "description": "WIP эпиков стрима: сколько эпиков сейчас в активных статусах "
                       "(Постановка задачи, Реализация/Разработка, Тестирование, Внедрение). "
                       "Аргумент jql — выборка эпиков, напр. project=AIHUB AND issuetype=Epic.",
        "inputSchema": {
            "type": "object",
            "properties": {"jql": {"type": "string", "description": "JQL для эпиков стрима"}},
            "required": ["jql"],
        },
        "handler": tool_wip_epics,
    },
    {
        "name": "throughput",
        "description": "Throughput/Velocity: сколько эпиков завершено (Done). Если задан quarter (напр. 26Q3) — "
                       "считает закрытые с датой закрытия внутри квартала. Аргумент jql — выборка эпиков стрима.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "jql": {"type": "string", "description": "JQL для эпиков стрима"},
                "quarter": {"type": "string", "description": "Квартал, напр. 26Q3 (опционально)"},
            },
            "required": ["jql"],
        },
        "handler": tool_throughput,
    },
    {
        "name": "predictability",
        "description": "Предсказуемость квартальных планов стрима (доля эпиков, завершённых в плановый квартал). "
                       "ВНИМАНИЕ: определение неоднозначно и НЕ сверено с эталоном — инструмент возвращает ВСЕ "
                       "трактовки сразу, не выдавай одно число как единственно верное. Аргументы: quarter (напр. 26Q2), "
                       "jql (выборка эпиков стрима, напр. project=AIHUB AND issuetype=Epic).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "quarter": {"type": "string", "description": "Квартал, напр. 26Q2"},
                "jql": {"type": "string", "description": "JQL для эпиков стрима, напр. project=AIHUB AND issuetype=Epic"},
            },
            "required": ["quarter"],
        },
        "handler": tool_predictability,
    },
    {
        "name": "ttm_epic",
        "description": "Детерминированно посчитать Time-to-Market (TTM) эпика в днях по данным Jira "
                       "(от статуса 'Постановка задачи' до 'Подтверждение эффекта'). Возвращает число "
                       "и исходные даты для проверки. Используй вместо ручного вычитания дат.",
        "inputSchema": {
            "type": "object",
            "properties": {"key": {"type": "string", "description": "Ключ эпика, напр. AIHUB-581"}},
            "required": ["key"],
        },
        "handler": tool_ttm_epic,
    },
    {
        "name": "lead_time_story",
        "description": "Детерминированно посчитать Lead Time (LT) истории в днях "
                       "(от статуса 'Анализ' до 'Done'). Возвращает число и исходные даты. "
                       "Используй вместо ручного вычитания дат.",
        "inputSchema": {
            "type": "object",
            "properties": {"key": {"type": "string", "description": "Ключ истории, напр. AIHUB-482"}},
            "required": ["key"],
        },
        "handler": tool_lead_time_story,
    },
    {
        "name": "epic_aging",
        "description": "Возраст незавершённого эпика в днях (от 'Постановка задачи' до сейчас).",
        "inputSchema": {
            "type": "object",
            "properties": {"key": {"type": "string", "description": "Ключ эпика"}},
            "required": ["key"],
        },
        "handler": tool_epic_aging,
    },
    {
        "name": "metric_by_jql",
        "description": "Посчитать метрику (lead_time|ttm|epic_aging) агрегированно по выборке issue из JQL. "
                       "Возвращает среднее по методологии (с исключениями: Снят, LT<1д, TTM<3д) и разбивку.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "jql": {"type": "string", "description": "JQL-запрос, напр. project=AIHUB AND issuetype=История"},
                "metric": {"type": "string", "enum": ["lead_time", "ttm", "epic_aging"],
                           "description": "Какую метрику считать (по умолчанию lead_time)"},
            },
            "required": ["jql"],
        },
        "handler": tool_metric_by_jql,
    },
]

_HANDLERS = {t["name"]: t["handler"] for t in TOOLS}


def _tools_list_payload():
    return [{k: t[k] for k in ("name", "description", "inputSchema")} for t in TOOLS]


# ---------- JSON-RPC цикл ----------

def handle(req: dict):
    """Возвращает объект-ответ или None для нотификаций."""
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        proto = params.get("protocolVersion", DEFAULT_PROTOCOL)
        return _ok(rid, {
            "protocolVersion": proto,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return _ok(rid, {})
    if method == "tools/list":
        return _ok(rid, {"tools": _tools_list_payload()})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        handler = _HANDLERS.get(name)
        if not handler:
            return _err(rid, -32601, f"неизвестный инструмент: {name}")
        try:
            text = handler(args)
            return _ok(rid, {"content": [{"type": "text", "text": text}], "isError": False})
        except Exception as e:
            log("ошибка инструмента", name, repr(e))
            log(traceback.format_exc())
            return _ok(rid, {"content": [{"type": "text", "text": f"Ошибка: {e}"}], "isError": True})

    if rid is not None:
        return _err(rid, -32601, f"метод не поддерживается: {method}")
    return None


def _ok(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def main():
    log("старт, инструментов:", len(TOOLS))
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            log("не JSON:", line[:120])
            continue
        try:
            resp = handle(req)
        except Exception as e:
            log("фатальная ошибка обработки:", repr(e))
            resp = _err(req.get("id"), -32603, str(e))
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
