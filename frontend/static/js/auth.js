// Login, sign-up, forgot and reset password forms.
import { api, setBusy, toast } from "./core.js";

function showError(form, message) {
  const box = form.querySelector("[data-form-error]");
  if (!box) return toast(message, { tone: "error" });
  box.textContent = message;
  box.hidden = !message;
}

// Show / hide password
document.querySelectorAll("[data-toggle-password]").forEach((button) => {
  button.addEventListener("click", () => {
    const input = button.parentElement.querySelector("input");
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    button.setAttribute("aria-pressed", String(show));
    button.setAttribute("aria-label", show ? "Hide password" : "Show password");
    button.querySelector("[data-toggle-label]").textContent = show ? "Hide" : "Show";
  });
});

function messageFor(input) {
  if (input.validity.valueMissing) {
    const label = input.labels?.[0]?.textContent.trim().toLowerCase() || "this field";
    return `Enter your ${label}.`;
  }
  if (input.type === "email") return "Enter a valid email address, like name@example.com.";
  if (input.name === "username") return "Use 3–30 letters, numbers, dots, dashes or underscores.";
  if (input.type === "password") return "Use at least 8 characters.";
  return input.validationMessage;
}

// Shows a message under each invalid field; returns the first invalid one.
function firstInvalid(form) {
  let first = null;
  form.querySelectorAll("input[required]").forEach((input) => {
    const message = input.checkValidity() ? "" : messageFor(input);
    let error = form.querySelector(`[data-error-for="${input.name}"]`);
    if (!error) {
      error = document.createElement("p");
      error.className = "field-error";
      error.id = `${input.id}-error`;
      error.dataset.errorFor = input.name;
      (input.closest(".relative") || input).after(error);
      input.setAttribute("aria-describedby", `${input.getAttribute("aria-describedby") || ""} ${error.id}`.trim());
      input.addEventListener("input", () => {
        if (input.checkValidity()) {
          error.hidden = true;
          input.setAttribute("aria-invalid", "false");
        }
      });
    }
    error.textContent = message;
    error.hidden = !message;
    input.setAttribute("aria-invalid", String(Boolean(message)));
    if (message && !first) first = input;
  });
  return first;
}

// Login / sign-up
const authForm = document.querySelector("[data-auth-form]");
authForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const invalid = firstInvalid(authForm);
  if (invalid) {
    showError(authForm, "");
    invalid.focus();
    return;
  }
  showError(authForm, "");
  const signup = authForm.dataset.mode === "signup";
  const data = Object.fromEntries(new FormData(authForm));
  const button = authForm.querySelector('button[type="submit"]');
  setBusy(button, true, signup ? "Creating account…" : "Logging in…");
  try {
    const result = await api(signup ? "/auth/register" : "/auth/login", { method: "POST", body: data });
    location.href = signup ? "/welcome" : result.next === "/welcome" ? "/welcome" : authForm.dataset.next || "/dashboard";
  } catch (error) {
    setBusy(button, false);
    showError(authForm, error.message);
  }
});

// Google Identity Services calls this by name.
window.handleGoogleCredential = async (response) => {
  try {
    const result = await api("/auth/google", { method: "POST", body: { credential: response.credential } });
    location.href = result.next || "/dashboard";
  } catch (error) {
    if (authForm) showError(authForm, error.message);
    else toast(error.message, { tone: "error" });
  }
};

// Forgot password
const forgotForm = document.querySelector("[data-forgot-form]");
forgotForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const invalid = firstInvalid(forgotForm);
  if (invalid) {
    invalid.focus();
    return;
  }
  const button = forgotForm.querySelector('button[type="submit"]');
  setBusy(button, true, "Sending…");
  try {
    const result = await api("/auth/forgot-password", { method: "POST", body: Object.fromEntries(new FormData(forgotForm)) });
    forgotForm.hidden = true;
    const done = document.querySelector("[data-forgot-done]");
    done.querySelector("p").textContent = result.message;
    done.hidden = false;
  } catch (error) {
    setBusy(button, false);
    showError(forgotForm, error.message);
  }
});

// Reset password
const resetForm = document.querySelector("[data-reset-form]");
resetForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const invalid = firstInvalid(resetForm);
  if (invalid) {
    invalid.focus();
    return;
  }
  const data = Object.fromEntries(new FormData(resetForm));
  if (data.password !== data.confirm) {
    showError(resetForm, "The two passwords don't match.");
    return;
  }
  const button = resetForm.querySelector('button[type="submit"]');
  setBusy(button, true, "Saving…");
  try {
    await api("/auth/reset-password", { method: "POST", body: { token: data.token, password: data.password } });
    location.href = "/dashboard";
  } catch (error) {
    setBusy(button, false);
    showError(resetForm, error.message);
  }
});
