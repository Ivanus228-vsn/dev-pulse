"""mm_bot.py — Mattermost-бот (polling) поверх ask_jira.
Опрашивает личные каналы, отвечает через агента, у каждого юзера своя память."""
import json, time, os, sys, urllib.request
import ask_jira

TOKEN = os.environ.get("MM_BOT_TOKEN")
if not TOKEN:
    sys.exit("MM_BOT_TOKEN не задан в окружении (source .env). См. .env.example")
BASE = "https://tag.magnit.ru/api/v4"
BOT_ID = os.environ.get("MM_BOT_ID", "")  # id бота из окружения
POLL_INTERVAL = 2

def api(method, path, payload=None):
    url = BASE + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data,
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
        method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))

def send(channel_id, message):
    api("POST", "/posts", {"channel_id": channel_id, "message": message})

def get_dm_channels():
    chans = api("GET", f"/users/{BOT_ID}/channels")
    return [c for c in chans if c["type"] == "D"]

last_seen = {}       # channel_id -> create_at последнего обработанного
processed = set()    # id постов уже взятых в работу (защита от повтора)

def poll_channel(channel_id):
    posts = api("GET", f"/channels/{channel_id}/posts?per_page=5")
    order = posts.get("order", [])
    for post_id in reversed(order):
        post = posts["posts"][post_id]
        sender_id = post["user_id"]
        text = post["message"].strip()

        if sender_id == BOT_ID:
            last_seen[channel_id] = max(last_seen.get(channel_id, 0), post["create_at"])
            continue
        if post["create_at"] <= last_seen.get(channel_id, 0):
            continue
        if post_id in processed:
            continue

        # СРАЗУ помечаем обработанным — до долгого вызова ask(),
        # чтобы следующая итерация цикла не взяла это же сообщение
        processed.add(post_id)
        last_seen[channel_id] = post["create_at"]
        if not text:
            continue

        print(f"[вопрос] от {sender_id}: {text}")
        send(channel_id, "🔍 Смотрю в Jira, секунду…")
        try:
            answer = ask_jira.ask(text, user_id=sender_id)
        except Exception as e:
            answer = f"⚠️ Ошибка при обработке: {e}"
        send(channel_id, answer or "(пустой ответ)")
        print("[ответ] отправлен")

# при старте — пометить текущие последние посты как виденные
print("Инициализация…")
for c in get_dm_channels():
    try:
        posts = api("GET", f"/channels/{c['id']}/posts?per_page=1")
        order = posts.get("order", [])
        last_seen[c["id"]] = posts["posts"][order[0]]["create_at"] if order else 0
    except Exception:
        last_seen[c["id"]] = 0

print("Бот запущен (polling). Слушаю личные сообщения… (Ctrl+C для выхода)")
while True:
    try:
        for c in get_dm_channels():
            poll_channel(c["id"])
        time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\nОстановлен.")
        break
    except Exception as e:
        print(f"[ошибка опроса] {e}")
        time.sleep(POLL_INTERVAL)
