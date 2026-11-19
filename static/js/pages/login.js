(function () {
  "use strict";
  const api = window.BookingApi;
  const root = document.querySelector('[data-page="login"]');
  const form = root?.querySelector("form");
  const button = form?.querySelector("button[type=submit]");
  api.init().catch((error) => api.showAlert(api.responseMessage(error)));

  const slug = root?.dataset.business;
  if (slug) {
    api.get(`/api/b/${encodeURIComponent(slug)}`).then(({ data }) => {
      if (data?.name) {
        document.querySelector("#page-heading").textContent = `Sign in to ${data.name}`;
        document.querySelector(".auth-brand").textContent = data.name;
        document.querySelector("[data-business-name]").textContent = data.name;
        document.querySelector("[data-business-location]").textContent = data.name;
      }
    }).catch(() => {});
  }

  function safeNext(value) {
    return value && value.startsWith("/") && !value.startsWith("//") && !value.includes("\\") && !/[\r\n]/.test(value) ? value : null;
  }
  function setBusy(busy) {
    button.disabled = busy;
    button.setAttribute("aria-busy", String(busy));
  }
  function startCooldown(button, retryAfter) {
    const seconds = Math.max(0, Number.parseInt(retryAfter, 10) || 0);
    if (!seconds) { button.disabled = false; return; }
    const ends = Date.now() + seconds * 1000;
    const tick = () => {
      const remaining = Math.max(0, Math.ceil((ends - Date.now()) / 1000));
      button.textContent = remaining ? `Resend verification email in ${remaining} seconds` : "Resend verification email";
      button.disabled = remaining > 0;
      if (!remaining) window.clearInterval(timer);
    };
    tick();
    const timer = window.setInterval(tick, 1000);
  }

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.checkValidity()) return;
    const values = new FormData(form);
    setBusy(true);
    try {
      await api.post("/api/auth/login", { email: values.get("email"), password: values.get("password") });
      const { data } = await api.get("/api/auth/me");
      const memberships = data.user.memberships || [];
      if (memberships.some((item) => item.role === "owner" || item.role === "staff")) {
        window.location.assign("/app");
        return;
      }
      window.location.assign(safeNext(root.dataset.next) || "/account");
    } catch (error) {
      if (error.code === "email_not_verified") {
        sessionStorage.setItem("auth-verification-email", String(values.get("email")));
        api.showAlert("Your email address needs verification before you can sign in.");
        root.querySelector("[data-verification-link]").hidden = false;
        root.querySelector("[data-resend-from-login]").hidden = false;
      } else {
        if (error.status === 429) api.startRateLimitCountdown(error, button);
        else api.showAlert(error.code === "invalid_credentials" ? "Email or password is incorrect." : api.responseMessage(error));
      }
    } finally {
      if (button.dataset.rateLimitActive !== "true") setBusy(false);
      else button.setAttribute("aria-busy", "false");
    }
  });

  root?.querySelector("[data-resend-from-login]")?.addEventListener("click", async (event) => {
    const resend = event.currentTarget;
    resend.disabled = true;
    try {
      const email = sessionStorage.getItem("auth-verification-email");
      const { response } = await api.post("/api/auth/resend-verification", { email });
      api.showAlert("If the account needs verification, a fresh email is on its way.", "success");
      startCooldown(resend, response.headers.get("Retry-After"));
    } catch (error) {
      api.showAlert(api.responseMessage(error));
      if (error.status === 429) startCooldown(resend, error.retryAfter);
      else resend.disabled = false;
    }
  });
})();
