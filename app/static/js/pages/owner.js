(function () {
  "use strict";
  const root = document.querySelector("[data-owner-page]");
  if (!root || !window.BookingApi) return;
  const content = root.querySelector("[data-owner-content]");
  const notice = root.querySelector("[data-owner-notice]");
  const dialog = root.querySelector("[data-owner-dialog]");
  const section = root.dataset.section;
  let businessId = Number(root.dataset.businessId) || 0;
  let business = null;
  let membership = null;
  let staffRows = [];
  let serviceRows = [];
  const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const nav = ["dashboard", "week", "bookings", "services", "staff", "hours", "customers", "payments", "analytics", "settings", "audit"];
  const labels = { dashboard: "Overview", week: "Week view", bookings: "Bookings", services: "Services", staff: "Staff", hours: "Working hours", customers: "Customers", payments: "Payments", analytics: "Analytics", settings: "Settings", audit: "Audit log", onboarding: "Setup" };
  const money = (cents) => new Intl.NumberFormat(undefined, { style: "currency", currency: "ZAR", maximumFractionDigits: 0 }).format((Number(cents) || 0) / 100);
  const formatDateTime = (value) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: business?.timezone || "UTC" }).format(new Date(value));
  const formatTime = (value) => new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", timeZone: business?.timezone || "UTC" }).format(new Date(value));
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  const dateString = (date) => date.toISOString().slice(0, 10);
  const today = () => {
    const parts = new Intl.DateTimeFormat("en", { timeZone: business?.timezone || "Africa/Johannesburg", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
    const part = (type) => parts.find((item) => item.type === type)?.value;
    return `${part("year")}-${part("month")}-${part("day")}`;
  };
  function businessMidnight(day) {
    const target = new Date(`${day}T00:00:00Z`);
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: business?.timezone || "UTC", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).formatToParts(target);
    const value = (type) => Number(parts.find((part) => part.type === type)?.value);
    const represented = Date.UTC(value("year"), value("month") - 1, value("day"), value("hour"), value("minute"), value("second"));
    return new Date(target.getTime() - (represented - target.getTime()));
  }
  function businessEndOfDay(day) {
    const next = new Date(`${day}T00:00:00Z`); next.setUTCDate(next.getUTCDate() + 1);
    return new Date(businessMidnight(dateString(next)).getTime() - 1);
  }
  const isoRange = () => {
    const end = new Date(); const start = new Date(); start.setDate(start.getDate() - 29);
    return { from: dateString(start), to: dateString(end) };
  };
  const api = window.BookingApi;
  async function get(path) { return (await api.get(path, { signedIn: true })).data; }
  async function post(path, body) { return (await api.post(path, body, { signedIn: true })).data; }
  async function patch(path, body) { return (await api.patch(path, body, { signedIn: true })).data; }
  async function put(path, body) {
    const response = await fetch(path, { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": api.csrfToken() }, body: JSON.stringify(body) });
    const result = await response.json(); if (!response.ok) throw Object.assign(new Error(result?.error?.message || "Request failed"), { status: response.status }); return result.data;
  }
  async function del(path) {
    const response = await fetch(path, { method: "DELETE", credentials: "same-origin", headers: { "X-CSRF-Token": api.csrfToken() } });
    const result = await response.json().catch(() => ({})); if (!response.ok) throw Object.assign(new Error(result?.error?.message || "Request failed"), { status: response.status }); return result.data;
  }
  function url(path) { return `/api/admin/businesses/${businessId}${path}`; }
  function showError(error) {
    if (error.status === 401) { window.dispatchEvent(new CustomEvent("session:expired")); return; }
    notice.hidden = false; notice.textContent = error instanceof TypeError ? "You appear to be offline. Reconnect and try again." : error.message || "Something went wrong. Try again.";
    notice.classList.toggle("owner-error", true);
  }
  function setPage(title, subtitle, actions = "") {
    root.querySelector("[data-section-label]").textContent = title;
    content.innerHTML = `<div class="owner-page-heading"><div><h1>${esc(title)}</h1><p>${esc(subtitle || business?.name || "")}</p></div><div class="owner-actions">${actions}</div></div><div data-page-body></div>`;
    return content.querySelector("[data-page-body]");
  }
  function card(label, value, delta, values) {
    const chart = values ? window.BookingCharts.sparkline(values, `${label} trend`) : null;
    return `<article class="owner-card"><div class="owner-card__label">${esc(label)}</div><div class="owner-card__value"><span>${esc(value)}</span>${chart ? `<span class="owner-sparkline"></span>` : ""}</div><span class="owner-card__delta">${esc(delta || "Current period")}</span></article>`;
  }
  function table(headers, rows) {
    return `<div class="owner-table-wrap"><table class="owner-table"><thead><tr>${headers.map((header) => `<th scope="col">${esc(header)}</th>`).join("")}</tr></thead><tbody>${rows.length ? rows.join("") : `<tr><td colspan="${headers.length}"><div class="owner-empty">No records yet</div></td></tr>`}</tbody></table></div>`;
  }
  function status(value) { return `<span class="owner-badge owner-badge--${esc(value)}">${esc(String(value || "unknown").replaceAll("_", " "))}</span>`; }
  function openDialog(html) {
    root.querySelector("[data-owner-dialog-content]").innerHTML = html;
    dialog.showModal();
  }
  function bookingActions(item) {
    const choices = item.status === "pending" ? [["confirm", "Confirm"]] : item.status === "confirmed" ? [["complete", "Complete"], ["no_show", "Mark no-show"]] : [];
    return `<div class="owner-actions">${choices.map(([action, label]) => `<button type="button" class="button button--secondary" data-booking-action="${action}" data-booking-id="${item.id}">${label}</button>`).join("")}</div>`;
  }
  async function loadOverview() {
    const body = setPage("Overview", `${business?.name || "Business"} · ${new Date().toLocaleDateString(undefined, { dateStyle: "full" })}`, '<button class="button button--secondary" type="button" data-add-service>Create service</button>');
    const { from, to } = isoRange(); const range = `?from=${from}&to=${to}`;
    try {
      const [summary, bookings, revenue, mix, utilisation, calendar] = await Promise.all([
        get(`${url("/analytics/summary")}${range}`), get(`${url("/analytics/timeseries")}${range}&metric=bookings&interval=day`),
        get(`${url("/analytics/timeseries")}${range}&metric=revenue&interval=day`), get(`${url("/analytics/status-mix")}${range}`),
        get(`${url("/analytics/utilisation")}${range}`), get(`${url("/calendar")}?date=${today()}`),
      ]);
      const current = summary.current || {};
      body.innerHTML = `<div class="owner-grid owner-grid--4">${card("Bookings", current.bookings || 0, `fill ${current.fill_rate_percent || 0}%`, bookings.map((item) => item.bookings))}${card("Revenue", money(current.revenue_cents), `${summary.change_percent?.revenue_cents ?? "—"}% vs prior period`, revenue.map((item) => item.revenue))}${card("Deposits collected", money(current.deposits_collected_cents), "Paid deposits")}${card("No-show rate", `${current.no_show_rate_percent || 0}%`, `${current.cancellation_rate_percent || 0}% cancellations`)}</div><h2 class="owner-section-title">Today’s timeline</h2><div data-timeline></div><div class="owner-grid owner-grid--2"><section class="owner-panel"><h2>Revenue · 30 days</h2><div data-area-chart></div></section><section class="owner-panel"><h2>Booking status</h2><div class="owner-inline"><div data-donut></div><ul data-status-legend></ul></div></section></div><h2 class="owner-section-title">Team utilisation</h2><div class="owner-grid owner-grid--4" data-rings></div>`;
      body.querySelectorAll(".owner-sparkline").forEach((node, index) => node.append(window.BookingCharts.sparkline([bookings, revenue, bookings, revenue][index].map((item) => Number(item.bookings ?? item.revenue)), "Recent trend")));
      body.querySelector("[data-area-chart]").append(window.BookingCharts.area(revenue.map((item) => ({ value: item.revenue })), "Revenue over the past thirty days"));
      body.querySelector("[data-donut]").append(window.BookingCharts.donut(mix.map((item) => ({ value: item.count })), "Booking status distribution"));
      body.querySelector("[data-status-legend]").innerHTML = mix.map((item) => `<li>${status(item.status)} ${item.count}</li>`).join("") || "<li class='owner-empty'>No bookings in this period</li>";
      body.querySelector("[data-rings]").innerHTML = utilisation.map((item) => `<article class="owner-card"><h3>${esc(item.staff_name)}</h3><div data-ring="${item.utilisation_percent}" data-ring-label="${esc(item.staff_name)} utilisation"></div></article>`).join("") || "<div class='owner-empty'>No staff utilisation yet</div>";
      body.querySelectorAll("[data-ring]").forEach((node) => node.append(window.BookingCharts.ring(node.dataset.ring, node.dataset.ringLabel)));
      renderTimeline(body.querySelector("[data-timeline]"), calendar);
    } catch (error) { body.innerHTML = `<div class="owner-empty">Could not load dashboard data. <button type="button" class="owner-text-button" data-retry>Retry</button></div>`; showError(error); }
  }
  async function loadStaffOverview() {
    const body = setPage("My calendar", `${business?.name || "Business"} · Your appointments`);
    try { const calendar = await get(`${url("/calendar")}?date=${today()}`); renderTimeline(body, calendar); }
    catch (error) { showError(error); }
  }
  function renderTimeline(target, data) {
    const staff = data.staff || [];
    if (!staff.length) { target.innerHTML = `<div class="owner-empty">No staff or bookings to show today.</div>`; return; }
    const hours = Array.from({ length: 12 }, (_, index) => `${String(index + 7).padStart(2, "0")}:00`);
    target.innerHTML = `<div class="owner-timeline"><div class="owner-timeline-row"><div class="owner-timeline-cell"></div>${staff.map((member) => `<div class="owner-timeline-cell"><strong>${esc(member.display_name)}</strong></div>`).join("")}</div>${hours.map((hour) => `<div class="owner-timeline-row" data-hour="${hour.slice(0, 2)}"><div class="owner-timeline-cell">${hour}</div>${staff.map((member) => `<div class="owner-timeline-cell">${(member.bookings || []).filter((item) => Number(new Intl.DateTimeFormat("en", { timeZone: data.timezone, hour: "2-digit", hourCycle: "h23" }).format(new Date(item.start_at))) === Number(hour.slice(0, 2))).map((item) => `<button type="button" class="owner-booking-block owner-booking-block--${esc(item.status)}" data-open-booking="${item.id}"><strong>${esc(item.service)}</strong><span>${esc(item.customer_name)} · ${esc(formatTime(item.start_at))}</span>${status(item.status)}</button>`).join("")}</div>`).join("")}</div>`).join("")}</div>`;
    target.querySelectorAll(".owner-timeline-row").forEach((row) => row.style.setProperty("grid-template-columns", `92px repeat(${staff.length}, minmax(180px, 1fr))`));
    const nowParts = new Intl.DateTimeFormat("en", { timeZone: data.timezone, hour: "2-digit", hourCycle: "h23" }).formatToParts(new Date());
    const nowHour = Number(nowParts.find((part) => part.type === "hour")?.value);
    const dateInZone = new Intl.DateTimeFormat("en-CA", { timeZone: data.timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
    if (dateInZone === data.date) target.querySelector(`[data-hour="${String(nowHour).padStart(2, "0")}"]`)?.classList.add("owner-now-line");
  }
  async function loadWeek() {
    const body = setPage("Week view", "Seven days across your team", '<button class="button button--secondary" type="button" data-week-prev>Previous week</button><button class="button button--secondary" type="button" data-week-next>Next week</button>');
    const requested = new URLSearchParams(window.location.search).get("start");
    const start = requested && !Number.isNaN(Date.parse(requested)) ? new Date(`${requested}T00:00:00Z`) : new Date(`${today()}T00:00:00Z`);
    if (!requested) start.setUTCDate(start.getUTCDate() - ((start.getUTCDay() + 6) % 7));
    try {
      const data = await get(`${url("/calendar/week")}?start=${dateString(start)}`);
      const cells = [];
      (data.staff || []).forEach((staff) => staff.days.forEach((day) => cells.push({ value: day.bookings, label: `${staff.staff_name} ${day.date}` })));
      body.innerHTML = `<section class="owner-panel"><h2>Bookings by staff and day</h2><div data-heatmap></div><p class="field__help">Five flat activity steps. ${esc(data.start)} to ${esc(data.end)} · ${esc(data.timezone)}</p></section><div class="owner-grid owner-grid--2" data-week-summary></div>`;
      body.querySelector("[data-heatmap]").append(window.BookingCharts.heatmap(cells, "Seven day booking density by staff"));
      body.querySelector("[data-week-summary]").innerHTML = (data.staff || []).map((person) => `<section class="owner-panel"><h2>${esc(person.staff_name)}</h2>${table(["Date", "Bookings", "Open slots"], person.days.map((day) => `<tr><td>${esc(day.date)}</td><td>${day.bookings}</td><td>${day.open_slots}</td></tr>`))}</section>`).join("") || `<div class="owner-empty">No staff schedules available.</div>`;
    } catch (error) { showError(error); }
  }
  async function loadBookings() {
    const body = setPage("Bookings", "Appointments and status actions");
    body.innerHTML = `<label class="owner-field">Date<input type="date" data-booking-date value="${today()}"></label><div data-booking-list></div>`;
    async function refresh() {
      try {
        const date = body.querySelector("[data-booking-date]").value;
        const start = businessMidnight(date).toISOString(); const end = businessEndOfDay(date).toISOString();
        const rows = await get(`/api/admin/businesses/${businessId}/bookings?from=${encodeURIComponent(start)}&to=${encodeURIComponent(end)}`);
        body.querySelector("[data-booking-list]").innerHTML = table(["Time", "Customer", "Service", "Staff", "Status", "Actions"], rows.map((item) => `<tr><td>${esc(formatDateTime(item.start_at))}</td><td>${esc(item.customer_name || `Customer ${item.customer_id}`)}</td><td>${esc(item.service_name || `Service ${item.service_id}`)}</td><td>${esc(item.staff_name || `Staff ${item.staff_id}`)}</td><td>${status(item.status)}</td><td>${bookingActions(item)} <button type="button" class="owner-text-button" data-open-booking="${item.id}">Details</button></td></tr>`));
      } catch (error) { showError(error); }
    }
    body.addEventListener("change", (event) => { if (event.target.matches("[data-booking-date]")) refresh(); }); await refresh();
  }
  async function loadServices() {
    const body = setPage("Services", "Manage what customers can book", '<button class="button button--primary" type="button" data-service-new>Create service</button>');
    try {
      [serviceRows, staffRows] = await Promise.all([get(url("/services")), get(url("/staff"))]);
      body.innerHTML = table(["Service", "Duration", "Price", "Deposit", "Assigned team", "Status", ""], serviceRows.map((item) => `<tr><td>${esc(item.name)}<small>${esc(item.description || "")}</small></td><td>${item.duration_min} min</td><td>${money(item.price_cents)}</td><td>${money(item.deposit_cents)}</td><td>${staffRows.filter((member) => member.service_ids?.includes(item.id)).map((member) => esc(member.display_name)).join(", ") || "—"}</td><td>${status(item.active ? "bookable" : "inactive")}</td><td><button type="button" class="owner-text-button" data-service-edit="${item.id}">Edit</button> ${item.active ? `<button type="button" class="owner-text-button" data-service-deactivate="${item.id}">Deactivate</button>` : ""}</td></tr>`));
    } catch (error) { showError(error); }
  }
  async function serviceForm(item = {}) {
    if (!staffRows.length) staffRows = await get(url("/staff"));
    openDialog(`<h2 id="owner-dialog-title">${item.id ? "Edit service" : "Create service"}</h2><form class="owner-form" data-service-form><label>Name<input name="name" required maxlength="120" value="${esc(item.name)}"></label><label>Description<textarea name="description">${esc(item.description)}</textarea></label><label>Duration (minutes)<input name="duration_min" type="number" min="1" required value="${item.duration_min || 30}"></label><label>Buffer (minutes)<input name="buffer_min" type="number" min="0" value="${item.buffer_min || 0}"></label><label>Price (ZAR)<input name="price" type="number" min="0" step="0.01" required value="${(item.price_cents || 0) / 100}"></label><label>Deposit (ZAR)<input name="deposit" type="number" min="0" step="0.01" value="${(item.deposit_cents || 0) / 100}"></label><fieldset><legend>Available staff</legend>${staffRows.map((member) => `<label><input type="checkbox" name="staff_ids" value="${member.id}" ${member.service_ids?.includes(item.id) ? "checked" : ""}> ${esc(member.display_name)}</label>`).join("") || "<p class='owner-empty'>Add staff before assigning services.</p>"}</fieldset><button class="button button--primary" type="submit">Save service</button></form>`);
    dialog.querySelector("[data-service-form]").addEventListener("submit", async (event) => {
      event.preventDefault(); const form = new FormData(event.currentTarget); const data = { name: form.get("name"), description: form.get("description") || null, duration_min: Number(form.get("duration_min")), buffer_min: Number(form.get("buffer_min")), price_cents: Math.round(Number(form.get("price")) * 100), deposit_cents: Math.round(Number(form.get("deposit")) * 100) };
      try {
        const serviceRow = item.id ? await patch(url(`/services/${item.id}`), data) : await post(url("/services"), data);
        const selected = new Set(Array.from(event.currentTarget.querySelectorAll("[name='staff_ids']:checked"), (input) => Number(input.value)));
        await Promise.all(staffRows.map((member) => {
          const wasAssigned = member.service_ids?.includes(serviceRow.id) || false;
          if (selected.has(member.id) && !wasAssigned) return post(url(`/staff/${member.id}/services/${serviceRow.id}`), {});
          if (!selected.has(member.id) && wasAssigned) return del(url(`/staff/${member.id}/services/${serviceRow.id}`));
          return Promise.resolve();
        }));
        dialog.close(); await loadServices();
      } catch (error) { showError(error); }
    });
  }
  async function loadStaff() {
    const body = setPage("Staff", "People, service assignments, and schedules", '<button class="button button--primary" type="button" data-staff-new>Add staff member</button>');
    try { staffRows = await get(url("/staff")); serviceRows = await get(url("/services"));
      body.innerHTML = table(["Team member", "Assigned services", "Status", ""], staffRows.map((item) => `<tr><td>${esc(item.display_name)}</td><td>${serviceRows.map((service) => `<label><input type="checkbox" data-assignment-staff="${item.id}" data-assignment-service="${service.id}" ${item.service_ids?.includes(service.id) ? "checked" : ""}> ${esc(service.name)}</label>`).join("<br>")}</td><td>${status(item.active ? "active" : "inactive")}</td><td><button type="button" class="owner-text-button" data-staff-edit="${item.id}">Edit</button> ${item.active ? `<button type="button" class="owner-text-button" data-staff-deactivate="${item.id}">Deactivate</button>` : ""}</td></tr>`));
    } catch (error) { showError(error); }
  }
  function staffForm(item = {}) {
    openDialog(`<h2 id="owner-dialog-title">${item.id ? "Edit staff member" : "Add staff member"}</h2><form class="owner-form" data-staff-form><label>Display name<input name="display_name" required maxlength="120" value="${esc(item.display_name)}"></label><label>Linked user ID (optional)<input name="user_id" type="number" min="1" value="${esc(item.user_id)}"></label><button class="button button--primary" type="submit">Save staff member</button></form>`);
    dialog.querySelector("[data-staff-form]").addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); const id = Number(form.get("user_id")); const data = { display_name: form.get("display_name"), user_id: id || null }; try { if (item.id) await patch(url(`/staff/${item.id}`), data); else await post(url("/staff"), data); dialog.close(); await loadStaff(); } catch (error) { showError(error); } });
  }
  async function loadHours() {
    const body = setPage("Working hours", "Weekly availability and time off");
    try {
      staffRows = await get(url("/staff"));
      body.innerHTML = staffRows.map((member) => `<section class="owner-panel" data-hours-staff="${member.id}"><h2>${esc(member.display_name)}</h2><form class="owner-form" data-hours-form="${member.id}"><div class="owner-hours-grid">${days.map((day, index) => `<div class="owner-day-row"><strong>${day}</strong><label class="owner-field">From<input type="time" data-weekday="${index}" data-edge="start"></label><label class="owner-field">To<input type="time" data-weekday="${index}" data-edge="end"></label><label><input type="checkbox" data-weekday="${index}" data-open> Open</label></div>`).join("")}</div><button class="button button--primary" type="submit">Save weekly hours</button></form><h3>Time off</h3><div data-timeoff-list>Loading…</div><form class="owner-inline" data-timeoff-form="${member.id}"><label class="owner-field">From<input type="datetime-local" name="start_at" required></label><label class="owner-field">To<input type="datetime-local" name="end_at" required></label><label class="owner-field">Reason<input name="reason" maxlength="200"></label><button class="button button--secondary" type="submit">Add time off</button></form></section>`).join("") || `<div class="owner-empty">Add staff members before editing working hours.</div>`;
      for (const member of staffRows) {
        const panel = body.querySelector(`[data-hours-staff="${member.id}"]`); const result = await get(url(`/staff/${member.id}/working-hours`));
        (result.hours || result || []).forEach((row) => { const index = Number(row.weekday); const checkbox = panel.querySelector(`[data-weekday="${index}"][data-open]`); checkbox.checked = true; panel.querySelector(`[data-weekday="${index}"][data-edge="start"]`).value = row.start_time; panel.querySelector(`[data-weekday="${index}"][data-edge="end"]`).value = row.end_time; });
        const timeoff = await get(url(`/staff/${member.id}/time-off`)); panel.querySelector("[data-timeoff-list]").innerHTML = (timeoff || []).map((item) => `<p>${esc(formatDateTime(item.start_at))} — ${esc(formatDateTime(item.end_at))} · ${esc(item.reason || "Time off")} <button type="button" class="owner-text-button" data-timeoff-delete="${item.id}" data-staff-id="${member.id}">Remove</button></p>`).join("") || `<p class="owner-empty">No time off recorded.</p>`;
      }
    } catch (error) { showError(error); }
  }
  async function loadCustomers() {
    const body = setPage("Customers", "Search customer history for this business", '<label class="owner-field">Search<input type="search" data-customer-search placeholder="Name or email"></label>');
    async function refresh() { try { const q = body.querySelector("[data-customer-search]").value; const rows = await get(url(`/customers?search=${encodeURIComponent(q)}&sort=name`)); body.querySelector("[data-customer-table]")?.remove(); body.insertAdjacentHTML("beforeend", `<div data-customer-table>${table(["Customer", "Bookings", "No-shows", "Last visit", ""], rows.map((item) => `<tr><td>${esc(item.name)}<small>${esc(item.email)}</small></td><td>${item.booking_count}</td><td>${item.no_show_count}</td><td>${item.last_visit ? esc(formatDateTime(item.last_visit)) : "—"}</td><td><button type="button" class="owner-text-button" data-customer-detail="${item.id}">History</button></td></tr>`))}</div>`); } catch (error) { showError(error); } }
    body.innerHTML = `<div class="owner-filter-row"><label class="owner-field">Search<input type="search" data-customer-search placeholder="Name or email"></label></div><div data-customer-table></div>`;
    let timer; body.querySelector("[data-customer-search]").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(refresh, 250); }); await refresh();
  }
  async function loadPayments() {
    const body = setPage("Payments", "Deposit transactions and reconciliation");
    body.innerHTML = `<label class="owner-field">Status<select data-payment-status><option value="">All statuses</option><option>pending</option><option>paid</option><option>failed</option><option>refunded</option></select></label><section class="owner-panel"><h2>Completed revenue · 30 days</h2><div data-payments-chart></div></section><div data-payment-table></div>`;
    try { const range = isoRange(); const revenue = await get(`${url("/analytics/timeseries")}?from=${range.from}&to=${range.to}&metric=revenue&interval=day`); body.querySelector("[data-payments-chart]").append(window.BookingCharts.area(revenue.map((item) => ({ value: item.revenue })), "Completed revenue for the last thirty days"));
      async function refresh() { const state = body.querySelector("[data-payment-status]").value; const filter = `from=${range.from}&to=${range.to}${state ? `&status=${state}` : ""}`; const rows = await get(url(`/payments?${filter}&limit=100`)); const bookingRows = await get(`/api/admin/businesses/${businessId}/bookings?from=${encodeURIComponent(businessMidnight(range.from).toISOString())}&to=${encodeURIComponent(businessEndOfDay(range.to).toISOString())}&limit=100`); const bookingMap = new Map(bookingRows.map((item) => [item.id, item])); body.querySelector("[data-payment-table]").innerHTML = table(["Date", "Booking", "Provider", "Reference", "Amount", "Status", "Review"], rows.map((item) => { const booking = bookingMap.get(item.booking_id); const flag = item.status === "paid" && booking?.status === "cancelled"; return `<tr><td>${esc(formatDateTime(item.created_at))}</td><td>#${item.booking_id}${booking ? ` · ${esc(booking.status)}` : ""}</td><td>${esc(item.provider)}</td><td>${esc(item.provider_ref)}</td><td>${money(item.amount_cents)}</td><td>${status(item.status)}</td><td>${flag ? `<strong class="owner-error">Paid after cancellation — review refund</strong>` : "—"}</td></tr>`; })); }
      body.querySelector("[data-payment-status]").addEventListener("change", () => refresh().catch(showError)); await refresh();
    } catch (error) { showError(error); }
  }
  async function loadAnalytics() {
    const body = setPage("Analytics", "Outcomes, utilisation, and revenue");
    const range = isoRange();
    body.innerHTML = `<div class="owner-filter-row"><label class="owner-field">Start<input type="date" data-range-from value="${range.from}"></label><label class="owner-field">End<input type="date" data-range-to value="${range.to}"></label><button class="button button--secondary" type="button" data-analytics-refresh>Apply range</button></div><div class="owner-grid owner-grid--4" data-analytics-kpis></div><div class="owner-grid owner-grid--2"><section class="owner-panel"><h2>Bookings</h2><div data-booking-chart></div></section><section class="owner-panel"><h2>Revenue</h2><div data-revenue-chart></div></section><section class="owner-panel"><h2>Booking outcomes</h2><div data-outcomes></div></section><section class="owner-panel"><h2>Status mix</h2><div data-status-chart></div></section><section class="owner-panel"><h2>Weekly density</h2><div data-analytics-heatmap></div></section><section class="owner-panel"><h2>Team utilisation</h2><div data-analytics-utilisation></div></section></div>`;
    async function refresh() { try { const from = body.querySelector("[data-range-from]").value; const to = body.querySelector("[data-range-to]").value; const q = `?from=${from}&to=${to}`; const [summary, bookings, revenue, outcomes, mix, heatmap, utilisation] = await Promise.all([get(`${url("/analytics/summary")}${q}`), get(`${url("/analytics/timeseries")}${q}&metric=bookings&interval=day`), get(`${url("/analytics/timeseries")}${q}&metric=revenue&interval=day`), get(`${url("/analytics/outcomes")}${q}`), get(`${url("/analytics/status-mix")}${q}`), get(`${url("/analytics/heatmap")}${q}`), get(`${url("/analytics/utilisation")}${q}`)]); const current = summary.current || {}; const previous = summary.previous || {}; body.querySelector("[data-analytics-kpis]").innerHTML = card("Bookings", current.bookings || 0, `Previous period: ${previous.bookings || 0}`) + card("Completed revenue", money(current.revenue_cents), `Previous: ${money(previous.revenue_cents)}`) + card("Fill rate", `${current.fill_rate_percent || 0}%`, `${summary.change_percent?.fill_rate_percent ?? "—"}% vs previous`) + card("Deposits collected", money(current.deposits_collected_cents), "Successful deposits"); body.querySelector("[data-booking-chart]").replaceChildren(window.BookingCharts.area(bookings.map((item) => ({ value: item.bookings })), "Bookings across selected dates")); body.querySelector("[data-revenue-chart]").replaceChildren(window.BookingCharts.area(revenue.map((item) => ({ value: item.revenue })), "Revenue across selected dates")); body.querySelector("[data-outcomes]").innerHTML = Object.entries(outcomes).map(([key, value]) => `<p>${esc(key)}: <strong>${value}</strong></p>`).join(""); body.querySelector("[data-status-chart]").replaceChildren(window.BookingCharts.donut(mix.map((item) => ({ value: item.count })), "Booking status mix")); body.querySelector("[data-analytics-heatmap]").replaceChildren(window.BookingCharts.heatmap(heatmap.map((item) => ({ value: item.count, label: `Weekday ${item.weekday}, ${item.hour}:00` })), "Booking density by weekday and hour")); body.querySelector("[data-analytics-utilisation]").innerHTML = utilisation.map((item) => `<p>${esc(item.staff_name)} · ${item.booked_minutes} / ${item.available_minutes} minutes · ${item.utilisation_percent}%</p>`).join("") || `<div class="owner-empty">Not enough schedule data to calculate utilisation.</div>`; } catch (error) { showError(error); } }
    body.querySelector("[data-analytics-refresh]").addEventListener("click", refresh); await refresh();
  }
  async function loadSettings() {
    const body = setPage("Settings", "Business details, booking rules, and public link");
    try { business = await get(`/api/admin/businesses/${businessId}`); body.innerHTML = `<div class="owner-grid owner-grid--2"><section class="owner-panel"><h2>Business profile</h2><form class="owner-form" data-business-form><label>Business name<input name="name" required value="${esc(business.name)}"></label><label>Timezone<input name="timezone" required value="${esc(business.timezone)}"></label><label>Cancellation cutoff (hours)<input name="cancel_cutoff_hours" type="number" min="0" value="${business.cancel_cutoff_hours}"></label><label>Slot step (minutes)<input name="slot_step_min" type="number" min="1" value="${business.slot_step_min}"></label><button class="button button--primary" type="submit">Save settings</button></form></section><section class="owner-panel"><h2>Booking link</h2><p><a href="/b/${esc(business.slug)}">/b/${esc(business.slug)}</a></p><button class="button button--secondary" type="button" data-copy-link>Copy booking link</button><div class="owner-qr" data-qr aria-label="QR code for booking page"></div></section></div>`; const qr = await fetch(`/app/${businessId}/qr.svg`, { credentials: "same-origin" }); if (qr.ok) { const parser = new DOMParser(); const svg = parser.parseFromString(await qr.text(), "image/svg+xml").documentElement; body.querySelector("[data-qr]").replaceChildren(document.importNode(svg, true)); }
    } catch (error) { showError(error); }
  }
  async function loadAudit() {
    const body = setPage("Audit log", "Recent changes made in this business");
    try { const rows = await get(url("/audit-log?limit=100")); body.innerHTML = table(["When", "Actor", "Entity", "Action", "Changes"], rows.map((item) => `<tr><td>${esc(formatDateTime(item.created_at))}</td><td>${esc(item.actor_name || item.actor_id || "System")}</td><td>${esc(item.entity)} #${item.entity_id}</td><td>${esc(item.action)}</td><td><details><summary>View safe diff</summary><pre>${esc(JSON.stringify(item.diff || {}, null, 2))}</pre></details></td></tr>`)); } catch (error) { showError(error); }
  }
  async function onboarding() {
    root.querySelector("[data-section-label]").textContent = "Setup";
    content.innerHTML = `<div class="owner-page-heading"><div><h1>Let’s get your business ready</h1><p>Create a business, add a service, set hours and staff, then share your booking page.</p></div></div><nav class="owner-stepper" aria-label="Onboarding steps"><span class="owner-step" aria-current="step">1 · Business</span><span class="owner-step">2 · Service</span><span class="owner-step">3 · Hours and staff</span><span class="owner-step">4 · Share</span></nav><section class="owner-panel" data-onboarding-step></section>`;
    const stage = content.querySelector("[data-onboarding-step]"); const data = {};
    const show = (number, title, fields, button) => { content.querySelectorAll(".owner-step").forEach((item, index) => item.toggleAttribute("aria-current", index === number - 1)); stage.innerHTML = `<h2>${title}</h2><form class="owner-form" data-onboard-form>${fields}<button class="button button--primary" type="submit">${button}</button></form>`; };
    show(1, "Business profile", '<label>Business name<input name="name" required></label><label>Booking page slug<input name="slug" pattern="[a-z0-9-]{3,40}" minlength="3" maxlength="40" required></label><label>Timezone<input name="timezone" value="Africa/Johannesburg" required></label>', "Create business");
    stage.addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(event.target); try {
      if (!businessId) { const created = await post("/api/admin/businesses", { name: form.get("name"), slug: form.get("slug"), timezone: form.get("timezone") }); businessId = created.id; data.business = created; root.dataset.businessId = String(businessId); }
      if (content.querySelector("[aria-current='step']")?.textContent.startsWith("1")) { show(2, "First service", '<label>Service name<input name="service" required></label><label>Duration in minutes<input name="duration" type="number" min="1" value="30" required></label><label>Price in ZAR<input name="price" type="number" min="0" step="0.01" required></label>', "Add service"); return; }
      if (content.querySelector("[aria-current='step']")?.textContent.startsWith("2")) { const item = await post(`/api/admin/businesses/${businessId}/services`, { name: form.get("service"), duration_min: Number(form.get("duration")), buffer_min: 0, price_cents: Math.round(Number(form.get("price")) * 100), deposit_cents: 0 }); data.service = item; show(3, "Working hours and staff", '<label>Staff member name<input name="staff" required></label><label>First day opens<input name="start" type="time" value="09:00" required></label><label>First day closes<input name="end" type="time" value="17:00" required></label>', "Add staff and hours"); return; }
      if (content.querySelector("[aria-current='step']")?.textContent.startsWith("3")) { const member = await post(`/api/admin/businesses/${businessId}/staff`, { display_name: form.get("staff") }); data.staff = member; const start = form.get("start"), end = form.get("end"); await put(`/api/admin/businesses/${businessId}/staff/${member.id}/working-hours`, { hours: [0, 1, 2, 3, 4, 5].map((weekday) => ({ weekday, start_time: start, end_time: end })) }); await post(`/api/admin/businesses/${businessId}/staff/${member.id}/services/${data.service.id}`, {}); show(4, "Your booking page is ready", `<p>Share <a href="/b/${esc(data.business.slug)}">/b/${esc(data.business.slug)}</a> with your customers.</p>`, "Open workspace"); return; }
      window.location.assign(`/app/${businessId}/dashboard`);
    } catch (error) { showError(error); }
    });
  }
  async function showBooking(id) {
    try { const item = await get(`/api/admin/businesses/${businessId}/bookings?limit=100`); const booking = item.find((row) => row.id === Number(id)); if (!booking) throw new Error("Booking not found in this business."); openDialog(`<h2 id="owner-dialog-title">Booking #${booking.id}</h2><p>${esc(booking.customer_name || `Customer ${booking.customer_id}`)} · ${esc(booking.service_name || `Service ${booking.service_id}`)}</p><p>${esc(new Date(booking.start_at).toLocaleString())} · ${status(booking.status)}</p>${bookingActions(booking)}<p>Booking price: ${money(booking.price_cents)} · Deposit: ${money(booking.deposit_cents)}</p>`); } catch (error) { showError(error); }
  }
  async function affectedBookings(resource, id) {
    const from = new Date().toISOString(); const to = new Date(); to.setFullYear(to.getFullYear() + 1);
    let offset = 0; let count = 0; const limit = 100;
    while (true) {
      const rows = await get(`/api/admin/businesses/${businessId}/bookings?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to.toISOString())}&limit=${limit}&offset=${offset}`);
      count += rows.filter((item) => item.status === "confirmed" || item.status === "pending").filter((item) => item[`${resource}_id`] === id).length;
      if (rows.length < limit) return count;
      offset += limit;
    }
  }
  function route(sectionName) { window.location.assign(`/app/${businessId}/${sectionName}`); }
  async function start() {
    try {
      await api.init(); const me = await get("/api/auth/me"); const user = me.user; const memberships = user.memberships || [];
      membership = businessId ? memberships.find((item) => item.business_id === businessId) : memberships[0];
      if (!businessId && !membership && section !== "onboarding") { window.location.replace("/app/onboarding"); return; }
      if (!businessId && section === "onboarding" && memberships.length) { window.location.replace(`/app/${memberships[0].business_id}/dashboard`); return; }
      if (!businessId && membership) { window.location.replace(`/app/${membership.business_id}/dashboard`); return; }
      if (businessId && !membership) throw new Error("This business is not available to your account.");
      if (section === "onboarding") { onboarding(); return; }
      business = await get(`/api/admin/businesses/${businessId}`);
      root.querySelectorAll("[data-business-name]").forEach((node) => { node.textContent = business.name; node.href = `/app/${businessId}/dashboard`; });
      root.querySelector("[data-section-label]").textContent = labels[section] || "Overview";
      root.querySelectorAll("[data-nav-section]").forEach((node) => { node.href = `/app/${businessId}/${node.dataset.navSection}`; if (node.dataset.navSection === section) node.setAttribute("aria-current", "page"); if (membership.role === "staff" && !["dashboard", "week", "bookings"].includes(node.dataset.navSection)) node.hidden = true; });
      root.querySelector("[data-create-booking]").hidden = membership.role === "staff";
      if (membership.role === "staff" && !["dashboard", "week", "bookings"].includes(section)) throw new Error("This section is only available to business owners.");
      const loaders = { dashboard: membership.role === "staff" ? loadStaffOverview : loadOverview, week: loadWeek, bookings: loadBookings, services: loadServices, staff: loadStaff, hours: loadHours, customers: loadCustomers, payments: loadPayments, analytics: loadAnalytics, settings: loadSettings, audit: loadAudit };
      await (loaders[section] || loadOverview)();
    } catch (error) { showError(error); content.innerHTML = `<div class="owner-empty">${esc(error.message)} <p><a href="/auth/login?next=${encodeURIComponent(window.location.pathname)}">Sign in</a> or start <a href="/app/onboarding">business setup</a>.</p></div>`; }
  }
  root.addEventListener("click", async (event) => {
    const target = event.target.closest("button"); if (!target) return;
    try {
      if (target.matches("[data-signout]")) { await post("/api/auth/logout", {}); window.location.assign("/auth/login"); }
      else if (target.matches("[data-command-open]")) { root.querySelector("[data-owner-palette]").showModal(); root.querySelector("[data-command-input]").focus(); }
      else if (target.matches("[data-add-service], [data-service-new]")) serviceForm();
      else if (target.matches("[data-service-edit]")) serviceForm(serviceRows.find((item) => item.id === Number(target.dataset.serviceEdit)) || {});
      else if (target.matches("[data-service-deactivate]")) { const id = Number(target.dataset.serviceDeactivate); const item = serviceRows.find((service) => service.id === id); const affected = await affectedBookings("service", id); openDialog(`<h2 id="owner-dialog-title">Deactivate ${esc(item?.name)}</h2><p>${affected ? `${affected} pending or confirmed future booking(s) use this service. They remain on the calendar.` : "No pending or confirmed future bookings use this service."} Customers will no longer be able to book it.</p><button type="button" class="button button--primary" data-service-deactivate-confirm="${id}">Deactivate service</button>`); }
      else if (target.matches("[data-service-deactivate-confirm]")) { const result = await post(url(`/services/${target.dataset.serviceDeactivateConfirm}/deactivate`), {}); dialog.close(); if (result.affected_future_bookings) { notice.hidden = false; notice.textContent = `${result.affected_future_bookings} future booking(s) still reference this service.`; } await loadServices(); }
      else if (target.matches("[data-staff-new]")) staffForm();
      else if (target.matches("[data-staff-edit]")) staffForm(staffRows.find((item) => item.id === Number(target.dataset.staffEdit)) || {});
      else if (target.matches("[data-staff-deactivate]")) { const id = Number(target.dataset.staffDeactivate); const member = staffRows.find((row) => row.id === id); const affected = await affectedBookings("staff", id); openDialog(`<h2 id="owner-dialog-title">Deactivate ${esc(member?.display_name)}</h2><p>${affected ? `${affected} pending or confirmed future booking(s) use this staff member. They remain on the calendar.` : "No pending or confirmed future bookings use this staff member."}</p><button type="button" class="button button--primary" data-staff-deactivate-confirm="${id}">Deactivate staff</button>`); }
      else if (target.matches("[data-staff-deactivate-confirm]")) { const id = Number(target.dataset.staffDeactivateConfirm); const result = await post(url(`/staff/${id}/deactivate`), {}); dialog.close(); if (result.affected_future_bookings) { notice.hidden = false; notice.textContent = `${result.affected_future_bookings} future booking(s) still reference this staff member.`; } await loadStaff(); }
      else if (target.matches("[data-open-booking]")) await showBooking(target.dataset.openBooking);
      else if (target.matches("[data-customer-detail]")) { const person = await get(url(`/customers/${target.dataset.customerDetail}`)); openDialog(`<h2 id="owner-dialog-title">${esc(person.name)}’s history</h2><p>${esc(person.email)}</p>${table(["When", "Service", "Staff", "Status", "Amount"], (person.bookings || []).map((item) => `<tr><td>${esc(formatDateTime(item.start_at))}</td><td>${esc(item.service)}</td><td>${esc(item.staff)}</td><td>${status(item.status)}</td><td>${money(item.price_cents)}</td></tr>`))}`); }
      else if (target.matches("[data-booking-action]")) { await patch(`/api/bookings/${target.dataset.bookingId}`, { action: target.dataset.bookingAction }); dialog.open && dialog.close(); if (section === "bookings") await loadBookings(); else await loadOverview(); }
      else if (target.matches("[data-create-booking]")) openDialog(`<h2 id="owner-dialog-title">Walk-in booking</h2><p>Walk-in appointments are not supported yet. The current booking API requires a registered customer account, and changing that relationship would require a schema change.</p><a class="button button--secondary" href="/app/${businessId}/bookings">Open bookings</a>`);
      else if (target.matches("[data-timeoff-delete]")) { await del(url(`/staff/${target.dataset.staffId}/time-off/${target.dataset.timeoffDelete}`)); await loadHours(); }
      else if (target.matches("[data-retry]")) await loadOverview();
      else if (target.matches("[data-copy-link]")) await navigator.clipboard.writeText(`${window.location.origin}/b/${business.slug}`);
      else if (target.matches("[data-week-prev], [data-week-next]")) { const current = new URLSearchParams(window.location.search).get("start"); const d = current ? new Date(`${current}T00:00:00Z`) : new Date(`${today()}T00:00:00Z`); if (!current) d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7)); d.setUTCDate(d.getUTCDate() + (target.matches("[data-week-prev]") ? -7 : 7)); window.location.assign(`/app/${businessId}/week?start=${dateString(d)}`); }
    } catch (error) { showError(error); }
  });
  root.addEventListener("change", async (event) => {
    const target = event.target;
    try {
      if (target.matches("[data-assignment-staff]")) { const path = url(`/staff/${target.dataset.assignmentStaff}/services/${target.dataset.assignmentService}`); if (target.checked) await post(path, {}); else await del(path); }
    } catch (error) { target.checked = !target.checked; showError(error); }
  });
  root.addEventListener("submit", async (event) => {
    const form = event.target;
    if (form.matches("[data-hours-form]")) { event.preventDefault(); const staffId = form.dataset.hoursForm; const hours = days.flatMap((_, index) => { const open = form.querySelector(`[data-weekday="${index}"][data-open]`).checked; if (!open) return []; return [{ weekday: index, start_time: form.querySelector(`[data-weekday="${index}"][data-edge="start"]`).value, end_time: form.querySelector(`[data-weekday="${index}"][data-edge="end"]`).value }]; }); try { await put(url(`/staff/${staffId}/working-hours`), { hours }); notice.hidden = false; notice.textContent = "Weekly hours saved."; } catch (error) { showError(error); } }
    if (form.matches("[data-timeoff-form]")) { event.preventDefault(); const data = new FormData(form); const staffId = form.dataset.timeoffForm; try { await post(url(`/staff/${staffId}/time-off`), { start_at: new Date(data.get("start_at")).toISOString(), end_at: new Date(data.get("end_at")).toISOString(), reason: data.get("reason") }); await loadHours(); } catch (error) { showError(error); } }
    if (form.matches("[data-business-form]")) { event.preventDefault(); const data = new FormData(form); try { business = await patch(`/api/admin/businesses/${businessId}`, { name: data.get("name"), timezone: data.get("timezone"), cancel_cutoff_hours: Number(data.get("cancel_cutoff_hours")), slot_step_min: Number(data.get("slot_step_min")) }); notice.hidden = false; notice.textContent = "Business settings saved."; } catch (error) { showError(error); } }
  });
  root.querySelector("[data-command-input]").addEventListener("input", (event) => {
    const query = event.target.value.toLowerCase(); const results = nav.filter((item) => item.includes(query) || labels[item].toLowerCase().includes(query));
    root.querySelector("[data-command-results]").innerHTML = results.map((item) => `<button type="button" data-command-route="${item}">${esc(labels[item])}</button>`).join("") || `<p class="owner-empty">No matching pages.</p>`;
  });
  root.querySelector("[data-command-results]").addEventListener("click", (event) => { const button = event.target.closest("[data-command-route]"); if (button) route(button.dataset.commandRoute); });
  root.querySelector("[data-owner-palette]").addEventListener("keydown", (event) => { if (event.key === "Escape") event.currentTarget.close(); });
  start();
})();
