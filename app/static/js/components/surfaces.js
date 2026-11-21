(function () {
  "use strict";
  const focusable = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
  let previousFocus = null;

  function openDialog(dialog) {
    if (!dialog || typeof dialog.showModal !== "function") return;
    previousFocus = document.activeElement;
    dialog.showModal();
    const target = dialog.querySelector(focusable);
    if (target) target.focus();
  }

  document.addEventListener("click", (event) => {
    const openButton = event.target.closest("[data-dialog-open]");
    if (openButton) openDialog(document.getElementById(openButton.dataset.dialogOpen));
    if (event.target.closest("[data-palette-open]")) openDialog(document.querySelector("[data-palette]"));
    if (event.target.closest("[data-dialog-close]")) event.target.closest("dialog")?.close();
    const dropdownTrigger = event.target.closest("[data-dropdown-trigger]");
    if (dropdownTrigger) {
      const menu = document.getElementById(dropdownTrigger.getAttribute("aria-controls"));
      const expanded = dropdownTrigger.getAttribute("aria-expanded") === "true";
      dropdownTrigger.setAttribute("aria-expanded", String(!expanded));
      if (menu) menu.hidden = expanded;
    }
    const tab = event.target.closest('[role="tab"]');
    if (tab) activateTab(tab);
  });

  function activateTab(tab) {
    const list = tab.closest('[role="tablist"]');
    const tabs = Array.from(list.querySelectorAll('[role="tab"]'));
    tabs.forEach((item) => {
      const active = item === tab;
      item.setAttribute("aria-selected", String(active));
      item.tabIndex = active ? 0 : -1;
      const panel = document.getElementById(item.getAttribute("aria-controls"));
      if (panel) panel.hidden = !active;
    });
    tab.focus();
  }

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openDialog(document.querySelector("[data-palette]"));
    }
    const dialog = event.target.closest("dialog[open]");
    if (event.key === "Escape" && dialog) dialog.close();
    if (event.key === "Tab" && dialog) {
      const items = Array.from(dialog.querySelectorAll(focusable)).filter((item) => item.offsetParent !== null);
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  document.addEventListener("close", (event) => {
    if (event.target.matches("dialog") && previousFocus?.isConnected) previousFocus.focus();
  }, true);
})();
