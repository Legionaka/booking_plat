(function () {
  "use strict";
  window.addEventListener("session:expired", () => {
    const dialog = document.querySelector("[data-session-modal]");
    const link = dialog?.querySelector("[data-modal-sign-in]");
    if (link) {
      const next = `${window.location.pathname}${window.location.search}`;
      link.href = `/auth/login?next=${encodeURIComponent(next)}`;
    }
    if (dialog && typeof dialog.showModal === "function" && !dialog.open) dialog.showModal();
  });
})();
