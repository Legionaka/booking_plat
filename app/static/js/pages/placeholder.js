(function () {
  "use strict";
  const api = window.BookingApi;
  const modal = document.querySelector("[data-session-modal]");
  const signIn = document.querySelector("[data-modal-sign-in]");
  const pageNext = `${window.location.pathname}${window.location.search}`;
  signIn.href = `/auth/login?next=${encodeURIComponent(pageNext)}`;
  window.addEventListener("session:expired", () => { if (!modal.open) modal.showModal(); });
  api.get("/api/auth/me", { signedIn: true }).then(({ data }) => {
    const user = data.user;
    const memberships = user.memberships || [];
    const workspace = memberships.find((item) => item.role === "owner" || item.role === "staff");
    document.querySelector("[data-user-name]").textContent = user.full_name;
    document.querySelector("[data-user-role]").textContent = workspace?.role || "customer";
    const workspaceLink = document.querySelector("[data-workspace-link]");
    if (workspaceLink) {
      workspaceLink.hidden = !workspace;
      if (workspace) workspaceLink.href = `/app/${workspace.business_id}/dashboard`;
    }
    document.querySelector("[data-sign-out]").hidden = false;
  }).catch((error) => { if (error.status !== 401) api.showAlert(api.responseMessage(error)); });
  document.querySelector("[data-sign-out]").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    try { await api.post("/api/auth/logout", {}, { signedIn: true }); window.location.assign("/auth/login"); }
    catch (error) { api.showAlert(api.responseMessage(error)); button.disabled = false; button.setAttribute("aria-busy", "false"); }
  });
})();
