// Quizzarr front end: plain JavaScript, no framework, no build step.
"use strict";

const $ = (id) => document.getElementById(id);
const VIEWS = ["home", "question", "results", "settings"];

const state = {
  view: "home",
  answers: [],      // [{q, choice}] — the server replays them at each step
  seed: "",
  status: null,
  lastQuiz: null,   // last /api/quiz answer (to come back from Réglages)
  busy: false,
};

// ---------------------------------------------------------------------------
// "Pas ce soir": hidden until 5 a.m. the next day. localStorage when it works,
// memory otherwise (private browsing, storage blocked…).
// ---------------------------------------------------------------------------
const NOT_TONIGHT_KEY = "quizzarr.notTonight";
let memoryNotTonight = {};

function readNotTonight() {
  let data = memoryNotTonight;
  try {
    const raw = localStorage.getItem(NOT_TONIGHT_KEY);
    if (raw) data = JSON.parse(raw) || {};
  } catch (e) { /* storage unavailable: keep the memory copy */ }
  const now = Date.now();
  const fresh = {};
  for (const [id, until] of Object.entries(data)) if (until > now) fresh[id] = until;
  return fresh;
}

function writeNotTonight(data) {
  memoryNotTonight = data;
  try { localStorage.setItem(NOT_TONIGHT_KEY, JSON.stringify(data)); } catch (e) { /* memory only */ }
}

function hideTonight(id) {
  const until = new Date();
  until.setDate(until.getDate() + (until.getHours() < 5 ? 0 : 1));
  until.setHours(5, 0, 0, 0);
  const data = readNotTonight();
  data[id] = until.getTime();
  writeNotTonight(data);
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------
async function api(method, url, body) {
  const opts = { method, headers: { "X-Quizzarr": "1" }, cache: "no-store" };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let r;
  try {
    r = await fetch(url, opts);
  } catch (e) {
    throw new Error("Quizzarr ne répond pas. Es-tu bien sur le Wi-Fi de la maison ?");
  }
  let data = null;
  try { data = await r.json(); } catch (e) { /* not JSON */ }
  if (!r.ok) throw new Error((data && (data.message || data.detail)) || `Erreur ${r.status}`);
  return data;
}

// ---------------------------------------------------------------------------
// Views
// ---------------------------------------------------------------------------
function show(view) {
  state.view = view;
  for (const v of VIEWS) $(`view-${v}`).hidden = v !== view;
  $("back").hidden = view === "home";
  $("brand").hidden = view === "question";
  $("progress").hidden = view !== "question";
  $("open-settings").hidden = view === "settings";
  window.scrollTo(0, 0);
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

function setNotice(mode, error) {
  const n = $("notice");
  n.replaceChildren();
  n.classList.remove("error");
  if (error && mode !== "setup") {
    n.classList.add("error");
    n.append(el("span", {}, el("strong", {}, "Jellyfin : "), error));
  } else if (mode === "demo") {
    n.append(el("span", {}, el("strong", {}, "Mode démo"), " · une bibliothèque d'exemple, en attendant de connecter Jellyfin."));
    if (state.view !== "settings") n.append(el("button", { class: "link", type: "button", onclick: openSettings }, "Connecter"));
  } else if (mode === "setup") {
    n.append(el("span", {}, el("strong", {}, "Presque prêt"), " · choisis l'utilisateur de référence dans Réglages."));
    if (state.view !== "settings") n.append(el("button", { class: "link", type: "button", onclick: openSettings }, "Réglages"));
  } else {
    n.hidden = true;
    return;
  }
  n.hidden = false;
}

function plural(n, one, many) { return `${n} ${n === 1 ? one : many}`; }

// ---------------------------------------------------------------------------
// Home
// ---------------------------------------------------------------------------
async function loadHome() {
  show("home");
  $("start").disabled = true;
  try {
    const st = await api("GET", "/api/status");
    state.status = st;
    $("home-clock").textContent = st.now;
    const c = st.catalog;
    const hidden = Object.keys(readNotTonight()).length;
    if (c.total) {
      $("home-count").textContent = `${plural(c.total, "titre disponible", "titres disponibles")} · ${plural(c.movies, "film", "films")}, ${plural(c.series, "série", "séries")}`;
      $("start").disabled = false;
    } else if (st.mode === "setup") {
      $("home-count").textContent = "Jellyfin est connecté. Il reste à choisir l'utilisateur de référence.";
    } else {
      $("home-count").textContent = "Aucun titre pour l'instant. Vérifie les bibliothèques dans Réglages.";
    }
    $("home-hint").textContent = hidden
      ? `Cinq questions au plus. ${plural(hidden, "titre écarté", "titres écartés")} pour ce soir.`
      : "Cinq questions au plus, deux réponses à chaque fois.";
    setNotice(st.mode, c.error);
  } catch (e) {
    $("home-count").textContent = e.message;
  }
}

// ---------------------------------------------------------------------------
// Quiz
// ---------------------------------------------------------------------------
async function step() {
  if (state.busy) return;
  state.busy = true;
  try {
    const data = await api("POST", "/api/quiz", {
      answers: state.answers,
      excluded: Object.keys(readNotTonight()),
      seed: state.seed,
    });
    state.lastQuiz = data;
    state.answers = data.answers; // the server may drop an answer that no longer applies
    setNotice(data.mode, data.error);
    if (data.question) renderQuestion(data);
    else renderResults(data);
  } catch (e) {
    setNotice("jellyfin", e.message);
  } finally {
    state.busy = false;
  }
}

function startQuiz() {
  state.answers = [];
  state.seed = Math.random().toString(36).slice(2, 10);
  step();
}

function renderQuestion(data) {
  const q = data.question;
  $("q-step").textContent = `Question ${data.step} sur ${data.max} au plus`;
  $("q-text").textContent = q.text;
  for (const side of ["a", "b"]) {
    const b = $(`choice-${side}`);
    b.querySelector(".choice-label").textContent = q[side].label;
    b.querySelector(".choice-hint").textContent = q[side].hint;
    b.onclick = () => { state.answers.push({ q: q.id, choice: side }); step(); };
  }
  $("q-left").textContent = `${plural(data.remaining, "titre encore en lice", "titres encore en lice")}`;
  const bar = $("progress");
  bar.replaceChildren(...Array.from({ length: data.max }, (_, i) => el("span", { class: i < data.step - 1 ? "on" : "" })));
  show("question");
}

function renderResults(data) {
  const list = $("cards");
  list.replaceChildren(...data.results.map(card));
  const n = data.results.length;
  $("r-title").textContent = n ? "Ce soir, on pourrait regarder…" : "Rien ce soir";
  $("r-sub").textContent = n ? `${plural(n, "idée", "idées")} · il est ${data.now}` : "";
  $("r-empty").hidden = n > 0;
  if (!n) {
    $("r-empty").querySelector(".lead").textContent = data.available
      ? "Plus rien à proposer avec ces réponses."
      : "Aucun titre disponible. Vérifie les bibliothèques dans Réglages, ou les titres écartés pour ce soir.";
  }
  show("results");
  list.scrollLeft = 0;
}

function card(c) {
  const poster = c.image
    ? el("img", { class: "poster", src: c.image, alt: "", loading: "lazy", decoding: "async" })
    : el("div", { class: "poster", "aria-hidden": "true" }, (c.name || "?").trim().charAt(0).toUpperCase());
  if (c.image) poster.addEventListener("error", () => poster.replaceWith(el("div", { class: "poster" }, c.name.charAt(0))));

  const meta = el("p", { class: "meta" },
    el("span", {}, c.kind_label),
    c.year ? el("span", {}, c.year) : null,
    c.official_rating ? el("span", { class: "cert" }, c.official_rating) : null,
    c.rating ? el("span", { class: "rating", "aria-label": `Note ${c.rating} sur 10` }, `${c.rating}/10`) : null,
  );

  let overview = null;
  if (c.overview) {
    const text = el("p", { class: "text" }, c.overview);
    const more = el("button", { class: "link", type: "button" }, "Lire la suite");
    overview = el("div", { class: "overview" }, text, more);
    more.addEventListener("click", () => {
      const open = overview.classList.toggle("open");
      more.textContent = open ? "Réduire" : "Lire la suite";
    });
    // hide "Lire la suite" when the text already fits
    requestAnimationFrame(() => { if (text.scrollHeight <= text.clientHeight + 2) more.hidden = true; });
  }

  const play = c.play_url
    ? el("a", { class: "btn primary", href: c.play_url, target: "_blank", rel: "noopener noreferrer" }, icon("play"), "Lire")
    : el("button", { class: "btn primary", type: "button", disabled: true, title: "Indisponible en mode démo" }, icon("play"), "Lire");

  const node = el("article", { class: "card" },
    el("div", { class: "card-top" }, poster,
      el("div", {}, el("h2", {}, c.name), meta, c.genres.length ? el("p", { class: "genres" }, c.genres.join(" · ")) : null)),
    c.lines.length ? el("div", { class: "facts" }, c.lines.map((l) => el("p", {}, l))) : null,
    overview,
    el("div", { class: "card-actions" }, play,
      el("button", { class: "btn", type: "button", onclick: () => notTonight(c.id, node) }, icon("x"), "Pas ce soir")),
  );
  return node;
}

function notTonight(id, node) {
  hideTonight(id);
  node.remove();
  const left = $("cards").children.length;
  $("r-sub").textContent = left ? `${plural(left, "idée", "idées")}` : "";
  if (!left) {
    $("r-title").textContent = "Rien ce soir";
    $("r-empty").hidden = false;
    $("r-empty").querySelector(".lead").textContent = "Tout a été écarté. On recommence ?";
  }
}

function back() {
  if (state.view === "settings") {
    if (state.lastQuiz && state.answers.length) step();
    else loadHome();
    return;
  }
  if (state.view === "question" || state.view === "results") {
    if (!state.answers.length) return loadHome();
    state.answers.pop();
    step();
  }
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------
function message(id, text, kind) {
  const m = $(id);
  m.textContent = text;
  m.className = `msg ${kind || ""}`;
  m.hidden = !text;
}

async function openSettings() {
  show("settings");
  setNotice(state.status ? state.status.mode : "", "");
  message("jf-msg", "");
  message("refresh-msg", "");
  $("version").textContent = "";
  try {
    const [conns, st] = await Promise.all([api("GET", "/api/connections"), api("GET", "/api/status")]);
    state.status = st;
    setNotice(st.mode, "");
    $("version").textContent = `version ${st.version}`;
    $("jf-url").value = conns.jellyfin.url;
    $("jf-key").value = "";
    $("jf-key").placeholder = conns.jellyfin.has_key ? "Clé enregistrée (laisser vide pour la garder)" : "Coller la clé API";
    $("jf-key-state").textContent = conns.jellyfin.has_key ? "Clé présente sur le NAS." : "";
    catalogState(st);
  } catch (e) {
    message("jf-msg", e.message, "error");
  }
  loadUserAndLibraries();
}

function catalogState(st) {
  const c = st.catalog;
  const src = st.mode === "demo" ? "Bibliothèque d'exemple" : "Jellyfin";
  $("cat-state").textContent = c.loaded_at
    ? `${src} · ${plural(c.total, "titre", "titres")} (${plural(c.movies, "film", "films")}, ${plural(c.series, "série", "séries")}) · chargé à ${c.loaded_at}`
    : src;
}

async function loadUserAndLibraries() {
  message("settings-error", "");
  let st;
  try {
    st = await api("GET", "/api/settings");
  } catch (e) {
    return message("settings-error", e.message, "error");
  }
  renderSettings(st);
}

function renderSettings(st) {
  const hasUsers = st.users.length > 0;
  $("panel-user").hidden = !hasUsers;
  if (st.error) message("settings-error", st.error, "error");
  const sel = $("jf-user");
  sel.replaceChildren(el("option", { value: "" }, "Choisir…"),
    ...st.users.map((u) => el("option", { value: u.id, selected: u.id === st.jellyfin_user_id ? "selected" : null }, u.admin ? `${u.name} (administrateur)` : u.name)));
  sel.value = st.jellyfin_user_id || "";

  $("panel-libs").hidden = !st.libraries.length;
  $("libs").replaceChildren(...st.libraries.map((lib) => {
    const box = el("input", { type: "checkbox", checked: lib.included ? "checked" : null });
    box.checked = lib.included;
    box.addEventListener("change", () => saveSettings({ libraries: { [lib.id]: box.checked } }));
    const type = lib.type === "movies" ? "films" : lib.type === "tvshows" ? "séries" : "mixte";
    return el("label", { class: "check" }, box, el("span", {}, lib.name, " ", el("span", { class: "tag" }, lib.kids ? `${type} · exclue par défaut` : type)));
  }));
}

async function saveSettings(patch) {
  try {
    const st = await api("PUT", "/api/settings", patch);
    message("settings-error", "");
    renderSettings(st);
    const status = await api("GET", "/api/status");
    state.status = status;
    state.lastQuiz = null;
    setNotice(status.mode, status.catalog.error);
    catalogState(status);
  } catch (e) {
    message("settings-error", e.message, "error");
  }
}

async function testJellyfin() {
  message("jf-msg", "Test en cours…");
  try {
    const r = await api("POST", "/api/connections/jellyfin/test", { url: $("jf-url").value, key: $("jf-key").value });
    message("jf-msg", r.message, r.ok ? "ok" : "error");
  } catch (e) {
    message("jf-msg", e.message, "error");
  }
}

async function saveJellyfin(ev) {
  ev.preventDefault();
  message("jf-msg", "Enregistrement…");
  try {
    const conns = await api("PUT", "/api/connections/jellyfin", { url: $("jf-url").value, key: $("jf-key").value });
    $("jf-key").value = "";
    $("jf-url").value = conns.jellyfin.url;
    $("jf-key").placeholder = conns.jellyfin.has_key ? "Clé enregistrée (laisser vide pour la garder)" : "Coller la clé API";
    $("jf-key-state").textContent = conns.jellyfin.has_key ? "Clé présente sur le NAS." : "";
    state.lastQuiz = null;
    if (conns.jellyfin.url && conns.jellyfin.has_key) {
      const r = await api("POST", "/api/connections/jellyfin/test", {});
      message("jf-msg", r.ok ? `Enregistré. ${r.message}` : `Enregistré, mais : ${r.message}`, r.ok ? "ok" : "error");
    } else {
      message("jf-msg", "Enregistré. Sans adresse ni clé, Quizzarr reste en mode démo.", "ok");
    }
    const st = await api("GET", "/api/status");
    state.status = st;
    setNotice(st.mode, "");
    catalogState(st);
    loadUserAndLibraries();
  } catch (e) {
    message("jf-msg", e.message, "error");
  }
}

async function refreshCatalog() {
  message("refresh-msg", "Actualisation…");
  $("refresh").disabled = true;
  try {
    const r = await api("POST", "/api/refresh");
    message("refresh-msg", r.ok ? `C'est à jour : ${plural(r.catalog.total, "titre", "titres")}.` : r.error, r.ok ? "ok" : "error");
    const st = await api("GET", "/api/status");
    state.status = st;
    catalogState(st);
  } catch (e) {
    message("refresh-msg", e.message, "error");
  } finally {
    $("refresh").disabled = false;
  }
}

// ---------------------------------------------------------------------------
$("start").addEventListener("click", startQuiz);
$("restart").addEventListener("click", startQuiz);
$("back").addEventListener("click", back);
$("open-settings").addEventListener("click", openSettings);
$("jf-test").addEventListener("click", testJellyfin);
$("jf-form").addEventListener("submit", saveJellyfin);
$("jf-user").addEventListener("change", (e) => saveSettings({ jellyfin_user_id: e.target.value }));
$("refresh").addEventListener("click", refreshCatalog);

// keep the clock on the home screen right
setInterval(() => { if (state.view === "home" && !document.hidden) loadHome(); }, 60_000);
document.addEventListener("visibilitychange", () => { if (!document.hidden && state.view === "home") loadHome(); });

loadHome();
