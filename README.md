# Dev Pulse

Система delivery-мониторинга поверх Jira для Magnit Tech. Отвечает руководителям
на три вопроса: **всё ли ок / где не ок и почему / что делать**.

Три способа получить пользу:
1. **Чат-бот** в Tag (Mattermost) — спросил вопрос, получил ответ (через ИИ).
2. **Дайджест** — утром сам присылает тимлиду сводку по команде (без ИИ).
3. **Светофор-сайт** — веб-дэшборд со всеми стримами, метриками и drill-down до команд.

> Принцип всей системы: **ИИ интерпретирует и объясняет, а считает — детерминированный
> Python-код.** Метрики никогда не «придумывает» модель — они проверяемы.

Подробные README по частям:
- 🚦 **[webapp/README.md](webapp/README.md)** — светофор-сайт (архитектура, запуск, как добавлять стримы).
- ⚙️ **[config/README.md](config/README.md)** — как менять пороги и настройки **без кода** (для всей команды).

---

## 🟢 Для нетехнической команды

### Что можно менять самому (без программирования)
Всё в папке **`config/`** — это обычные текстовые файлы, правятся через git:
- **`config/zones.json`** — пороги зон 🟢🟡🔴 для каждой метрики (например, «Lead Time зелёный до 14 дней»). Меняешь число — светофор перекрашивается.
- **`config/dashboard.json`** — какие стримы показывать, их названия.
- Подробная инструкция что и как: **[config/README.md](config/README.md)**.

Правило: меняй **значения** (числа, названия, true/false), не трогай названия полей и скобки `{ }`.

### Как открыть светофор-сайт
Если сервис запущен — открой в браузере:
**http://localhost:8787** (позже будет постоянный адрес на сервере).

---

## 🔧 Для технической команды

### Запуск с нуля
```bash
# 1. Включить VPN (нужен доступ к корп-Jira)
# 2. Заполнить .env (скопировать из .env.example, вписать токены)

./start-server.sh              # opencode для чат-бота (терминал 1)
./start-bot.sh                 # чат-бот в Tag (терминал 2)
python3 webapp/server.py       # светофор-сайт → http://localhost:8787
python3 digest_bot.py --now    # разослать дайджест сейчас (тест)
```
После обрыва VPN/сна `opencode` сам не оживает — перезапустить `start-server.sh`.

### Три составляющие и как они устроены

**1. Чат-бот (через ИИ):**
```
Tag → mm_bot.py → ask_jira.py → opencode :4096
    → агент delivery-transform (LLM MagnitCopilot)
    → MCP-инструменты devpulse (Python, детерминированно) → Jira REST → ответ
```

**2. Дайджест (без ИИ):**
```
launchd 9:00 → digest_bot.py → devpulse (Python) → Jira REST → сообщение в Tag
```
Кому слать — задаётся в `subscriptions.json` (`[{"mm_user_id","project","team"}]`).
Автозапуск по расписанию **пока не установлен** — ставится вручную:
`cp com.devpulse.digest.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.devpulse.digest.plist`.
Проверить без отправки: `python3 digest_bot.py --dry`.

**3. Светофор-сайт (без ИИ):** веб-сервер + фоновый расчёт в кэш. См. [webapp/README.md](webapp/README.md).
```
webapp/server.py → фоновый воркер считает всё в кэш → отдаёт мгновенно (SPA + JSON API)
```

---

## Карта файлов

### Ядро расчёта — пакет `devpulse/` (Python, без ИИ, переиспользуется всеми частями)
| Файл | Что делает |
|---|---|
| `config.py` | Константы: статусы, пороги, поля Jira, границы кварталов |
| `jira_client.py` | Клиент Jira REST + Agile API (доски). Только чтение |
| `timeline.py` | **Ядро**: changelog → переходы статусов (основа метрик длительности) |
| `metrics.py` | Метрики: lead_time, ttm, epic_aging, cycle_time, wip, throughput, predictability |
| `triggers.py` | Детекторы проблем (просрочки, снятые КУБ, недекомпозиция) + `portfolio_overview` |
| `sprints.py` | Уровень команды. **Команда = доска Jira** (rapidViewId спринта → имя доски), 100% точно |
| `recommendations.py` | Библиотека «сигнал → совет» + `compose_digest` (текст дайджеста) |
| `svetofor/` | Светофор: `zones.py` (раскраска), `aggregate.py` (свод в цвет), `report.py` (сборка по стриму/команде), `placeholders.py` (заглушки) |
| `mcp_server.py` | Оборачивает всё выше в 15 MCP-инструментов для ИИ-агента |

### Точки входа (запускаются как процессы)
| Файл | Что это |
|---|---|
| `mm_bot.py` | Чат-бот в Tag (polling) |
| `ask_jira.py` | Мост чат-бот → opencode, память сессий per-user |
| `digest_bot.py` | Ежедневный дайджест тимлидам (без opencode). `--now` / `--dry` |
| `webapp/server.py` | Светофор-сайт (веб-сервер + фоновый расчёт) |
| `run_metrics.py` | CLI расчёта метрик (отладка) |
| `build_dashboard.py` | Генератор статического `dashboard.html` (альтернатива живому сайту) |

### Настройки (правит команда)
| Путь | Что это |
|---|---|
| `config/zones.json` | Пороги зон светофора 🟢🟡🔴 + кастом по стримам |
| `config/aggregation.json` | Как свести метрики в один цвет |
| `config/dashboard.json` | Список стримов, названия |
| `config/README.md` | Инструкция по правкам для всей команды |

### Инфраструктура и секреты
| Путь | Что это |
|---|---|
| `.env` | Секреты (НЕ коммитить): токены Jira/Confluence/LiteLLM/Mattermost |
| `.env.example` | Шаблон .env |
| `start-server.sh` / `start-bot.sh` | Запуск opencode / чат-бота |
| `com.devpulse.digest.plist` | launchd-задача автозапуска дайджеста в 9:00 (шаблон; **устанавливается вручную**, см. выше) |
| `subscriptions.json` | Кому слать дайджест (генерируется/правится руками; в .gitignore) |

Агент (системный промпт ИИ) — вне проекта: `~/.config/opencode/agent/delivery-transform.md`.
Конфиг провайдера модели и MCP: `~/.config/opencode/opencode.json`.

### Справочное (не код)
| Путь | Что это |
|---|---|
| `CONTEXT_confluence.md` | Конспект методологии из Confluence (метрики, гигиена, сущности) |
| `confluence_dump/` | Сырые выгрузки страниц Confluence |

### Генерируется автоматически (в `.gitignore`, руками не трогать)
`sessions.json` · `subscriptions.json` · `digest_state.json` · `webapp/cache/` · `*.log` · `dashboard.html`

---

## Полезные команды
```bash
python3 run_metrics.py issue AIHUB-596                 # метрики одной задачи
python3 digest_bot.py --now                            # разослать дайджест
python3 -c "from devpulse import sprints as s; print(s.list_active_teams('AIHUB'))"  # команды стрима
```

## Статус методологии (важно)
Часть порогов и метрик — **провизорные**, пока команда/Дима не подтвердят:
- Lead Time / TTM пороги — черновые (правятся в `config/zones.json`).
- **Predictability** — формула не зафиксирована → в светофоре выключена (`enabled: false`).
- **Чистота данных** — расчёт не построен → заглушка (`devpulse/svetofor/placeholders.py`).

Всё это меняется без переписывания кода — см. `config/README.md`.
