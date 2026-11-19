(function () {
  "use strict";
  const api = window.BookingApi;
  const root = document.querySelector('[data-page="reset"]');
  const form = root.querySelector("form");
  const button = form.querySelector("button[type=submit]");
  const title = root.querySelector("[data-reset-title]");
  const copy = root.querySelector("[data-reset-copy]");
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token");
  if (token) window.history.replaceState(null, "", window.location.pathname);
  api.init().catch((error) => api.showAlert(api.responseMessage(error)));
  if (!token) {
    title.textContent = "This link can’t be used";
    copy.textContent = "Request a fresh password reset email to continue.";
    form.hidden = true;
    api.showAlert("This password reset link is invalid or has expired.");
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!token || !form.checkValidity()) return;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    try {
      const newPassword = new FormData(form).get("new_password");
      await api.post("/api/auth/reset", { token, new_password: newPassword });
      title.textContent = "Password updated";
      copy.textContent = "Your password has been changed. Sign in with your new password.";
      form.hidden = true;
      api.showAlert("Your password was updated.", "success");
    } catch (error) {
      if (error.status === 429) {
        api.startRateLimitCountdown(error, button);
        return;
      }
      if (error.code === "invalid_token") {
        title.textContent = "This link can’t be used";
        copy.textContent = "Request a fresh password reset email to continue.";
        form.hidden = true;
      }
      api.showAlert(api.responseMessage(error));
    } finally {
      if (button.dataset.rateLimitActive !== "true") button.disabled = false;
      button.setAttribute("aria-busy", "false");
    }
  });
})();
