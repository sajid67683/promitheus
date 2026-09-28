// The landing page's sample question.
import { play } from "./core.js";

const demo = document.querySelector("[data-demo]");
const CORRECT = "Chlorophyll";

demo?.querySelectorAll("[data-demo-option]").forEach((button) => {
  button.addEventListener("click", () => {
    const right = button.dataset.demoOption === CORRECT;
    demo.querySelectorAll("[data-demo-option]").forEach((b) => {
      b.disabled = true;
      if (b.dataset.demoOption === CORRECT) b.dataset.result = "correct";
    });
    if (!right) button.dataset.result = "wrong";
    play(right ? "correct" : "wrong");

    const box = demo.querySelector("[data-demo-feedback]");
    box.className = `mt-5 rounded-2xl px-4 py-3 ${right ? "bg-good-soft text-good" : "bg-bad-soft text-bad"}`;
    box.querySelector("[data-demo-title]").textContent = right ? "Nicely done!" : "Not quite. It's chlorophyll.";
    box.hidden = false;
    demo.querySelector("[data-demo-hint]").innerHTML =
      'That\'s one question. <a class="font-semibold text-brand hover:underline" href="/signup">Make lessons from your own lecture</a>';
  });
});
