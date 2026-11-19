(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", () => {
    if (window.BookingApi) document.querySelectorAll("form[data-auth-form]").forEach(window.BookingApi.bindForm);
  });
})();
