// Quiz player: one question at a time, graded by the server.
import { api, play, toast } from "./core.js";

const root = document.getElementById("quiz-app");
const mode = root.dataset.mode; // "lesson" | "practice"
const lessonId = root.dataset.lessonId;

const $ = (sel) => root.querySelector(sel);
const views = {
  loading: $('[data-view="loading"]'),
  error: $('[data-view="error"]'),
  question: $('[data-view="question"]'),
  results: $('[data-view="results"]'),
};
const bar = $("[data-action-bar]");
const primary = $("[data-primary]");
const feedback = $("[data-feedback]");
const progress = $("[data-progress]");
const counter = $("[data-counter]");
const quitDialog = document.querySelector("[data-quit-dialog]");
const reportDialog = document.querySelector("[data-report-dialog]");

const ICON = {
  check: '<svg class="size-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>',
  x: '<svg class="size-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>',
};

const KIND_LABEL = {
  short_answer: "Type the answer",
  fill_blank: "Fill in the blank",
  multiple_choice: "Choose the right answer",
  true_false: "True or false?",
  rearrange: "Put the pieces in order",
  explain: "Explain in your own words",
};
const PRAISE = ["Nicely done!", "Correct!", "You got it!", "Great work!", "Spot on!"];

const state = {
  attemptId: null,
  questions: [],
  index: 0,
  answer: null, // current answer value
  phase: "loading", // answering | checking | feedback | finishing | results
  lastResult: null,
  answered: 0,
};

function show(view) {
  Object.entries(views).forEach(([name, el]) => (el.hidden = name !== view));
}

function setProgress() {
  const total = state.questions.length || 1;
  const pct = Math.round((state.answered / total) * 100);
  progress.querySelector("span").style.width = `${pct}%`;
  progress.setAttribute("aria-valuenow", String(pct));
  counter.textContent = state.questions.length ? `${Math.min(state.index + 1, total)} / ${total}` : "";
}

function setPrimary(label, style = "primary", enabled = true) {
  primary.textContent = label;
  primary.className = `btn btn-lg w-full sm:w-auto sm:min-w-44 btn-${style}`;
  primary.disabled = !enabled;
}

// ---------- start ----------
async function start() {
  try {
    const data =
      mode === "practice"
        ? await api("/practice/attempts", { method: "POST" })
        : await api(`/lessons/${encodeURIComponent(lessonId)}/attempts`, { method: "POST" });
    state.attemptId = data.attempt_id;
    state.questions = data.questions;
    state.startedAt = Date.now();
    renderQuestion();
  } catch (error) {
    $("[data-error-title]").textContent =
      error.status === 404 && mode === "practice" ? "Nothing to practice" : "Couldn't load this lesson";
    $("[data-error-text]").textContent = error.message;
    show("error");
    bar.hidden = true;
  }
}

// ---------- rendering ----------
function renderQuestion() {
  const q = state.questions[state.index];
  state.answer = null;
  state.phase = "answering";
  bar.dataset.state = "idle";
  feedback.hidden = true;
  $("[data-spacer]").hidden = false;
  $("[data-results-actions]").hidden = true;
  primary.hidden = false;
  setPrimary(q.type === "explain" ? "Check with AI" : "Check", "primary", false);
  setProgress();

  $("[data-kind]").textContent = KIND_LABEL[q.type] || "Question";
  const promptEl = $("[data-prompt]");
  promptEl.textContent = "";
  const area = $("[data-answer-area]");
  area.textContent = "";

  const text = q.data.prompt || "";
  if (q.type === "fill_blank" && /_{2,}/.test(text)) {
    const match = text.match(/_{2,}/);
    const blank = document.createElement("span");
    blank.className = "inline-block min-w-20 mx-1 border-b-[3px] border-brand-fill align-baseline";
    blank.setAttribute("aria-label", "blank");
    promptEl.append(text.slice(0, match.index), blank, text.slice(match.index + match[0].length));
  } else {
    promptEl.textContent = text;
  }

  if (q.type === "multiple_choice" || q.type === "true_false") renderChoices(q, area);
  else if (q.type === "rearrange") renderRearrange(q, area);
  else renderText(q, area);

  show("question");
  promptEl.focus({ preventScroll: true });
  window.scrollTo({ top: 0 });
}

function renderChoices(q, area) {
  const list = document.createElement("div");
  list.className = "flex flex-col gap-3";
  list.setAttribute("role", "group");
  list.setAttribute("aria-label", "Answer options");
  q.data.options.forEach((option, i) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "option";
    button.setAttribute("aria-pressed", "false");
    button.dataset.value = option;
    const key = document.createElement("span");
    key.className = "key";
    key.textContent = String(i + 1);
    const label = document.createElement("span");
    label.textContent = option;
    button.append(key, label);
    button.addEventListener("click", () => selectOption(button));
    list.appendChild(button);
  });
  area.appendChild(list);
}

function selectOption(button) {
  if (state.phase !== "answering") return;
  button.parentElement.querySelectorAll(".option").forEach((b) => b.setAttribute("aria-pressed", "false"));
  button.setAttribute("aria-pressed", "true");
  state.answer = button.dataset.value;
  primary.disabled = false;
  play("tap");
}

function renderText(q, area) {
  const multiline = q.type === "explain";
  const field = document.createElement(multiline ? "textarea" : "input");
  field.className = "input text-lg";
  field.id = "answer-input";
  field.setAttribute("aria-label", "Your answer");
  field.autocomplete = "off";
  field.spellcheck = false;
  if (multiline) {
    field.rows = 5;
    field.maxLength = 2000;
    field.placeholder = "Write two or three sentences…";
  } else {
    field.type = "text";
    field.maxLength = 200;
    field.placeholder = q.type === "fill_blank" ? "The missing word" : "Your answer";
    field.setAttribute("enterkeyhint", "done");
  }
  field.addEventListener("input", () => {
    state.answer = field.value;
    primary.disabled = !field.value.trim();
  });
  area.appendChild(field);
  if (multiline) {
    const hint = document.createElement("p");
    hint.className = "field-hint";
    hint.textContent = "Press Ctrl + Enter to check.";
    area.appendChild(hint);
  }
  setTimeout(() => field.focus(), 50);
}

function renderRearrange(q, area) {
  const chunks = q.data.chunks;
  const placed = []; // indexes into chunks

  const answerZone = document.createElement("div");
  answerZone.className =
    "min-h-20 p-3 rounded-2xl border-2 border-dashed border-line-strong flex flex-wrap gap-2 items-start content-start";
  answerZone.setAttribute("aria-label", "Your answer");
  const bank = document.createElement("div");
  bank.className = "mt-6 flex flex-wrap gap-2 justify-center";
  bank.setAttribute("aria-label", "Pieces to use");

  const render = () => {
    answerZone.textContent = "";
    bank.textContent = "";
    if (!placed.length) {
      const empty = document.createElement("span");
      empty.className = "text-faint p-2";
      empty.textContent = "Tap the pieces below in the right order";
      answerZone.appendChild(empty);
    }
    placed.forEach((chunkIndex, position) => {
      answerZone.appendChild(
        chunkButton(chunks[chunkIndex], true, () => {
          placed.splice(position, 1);
          render();
        }),
      );
    });
    chunks.forEach((chunk, i) => {
      if (placed.includes(i)) return;
      bank.appendChild(
        chunkButton(chunk, false, () => {
          placed.push(i);
          play("tap");
          render();
        }),
      );
    });
    state.answer = placed.map((i) => chunks[i]);
    primary.disabled = placed.length !== chunks.length;
  };

  area.append(answerZone, bank);
  render();
}

function chunkButton(text, isPlaced, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `chunk${isPlaced ? " placed" : ""}`;
  button.textContent = text;
  button.addEventListener("click", () => state.phase === "answering" && onClick());
  return button;
}

// ---------- checking ----------
async function check() {
  const q = state.questions[state.index];
  if (state.phase !== "answering" || state.answer === null) return;
  state.phase = "checking";
  root.querySelectorAll("[data-answer-area] button, [data-answer-area] input, [data-answer-area] textarea").forEach((el) => {
    el.disabled = true;
  });
  primary.disabled = true;
  primary.innerHTML = `<span class="spinner"></span><span>${q.type === "explain" ? "Checking with AI…" : "Checking…"}</span>`;

  try {
    const result = await api(`/attempts/${state.attemptId}/answers`, {
      method: "POST",
      body: { question_id: q.question_id, answer: state.answer },
    });
    state.answered += 1;
    showFeedback(q, result);
  } catch (error) {
    toast(error.message, { tone: "error" });
    state.phase = "answering";
    root.querySelectorAll("[data-answer-area] button, [data-answer-area] input, [data-answer-area] textarea").forEach((el) => {
      el.disabled = false;
    });
    setPrimary(q.type === "explain" ? "Check with AI" : "Check", "primary", true);
  }
}

function showFeedback(q, result) {
  state.phase = "feedback";
  state.lastResult = result;
  setProgress();
  const ok = result.correct;
  play(ok ? "correct" : "wrong");

  // Mark choices
  if (q.type === "multiple_choice" || q.type === "true_false") {
    root.querySelectorAll(".option").forEach((button) => {
      if (button.dataset.value === result.correct_answer) button.dataset.result = "correct";
      else if (button.getAttribute("aria-pressed") === "true") button.dataset.result = "wrong";
    });
  }
  const input = root.querySelector("#answer-input");
  if (input) input.setAttribute("aria-invalid", String(!ok));
  if (!ok) $("[data-answer-area]").firstElementChild?.classList.add("animate-shake");

  bar.dataset.state = ok ? "correct" : "wrong";
  const iconEl = $("[data-feedback-icon]");
  iconEl.innerHTML = ok ? ICON.check : ICON.x;
  iconEl.className = `grid place-items-center size-11 rounded-full bg-surface shrink-0 ${ok ? "text-good" : "text-bad"}`;

  const title = $("[data-feedback-title]");
  const answerLine = $("[data-feedback-answer]");
  const explanation = $("[data-feedback-explanation]");
  title.className = `text-xl font-extrabold ${ok ? "text-good" : "text-bad"}`;
  answerLine.className = `mt-1 font-semibold ${ok ? "text-good" : "text-bad"}`;

  if (ok && result.typo) {
    title.textContent = "Correct, but check the spelling";
    answerLine.textContent = `It's spelled “${result.correct_answer}”.`;
  } else if (ok) {
    title.textContent = PRAISE[Math.floor(Math.random() * PRAISE.length)];
    answerLine.textContent = "";
  } else {
    title.textContent = "Not quite";
    answerLine.textContent =
      q.type === "explain" ? `A strong answer: ${result.correct_answer}` : `Correct answer: ${result.correct_answer}`;
  }
  explanation.textContent = q.type === "explain" ? result.feedback || result.explanation : result.explanation || "";
  explanation.hidden = !explanation.textContent;

  // "My answer should be accepted" only makes sense after a wrong answer.
  reportDialog.querySelector("[data-reason-accept]").hidden = ok;

  feedback.hidden = false;
  feedback.classList.remove("feedback-enter");
  void feedback.offsetWidth;
  feedback.classList.add("feedback-enter");
  $("[data-spacer]").hidden = true;

  const last = state.index === state.questions.length - 1;
  setPrimary(last ? "Finish" : "Continue", ok ? "good" : "bad", true);
  primary.focus({ preventScroll: true });
}

// ---------- flow ----------
async function next() {
  if (state.phase !== "feedback") return;
  if (state.index < state.questions.length - 1) {
    state.index += 1;
    renderQuestion();
  } else {
    await finish();
  }
}

async function finish() {
  state.phase = "finishing";
  setPrimary("Saving…", "primary", false);
  try {
    const result = await api(`/attempts/${state.attemptId}/complete`, { method: "POST" });
    showResults(result);
  } catch (error) {
    toast(error.message, { tone: "error" });
    state.phase = "feedback";
    setPrimary("Try again", "primary", true);
  }
}

function formatDuration(seconds) {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function showResults(result) {
  state.phase = "results";
  play("complete");
  counter.textContent = "";
  progress.querySelector("span").style.width = "100%";

  const accuracy = result.total ? Math.round((result.correct / result.total) * 100) : 0;
  $("[data-results-title]").textContent = mode === "practice" ? "Practice complete!" : "Lesson complete!";
  $("[data-results-subtitle]").textContent =
    result.xp_awarded === 0 && mode === "lesson" && result.correct > 0
      ? `You got ${result.correct} of ${result.total} right. Replays are practice, so no new XP.`
      : `You got ${result.correct} of ${result.total} right.`;
  $('[data-stat="xp"]').textContent = `+${result.xp_awarded}`;
  const accuracyEl = $('[data-stat="accuracy"]');
  accuracyEl.textContent = `${accuracy}%`;
  accuracyEl.classList.add(accuracy >= 80 ? "text-good" : accuracy >= 50 ? "text-gold" : "text-bad");
  $('[data-stat="time"]').textContent = formatDuration(
    result.duration_seconds ?? (Date.now() - state.startedAt) / 1000,
  );

  const streakNote = $("[data-streak-note]");
  if (result.streak_extended) {
    streakNote.querySelector("span").textContent =
      result.streak === 1 ? "You started a streak! Come back tomorrow to keep it." : `${result.streak} day streak! Keep it going tomorrow.`;
    streakNote.hidden = false;
  }
  const goalNote = $("[data-goal-note]");
  if (result.goal_reached_now) {
    goalNote.querySelector("span").textContent = `You hit today's goal of ${result.daily_goal} XP.`;
    goalNote.hidden = false;
  }

  const review = $("[data-review]");
  const list = $("[data-review-list]");
  list.textContent = "";
  result.mistakes.forEach((m) => {
    const item = document.createElement("li");
    item.className = "panel p-4";
    const prompt = document.createElement("p");
    prompt.className = "font-semibold";
    prompt.textContent = m.prompt;
    const yours = document.createElement("p");
    yours.className = "mt-2 text-sm text-bad";
    yours.textContent = `Your answer: ${m.your_answer || "(blank)"}`;
    const correct = document.createElement("p");
    correct.className = "mt-1 text-sm text-good font-semibold";
    correct.textContent = `Correct: ${m.correct_answer}`;
    item.append(prompt, yours, correct);
    if (m.explanation) {
      const why = document.createElement("p");
      why.className = "mt-2 text-sm text-muted";
      why.textContent = m.explanation;
      item.appendChild(why);
    }
    list.appendChild(item);
  });
  review.hidden = !result.mistakes.length;

  // Actions
  bar.dataset.state = "idle";
  feedback.hidden = true;
  $("[data-spacer]").hidden = false;
  primary.hidden = true;
  const actions = $("[data-results-actions]");
  actions.textContent = "";
  actions.hidden = false;
  actions.className = "flex flex-col-reverse sm:flex-row gap-3 w-full sm:w-auto";

  const secondary = [];
  if (mode === "lesson") secondary.push(["Retry lesson", () => location.reload()]);
  if (result.mistakes.length) secondary.push(["Practice mistakes", () => (location.href = "/practice/session")]);
  secondary.forEach(([label, onClick]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-lg btn-secondary";
    button.textContent = label;
    button.addEventListener("click", onClick);
    actions.appendChild(button);
  });
  const go = document.createElement("a");
  go.className = "btn btn-lg btn-primary sm:min-w-44";
  go.href = result.next_lesson_id ? `/quiz/${result.next_lesson_id}` : "/dashboard";
  go.textContent = result.next_lesson_id ? "Next lesson" : "Continue";
  actions.appendChild(go);

  show("results");
  go.focus({ preventScroll: true });
  window.scrollTo({ top: 0 });
}

// ---------- events ----------
primary.addEventListener("click", () => {
  if (state.phase === "answering") check();
  else if (state.phase === "feedback") next();
  else if (state.phase === "finishing") finish();
});

document.addEventListener("keydown", (event) => {
  if (document.querySelector("dialog[open]")) return;
  const q = state.questions[state.index];
  const inTextarea = event.target.tagName === "TEXTAREA";

  if (event.key === "Enter") {
    if (inTextarea && !(event.ctrlKey || event.metaKey)) return;
    if (event.target.tagName === "BUTTON" && event.target !== primary && state.phase === "answering") return;
    if (state.phase === "answering" && !primary.disabled) {
      event.preventDefault();
      check();
    } else if (state.phase === "feedback") {
      event.preventDefault();
      next();
    }
    return;
  }
  if (state.phase === "answering" && q && (q.type === "multiple_choice" || q.type === "true_false")) {
    const n = Number(event.key);
    const options = root.querySelectorAll(".option");
    if (n >= 1 && n <= options.length) selectOption(options[n - 1]);
  }
});

$("[data-quit]").addEventListener("click", () => {
  if (state.phase === "results" || state.phase === "loading") {
    location.href = mode === "practice" ? "/practice" : "/dashboard";
    return;
  }
  quitDialog.showModal();
});
quitDialog.addEventListener("close", () => {
  if (quitDialog.returnValue === "quit") location.href = mode === "practice" ? "/practice" : "/dashboard";
});

// Report a problem
$("[data-report]").addEventListener("click", () => {
  const form = reportDialog.querySelector("form");
  form.reset();
  reportDialog.querySelector("[data-report-send]").disabled = true;
  reportDialog.showModal();
});
reportDialog.querySelector("form").addEventListener("change", () => {
  reportDialog.querySelector("[data-report-send]").disabled = !reportDialog.querySelector('input[name="reason"]:checked');
});
reportDialog.addEventListener("close", async () => {
  if (reportDialog.returnValue !== "send") return;
  const q = state.questions[state.index];
  const reason = reportDialog.querySelector('input[name="reason"]:checked')?.value;
  const details = reportDialog.querySelector("textarea").value.trim() || null;
  try {
    const result = await api(`/questions/${q.question_id}/report`, {
      method: "POST",
      body: { reason, details, attempt_id: state.attemptId },
    });
    if (result.accepted) toast("Got it. Your answer will be accepted from now on.");
    else if (result.hidden) toast("Thanks. That question won't appear again.");
    else toast("Thanks for the report.");
  } catch (error) {
    toast(error.message, { tone: "error" });
  }
});

start();
