// Runs on every page.
import { api, applyTheme, getPref, play, setSoundEnabled, showFlash, soundEnabled, timezone, toast } from "./core.js";

// Let the server know the browser's timezone for server-rendered pages ("today", streaks).
document.cookie = `tz=${encodeURIComponent(timezone())}; path=/; max-age=31536000; samesite=lax`;

// Follow the OS theme live when the preference is "system".
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (getPref("theme", "system") === "system") applyTheme("system");
});

function syncSoundToggles() {
  const on = soundEnabled();
  document.querySelectorAll("[data-sound-toggle]").forEach((button) => {
    button.setAttribute("aria-pressed", String(on));
    button.title = on ? "Mute sound effects" : "Turn on sound effects";
    button.querySelector("[data-sound-on]")?.toggleAttribute("hidden", !on);
    button.querySelector("[data-sound-off]")?.toggleAttribute("hidden", on);
  });
}

document.addEventListener("click", async (event) => {
  const soundButton = event.target.closest("[data-sound-toggle]");
  if (soundButton) {
    setSoundEnabled(!soundEnabled());
    syncSoundToggles();
    play("tap");
    return;
  }

  const logout = event.target.closest("[data-logout]");
  if (logout) {
    event.preventDefault();
    try {
      await api("/auth/logout", { method: "POST" });
    } catch (error) {
      toast(error.message, { tone: "error" });
      return;
    }
    location.href = "/";
  }
});

syncSoundToggles();
showFlash();
