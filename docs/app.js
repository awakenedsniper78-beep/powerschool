// Dashboard for GitHub Pages. Two halves:
//   1. unlock  -- turn your username + password into a key and decrypt data.enc.json
//   2. render  -- the same drawing code as the local dashboard
//
// There is no server here. GitHub Pages serves files and nothing else, so there is
// nobody to check a password against. Instead the password IS the key: data.enc.json is
// AES-GCM ciphertext, and a wrong password produces no plaintext at all, just a failed
// authentication tag. Nothing is ever sent anywhere -- decryption happens on your phone.

const $ = (sel) => document.querySelector(sel);

const STORE_KEY = "grades.credentials";

/* ---------- unlock ---------- */

function b64ToBytes(s) {
  return Uint8Array.from(atob(s), (ch) => ch.charCodeAt(0));
}

async function deriveKey(username, password, salt, iterations) {
  // Username and password both go into the key material, matching publish.py, so
  // getting either one wrong fails exactly the same way.
  const material = new TextEncoder().encode(`${username.trim().toLowerCase()}\n${password}`);
  const base = await crypto.subtle.importKey("raw", material, "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations, hash: "SHA-256" },
    base,
    { name: "AES-GCM", length: 256 },
    false,
    ["decrypt"],
  );
}

async function loadBlob() {
  // build_offline.py inlines the encrypted blob so the single-file build works with no
  // server behind it -- a fetch() would fail outright from a file:// page.
  if (window.__GRADES_BLOB__) return window.__GRADES_BLOB__;

  // Cache-bust so a push of new grades shows up instead of Safari's stale copy.
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
      { name: "AES-GCM", iv: b64ToBytes(blob.nonce) },
      key,
      b64ToBytes(blob.ciphertext),
    );
  } catch {
    // AES-GCM rejects wrong keys outright -- this is the only failure mode there is,
    // and it can't tell us whether the username or the password was the wrong half.
    throw new Error("Wrong username or password.");
  }
  return JSON.parse(new TextDecoder().decode(plaintext));
}

/* ---------- sign in / out ---------- */

async function attempt(username, password, remember) {
  const data = await unlock(username, password);

  if (remember) {
    // Kept on this device only, in this site's own storage -- it is never transmitted.
    // It is also plainly readable to anyone holding an unlocked phone, which is the
    // trade you are making by ticking the box.
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({ username, password }));
    } catch { /* private browsing blocks writes; signing in still worked */ }
  }

  $("#login").classList.add("hidden");
  $("#app").classList.remove("hidden");
  render(data);
}

function signOut() {
  try { localStorage.removeItem(STORE_KEY); } catch { /* nothing stored */ }
  // Reload rather than just hiding the dashboard, so the decrypted grades leave memory
  // and the DOM instead of sitting one devtools poke away.
  location.reload();
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const btn = $("#signin");
  const err = $("#login-error");

  btn.disabled = true;
  btn.textContent = "Unlocking…";
  err.classList.add("hidden");

  try {
    await attempt($("#username").value, $("#password").value, $("#remember").checked);
  } catch (e) {
    err.textContent = e.message;
    err.classList.remove("hidden");
    $("#password").value = "";
    $("#password").focus();
  } finally {
    btn.disabled = false;
    btn.textContent = "Sign in";
  }
});

$("#signout").addEventListener("click", signOut);

// If "stay signed in" was ticked, go straight through on the next visit.
(async function resume() {
  let saved;
  try { saved = JSON.parse(localStorage.getItem(STORE_KEY) || "null"); } catch { return; }
  if (!saved) return;
  try {
    await attempt(saved.username, saved.password, true);
  } catch {
    // Stored password no longer opens the file (republished under a new one), so drop it
    // and fall back to the login screen.
    try { localStorage.removeItem(STORE_KEY); } catch { /* already gone */ }
  }
})();

/* ---------- render ---------- */

function render(data) {
  const courses = data.courses || [];
  const anyGrades = courses.some((c) => typeof c.grade_percent === "number");
  const banner = $("#sample-banner");

  if (data.is_sample) {
    banner.innerHTML = "Showing <strong>sample data</strong> — no real grades published yet.";
    banner.classList.remove("hidden");
  } else if (courses.length && !anyGrades) {
    banner.innerHTML =
      "<strong>No grades posted yet.</strong> Your courses are below, but your teachers " +
      "haven't entered any grades or assignments for this term.";
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }

  const name = (data.student?.name || "").split(" ")[0];
  $("#greeting").textContent = name ? `Hey, ${name}.` : "Your grades";
  $("#subline").textContent = data.scraped_at
    ? `Last synced ${formatSynced(data.scraped_at)}`
    : "";

  renderStats(data);
  renderCourses(courses);
  renderUpcoming(courses);
}

function renderStats(data) {
  const courses = data.courses || [];
  const graded = courses.filter((c) => typeof c.grade_percent === "number");
  const avg = graded.length
    ? graded.reduce((sum, c) => sum + c.grade_percent, 0) / graded.length
    : null;
  const missing = courses.reduce(
    (n, c) => n + (c.assignments || []).filter((a) => a.missing).length, 0);

  const tiles = [];
  if (data.gpa?.weighted != null) {
    tiles.push({
      label: "Weighted GPA",
      value: Number(data.gpa.weighted).toFixed(2),
      note: data.gpa.unweighted != null
        ? `${Number(data.gpa.unweighted).toFixed(2)} unweighted` : "",
    });
  }
  tiles.push({
    label: "Average",
    value: avg == null ? "—" : `${avg.toFixed(1)}%`,
    note: `across ${graded.length} course${graded.length === 1 ? "" : "s"}`,
    cls: gradeClass(avg),
  });
  tiles.push({
    label: "Missing work",
    value: String(missing),
    note: missing ? "needs attention" : "nothing missing",
    cls: missing ? "g-bad" : "g-good",
  });
  if (data.attendance) {
    tiles.push({
      label: "Attendance",
      value: `${data.attendance.absences ?? 0}`,
      note: `absences · ${data.attendance.tardies ?? 0} tardies`,
    });
  }

  $("#stats").innerHTML = tiles.map((t) => `
    <div class="stat">
      <div class="label">${esc(t.label)}</div>
      <div class="value ${t.cls || ""}">${esc(t.value)}</div>
      <div class="note">${esc(t.note || "")}</div>
    </div>`).join("");
}

function renderCourses(courses) {
  if (!courses.length) {
    $("#courses").innerHTML = `<div class="empty">No courses found.</div>`;
    return;
  }

  $("#courses").innerHTML = courses.map((c, i) => {
    const missing = (c.assignments || []).filter((a) => a.missing).length;
    const late = (c.assignments || []).filter((a) => a.late).length;
    const pct = typeof c.grade_percent === "number" ? `${c.grade_percent.toFixed(1)}` : "—";

    return `
      <div class="course" data-i="${i}">
        <button class="course-head" aria-expanded="false">
          <div>
            <div class="course-name">${esc(c.name || "Untitled course")}</div>
            <div class="course-meta">${esc([c.teacher, c.period, c.term].filter(Boolean).join(" · "))}</div>
          </div>
          <div class="flags">
            ${missing ? `<span class="pill missing">${missing} missing</span>` : ""}
            ${late ? `<span class="pill late">${late} late</span>` : ""}
          </div>
          <div class="grade ${gradeClass(c.grade_percent)}">
            ${pct}${c.grade_letter ? `<span class="letter">${esc(c.grade_letter)}</span>` : ""}
          </div>
        </button>
        <div class="assignments">${assignmentTable(c.assignments || [])}</div>
      </div>`;
  }).join("");

  document.querySelectorAll(".course-head").forEach((btn) => {
    btn.addEventListener("click", () => {
      const course = btn.closest(".course");
      const open = course.classList.toggle("open");
      btn.setAttribute("aria-expanded", String(open));
    });
  });
}

function assignmentTable(list) {
  if (!list.length) return `<div class="empty">No assignments listed.</div>`;

  const rows = [...list]
    .sort((a, b) => (b.due_date || "").localeCompare(a.due_date || ""))
    .map((a) => {
      const scored = a.score != null && a.score !== "";
      return `
        <tr>
          <td>${esc(formatDate(a.due_date))}</td>
          <td>
            ${esc(a.name || "")}
            ${a.missing ? ` <span class="pill missing">missing</span>` : ""}
            ${a.late ? ` <span class="pill late">late</span>` : ""}
          </td>
          <td class="cat">${esc(a.category || "")}</td>
          <td class="num">${scored ? `${esc(a.score)} / ${esc(a.points_possible ?? "—")}`
                                   : `— / ${esc(a.points_possible ?? "—")}`}</td>
          <td class="num ${gradeClass(a.percent)}">
            ${typeof a.percent === "number" ? `${a.percent.toFixed(1)}%` : ""}
          </td>
        </tr>`;
    }).join("");

  return `<table>
    <thead><tr><th>Due</th><th>Assignment</th><th>Category</th><th class="num">Score</th><th class="num">%</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

function renderUpcoming(courses) {
  const today = new Date().toISOString().slice(0, 10);
  const soon = [];

  courses.forEach((c) => {
    (c.assignments || []).forEach((a) => {
      // "Upcoming" = due today or later and not yet scored.
      if (a.due_date && a.due_date >= today && (a.score == null || a.score === "")) {
        soon.push({ ...a, course: c.name });
      }
    });
  });

  soon.sort((a, b) => (a.due_date || "").localeCompare(b.due_date || ""));

  $("#upcoming").innerHTML = soon.length
    ? `<table>
         <thead><tr><th>Due</th><th>Assignment</th><th>Course</th><th class="num">Points</th></tr></thead>
         <tbody>${soon.slice(0, 15).map((a) => `
           <tr>
             <td>${esc(formatDate(a.due_date))}</td>
             <td>${esc(a.name || "")}</td>
             <td class="cat">${esc(a.course || "")}</td>
             <td class="num">${esc(a.points_possible ?? "—")}</td>
           </tr>`).join("")}</tbody>
       </table>`
    : `<div class="empty">Nothing upcoming.</div>`;
}

/* helpers */
function gradeClass(pct) {
  if (typeof pct !== "number") return "";
  if (pct >= 90) return "g-good";
  if (pct >= 80) return "g-warn";
  return "g-bad";
}

function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(`${iso}T00:00:00`);
  if (isNaN(d)) return iso;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatSynced(iso) {
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

// Escape anything from the portal before putting it in the DOM -- assignment names are
// typed by teachers and could contain characters that break the HTML.
function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[ch]);
}
