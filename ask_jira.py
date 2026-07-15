"""ask_jira.py — спросить Jira через локальный opencode-сервер из питона.
Память диалога: у каждого userID своя сессия OpenCode (переиспользуется).
Нужен запущенный `opencode serve --port 4096` + включённый VPN."""
import json, sys, os, urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://localhost:4096"
MODEL = {"providerID": "magnit_prod", "modelID": "MagnitCopilot"}
AGENT = "delivery-transform"
SESSIONS_FILE = "sessions.json"

def post(path, payload):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))

def _load_sessions() -> dict:
    if os.path.exists(SESSIONS_FILE):
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save_sessions(data: dict):
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _create_session() -> str:
    return post("/session", {
        "title": "agent",
        "permission": [{"permission": "question", "action": "deny", "pattern": "*"}]
    })["id"]

def get_session_for_user(user_id: str) -> str:
    sessions = _load_sessions()
    sid = sessions.get(user_id)
    if sid:
        return sid
    sid = _create_session()
    sessions[user_id] = sid
    _save_sessions(sessions)
    return sid

def ask(question: str, user_id: str = "local") -> str:
    sid = get_session_for_user(user_id)
    msg = post(f"/session/{sid}/message", {
        "agent": AGENT,
        "model": MODEL,
        "parts": [{"type": "text", "text": question}]
    })
    parts = msg.get("parts", [])
    texts = [p.get("text", "") for p in parts if p.get("type") == "text"]
    return "\n".join(t for t in texts if t).strip()

def reset_user(user_id: str):
    sessions = _load_sessions()
    if user_id in sessions:
        del sessions[user_id]
        _save_sessions(sessions)

if __name__ == "__main__":
    user = "local"
    print("Чат с агентом (память включена). Пустая строка — выход.\n")
    while True:
        try:
            q = input("Ты: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            break
        print("\nАгент:", ask(q, user_id=user), "\n")
