(function () {
  "use strict";
  let csrfToken = "";

  class ApiError extends Error {
    constructor(status, code, message, retryAfter) {
      super(message);
      this.status = status;
      this.code = code;
      this.retryAfter = retryAfter;
    }
  }

  async function init() {
    const response = await fetch("/api/auth/csrf", { credentials: "same-origin" });
    const payload = await response.json();
    if (!response.ok) throw new ApiError(response.status, payload?.error?.code, payload?.error?.message);
    csrfToken = payload.data.csrf_token;
  }

  async function request(path, options = {}) {
    const method = options.method || "GET";
    const headers = new Headers(options.headers || {});
    if (method !== "GET" && method !== "HEAD") {
      if (!csrfToken) await init();
      headers.set("X-CSRF-Token", csrfToken);
      headers.set("Content-Type", "application/json");
    }
    let response;
    try {
      response = await fetch(path, { ...options, method, headers, credentials: "same-origin" });
    } catch (error) {
      window.dispatchEvent(new CustomEvent("api:offline"));
      throw error;
    }
    let payload = {};
    try { payload = await response.json(); } catch (_) { payload = {}; }
    if (response.status === 401 && options.signedIn) {
      window.dispatchEvent(new CustomEvent("session:expired"));
    }
    if (!response.ok) {
      const problem = payload.error || {};
      throw new ApiError(response.status, problem.code || "request_failed", problem.message || "Something went wrong.", response.headers.get("Retry-After"));
    }
    return { data: payload.data, response };
  }

  const api = {
    init,
    get: (path, options = {}) => request(path, { ...options, method: "GET" }),
    post: (path, body, options = {}) => request(path, { ...options, method: "POST", body: JSON.stringify(body) }),
    ApiError,
  };

  function validityMessage(input) {
    const v = input.validity;
    if (v.valueMissing) return input.type === "email" ? "Enter your email address." : "This field is required.";
    if (v.typeMismatch && input.type === "email") return "Enter a valid email address.";
    if (v.tooShort) return `Use at least ${input.minLength} characters.`;
    if (v.tooLong) return `Use no more than ${input.maxLength} characters.`;
    return "Check this field and try again.";
  }

  function validateField(input) {
    if (!input.willValidate) return true;
    const error = document.getElementById(`${input.id}-error`);
    const valid = input.checkValidity();
    input.toggleAttribute("aria-invalid", !valid);
    if (error) error.textContent = valid ? "" : validityMessage(input);
    return valid;
  }

  function bindFields(root = document) {
    root.querySelectorAll("[data-field] input").forEach((input) => {
      input.addEventListener("blur", () => validateField(input));
      input.addEventListener("input", () => {
        if (input.getAttribute("aria-invalid") === "true") validateField(input);
        updateStrength(input);
      });
    });
    root.querySelectorAll("[data-password-field]").forEach((wrap) => {
      const input = wrap.querySelector("input");
      const toggle = wrap.querySelector(".password-toggle");
      toggle.addEventListener("click", () => {
        const visible = input.type === "password";
        input.type = visible ? "text" : "password";
        toggle.textContent = visible ? "Hide" : "Show";
        toggle.setAttribute("aria-label", visible ? "Hide password" : "Show password");
        toggle.setAttribute("aria-pressed", String(visible));
        input.focus();
      });
      input.addEventListener("keyup", (event) => {
        const caps = document.getElementById(`${input.id}-caps`);
        if (caps) caps.hidden = !event.getModifierState("CapsLock");
      });
    });
  }

  function updateStrength(input) {
    const wrap = input.closest("[data-field]");
    const meter = wrap?.querySelector("[data-strength]");
    if (!meter) return;
    const value = input.value;
    const groups = [/[a-z]/.test(value), /[A-Z]/.test(value), /\d/.test(value), /[^A-Za-z0-9]/.test(value)].filter(Boolean).length;
    const score = value.length < 10 ? 0 : Math.min(4, groups + (value.length >= 14 ? 1 : 0));
    const fill = meter.querySelector(".strength__fill");
    const label = meter.querySelector("[data-strength-label]");
    fill.dataset.level = String(score);
    fill.setAttribute("aria-label", `Strength ${score} of 4`);
    fill.style.setProperty("width", `${score * 25}%`);
    label.textContent = value.length === 0 ? "Not entered" : score < 2 ? "Weak" : score < 4 ? "Fair" : "Strong";
  }

  function bindForm(form) {
    if (!form) return;
    bindFields(form);
    form.addEventListener("submit", (event) => {
      const fields = Array.from(form.querySelectorAll("input"));
      const invalid = fields.filter((field) => !validateField(field));
      if (invalid.length) {
        event.preventDefault();
        invalid[0].focus();
      }
    }, true);
  }

  function showAlert(message, tone = "error", linkText = "", linkHref = "") {
    const alert = document.querySelector("[data-alert]");
    if (!alert) return;
    alert.hidden = false;
    alert.className = `alert alert--${tone}`;
    const copy = alert.querySelector("[data-alert-message]");
    copy.textContent = message;
    const priorLink = alert.querySelector("a");
    if (priorLink) priorLink.remove();
    if (linkText) {
      const link = document.createElement("a");
      link.href = linkHref;
      link.textContent = linkText;
      alert.querySelector(".alert__copy").append(link);
    }
  }

  function responseMessage(error) {
    if (error instanceof TypeError) return "You appear to be offline. Check your connection and try again.";
    if (error.status === 429) return "Too many requests. Please try again when the countdown ends.";
    if (error.status === 503 && error.code === "dependency_unavailable") return "Authentication is temporarily unavailable. Please try again.";
    return error.message || "Something went wrong. Please try again.";
  }

  function startRateLimitCountdown(error, button) {
    const header = error.retryAfter;
    let seconds = Number.parseInt(header, 10);
    if (!Number.isFinite(seconds) && header) seconds = Math.ceil((Date.parse(header) - Date.now()) / 1000);
    seconds = Math.max(0, seconds || 0);
    showAlert(responseMessage(error));
    if (!seconds || !button) return;
    let status = document.querySelector("[data-rate-countdown]");
    if (!status) {
      status = document.createElement("p");
      status.className = "field__help";
      status.setAttribute("data-rate-countdown", "");
      status.setAttribute("aria-live", "polite");
      button.insertAdjacentElement("afterend", status);
    }
    const ends = Date.now() + seconds * 1000;
    button.dataset.rateLimitActive = "true";
    button.disabled = true;
    button.setAttribute("aria-busy", "false");
    const tick = () => {
      const remaining = Math.max(0, Math.ceil((ends - Date.now()) / 1000));
      status.textContent = remaining ? `Try again in ${remaining} seconds.` : "You can try again now.";
      if (!remaining) {
        window.clearInterval(timer);
        button.dataset.rateLimitActive = "false";
        button.disabled = false;
      }
    };
    tick();
    const timer = window.setInterval(tick, 1000);
  }

  window.BookingApi = { ...api, bindFields, bindForm, validateField, showAlert, responseMessage, startRateLimitCountdown };
})();
