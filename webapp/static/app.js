"use strict";
const CMAP = { green: "green", yellow: "amber", red: "red", grey: "grey" };
const STAGE_COLORS = {
  "Постановка задачи": "#6b7cff", "Оценка БЦ": "#8aa0b8",
  "Разработка": "#d9822b", "Реализация": "#d9822b",
  "Тестирование": "#8a5cd1", "Внедрение": "#2f9e5f", "Подтверждение эффекта": "#38a3a5"
};
let STREAMS = null;   // лёгкий список из /api/streams
let NAV = 0;

const $ = (id) => document.getElementById(id);
const esc = (s) => (s == null ? "" : String(s)).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
async function api(p) { const r = await fetch(p); if (!r.ok && r.status !== 202) throw new Error("HTTP " + r.status); return r.json(); }

// ── боковая панель ──
async function loadStreams() {
  const d = await api("/api/streams");
  STREAMS = d;
  $("sideSub").textContent = `${d.total || 0} стримов · посчитано ${d.computed || 0}/${d.total || 0} · ${d.quarter || ""}`;
  renderSidebar($("q").value.trim().toLowerCase());
}
function renderSidebar(filter) {
  if (!STREAMS) return;
  const cur = (location.hash.match(/#\/stream\/([^/]+)/) || [])[1];
  const list = $("streamList");
  const rows = STREAMS.streams
    .filter(s => !filter || s.label.toLowerCase().includes(filter) || s.project.toLowerCase().includes(filter))
    .map(s => {
      const c = CMAP[s.overall] || "grey";
      const od = s.overdue || 0;
      return `<div class="sitem ${s.project === cur ? "active" : ""}" onclick="location.hash='#/stream/${esc(s.project)}'">
        <span class="ov ${c}" title="${s.ready ? "" : "детализация считается…"}"></span>
        <span class="nm"><b>${esc(s.label)}</b><span>${esc(s.project)}</span></span>
        <span class="od ${od > 0 ? "warn" : ""}" title="просроченных эпиков">${od}</span>
      </div>`;
    }).join("");
  list.innerHTML = rows || `<div class="loading">ничего не найдено</div>`;
}

// ── общие рендеры ──
function kpi(k, v, s, color) { return `<div class="kpi gl ${color || ""}"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s || ""}</div></div>`; }
function renderStages(det, elId) {
  const st = det.stages_avg || {};
  const work = Object.entries(st).filter(([, v]) => v > 0);
  const p = $(elId);
  if (!work.length) { p.innerHTML = `<h3>Где теряется время</h3><div class="empty">нет данных по стадиям</div>`; return; }
  const total = work.reduce((a, [, v]) => a + v, 0);
  const segs = work.map(([k, v]) => {
    const col = STAGE_COLORS[k] || "#8a93a0", w = Math.max(6, Math.round(100 * v / total));
    const bn = k === det.bottleneck ? "outline:2px solid var(--ink);outline-offset:-2px" : "";
    return `<span style="width:${w}%;background:${col};${bn}" title="${esc(k)}: ${v} дн">${w > 12 ? esc(v) : ""}</span>`;
  }).join("");
  const leg = work.map(([k, v]) => `<b><span class="sq" style="background:${STAGE_COLORS[k] || "#8a93a0"}"></span>${esc(k)} — ${v} дн${k === det.bottleneck ? " ⬅ узкое место" : ""}</b>`).join("");
  p.innerHTML = `<h3>Где теряется время <span class="h-sub">среднее по стадиям, закрытые эпики</span></h3><div class="stagebar">${segs}</div><div class="stagelegend">${leg}</div>`;
}
function renderSignals(det, elId) {
  const s = det.signals || { total: 0, by_type: {}, findings: [] };
  const names = { overdue_epic: "просроченные эпики", removed_kub_label: "снятые метки КУБ", undecomposed_epic: "недекомпозированные" };
  const chips = Object.entries(s.by_type || {}).map(([k, v]) => `<span class="sig ${v > 0 ? "red" : "grey"}">${esc(names[k] || k)}: ${v}</span>`).join("") || `<span class="sig grey">сигналов нет</span>`;
  const items = (s.findings || []).map(f => `<li><span class="sv ${esc(f.severity)}">${f.severity === "high" ? "●" : "○"}</span><span><b>${esc(f.key)}</b> — ${esc(f.detail)}</span></li>`).join("");
  $(elId).innerHTML = `<h3>Сигналы <span class="h-sub">всего ${s.total}</span></h3><div class="sigrow">${chips}</div>${items ? `<ul class="findings">${items}</ul>` : ""}`;
}
function teamCard(t) {
  const c = CMAP[t.color] || "grey";
  const fill = { green: "var(--green)", amber: "var(--amber)", red: "var(--red)", grey: "var(--grey)" }[c];
  const doneW = Math.min(t.pct_done || 0, 100), elW = Math.min(t.pct_elapsed || 0, 100);
  return `<div class="tcard" onclick="location.hash='#/team/${esc(t.project)}/${encodeURIComponent(t.team)}'">
    <div class="tt"><span class="tn"><span class="ov ${c}" style="width:12px;height:12px"></span>${esc(t.team)}</span><span class="rs">${esc(t.reason || "")}</span></div>
    <div class="rs">${esc(t.sprint || "")} · день ${t.day ?? "?"}/${t.of ?? "?"}</div>
    <div class="prog"><i style="width:${doneW}%;background:${fill}"></i><span class="el" style="left:${elW}%"></span></div>
    <div class="tstat"><span>закрыто ${t.done}/${t.total}</span><span>в работе ${t.active}</span><span>риск ${t.at_risk}</span><span>деф ${t.defects}</span></div>
  </div>`;
}

// ── виды ──
function viewHome() {
  crumbs([{ t: "Обзор" }]);
  $("foot").innerHTML = "Пороги — в <code>config/zones.json</code> без кода. Слева выбери стрим. Данные считаются в фоне; серый кружок = детализация ещё считается.";
  if (!STREAMS) { $("app").innerHTML = `<div class="loading">Загрузка…</div>`; return; }
  const s = STREAMS.streams;
  const cnt = c => s.filter(x => x.overall === c).length;
  const top = s.filter(x => x.overdue > 0).slice(0, 12);
  $("app").innerHTML = `
    <h2 style="margin:2px 0 14px;font-size:20px">Обзор портфеля <span class="h-sub">${s.length} стримов, квартал ${esc(STREAMS.quarter || "")}</span></h2>
    <div class="grid">
      ${kpi("🔴 Проблемные", cnt("red"), "стримов красные", "red")}
      ${kpi("🟡 Внимание", cnt("yellow"), "жёлтые", "amber")}
      ${kpi("🟢 В норме", cnt("green"), "зелёные", "green")}
      ${kpi("⚪ Считается", cnt("grey"), "детализация в фоне", "")}
    </div>
    <div class="panel"><h3>Топ по просрочкам <span class="h-sub">клик — детализация</span></h3>
      <table class="tbl"><thead><tr><th class="l">Стрим</th><th>Просрочено</th><th>WIP</th><th>Эпиков</th></tr></thead><tbody>
      ${top.map(x => `<tr class="srow" onclick="location.hash='#/stream/${esc(x.project)}'">
        <td class="l"><span class="sname"><span class="ov ${CMAP[x.overall] || "grey"}"></span>${esc(x.label)} <span class="skey">${esc(x.project)}</span></span></td>
        <td><span class="num warn">${x.overdue}</span></td><td><span class="num">${x.wip}</span></td><td><span class="num">${x.epics}</span></td></tr>`).join("")}
      </tbody></table></div>`;
}

async function viewStream(project) {
  const my = ++NAV;
  const lite = STREAMS && STREAMS.streams.find(s => s.project === project);
  crumbs([{ t: "Обзор", h: "#/" }, { t: (lite && lite.label) || project }]);
  renderSidebar($("q").value.trim().toLowerCase());
  $("app").innerHTML = `<div class="loading">Открываю ${esc(project)}…</div>`;
  const row = await api("/api/stream/" + encodeURIComponent(project));
  if (my !== NAV) return;
  if (row.computing) {
    const l = row.light || {};
    $("app").innerHTML = `<div class="grid">
      ${kpi("Просрочено", l.overdue ?? "—", "эпиков", (l.overdue > 0 ? "red" : ""))}
      ${kpi("WIP эпиков", l.wip ?? "—", "в работе", "")}
      ${kpi("Эпиков", l.epics ?? "—", "всего", "")}</div>
      <div class="panel"><div class="empty">Полная детализация (LT, TTM, стадии, сигналы, команды) считается в фоне — появится в течение минуты. Обновляю автоматически…</div></div>`;
    setTimeout(() => { if (my === NAV) viewStream(project); }, 8000);
    return;
  }
  renderStreamFull(row);
}

function renderStreamFull(row) {
  const bym = row.metrics || {}, ex = row.extra || {};
  const mk = (mo, k) => mo ? kpi(k, mo.value == null ? "—" : mo.value, esc((mo.reason || "").split(" при ")[0] || ""), CMAP[mo.color]) : kpi(k, "—", "нет данных", "grey");
  const kpis = [
    kpi("Итог", "", esc((row.reason || "").replace(/\s*\((?:green|yellow|red|grey)\)\s*$/, "")), CMAP[row.overall]),
    mk(bym.lead_time, "Lead Time (дни)"), mk(bym.ttm, "TTM (дни)"),
    kpi("WIP эпиков", ex.wip ?? "—", "в активных статусах"),
    kpi("Закрыто эпиков", ex.closed_epics ?? "—", "всего Done"),
    kpi("Просрочено", ex.overdue ?? "—", "дата в прошлом", (ex.overdue > 0 ? "red" : "green")),
  ].join("");
  const teams = (row.teams || []).map(teamCard).join("") || `<div class="empty">Нет активных команд со спринтом.</div>`;
  $("app").innerHTML = `
    <div class="grid">${kpis}</div>
    <div class="panel" id="stagePanel"></div>
    <div class="panel" id="sigPanel"></div>
    <div class="panel"><h3>Команды стрима <span class="h-sub">клик — детализация и рекомендации</span></h3><div class="teams">${teams}</div></div>`;
  renderStages(row.detail || {}, "stagePanel");
  renderSignals(row.detail || {}, "sigPanel");
}

async function viewTeam(project, team) {
  const my = ++NAV;
  crumbs([{ t: "Обзор", h: "#/" }, { t: project, h: "#/stream/" + project }, { t: team }]);
  const t = await api(`/api/team/${encodeURIComponent(project)}/${encodeURIComponent(team)}`);
  if (my !== NAV) return;
  if (!t.found) { $("app").innerHTML = `<div class="panel"><div class="empty">${esc(t.reason || t.error || "нет данных")}</div></div>`; return; }
  const c = CMAP[t.color] || "grey", fill = { green: "var(--green)", amber: "var(--amber)", red: "var(--red)", grey: "var(--grey)" }[c];
  const recs = (t.recommendations || []).map(r => `<li class="${esc(r.severity)}"><div class="sg">${esc(r.signal)}</div><div class="ad">${esc(r.advice)}</div></li>`).join("") || `<div class="empty">Острых сигналов нет.</div>`;
  const risk = (t.at_risk_items || []).map(x => `<li>${esc(x)}</li>`).join("");
  $("app").innerHTML = `
    <div class="grid">
      <div class="kpi gl ${c}"><div class="k">Спринт</div><div class="v" style="font-size:15px">${esc(t.sprint)}</div><div class="s">${esc(t.reason)}</div></div>
      <div class="kpi"><div class="k">Прогресс</div><div class="v">${t.day}/${t.of}</div><div class="s">${t.pct_elapsed}% времени</div></div>
      <div class="kpi"><div class="k">Закрыто</div><div class="v">${t.done}/${t.total}</div><div class="s">${t.pct_done}%</div></div>
      <div class="kpi"><div class="k">В работе</div><div class="v">${t.active}</div><div class="s">дефектов ${t.defects}</div></div>
      <div class="kpi gl ${t.at_risk > 0 ? "red" : "green"}"><div class="k">Под риском</div><div class="v">${t.at_risk}</div><div class="s">не закроются</div></div>
    </div>
    <div class="panel"><h3>Прогресс спринта</h3><div class="prog" style="height:12px"><i style="width:${Math.min(t.pct_done, 100)}%;background:${fill}"></i><span class="el" style="left:${Math.min(t.pct_elapsed, 100)}%"></span></div>
      <div class="tstat" style="margin-top:8px"><span>закрыто ${t.pct_done}%</span><span>прошло времени ${t.pct_elapsed}%</span></div></div>
    <div class="panel"><h3>Что стоит сделать <span class="h-sub">рекомендации по данным команды</span></h3><ul class="recs">${recs}</ul></div>
    ${risk ? `<div class="panel"><h3>Под риском не закрыться</h3><ul class="risk">${risk}</ul></div>` : ""}`;
}

function crumbs(items) {
  $("crumbs").innerHTML = items.map((it, i) => {
    const sep = i > 0 ? '<span class="sep">›</span>' : "";
    return sep + (i === items.length - 1 ? `<span class="cur">${esc(it.t)}</span>` : `<a href="${it.h}">${esc(it.t)}</a>`);
  }).join(" ");
}

async function route() {
  NAV++;
  const h = location.hash || "#/";
  try {
    const mt = h.match(/^#\/team\/([^/]+)\/(.+)$/), ms = h.match(/^#\/stream\/(.+)$/);
    if (mt) await viewTeam(decodeURIComponent(mt[1]), decodeURIComponent(mt[2]));
    else if (ms) await viewStream(decodeURIComponent(ms[1]));
    else viewHome();
  } catch (e) {
    $("app").innerHTML = `<div class="panel"><div class="empty">Ошибка: ${esc(e.message)}</div></div>`;
  }
}

$("q").addEventListener("input", () => renderSidebar($("q").value.trim().toLowerCase()));
window.addEventListener("hashchange", route);
(async () => { await loadStreams(); route(); setInterval(loadStreams, 20000); })();
