(function () {
  var guest = document.getElementById("nav-guest");
  var user = document.getElementById("nav-user");
  if (!guest || !user) return;

  var header = document.querySelector(".site-header");
  var nav = header && header.querySelector("nav");
  var menuButton;
  function updateMobileMenu(loggedIn) {
    if (!header || !nav) return;
    header.classList.toggle("mobile-nav-collapsible", loggedIn);
    if (!loggedIn) {
      header.classList.remove("nav-open");
      if (menuButton) {
        menuButton.classList.add("hidden");
        menuButton.setAttribute("aria-expanded", "false");
      }
      return;
    }
    if (!menuButton) {
      nav.id = nav.id || "site-navigation";
      menuButton = document.createElement("button");
      menuButton.type = "button";
      menuButton.className = "mobile-menu-toggle";
      menuButton.textContent = "Menü";
      menuButton.setAttribute("aria-controls", nav.id);
      menuButton.setAttribute("aria-expanded", "false");
      header.insertBefore(menuButton, nav);
      menuButton.addEventListener("click", function () {
        var open = header.classList.toggle("nav-open");
        menuButton.setAttribute("aria-expanded", String(open));
        menuButton.textContent = open ? "Schließen" : "Menü";
      });
      header.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && header.classList.contains("nav-open")) {
          header.classList.remove("nav-open");
          menuButton.setAttribute("aria-expanded", "false");
          menuButton.textContent = "Menü";
          menuButton.focus();
        }
      });
    }
    menuButton.classList.remove("hidden");
  }
  if (nav) {
    nav.querySelectorAll("a[href]").forEach(function (link) {
      if (link.pathname === window.location.pathname) link.setAttribute("aria-current", "page");
    });
  }
  updateMobileMenu(!user.classList.contains("hidden"));

  var cfg = window.APP_CONFIG || {};
  var apiUrl = typeof cfg.resolveApiUrl === "function" ? cfg.resolveApiUrl("/api/me") : "/api/me";

  fetch(apiUrl, { credentials: "include" })
    .then(function (r) {
      if (!r.ok) throw new Error();
      return r.json();
    })
    .then(function (data) {
      updateMobileMenu(true);
      var welcomeActions = document.getElementById("welcome-actions");
      if (welcomeActions) {
        welcomeActions.innerHTML = '<a class="btn" href="/dashboard.html">Zu meinem Dashboard <span aria-hidden="true">↗</span></a><a class="text-link" href="/chat.html">Lerngruppe öffnen <span aria-hidden="true">→</span></a>';
        var entryNote = document.querySelector(".entry-note");
        if (entryNote) entryNote.textContent = "Schön, dass du wieder da bist. Deine Lerngruppe wartet auf dich.";
      }
      guest.classList.add("hidden");
      user.classList.remove("hidden");
      var nameEl = document.getElementById("nav-username");
      if (nameEl && data.username) nameEl.textContent = data.username;
      var adminEl = document.getElementById("nav-admin");
      if (adminEl) {
        if (data.role === "teacher" || data.role === "admin" || data.role === "tester" || data.role === "dev") {
          adminEl.classList.remove("hidden");
        }
        else adminEl.classList.add("hidden");
      }
    })
    .catch(function () {
      updateMobileMenu(false);
      user.classList.add("hidden");
      guest.classList.remove("hidden");
    });
})();
