// Settings page.
import { api, applyTheme, confirmDialog, flash, getPref, play, setBusy, setPref, setSoundEnabled, soundEnabled, toast } from "./core.js";

function formError(form, message) {
  const box = form.querySelector("[data-form-error]");
  box.textContent = message || "";
  box.hidden = !message;
}

// Profile
const profileForm = document.querySelector("[data-profile-form]");
profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError(profileForm, "");
  const data = new FormData(profileForm);
  const button = profileForm.querySelector('button[type="submit"]');
  setBusy(button, true, "Saving…");
  try {
    await api("/users/me", { method: "PATCH", body: { username: data.get("username"), avatar: data.get("avatar") } });
    flash("Profile saved.");
    location.reload();
  } catch (error) {
    setBusy(button, false);
    formError(profileForm, error.message);
  }
});

// Daily goal: saves as soon as it's picked
document.querySelector("[data-goal-form]").addEventListener("change", async (event) => {
  try {
    await api("/users/me", { method: "PATCH", body: { daily_xp_goal: Number(event.target.value) } });
    toast(`Daily goal set to ${event.target.value} XP.`);
  } catch (error) {
    toast(error.message, { tone: "error" });
  }
});

// Theme
const themePref = getPref("theme", "system");
document.querySelectorAll('[data-theme-options] input').forEach((input) => {
  input.checked = input.value === themePref;
  input.addEventListener("change", () => {
    setPref("theme", input.value);
    applyTheme(input.value);
  });
});

// Sound
const soundSwitch = document.querySelector("[data-sound-switch]");
const knob = soundSwitch.querySelector("[data-knob]");
function syncSwitch() {
  const on = soundEnabled();
  soundSwitch.setAttribute("aria-checked", String(on));
  knob.style.transform = on ? "translateX(1.5rem)" : "none";
  document.querySelectorAll("[data-sound-toggle]").forEach((b) => {
    b.setAttribute("aria-pressed", String(on));
    b.querySelector("[data-sound-on]")?.toggleAttribute("hidden", !on);
    b.querySelector("[data-sound-off]")?.toggleAttribute("hidden", on);
  });
}
soundSwitch.addEventListener("click", () => {
  setSoundEnabled(!soundEnabled());
  syncSwitch();
  play("tap");
});
document.addEventListener("click", (event) => {
  if (event.target.closest("[data-sound-toggle]")) setTimeout(syncSwitch, 0);
});
syncSwitch();

const volume = document.querySelector("[data-volume]");
volume.value = getPref("volume", "0.7");
volume.addEventListener("change", () => {
  setPref("volume", volume.value);
  play("correct");
});
document.querySelector("[data-sound-preview]").addEventListener("click", () => {
  if (!soundEnabled()) {
    toast("Sound effects are off. Turn them on first.");
    return;
  }
  play("correct");
  setTimeout(() => play("wrong"), 450);
});

// Password
const passwordForm = document.querySelector("[data-password-form]");
passwordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError(passwordForm, "");
  const data = Object.fromEntries(new FormData(passwordForm));
  if ((data.new_password || "").length < 8) {
    formError(passwordForm, "Your new password needs at least 8 characters.");
    return;
  }
  const button = passwordForm.querySelector('button[type="submit"]');
  setBusy(button, true, "Saving…");
  try {
    const result = await api("/users/me/password", { method: "POST", body: data });
    passwordForm.reset();
    toast(result.message);
  } catch (error) {
    formError(passwordForm, error.message);
  } finally {
    setBusy(button, false);
  }
});

document.querySelector("[data-sign-out-all]").addEventListener("click", async () => {
  const ok = await confirmDialog({
    title: "Sign out everywhere?",
    body: "You'll be logged out on every device, including this one.",
    confirmLabel: "Sign out everywhere",
  });
  if (!ok) return;
  try {
    await api("/users/me/sign-out-everywhere", { method: "POST" });
    location.href = "/login";
  } catch (error) {
    toast(error.message, { tone: "error" });
  }
});

// Delete account
const deleteDialog = document.querySelector("[data-delete-dialog]");
const deleteInput = deleteDialog.querySelector("[data-delete-input]");
const deleteConfirm = deleteDialog.querySelector("[data-delete-confirm]");
const username = document.querySelector("#username").defaultValue;
document.querySelector("[data-delete-account]").addEventListener("click", () => {
  deleteInput.value = "";
  deleteConfirm.disabled = true;
  deleteDialog.showModal();
});
deleteInput.addEventListener("input", () => {
  deleteConfirm.disabled = deleteInput.value.trim().toLowerCase() !== username.toLowerCase();
});
deleteDialog.addEventListener("close", async () => {
  if (deleteDialog.returnValue !== "delete") return;
  try {
    await api("/users/me", { method: "DELETE", body: { confirm_username: deleteInput.value } });
    location.href = "/";
  } catch (error) {
    toast(error.message, { tone: "error" });
  }
});
