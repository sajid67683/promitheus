// Library: rename, regenerate and delete units.
import { api, confirmDialog, flash, toast } from "./core.js";

const renameDialog = document.querySelector("[data-rename-dialog]");
let renaming = null;

function closeMenus(except) {
  document.querySelectorAll("[data-menu]").forEach((menu) => {
    if (menu === except) return;
    menu.hidden = true;
    menu.parentElement.querySelector("[data-menu-button]").setAttribute("aria-expanded", "false");
  });
}

document.addEventListener("click", async (event) => {
  const menuButton = event.target.closest("[data-menu-button]");
  if (menuButton) {
    const menu = menuButton.parentElement.querySelector("[data-menu]");
    closeMenus(menu);
    menu.hidden = !menu.hidden;
    menuButton.setAttribute("aria-expanded", String(!menu.hidden));
    if (!menu.hidden) menu.querySelector("[role=menuitem]").focus();
    return;
  }

  const action = event.target.closest("[data-action]");
  if (!action) {
    if (!event.target.closest("[data-menu]")) closeMenus();
    return;
  }
  closeMenus();
  const item = action.closest("[data-unit]");
  const id = item.dataset.unit;
  const title = item.dataset.title;

  if (action.dataset.action === "rename") {
    renaming = item;
    renameDialog.querySelector("input").value = title;
    renameDialog.showModal();
    renameDialog.querySelector("input").select();
  }

  if (action.dataset.action === "delete") {
    const ok = await confirmDialog({
      title: `Delete “${title}”?`,
      body: "Its lessons and questions will be removed. XP you've already earned stays.",
      confirmLabel: "Delete unit",
      danger: true,
    });
    if (!ok) return;
    try {
      await api(`/materials/${id}`, { method: "DELETE" });
      item.remove();
      toast(`Deleted “${title}”.`);
    } catch (error) {
      toast(error.message, { tone: "error" });
    }
  }

  if (action.dataset.action === "regenerate") {
    const ok = await confirmDialog({
      title: "Make new questions?",
      body: "We'll write a fresh set of questions from the same lecture. Progress on this unit's lessons starts over; your XP stays.",
      confirmLabel: "Make new questions",
    });
    if (!ok) return;
    item.setAttribute("aria-busy", "true");
    item.style.opacity = "0.6";
    toast("Writing new questions. This takes up to a minute…");
    try {
      const result = await api(`/materials/${id}/regenerate`, { method: "POST" });
      flash(result.message);
      location.reload();
    } catch (error) {
      item.removeAttribute("aria-busy");
      item.style.opacity = "";
      toast(error.message, { tone: "error" });
    }
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeMenus();
});

renameDialog?.addEventListener("close", async () => {
  if (renameDialog.returnValue !== "save" || !renaming) return;
  const title = renameDialog.querySelector("input").value.trim();
  if (!title) return;
  try {
    const result = await api(`/materials/${renaming.dataset.unit}`, { method: "PATCH", body: { title } });
    renaming.dataset.title = result.title;
    renaming.querySelector("[data-unit-title]").textContent = result.title;
    toast("Renamed.");
  } catch (error) {
    toast(error.message, { tone: "error" });
  }
});
