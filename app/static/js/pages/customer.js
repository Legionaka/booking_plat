(function () {
  "use strict";
  const root = document.querySelector("[data-customer-page]");
  if (!root) return;
  const api = window.BookingApi;
  const view = root.dataset.view;
  const slug = root.dataset.businessSlug;
  const bookingId = root.dataset.bookingId;
  const state = root.querySelector("[data-page-state]");
  const params = new URLSearchParams(window.location.search);
  let business = null;
  let services = [];
  let staff = [];
  let selectedSlot = null;
  let currentBooking = null;

  root.querySelectorAll("[data-section]").forEach((section) => {
    section.hidden = section.dataset.section !== view;
  });

  function setState(message = "", tone = "info") {
    state.textContent = message;
    state.dataset.tone = tone;
    state.hidden = !message;
  }

  window.addEventListener("api:offline", () => setState("You appear to be offline. Check your connection and try again.", "offline"));

  function money(cents) {
    return new Intl.NumberFormat("en-ZA", { style: "currency", currency: "ZAR" }).format((cents || 0) / 100);
  }

  function businessDate(date = new Date()) {
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: business?.timezone || "Africa/Johannesburg", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(date);
    return `${parts.find((x) => x.type === "year").value}-${parts.find((x) => x.type === "month").value}-${parts.find((x) => x.type === "day").value}`;
  }

  function addDays(value, count) {
    const date = new Date(`${value}T12:00:00Z`);
    date.setUTCDate(date.getUTCDate() + count);
    return date.toISOString().slice(0, 10);
  }

  function dateLabel(value) {
    const date = new Date(`${value}T12:00:00Z`);
    return new Intl.DateTimeFormat("en-ZA", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(date);
  }

  function dateTime(value, timezone = business?.timezone || "Africa/Johannesburg") {
    return new Intl.DateTimeFormat("en-ZA", { dateStyle: "medium", timeStyle: "short", timeZone: timezone }).format(new Date(value));
  }

  function serviceById(id) { return services.find((item) => String(item.id) === String(id)); }
  function displayService(item) { return item?.name || "Appointment"; }

  async function get(path, signedIn = false) {
    return (await api.get(path, { signedIn })).data;
  }

  function errorMessage(error) {
    if (error.status === 429) return `Too many requests. Try again${error.retryAfter ? ` in ${error.retryAfter} seconds` : " shortly"}.`;
    if (error.status === 503) return "This service is temporarily unavailable. Please try again shortly.";
    if (error.status === 422) return error.message || "Check the information and try again.";
    return error.message || "Something went wrong. Please try again.";
  }

  function showFailure(error) {
    if (error.status === 409 && error.code === "slot_taken") {
      setState("That time was just taken. Choose another slot; availability will refresh when you return to the time picker.", "error");
      const link = document.createElement("a");
      link.className = "button button--secondary";
      link.href = `/b/${encodeURIComponent(slug)}/book/time?service=${encodeURIComponent(params.get("service") || "")}&staff=${encodeURIComponent(params.get("staff") || "any")}`;
      link.textContent = "Pick another time";
      state.append(" ", link);
      return;
    }
    if (error.status === 403 && error.code === "late_cancellation") {
      root.querySelectorAll("[data-late-state]").forEach((node) => { node.hidden = false; });
      setState("This booking is inside the cancellation cutoff. Contact the business to change it.", "error");
      return;
    }
    setState(errorMessage(error), "error");
  }

  function serviceCard(item, target) {
    const card = document.createElement("a");
    card.className = "service-card";
    card.href = `${target}?service=${encodeURIComponent(item.id)}&staff=any`;
    const name = document.createElement("h3"); name.textContent = item.name;
    const description = document.createElement("p"); description.textContent = item.description || `${item.duration_min} minutes`;
    const detail = document.createElement("p"); detail.className = "service-card__price";
    detail.textContent = `${item.duration_min} min · ${money(item.price_cents)}${item.deposit_cents ? ` · ${money(item.deposit_cents)} deposit` : ""}`;
    card.append(name, description, detail);
    return card;
  }

  async function loadBusiness() {
    const [businessResponse, servicesResponse, staffResponse] = await Promise.all([
      get(`/api/b/${encodeURIComponent(slug)}`),
      get(`/api/b/${encodeURIComponent(slug)}/services`),
      get(`/api/b/${encodeURIComponent(slug)}/staff`),
    ]);
    business = businessResponse;
    services = servicesResponse || [];
    staff = staffResponse || [];
    root.querySelectorAll("[data-business-name]").forEach((node) => { node.textContent = business.name; });
    root.querySelectorAll("[data-business-meta]").forEach((node) => { node.textContent = `Book online with ${business.name} · ${business.timezone}`; });
    const landing = root.querySelector("[data-landing-services]");
    if (landing) {
      landing.replaceChildren(...services.map((item) => serviceCard(item, `/b/${encodeURIComponent(slug)}/book`)));
      if (!services.length) landing.append(emptyMessage("No services are available for online booking yet."));
    }
    return business;
  }

  function emptyMessage(message) {
    const node = document.createElement("p");
    node.className = "customer-empty";
    node.textContent = message;
    return node;
  }

  async function loadNextSlot() {
    const output = root.querySelector("[data-next-slot-value]");
    const service = services[0];
    if (!service || !output) return;
    const from = businessDate();
    const to = addDays(from, Math.min(60, Number(window.bookingMaxAdvanceDays || 60)));
    const range = await get(`/api/b/${encodeURIComponent(slug)}/availability?service=${service.id}&staff=any&from=${from}&to=${to}`);
    const openDay = (range.days || []).find((day) => day.open);
    if (!openDay) { output.textContent = "No upcoming slots available"; return; }
    const slots = await get(`/api/b/${encodeURIComponent(slug)}/slots?service=${service.id}&staff=any&date=${openDay.date}`);
    const first = slots.slots?.[0];
    if (!first) { output.textContent = "Check back for availability"; return; }
    output.textContent = `${dateTime(first.start_at)} · ${business.name}`;
    const link = root.querySelector("[data-next-slot] .button");
    if (link) link.href = `/b/${encodeURIComponent(slug)}/book/time?service=${service.id}&staff=any&date=${openDay.date}`;
  }

  function chosenService() { return params.get("service") || ""; }
  function chosenStaff() { return params.get("staff") || "any"; }

  async function initServices() {
    const [serviceResponse, staffResponse] = await Promise.all([
      get(`/api/b/${encodeURIComponent(slug)}/services`),
      get(`/api/b/${encodeURIComponent(slug)}/staff`),
    ]);
    services = serviceResponse || [];
    staff = staffResponse || [];
    const list = root.querySelector("[data-service-list]");
    const select = root.querySelector("[data-staff-select]");
    const next = root.querySelector("[data-continue-time]");
    const serviceId = chosenService();
    if (serviceId && staff.length) {
      const from = businessDate();
      const to = addDays(from, 60);
      const availability = await Promise.all(staff.map(async (person) => {
        try {
          const result = await get(
            `/api/b/${encodeURIComponent(slug)}/availability?service=${serviceId}`
            + `&staff=${person.id}&from=${from}&to=${to}`
          );
          return { person, available: (result.days || []).some((day) => day.open) };
        } catch (error) {
          if (error.status === 404 || error.status === 422) return { person, available: false };
          throw error;
        }
      }));
      staff = availability.filter((item) => item.available).map((item) => item.person);
    }
    list.replaceChildren();
    services.forEach((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "service-card";
      button.setAttribute("aria-pressed", String(String(item.id) === chosenService()));
      const title = document.createElement("h3"); title.textContent = item.name;
      const description = document.createElement("p"); description.textContent = item.description || `${item.duration_min} minutes`;
      const price = document.createElement("p"); price.className = "service-card__price"; price.textContent = `${money(item.price_cents)}${item.deposit_cents ? ` · ${money(item.deposit_cents)} deposit` : ""}`;
      button.append(title, description, price);
      button.addEventListener("click", () => {
        list.querySelectorAll(".service-card").forEach((card) => card.setAttribute("aria-pressed", "false"));
        button.setAttribute("aria-pressed", "true");
        params.set("service", String(item.id));
        next.disabled = false;
      });
      list.append(button);
    });
    if (!services.length) list.append(emptyMessage("No services are available for booking."));
    staff.forEach((member) => {
      const option = document.createElement("option"); option.value = String(member.id); option.textContent = member.display_name; select.append(option);
    });
    select.value = chosenStaff();
    next.disabled = !chosenService();
    next.addEventListener("click", () => {
      if (!chosenService()) return;
      const selectedStaff = select.value || "any";
      window.location.assign(`/b/${encodeURIComponent(slug)}/book/time?service=${encodeURIComponent(chosenService())}&staff=${encodeURIComponent(selectedStaff)}`);
    });
  }

  function renderSlots(container, slots, onSelect) {
    container.replaceChildren();
    if (!slots.length) { container.append(emptyMessage("No available times on this date. Choose another date.")); return; }
    slots.forEach((slot) => {
      const time = slot.local_start || dateTime(slot.start_at);
      const button = document.createElement("button");
      button.type = "button"; button.className = "slot-key"; button.textContent = time;
      button.addEventListener("click", () => {
        container.querySelectorAll(".slot-key").forEach((node) => { node.classList.remove("slot-key--selected"); node.setAttribute("aria-pressed", "false"); });
        button.classList.add("slot-key--selected"); button.setAttribute("aria-pressed", "true");
        onSelect(slot);
      });
      container.append(button);
    });
  }

  async function initTime() {
    const serviceId = chosenService();
    if (!serviceId) throw new Error("Choose a service before selecting a time.");
    const [businessResponse, serviceResponse, staffResponse] = await Promise.all([
      get(`/api/b/${encodeURIComponent(slug)}`),
      get(`/api/b/${encodeURIComponent(slug)}/services`),
      get(`/api/b/${encodeURIComponent(slug)}/staff`),
    ]);
    business = businessResponse; services = serviceResponse || []; staff = staffResponse || [];
    const service = serviceById(serviceId);
    if (!service) throw new Error("That service is no longer available. Choose another service.");
    root.querySelector("[data-summary-service]").textContent = service.name;
    root.querySelector("[data-summary-staff]").textContent = staff.find((person) => String(person.id) === chosenStaff())?.display_name || "Anyone available";
    const dateInput = root.querySelector("[data-booking-date]");
    const initialDate = params.get("date") || businessDate();
    dateInput.min = businessDate(); dateInput.value = initialDate;
    const list = root.querySelector("[data-slot-list]");
    const reviewLink = root.querySelector("[data-review-link]");
    const strip = root.querySelector("[data-availability-strip]");
    async function loadDate(date) {
      setState("Loading available times…");
      const result = await get(`/api/b/${encodeURIComponent(slug)}/slots?service=${serviceId}&staff=${encodeURIComponent(chosenStaff())}&date=${date}`);
      renderSlots(list, result.slots || [], (slot) => {
        selectedSlot = slot;
        root.querySelector("[data-summary-date]").textContent = `${dateLabel(date)} · ${slot.local_start || dateTime(slot.start_at)}`;
        reviewLink.href = `/b/${encodeURIComponent(slug)}/book/review?service=${serviceId}&staff=${encodeURIComponent(chosenStaff())}&start_at=${encodeURIComponent(slot.start_at)}&staff_id=${encodeURIComponent(chosenStaff() === "any" ? (slot.staff_ids || ["any"])[0] : chosenStaff())}`;
        reviewLink.setAttribute("aria-disabled", "false");
      });
      setState(result.slots?.length ? "Times updated." : "No times available on this date.", result.slots?.length ? "success" : "info");
    }
    dateInput.addEventListener("change", () => loadDate(dateInput.value).catch(showFailure));
    const from = businessDate();
    const to = addDays(from, 6);
    const range = await get(`/api/b/${encodeURIComponent(slug)}/availability?service=${serviceId}&staff=${encodeURIComponent(chosenStaff())}&from=${from}&to=${to}`);
    strip.replaceChildren();
    (range.days || []).forEach((day) => {
      const button = document.createElement("button"); button.type = "button"; button.className = "availability-day";
      button.textContent = dateLabel(day.date); button.disabled = !day.open; button.setAttribute("aria-pressed", String(day.date === initialDate));
      button.addEventListener("click", () => {
        strip.querySelectorAll("button").forEach((item) => item.setAttribute("aria-pressed", "false"));
        button.setAttribute("aria-pressed", "true"); dateInput.value = day.date;
        loadDate(day.date).catch(showFailure);
      });
      strip.append(button);
    });
    root.querySelector("[data-review-link]").addEventListener("click", (event) => {
      if (reviewLink.getAttribute("aria-disabled") === "true") event.preventDefault();
    });
    await loadDate(initialDate);
  }

  async function initReview() {
    const serviceId = params.get("service");
    const startAt = params.get("start_at");
    if (!serviceId || !startAt) throw new Error("Select a service and time before confirming your booking.");
    const [businessResponse, serviceResponse, staffResponse] = await Promise.all([
      get(`/api/b/${encodeURIComponent(slug)}`), get(`/api/b/${encodeURIComponent(slug)}/services`), get(`/api/b/${encodeURIComponent(slug)}/staff`),
    ]);
    business = businessResponse; services = serviceResponse || []; staff = staffResponse || [];
    const item = serviceById(serviceId);
    if (!item) throw new Error("That service is no longer available.");
    const staffId = params.get("staff_id") || chosenStaff();
    root.querySelector("[data-review-service]").textContent = `${item.name} · ${item.duration_min} minutes`;
    root.querySelector("[data-review-staff]").textContent = staff.find((person) => String(person.id) === staffId)?.display_name || "Team member selected based on availability";
    root.querySelector("[data-review-time]").textContent = dateTime(startAt);
    root.querySelector("[data-review-price]").textContent = `Service total: ${money(item.price_cents)}`;
    root.querySelector("[data-review-deposit]").textContent = item.deposit_cents ? `Deposit due now: ${money(item.deposit_cents)}` : "No deposit required";
    root.querySelector("[data-back-to-time]").href = `/b/${encodeURIComponent(slug)}/book/time?service=${serviceId}&staff=${encodeURIComponent(chosenStaff())}`;
    root.querySelector("[data-booking-submit]").addEventListener("click", async (event) => {
      const button = event.currentTarget; button.disabled = true; button.setAttribute("aria-busy", "true");
      try {
        const result = await api.post(`/api/b/${encodeURIComponent(slug)}/bookings`, { service_id: Number(serviceId), staff_id: staffId, start_at: startAt }, { signedIn: true });
        const booking = result.data;
        if (booking.deposit_cents > 0) {
          await api.post(`/api/bookings/${booking.id}/pay`, {}, { signedIn: true });
          await api.init();
          const form = document.createElement("form"); form.method = "post"; form.action = `/payments/handoff/${booking.id}`;
          const token = document.createElement("input"); token.type = "hidden"; token.name = "csrf_token"; token.value = api.csrfToken();
          form.append(token); document.body.append(form); form.submit(); return;
        }
        window.location.assign(`/b/${encodeURIComponent(slug)}/book/confirmed/${booking.id}`);
      } catch (error) { showFailure(error); button.disabled = false; button.removeAttribute("aria-busy"); }
    });
  }

  async function loadBooking(id) {
    const payload = await get(`/api/me/bookings/${encodeURIComponent(id)}`, true);
    currentBooking = payload;
    business = { name: payload.business_name, slug: payload.business_slug, timezone: payload.business_timezone };
    const serviceLine = `${payload.service_name} · ${payload.service_duration_min} minutes`;
    return { ...payload, serviceLine, when: dateTime(payload.start_at) };
  }

  function bookingDetail(node, booking) {
    node.replaceChildren();
    const lines = [booking.business_name, booking.serviceLine, booking.staff_name, booking.when, `Status: ${booking.status.replaceAll("_", " ")}`, `Total ${money(booking.price_cents)}${booking.deposit_cents ? ` · deposit ${money(booking.deposit_cents)}` : ""}`];
    lines.forEach((text) => { const p = document.createElement("p"); p.textContent = text; node.append(p); });
  }

  async function initConfirmed() {
    const booking = await loadBooking(bookingId);
    root.querySelector("[data-confirmed-title]").textContent = booking.status === "pending" ? "Your payment is pending." : "Your booking is confirmed.";
    root.querySelector("[data-confirmed-copy]").textContent = booking.status === "pending" ? "We’ll update this page after the payment provider confirms your deposit." : "We’ve saved your appointment.";
    bookingDetail(root.querySelector("[data-confirmed-summary]"), booking);
  }

  async function initRescheduled() {
    const booking = await loadBooking(bookingId);
    bookingDetail(root.querySelector("[data-rescheduled-summary]"), booking);
    root.querySelector("[data-rescheduled-detail]").href = `/account/bookings/${booking.id}`;
  }

  async function initCancelled() {
    const booking = await loadBooking(bookingId);
    bookingDetail(root.querySelector("[data-cancelled-summary]"), booking);
  }

  async function initBookings(filter = "upcoming") {
    const rows = await get(`/api/me/bookings?filter=${filter}`, true);
    const list = root.querySelector("[data-booking-list]");
    list.replaceChildren();
    root.querySelectorAll("[data-booking-filter]").forEach((tab) => {
      const active = tab.dataset.bookingFilter === filter;
      tab.setAttribute("aria-selected", String(active)); tab.classList.toggle("is-active", active);
    });
    root.querySelector("[data-bookings-empty]").hidden = rows.length > 0;
    rows.forEach((booking) => {
      const link = document.createElement("a"); link.className = "booking-row"; link.href = `/account/bookings/${booking.id}`;
      const content = document.createElement("span"); const heading = document.createElement("strong");
      heading.textContent = `${booking.business_name} · ${booking.service_name}`;
      const sub = document.createElement("p");
      sub.textContent = `${booking.business_name} · ${booking.service_name} · ${dateTime(booking.start_at, booking.business_timezone)} · ${booking.status.replaceAll("_", " ")}`;
      content.append(heading, sub); const badge = document.createElement("span"); badge.className = `status-badge status-badge--${booking.status === "confirmed" ? "confirmed" : booking.status === "pending" ? "pending" : "neutral"}`; badge.textContent = booking.status.replaceAll("_", " ");
      link.append(content, badge); list.append(link);
    });
    setState(rows.length ? "Bookings loaded." : "No bookings in this list.", rows.length ? "success" : "info");
  }

  async function initDetail() {
    const booking = await loadBooking(bookingId); bookingDetail(root.querySelector("[data-booking-detail]"), booking);
    root.querySelector("[data-reschedule-link]").href = `/account/bookings/${booking.id}/reschedule`;
    root.querySelector("[data-cancel-link]").href = `/account/bookings/${booking.id}/cancel`;
  }

  async function initCancel() {
    const booking = await loadBooking(bookingId); bookingDetail(root.querySelector("[data-cancel-summary]"), booking);
    root.querySelector("[data-cancel-submit]").addEventListener("click", async (event) => {
      const button = event.currentTarget; button.disabled = true;
      try { await api.patch(`/api/bookings/${bookingId}`, { action: "cancel" }, { signedIn: true }); window.location.assign(`/account/bookings/${bookingId}/cancelled`); }
      catch (error) { button.disabled = false; showFailure(error); }
    });
  }

  async function initReschedule() {
    const booking = await loadBooking(bookingId);
    const dateInput = root.querySelector("[data-reschedule-date]"); dateInput.min = businessDate(); dateInput.value = businessDate();
    const slotsNode = root.querySelector("[data-reschedule-slots]"); const confirm = root.querySelector("[data-reschedule-submit]");
    async function refresh() {
      const day = dateInput.value;
      const response = await get(`/api/b/${encodeURIComponent(booking.business_slug)}/slots?service=${booking.service_id}&staff=${booking.staff_id}&date=${day}`);
      renderSlots(slotsNode, response.slots || [], (slot) => { selectedSlot = slot; confirm.disabled = false; });
    }
    dateInput.addEventListener("change", () => refresh().catch(showFailure));
    confirm.addEventListener("click", async () => {
      if (!selectedSlot) return;
      confirm.disabled = true;
      try { await api.patch(`/api/bookings/${bookingId}`, { action: "reschedule", start_at: selectedSlot.start_at, staff_id: booking.staff_id }, { signedIn: true }); window.location.assign(`/account/bookings/${bookingId}/rescheduled`); }
      catch (error) { confirm.disabled = false; showFailure(error); }
    });
    await refresh();
  }

  async function initPaymentReturn() {
    if (!bookingId) throw new Error("The booking reference is missing from the payment return.");
    const status = root.querySelector("[data-payment-status]");
    let tries = 0;
    async function poll() {
      const booking = await get(`/api/me/bookings/${encodeURIComponent(bookingId)}`, true);
      business = { timezone: booking.business_timezone, name: booking.business_name };
      const paid = booking.payment_status === "paid" && booking.status === "confirmed";
      status.textContent = paid ? "Payment confirmed. Your booking is confirmed." : booking.payment_status === "failed" ? "The payment was not completed. Your booking hold may expire." : "Payment is still being confirmed. This page will not confirm a booking until the server receives the payment notification.";
      if (paid) { setState("Payment received.", "success"); return; }
      tries += 1;
      if (tries < 6) window.setTimeout(poll, 3000);
    }
    await poll();
  }

  root.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-booking-filter]");
    if (tab) initBookings(tab.dataset.bookingFilter).catch(showFailure);
  });

  async function init() {
    setState("Loading…");
    try {
      // /api/config intentionally uses a top-level shape rather than the
      // authenticated API's {data: ...} envelope.
      const configResponse = await fetch("/api/config", { credentials: "same-origin" });
      if (!configResponse.ok) throw new Error("Demo configuration is temporarily unavailable.");
      const config = await configResponse.json();
      const banner = root.querySelector("[data-demo-banner]");
      if (banner) banner.hidden = !config.demo_mode;
      if (["landing", "services", "time", "review"].includes(view)) await loadBusiness();
      if (view === "landing") await loadNextSlot();
      else if (view === "services") await initServices();
      else if (view === "time") await initTime();
      else if (view === "review") await initReview();
      else if (view === "confirmed") await initConfirmed();
      else if (view === "rescheduled") await initRescheduled();
      else if (view === "cancelled") await initCancelled();
      else if (view === "bookings") await initBookings(params.get("filter") || "upcoming");
      else if (view === "detail") await initDetail();
      else if (view === "cancel") await initCancel();
      else if (view === "reschedule") await initReschedule();
      else if (view === "payment_return") await initPaymentReturn();
      setState("", "success");
    } catch (error) { showFailure(error); }
  }

  init();
})();
