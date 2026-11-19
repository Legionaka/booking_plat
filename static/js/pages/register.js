(function () {
  "use strict";
  const api = window.BookingApi;
  const form = document.querySelector('[data-page="register"] form');
  const button = form?.querySelector("button[type=submit]");
  api.init().catch((error) => api.showAlert(api.responseMessage(error)));
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.checkValidity()) return;
    const values = new FormData(form);
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    try {
      await api.post("/api/auth/register", { full_name: values.get("full_name"), email: values.get("email"), password: values.get("password") });
      sessionStorage.setItem("auth-verification-email", String(values.get("email")));
      window.location.assign("/auth/verify");
    } catch (error) {
      if (error.code === "email_in_use") {
        api.showAlert("An account with this email already exists.", "error", "Sign in instead", "/auth/login");
      } else if (error.status === 429) api.startRateLimitCountdown(error, button);
      else api.showAlert(api.responseMessage(error));
    } finally {
      if (button.dataset.rateLimitActive !== "true") button.disabled = false;
      button.setAttribute("aria-busy", "false");
    }
  });
})();
