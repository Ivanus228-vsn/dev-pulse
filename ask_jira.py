"""ask_jira.py — спросить Jira через локальный opencode-сервер из питона.
Память диалога: у каждого userID своя сессия OpenCode (переиспользуется).
Нужен запущенный `opencode serve --port 4096` + включённый VPN."""
import json, sys, os, re, time, urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://localhost:4096"
MODEL = {"providerID": "magnit_prod", "modelID": "MagnitCopilot"}
AGENT = "delivery-transform"
SESSIONS_FILE = "sessions.json"

# Сколько раз пересылать вопрос, если модель выдала «протёкший» tool-call
# сырым текстом (баг формата MiniMax ↔ парсер OpenCode) или пустоту.
MAX_RETRIES = int(os.environ.get("ASK_MAX_RETRIES", "3"))
RETRY_DELAY = float(os.environ.get("ASK_RETRY_DELAY", "1.5"))  # сек между попытками

# Структурные маркеры вызова инструмента, которые НЕ должны попадать в чат.
# В нормальном ответе агента их не бывает → ложные срабатывания почти исключены.
_LEAK_RE = re.compile(
    r"</?\s*(?:[a-z0-9_]+:)?tool_call\b"      # <tool_call> / </minimax:tool_call>
    r"|</?\s*invoke\b"                          # <invoke name=...> / </invoke>
    r"|</?\s*arg_value\b"                       # <arg_value> / </arg_value>
    r"|</?\s*parameter\b"                       # <parameter name=...>
    r"|</?\s*function_calls?\b",                # <function_calls> / </function_call>
    re.IGNORECASE,
)
# Блок «протечки» целиком — чтобы вырезать его при аварийной очистке.
_LEAK_BLOCK_RE = re.compile(
    r"<\s*(?:[a-z0-9_]+:)?tool_call\b.*?</\s*(?:[a-z0-9_]+:)?tool_call\s*>"
    r"|<\s*invoke\b.*?</\s*invoke\s*>",
    re.IGNORECASE | re.DOTALL,
)

def _looks_broken(text: str) -> bool:
    """Ответ считается битым, если пустой или содержит сырой tool-call."""
    return (not text) or (not text.strip()) or bool(_LEAK_RE.search(text))

def _strip_leak(text: str) -> str:
    """Аварийная очистка: убрать блоки/огрызки tool-call, оставить осмысленный текст."""
    if not text:
        return ""
    cleaned = _LEAK_BLOCK_RE.sub("", text)
    cleaned = _LEAK_RE.sub("", cleaned)  # добить незакрытые огрызки тегов
    return cleaned.strip()

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

def _ask_once(sid: str, question: str) -> str:
    msg = post(f"/session/{sid}/message", {
        "agent": AGENT,
        "model": MODEL,
        "parts": [{"type": "text", "text": question}]
    })
    parts = msg.get("parts", [])
    texts = [p.get("text", "") for p in parts if p.get("type") == "text"]
    return "\n".join(t for t in texts if t).strip()

def ask(question: str, user_id: str = "local") -> str:
    """Спросить агента. При протечке tool-call / пустом ответе — пересылаем тот же
    вопрос (сэмплинг недетерминирован, повтор обычно даёт чистый ответ)."""
    sid = get_session_for_user(user_id)
    answer = ""
    for attempt in range(1, MAX_RETRIES + 1):
        answer = _ask_once(sid, question)
        if not _looks_broken(answer):
            return answer
        print(f"[retry {attempt}/{MAX_RETRIES}] битый ответ "
              f"(протечка tool-call/пусто), пересылаю вопрос", file=sys.stderr)
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)
    # Все попытки битые — не отдаём пользователю сырой tool-call.
    salvaged = _strip_leak(answer)
    if len(salvaged) >= 40:            # осталось что-то осмысленное — отдаём его
        return salvaged
    return ("⚠️ Не удалось получить корректный ответ (модель зациклилась на "
            "внутренней команде). Переспросите, пожалуйста, ещё раз.")

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
