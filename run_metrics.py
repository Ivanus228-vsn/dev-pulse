#!/usr/bin/env python3
"""CLI для вычислительного слоя Dev Pulse.

Примеры:
  python3 run_metrics.py lead-time --jql 'project = TRAN AND issuetype = "История"'
  python3 run_metrics.py ttm       --jql 'project = TRAN AND issuetype = Epic'
  python3 run_metrics.py issue TRAN-51        # разбор одной issue по всем метрикам
  python3 run_metrics.py lead-time --jql '...' --json   # машинный вывод

Нужен JIRA_TOKEN в окружении (source .env) и VPN.
"""
from __future__ import annotations
import argparse
import json
import sys

from devpulse import jira_client as jc, metrics as m


def _print_result(r: m.MetricResult):
    flag = "✓" if r.included else "·"
    val = f"{r.value} дн" if r.value is not None else "—"
    print(f"  {flag} {r.key}: {r.metric}={val}  ({r.reason})")
    if r.included and r.dates:
        ds = "  ".join(f"{k}={v}" for k, v in r.dates.items() if v)
        print(f"      {ds}")


def cmd_metric(fn, jql: str, as_json: bool):
    issues = jc.search(jql, fields="status,issuetype,summary",
                       max_results=200, expand_changelog=True)
    results = [fn(it) for it in issues]
    if as_json:
        out = {"results": [r.as_dict() for r in results],
               "aggregate": m.aggregate(results)}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    print(f"Выбрано issue: {len(issues)}")
    for r in results:
        _print_result(r)
    print("\nАГРЕГАТ:", m.aggregate(results))


def cmd_issue(key: str, as_json: bool):
    it = jc.get_issue(key)
    all_m = {"lead_time": m.lead_time(it), "ttm": m.ttm(it), "epic_aging": m.epic_aging(it)}
    if as_json:
        print(json.dumps({k: v.as_dict() for k, v in all_m.items()},
                         ensure_ascii=False, indent=2))
        return
    st = it.get("fields", {}).get("status", {}).get("name", "?")
    ty = it.get("fields", {}).get("issuetype", {}).get("name", "?")
    print(f"{key} [{ty} / {st}]")
    for r in all_m.values():
        _print_result(r)


def main():
    p = argparse.ArgumentParser(description="Вычислительный слой Dev Pulse")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("lead-time", "ttm", "epic-aging"):
        sp = sub.add_parser(name)
        sp.add_argument("--jql", required=True)
        sp.add_argument("--json", action="store_true")
    ip = sub.add_parser("issue")
    ip.add_argument("key")
    ip.add_argument("--json", action="store_true")

    a = p.parse_args()
    fnmap = {"lead-time": m.lead_time, "ttm": m.ttm, "epic-aging": m.epic_aging}
    if a.cmd in fnmap:
        cmd_metric(fnmap[a.cmd], a.jql, a.json)
    elif a.cmd == "issue":
        cmd_issue(a.key, a.json)


if __name__ == "__main__":
    try:
        main()
    except jc.JiraError as e:
        print(f"Ошибка Jira: {e}", file=sys.stderr)
        sys.exit(1)
