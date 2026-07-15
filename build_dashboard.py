#!/usr/bin/env python3
"""build_dashboard.py — генератор фронта светофора.

Считает данные светофора по стримам (config/dashboard.json) и печёт
самодостаточный dashboard.html (данные вшиты внутрь). Как дайджест —
можно пересобирать по расписанию. Без opencode/LLM.

  python3 build_dashboard.py           # реальные данные (нужен VPN)
  python3 build_dashboard.py --mock    # демо-данные (без сети) — показать UI
"""
from __future__ import annotations
import os
import sys
import json
import html
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

CONFIG = os.path.join(_HERE, "config", "dashboard.json")
OUT = os.path.join(_HERE, "dashboard.html")


def _load_dotenv():
    p = os.path.join(_HERE, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


# ---------- сбор реальных данных ----------
def collect_real() -> dict:
    _load_dotenv()
    from devpulse.svetofor import report as R
    from devpulse import sprints as sp
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    streams = []
    for s in cfg["streams"]:
        proj, label = s["project"], s.get("label", s["project"])
        st = R.svetofor_stream(proj)
        teams = []
        try:
            for t in sp.list_active_teams(proj):
                tr = R.svetofor_team(proj, t)
                if tr.get("found"):
                    teams.append(tr)
        except Exception:
            pass
        streams.append({"project": proj, "label": label,
                        "overall": st["color"], "reason": st["reason"],
                        "metrics": st["metrics"], "teams": teams,
                        "quarter": st["quarter"]})
    return {"title": cfg.get("title", "Светофор стримов"),
            "note": cfg.get("note_prototype", ""),
            "quarter": streams[0]["quarter"] if streams else "",
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "streams": streams}


# ---------- демо-данные (без сети) ----------
def collect_mock() -> dict:
    def met(metric, label, color, value, reason, note=None):
        return {"metric": metric, "label": label, "color": color,
                "value": value, "reason": reason, "note": note}
    aihub_metrics = [
        met("lead_time", "Lead Time истории (дни)", "green", 6.4, "6.4 при порогах 🟢≤14 🟡≤21",
            "цель 14 / норма 21 — не подтверждено"),
        met("ttm", "Time-to-Market эпика (дни)", "red", 83.8, "83.8 при порогах 🟢≤57 🟡≤75",
            "провизорно"),
        met("predictability", "Предсказуемость квартала (%)", "yellow", 66.0, "66 при порогах 🟢≥80 🟡≥60",
            "заглушка: формула не зафиксирована"),
        met("data_quality", "Чистота данных (%)", "grey", None, "метрика выключена", "нет расчёта"),
    ]
    teams = [
        {"team": "Copilot", "color": "red", "reason": "сильно отстаёт (темп 0.55)",
         "sprint": "Copilot: спринт 36", "day": 13, "of": 14, "pct_elapsed": 93, "pct_done": 51,
         "total": 77, "done": 36, "active": 31, "at_risk": 34, "defects": 0,
         "at_risk_items": ["AIHUB-1985 [Разработка] Доработки TalkSummarizer",
                           "AIHUB-1974 [Разработка] Обновление MagnitGPT",
                           "AIHUB-1968 [В ожидании тестирования] Тестовая группа"]},
        {"team": "NLP", "color": "yellow", "reason": "отстаёт (темп 0.78)",
         "sprint": "NLP: спринт 36", "day": 10, "of": 14, "pct_elapsed": 71, "pct_done": 55,
         "total": 40, "done": 22, "active": 15, "at_risk": 12, "defects": 1, "at_risk_items": []},
        {"team": "CV", "color": "green", "reason": "идёт по плану (темп 0.95)",
         "sprint": "CV: спринт 38", "day": 3, "of": 14, "pct_elapsed": 21, "pct_done": 20,
         "total": 30, "done": 6, "active": 12, "at_risk": 0, "defects": 0, "at_risk_items": []},
    ]
    streams = [
        {"project": "AIHUB", "label": "AI HUB", "overall": "red",
         "reason": "по худшей метрике: TTM (red)", "metrics": aihub_metrics, "teams": teams, "quarter": "26Q3"},
        {"project": "CMASSORT", "label": "Ассортимент", "overall": "yellow",
         "reason": "по худшей метрике: Predictability (yellow)",
         "metrics": [met("lead_time", "Lead Time истории (дни)", "green", 12.1, "ок"),
                     met("ttm", "Time-to-Market эпика (дни)", "yellow", 68.0, "ок"),
                     met("predictability", "Предсказуемость квартала (%)", "yellow", 62.0, "ок", "заглушка"),
                     met("data_quality", "Чистота данных (%)", "grey", None, "выключена")],
         "teams": [], "quarter": "26Q3"},
        {"project": "OPERSTORE", "label": "Операции · Магазин", "overall": "red",
         "reason": "по худшей метрике: TTM (red)",
         "metrics": [met("lead_time", "Lead Time истории (дни)", "yellow", 18.5, "ок"),
                     met("ttm", "Time-to-Market эпика (дни)", "red", 91.0, "ок", "провизорно"),
                     met("predictability", "Предсказуемость квартала (%)", "green", 81.0, "ок", "заглушка"),
                     met("data_quality", "Чистота данных (%)", "grey", None, "выключена")],
         "teams": [], "quarter": "26Q3"},
    ]
    return {"title": "Dev Pulse — Светофор стримов", "note": "ДЕМО-данные (мок). Реальные — сборка с VPN.",
            "quarter": "26Q3", "generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "streams": streams}


def render(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return TEMPLATE.replace("/*__DATA__*/null", payload)


TEMPLATE = r"""<!doctype html>
<html lang="ru" data-theme="auto">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dev Pulse — Светофор</title>
<style>
  :root{
    --bg:#f4f6f8; --card:#fff; --ink:#161b22; --ink2:#5b636d; --line:#e1e6eb; --line2:#eef1f4;
    --green:#2f9e5f; --green-bg:#e4f4ea; --amber:#c98a1e; --amber-bg:#faf0d9;
    --red:#cf4a3c; --red-bg:#fae2df; --grey:#9aa2ad; --grey-bg:#eceff2;
    --accent:#0e7c86; --shadow:0 1px 2px rgba(20,27,38,.05),0 4px 16px rgba(20,27,38,.06);
  }
  @media (prefers-color-scheme:dark){:root{
    --bg:#0d1117; --card:#161c24; --ink:#e9edf2; --ink2:#9aa3ae; --line:#252d38; --line2:#1d242d;
    --green:#4cc47f; --green-bg:#132a1d; --amber:#d6a54a; --amber-bg:#2c2410;
    --red:#e07364; --red-bg:#2e1815; --grey:#6b7480; --grey-bg:#1c232c; --accent:#34b3bd;
    --shadow:0 1px 2px rgba(0,0,0,.3),0 6px 20px rgba(0,0,0,.35);}}
  :root[data-theme="light"]{color-scheme:light}
  :root[data-theme="dark"]{color-scheme:dark;--bg:#0d1117;--card:#161c24;--ink:#e9edf2;--ink2:#9aa3ae;--line:#252d38;--line2:#1d242d;--green:#4cc47f;--green-bg:#132a1d;--amber:#d6a54a;--amber-bg:#2c2410;--red:#e07364;--red-bg:#2e1815;--grey:#6b7480;--grey-bg:#1c232c;--accent:#34b3bd}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;line-height:1.5}
  .wrap{max-width:1080px;margin:0 auto;padding:28px 20px 60px}
  header{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:6px}
  h1{font-size:24px;font-weight:680;margin:0;letter-spacing:-.02em}
  .meta{font-size:12.5px;color:var(--ink2);text-align:right}
  .note{background:var(--amber-bg);color:var(--ink);border-radius:10px;padding:9px 14px;font-size:13px;margin:14px 0 18px}
  .bar{display:flex;gap:10px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
  input[type=search]{flex:1;min-width:200px;background:var(--card);border:1px solid var(--line);border-radius:9px;padding:9px 13px;color:var(--ink);font-size:14px}
  .legend{display:flex;gap:14px;font-size:12.5px;color:var(--ink2);flex-wrap:wrap}
  .legend b{display:inline-flex;align-items:center;gap:6px;font-weight:400}
  .dot{width:11px;height:11px;border-radius:50%;display:inline-block}
  .d-green{background:var(--green)}.d-amber{background:var(--amber)}.d-red{background:var(--red)}.d-grey{background:var(--grey)}

  table{width:100%;border-collapse:separate;border-spacing:0 8px}
  th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink2);font-weight:600;text-align:left;padding:0 12px 4px}
  th.c,td.c{text-align:center}
  .strip{background:var(--card);box-shadow:var(--shadow);border-radius:12px}
  .row td{padding:14px 12px;border-top:1px solid var(--line2);border-bottom:1px solid var(--line2);cursor:pointer;vertical-align:middle}
  .row td:first-child{border-left:1px solid var(--line2);border-radius:12px 0 0 12px}
  .row td:last-child{border-right:1px solid var(--line2);border-radius:0 12px 12px 0}
  .row:hover td{background:var(--line2)}
  .sname{font-weight:600;font-size:15px;display:flex;align-items:center;gap:9px}
  .chev{color:var(--ink2);font-size:12px;transition:transform .15s;display:inline-block}
  .row.open .chev{transform:rotate(90deg)}
  .skey{font-size:11px;color:var(--ink2);font-variant-numeric:tabular-nums}

  .cell{display:inline-flex;flex-direction:column;align-items:center;gap:2px;min-width:64px;padding:7px 8px;border-radius:9px;font-variant-numeric:tabular-nums}
  .cell .v{font-weight:680;font-size:15px}
  .cell .l{font-size:10px;opacity:.85}
  .green{background:var(--green-bg);color:var(--green)}
  .amber{background:var(--amber-bg);color:var(--amber)}
  .red{background:var(--red-bg);color:var(--red)}
  .grey{background:var(--grey-bg);color:var(--grey)}
  .ov{width:16px;height:16px;border-radius:50%;display:inline-block;flex:none}

  .drill{display:none}
  .drill.show{display:table-row}
  .drill td{padding:0 12px 14px}
  .teams{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px;padding:6px 2px 2px}
  .tcard{background:var(--bg);border:1px solid var(--line);border-radius:11px;padding:13px 15px}
  .tcard .th{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px}
  .tcard .tn{font-weight:640;font-size:14px;display:flex;align-items:center;gap:8px}
  .tcard .sp{font-size:11.5px;color:var(--ink2)}
  .prog{height:7px;border-radius:5px;background:var(--grey-bg);overflow:hidden;margin:8px 0 6px;position:relative}
  .prog>i{display:block;height:100%}
  .prog>.el{position:absolute;top:0;bottom:0;width:2px;background:var(--ink2);opacity:.6}
  .tstat{font-size:12px;color:var(--ink2);display:flex;gap:12px;flex-wrap:wrap;font-variant-numeric:tabular-nums}
  .risk{margin-top:8px;font-size:11.5px;color:var(--ink2)}
  .risk b{color:var(--red);font-weight:600}
  .risk ul{margin:4px 0 0;padding-left:16px}
  .empty{color:var(--ink2);font-size:13px;padding:8px 2px}
  .prov{font-size:10px;color:var(--ink2);margin-left:6px}
  footer{margin-top:26px;font-size:12px;color:var(--ink2);border-top:1px solid var(--line);padding-top:14px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1 id="title">Светофор</h1>
    <div class="meta" id="meta"></div>
  </header>
  <div class="note" id="note"></div>
  <div class="bar">
    <input type="search" id="q" placeholder="Поиск стрима…" autocomplete="off">
    <div class="legend">
      <b><span class="dot d-green"></span>ок</b>
      <b><span class="dot d-amber"></span>внимание</b>
      <b><span class="dot d-red"></span>проблема</b>
      <b><span class="dot d-grey"></span>нет данных</b>
    </div>
  </div>
  <table>
    <thead><tr>
      <th>Стрим</th><th class="c">Итог</th>
      <th class="c">Lead Time</th><th class="c">TTM</th><th class="c">Predict.</th><th class="c">Чистота</th>
    </tr></thead>
    <tbody id="rows"></tbody>
  </table>
  <footer id="foot"></footer>
</div>

<script>
const DATA = /*__DATA__*/null;
const CMAP = {green:"green",yellow:"amber",red:"red",grey:"grey"};
const METRIC_ORDER = ["lead_time","ttm","predictability","data_quality"];

function esc(s){return (s==null?"":String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function cell(m){
  const c=CMAP[m.color]||"grey";
  const v=(m.value==null)?"—":m.value;
  const note=m.note?` · ${m.note}`:"";
  return `<td class="c"><span class="cell ${c}" title="${esc(m.reason)}${esc(note)}"><span class="v">${esc(v)}</span></span></td>`;
}
function teamCard(t){
  const c=CMAP[t.color]||"grey";
  const doneW=Math.min(t.pct_done||0,100), elW=Math.min(t.pct_elapsed||0,100);
  const fill={green:"var(--green)",amber:"var(--amber)",red:"var(--red)",grey:"var(--grey)"}[c];
  let risk="";
  if(t.at_risk>0){
    const items=(t.at_risk_items||[]).map(x=>`<li>${esc(x)}</li>`).join("");
    risk=`<div class="risk"><b>под риском: ${t.at_risk}</b>${items?`<ul>${items}</ul>`:""}</div>`;
  }
  return `<div class="tcard">
    <div class="th"><span class="tn"><span class="ov ${c}" style="width:12px;height:12px"></span>${esc(t.team)}</span>
      <span class="sp">${esc(t.reason||"")}</span></div>
    <div class="sp">${esc(t.sprint||"")} · день ${t.day??"?"}/${t.of??"?"}</div>
    <div class="prog"><i style="width:${doneW}%;background:${fill}"></i><span class="el" style="left:${elW}%"></span></div>
    <div class="tstat"><span>закрыто ${t.done}/${t.total} (${t.pct_done}%)</span><span>в работе ${t.active}</span><span>дефектов ${t.defects}</span></div>
    ${risk}
  </div>`;
}
function render(){
  document.getElementById("title").textContent=DATA.title;
  document.getElementById("meta").innerHTML=`квартал ${esc(DATA.quarter)} · обновлено ${esc(DATA.generated)}`;
  document.getElementById("note").textContent=DATA.note;
  document.getElementById("foot").innerHTML="Пороги провизорные — правятся в <code>config/zones.json</code> без изменения кода. Серое = нет данных или заглушка (напр. Чистота данных). Клик по стриму — детализация по командам.";
  draw("");
}
function draw(filter){
  const rows=document.getElementById("rows"); rows.innerHTML="";
  DATA.streams.filter(s=>!filter||s.label.toLowerCase().includes(filter)||s.project.toLowerCase().includes(filter))
  .forEach((s,i)=>{
    const bym={}; s.metrics.forEach(m=>bym[m.metric]=m);
    const cells=METRIC_ORDER.map(k=>cell(bym[k]||{color:"grey",value:null,reason:"нет"})).join("");
    const ovc=CMAP[s.overall]||"grey";
    const tr=document.createElement("tr"); tr.className="row strip"; tr.dataset.i=i;
    tr.innerHTML=`<td><span class="sname"><span class="chev">▶</span>${esc(s.label)} <span class="skey">${esc(s.project)}</span></span></td>
      <td class="c"><span class="ov ${ovc}" title="${esc(s.reason)}"></span></td>${cells}`;
    const drill=document.createElement("tr"); drill.className="drill"; drill.dataset.for=i;
    const teams=(s.teams&&s.teams.length)?`<div class="teams">${s.teams.map(teamCard).join("")}</div>`
      :`<div class="empty">Нет активных команд со спринтом (или нет данных по этому стриму).</div>`;
    drill.innerHTML=`<td colspan="6">${teams}</td>`;
    tr.onclick=()=>{tr.classList.toggle("open");drill.classList.toggle("show");};
    rows.appendChild(tr); rows.appendChild(drill);
  });
}
document.getElementById("q").addEventListener("input",e=>draw(e.target.value.trim().toLowerCase()));
render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    mock = "--mock" in sys.argv
    data = collect_mock() if mock else collect_real()
    open(OUT, "w", encoding="utf-8").write(render(data))
    print(f"[dashboard] готово: {OUT}  ({'мок' if mock else 'реальные данные'}, стримов: {len(data['streams'])})")
