// ==========================================
// 🔊 AUDIO MANAGER
// ==========================================
const sfx = {
  // We are using temporary prototype URLs. Replace these with your local '/static/audio/filename.mp3' later!
  pop: new Audio(
    "https://assets.mixkit.co/active_storage/sfx/2013/2013-preview.mp3",
  ),
  success: new Audio(
    "https://assets.mixkit.co/active_storage/sfx/1435/1435-preview.mp3",
  ),
  whoosh: new Audio(
    "https://assets.mixkit.co/active_storage/sfx/2997/2997-preview.mp3",
  ),
  // ✨ THESE ARE THE TWO NEW SOUNDS FOR THE QUIZ ✨
  correct: new Audio(
    "https://assets.mixkit.co/active_storage/sfx/1435/1435-preview.mp3", // Happy ding (same as success)
  ),
  wrong: new Audio(
    "https://assets.mixkit.co/active_storage/sfx/3112/3112-preview.mp3", // Soft error tone
  ),
};

// Lower the volume a bit so it isn't deafening
Object.values(sfx).forEach((audio) => (audio.volume = 0.5));

function playSound(type) {
  if (sfx[type]) {
    // Reset to 0 so you can rapidly click and hear it every time
    sfx[type].currentTime = 0;

    // Browsers block audio unless the user interacts first, so we catch errors
    sfx[type]
      .play()
      .catch((err) =>
        console.log("Sound skipped (user hasn't interacted yet)"),
      );
  }
}
// --- 1. GLOBAL STATE & INIT ---
let currentQuestions = [];
let currentQuestionIndex = 0;
let isLoginMode = true;
let score = 0;
let timerInterval;
let timeLeft = 600; // 10 minutes

document.addEventListener("DOMContentLoaded", () => {
  // 1. Theme Setup
  const savedTheme =
    localStorage.getItem("theme") ||
    (window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light");
  applyTheme(savedTheme);
  updateUI();
  if (typeof renderLeaderboard === "function") {
    renderLeaderboard();
  }
  renderProfile();
  // 2. Global Data Fetching
  fetchUserStats();
  updateQuestTimers();
  setInterval(updateQuestTimers, 60000);

  // 3. Route-Specific Logic
  const path = window.location.pathname;

  // Home / Dashboard
  if (path === "/" || path === "/dashboard") {
    fetchLessons();
  }

  // Streaks Page
  if (path === "/streaks") {
    renderStreakCalendar(); // ✅ Now it runs on the correct page!
  }

  // Leaderboard Page
  if (path === "/leaderboard") {
    renderLeaderboard();
  }

  // Quiz Page logic
  if (path.startsWith("/quiz/")) {
    // ✨ SAFER URL PARSING: Handles /quiz/1 and /quiz/1/
    const pathParts = path.split("/").filter((part) => part !== "");
    const lessonId = pathParts[pathParts.length - 1];

    if (lessonId) {
      startQuiz(lessonId);
    }

    // Handle the Bottom Feedback Bar button
    const nextBtn = document.getElementById("next-question-btn");
    if (nextBtn) {
      nextBtn.onclick = function () {
        document
          .getElementById("quiz-feedback-bar")
          .classList.add("translate-y-full");
        nextQuestion();
      };
    }
  }

  // 4. Protection Logic
  const protectedRoutes = [
    "/",
    "/dashboard",
    "/leaderboard",
    "/streaks",
    "/quests",
  ];
  const isQuizRoute = path.startsWith("/quiz/");

  if (protectedRoutes.includes(path) || isQuizRoute) {
    if (!localStorage.getItem("promitheus_token")) {
      window.location.href = "/login";
    }
  }
});

// --- 2. THEME ENGINE ---
function applyTheme(theme) {
  const html = document.documentElement;
  const themeBtn = document.getElementById("theme-toggle");
  if (theme === "dark") {
    html.classList.add("dark");
    if (themeBtn) themeBtn.innerHTML = "☀️";
  } else {
    html.classList.remove("dark");
    if (themeBtn) themeBtn.innerHTML = "🌙";
  }
  localStorage.setItem("theme", theme);
}

function toggleTheme() {
  const newTheme = document.documentElement.classList.contains("dark")
    ? "light"
    : "dark";
  applyTheme(newTheme);
}

// --- 3. AUTH & UI ---
function updateUI() {
  const token = localStorage.getItem("promitheus_token");
  const username = localStorage.getItem("username");
  const path = window.location.pathname;

  // 1. Handle Auth State (Username and Login/Logout buttons)
  const sidebarUsername = document.getElementById("sidebar-username");
  const logoutBtn = document.getElementById("logout-btn");
  const loginBtn = document.getElementById("login-btn");

  if (token && username) {
    // User is logged in
    if (sidebarUsername) sidebarUsername.textContent = username;
    if (logoutBtn) logoutBtn.classList.remove("hidden");
    if (loginBtn) loginBtn.classList.add("hidden");
  } else {
    // User is a guest
    if (sidebarUsername) sidebarUsername.textContent = "Guest";
    if (logoutBtn) logoutBtn.classList.add("hidden");
    if (loginBtn) loginBtn.classList.remove("hidden");
  }

  // 2. ✨ Handle Sidebar Highlighting (The Active State)
  // First: Clear 'active' from all navigation items
  document.querySelectorAll(".nav-item").forEach((link) => {
    link.classList.remove("active");
  });

  // Second: Apply the 'active' class based on the URL path
  // Using .includes ensures it works with the new /users/ prefix
  if (path.includes("leaderboard")) {
    const nav = document.getElementById("nav-leaderboard");
    if (nav) nav.classList.add("active");
  } else if (path.includes("quests")) {
    const nav = document.getElementById("nav-quests");
    if (nav) nav.classList.add("active");
  } else if (path.includes("profile")) {
    const nav = document.getElementById("nav-profile");
    if (nav) nav.classList.add("active");
  } else if (path === "/" || path.includes("dashboard")) {
    const nav = document.getElementById("nav-learn");
    if (nav) nav.classList.add("active");
  }
}

async function handleAuth() {
  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;
  const email = document.getElementById("email")
    ? document.getElementById("email").value
    : "";

  const endpoint = isLoginMode ? "/auth/login" : "/auth/register";
  const payload = isLoginMode
    ? { username, password }
    : { username, email, password };

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await response.json();

    if (response.ok) {
      if (isLoginMode) {
        // ✨ TWEAK 1: Use the username from the backend response
        localStorage.setItem("promitheus_token", data.access_token);
        localStorage.setItem("username", data.username);

        // ✨ TWEAK 2: Match the Google redirect path
        window.location.href = "/dashboard";
      } else {
        showNotification("Account created! Login now 🔥", "success");
        toggleAuthMode();
      }
    } else {
      showNotification(data.detail || "Auth failed", "error");
    }
  } catch (error) {
    showNotification("Connection failed!", "error");
  }
}

function logout() {
  localStorage.removeItem("promitheus_token");
  localStorage.removeItem("username");
  window.location.href = "/login";
}

function toggleAuthMode() {
  isLoginMode = !isLoginMode;
  document.getElementById("auth-title").textContent = isLoginMode
    ? "Welcome Back"
    : "Create Account";
  document.getElementById("email").classList.toggle("hidden", isLoginMode);
  document.getElementById("auth-btn").textContent = isLoginMode
    ? "Login"
    : "Sign Up";
  document.getElementById("toggle-text").textContent = isLoginMode
    ? "Don't have an account?"
    : "Already have an account?";
}

function toggleMoreMenu(event) {
  if (event) event.stopPropagation();
  const menu = document.getElementById("more-menu");
  if (menu) menu.classList.toggle("hidden");
}

document.addEventListener("click", (event) => {
  const menu = document.getElementById("more-menu");
  if (!menu) return;
  const moreBtn = menu.nextElementSibling;
  if (!menu.contains(event.target) && !moreBtn.contains(event.target)) {
    menu.classList.add("hidden");
  }
});

// ✨ 1. FETCH XP & UPDATE ALL QUEST WIDGETS ✨
async function fetchUserStats() {
  const token = localStorage.getItem("promitheus_token");
  if (!token) return;

  try {
    const response = await fetch("/users/me", {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (response.ok) {
      const userData = await response.json();

      // Top Nav Stats
      const xpDisplay = document.getElementById("xp-display");
      const streakDisplay = document.getElementById("streak-display");
      const xpHoverText = document.getElementById("xp-hover-text");
      const streakHoverText = document.getElementById("streak-hover-text");
      const streakPageCount = document.getElementById("streak-page-count");
      const userDisplayName = document.getElementById("user-display-name");
      // Inside fetchUserStats() after you get userData
      const dailyXP = userData.daily_xp || 0;
      const dailyLessons = userData.daily_lessons || 0;
      animateDailyQuests(dailyXP, dailyLessons);
      if (xpDisplay) xpDisplay.textContent = userData.xp + " XP";
      if (streakDisplay) streakDisplay.textContent = userData.streak;
      if (xpHoverText) xpHoverText.textContent = userData.xp;
      if (streakHoverText) streakHoverText.textContent = userData.streak;
      if (streakPageCount) streakPageCount.textContent = userData.streak;
      if (userDisplayName) {
        userDisplayName.textContent = userData.username;
      }

      // Extract the REAL Daily Stats from the database!
      let questXP = userData.daily_xp || 0;
      if (questXP > 50) questXP = 50;

      let questLessons = userData.daily_lessons || 0;
      if (questLessons > 1) questLessons = 1;

      // 👉 UPDATE DASHBOARD WIDGETS
      const q1Bar = document.getElementById("quest-1-bar");
      const q1Text = document.getElementById("quest-1-text");
      const q1Chest = document.getElementById("quest-1-chest");
      if (q1Bar) {
        setTimeout(() => {
          q1Bar.style.width = `${(questXP / 50) * 100}%`;
          q1Text.textContent = `${questXP}/50`;
          if (questXP >= 50) {
            q1Chest.classList.remove("grayscale", "opacity-40");
            q1Chest.classList.add("drop-shadow-lg", "scale-110");
          }
        }, 300);
      }

      const q2Bar = document.getElementById("quest-2-bar");
      const q2Text = document.getElementById("quest-2-text");
      const q2Chest = document.getElementById("quest-2-chest");
      if (q2Bar) {
        setTimeout(() => {
          q2Bar.style.width = `${(questLessons / 1) * 100}%`;
          q2Text.textContent = `${questLessons}/1`;
          if (questLessons >= 1) {
            q2Chest.classList.remove("grayscale", "opacity-40");
            q2Chest.classList.add("drop-shadow-lg", "scale-110");
          }
        }, 500);
      }

      // 👉 UPDATE DEDICATED QUESTS PAGE
      if (window.location.pathname === "/quests") {
        const qPageXpBar = document.getElementById("qpage-xp-bar");
        const qPageXpText = document.getElementById("qpage-xp-text");
        const qPageXpChest = document.getElementById("qpage-xp-chest");
        if (qPageXpBar) {
          setTimeout(() => {
            qPageXpBar.style.width = `${(questXP / 50) * 100}%`;
            qPageXpText.textContent = `${questXP}/50`;
            if (questXP >= 50) {
              qPageXpChest.classList.remove("grayscale", "opacity-40");
              qPageXpChest.classList.add("drop-shadow-lg", "scale-110");
            }
          }, 300);
        }

        const qPageLessonBar = document.getElementById("qpage-lesson-bar");
        const qPageLessonText = document.getElementById("qpage-lesson-text");
        const qPageLessonChest = document.getElementById("qpage-lesson-chest");
        if (qPageLessonBar) {
          setTimeout(() => {
            qPageLessonBar.style.width = `${(questLessons / 1) * 100}%`;
            qPageLessonText.textContent = `${questLessons}/1`;
            if (questLessons >= 1) {
              qPageLessonChest.classList.remove("grayscale", "opacity-40");
              qPageLessonChest.classList.add("drop-shadow-lg", "scale-110");
            }
          }, 500);
        }

        // ✨ THE FIX: Upgraded Monthly Badge Logic
        // Count exactly how many daily quests you finished today
        let dailyQuestsCompletedToday = 0;
        if (questXP >= 50) dailyQuestsCompletedToday++;
        if (questLessons >= 1) dailyQuestsCompletedToday++;

        // Combine today's completed quests with your past streak history
        const pastProgress = (userData.streak || 0) * 2;
        const monthlyProgress = Math.min(
          pastProgress + dailyQuestsCompletedToday,
          20,
        );

        const monthlyBar = document.getElementById("monthly-bar");
        const monthlyText = document.getElementById("monthly-text");

        if (monthlyBar) {
          setTimeout(() => {
            monthlyBar.style.width = `${(monthlyProgress / 20) * 100}%`;
            monthlyText.textContent = `${Math.floor(monthlyProgress)} / 20`;
          }, 700);
        }
      }
    }
  } catch (error) {
    console.error("Failed to fetch stats", error);
  }
}

// ✨ 2. FETCH LESSONS (Cleaned up: Only handles the Snake Path now!) ✨
async function fetchLessons() {
  const pathContainer = document.getElementById("study-path");
  if (!pathContainer) return;
  const token = localStorage.getItem("promitheus_token");

  try {
    const response = await fetch("/lessons/", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error("Failed to fetch");
    const lessons = await response.json();

    if (lessons.length === 0) {
      pathContainer.innerHTML = `<div class="p-6 text-center text-slate-400 font-bold mt-10">Upload a lecture to begin.</div>`;
      return;
    }

    const units = {};
    lessons.forEach((l) => {
      if (!units[l.unit_number]) units[l.unit_number] = [];
      units[l.unit_number].push(l);
    });

    pathContainer.innerHTML = "";
    let isPreviousUnitComplete = true;

    const unitColors = [
      { bg: "bg-[#58cc02]", border: "border-[#46a302]" },
      { bg: "bg-[#ce82ff]", border: "border-[#a568cc]" },
      { bg: "bg-[#1cb0f6]", border: "border-[#1899d6]" },
      { bg: "bg-[#ff9600]", border: "border-[#cc7800]" },
    ];

    Object.keys(units).forEach((uNum, unitIndex) => {
      const unitLessons = units[uNum];
      const isUnitLocked = !isPreviousUnitComplete;
      const isUnitComplete = unitLessons.every((l) => l.is_completed);

      const rawTitle = unitLessons[0].unit_title || "New Unit";
      const cleanTitle = rawTitle.replace(".pdf", "").replace(".txt", "");
      const color = unitColors[unitIndex % unitColors.length];

      const headerBox = document.createElement("div");
      headerBox.className = `w-full ${color.bg} text-white p-6 rounded-3xl shadow-md mb-8 relative overflow-hidden border-b-4 ${color.border}`;
      headerBox.innerHTML = `
          <div class="relative z-10">
              <p class="uppercase font-black text-sm opacity-90 tracking-wider mb-1">UNIT ${unitIndex + 1}</p>
              <h2 class="text-2xl font-black">${cleanTitle}</h2>
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

        let tooltipHtml = `<div class="path-tooltip">${lesson.title}</div>`;
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
  uploadBtn.innerHTML = "Generating... 🧠";
  uploadBtn.disabled = true;
  const token = localStorage.getItem("promitheus_token");

  try {
    const response = await fetch("/upload/lecture", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });

    if (response.ok) {
      showNotification("Lesson ready!", "success");
      fileInput.value = "";
      fetchLessons();
    } else {
      const data = await response.json();
      showNotification(data.detail || "Upload failed", "error");
    }
  } catch (error) {
    showNotification("Server error", "error");
  } finally {
    uploadBtn.innerHTML = "Generate with AI ✨";
    uploadBtn.disabled = false;
  }
}

// --- 5. QUIZ LOGIC & TIMER ---
function startTimer() {
  clearInterval(timerInterval);
  timeLeft = 600; // 10 minutes

  let timerDisplay = document.getElementById("quiz-timer");
  if (!timerDisplay) {
    // ✨ FIX: Target the new header ID instead of the deleted question-text ID
    const targetElement = document.getElementById("question-header");

    if (targetElement) {
      timerDisplay = document.createElement("div");
      timerDisplay.id = "quiz-timer";
      timerDisplay.className =
        "text-2xl font-black text-[#E2E8F0] text-center mb-6 font-mono bg-[#4f46e5] py-2 rounded-xl border-2 border-[#E2E8F0] w-fit px-6";
      targetElement.parentNode.insertBefore(timerDisplay, targetElement);
    }
  }

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

// 1. Global State - CRITICAL: These must be outside the functions

async function startQuiz(lessonId) {
  try {
    const token = localStorage.getItem("promitheus_token");
    const response = await fetch(`/lessons/${lessonId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!response.ok) throw new Error("Lesson data not found");

    const data = await response.json();
    currentQuestions = data.questions || [];

    if (currentQuestions.length > 0) {
      currentQuestionIndex = 0;
      score = 0;
      // Safety Check: Only call startTimer if you have defined it elsewhere
      if (typeof startTimer === "function") startTimer();
      showQuestion();
    } else {
      const container = document.getElementById("sentence-container");
      if (container) container.textContent = "No questions found.";
    }
  } catch (err) {
    console.error("Quiz Initialization Error:", err);
    showNotification("Failed to load questions.", "error");
  }
}

function showQuestion() {
  const q = currentQuestions[currentQuestionIndex];
  if (!q) return;

  const sentenceContainer = document.getElementById("sentence-container");
  const optionsContainer = document.getElementById("options-container");
  const header = document.getElementById("question-header");
  const progressBar = document.getElementById("progress-bar");

  // Clear previous UI
  optionsContainer.innerHTML = "";
  sentenceContainer.innerHTML = "";

  // Update Progress Bar
  if (progressBar) {
    const progress = (currentQuestionIndex / currentQuestions.length) * 100;
    progressBar.style.width = `${progress}%`;
  }

  // ✨ FIX 1: Dynamic Header Text
  if (q.type === "fill_blank") {
    header.textContent = "Fill in the blank";
  } else if (q.type === "explain" || q.type === "open_ended") {
    header.textContent = "Explain your answer";
  } else if (q.type === "rearrange") {
    header.textContent = "Form the correct sentence";
  } else {
    header.textContent = "Select the correct option";
  }

  // Render Question Text
  const promptText =
    q.data.prompt || q.data.sentence || "Question text missing";
  if (q.type === "fill_blank") {
    sentenceContainer.innerHTML = promptText.replace(
      "____",
      '<span class="quiz-blank"></span>',
    );
  } else {
    sentenceContainer.textContent = promptText;
  }

  // Render Options (Multiple Choice / True False)
  if (q.type === "multiple_choice" || q.type === "true_false") {
    const options = q.data.options || [];
    options.forEach((opt) => {
      const btn = document.createElement("button");
      btn.className = "option-btn";
      btn.textContent = opt;
      btn.onclick = () => checkAnswer(btn, opt, q.data.answer);
      optionsContainer.appendChild(btn);
    });
  }
  // Render Fill Blank / Short Answer
  else if (q.type === "fill_blank" || q.type === "short_answer") {
    const input = document.createElement("input");
    input.className =
      "w-full p-4 border-2 rounded-2xl bg-white dark:bg-slate-800 text-slate-800 dark:text-white outline-none mb-4";
    input.placeholder = "Type your exact answer here...";

    const btn = document.createElement("button");
    btn.textContent = "Check";
    btn.className =
      "w-full bg-[#58cc02] text-white py-4 rounded-xl font-bold shadow-[0_4px_0_#46a302] active:translate-y-1 active:shadow-none transition-all uppercase tracking-widest";
    btn.onclick = () => checkAnswer(input, input.value.trim(), q.data.answer);

    optionsContainer.appendChild(input);
    optionsContainer.appendChild(btn);
  }
  // Render Rearrange
  else if (q.type === "rearrange") {
    let selectedOrder = [];
    const dropZone = document.createElement("div");
    dropZone.className =
      "w-full min-h-[80px] p-4 border-4 border-dashed border-slate-200 dark:border-slate-800 rounded-2xl mb-4 flex flex-wrap gap-2 items-center bg-slate-50 dark:bg-slate-900/50";

    const wordBank = document.createElement("div");
    wordBank.className = "flex flex-wrap gap-2";

    const renderChunks = () => {
      dropZone.innerHTML =
        selectedOrder.length === 0
          ? '<span class="text-slate-400 font-bold mx-auto">Click words to build the sentence</span>'
          : "";
      wordBank.innerHTML = "";

      selectedOrder.forEach((word, idx) => {
        const btn = document.createElement("button");
        btn.className =
          "px-4 py-2 bg-indigo-500 text-white font-bold rounded-lg shadow-sm";
        btn.textContent = word;
        btn.onclick = () => {
          selectedOrder.splice(idx, 1);
          renderChunks();
        };
        dropZone.appendChild(btn);
      });

      q.data.chunks.forEach((word) => {
        if (!selectedOrder.includes(word)) {
          const btn = document.createElement("button");
          btn.className =
            "px-4 py-2 bg-white dark:bg-slate-800 border-2 border-slate-200 dark:border-slate-700 font-bold rounded-lg hover:border-indigo-500 transition-colors";
          btn.textContent = word;
          btn.onclick = () => {
            selectedOrder.push(word);
            renderChunks();
          };
          wordBank.appendChild(btn);
        }
      });
    };

    const checkBtn = document.createElement("button");
    checkBtn.textContent = "Check Order";
    checkBtn.className =
      "w-full mt-6 bg-[#58cc02] text-white py-4 rounded-xl font-bold shadow-[0_4px_0_#46a302] uppercase tracking-widest active:translate-y-1 active:shadow-none transition-all";
    checkBtn.onclick = () => {
      const isMatch =
        JSON.stringify(selectedOrder) === JSON.stringify(q.data.answer);
      checkAnswer(dropZone, isMatch ? "match" : "fail", "match");
    };

    optionsContainer.appendChild(dropZone);
    optionsContainer.appendChild(wordBank);
    optionsContainer.appendChild(checkBtn);
    renderChunks();
  }
  // ✨ FIX 2: Render Open-Ended / Explain Questions
  else if (q.type === "explain" || q.type === "open_ended") {
    const textarea = document.createElement("textarea");
    textarea.id = "explain-input";
    textarea.className =
      "w-full p-4 border-2 border-slate-200 dark:border-slate-700 rounded-2xl bg-white dark:bg-slate-800 text-slate-800 dark:text-white outline-none mb-4 min-h-[150px] resize-y focus:border-[#1cb0f6] transition-colors";
    textarea.placeholder = "Type your explanation here...";

    const btn = document.createElement("button");
    btn.textContent = "Submit for AI Review ✨";
    btn.className =
      "w-full bg-[#1cb0f6] text-white py-4 rounded-xl font-bold shadow-[0_4px_0_#1899d6] active:translate-y-1 active:shadow-none transition-all uppercase tracking-widest";

    btn.onclick = () =>
      gradeWithAI(q.data.prompt, textarea.value, q.data.answer, btn);

    optionsContainer.appendChild(textarea);
    optionsContainer.appendChild(btn);
  }
}

function checkAnswer(element, selected, correct) {
  const isCorrect = selected.toLowerCase() === correct.toLowerCase();
  const feedbackBar = document.getElementById("quiz-feedback-bar");
  const iconCircle = document.getElementById("feedback-icon-circle");
  const icon = document.getElementById("feedback-icon");
  const title = document.getElementById("feedback-title");
  const solutionText = document.getElementById("feedback-solution");
  const continueBtn = document.getElementById("next-question-btn");

  // Disable all options
  document.querySelectorAll(".option-btn").forEach((b) => (b.disabled = true));

  // Reset feedback bar animations/styles
  feedbackBar.classList.remove(
    "translate-y-full",
    "bg-[#d7ffb8]",
    "bg-[#ffdfe0]",
    "border-[#b8f28b]",
    "border-[#f4c2c2]",
  );
  title.classList.remove("text-[#58a700]", "text-[#ea2b2b]");

  if (isCorrect) {
    // 🔊 TRIGGER CORRECT SOUND
    playSound("correct");

    score++;
    element.classList.add("is-correct-selection");
    feedbackBar.classList.add("bg-[#d7ffb8]", "border-[#b8f28b]");
    iconCircle.className =
      "w-20 h-20 rounded-full flex items-center justify-center text-4xl bg-white text-[#58cc02]";
    icon.textContent = "✔";
    title.textContent = "You are correct!";
    title.classList.add("text-[#58a700]");
    solutionText.textContent = "";
    continueBtn.className =
      "px-12 py-4 rounded-2xl font-black text-xl bg-[#58cc02] text-white uppercase tracking-widest shadow-[0_4px_0_#46a302]";
  } else {
    // 🔊 TRIGGER WRONG SOUND
    playSound("wrong");

    element.classList.add("is-wrong-selection", "animate-shake");
    feedbackBar.classList.add("bg-[#ffdfe0]", "border-[#f4c2c2]");
    iconCircle.className =
      "w-20 h-20 rounded-full flex items-center justify-center text-4xl bg-white text-[#ea2b2b]";
    icon.textContent = "✖";
    title.textContent = "Correct solution:";
    title.classList.add("text-[#ea2b2b]");
    solutionText.textContent = correct;
    solutionText.classList.add("text-[#ea2b2b]");
    continueBtn.className =
      "px-12 py-4 rounded-2xl font-black text-xl bg-[#ff4b4b] text-white uppercase tracking-widest shadow-[0_4px_0_#af2323]";
  }

  // Show the feedback bar
  feedbackBar.classList.remove("translate-y-full");
}

// --- ✨ THE FINAL & ONLY NEXTQUESTION FUNCTION ✨ ---
async function nextQuestion() {
  // 1. Check if we have more questions
  currentQuestionIndex++;

  if (currentQuestionIndex < currentQuestions.length) {
    // Just show the next question
    showQuestion();
  } else {
    // 🏆 QUIZ COMPLETE LOGIC
    console.log("Quiz Finished! Calculating rewards...");

    // Stop any active timers
    if (typeof timerInterval !== "undefined") clearInterval(timerInterval);

    const earnedXP = score * 10;
    const token = localStorage.getItem("promitheus_token");

    // Get Lesson ID safely
    const pathParts = window.location.pathname
      .split("/")
      .filter((p) => p !== "");
    const lessonId = pathParts[pathParts.length - 1];

    showNotification(`Lesson Complete! +${earnedXP} XP 🌟`, "success");

    if (token && lessonId) {
      try {
        // Update User XP
        await fetch("/users/update_xp", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ xp: earnedXP }),
        });

        // Trigger Streak & Lesson Completion
        await fetch(`/lessons/${lessonId}/complete`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });

        console.log("Progress saved successfully.");
      } catch (err) {
        console.error("Failed to save progress:", err);
      }
    }

    // Redirect back to dashboard after a short delay
    setTimeout(() => {
      window.location.href = "/dashboard";
    }, 2000);
  }
}

// --- 6. UTILS ---
function showNotification(message, type = "success") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `${type === "success" ? "bg-[#58cc02]" : "bg-[#ff4b4b]"} text-white px-6 py-4 rounded-2xl shadow-xl font-bold mb-2 transition-all duration-300 toast-pop`;
  toast.innerHTML = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// --- 7. TIMERS & COUNTDOWNS ---
function updateQuestTimers() {
  // Only run this if we are actually on the Quests page!
  if (window.location.pathname !== "/quests") return;

  const now = new Date();

  // 1. DYNAMIC MONTH NAME
  const monthNames = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
  ];
  const currentMonthName = monthNames[now.getMonth()];

  const monthBadge = document.getElementById("dynamic-month-badge");
  const monthTitle = document.getElementById("dynamic-month-title");

  if (monthBadge) monthBadge.textContent = currentMonthName;
  if (monthTitle) monthTitle.textContent = `${currentMonthName} Quest`;

  // 2. MONTHLY TIMER (Days until end of month)
  const lastDayOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  const daysLeft = lastDayOfMonth.getDate() - now.getDate();

  const monthlyTimerDisplay = document.getElementById("monthly-timer");
  if (monthlyTimerDisplay) {
    monthlyTimerDisplay.textContent = `⏱️ ${daysLeft} DAYS`;
  }

  // 3. DAILY TIMER (Hours and minutes until midnight)
  const midnight = new Date(now);
  midnight.setHours(24, 0, 0, 0); // Set clock to exactly 12:00 AM tonight

  const diffMs = midnight - now;
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffMins = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));

  const dailyTimerDisplay = document.getElementById("daily-timer");
  if (dailyTimerDisplay) {
    // If less than an hour, show minutes. Otherwise, show hours.
    if (diffHours === 0) {
      dailyTimerDisplay.textContent = `⏱️ ${diffMins} MINS`;
    } else {
      dailyTimerDisplay.textContent = `⏱️ ${diffHours} HOURS`;
    }
  }
}

// Global variable to keep track of which month the user is viewing
let currentViewDate = new Date();

async function renderStreakCalendar(targetDate = new Date()) {
  const mount = document.getElementById("streak-calendar-mount");
  if (!mount || window.location.pathname !== "/streaks") return;

  const token = localStorage.getItem("promitheus_token");

  try {
    // ✨ FIX 1: Fetch User Data instead of Lesson Data
    const response = await fetch("/users/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    const userData = await response.json();

    // ✨ FIX 2: Mathematical Backfill Logic
    const completedDates = new Set();
    const streakCount = userData.streak || 0;

    // Anchor the streak. If they haven't played today, start counting backward from yesterday.
    let anchorDate = new Date();
    if (userData.daily_lessons === 0 && streakCount > 0) {
      anchorDate.setDate(anchorDate.getDate() - 1);
    }

    // Mathematically calculate the exact past dates for the fire icons
    for (let i = 0; i < streakCount; i++) {
      const d = new Date(anchorDate);
      d.setDate(d.getDate() - i); // Go back 'i' days

      const year = d.getFullYear();
      const month = String(d.getMonth() + 1).padStart(2, "0");
      const day = String(d.getDate()).padStart(2, "0");

      completedDates.add(`${year}-${month}-${day}`);
    }

    const year = targetDate.getFullYear();
    const month = targetDate.getMonth();
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const monthName = targetDate.toLocaleString("default", { month: "long" });

    // Build the HTML with Navigation Buttons
    let html = `
            <div class="calendar-container w-full max-w-md mx-auto">
                <div class="flex justify-between items-center mb-8">
                    <button onclick="changeMonth(-1)" class="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition-colors text-slate-500">◀</button>
                    <h4 class="text-xl font-black text-slate-800 dark:text-slate-200">${monthName} ${year}</h4>
                    <button onclick="changeMonth(1)" class="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition-colors text-slate-500">▶</button>
                </div>
                
                <div class="grid grid-cols-7 gap-2 text-center text-xs font-bold text-slate-400 mb-4">
                    <div>SUN</div><div>MON</div><div>TUE</div><div>WED</div><div>THU</div><div>FRI</div><div>SAT</div>
                </div>
                
                <div class="grid grid-cols-7 gap-y-6 justify-items-center">
        `;

    // Empty slots for alignment
    for (let i = 0; i < firstDay; i++) html += `<div></div>`;

    // Days of the month
    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      const isCompleted = completedDates.has(dateStr);
      const isToday =
        day === new Date().getDate() &&
        month === new Date().getMonth() &&
        year === new Date().getFullYear();

      if (isCompleted) {
        // ✨ FIRE ICON STYLE (Duolingo Style)
        html += `
                    <div class="relative group cursor-pointer">
                        <span class="text-2xl absolute -top-5 left-1/2 -translate-x-1/2 animate-bounce drop-shadow-md">🔥</span>
                        <div class="h-10 w-10 rounded-full bg-orange-500 flex items-center justify-center font-black text-white shadow-[0_0_15px_rgba(249,115,22,0.4)] scale-110">
                            ${day}
                        </div>
                    </div>`;
      } else if (isToday) {
        // Today's ring
        html += `
                    <div class="h-10 w-10 rounded-full border-2 border-orange-500 flex items-center justify-center font-bold text-orange-500">
                        ${day}
                    </div>`;
      } else {
        // Empty day
        html += `
                    <div class="h-10 w-10 flex items-center justify-center font-bold text-slate-400 hover:text-slate-600 transition-colors">
                        ${day}
                    </div>`;
      }
    }

    html += `</div></div>`;
    mount.innerHTML = html;

    // ==========================================
    // 🔊 TRIGGER THE SOUND JUICE!
    // ==========================================
    // Play a fire whoosh sound if they have an active streak!
    if (streakCount > 0) {
      setTimeout(() => {
        playSound("whoosh");
      }, 300); // 300ms delay so it syncs perfectly with the visual load
    }
  } catch (error) {
    console.error("Calendar Error:", error);
    mount.innerHTML = `<p class="text-red-500 text-center font-bold">Unable to sync history.</p>`;
  }
}

// ✨ Helper function to handle month navigation
window.changeMonth = (offset) => {
  currentViewDate.setMonth(currentViewDate.getMonth() + offset);
  renderStreakCalendar(currentViewDate);
};

// --- 9. LEADERBOARD SYSTEM ---
async function renderLeaderboard() {
  const listContainer = document.getElementById("leaderboard-list");

  // 1. Safety Check
  if (!listContainer || !window.location.pathname.includes("/leaderboard"))
    return;

  try {
    // 2. ✨ STEP 1: Get YOUR current league info first
    const userResponse = await fetch("/users/me", {
      headers: {
        Authorization: `Bearer ${localStorage.getItem("promitheus_token")}`,
      },
    });
    const userData = await userResponse.json();
    const myLeague = userData.league || "Paper";

    // 3. ✨ STEP 2: Fetch only competitors in your league
    const response = await fetch(`/users/leaderboard/data?league=${myLeague}`);
    const topUsers = await response.json();

    // 4. ✨ UPDATE TOP LEAGUE HEADER ✨
    if (topUsers.length > 0) {
      // Use myLeague instead of the first user's league for the header consistency
      const leagueEmojiEl = document.getElementById("league-emoji");
      const leagueTextEl = document.getElementById("current-league-display");

      if (leagueTextEl) leagueTextEl.textContent = `${myLeague} League`;

      if (leagueEmojiEl) {
        const leagueEmojis = {
          Paper: "📄",
          Iron: "⛓️",
          Bronze: "🥉",
          Silver: "🥈",
          Gold: "🥇",
          Platinum: "💎",
          Diamond: "👑",
        };
        leagueEmojiEl.textContent = leagueEmojis[myLeague] || "🛡️";
      }
    }

    let html = "";
    const currentUsername = document
      .getElementById("sidebar-username")
      ?.textContent.trim();

    topUsers.forEach((user, index) => {
      const isMe = user.username === currentUsername;
      const rank = user.rank;
      const displayLeague = user.current_league || "Paper";

      // ==========================================
      // 🛑 ZONE DIVIDERS (Promote, Safe, Demote)
      // ==========================================
      if (rank === 1) {
        html += `<div class="bg-emerald-500/10 text-emerald-500 font-bold text-[10px] uppercase tracking-[0.2em] p-3 text-center border-y border-emerald-500/10">🚀 Promotion Zone — Top 10 promoting to ${user.next_tier}</div>`;
      } else if (rank === 11) {
        html += `<div class="bg-slate-500/10 text-slate-400 font-bold text-[10px] uppercase tracking-[0.2em] p-3 text-center border-y border-slate-500/10">🛡️ Safe Zone</div>`;
      } else if (rank === 21) {
        html += `<div class="bg-red-500/10 text-red-500 font-bold text-[10px] uppercase tracking-[0.2em] p-3 text-center border-y border-red-500/10">⚠️ Demotion Zone</div>`;
      }

      // Special styling for top 3 Medals
      let rankDisplay = `<span class="font-black text-slate-500 w-8 text-center text-lg">${rank}</span>`;
      if (rank === 1)
        rankDisplay = `<span class="text-3xl w-8 text-center drop-shadow-sm">🥇</span>`;
      if (rank === 2)
        rankDisplay = `<span class="text-3xl w-8 text-center drop-shadow-sm">🥈</span>`;
      if (rank === 3)
        rankDisplay = `<span class="text-3xl w-8 text-center drop-shadow-sm">🥉</span>`;

      // Assign colors based on the zone
      let borderClass = "border-l-4 border-transparent";
      if (user.zone === "promote")
        borderClass = "border-l-4 border-emerald-500 bg-emerald-500/[0.02]";
      if (user.zone === "demote")
        borderClass = "border-l-4 border-red-500 bg-red-500/[0.02]";
      if (isMe) borderClass = "border-l-4 border-blue-500 bg-blue-500/10";

      const avatarSeed = encodeURIComponent(user.username);
      const avatarUrl = `https://api.dicebear.com/7.x/bottts/svg?seed=${avatarSeed}&backgroundColor=c0aede,d1d4f9,b6e3f4`;

      html += `
        <div class="flex items-center gap-4 p-4 ${borderClass} transition-all border-b border-slate-100 dark:border-slate-800/50 last:border-0">
            <div class="w-10 flex justify-center">${rankDisplay}</div>
            <div class="h-12 w-12 rounded-full overflow-hidden border-2 border-slate-200 dark:border-slate-700 bg-white shadow-sm">
                <img src="${avatarUrl}" alt="avatar" class="w-full h-full object-cover">
            </div>
            <div class="flex-1">
                <p class="font-bold text-slate-800 dark:text-slate-200 ${isMe ? "text-blue-500" : ""}">
                    ${user.username}
                    ${isMe ? '<span class="ml-2 text-[10px] bg-blue-500 text-white px-2 py-0.5 rounded shadow-sm">YOU</span>' : ""}
                </p>
                <p class="text-[10px] font-bold text-slate-400 uppercase tracking-widest">${displayLeague} League</p>
            </div>
            <div class="flex items-center gap-6">
                <div class="flex items-center gap-1 text-orange-500 font-bold">
                    <span class="text-sm">🔥</span> ${user.streak || 0}
                </div>
                <div class="text-right">
                    <span class="block font-black text-lg text-slate-700 dark:text-white leading-none">${user.xp}</span>
                    <span class="text-[9px] font-black text-slate-400 uppercase tracking-tighter">Weekly XP</span>
                </div>
            </div>
        </div>
      `;
    });

    listContainer.innerHTML = html;
  } catch (error) {
    console.error("Leaderboard Error:", error);
    listContainer.innerHTML = `<p class="p-10 text-center text-red-500 font-bold">Failed to load rankings.</p>`;
  }
}

async function gradeWithAI(promptText, userAnswer, idealAnswer, btnElement) {
  if (!userAnswer.trim()) {
    showNotification("Please write an answer first!", "error");
    return;
  }

  // Set loading state
  btnElement.textContent = "AI is grading... 🧠";
  btnElement.disabled = true;
  btnElement.classList.add("opacity-75", "cursor-wait");

  try {
    const token = localStorage.getItem("promitheus_token");
    const response = await fetch("/api/grade-answer", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        question: promptText,
        student_answer: userAnswer,
        ideal_answer: idealAnswer || "",
      }),
    });

    if (!response.ok) throw new Error("Grading failed");

    const result = await response.json();

    // ✨ FIX: We are now passing 'idealAnswer' into the feedback function
    showAIFeedback(result.is_correct, result.feedback, idealAnswer);
  } catch (err) {
    console.error(err);
    showNotification("AI grading failed. Try again.", "error");
    btnElement.textContent = "Submit for AI Review ✨";
    btnElement.disabled = false;
    btnElement.classList.remove("opacity-75", "cursor-wait");
  }
}

function showAIFeedback(isCorrect, feedbackText, idealAnswer) {
  const feedbackBar = document.getElementById("quiz-feedback-bar");
  const iconCircle = document.getElementById("feedback-icon-circle");
  const icon = document.getElementById("feedback-icon");
  const title = document.getElementById("feedback-title");
  const solutionText = document.getElementById("feedback-solution");
  const continueBtn = document.getElementById("next-question-btn");
  const textarea = document.getElementById("explain-input");

  // Lock the input
  if (textarea) textarea.disabled = true;

  // Reset styles
  feedbackBar.classList.remove(
    "translate-y-full",
    "bg-[#d7ffb8]",
    "bg-[#ffdfe0]",
    "border-[#b8f28b]",
    "border-[#f4c2c2]",
  );
  title.classList.remove("text-[#58a700]", "text-[#ea2b2b]");

  if (isCorrect) {
    score++;
    feedbackBar.classList.add("bg-[#d7ffb8]", "border-[#b8f28b]");
    iconCircle.className =
      "w-20 h-20 rounded-full flex items-center justify-center text-4xl bg-white text-[#58cc02]";
    icon.textContent = "✔";
    title.textContent = "Great explanation!";
    title.classList.add("text-[#58a700]");

    // We keep the feedback here so the AI can praise what you did right!
    solutionText.textContent = feedbackText;
    solutionText.className = "font-bold text-lg text-[#58a700] mt-2";

    continueBtn.className =
      "px-12 py-4 rounded-2xl font-black text-xl bg-[#58cc02] text-white uppercase tracking-widest shadow-[0_4px_0_#46a302]";
  } else {
    if (textarea) textarea.classList.add("border-[#ea2b2b]", "animate-shake");
    feedbackBar.classList.add("bg-[#ffdfe0]", "border-[#f4c2c2]");
    iconCircle.className =
      "w-20 h-20 rounded-full flex items-center justify-center text-4xl bg-white text-[#ea2b2b]";
    icon.textContent = "✖";
    title.textContent = "Not quite right:";
    title.classList.add("text-[#ea2b2b]");

    // ✨ FIX: Removed the AI feedback completely. Now it ONLY shows the Ideal Answer.
    solutionText.className = "text-[#ea2b2b] mt-1";
    solutionText.innerHTML = `
            <div class="text-lg mt-1">
                <span class="font-black uppercase tracking-wider text-sm opacity-80 mr-2">Ideal Answer:</span> 
                <span class="font-bold">${idealAnswer}</span>
            </div>
        `;

    continueBtn.className =
      "px-12 py-4 rounded-2xl font-black text-xl bg-[#ff4b4b] text-white uppercase tracking-widest shadow-[0_4px_0_#af2323]";
  }

  feedbackBar.classList.remove("translate-y-full");
}

function animateDailyQuests(dailyXP, dailyLessons) {
  const maxXP = 50;
  const maxLessons = 1;

  // --- QUEST 1: XP ---
  const xpBar = document.getElementById("quest-1-bar");
  const xpText = document.getElementById("quest-1-text");
  const xpChest = document.getElementById("quest-1-chest");

  if (xpBar && xpText && xpChest) {
    let xpPercentage = (dailyXP / maxXP) * 100;
    if (xpPercentage >= 100) xpPercentage = 100;

    xpBar.style.width = `${xpPercentage}%`;
    xpText.textContent = `${Math.min(dailyXP, maxXP)}/${maxXP}`;

    // If the quest is complete...
    if (dailyXP >= maxXP) {
      xpBar.classList.replace("bg-[#ffc800]", "bg-[#58cc02]");

      // Check if it hasn't been clicked yet
      if (!xpChest.classList.contains("claimed")) {
        // Wake the chest up! Make it colorful and wiggle
        xpChest.classList.remove("grayscale", "opacity-40");
        xpChest.classList.add("ready-to-claim");

        // ✨ WAIT FOR THE CLICK ✨
        xpChest.onclick = function () {
          // Remove the wiggle, add the POP!
          xpChest.classList.remove("ready-to-claim");
          xpChest.classList.add("animate-chest-pop", "claimed");
          xpChest.textContent = "✅";

          // 🔊 TRIGGER THE SOUND JUICE!
          playSound("pop");
        };
      }
    }
  }

  // --- QUEST 2: LESSONS ---
  const lessonBar = document.getElementById("quest-2-bar");
  const lessonText = document.getElementById("quest-2-text");
  const lessonChest = document.getElementById("quest-2-chest");

  if (lessonBar && lessonText && lessonChest) {
    let lessonPercentage = (dailyLessons / maxLessons) * 100;
    if (lessonPercentage >= 100) lessonPercentage = 100;

    lessonBar.style.width = `${lessonPercentage}%`;
    lessonText.textContent = `${Math.min(dailyLessons, maxLessons)}/${maxLessons}`;

    // If the quest is complete...
    if (dailyLessons >= maxLessons) {
      lessonBar.classList.replace("bg-[#1cb0f6]", "bg-[#58cc02]");

      // Check if it hasn't been clicked yet
      if (!lessonChest.classList.contains("claimed")) {
        // Wake the chest up!
        lessonChest.classList.remove("grayscale", "opacity-40");
        lessonChest.classList.add("ready-to-claim");

        // ✨ WAIT FOR THE CLICK ✨
        lessonChest.onclick = function () {
          lessonChest.classList.remove("ready-to-claim");
          lessonChest.classList.add("animate-chest-pop", "claimed");
          lessonChest.textContent = "✅";

          // 🔊 TRIGGER THE SOUND JUICE!
          playSound("pop");
        };
      }
    }
  }
}

// Function triggered by Google Identity Services after a successful popup login
async function handleGoogleLogin(response) {
  const googleCredential = response.credential; // This is the JWT from Google

  try {
    // Send it to our new FastAPI route
    const res = await fetch("/auth/google", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ credential: googleCredential }),
    });

    if (res.ok) {
      const data = await res.json();

      // Save the Promitheus token exactly like standard login
      localStorage.setItem("promitheus_token", data.access_token);
      localStorage.setItem("username", data.username);
      // Show success and redirect!
      showNotification("Successfully logged in with Google! 🔥", "success");
      setTimeout(() => {
        window.location.href = "/dashboard";
      }, 1000);
    } else {
      const errorData = await res.json();
      showNotification(
        errorData.detail || "Google authentication failed",
        "error",
      );
    }
  } catch (err) {
    console.error("Google Login Error:", err);
    showNotification("Failed to connect to server.", "error");
  }
}

// ==========================================
// 🎒 PROFILE PAGE LOGIC
// ==========================================
async function renderProfile() {
  const profileMount = document.getElementById("profile-page-mount");
  if (!profileMount) return; // Only run this if we are on the profile page!

  const token = localStorage.getItem("promitheus_token");
  if (!token) {
    window.location.href = "/login";
    return;
  }

  try {
    const response = await fetch("/users/me", {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!response.ok) throw new Error("Failed to fetch profile");

    const userData = await response.json();

    // 1. Fill in the standard text stats
    document.getElementById("profile-username").textContent = userData.username;
    document.getElementById("profile-email").textContent =
      userData.email || "Google Authenticated";

    // Ensure these IDs match what you have in profile.html
    document.getElementById("profile-xp").textContent = userData.xp || 0;
    document.getElementById("profile-streak").textContent =
      userData.streak || 0;

    // 2. ✨ THE FIX: Update Quests and League boxes
    const questEl = document.getElementById("profile-quests-done");
    const leagueEl = document.getElementById("profile-league");

    if (questEl) questEl.textContent = userData.quests_completed || 0;
    if (leagueEl) leagueEl.textContent = userData.league || "Paper";

    // 3. Generate the unique DiceBear Avatar
    const seed = encodeURIComponent(userData.username);
    const avatarUrl = `https://api.dicebear.com/7.x/bottts/svg?seed=${seed}&backgroundColor=c0aede,d1d4f9,b6e3f4`;

    const avatarImg = document.getElementById("profile-avatar");
    if (avatarImg) avatarImg.src = avatarUrl;
  } catch (err) {
    console.error(err);
    // Optional: Only show notification if it's actually a 401 Unauthorized
    // showNotification("Session expired. Please log in again.", "error");
  }
}
