// Shared helpers: API client, toasts, preferences and sound.

// ---------- preferences (per device) ----------
const PREF_PREFIX = "promitheus:";

export function getPref(key, fallback) {
  try {
    const value = localStorage.getItem(PREF_PREFIX + key);
    return value === null ? fallback : value;
  } catch {
    return fallback;
  }
}

export function setPref(key, value) {
  try {
    localStorage.setItem(PREF_PREFIX + key, value);
  } catch {
    /* private mode: preference just won't persist */
  }
}

export function applyTheme(pref = getPref("theme", "system")) {
  const dark = pref === "dark" || (pref === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

export function timezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

// ---------- API ----------
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export async function api(path, { method = "GET", body, form } = {}) {
  const headers = { Accept: "application/json", "X-Timezone": timezone() };
  const options = { method, headers, credentials: "same-origin" };
  if (form) {
    options.body = form;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new ApiError("You seem to be offline. Check your connection and try again.", 0);
  }

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (response.status === 401 && !location.pathname.startsWith("/login")) {
    location.href = "/login?next=" + encodeURIComponent(location.pathname + location.search);
    throw new ApiError("Your session ended. Log in again.", 401);
  }
  if (!response.ok) {
    let message = "Something went wrong. Try again.";
    if (typeof data?.detail === "string") message = data.detail;
    else if (Array.isArray(data?.detail) && data.detail[0]?.msg) message = data.detail[0].msg.replace(/^Value error, /, "");
    throw new ApiError(message, response.status);
  }
  return data;
}

// ---------- toasts ----------
export function toast(message, { tone = "info", duration = 4200 } = {}) {
  const region = document.getElementById("toasts");
  if (!region) return;
  const el = document.createElement("div");
  el.className = "toast pointer-events-auto";
  el.dataset.tone = tone;
  el.setAttribute("role", tone === "error" ? "alert" : "status");
  el.textContent = message;
  region.appendChild(el);
  setTimeout(() => {
    el.style.transition = "opacity 200ms ease";
    el.style.opacity = "0";
    setTimeout(() => el.remove(), 220);
  }, duration);
}

// Show a toast on the next page (after a redirect).
export function flash(message, tone = "info") {
  try {
    sessionStorage.setItem(PREF_PREFIX + "flash", JSON.stringify({ message, tone }));
  } catch {
    /* ignore */
  }
}

export function showFlash() {
  try {
    const raw = sessionStorage.getItem(PREF_PREFIX + "flash");
    if (!raw) return;
    sessionStorage.removeItem(PREF_PREFIX + "flash");
    const { message, tone } = JSON.parse(raw);
    toast(message, { tone });
  } catch {
    /* ignore */
  }
}

// ---------- confirm dialog ----------
export function confirmDialog({ title, body, confirmLabel = "Confirm", danger = false }) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.className = "modal";
    dialog.innerHTML = `
      <form method="dialog" class="p-6">
        <h2 class="text-xl font-bold"></h2>
        <p class="mt-2 text-muted"></p>
        <div class="mt-6 flex flex-col-reverse sm:flex-row gap-3 sm:justify-end">
          <button value="cancel" class="btn btn-secondary">Cancel</button>
          <button value="ok" class="btn ${danger ? "btn-bad" : "btn-primary"}"></button>
        </div>
      </form>`;
    dialog.querySelector("h2").textContent = title;
    dialog.querySelector("p").textContent = body;
    dialog.querySelector('button[value="ok"]').textContent = confirmLabel;
    document.body.appendChild(dialog);
    dialog.addEventListener("close", () => {
      resolve(dialog.returnValue === "ok");
      dialog.remove();
    });
    dialog.showModal();
  });
}

// ---------- button busy state ----------
export function setBusy(button, busy, busyLabel) {
  if (!button) return;
  if (busy) {
    button.dataset.label = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span><span>${busyLabel ?? "Working…"}</span>`;
  } else {
    button.disabled = false;
    if (button.dataset.label) button.innerHTML = button.dataset.label;
  }
}

// ---------- sound ----------
// Short, quiet synthesized tones (no audio files). Muted with the header toggle.
let audioCtx = null;

export function soundEnabled() {
  return getPref("sound", "on") === "on";
}

export function setSoundEnabled(on) {
  setPref("sound", on ? "on" : "off");
}

function context() {
  if (!audioCtx) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    audioCtx = new Ctx();
  }
  if (audioCtx.state === "suspended") audioCtx.resume();
  return audioCtx;
}

function tone({ freq, to, type = "sine", start = 0, dur = 0.16, gain = 0.06 }) {
  const ctx = context();
  if (!ctx) return;
  const volume = Number(getPref("volume", "0.7"));
  const t = ctx.currentTime + start;
  const osc = ctx.createOscillator();
  const filter = ctx.createBiquadFilter();
  const amp = ctx.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t);
  if (to) osc.frequency.exponentialRampToValueAtTime(to, t + dur);
  filter.type = "lowpass";
  filter.frequency.value = 2200;
  amp.gain.setValueAtTime(0.0001, t);
  amp.gain.exponentialRampToValueAtTime(Math.max(0.0002, gain * volume), t + 0.015);
  amp.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  osc.connect(filter).connect(amp).connect(ctx.destination);
  osc.start(t);
  osc.stop(t + dur + 0.05);
}

const SOUNDS = {
  correct() {
    tone({ freq: 659.25, dur: 0.13, gain: 0.07 }); // E5
    tone({ freq: 987.77, start: 0.08, dur: 0.24, gain: 0.06 }); // B5
  },
  wrong() {
    tone({ freq: 233.08, to: 196, type: "triangle", dur: 0.24, gain: 0.08 });
  },
  complete() {
    [523.25, 659.25, 783.99, 1046.5].forEach((freq, i) => tone({ freq, start: i * 0.09, dur: 0.3, gain: 0.05 }));
  },
  tap() {
    tone({ freq: 740, dur: 0.05, gain: 0.02 });
  },
};

export function play(name) {
  if (!soundEnabled() || !SOUNDS[name]) return;
  try {
    SOUNDS[name]();
  } catch {
    /* audio unavailable */
  }
}
