// Curve -- grades dashboard.
//
// Two halves, same as before:
//   1. unlock  -- turn your username + password into a key and decrypt the data
//   2. render  -- four screens driven entirely by what the portal gave us
//
// There is no server here. GitHub Pages serves files and nothing else, so nobody can
// check a password. Instead the password IS the key: the data file is AES-GCM
// ciphertext, and a wrong password produces no plaintext at all. Decryption happens on
// your phone; nothing is ever sent anywhere.

const $ = (sel) => document.querySelector(sel);
const STORE_KEY = "grades.credentials";

/* ================= unlock ================= */

function b64ToBytes(s) {
  return Uint8Array.from(atob(s), (ch) => ch.charCodeAt(0));
}

async function deriveKey(username, password, salt, iterations) {
  const material = new TextEncoder().encode(`${username.trim().toLowerCase()}\n${password}`);
  const base = await crypto.subtle.importKey("raw", material, "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations, hash: "SHA-256" },
    base, { name: "AES-GCM", length: 256 }, false, ["decrypt"],
  );
}

async function loadBlob() {
  // build_offline.py inlines the blob so the single-file build works with no server --
  // a fetch() would fail outright from a file:// page.
  if (window.__GRADES_BLOB__) return window.__GRADES_BLOB__;
  const res = await fetch(`data.enc.json?t=${Date.now()}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Couldn't load the grade file. Has it been published yet?");
  return res.json();
}

async function unlock(username, password) {
  const blob = await loadBlob();
  const key = await deriveKey(username, password, b64ToBytes(blob.salt), blob.iterations);
  let plaintext;
  try {
    plaintext = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: b64ToBytes(blob.nonce) }, key, b64ToBytes(blob.ciphertext));
  } catch {
    // AES-GCM rejects a wrong key outright; it can't say which half was wrong.
    throw new Error("Wrong username or password.");
  }
  return JSON.parse(new TextDecoder().decode(plaintext));
}


/* ================= theme ================= */

const THEME_KEY = "grades.theme";
const ACCENTS = [
  ["violet", "#8b7cf6"], ["sky", "#38bdf8"], ["mint", "#34d399"],
  ["amber", "#fbbf24"], ["rose", "#fb7185"],
];

const theme = { mode: "system", accent: "violet" };

function loadTheme() {
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(THEME_KEY) || "null"); }
  catch { /* unreadable or blocked; defaults stand */ }
  if (saved?.mode) theme.mode = saved.mode;
  if (saved?.accent && ACCENTS.some(([n]) => n === saved.accent)) theme.accent = saved.accent;
}

const prefersLight = () =>
  window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;

/** Resolve "system" here so the CSS only ever deals with an explicit light or dark. */
function applyTheme() {
  const resolved = theme.mode === "system" ? (prefersLight() ? "light" : "dark") : theme.mode;
  const root = document.documentElement;
  root.setAttribute("data-theme", resolved);
  root.setAttribute("data-accent", theme.accent);

  // Keeps the iOS status bar from clashing with the page behind it.
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    meta.setAttribute("content",
      getComputedStyle(root).getPropertyValue("--bg").trim() || "#0b0d14");
  }
}

function setTheme(patch) {
  Object.assign(theme, patch);
  try { localStorage.setItem(THEME_KEY, JSON.stringify(theme)); }
  catch { /* private browsing; the choice still applies for this session */ }
  applyTheme();
}

loadTheme();
applyTheme();

// Follow the phone's own light/dark switch, but only while set to System.
if (window.matchMedia) {
  window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => {
    if (theme.mode === "system") applyTheme();
  });
}

/* ================= state ================= */

const state = { data: null, tab: "today", course: null };

async function attempt(username, password, remember) {
  const data = await unlock(username, password);
  if (remember) {
    try { localStorage.setItem(STORE_KEY, JSON.stringify({ username, password })); }
    catch { /* private browsing blocks writes; signing in still worked */ }
  }
  state.data = data;
  $("#login").classList.add("hidden");
  $("#app").classList.remove("hidden");
  draw();
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const btn = $("#signin"), err = $("#login-error");
  btn.disabled = true; btn.textContent = "Unlocking…"; err.classList.add("hidden");
  try {
    await attempt($("#username").value, $("#password").value, $("#remember").checked);
  } catch (e) {
    err.textContent = e.message; err.classList.remove("hidden");
    $("#password").value = ""; $("#password").focus();
  } finally {
    btn.disabled = false; btn.textContent = "Sign in";
  }
});

(async function resume() {
  let saved;
  try { saved = JSON.parse(localStorage.getItem(STORE_KEY) || "null"); } catch { return; }
  if (!saved) return;
  try { await attempt(saved.username, saved.password, true); }
  catch { try { localStorage.removeItem(STORE_KEY); } catch { /* already gone */ } }
})();

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.tab = btn.dataset.tab;
    state.course = null;
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("on", b === btn));
    draw();
    window.scrollTo(0, 0);
  });
});

/* ================= derivations ================= */

// Standard cutoffs. PowerSchool hands us a letter for the course grade, so this is only
// used for "how far to the next letter" and for what-if answers -- which means those two
// are estimates if your school grades on a different scale.
const SCALE = [
  [97, "A+"], [93, "A"], [90, "A-"], [87, "B+"], [83, "B"], [80, "B-"],
  [77, "C+"], [73, "C"], [70, "C-"], [67, "D+"], [63, "D"], [60, "D-"], [0, "F"],
];

const letterFor = (pct) => (SCALE.find(([min]) => pct >= min) || ["", "F"])[1];

function nextLetterUp(pct) {
  // The lowest cutoff strictly above the current grade.
  const above = SCALE.filter(([min]) => min > pct).sort((a, b) => a[0] - b[0])[0];
  return above ? { letter: above[1], gap: +(above[0] - pct).toFixed(1) } : null;
}

const scored = (a) => a.score != null && a.score !== "" && Number(a.points_possible) > 0;

/** How the grade got where it is: a running total in due-date order. */
function runningSeries(assignments) {
  const graded = (assignments || []).filter((a) => scored(a) && a.due_date)
    .sort((a, b) => a.due_date.localeCompare(b.due_date));
  let got = 0, out = 0;
  return graded.map((a) => {
    got += Number(a.score); out += Number(a.points_possible);
    return { date: a.due_date, pct: (got / out) * 100 };
  });
}

/** Change over roughly the last fortnight, or null when there isn't enough history. */
function recentDelta(series, days = 14) {
  if (series.length < 2) return null;
  const last = series[series.length - 1];
  const cutoff = new Date(`${last.date}T00:00:00`);
  cutoff.setDate(cutoff.getDate() - days);
  const iso = cutoff.toISOString().slice(0, 10);
  const before = [...series].reverse().find((p) => p.date <= iso);
  const from = before || series[0];
  if (from === last) return null;
  return +(last.pct - from.pct).toFixed(1);
}

const courseTotals = (c) => (c.assignments || []).reduce(
  (t, a) => {
    if (a.missing) t.missing += Number(a.points_possible) || 0;
    if (scored(a)) { t.got += Number(a.score); t.out += Number(a.points_possible); }
    return t;
  }, { missing: 0, got: 0, out: 0 });

/** The single assignment worth chasing: the biggest pile of missing points. */
function topAction(courses) {
  let best = null, totalMissing = 0;
  courses.forEach((c) => {
    (c.assignments || []).forEach((a) => {
      if (!a.missing) return;
      const pts = Number(a.points_possible) || 0;
      totalMissing += pts;
      if (!best || pts > best.pts) best = { course: c, assignment: a, pts };
    });
  });
  return best ? { ...best, totalMissing } : null;
}

const todayISO = () => new Date().toLocaleDateString("en-CA");

function dueOn(course, iso) {
  return (course.assignments || []).filter((a) => a.due_date === iso);
}

function upcoming(courses) {
  const today = todayISO(), out = [];
  courses.forEach((c) => (c.assignments || []).forEach((a) => {
    if (a.due_date && a.due_date >= today && !scored(a)) out.push({ ...a, course: c.name });
  }));
  return out.sort((a, b) => a.due_date.localeCompare(b.due_date));
}

function missingList(courses) {
  const out = [];
  courses.forEach((c) => (c.assignments || []).forEach((a) => {
    if (a.missing) out.push({ ...a, course: c.name });
  }));
  return out.sort((a, b) => (b.points_possible || 0) - (a.points_possible || 0));
}

/* ================= small view helpers ================= */

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[ch]);
}

const fmtPct = (n) => (typeof n === "number" ? n.toFixed(1) : "—");

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(`${iso}T00:00:00`);
  return isNaN(d) ? iso : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function fmtWhen(iso) {
  const d = new Date(iso);
  return isNaN(d) ? iso
    : d.toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });
}

const deltaClass = (d) => (d == null ? "flat" : d > 0.05 ? "up" : d < -0.05 ? "down" : "flat");
const deltaText = (d) => (d == null || Math.abs(d) < 0.05 ? "" : `${d > 0 ? "↑" : "↓"}${Math.abs(d).toFixed(1)}`);

function sparkline(series, w = 62, h = 22) {
  if (series.length < 2) return `<svg class="spark" viewBox="0 0 ${w} ${h}"></svg>`;
  const ys = series.map((p) => p.pct);
  const lo = Math.min(...ys), hi = Math.max(...ys), range = hi - lo;
  const flat = range < 0.05;
  const pts = series.map((p, i) => {
    const x = (i / (series.length - 1)) * (w - 2) + 1;
    const y = flat ? h / 2 : h - 2 - ((p.pct - lo) / range) * (h - 4);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const trend = ys[ys.length - 1] - ys[0];
  const color = trend > 0.05 ? "var(--good)" : trend < -0.05 ? "var(--bad)" : "var(--muted)";
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" aria-hidden="true">
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.6"
      stroke-linecap="round" stroke-linejoin="round" /></svg>`;
}

function targetIcon(size = 32) {
  const c = size / 2;
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">
    <circle cx="${c}" cy="${c}" r="${c - 2}" fill="none" stroke="var(--accent)" stroke-width="1.5" opacity=".5"/>
    <circle cx="${c}" cy="${c}" r="${c - 7}" fill="none" stroke="var(--accent)" stroke-width="1.5"/>
    <circle cx="${c}" cy="${c}" r="2.5" fill="var(--accent)"/></svg>`;
}

function donut(pct, label, size = 58) {
  const r = size / 2 - 4, c = 2 * Math.PI * r;
  const shown = typeof pct === "number" ? Math.max(0, Math.min(100, pct)) : 0;
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--line)" stroke-width="4"/>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--accent)" stroke-width="4"
      stroke-linecap="round" stroke-dasharray="${(c * shown / 100).toFixed(1)} ${c.toFixed(1)}"
      transform="rotate(-90 ${size / 2} ${size / 2})"/>
    <text x="50%" y="50%" text-anchor="middle" dominant-baseline="central"
      fill="var(--text)" font-size="15" font-weight="600">${esc(label)}</text></svg>`;
}

function lineChart(series, w = 560, h = 74) {
  if (series.length < 2) {
    return `<div class="empty">Not enough graded work yet to draw a trend.</div>`;
  }
  const ys = series.map((p) => p.pct);
  const lo = Math.min(...ys), hi = Math.max(...ys), range = hi - lo;
  const flat = range < 0.05;
  const pt = (p, i) => {
    const x = (i / (series.length - 1)) * (w - 4) + 2;
    // With no variation there's no shape to show, so sit the line mid-box rather than
    // pinning it to the floor.
    const y = flat ? h / 2 : h - 6 - ((p.pct - lo) / range) * (h - 14);
    return [x, y];
  };
  const d = series.map((p, i) => { const [x, y] = pt(p, i); return `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`; }).join(" ");
  const [ex, ey] = pt(series[series.length - 1], series.length - 1);
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
    <path d="${d}" fill="none" stroke="var(--accent)" stroke-width="2"
      stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>
    <circle cx="${ex.toFixed(1)}" cy="${ey.toFixed(1)}" r="3" fill="var(--accent)"/></svg>`;
}

/* ================= screens ================= */

function draw() {
  const el = $("#screen");
  if (state.course != null) el.innerHTML = viewCourse(state.course);
  else if (state.tab === "today") el.innerHTML = viewToday();
  else if (state.tab === "grades") el.innerHTML = viewGrades();
  else if (state.tab === "work") el.innerHTML = viewWork();
  else el.innerHTML = viewMe();
  wire();
  // The what-if card can only be filled once its container is in the DOM.
  if (state.course != null) renderWhatIf(state.course, Number($("#whatif")?.value || 85));
}

function wire() {
  document.querySelectorAll("[data-course]").forEach((el) => {
    el.addEventListener("click", () => {
      state.course = Number(el.dataset.course);
      draw(); window.scrollTo(0, 0);
    });
  });
  const back = $("#back");
  if (back) back.addEventListener("click", () => { state.course = null; draw(); window.scrollTo(0, 0); });
  const slider = $("#whatif");
  if (slider) slider.addEventListener("input", () => renderWhatIf(state.course, Number(slider.value)));
  document.querySelectorAll("#mode button").forEach((b) =>
    b.addEventListener("click", () => { setTheme({ mode: b.dataset.mode }); draw(); }));
  document.querySelectorAll("#accents .swatch").forEach((b) =>
    b.addEventListener("click", () => { setTheme({ accent: b.dataset.accent }); draw(); }));

  const out = $("#signout");
  if (out) out.addEventListener("click", signOut);
}

function courses() { return state.data?.courses || []; }

function header() {
  const at = state.data?.scraped_at;
  return `<div class="topline">
    <div class="brand"><span class="mark"></span> Curve</div>
    ${at ? `<span class="chip">synced ${esc(fmtWhen(at))}</span>` : ""}
  </div>`;
}

function viewToday() {
  const cs = courses();
  const withDelta = cs.map((c, i) => {
    const series = runningSeries(c.assignments);
    return { c, i, series, delta: recentDelta(series) };
  });

  const dropped = withDelta.filter((x) => x.delta != null && x.delta < -0.05);
  const gpa = state.data?.gpa?.weighted;

  let head, quiet;
  if (!cs.length) { head = "Nothing here yet."; quiet = "No courses came back from the portal."; }
  else if (!dropped.length) { head = "You're steady."; quiet = "Nothing dropped this week."; }
  else if (dropped.length === 1) { head = "One grade slipped."; quiet = `${dropped[0].c.name} is moving down.`; }
  else { head = `${dropped.length} grades slipped.`; quiet = dropped.map((x) => x.c.name).join(", ") + " are moving down."; }

  const today = todayISO();
  const strip = cs.slice(0, 4).map((c) => {
    const due = dueOn(c, today);
    const label = due.length ? (due[0].category || due[0].name || "due") : "—";
    return `<div class="period ${due.length ? "flag" : ""}">
      <div class="p">${esc(c.period || "")}</div>
      <div class="n">${esc(abbrev(c.name))}</div>
      <div class="d ${due.length ? "" : "none"}">${esc(label)}</div>
    </div>`;
  }).join("");

  return `${header()}
    <h1 class="headline">${esc(head)}<span class="quiet">${esc(quiet)}</span></h1>
    <p class="underline">${gpa != null ? `<strong>${Number(gpa).toFixed(2)} GPA</strong>` : "GPA not published"}</p>

    <div class="sec-label">Today · ${esc(new Date().toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }))}</div>
    <div class="periods">${strip || `<div class="empty">No courses.</div>`}</div>

    <div class="sec-label">Courses <span class="link">${cs.length} total</span></div>
    <div class="rows">${withDelta.map(rowFor).join("") || `<div class="empty">No courses.</div>`}</div>`;
}

function shortName(name) {
  return String(name || "").replace(/\s*\(.*\)\s*/g, "").slice(0, 14);
}

const NUMERAL = /^(\d+|[ivx]+)$/i;

/** Squeeze a course name into a quarter-width chip: "Algebra II" -> "Alg II". */
function abbrev(name) {
  const words = String(name || "").replace(/\s*\(.*\)\s*/g, "").trim().split(/\s+/);
  if (!words[0]) return "";
  if (words.length === 1) return words[0].slice(0, 3);
  const last = words[words.length - 1];
  if (NUMERAL.test(last)) return `${words[0].slice(0, 3)} ${last}`;
  // Otherwise initials, keeping short all-caps words whole: "US History" -> "USH".
  return words.map((w) => (w.length <= 2 && w === w.toUpperCase() ? w : w[0])).join("");
}

function rowFor({ c, i, series, delta }) {
  return `<button class="row" data-course="${i}">
    <div>
      <div class="nm">${esc(c.name || "Untitled")}</div>
      <div class="mt">${esc([c.teacher, c.period].filter(Boolean).join(" · "))}</div>
    </div>
    ${sparkline(series)}
    <div class="val">
      <div class="pct">${fmtPct(c.grade_percent)}${typeof c.grade_percent === "number" ? "%" : ""}</div>
      <div class="sub2">${esc(c.grade_letter || "")} <span class="${deltaClass(delta)}">${deltaText(delta)}</span></div>
    </div>
  </button>`;
}

function viewGrades() {
  const cs = courses();
  const gpa = state.data?.gpa;
  const weighted = gpa?.weighted;

  const withDelta = cs.map((c) => ({ c, delta: recentDelta(runningSeries(c.assignments)) }));
  const moving = withDelta.filter((x) => x.delta != null && x.delta < -0.05);
  const holding = withDelta.length - moving.length;

  let prose;
  if (!withDelta.some((x) => x.delta != null)) {
    prose = "Not enough graded work yet to say which way anything is moving.";
  } else if (!moving.length) {
    prose = `All <span class="em">${withDelta.length}</span> courses are holding or climbing.`;
  } else {
    prose = `<span class="em">${holding}</span> of ${withDelta.length} courses are holding. ` +
      (moving.length === 1
        ? `<span class="em">${esc(moving[0].c.name)}</span> is the only one moving down.`
        : `${moving.length} are moving down.`);
  }

  const act = topAction(cs);
  const nudge = act ? `<button class="nudge" data-course="${cs.indexOf(act.course)}">
      <span class="ring">${targetIcon()}</span>
      <span>
        <span class="t">One thing today</span>
        <span class="b">Turn in ${esc(act.assignment.name || "the missing work")} for
          ${esc(act.course.name)} — it's ${act.pts} of the ${act.totalMissing} points you're missing.</span>
      </span>
      <span class="go">›</span>
    </button>` : "";

  return `${header()}
    <div class="standing-hero">
      <div class="sec-label" style="margin-top:0">Where you stand</div>
      ${weighted != null ? `<div class="gpa-big">
          <div class="n">${Number(weighted).toFixed(2)}</div>
          <div class="u">weighted<br>GPA</div>
        </div>
        <div class="scale"><span class="dot" style="left:${Math.max(0, Math.min(100, (Number(weighted) / 5) * 100))}%"></span></div>`
      : `<div class="gpa-big"><div class="n">—</div><div class="u">GPA not<br>published</div></div>`}
      <p class="prose">${prose}</p>
    </div>
    ${nudge}
    <div class="sec-label">Your ${cs.length}</div>
    <div class="donuts">${cs.map((c, i) => `
      <button class="donut" data-course="${i}">
        ${donut(c.grade_percent, c.grade_letter || "—")}
        <span class="lb">${esc(shortName(c.name))}</span>
      </button>`).join("") || `<div class="empty">No courses.</div>`}</div>`;
}

function viewCourse(i) {
  const c = courses()[i];
  if (!c) return `${header()}<div class="empty">Course not found.</div>`;

  const series = runningSeries(c.assignments);
  const pct = c.grade_percent;
  const next = typeof pct === "number" ? nextLetterUp(pct) : null;
  const items = [...(c.assignments || [])]
    .sort((a, b) => (b.due_date || "").localeCompare(a.due_date || ""));

  return `<div class="back" id="back"><span class="a">←</span> Courses</div>
    <h1 class="detail-h">${esc(c.name || "Course")}</h1>
    <p class="detail-m">${esc([c.teacher, c.period, c.term].filter(Boolean).join(" · "))}</p>

    <div class="detail-grade">
      <div class="n">${fmtPct(pct)}</div>
      <div class="l">${esc(c.grade_letter || "")}</div>
      ${next ? `<div class="gap">${next.gap} pts from ${esc(next.letter)}</div>` : ""}
    </div>

    <div class="chart">${lineChart(series)}
      ${series.length > 1 ? `<div class="chart-x">
        <span>${esc(fmtDate(series[0].date))}</span><span>today</span></div>` : ""}</div>

    <div class="card">
      <div class="k">What if</div>
      <div id="whatif-body"></div>
      <input type="range" id="whatif" min="40" max="100" step="1" value="85" />
      <div class="range-x"><span>40%</span><span>100%</span></div>
      <p class="note" id="whatif-note"></p>
    </div>

    <div class="sec-label">What's moving it <span class="link">${items.length} items</span></div>
    <div class="items">${items.map(itemRow).join("") || `<div class="empty">No assignments listed.</div>`}</div>`;
}

function itemRow(a) {
  const has = scored(a);
  const pct = typeof a.percent === "number" ? a.percent : (has ? (a.score / a.points_possible) * 100 : null);
  const color = a.missing ? "var(--bad)" : a.late ? "var(--warn)"
    : pct == null ? "var(--dim)" : pct >= 90 ? "var(--good)" : pct >= 80 ? "var(--warn)" : "var(--bad)";
  const status = a.missing ? "Missing" : has ? "Graded" : "Not graded";
  return `<div class="item">
    <div class="bar" style="background:${color}"></div>
    <div>
      <div class="nm">${esc(a.name || "Assignment")}</div>
      <div class="mt">${esc(status)} · due ${esc(fmtDate(a.due_date))}${a.category ? ` · ${esc(a.category)}` : ""}${a.late ? " · late" : ""}</div>
    </div>
    <div class="val">
      <div class="sc">${has ? `${esc(a.score)}/${esc(a.points_possible)}` : `—/${esc(a.points_possible ?? "—")}`}</div>
      <div class="p2">${pct != null ? `${pct.toFixed(0)}%` : (a.missing ? `−${a.points_possible || 0} pts` : "")}</div>
    </div>
  </div>`;
}

/**
 * What-if, done on points rather than category weights.
 *
 * PowerSchool's assignment pages give us a category name but never its weight, so a
 * "15% of your grade" style answer would be invented. Adding the hypothetical score to
 * the running points total is arithmetic we can actually stand behind.
 */
function renderWhatIf(i, scorePct) {
  const c = courses()[i];
  const body = $("#whatif-body");
  if (!c || !body) return;

  const { got, out } = courseTotals(c);
  const pending = (c.assignments || []).filter((a) => !scored(a) && Number(a.points_possible) > 0);

  if (!out || !pending.length) {
    body.innerHTML = `<p class="whatif-q">${!out
      ? "Nothing is graded yet, so there's no grade to move."
      : "Every assignment already has a score, so there's nothing left to change it."}</p>`;
    const slider = $("#whatif");
    if (slider) slider.classList.add("hidden");
    return;
  }

  const target = pending.reduce((a, b) =>
    (Number(b.points_possible) > Number(a.points_possible) ? b : a));
  const pts = Number(target.points_possible);
  const now = (got / out) * 100;
  const after = ((got + pts * (scorePct / 100)) / (out + pts)) * 100;
  const diff = after - now;

  // The portal's own grade usually differs from a plain points average because it
  // weights categories, and we can't see those weights. Showing "lands at 77.3" beside
  // a header reading 79.1 would look like a contradiction, so when the two disagree,
  // say which number is which and point at the change instead.
  const portal = c.grade_percent;
  const mismatch = typeof portal === "number" && Math.abs(portal - now) > 1;

  body.innerHTML = `
    <p class="whatif-q">If I score <b>${scorePct}%</b> on
      ${esc(target.name || "the next assignment")} (<b>${pts}</b> points),
      ${mismatch ? "your points average goes from <b>" + now.toFixed(1) + "</b> to"
                 : "the course lands at"}</p>
    <div class="whatif-a">
      <div class="n">${after.toFixed(1)}</div>
      <div class="l">${esc(letterFor(after))}</div>
      <div class="delta ${deltaClass(diff)}">${diff >= 0 ? "+" : "−"}${Math.abs(diff).toFixed(1)} pts</div>
    </div>`;

  const note = $("#whatif-note");
  if (note) {
    note.innerHTML = mismatch
      ? `The portal shows <b>${portal.toFixed(1)}</b> for this course because it weights
         categories, and it doesn't publish those weights. So trust the change
         (<b>${diff >= 0 ? "+" : "−"}${Math.abs(diff).toFixed(1)}</b>), not the number itself.`
      : `Worked out from points, not category weights — the portal doesn't publish those.
         Letter cutoffs assume a standard 90/80/70 scale.`;
  }
}

function viewWork() {
  const cs = courses();
  const missing = missingList(cs), soon = upcoming(cs);
  const line = (a, tag) => `<div class="item">
      <div class="bar" style="background:${tag === "missing" ? "var(--bad)" : "var(--accent)"}"></div>
      <div>
        <div class="nm">${esc(a.name || "Assignment")}</div>
        <div class="mt">${esc(a.course)} · due ${esc(fmtDate(a.due_date))}</div>
      </div>
      <div class="val"><div class="sc">${esc(a.points_possible ?? "—")}</div><div class="p2">pts</div></div>
    </div>`;

  return `${header()}
    <h1 class="headline">Work</h1>
    <p class="underline">${missing.length} missing · ${soon.length} coming up</p>
    <div class="group-h">Missing</div>
    <div class="items">${missing.map((a) => line(a, "missing")).join("")
      || `<div class="empty">Nothing missing. Nice.</div>`}</div>
    <div class="group-h">Coming up</div>
    <div class="items">${soon.slice(0, 20).map((a) => line(a, "soon")).join("")
      || `<div class="empty">Nothing upcoming.</div>`}</div>`;
}

function viewMe() {
  const d = state.data || {};
  const att = d.attendance || {};
  return `${header()}
    <h1 class="headline">${esc(d.student?.name || "You")}</h1>
    <p class="underline">${esc(d.student?.school || "")}</p>
    <div class="sec-label">Attendance</div>
    <div class="mini">
      <div class="b"><div class="k">Absences</div><div class="v">${esc(att.absences ?? 0)}</div></div>
      <div class="b"><div class="k">Tardies</div><div class="v">${esc(att.tardies ?? 0)}</div></div>
    </div>
    <div class="sec-label">Data</div>
    <div class="mini">
      <div class="b"><div class="k">Courses</div><div class="v">${courses().length}</div></div>
      <div class="b"><div class="k">Synced</div><div class="v" style="font-size:17px">${esc(d.scraped_at ? fmtWhen(d.scraped_at) : "—")}</div></div>
    </div>
    <div class="sec-label">Appearance</div>
    <div class="seg" id="mode">
      ${[["system", "System"], ["light", "Light"], ["dark", "Dark"]].map(([v, lb]) =>
        `<button data-mode="${v}" class="${theme.mode === v ? "on" : ""}">${lb}</button>`).join("")}
    </div>
    <div class="sec-label">Colour</div>
    <div class="swatches" id="accents">
      ${ACCENTS.map(([name, hex]) => `<button class="swatch ${theme.accent === name ? "on" : ""}"
          data-accent="${name}" style="--sw:${hex}" aria-label="${name}"><i></i></button>`).join("")}
    </div>
    ${d.is_sample ? `<p class="note">This is sample data — no real grades have been published yet.</p>` : ""}
    <button class="btn ghost" id="signout">Sign out</button>`;
}

function signOut() {
  try { localStorage.removeItem(STORE_KEY); } catch { /* nothing stored */ }
  // Reload rather than just hiding, so decrypted grades leave memory and the DOM.
  location.reload();
}
