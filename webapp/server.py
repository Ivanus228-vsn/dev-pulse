#!/usr/bin/env python3
"""Автономный веб-сервис светофора Dev Pulse — все стримы, двухуровневый кэш.

Лёгкий уровень: список ВСЕХ стримов + дешёвые счётчики (быстро, для боковой
панели выбора). Тяжёлый уровень: полная детализация каждого стрима (LT/TTM,
сигналы, стадии, команды с рекомендациями) — считается фоном прогрессивно и
кэшируется. Пользователь ничего не ждёт. Без opencode/LLM, чистый stdlib.

  python3 webapp/server.py    → http://localhost:8787
"""
from __future__ import annotations
import os
import sys
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _load_dotenv():
    p = os.path.join(_ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

from webapp import model  # noqa: E402

PORT = int(os.environ.get("DEVPULSE_PORT", "8787"))
LIGHT_MIN = int(os.environ.get("DEVPULSE_LIGHT_MIN", "20"))
STATIC = os.path.join(_HERE, "static")
CACHE_DIR = os.path.join(_HERE, "cache")
LIGHT_FILE = os.path.join(CACHE_DIR, "light.json")
FULL_FILE = os.path.join(CACHE_DIR, "full.json")
os.makedirs(CACHE_DIR, exist_ok=True)

_lock = threading.Lock()
_light = {"generated": None, "streams": [], "status": "старт…"}
_full: dict[str, dict] = {}      # project -> полная детализация


def log(*a):
    print("[web]", *a, flush=True)


def _save(path, obj):
    try:
        json.dump(obj, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception as e:
        log("save error", path, e)


def _load_disk():
    global _light, _full
    if os.path.exists(LIGHT_FILE):
        try:
            _light = json.load(open(LIGHT_FILE, encoding="utf-8"))
            _light["status"] = "из снимка"
        except Exception:
            pass
    if os.path.exists(FULL_FILE):
        try:
            _full = json.load(open(FULL_FILE, encoding="utf-8"))
        except Exception:
            pass


def refresh_light():
    log("light: список стримов…")
    t = time.time()
    try:
        streams = model.discover_streams()
        with _lock:
            _light["streams"] = streams
            _light["generated"] = time.strftime("%Y-%m-%d %H:%M")
            _light["status"] = "актуально"
            _light["quarter"] = model._current_quarter()
        _save(LIGHT_FILE, _light)
        log(f"light готов за {time.time()-t:.0f}s, стримов: {len(streams)}")
    except Exception as e:
        log("light ошибка:", repr(e))


def heavy_worker():
    """Бесконечно обходит стримы и досчитывает полную детализацию в кэш."""
    while True:
        with _lock:
            streams = list(_light.get("streams", []))
        if not streams:
            time.sleep(10)
            continue
        for s in streams:
            proj, label = s["project"], s["label"]
            try:
                data = model.build_stream_full(proj, label)
                with _lock:
                    _full[proj] = data
                _save(FULL_FILE, _full)
            except Exception as e:
                log("heavy", proj, "ошибка:", repr(e))
            time.sleep(1)
        log("heavy: полный цикл детализации пройден")
        time.sleep(30)


def light_worker():
    refresh_light()
    while True:
        time.sleep(LIGHT_MIN * 60)
        refresh_light()


def _streams_payload():
    """Лёгкий список + цвет из полного кэша, где посчитан."""
    with _lock:
        streams = []
        for s in _light.get("streams", []):
            full = _full.get(s["project"])
            row = dict(s)
            if full:
                row["overall"] = full.get("overall")
                row["metrics"] = full.get("metrics", {})
                row["ready"] = True
            else:
                row["overall"] = "grey"
                row["ready"] = False
            streams.append(row)
        return {"generated": _light.get("generated"), "status": _light.get("status"),
                "quarter": _light.get("quarter"), "streams": streams,
                "computed": sum(1 for s in streams if s.get("ready")), "total": len(streams)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(b)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False), )

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        try:
            if path in ("/", "/index.html"):
                return self._file("index.html", "text/html; charset=utf-8")
            if path.startswith("/static/"):
                return self._file(path[len("/static/"):], self._ctype(path))
            if path == "/api/streams":
                return self._json(_streams_payload())
            if path.startswith("/api/stream/"):
                proj = path[len("/api/stream/"):].strip("/")
                with _lock:
                    full = _full.get(proj)
                    light = next((s for s in _light["streams"] if s["project"] == proj), None)
                if full:
                    return self._json(full)
                return self._json({"computing": True, "project": proj, "light": light}, 202)
            if path.startswith("/api/team/"):
                rest = path[len("/api/team/"):].strip("/").split("/", 1)
                if len(rest) == 2:
                    proj, team = rest
                    with _lock:
                        full = _full.get(proj)
                    t = next((x for x in (full or {}).get("teams", []) if x["team"] == team), None)
                    return self._json(t or {"error": "команда не найдена/не посчитана"}, 200 if t else 404)
            return self._json({"error": "not found", "path": path}, 404)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _file(self, rel, ctype):
        fp = os.path.join(STATIC, rel)
        if not os.path.abspath(fp).startswith(STATIC) or not os.path.exists(fp):
            return self._json({"error": "not found"}, 404)
        with open(fp, "rb") as f:
            self._send(200, f.read(), ctype)

    @staticmethod
    def _ctype(path):
        if path.endswith(".js"):
            return "application/javascript; charset=utf-8"
        if path.endswith(".css"):
            return "text/css; charset=utf-8"
        return "application/octet-stream"


def main():
    _load_disk()
    threading.Thread(target=light_worker, daemon=True).start()
    threading.Thread(target=heavy_worker, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    log(f"светофор на http://localhost:{PORT}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
