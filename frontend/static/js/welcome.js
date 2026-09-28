// Onboarding: daily goal, then the first lecture.
import { api, flash, setBusy, toast } from "./core.js";

const steps = {
  goal: document.querySelector('[data-welcome-step="goal"]'),
  lecture: document.querySelector('[data-welcome-step="lecture"]'),
};
const label = document.querySelector("[data-step-label]");
const uploader = steps.lecture.querySelector("[data-uploader]");
uploader.dataset.after = "event";

function go(step) {
  steps.goal.hidden = step !== "goal";
  steps.lecture.hidden = step !== "lecture";
  label.textContent = step === "goal" ? "Step 1 of 2" : "Step 2 of 2";
  steps[step].querySelector("h1").focus?.();
  window.scrollTo({ top: 0 });
}

async function finishOnboarding() {
  await api("/users/me", { method: "PATCH", body: { onboarded: true } });
}

document.querySelector("[data-goal-form]").addEventListener("submit", async (event) => {
  event.preventDefault();
  const goal = new FormData(event.target).get("goal");
  if (!goal) {
    toast("Pick a daily goal to continue.", { tone: "error" });
    return;
  }
  const button = event.target.querySelector('button[type="submit"]');
  setBusy(button, true, "Saving…");
  try {
    await api("/users/me", { method: "PATCH", body: { daily_xp_goal: Number(goal) } });
    go("lecture");
  } catch (error) {
    toast(error.message, { tone: "error" });
  } finally {
    setBusy(button, false);
  }
});

document.querySelector("[data-back]").addEventListener("click", () => go("goal"));

document.querySelector("[data-skip]").addEventListener("click", async () => {
  try {
    await finishOnboarding();
    location.href = "/dashboard";
  } catch (error) {
    toast(error.message, { tone: "error" });
  }
});

uploader.addEventListener("uploaded", async (event) => {
  try {
    await finishOnboarding();
  } catch {
    /* the lesson still works; onboarding will show again next time */
  }
  flash("Your first lessons are ready. Let's start!");
  const first = event.detail.first_lesson_id;
  location.href = first ? `/quiz/${first}` : "/dashboard";
});
