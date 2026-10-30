"use strict";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const res = await fetch(path, { credentials: "same-origin", ...opts });
  let data = null;
  try { data = await res.json(); } catch (_) { /* empty body */ }
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    state.user = null;
    if (!location.hash.startsWith("#/login")) { state.afterLogin = location.hash; location.hash = "#/login"; }
  }
  if (!res.ok) throw new Error((data && data.detail) || `Request failed (${res.status})`);
  return data;
}
const postJSON = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

const VERDICT = {
  STRONG_HIRE: ["Strong hire", "good"], HIRE: ["Hire", "good"], LEAN_HIRE: ["Lean hire", "mid"],
  LEAN_NO: ["Lean no hire", "low"], NO_HIRE: ["No hire", "low"],
};
const TOPIC_STATUS = { MISSED: "Missed", PARTIAL: "Partly covered", NOT_REACHED: "Not reached before time ran out", SKIPPED: "Skipped" };
const VIEWS = ["auth", "dashboard", "setup", "interview", "report"];

const state = { user: null, packs: [], session: null, mode: "voice", waiting: false, speaking: false,
                timer: null, afterLogin: null, lastSetup: null, profile: null, reportFor: null,
                hold: false, confirming: false, testAccount: null };

const fmtDate = (iso) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
function fmtMinutes(m) {
  if (m < 1) return "less than a minute";
  if (m < 60) return `${m} minute${m === 1 ? "" : "s"}`;
  const h = Math.floor(m / 60), r = m % 60;
  return r ? `${h} h ${r} min` : `${h} h`;
}

/* ---------------- Views & router ---------------- */
function showView(name) {
  for (const v of VIEWS) $(v).hidden = v !== name;
  $("endBtn").hidden = name !== "interview";
  $("mainNav").hidden = !state.user || name === "interview";
  $("logoutBtn").hidden = !state.user || name === "interview";
  $("userName").textContent = state.user && name !== "interview" ? state.user.name : "";
  if (name !== "interview") {
    clearInterval(state.timer); $("timer").textContent = ""; $("roundRail").innerHTML = "";
    stopSpeaking(); if (listening) stopListening();
    state.hold = false; state.confirming = false;
  }
  if (name !== "report") state.reportFor = null;
  for (const a of document.querySelectorAll("[data-nav]")) a.classList.toggle("active", a.dataset.nav === name || (name === "setup" && a.dataset.nav === "new"));
  window.scrollTo(0, 0);
}

async function route() {
  const [, page = "", arg] = (location.hash.slice(1) || "/").split("/");
  if (!state.user) {
    if (page !== "login" && page !== "signup") { state.afterLogin = location.hash || "#/dashboard"; location.replace("#/login"); return; }
    renderAuth(page);
    return;
  }
  try {
    switch (page) {
      case "login": case "signup": location.replace(state.afterLogin || "#/dashboard"); state.afterLogin = null; break;
      case "new": await showSetup(); break;
      case "interview": await openInterview(arg); break;
      case "report": await showReport(arg); break;
      default: await showDashboard();
    }
  } catch (e) {
    if (!state.user) return; // 401 already redirected
    showView("dashboard");
    $("dashBody").innerHTML = `<p class="error">${esc(e.message)}</p><p><a href="#/dashboard">Back to your dashboard</a></p>`;
  }
}

/* ---------------- Auth ---------------- */
function renderAuth(page) {
  const signup = page === "signup";
  showView("auth");
  $("authTitle").textContent = signup ? "Create your account." : "Sign in to keep your progress.";
  $("nameRow").hidden = !signup;
  $("authSubmit").textContent = signup ? "Create account" : "Sign in";
  $("authPassword").autocomplete = signup ? "new-password" : "current-password";
  $("authSwitchText").textContent = signup ? "Already have an account?" : "New here?";
  $("authSwitch").textContent = signup ? "Sign in" : "Create an account";
  $("authSwitch").href = signup ? "#/login" : "#/signup";
  $("authError").textContent = "";
  $("authForm").dataset.mode = signup ? "signup" : "login";
  const hint = $("authHint");
  const test = !signup && state.testAccount;
  hint.hidden = !test;
  hint.textContent = test
    ? `Testing only. This account lives in memory and is cleared when the app stops. Email ${state.testAccount.email}, password ${state.testAccount.password}.`
    : "";
  if (test && !$("authEmail").value) {
    $("authEmail").value = state.testAccount.email;
    $("authPassword").value = state.testAccount.password;
  }
}

async function onAuthSubmit(ev) {
  ev.preventDefault();
  const signup = $("authForm").dataset.mode === "signup";
  const body = { email: $("authEmail").value, password: $("authPassword").value };
  if (signup) body.name = $("authName").value;
  $("authSubmit").disabled = true;
  $("authError").textContent = "";
  try {
    state.user = await postJSON(signup ? "/api/auth/signup" : "/api/auth/login", body);
    $("authPassword").value = "";
    const next = state.afterLogin && !/#\/(login|signup)/.test(state.afterLogin) ? state.afterLogin : "#/dashboard";
    state.afterLogin = null;
    if (location.hash === next) route(); else location.hash = next;
  } catch (e) {
    $("authError").textContent = e.message;
  } finally {
    $("authSubmit").disabled = false;
  }
}

async function logout() {
  try { await api("/api/auth/logout", { method: "POST" }); } catch (_) { /* already signed out */ }
  state.user = null; state.lastSetup = null; state.profile = null;
  location.hash = "#/login";
}

/* ---------------- Dashboard ---------------- */
async function showDashboard() {
  showView("dashboard");
  $("dashBody").innerHTML = `<p class="status">Loading your progress...</p>`;
  const d = await api(`/api/me/dashboard?tz_offset=${new Date().getTimezoneOffset()}`);
  state.lastSetup = d.last_setup;
  renderDashboard(d);
}

function greeting() {
  const h = new Date().getHours();
  const part = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  return `${part}, ${esc(state.user.name.split(" ")[0])}.`;
}

function trendSvg(points, width) {
  // Draw at the real container width so labels stay readable on phones.
  const W = Math.round(Math.max(300, Math.min(900, width || 640))), H = W < 480 ? 200 : 230;
  const L = 30, R = 64, T = 12, B = 30, n = points.length;
  const x = (i) => (n === 1 ? L + (W - L - R) / 2 : L + (i * (W - L - R)) / (n - 1));
  const y = (v) => T + ((5 - v) / 4) * (H - T - B);
  const out = [`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Interview scores over time, out of 5">`];
  for (let v = 1; v <= 5; v++) out.push(`<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${L - 10}" y="${y(v) + 4}" text-anchor="end">${v}</text>`);
  out.push(`<line class="bar-line" x1="${L}" x2="${W - R}" y1="${y(3.6)}" y2="${y(3.6)}"/><text class="bar-label" x="${W - R + 8}" y="${y(3.6) + 4}">Hire bar</text>`);
  const coords = points.map((p, i) => `${x(i)},${y(p.overall)}`);
  if (n > 1) {
    out.push(`<polygon class="area" points="${x(0)},${H - B} ${coords.join(" ")} ${x(n - 1)},${H - B}"/>`);
    out.push(`<polyline class="line" points="${coords.join(" ")}"/>`);
  }
  points.forEach((p, i) => {
    const [label, tone] = VERDICT[p.verdict] || ["", "mid"];
    out.push(`<a href="#/report/${esc(p.session_id)}" aria-label="${esc(fmtDate(p.date))}: ${p.overall.toFixed(1)}, ${esc(label)}"><title>${esc(fmtDate(p.date))}, ${esc(p.role)}: ${p.overall.toFixed(1)} (${esc(label)})</title><circle class="pt-${tone}" cx="${x(i)}" cy="${y(p.overall)}" r="7"/></a>`);
  });
  if (n) {
    out.push(`<text class="axis" x="${x(0)}" y="${H - 6}" text-anchor="${n === 1 ? "middle" : "start"}">${esc(fmtDate(points[0].date))}</text>`);
    if (n > 1) out.push(`<text class="axis" x="${x(n - 1)}" y="${H - 6}" text-anchor="end">${esc(fmtDate(points[n - 1].date))}</text>`);
  }
  out.push(`</svg>`);
  return out.join("");
}

function titleCase(name) {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function verdictPill(verdict, fallback) {
  const [label, tone] = VERDICT[verdict] || [fallback, ""];
  return `<span class="pill ${tone}">${esc(label)}</span>`;
}

function renderDashboard(d) {
  const s = d.stats, h = [];
  const start = s.interviews ? `<a class="primary as-button" href="#/new">New interview</a>` : "";
  h.push(`<header class="dash-head"><div><p class="kicker">Progress</p><h1>${greeting()}</h1><p class="dash-sub">Hire bar is 3.6 out of 5. Scores, gaps and practice time stay on this page.</p></div>${start}</header>`);
  if (s.interviews === 0) {
    h.push(`<div class="empty dash-empty"><p class="kicker">No interviews yet</p><h2>Your first mock builds this page.</h2><p>One round is enough. After it, you will see a score, the topics you missed, and a place to practise them.</p><a class="primary as-button" href="#/new">Start your first interview</a></div>`);
    $("dashBody").innerHTML = h.join("");
    return;
  }

  const recentN = Math.min(5, d.trend.length);
  h.push(`<section class="kpi-row" aria-label="Practice summary">`);
  h.push(`<article class="kpi"><span class="kpi-label">Interviews</span><strong class="kpi-value">${s.interviews}</strong><span class="kpi-note">${s.completed} completed</span></article>`);
  h.push(`<article class="kpi"><span class="kpi-label">Practice time</span><strong class="kpi-value">${fmtMinutes(s.practice_minutes)}</strong><span class="kpi-note">Across every round</span></article>`);
  h.push(`<article class="kpi"><span class="kpi-label">Streak</span><strong class="kpi-value">${s.streak_days}<span class="kpi-unit"> day${s.streak_days === 1 ? "" : "s"}</span></strong><span class="kpi-note">${s.streak_days > 0 ? "Keep it going today" : "Practise today to start one"}</span></article>`);
  h.push(`<article class="kpi"><span class="kpi-label">Recent average</span><strong class="kpi-value">${s.avg_recent != null ? s.avg_recent.toFixed(1) : "–"}</strong><span class="kpi-note">${s.avg_recent != null ? `Last ${recentN} scored${s.best != null ? ` · best ${s.best.toFixed(1)}` : ""}` : "Waiting for a scored report"}</span></article>`);
  h.push(`</section>`);

  if (d.in_progress.length) {
    h.push(`<section class="dash-card"><div class="card-head"><h2>In progress</h2><span class="tag">Pick up the round you left open.</span></div><div class="resume-list">`);
    for (const p of d.in_progress.slice(0, 3)) {
      const focus = p.focus === "weak" ? `<span class="pill">Weak topics</span>` : "";
      h.push(`<div class="resume-item"><div class="resume-copy"><strong>${esc(p.role)}</strong><span>${esc(p.level)} · Round ${p.rounds_done + 1} of ${p.rounds_total} · ${esc(p.current_round)}</span><span class="tag">Started ${esc(fmtDate(p.date))}</span>${focus}</div><a class="primary as-button" href="#/interview/${esc(p.session_id)}">Resume</a></div>`);
    }
    h.push(`</div></section>`);
  }

  if (d.trend.length) {
    const chartWidth = Math.max(320, Math.min(860, ($("dashBody").clientWidth || 860) - 64));
    h.push(`<section class="dash-card trend"><div class="card-head"><div><h2>Score over time</h2><p class="card-note">Each point opens that report. The dashed line is the hire bar.</p></div></div>${trendSvg(d.trend, chartWidth)}</section>`);
  }

  h.push(`<div class="dash-grid">`);
  h.push(`<section class="dash-card"><div class="card-head"><h2>Skills</h2><span class="tag">Weakest first</span></div>`);
  if (d.competencies.length) {
    h.push(`<div class="skill-list">`);
    for (const c of d.competencies.slice(0, 8)) {
      let delta = `${c.samples} score${c.samples === 1 ? "" : "s"}`, cls = "";
      if (c.change != null && Math.abs(c.change) >= 0.25) { delta = `${c.change > 0 ? "+" : ""}${c.change.toFixed(1)} recent`; cls = c.change > 0 ? "up" : "down"; }
      h.push(`<div class="skill"><div class="skill-top"><span class="name">${esc(titleCase(c.name))}</span><span class="delta ${cls}">${c.avg.toFixed(1)} <span>${delta}</span></span></div><span class="bar" aria-hidden="true"><b style="width:${(c.avg / 5) * 100}%"></b></span></div>`);
    }
    h.push(`</div>`);
  } else h.push(`<p class="card-note">Skills appear once a report is ready.</p>`);
  h.push(`</section>`);

  h.push(`<section class="dash-card"><div class="card-head"><h2>Weak topics</h2><span class="tag">What to practise next</span></div>`);
  if (d.weak_topics.length) {
    const groups = {};
    for (const w of d.weak_topics) (groups[w.role_pack] ||= { role: w.role, items: [] }).items.push(w);
    for (const [slug, g] of Object.entries(groups)) {
      h.push(`<div class="weak-group"><h3>${esc(g.role)}</h3><ul class="weak-list">`);
      for (const w of g.items) h.push(`<li><span>${esc(w.topic)}</span><span class="count">${w.times_missed}×</span></li>`);
      h.push(`</ul><button class="ghost focus-btn" data-focus="${esc(slug)}">Practise these topics</button></div>`);
    }
  } else h.push(`<p class="card-note">Topics you miss or only partly cover will be listed here.</p>`);
  h.push(`</section></div>`);

  h.push(`<section class="dash-card history-wrap"><div class="card-head"><h2>History</h2><span class="tag">${d.history.length} session${d.history.length === 1 ? "" : "s"}</span></div><table class="history"><thead><tr><th>Date</th><th>Interview</th><th>Result</th><th class="num">Score</th></tr></thead><tbody>`);
  for (const r of d.history) {
    const fallback = r.status === "COMPLETED" ? (r.report_status === "FAILED" ? "Scoring failed" : "Scoring") : "In progress";
    const href = r.status === "COMPLETED" ? `#/report/${r.session_id}` : `#/interview/${r.session_id}`;
    const focus = r.focus === "weak" ? `<span class="pill">Weak topics</span>` : "";
    h.push(`<tr><td class="when">${esc(fmtDate(r.date))}</td><td><a href="${href}">${esc(r.role)}</a><span class="tag">${esc(r.level)}${r.rounds.length ? ` · ${esc(r.rounds.join(", "))}` : ""}</span>${focus}</td><td>${verdictPill(r.verdict, fallback)}</td><td class="num">${r.overall != null ? r.overall.toFixed(1) : "–"}</td></tr>`);
  }
  h.push(`</tbody></table></section>`);
  $("dashBody").innerHTML = h.join("");
  for (const b of document.querySelectorAll("[data-focus]")) b.addEventListener("click", () => startFocus(b.dataset.focus, b));
}

async function startFocus(rolePack, btn) {
  btn.disabled = true;
  try {
    const pack = state.packs.find((p) => p.slug === rolePack);
    const level = state.lastSetup?.role_pack === rolePack ? state.lastSetup.level
      : (pack.levels.find((l) => l.key === "L2") || pack.levels[0]).key;
    const profile = await api("/api/me/profile");
    const s = await postJSON("/api/sessions", { role_pack: rolePack, level, focus_weak: true,
      mode: SR ? "voice" : "chat", profile_id: profile?.id || null });
    location.hash = `#/interview/${s.id}`;
  } catch (e) {
    btn.disabled = false;
    btn.insertAdjacentHTML("afterend", `<p class="error">${esc(e.message)}</p>`);
  }
}

/* ---------------- Setup ---------------- */
function chip(name, value, label, type = "radio", checked = false) {
  return `<label class="chip"><input type="${type}" name="${name}" value="${esc(value)}" ${checked ? "checked" : ""}><span>${esc(label)}</span></label>`;
}
const selected = (name) => document.querySelector(`input[name="${name}"]:checked`)?.value;
const currentPack = () => state.packs.find((p) => p.slug === selected("role"));
const currentLevel = () => currentPack()?.levels.find((l) => l.key === selected("level"));

function renderRoles(pref) {
  const first = state.packs.find((p) => p.slug === pref?.role_pack) || state.packs[0];
  $("roleChoices").innerHTML = state.packs.map((p) => chip("role", p.slug, p.title, "radio", p === first)).join("");
  renderLevels(pref?.role_pack === first.slug ? pref.level : null);
}
function renderLevels(prefLevel) {
  const pack = currentPack();
  const levels = pack.levels;
  const def = levels.find((l) => l.key === prefLevel) || levels.find((l) => l.key === "L2") || levels[0];
  $("levelChoices").innerHTML = levels.map((l) => chip("level", l.key, l.label, "radio", l === def)).join("");
  $("stackField").hidden = pack.stacks.length === 0;
  $("stackChoices").innerHTML = pack.stacks.map((s) => chip("stack", s.slug, s.label, "checkbox")).join("");
  renderRounds();
}
function renderRounds() {
  const lvl = currentLevel();
  $("roundChoices").innerHTML = lvl.rounds.map((r) =>
    `<label><input type="checkbox" name="round" value="${r.index}" checked><span>${esc(r.title)}</span><span class="mins">${r.duration_min} min</span></label>`).join("");
}

async function showSetup() {
  showView("setup");
  $("setupError").textContent = "";
  if (!state.lastSetup) {
    try { state.lastSetup = (await api(`/api/me/dashboard?tz_offset=${new Date().getTimezoneOffset()}`)).last_setup; } catch (_) { /* optional */ }
  }
  renderRoles(state.lastSetup);
  $("resumeFile").value = ""; $("resumeFileLabel").textContent = "Upload PDF, DOCX or TXT"; $("resumeText").value = "";
  state.profile = await api("/api/me/profile");
  $("savedResume").hidden = !state.profile;
  if (state.profile) {
    const name = state.profile.filename ? `${state.profile.filename}, ` : "";
    $("savedResumeText").textContent = `Use my saved resume (${name}added ${fmtDate(state.profile.created_at)}). Upload or paste a new one to replace it.`;
    $("useSaved").checked = true;
  }
}

async function onStart(ev) {
  ev.preventDefault();
  $("setupError").textContent = "";
  const rounds = [...document.querySelectorAll('input[name="round"]:checked')].map((i) => Number(i.value));
  if (!rounds.length) { $("setupError").textContent = "Pick at least one round."; return; }
  const btn = $("startBtn");
  btn.disabled = true;
  try {
    let profileId = null;
    const file = $("resumeFile").files[0];
    const text = $("resumeText").value.trim();
    if (file || text) {
      $("setupStatus").textContent = "Reading your resume...";
      const fd = new FormData();
      if (file) fd.append("file", file);
      if (text) fd.append("text", text);
      profileId = (await api("/api/profiles", { method: "POST", body: fd })).id;
    } else if (state.profile && $("useSaved").checked) {
      profileId = state.profile.id;
    }
    $("setupStatus").textContent = "Planning your rounds...";
    const s = await postJSON("/api/sessions", {
      profile_id: profileId, role_pack: selected("role"), level: selected("level"),
      stack: [...document.querySelectorAll('input[name="stack"]:checked')].map((i) => i.value),
      rounds, mode: selected("mode"),
    });
    state.lastSetup = { role_pack: selected("role"), level: selected("level") };
    location.hash = `#/interview/${s.id}`;
  } catch (e) {
    $("setupError").textContent = e.message;
  } finally {
    btn.disabled = false;
    $("setupStatus").textContent = "";
  }
}

/* ---------------- Interview ---------------- */
async function openInterview(id) {
  const s = await api(`/api/sessions/${id}`);
  if (s.status === "COMPLETED") { location.replace(`#/report/${id}`); return; }
  showInterview(s);
  if (s.status === "PLANNED") {
    setInterviewer("thinking");
    try { await afterResponse(await postJSON(`/api/sessions/${id}/start`)); }
    catch (e) { $("turnError").textContent = e.message; setInterviewer("idle"); }
  } else setInterviewer("idle");
}

function showInterview(view) {
  state.mode = view.mode;
  state.session = null;
  showView("interview");
  $("turnError").textContent = "";
  $("answer").value = "";
  $("workpadText").value = "";
  $("interviewerName").textContent = view.interviewer;
  $("micBtn").disabled = !SR;
  $("voiceControls").hidden = !SR;
  $("handsFree").checked = prefs.handsFree;
  $("silenceSel").value = String(prefs.silenceMs);
  $("heard").textContent = "";
  applyView(view);
}

function applyView(view) {
  const prevRound = state.session?.id === view.id ? state.session.current_round : undefined;
  state.session = view;
  renderRail();
  renderTranscript();
  const rnd = view.rounds.find((r) => r.seq === view.current_round);
  const tools = rnd?.tools || [];
  const pad = tools.includes("editor") ? "Code editor" : tools.includes("notes") ? "Design notes" : null;
  $("workpad").hidden = !pad;
  $("interview").classList.toggle("with-pad", !!pad);
  if (pad) $("workpadLabel").textContent = pad;
  if (prevRound !== undefined && prevRound !== view.current_round) $("workpadText").value = "";
  startTimer(rnd);
}

function renderRail() {
  const s = state.session;
  $("roundRail").innerHTML = s.rounds.map((r) => {
    const cls = r.seq === s.current_round && s.status !== "COMPLETED" ? "current" : ["COMPLETED", "ENDED_EARLY", "SKIPPED"].includes(r.status) ? "done" : "";
    return `<span class="step ${cls}">${r.seq}. ${esc(r.title)}</span>`;
  }).join("");
}

function renderTranscript() {
  const s = state.session;
  let lastRound = null;
  const items = [];
  for (const t of s.transcript) {
    if (t.round_seq !== lastRound) {
      const r = s.rounds.find((x) => x.seq === t.round_seq);
      items.push(`<li class="divider">Round ${r.seq}: ${esc(r.title)}</li>`);
      lastRound = t.round_seq;
    }
    if (t.speaker === "INTERVIEWER") items.push(`<li class="interviewer"><span class="who">${esc(s.interviewer)}</span><p>${esc(t.text)}</p></li>`);
    else items.push(`<li class="candidate"><span class="who">You</span><p>${esc(t.text)}</p></li>`);
  }
  $("transcript").innerHTML = items.join("");
  $("transcript").scrollTop = $("transcript").scrollHeight;
}

function startTimer(rnd) {
  clearInterval(state.timer);
  const el = $("timer");
  if (!rnd || !state.session.round_started_at) { el.textContent = ""; return; }
  const start = new Date(state.session.round_started_at).getTime();
  const tick = () => {
    const sec = Math.max(0, Math.floor((Date.now() - start) / 1000));
    const mm = String(Math.floor(sec / 60)).padStart(2, "0"), ss = String(sec % 60).padStart(2, "0");
    el.textContent = `${mm}:${ss} of ${rnd.duration_min}:00`;
    el.classList.toggle("over", sec > rnd.duration_min * 60);
  };
  tick();
  state.timer = setInterval(tick, 1000);
}

const STATE_TEXT = { idle: "Waiting for your answer", thinking: "Thinking...", speaking: "Speaking", listening: "Listening to you" };
function setInterviewer(kind) {
  const stage = $("interview");
  stage.classList.remove("idle", "thinking", "speaking", "listening");
  stage.classList.add(kind);
  $("interviewerState").textContent = STATE_TEXT[kind];
}

/* ---------------- Voice out (speech synthesis) ---------------- */
let voice = null;
function pickVoice() {
  if (!window.speechSynthesis) return;
  const vs = speechSynthesis.getVoices();
  voice = vs.find((v) => v.lang === "en-IN") || vs.find((v) => /en-GB/.test(v.lang) && /Google|Natural/.test(v.name))
    || vs.find((v) => /^en/.test(v.lang) && /Google|Natural/.test(v.name)) || vs.find((v) => /^en/.test(v.lang)) || null;
}
if (window.speechSynthesis) { pickVoice(); speechSynthesis.onvoiceschanged = pickVoice; }

function speak(texts) {
  return new Promise((resolve) => {
    if (state.mode !== "voice" || !window.speechSynthesis || !texts.length) { resolve(); return; }
    speechSynthesis.cancel();
    // Chrome cuts off long utterances, so speak sentence by sentence.
    const parts = texts.join(" ").split(/(?<=[.?!])\s+/).filter(Boolean);
    let i = 0;
    state.speaking = true;
    setInterviewer("speaking");
    const next = () => {
      if (!state.speaking || i >= parts.length) { state.speaking = false; resolve(); return; }
      const u = new SpeechSynthesisUtterance(parts[i++]);
      if (voice) u.voice = voice;
      u.rate = prefs.rate;
      u.onend = next;
      u.onerror = next;
      speechSynthesis.speak(u);
    };
    next();
  });
}
function stopSpeaking() {
  if (state.speaking && window.speechSynthesis) { state.speaking = false; speechSynthesis.cancel(); }
}

/* ---------------- Voice preferences ---------------- */
const VC = window.VoiceCommands;
const prefs = (() => {
  const d = { handsFree: true, silenceMs: 3000, rate: 1.02 };
  try { return { ...d, ...JSON.parse(localStorage.getItem("mockiq.voice") || "{}") }; } catch (_) { return d; }
})();
function savePrefs() { try { localStorage.setItem("mockiq.voice", JSON.stringify(prefs)); } catch (_) { /* private mode */ } }

/* ---------------- Voice in (speech recognition + commands) ---------------- */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let rec = null, listening = false, base = "", lastSpeechAt = 0, heardTimer = null, confirmTimer = null;

function showHeard(msg) {
  $("heard").textContent = msg;
  clearTimeout(heardTimer);
  heardTimer = setTimeout(() => { $("heard").textContent = ""; }, 4000);
}

function startListening() {
  if (!SR || listening) return;
  stopSpeaking(); // barge-in: tapping the mic while the interviewer talks stops it
  base = $("answer").value ? $("answer").value.trimEnd() + " " : "";
  lastSpeechAt = Date.now();
  rec = new SR();
  rec.lang = "en-IN";
  rec.continuous = true;
  rec.interimResults = true;
  rec.onresult = (e) => {
    lastSpeechAt = Date.now();
    state.hold = false; // speaking again ends a "give me a minute" pause
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = e.results[i][0].transcript;
      if (!e.results[i].isFinal) { interim += t; continue; }
      const seg = t.trim();
      if (!seg) continue;
      if (state.confirming) { setTimeout(() => onConfirmReply(seg)); continue; }
      const cmd = VC.detect(seg, { answerEmpty: !base.trim() });
      if (cmd) { setTimeout(() => runCommand(cmd)); continue; } // commands never enter the answer
      base += seg + " ";
      const stripped = VC.stripSubmit(base);
      if (stripped !== null) {
        base = stripped ? stripped + " " : seg + " "; // a bare "that's all" is a real reply to "any questions?"
        $("answer").value = base.trim();
        showHeard("Sending your answer");
        setTimeout(() => send());
        return;
      }
    }
    $("answer").value = base + interim;
  };
  rec.onerror = (e) => {
    if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      listening = false;
      $("turnError").textContent = "Microphone access is blocked. Allow it in your browser settings, or type your answer.";
      updateMic();
    }
  };
  rec.onend = () => { if (listening && rec) { try { rec.start(); } catch (_) { /* restarting */ } } };
  try { rec.start(); listening = true; } catch (_) { listening = false; }
  updateMic();
  if (listening) setInterviewer("listening");
}

function stopListening() {
  return new Promise((resolve) => {
    if (!rec) { listening = false; updateMic(); resolve(); return; }
    listening = false;
    const r = rec;
    rec = null;
    const done = () => { updateMic(); resolve(); };
    const t = setTimeout(done, 900); // wait for final results to land
    r.onend = () => { clearTimeout(t); done(); };
    try { r.stop(); } catch (_) { clearTimeout(t); done(); }
  });
}
function updateMic() {
  const b = $("micBtn");
  b.setAttribute("aria-pressed", String(listening));
  b.setAttribute("aria-label", listening ? "Stop listening" : "Start speaking");
  if (!listening && !state.waiting && !state.speaking && !$("interview").hidden) setInterviewer("idle");
}

/** Interviewer says something that isn't part of the interview record, then listens again. */
async function say(text) {
  await stopListening();
  await speak([text]);
  if (state.session && onInterview(state.session.id) && state.mode === "voice" && SR) startListening();
}

function lastQuestion() {
  const t = [...(state.session?.transcript || [])].reverse().find((x) => x.speaker === "INTERVIEWER");
  return t ? t.text : "";
}

async function runCommand(cmd) {
  if (state.waiting || !state.session) return;
  switch (cmd.type) {
    case "repeat":
      showHeard("Repeating the question");
      await say(lastQuestion());
      break;
    case "think":
      state.hold = true;
      showHeard("Take your time. Auto-send waits until you start talking again.");
      await say("Sure, take your time.");
      state.hold = true;
      break;
    case "skip":
      showHeard("Skipping this question");
      await send({ command: "skip" });
      break;
    case "clear":
      base = "";
      $("answer").value = "";
      showHeard("Answer cleared. Start again whenever you're ready.");
      break;
    case "slower": case "faster":
      prefs.rate = Math.min(1.4, Math.max(0.7, prefs.rate + (cmd.type === "slower" ? -0.15 : 0.15)));
      savePrefs();
      showHeard(cmd.type === "slower" ? "Speaking slower" : "Speaking faster");
      await say(cmd.type === "slower" ? "Okay, I'll slow down." : "Okay, I'll speak a little faster.");
      break;
    case "end":
      state.confirming = true;
      showHeard("Say “yes” to end the interview, or “no” to keep going.");
      await say("Do you want to end the interview now? Say yes to end, or no to keep going.");
      clearTimeout(confirmTimer);
      confirmTimer = setTimeout(() => { if (state.confirming) { state.confirming = false; showHeard("Okay, continuing the interview."); } }, 12000);
      break;
  }
}

async function onConfirmReply(text) {
  const answer = VC.confirm(text);
  if (answer === null) { await say("Sorry, say yes to end the interview, or no to keep going."); return; }
  state.confirming = false;
  clearTimeout(confirmTimer);
  if (answer) await endInterview({ skipConfirm: true });
  else { showHeard("Continuing the interview"); await say("Okay, let's continue."); }
}

/* Auto-send: when hands-free, a pause after a real answer sends it. Speaking again cancels. */
const TALKING_GRACE_MS = 700;
function autoSendTick() {
  const bar = $("autosend");
  const text = $("answer").value.trim();
  const active = prefs.handsFree && listening && !state.waiting && !state.speaking && !state.hold && !state.confirming;
  if (!active || VC.words(text) < 3) { bar.hidden = true; return; }
  const limit = prefs.silenceMs * (VC.endsMidThought(text) ? 2 : 1);
  const quiet = Date.now() - lastSpeechAt;
  if (quiet < TALKING_GRACE_MS) { bar.hidden = true; return; }
  bar.hidden = false;
  const pct = Math.min(1, (quiet - TALKING_GRACE_MS) / (limit - TALKING_GRACE_MS));
  $("autosendFill").style.width = `${pct * 100}%`;
  $("autosendText").textContent = `Sending in ${Math.max(1, Math.ceil((limit - quiet) / 1000))}s. Keep talking to add more.`;
  if (quiet >= limit) { bar.hidden = true; send(); }
}
setInterval(autoSendTick, 150);

/* ---------------- Turn loop ---------------- */
const onInterview = (id) => location.hash === `#/interview/${id}`;

async function afterResponse(view) {
  if (!onInterview(view.id)) return; // user navigated away
  applyView(view);
  setInterviewer("idle");
  await speak((view.messages || []).map((m) => m.text));
  if (!onInterview(view.id)) return;
  if (view.status === "COMPLETED") { await stopListening(); location.hash = `#/report/${view.id}`; return; }
  setInterviewer("idle");
  if (state.mode === "voice" && SR && prefs.handsFree) startListening();
}

async function send(opts = {}) {
  if (state.waiting || !state.session) return;
  state.waiting = true; // set before awaiting so a second trigger can't double-send
  await stopListening();
  const command = opts.command || null;
  const text = command ? "" : $("answer").value.trim();
  if (!command && !text) {
    state.waiting = false;
    $("turnError").textContent = "Say or type an answer first.";
    return;
  }
  $("turnError").textContent = "";
  $("sendBtn").disabled = true;
  $("autosend").hidden = true;
  state.hold = false;
  setInterviewer("thinking");
  const bubble = command === "skip" ? "(Skipped this question)" : text;
  $("transcript").insertAdjacentHTML("beforeend", `<li class="candidate"><span class="who">You</span><p>${esc(bubble)}</p></li>`);
  $("transcript").scrollTop = $("transcript").scrollHeight;
  $("answer").value = "";
  base = "";
  const code = $("workpad").hidden ? null : ($("workpadText").value.trim() || null);
  try {
    const view = await postJSON(`/api/sessions/${state.session.id}/turns`, command ? { command, code } : { text, code });
    state.waiting = false;
    await afterResponse(view);
  } catch (e) {
    $("turnError").textContent = e.message;
    if (text) $("answer").value = text;
    renderTranscript();
    setInterviewer("idle");
  } finally {
    state.waiting = false;
    $("sendBtn").disabled = false;
  }
}

async function endInterview(opts = {}) {
  if (!opts.skipConfirm && !confirm("End the interview now? You'll get a report on what you've answered so far.")) return;
  stopSpeaking();
  await stopListening();
  try {
    await postJSON(`/api/sessions/${state.session.id}/end`);
    location.hash = `#/report/${state.session.id}`;
  } catch (e) { $("turnError").textContent = e.message; }
}

/* ---------------- Report ---------------- */
async function showReport(id) {
  showView("report");
  if (state.reportFor === id && $("reportBody").innerHTML) return;
  state.reportFor = id;
  $("roundRail").innerHTML = "";
  $("reportPending").hidden = false;
  $("reportBody").innerHTML = "";
  for (let i = 0; i < 120 && location.hash === `#/report/${id}`; i++) {
    try {
      const r = await api(`/api/sessions/${id}/report`);
      if (r.status === "READY") { $("reportPending").hidden = true; renderReport(id, r.body, r.rating); return; }
      if (r.status === "FAILED") { $("reportPending").hidden = true; $("reportBody").innerHTML = `<p class="error">The report could not be generated: ${esc(r.error)}</p>`; return; }
    } catch (e) { /* not ready yet */ }
    await new Promise((res) => setTimeout(res, 2500));
  }
  $("reportPending").hidden = true;
  $("reportBody").innerHTML = `<p class="error">Scoring is taking longer than expected. Reload this page in a minute.</p>`;
}

function renderReport(id, b, rating) {
  const [label, tone] = VERDICT[b.verdict] || ["Not enough signal", "mid"];
  const html = [];
  html.push(`<p class="verdict ${tone}">${label}</p>`);
  html.push(`<p class="verdict-sub">${esc(b.role)}, ${esc(b.level)}.${b.overall != null ? ` Overall ${b.overall.toFixed(1)} out of 5.` : ""}</p>`);
  if (b.summary) html.push(`<p class="summary">${esc(b.summary)}</p>`);

  if (b.missed_topics?.length) {
    html.push(`<h2>What you missed</h2><ul class="gaps">`);
    for (const g of b.missed_topics) {
      const pts = g.key_points_missed?.length ? ` Points to cover: ${esc(g.key_points_missed.join(", "))}.` : "";
      html.push(`<li><strong>${esc(g.topic)}</strong> <span class="tag">${esc(TOPIC_STATUS[g.status] || g.status)}, depth ${g.depth_reached} of ${g.target_depth}.</span>${pts}</li>`);
    }
    html.push(`</ul>`);
  }

  if (b.study_plan?.length) {
    html.push(`<h2>Study plan</h2><ol class="plan">`);
    for (const p of b.study_plan) html.push(`<li><strong>${esc(p.topic)}</strong>. ${esc(p.why)} <em>${esc(p.how_to_practice)}</em></li>`);
    html.push(`</ol>`);
  }

  html.push(`<h2>Round by round</h2>`);
  for (const r of b.rounds) {
    const [rl] = VERDICT[r.verdict] || ["Not enough signal"];
    html.push(`<div class="round-head"><h3>${r.round_seq}. ${esc(r.title)}</h3><span class="conf">${esc(rl)}, ${esc(r.confidence.toLowerCase())} confidence</span><span class="score">${r.overall != null ? r.overall.toFixed(1) : "n/a"}</span></div>`);
    for (const c of r.competencies) {
      const pct = c.score != null ? (c.score / 5) * 100 : 0;
      const ev = (c.evidence || []).slice(0, 2).map((e) => `<blockquote>"${esc(e.quote)}" <cite>Turn ${e.turn}</cite></blockquote>`).join("");
      const missed = c.missed_points?.length ? `<br>Missing: ${esc(c.missed_points.join(", "))}` : "";
      html.push(`<div class="comp"><span class="name">${esc(c.name.replace(/_/g, " "))}</span><span class="bar"><b style="width:${pct}%"></b></span><span class="val">${c.score ?? "n/a"}</span><div class="detail">${esc(c.reasoning)}${missed}${ev}</div></div>`);
    }
    if (r.strengths?.length) html.push(`<p><strong>Strengths:</strong> ${esc(r.strengths.join("; "))}</p>`);
    if (r.model_answers?.length) {
      html.push(`<details><summary>What strong answers would cover</summary><ul>`);
      for (const m of r.model_answers) html.push(`<li>${esc(m.question)}: ${esc(m.key_points.join(", "))}</li>`);
      html.push(`</ul></details>`);
    }
  }
  if (b.rounds_not_attempted?.length) html.push(`<p class="tag">Not attempted: ${esc(b.rounds_not_attempted.map((r) => r.title).join(", "))}.</p>`);
  if (b.next_mock_focus?.length) html.push(`<h2>Focus for your next mock</h2><p>${esc(b.next_mock_focus.join(", "))}</p>`);

  html.push(rating ? `<div class="rate"><span>You rated this feedback ${rating} out of 5.</span></div>` :
    `<div class="rate" id="rate"><span>Was this feedback accurate?</span>${[1, 2, 3, 4, 5].map((n) => `<button class="ghost" data-r="${n}">${n}</button>`).join("")}</div>`);
  html.push(`<p class="actions"><a class="primary as-button" href="#/dashboard">See your progress</a> <a class="ghost as-button" href="#/new">Start another interview</a></p>`);
  $("reportBody").innerHTML = html.join("");
  $("rate")?.addEventListener("click", async (e) => {
    const n = e.target.dataset.r;
    if (!n) return;
    try { await postJSON(`/api/sessions/${id}/report/rating`, { rating: Number(n) }); $("rate").innerHTML = "<span>Thanks. Your rating helps calibrate the scoring.</span>"; }
    catch (err) { $("rate").insertAdjacentHTML("beforeend", `<span class="error">${esc(err.message)}</span>`); }
  });
}

/* ---------------- Wiring ---------------- */
async function init() {
  $("voiceNote").textContent = SR ? "Hands-free: your answer is sent when you pause, and you can say “repeat the question”, “give me a minute” or “skip this one” at any time. Chrome or Edge work best." :
    "This browser can't take voice input. Use Chrome or Edge to speak, or choose Type.";
  $("authForm").addEventListener("submit", onAuthSubmit);
  $("logoutBtn").addEventListener("click", logout);
  $("setupForm").addEventListener("submit", onStart);
  $("roleChoices").addEventListener("change", () => renderLevels());
  $("levelChoices").addEventListener("change", renderRounds);
  $("resumeFile").addEventListener("change", (e) => {
    $("resumeFileLabel").textContent = e.target.files[0]?.name || "Upload PDF, DOCX or TXT";
    if (e.target.files[0]) $("useSaved").checked = false;
  });
  $("resumeText").addEventListener("input", () => { if ($("resumeText").value.trim()) $("useSaved").checked = false; });
  $("sendBtn").addEventListener("click", () => send());
  $("micBtn").addEventListener("click", () => (listening ? stopListening() : startListening()));
  $("endBtn").addEventListener("click", () => endInterview());
  $("handsFree").addEventListener("change", (e) => {
    prefs.handsFree = e.target.checked; savePrefs();
    showHeard(prefs.handsFree ? "Hands-free on: your answer is sent when you pause." : "Hands-free off: press Send or say “that's my answer”.");
    if (prefs.handsFree && state.mode === "voice" && !listening && !state.waiting && !state.speaking) startListening();
  });
  $("silenceSel").addEventListener("change", (e) => { prefs.silenceMs = Number(e.target.value); savePrefs(); });
  $("answer").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); } });
  $("workpadText").addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    e.preventDefault();
    const t = e.target, s = t.selectionStart;
    t.value = t.value.slice(0, s) + "    " + t.value.slice(t.selectionEnd);
    t.selectionStart = t.selectionEnd = s + 4;
  });
  window.addEventListener("hashchange", route);

  try {
    const health = await api("/api/health");
    state.testAccount = health.test_account || null;
  } catch (_) { state.testAccount = null; }
  try { state.packs = await api("/api/role-packs"); }
  catch (e) { document.body.insertAdjacentHTML("beforeend", `<p class="error">Could not load roles: ${esc(e.message)}</p>`); return; }
  try { state.user = await api("/api/auth/me"); } catch (_) { state.user = null; }
  route();
}
init();
