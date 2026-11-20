(function () {
  "use strict";
  const api = window.BookingApi;
  const root = document.querySelector('[data-page="verify"]');
  const form = root.querySelector("form");
  const input = form.querySelector("input[name=email]");
  const submit = form.querySelector("button[type=submit]");
  const title = root.querySelector("[data-verify-title]");
  const copy = root.querySelector("[data-verify-copy]");
  const cooldown = root.querySelector("[data-cooldown]");
  const email = sessionStorage.getItem("auth-verification-email");
  if (email) input.value = email;
  api.init().catch((error) => api.showAlert(api.responseMessage(error)));

  function startCooldown(raw) {
    const seconds = Math.max(0, Number.parseInt(raw, 10) || 0);
    if (!seconds) return;
    const ends = Date.now() + seconds * 1000;
    submit.disabled = true;
    const tick = () => {
      const remaining = Math.max(0, Math.ceil((ends - Date.now()) / 1000));
      cooldown.textContent = remaining ? `You can request another email in ${remaining} seconds.` : "You can request another email now.";
      if (!remaining) { window.clearInterval(timer); submit.disabled = false; }
    };
    tick();
    const timer = window.setInterval(tick, 1000);
  }

  const params = new URLSearchParams(window.location.search);
  const token = params.get("token");
  if (token) {
    window.history.replaceState(null, "", window.location.pathname);
    form.hidden = true;
    title.textContent = "Verifying your email";
    copy.textContent = "This should only take a moment.";
    api.post("/api/auth/verify", { token }).then(() => {
      title.textContent = "Email verified";
      copy.textContent = "Your account is ready. Sign in to continue.";
      api.showAlert("Your email has been verified.", "success");
      root.querySelector("a.button").textContent = "Sign in";
    }).catch((error) => {
      title.textContent = "This link can’t be used";
      copy.textContent = "It may have expired or already been used. Enter your email to request a fresh link.";
      form.hidden = false;
      api.showAlert(error.code === "invalid_token" ? "This verification link is invalid or has expired." : api.responseMessage(error));
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.checkValidity()) return;
    submit.disabled = true;
    submit.setAttribute("aria-busy", "true");
    try {
      const { response } = await api.post("/api/auth/resend-verification", { email: input.value });
      api.showAlert("If the account needs verification, a fresh email is on its way.", "success");
      startCooldown(response.headers.get("Retry-After"));
    } catch (error) {
      api.showAlert(api.responseMessage(error));
      if (error.status === 429) startCooldown(error.retryAfter);
      else submit.disabled = false;
    } finally { submit.setAttribute("aria-busy", "false"); }
  });
})();
