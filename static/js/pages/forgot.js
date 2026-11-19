(function () {
  "use strict";
  const api = window.BookingApi;
  const form = document.querySelector('[data-page="forgot"] form');
  const button = form.querySelector("button[type=submit]");
  api.init().catch((error) => api.showAlert(api.responseMessage(error)));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.checkValidity()) return;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    try {
      const email = new FormData(form).get("email");
      await api.post("/api/auth/forgot", { email });
      window.location.assign("/auth/forgot/sent");
    } catch (error) {
      if (error.status === 429) api.startRateLimitCountdown(error, button);
      else api.showAlert(api.responseMessage(error));
    } finally {
      if (button.dataset.rateLimitActive !== "true") button.disabled = false;
      button.setAttribute("aria-busy", "false");
    }
  });
})();
