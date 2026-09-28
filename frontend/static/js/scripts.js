// ==========================================
// 🔊 AUDIO MANAGER
// ==========================================
const sfx = {
  pop: new Audio("/static/audio/pop.mp3"),
  success: new Audio("/static/audio/final-success.mp3"),
  whoosh: new Audio("/static/audio/whoosh.mp3"),
  correct: new Audio("/static/audio/success.mp3"),
  wrong: new Audio("/static/audio/wrong.mp3"),
};

// Lower the volume a bit so it isn't deafening
Object.values(sfx).forEach((audio) => (audio.volume = 0.5));

function playSound(type) {
  if (!sfx[type]) return;
  // Reset to 0 so you can rapidly click and hear it every time
  sfx[type].currentTime = 0;
  // Browsers block audio until the user interacts with the page
  sfx[type].play().catch(() => {});
}

// ==========================================
// 🧰 HELPERS
// ==========================================
const TOKEN_KEY = "promitheus_token";
const LEAGUE_EMOJIS = {
  Paper: "📄",
  Iron: "⛓️",
  Bronze: "🥉",
  Silver: "🥈",
  Gold: "🥇",
  Platinum: "💎",
  Diamond: "👑",
};

// Anything that came from a user, a file or the AI must go through this before innerHTML.
function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function saveSession(data) {
  localStorage.setItem(TOKEN_KEY, data.access_token);
  localStorage.setItem("username", data.username);
}

function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem("username");
}

function userTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

// Single place for talking to the backend: adds the token and timezone,
// parses JSON, and sends the user to /login when their session has expired.
async function api(path, { method = "GET", body, formData } = {}) {
  const headers = { "X-Timezone": userTimezone() };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const options = { method, headers };
  if (formData) {
    options.body = formData;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  const response = await fetch(path, options);
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (response.status === 401 && window.location.pathname !== "/login") {
    clearSession();
    window.location.href = "/login";
    throw new ApiError("Please log in again.", 401);
  }
  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    if (typeof data?.detail === "string") message = data.detail;
    else if (Array.isArray(data?.detail) && data.detail[0]?.msg)
      message = data.detail[0].msg.replace(/^Value error, /, "");
    throw new ApiError(message, response.status);
  }
  return data;
}

// /users/me is needed by several widgets on the same page; fetch it once.
let mePromise = null;
function getMe() {
  if (!mePromise) {
    mePromise = api("/users/me").catch((err) => {
      mePromise = null;
      throw err;
    });
  }
  return mePromise;
}

function showNotification(message, type = "success") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `${type === "success" ? "bg-[#58cc02]" : "bg-[#ff4b4b]"} text-white px-6 py-4 rounded-2xl shadow-xl font-bold mb-2 transition-all duration-300 toast-pop`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// ==========================================
// 🚀 INIT
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname;

  // Every page except /login needs a session.
  if (path !== "/login" && !getToken()) {
    window.location.href = "/login";
    return;
  }
  if (path === "/login" && getToken()) {
    window.location.href = "/dashboard";
    return;
  }

  const savedTheme =
    localStorage.getItem("theme") ||
    (window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light");
  applyTheme(savedTheme);
  updateUI();

  if (path === "/login") return;

  fetchUserStats();

  if (path === "/" || path === "/dashboard") fetchLessons();
  if (path === "/quests") {
    updateQuestTimers();
    setInterval(updateQuestTimers, 60000);
  }
  if (path === "/streaks") renderStreakCalendar();
  if (path === "/leaderboard") renderLeaderboard();
  if (path === "/profile") renderProfile();

  if (path.startsWith("/quiz/")) {
    const lessonId = path.split("/").filter(Boolean).pop();
    if (lessonId) startQuiz(lessonId);

    const nextBtn = document.getElementById("next-question-btn");
    if (nextBtn) {
      nextBtn.onclick = () => {
        document
          .getElementById("quiz-feedback-bar")
          .classList.add("translate-y-full");
        nextQuestion();
      };
    }
  }
});

// ==========================================
// 🎨 THEME ENGINE
// ==========================================
function applyTheme(theme) {
  const html = document.documentElement;
  const themeBtn = document.getElementById("theme-toggle");
  if (theme === "dark") {
    html.classList.add("dark");
    if (themeBtn) themeBtn.textContent = "☀️";
  } else {
    html.classList.remove("dark");
    if (themeBtn) themeBtn.textContent = "🌙";
  }
  localStorage.setItem("theme", theme);
}

function toggleTheme() {
  const newTheme = document.documentElement.classList.contains("dark")
    ? "light"
    : "dark";
  applyTheme(newTheme);
}

// ==========================================
// 🔐 AUTH & UI
// ==========================================
let isLoginMode = true;

function updateUI() {
  const token = getToken();
  const username = localStorage.getItem("username");
  const path = window.location.pathname;

  const sidebarUsername = document.getElementById("sidebar-username");
  const logoutBtn = document.getElementById("logout-btn");
  const loginBtn = document.getElementById("login-btn");

  if (token && username) {
    if (sidebarUsername) sidebarUsername.textContent = username;
    if (logoutBtn) logoutBtn.classList.remove("hidden");
    if (loginBtn) loginBtn.classList.add("hidden");
  } else {
    if (sidebarUsername) sidebarUsername.textContent = "Guest";
    if (logoutBtn) logoutBtn.classList.add("hidden");
    if (loginBtn) loginBtn.classList.remove("hidden");
  }

  // Sidebar highlighting
  document
    .querySelectorAll(".nav-item")
    .forEach((link) => link.classList.remove("active"));
  let activeId = null;
  if (path.startsWith("/leaderboard")) activeId = "nav-leaderboard";
  else if (path.startsWith("/quests")) activeId = "nav-quests";
  else if (path.startsWith("/profile")) activeId = "nav-profile";
  else if (path === "/" || path.startsWith("/dashboard")) activeId = "nav-learn";
  if (activeId) document.getElementById(activeId)?.classList.add("active");
}

async function handleAuth() {
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;
  const email = document.getElementById("email")?.value.trim() || "";
  const authBtn = document.getElementById("auth-btn");

  const endpoint = isLoginMode ? "/auth/login" : "/auth/register";
  const payload = isLoginMode
    ? { username, password }
    : { username, email, password };

  authBtn.disabled = true;
  try {
    const data = await api(endpoint, { method: "POST", body: payload });
    saveSession(data);
    if (!isLoginMode) showNotification("Account created! Welcome 🔥", "success");
    window.location.href = "/dashboard";
  } catch (error) {
    showNotification(error.message || "Connection failed!", "error");
  } finally {
    authBtn.disabled = false;
  }
}

// Called by Google Identity Services after a successful popup login
async function handleGoogleLogin(response) {
  try {
    const data = await api("/auth/google", {
      method: "POST",
      body: { credential: response.credential },
    });
    saveSession(data);
    showNotification("Successfully logged in with Google! 🔥", "success");
    setTimeout(() => (window.location.href = "/dashboard"), 1000);
  } catch (err) {
    showNotification(err.message || "Google authentication failed", "error");
  }
}

function logout() {
  clearSession();
  window.location.href = "/login";
}

function toggleAuthMode() {
  isLoginMode = !isLoginMode;
  document.getElementById("auth-title").textContent = isLoginMode
    ? "Welcome Back"
    : "Create Account";
  document.getElementById("email").classList.toggle("hidden", isLoginMode);
  document.getElementById("username").placeholder = isLoginMode
    ? "Username or email"
    : "Username";
  document.getElementById("password").autocomplete = isLoginMode
    ? "current-password"
    : "new-password";
  document.getElementById("auth-btn").textContent = isLoginMode
    ? "Login"
    : "Sign Up";
  document.getElementById("toggle-text").textContent = isLoginMode
    ? "Don't have an account?"
    : "Already have an account?";
}

// ==========================================
// 💎 USER STATS & QUEST WIDGETS
// ==========================================
function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function fillQuestBar({ bar, text, chest, value, goal, delay, claimable }) {
  const barEl = document.getElementById(bar);
  const textEl = document.getElementById(text);
  const chestEl = document.getElementById(chest);
  if (!barEl || !textEl) return;

  const shown = Math.min(value, goal);
  setTimeout(() => {
    barEl.style.width = `${(shown / goal) * 100}%`;
    textEl.textContent = `${shown}/${goal}`;
    if (value < goal || !chestEl) return;

    chestEl.classList.remove("grayscale", "opacity-40");
    if (!claimable) {
      chestEl.classList.add("drop-shadow-lg", "scale-110");
      return;
    }
    // Wake the chest up and wait for the click
    if (!chestEl.classList.contains("claimed")) {
      chestEl.classList.add("ready-to-claim");
      chestEl.onclick = () => {
        chestEl.classList.remove("ready-to-claim");
        chestEl.classList.add("animate-chest-pop", "claimed");
        chestEl.textContent = "✅";
        playSound("pop");
      };
    }
  }, delay);
}

async function fetchUserStats() {
  let me;
  try {
    me = await getMe();
  } catch (error) {
    console.error("Failed to fetch stats", error);
    return;
  }

  // Top nav
  setText("xp-display", `${me.xp} XP`);
  setText("xp-hover-text", me.xp);
  setText("streak-display", me.streak);
  setText("streak-hover-text", me.streak);
  setText("streak-page-count", me.streak);

  const goals = me.goals;

  // Right sidebar (most pages)
  fillQuestBar({
    bar: "quest-1-bar",
    text: "quest-1-text",
    chest: "quest-1-chest",
    value: me.daily_xp,
    goal: goals.daily_xp,
    delay: 300,
    claimable: true,
  });
  fillQuestBar({
    bar: "quest-2-bar",
    text: "quest-2-text",
    chest: "quest-2-chest",
    value: me.daily_lessons,
    goal: goals.daily_lessons,
    delay: 500,
    claimable: true,
  });

  // Dedicated quests page
  if (window.location.pathname === "/quests") {
    fillQuestBar({
      bar: "qpage-xp-bar",
      text: "qpage-xp-text",
      chest: "qpage-xp-chest",
      value: me.daily_xp,
      goal: goals.daily_xp,
      delay: 300,
    });
    fillQuestBar({
      bar: "qpage-lesson-bar",
      text: "qpage-lesson-text",
      chest: "qpage-lesson-chest",
      value: me.daily_lessons,
      goal: goals.daily_lessons,
      delay: 500,
    });

    const monthly = Math.min(me.month_quests, goals.monthly_quests);
    setTimeout(() => {
      const monthlyBar = document.getElementById("monthly-bar");
      if (monthlyBar)
        monthlyBar.style.width = `${(monthly / goals.monthly_quests) * 100}%`;
      setText("monthly-text", `${monthly} / ${goals.monthly_quests}`);
    }, 700);

    if (monthly >= goals.monthly_quests) {
      document
        .getElementById("month-badge-card")
        ?.classList.remove("opacity-50", "grayscale");
      setText("sidebar-month-badge-status", "Badge earned! 🎉");
    }
  }
}

// ==========================================
// 🐍 STUDY PATH
// ==========================================
async function fetchLessons() {
  const pathContainer = document.getElementById("study-path");
  if (!pathContainer) return;

  try {
    const lessons = await api("/lessons/");

    if (lessons.length === 0) {
      pathContainer.innerHTML = `<div class="p-6 text-center text-slate-400 font-bold mt-10">Upload a lecture to begin.</div>`;
      return;
    }

    // Group lessons into units (one unit per uploaded lecture), keeping upload order.
    const units = new Map();
    lessons.forEach((l) => {
      if (!units.has(l.material_id)) units.set(l.material_id, []);
      units.get(l.material_id).push(l);
    });

    pathContainer.innerHTML = "";
    let isPreviousUnitComplete = true;

    const unitColors = [
      { bg: "bg-[#58cc02]", border: "border-[#46a302]" },
      { bg: "bg-[#ce82ff]", border: "border-[#a568cc]" },
      { bg: "bg-[#1cb0f6]", border: "border-[#1899d6]" },
      { bg: "bg-[#ff9600]", border: "border-[#cc7800]" },
    ];

    [...units.values()].forEach((unitLessons, unitIndex) => {
      const isUnitLocked = !isPreviousUnitComplete;
      const isUnitComplete = unitLessons.every((l) => l.is_completed);
      const unitTitle = unitLessons[0].unit_title || "New Unit";
      const color = unitColors[unitIndex % unitColors.length];

      const headerBox = document.createElement("div");
      headerBox.className = `w-full ${color.bg} text-white p-6 rounded-3xl shadow-md mb-8 relative overflow-hidden border-b-4 ${color.border}`;
      headerBox.innerHTML = `
          <div class="relative z-10">
              <p class="uppercase font-black text-sm opacity-90 tracking-wider mb-1">UNIT ${unitIndex + 1}</p>
              <h2 class="text-2xl font-black">${escapeHtml(unitTitle)}</h2>
          </div>
          <div class="absolute right-[-10px] top-[-20px] opacity-20 text-8xl">💧</div>
      `;
      pathContainer.appendChild(headerBox);

      const snakeContainer = document.createElement("div");
      snakeContainer.className = `flex flex-col items-center gap-6 py-4 w-full transition-all duration-500 ${isUnitLocked ? "opacity-40 grayscale pointer-events-none" : ""}`;

      unitLessons.forEach((lesson, index) => {
        let stateClass = "node-current";
        let icon = "⭐";
        if (index === 1) icon = "📖";
        if (index === 4) icon = "🧰";
        if (index === 5) icon = "🏆";

        if (lesson.is_completed) {
          stateClass = "node-completed";
          icon = "✔";
        } else if (index > 0 && !unitLessons[index - 1].is_completed) {
          stateClass = "node-locked";
          icon = "🔒";
        }

        let tooltipHtml = `<div class="path-tooltip">${escapeHtml(lesson.title)}</div>`;
        if (stateClass === "node-current" && !isUnitLocked) {
          tooltipHtml = `<div class="path-tooltip active-tooltip">START</div>`;
        }

        const node = document.createElement("div");
        node.className = `path-node ${stateClass}`;
        if (stateClass !== "node-locked" && !isUnitLocked) {
          node.onclick = () => (window.location.href = `/quiz/${lesson.id}`);
        }
        node.innerHTML = `${icon}${tooltipHtml}`;
        snakeContainer.appendChild(node);
      });

      pathContainer.appendChild(snakeContainer);
      isPreviousUnitComplete = isUnitComplete;
    });
  } catch (error) {
    console.error(error);
    pathContainer.innerHTML = `<div class="text-red-500 font-bold text-center">Failed to load study path.</div>`;
  }
}

async function uploadLecture() {
  const fileInput = document.getElementById("lecture-file");
  const uploadBtn = document.getElementById("upload-btn");
  if (fileInput.files.length === 0)
    return showNotification("Select a file!", "error");

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  uploadBtn.textContent = "Generating... 🧠";
  uploadBtn.disabled = true;

  try {
    const data = await api("/upload/lecture", { method: "POST", formData });
    showNotification(data.message || "Lesson ready!", "success");
    fileInput.value = "";
    fetchLessons();
  } catch (error) {
    showNotification(error.message || "Upload failed", "error");
  } finally {
    uploadBtn.textContent = "Generate with AI ✨";
    uploadBtn.disabled = false;
  }
}

// ==========================================
// 📝 QUIZ
// ==========================================
let attemptId = null;
let currentQuestions = [];
let currentQuestionIndex = 0;
let timerInterval;
let timeLeft = 600; // 10 minutes

function startTimer() {
  clearInterval(timerInterval);
  timeLeft = 600;

  let timerDisplay = document.getElementById("quiz-timer");
  if (!timerDisplay) {
    const targetElement = document.getElementById("question-header");
    if (targetElement) {
      timerDisplay = document.createElement("div");
      timerDisplay.id = "quiz-timer";
      timerDisplay.className =
        "text-2xl font-black text-[#E2E8F0] text-center mb-6 font-mono bg-[#4f46e5] py-2 rounded-xl border-2 border-[#E2E8F0] w-fit px-6";
      targetElement.parentNode.insertBefore(timerDisplay, targetElement);
    }
  }
  if (timerDisplay) timerDisplay.textContent = "⏱️ 10:00";

  timerInterval = setInterval(() => {
    timeLeft--;
    const m = Math.floor(timeLeft / 60)
      .toString()
      .padStart(2, "0");
    const s = (timeLeft % 60).toString().padStart(2, "0");
    if (timerDisplay) timerDisplay.textContent = `⏱️ ${m}:${s}`;

    if (timeLeft <= 0) {
      clearInterval(timerInterval);
      showNotification("Time is up!", "error");
      document
        .querySelectorAll("button, input, textarea")
        .forEach((el) => (el.disabled = true));
      setTimeout(() => (window.location.href = "/dashboard"), 2000);
    }
  }, 1000);
}

async function startQuiz(lessonId) {
  try {
    const data = await api(`/lessons/${encodeURIComponent(lessonId)}/attempts`, {
      method: "POST",
    });
    attemptId = data.attempt_id;
    currentQuestions = data.questions || [];

    if (currentQuestions.length > 0) {
      currentQuestionIndex = 0;
      startTimer();
      showQuestion();
    } else {
      setText("sentence-container", "No questions found.");
    }
  } catch (err) {
    console.error("Quiz Initialization Error:", err);
    setText("sentence-container", "Could not load this lesson.");
    showNotification(err.message || "Failed to load questions.", "error");
  }
}

function makeButton(label, className, onClick) {
  const btn = document.createElement("button");
  btn.textContent = label;
  btn.className = className;
  btn.onclick = onClick;
  return btn;
}

const CHECK_BTN_CLASS =
  "w-full bg-[#58cc02] text-white py-4 rounded-xl font-bold shadow-[0_4px_0_#46a302] active:translate-y-1 active:shadow-none transition-all uppercase tracking-widest";

function showQuestion() {
  const q = currentQuestions[currentQuestionIndex];
  if (!q) return;

  const sentenceContainer = document.getElementById("sentence-container");
  const optionsContainer = document.getElementById("options-container");
  const header = document.getElementById("question-header");
  const progressBar = document.getElementById("progress-bar");

  optionsContainer.innerHTML = "";
  sentenceContainer.textContent = "";

  if (progressBar) {
    const progress = (currentQuestionIndex / currentQuestions.length) * 100;
    progressBar.style.width = `${Math.max(progress, 5)}%`;
  }

  const headers = {
    fill_blank: "Fill in the blank",
    short_answer: "Answer the question",
    explain: "Explain your answer",
    rearrange: "Form the correct sentence",
  };
  header.textContent = headers[q.type] || "Select the correct option";

  // Question text (built with text nodes so AI output can't inject HTML)
  const promptText = q.data.prompt || "Question text missing";
  if (q.type === "fill_blank") {
    const match = promptText.match(/_{2,}/);
    if (match) {
      const blank = document.createElement("span");
      blank.className = "quiz-blank";
      sentenceContainer.append(
        promptText.slice(0, match.index),
        blank,
        promptText.slice(match.index + match[0].length),
      );
    } else {
      sentenceContainer.textContent = promptText;
    }
  } else {
    sentenceContainer.textContent = promptText;
  }

  if (q.type === "multiple_choice" || q.type === "true_false") {
    (q.data.options || []).forEach((opt) => {
      const btn = makeButton(opt, "option-btn", () =>
        submitAnswer(q, opt, btn),
      );
      optionsContainer.appendChild(btn);
    });
  } else if (q.type === "fill_blank" || q.type === "short_answer") {
    const input = document.createElement("input");
    input.className =
      "w-full p-4 border-2 rounded-2xl bg-white dark:bg-slate-800 text-slate-800 dark:text-white outline-none mb-4";
    input.placeholder = "Type your answer here...";
    input.maxLength = 200;

    const check = () => {
      if (!input.value.trim())
        return showNotification("Type an answer first!", "error");
      submitAnswer(q, input.value.trim(), input, btn);
    };
    const btn = makeButton("Check", CHECK_BTN_CLASS, check);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !btn.disabled) check();
    });

    optionsContainer.append(input, btn);
    input.focus();
  } else if (q.type === "rearrange") {
    renderRearrange(q, optionsContainer);
  } else if (q.type === "explain") {
    const textarea = document.createElement("textarea");
    textarea.id = "explain-input";
    textarea.maxLength = 2000;
    textarea.className =
      "w-full p-4 border-2 border-slate-200 dark:border-slate-700 rounded-2xl bg-white dark:bg-slate-800 text-slate-800 dark:text-white outline-none mb-4 min-h-[150px] resize-y focus:border-[#1cb0f6] transition-colors";
    textarea.placeholder = "Type your explanation here...";

    const btn = makeButton(
      "Submit for AI Review ✨",
      "w-full bg-[#1cb0f6] text-white py-4 rounded-xl font-bold shadow-[0_4px_0_#1899d6] active:translate-y-1 active:shadow-none transition-all uppercase tracking-widest",
      () => {
        if (!textarea.value.trim())
          return showNotification("Please write an answer first!", "error");
        submitAnswer(q, textarea.value, textarea, btn, "AI is grading... 🧠");
      },
    );
    optionsContainer.append(textarea, btn);
  }
}

function renderRearrange(q, optionsContainer) {
  const chunks = q.data.chunks || [];
  // Track chunk indexes (not text) so repeated words work.
  const selected = [];

  const dropZone = document.createElement("div");
  dropZone.className =
    "w-full min-h-[80px] p-4 border-4 border-dashed border-slate-200 dark:border-slate-800 rounded-2xl mb-4 flex flex-wrap gap-2 items-center bg-slate-50 dark:bg-slate-900/50";
  const wordBank = document.createElement("div");
  wordBank.className = "flex flex-wrap gap-2";

  const render = () => {
    dropZone.innerHTML =
      selected.length === 0
        ? '<span class="text-slate-400 font-bold mx-auto">Click words to build the sentence</span>'
        : "";
    wordBank.innerHTML = "";

    selected.forEach((chunkIdx, pos) => {
      dropZone.appendChild(
        makeButton(
          chunks[chunkIdx],
          "px-4 py-2 bg-indigo-500 text-white font-bold rounded-lg shadow-sm",
          () => {
            selected.splice(pos, 1);
            render();
          },
        ),
      );
    });

    chunks.forEach((word, idx) => {
      if (selected.includes(idx)) return;
      wordBank.appendChild(
        makeButton(
          word,
          "px-4 py-2 bg-white dark:bg-slate-800 border-2 border-slate-200 dark:border-slate-700 font-bold rounded-lg hover:border-indigo-500 transition-colors",
          () => {
            selected.push(idx);
            render();
          },
        ),
      );
    });
  };

  const checkBtn = makeButton("Check Order", `${CHECK_BTN_CLASS} mt-6`, () => {
    if (selected.length !== chunks.length)
      return showNotification("Use all the pieces first!", "error");
    dropZone
      .querySelectorAll("button")
      .forEach((b) => (b.disabled = true));
    wordBank.innerHTML = "";
    submitAnswer(
      q,
      selected.map((i) => chunks[i]),
      dropZone,
      checkBtn,
    );
  });

  optionsContainer.append(dropZone, wordBank, checkBtn);
  render();
}

async function submitAnswer(q, answer, element, button, loadingText) {
  const controls = document.querySelectorAll(
    "#options-container button, #options-container input, #options-container textarea",
  );
  controls.forEach((el) => (el.disabled = true));
  const originalLabel = button?.textContent;
  if (button && loadingText) {
    button.textContent = loadingText;
    button.classList.add("opacity-75", "cursor-wait");
  }

  try {
    const result = await api(`/attempts/${attemptId}/answers`, {
      method: "POST",
      body: { question_id: q.question_id, answer },
    });
    showFeedback(q, result, element);
  } catch (err) {
    showNotification(err.message || "Could not check your answer.", "error");
    // Let the user try again unless the server already has an answer recorded.
    if (err.status !== 409) {
      controls.forEach((el) => (el.disabled = false));
      if (q.type === "rearrange") showQuestion();
    }
    if (button && loadingText) {
      button.textContent = originalLabel;
      button.classList.remove("opacity-75", "cursor-wait");
    }
  }
}

function showFeedback(q, result, element) {
  const feedbackBar = document.getElementById("quiz-feedback-bar");
  const iconCircle = document.getElementById("feedback-icon-circle");
  const icon = document.getElementById("feedback-icon");
  const title = document.getElementById("feedback-title");
  const solutionText = document.getElementById("feedback-solution");
  const continueBtn = document.getElementById("next-question-btn");

  feedbackBar.classList.remove(
    "translate-y-full",
    "bg-[#d7ffb8]",
    "bg-[#ffdfe0]",
    "border-[#b8f28b]",
    "border-[#f4c2c2]",
  );
  title.classList.remove("text-[#58a700]", "text-[#ea2b2b]");
  solutionText.textContent = "";

  if (result.correct) {
    playSound("correct");
    element?.classList.add("is-correct-selection");
    feedbackBar.classList.add("bg-[#d7ffb8]", "border-[#b8f28b]");
    iconCircle.className =
      "w-20 h-20 rounded-full flex items-center justify-center text-4xl bg-white text-[#58cc02]";
    icon.textContent = "✔";
    title.textContent =
      q.type === "explain" ? "Great explanation!" : "You are correct!";
    title.classList.add("text-[#58a700]");
    // For explanations, the AI says what you got right
    solutionText.textContent = result.feedback || "";
    solutionText.className = "font-bold text-lg text-[#58a700] mt-2";
    continueBtn.className =
      "px-12 py-4 rounded-2xl font-black text-xl bg-[#58cc02] text-white uppercase tracking-widest shadow-[0_4px_0_#46a302]";
  } else {
    playSound("wrong");
    element?.classList.add("is-wrong-selection", "animate-shake");
    feedbackBar.classList.add("bg-[#ffdfe0]", "border-[#f4c2c2]");
    iconCircle.className =
      "w-20 h-20 rounded-full flex items-center justify-center text-4xl bg-white text-[#ea2b2b]";
    icon.textContent = "✖";
    title.classList.add("text-[#ea2b2b]");
    if (q.type === "explain") {
      title.textContent = "Not quite right:";
      const label = document.createElement("span");
      label.className =
        "font-black uppercase tracking-wider text-sm opacity-80 mr-2";
      label.textContent = "Ideal Answer:";
      const answer = document.createElement("span");
      answer.className = "font-bold";
      answer.textContent = result.correct_answer;
      solutionText.append(label, answer);
      solutionText.className = "text-lg text-[#ea2b2b] mt-1";
    } else {
      title.textContent = "Correct solution:";
      solutionText.textContent = result.correct_answer;
      solutionText.className = "font-bold text-lg text-[#ea2b2b]";
    }
    continueBtn.className =
      "px-12 py-4 rounded-2xl font-black text-xl bg-[#ff4b4b] text-white uppercase tracking-widest shadow-[0_4px_0_#af2323]";
  }
  continueBtn.disabled = false;
}

async function nextQuestion() {
  currentQuestionIndex++;
  if (currentQuestionIndex < currentQuestions.length) {
    showQuestion();
    return;
  }

  // 🏆 Quiz complete: the server counts the score and awards XP.
  clearInterval(timerInterval);
  const continueBtn = document.getElementById("next-question-btn");
  if (continueBtn) continueBtn.disabled = true;
  const progressBar = document.getElementById("progress-bar");
  if (progressBar) progressBar.style.width = "100%";

  try {
    const result = await api(`/attempts/${attemptId}/complete`, {
      method: "POST",
    });
    playSound("success");
    const xpText =
      result.xp_awarded > 0
        ? `+${result.xp_awarded} XP 🌟`
        : "(replays are practice, no XP)";
    showNotification(
      `Lesson complete! ${result.correct}/${result.total} correct ${xpText}`,
      "success",
    );
  } catch (err) {
    console.error("Failed to save progress:", err);
    showNotification(err.message || "Could not save your progress.", "error");
  }

  setTimeout(() => (window.location.href = "/dashboard"), 2500);
}

// ==========================================
// ⏱️ QUEST TIMERS
// ==========================================
function updateQuestTimers() {
  const now = new Date();
  const monthName = now.toLocaleString("default", { month: "long" });

  setText("dynamic-month-badge", monthName);
  setText("dynamic-month-title", `${monthName} Quest`);
  setText("sidebar-month-badge", `${monthName} Quest`);

  const lastDayOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  const daysLeft = lastDayOfMonth.getDate() - now.getDate();
  setText("monthly-timer", `⏱️ ${daysLeft} DAYS`);

  // Daily quests reset at the user's local midnight (the server uses the same timezone).
  const midnight = new Date(now);
  midnight.setHours(24, 0, 0, 0);
  const diffMs = midnight - now;
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffMins = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
  setText(
    "daily-timer",
    diffHours === 0 ? `⏱️ ${diffMins} MINS` : `⏱️ ${diffHours} HOURS`,
  );
}

// ==========================================
// 🔥 STREAK CALENDAR
// ==========================================
let currentViewDate = new Date();

function toDateKey(d) {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

async function renderStreakCalendar(targetDate = new Date()) {
  const mount = document.getElementById("streak-calendar-mount");
  if (!mount) return;

  try {
    const me = await getMe();

    // The streak is a run of consecutive days ending on the last lesson date.
    const completedDates = new Set();
    if (me.streak > 0 && me.last_lesson_date) {
      const [y, m, d] = me.last_lesson_date.split("-").map(Number);
      for (let i = 0; i < me.streak; i++) {
        completedDates.add(toDateKey(new Date(y, m - 1, d - i)));
      }
    }

    const year = targetDate.getFullYear();
    const month = targetDate.getMonth();
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const monthName = targetDate.toLocaleString("default", { month: "long" });
    const todayKey = toDateKey(new Date());

    let html = `
            <div class="calendar-container w-full max-w-md mx-auto">
                <div class="flex justify-between items-center mb-8">
                    <button onclick="changeMonth(-1)" class="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition-colors text-slate-500">◀</button>
                    <h4 class="text-xl font-black text-slate-800 dark:text-slate-200">${escapeHtml(monthName)} ${year}</h4>
                    <button onclick="changeMonth(1)" class="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition-colors text-slate-500">▶</button>
                </div>

                <div class="grid grid-cols-7 gap-2 text-center text-xs font-bold text-slate-400 mb-4">
                    <div>SUN</div><div>MON</div><div>TUE</div><div>WED</div><div>THU</div><div>FRI</div><div>SAT</div>
                </div>

                <div class="grid grid-cols-7 gap-y-6 justify-items-center">
        `;

    for (let i = 0; i < firstDay; i++) html += `<div></div>`;

    for (let day = 1; day <= daysInMonth; day++) {
      const dateKey = toDateKey(new Date(year, month, day));
      if (completedDates.has(dateKey)) {
        html += `
                    <div class="relative group cursor-pointer">
                        <span class="text-2xl absolute -top-5 left-1/2 -translate-x-1/2 animate-bounce drop-shadow-md">🔥</span>
                        <div class="h-10 w-10 rounded-full bg-orange-500 flex items-center justify-center font-black text-white shadow-[0_0_15px_rgba(249,115,22,0.4)] scale-110">
                            ${day}
                        </div>
                    </div>`;
      } else if (dateKey === todayKey) {
        html += `
                    <div class="h-10 w-10 rounded-full border-2 border-orange-500 flex items-center justify-center font-bold text-orange-500">
                        ${day}
                    </div>`;
      } else {
        html += `
                    <div class="h-10 w-10 flex items-center justify-center font-bold text-slate-400 hover:text-slate-600 transition-colors">
                        ${day}
                    </div>`;
      }
    }

    html += `</div></div>`;
    mount.innerHTML = html;

    if (me.streak > 0) setTimeout(() => playSound("whoosh"), 300);
  } catch (error) {
    console.error("Calendar Error:", error);
    mount.innerHTML = `<p class="text-red-500 text-center font-bold">Unable to sync history.</p>`;
  }
}

function changeMonth(offset) {
  currentViewDate.setMonth(currentViewDate.getMonth() + offset);
  renderStreakCalendar(currentViewDate);
}

// ==========================================
// 🛡️ LEADERBOARD
// ==========================================
const ZONE_HEADERS = {
  promote: (board) =>
    `<div class="bg-emerald-500/10 text-emerald-500 font-bold text-[10px] uppercase tracking-[0.2em] p-3 text-center border-y border-emerald-500/10">🚀 Promotion Zone — Top ${board.promote_count} promote to ${escapeHtml(board.next_league)}</div>`,
  safe: () =>
    `<div class="bg-slate-500/10 text-slate-400 font-bold text-[10px] uppercase tracking-[0.2em] p-3 text-center border-y border-slate-500/10">🛡️ Safe Zone</div>`,
  demote: () =>
    `<div class="bg-red-500/10 text-red-500 font-bold text-[10px] uppercase tracking-[0.2em] p-3 text-center border-y border-red-500/10">⚠️ Demotion Zone</div>`,
};

function leaderboardRow(entry, league) {
  let rankDisplay = `<span class="font-black text-slate-500 w-8 text-center text-lg">${entry.rank}</span>`;
  const medals = { 1: "🥇", 2: "🥈", 3: "🥉" };
  if (medals[entry.rank])
    rankDisplay = `<span class="text-3xl w-8 text-center drop-shadow-sm">${medals[entry.rank]}</span>`;

  let borderClass = "border-l-4 border-transparent";
  if (entry.zone === "promote")
    borderClass = "border-l-4 border-emerald-500 bg-emerald-500/[0.02]";
  if (entry.zone === "demote")
    borderClass = "border-l-4 border-red-500 bg-red-500/[0.02]";
  if (entry.is_me) borderClass = "border-l-4 border-blue-500 bg-blue-500/10";

  const avatarUrl = `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(entry.username)}&backgroundColor=c0aede,d1d4f9,b6e3f4`;

  return `
        <div class="flex items-center gap-4 p-4 ${borderClass} transition-all border-b border-slate-100 dark:border-slate-800/50 last:border-0">
            <div class="w-10 flex justify-center">${rankDisplay}</div>
            <div class="h-12 w-12 rounded-full overflow-hidden border-2 border-slate-200 dark:border-slate-700 bg-white shadow-sm">
                <img src="${escapeHtml(avatarUrl)}" alt="avatar" class="w-full h-full object-cover">
            </div>
            <div class="flex-1">
                <p class="font-bold text-slate-800 dark:text-slate-200 ${entry.is_me ? "text-blue-500" : ""}">
                    ${escapeHtml(entry.username)}
                    ${entry.is_me ? '<span class="ml-2 text-[10px] bg-blue-500 text-white px-2 py-0.5 rounded shadow-sm">YOU</span>' : ""}
                </p>
                <p class="text-[10px] font-bold text-slate-400 uppercase tracking-widest">${escapeHtml(league)} League</p>
            </div>
            <div class="flex items-center gap-6">
                <div class="flex items-center gap-1 text-orange-500 font-bold">
                    <span class="text-sm">🔥</span> ${Number(entry.streak) || 0}
                </div>
                <div class="text-right">
                    <span class="block font-black text-lg text-slate-700 dark:text-white leading-none">${Number(entry.xp) || 0}</span>
                    <span class="text-[9px] font-black text-slate-400 uppercase tracking-tighter">Weekly XP</span>
                </div>
            </div>
        </div>
      `;
}

async function renderLeaderboard() {
  const listContainer = document.getElementById("leaderboard-list");
  if (!listContainer) return;

  try {
    const board = await api("/users/leaderboard/data");

    setText("current-league-display", `${board.league} League`);
    setText("league-emoji", LEAGUE_EMOJIS[board.league] || "🛡️");
    if (board.next_league && board.promote_count > 0) {
      setText(
        "league-banner",
        `Top ${board.promote_count} earn a promotion to ${board.next_league} League next week! 🚀`,
      );
    } else if (!board.next_league) {
      setText("league-banner", "You're in the top league. Defend your spot! 👑");
    }

    let html = "";
    let lastZone = null;
    board.entries.forEach((entry) => {
      if (entry.zone !== lastZone) {
        html += ZONE_HEADERS[entry.zone](board);
        lastZone = entry.zone;
      }
      html += leaderboardRow(entry, board.league);
    });

    // You're ranked below the visible list
    if (board.me && !board.entries.some((e) => e.is_me)) {
      html += `<div class="p-2 text-center text-slate-400 font-black">⋯</div>`;
      html += leaderboardRow(board.me, board.league);
    }

    listContainer.innerHTML =
      html ||
      `<p class="p-10 text-center text-slate-400 font-bold">No competitors yet.</p>`;
  } catch (error) {
    console.error("Leaderboard Error:", error);
    listContainer.innerHTML = `<p class="p-10 text-center text-red-500 font-bold">Failed to load rankings.</p>`;
  }
}

// ==========================================
// 🎒 PROFILE PAGE
// ==========================================
async function renderProfile() {
  if (!document.getElementById("profile-page-mount")) return;

  try {
    const me = await getMe();
    setText("profile-username", me.username);
    setText("profile-email", me.email || "Google Authenticated");
    setText("profile-xp", me.xp);
    setText("profile-streak", me.streak);
    setText("profile-quests-done", me.quests_completed);
    setText("profile-league", me.league);

    const avatarImg = document.getElementById("profile-avatar");
    if (avatarImg)
      avatarImg.src = `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(me.username)}&backgroundColor=c0aede,d1d4f9,b6e3f4`;
  } catch (err) {
    console.error(err);
  }
}
