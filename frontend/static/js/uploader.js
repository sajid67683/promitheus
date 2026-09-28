// Lecture upload: drag & drop or file picker, checked in the browser first,
// then staged progress while the AI builds the unit.
import { api, flash, play } from "./core.js";

const ALLOWED = [".pdf", ".txt"];

function setStep(zone, current) {
  const order = ["read", "write", "save"];
  zone.querySelectorAll("[data-step]").forEach((li) => {
    const idx = order.indexOf(li.dataset.step);
    const cur = order.indexOf(current);
    const dot = li.querySelector(".step-dot");
    li.classList.toggle("text-muted", idx > cur);
    li.classList.toggle("font-semibold", idx === cur);
    li.classList.toggle("text-good", idx < cur);
    dot.className = `step-dot size-2 rounded-full ${idx < cur ? "bg-good-fill" : idx === cur ? "bg-brand-fill animate-pulse" : "bg-line-strong"}`;
  });
}

function showError(zone, message) {
  zone.querySelector("[data-upload-busy]").hidden = true;
  zone.querySelector("[data-upload-idle]").hidden = false;
  const box = zone.querySelector("[data-upload-error]");
  box.querySelector("[data-upload-error-text]").textContent = message;
  box.hidden = false;
}

async function run(zone, request, label) {
  zone.querySelector("[data-upload-error]").hidden = true;
  zone.querySelector("[data-upload-idle]").hidden = true;
  zone.querySelector("[data-upload-busy]").hidden = false;
  zone.querySelector("[data-upload-file]").textContent = label;
  setStep(zone, "read");
  const writing = setTimeout(() => setStep(zone, "write"), 1200);

  try {
    const result = await request();
    clearTimeout(writing);
    setStep(zone, "save");
    play("complete");
    zone.dispatchEvent(new CustomEvent("uploaded", { detail: result, bubbles: true }));
    if (zone.dataset.after === "event") return;
    flash(result.message || "Your lessons are ready.");
    location.href = zone.dataset.after === "lesson" && result.first_lesson_id ? `/quiz/${result.first_lesson_id}` : location.pathname;
  } catch (error) {
    clearTimeout(writing);
    showError(zone, error.message);
  }
}

function uploadFile(zone, file) {
  const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  if (!ALLOWED.includes(ext)) {
    showError(zone, "That file type isn't supported. Upload a PDF or a .txt file.");
    return;
  }
  const maxMb = Number(zone.dataset.maxMb || 4);
  if (file.size > maxMb * 1024 * 1024) {
    showError(zone, `That file is larger than ${maxMb} MB. Try a smaller file.`);
    return;
  }
  const form = new FormData();
  form.append("file", file);
  run(zone, () => api("/upload/lecture", { method: "POST", form }), `Working on “${file.name}”`);
}

document.querySelectorAll("[data-uploader]").forEach((zone) => {
  const input = zone.querySelector("[data-upload-input]");
  input?.addEventListener("change", () => {
    if (input.files[0]) uploadFile(zone, input.files[0]);
    input.value = "";
  });

  zone.querySelector("[data-upload-sample]")?.addEventListener("click", () => {
    run(zone, () => api("/upload/sample", { method: "POST" }), "Building the sample lecture");
  });

  ["dragenter", "dragover"].forEach((type) =>
    zone.addEventListener(type, (event) => {
      event.preventDefault();
      zone.dataset.drag = "true";
    }),
  );
  ["dragleave", "drop"].forEach((type) =>
    zone.addEventListener(type, (event) => {
      event.preventDefault();
      if (type === "dragleave" && zone.contains(event.relatedTarget)) return;
      zone.dataset.drag = "false";
    }),
  );
  zone.addEventListener("drop", (event) => {
    const file = event.dataTransfer?.files?.[0];
    if (file) uploadFile(zone, file);
  });
});
