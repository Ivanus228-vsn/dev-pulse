#!/usr/bin/env python3
"""digest_bot.py — ежедневный дайджест тимлидам в Tag (без opencode/LLM).

Чистый Python: Jira REST + Mattermost API. Не зависит от opencode-сервера,
поэтому переживает его смерть после VPN-обрыва. Запускается планировщиком
(launchd) раз в день, либо вручную с --now для теста.

Подписки — subscriptions.json: [{"mm_user_id","project","team"}].
Идемпотентность — digest_state.json (не слать дважды в день).
"""
from __future__ import annotations
import os
import sys
import json
import argparse
import urllib.request
from datetime import date

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _load_dotenv():
    path = os.path.join(_HERE, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

from devpulse import recommendations as rec, jira_client as jc  # noqa: E402

MM_TOKEN = os.environ.get("MM_BOT_TOKEN", "")
MM_BASE = "https://tag.magnit.ru/api/v4"
BOT_ID = os.environ.get("MM_BOT_ID", "")
SUBS_FILE = os.path.join(_HERE, "subscriptions.json")
STATE_FILE = os.path.join(_HERE, "digest_state.json")


def log(*a):
    print("[digest]", *a, flush=True)


def _mm(method: str, path: str, payload=None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        MM_BASE + path, data=data, method=method,
        headers={"Authorization": "Bearer " + MM_TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def dm_channel(user_id: str) -> str:
    """id личного канала бота с пользователем (создаётся, если нет)."""
    ch = _mm("POST", "/channels/direct", [BOT_ID, user_id])
    return ch["id"]


def send_dm(user_id: str, message: str):
    _mm("POST", "/posts", {"channel_id": dm_channel(user_id), "message": message})


def jira_reachable() -> bool:
    try:
        jc._get("/myself", timeout=10)
        return True
    except Exception as e:
        log("Jira недоступна (VPN?):", repr(e))
        return False


def _load(path, default):
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    return default


def _save_state(state):
    json.dump(state, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def run(force: bool, dry: bool):
    today = date.today().isoformat()
    if not force and date.today().weekday() >= 5:
        log("выходной — пропускаю (используй --now, чтобы форсировать)")
        return
    subs = _load(SUBS_FILE, [])
    if not subs:
        log("нет подписок в subscriptions.json")
        return
    if not dry and not jira_reachable():
        log("прерываю: нет доступа к Jira")
        return
    state = _load(STATE_FILE, {})
    for s in subs:
        key = f'{s["mm_user_id"]}:{s["project"]}:{s["team"]}'
        if not force and state.get(key) == today:
            log("уже отправлено сегодня:", key)
            continue
        try:
            msg = rec.compose_digest(s["project"], s["team"])
        except Exception as e:
            log("ошибка сборки дайджеста", key, repr(e))
            continue
        if dry:
            log("DRY —", key, "\n" + msg + "\n")
            continue
        try:
            send_dm(s["mm_user_id"], msg)
            state[key] = today
            log("отправлено:", key)
        except Exception as e:
            log("ошибка отправки", key, repr(e))
    if not dry:
        _save_state(state)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Ежедневный дайджест Dev Pulse")
    ap.add_argument("--now", action="store_true", help="форсировать (игнор выходных и идемпотентности)")
    ap.add_argument("--dry", action="store_true", help="только показать, не отправлять")
    a = ap.parse_args()
    run(force=a.now, dry=a.dry)
