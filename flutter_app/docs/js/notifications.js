(function () {
  if (document.getElementById("learning-notifications")) return;
  var entries = {};
  var loading = false;
  var revision = 0;
  var stopped = false;
  var root = document.createElement("aside");
  root.id = "learning-notifications";
  root.className = "learning-notifications";
  root.setAttribute("aria-label", "Benachrichtigungen");
  root.innerHTML = '<button type="button" class="notification-bell" aria-label="Benachrichtigungen" aria-expanded="false" aria-controls="notification-inbox">' +
    '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg>' +
    '<span class="notification-count" hidden></span></button>' +
    '<section id="notification-inbox" class="notification-inbox" aria-label="Offene Einladungen" hidden>' +
    '<h2>Einladungen zu Lerngruppen</h2><div class="notification-list"></div></section>' +
    '<div class="notification-popups" aria-live="polite" aria-relevant="additions"></div>' +
    '<p class="sr-only notification-feedback" role="status"></p>';
  document.body.appendChild(root);
  document.body.classList.add("has-learning-notifications");
  var bell = root.querySelector(".notification-bell");
  var badge = root.querySelector(".notification-count");
  var inbox = root.querySelector(".notification-inbox");
  var list = root.querySelector(".notification-list");
  var popups = root.querySelector(".notification-popups");
  var feedback = root.querySelector(".notification-feedback");

  function api(path, body) {
    var cfg = window.APP_CONFIG || {};
    var url = typeof cfg.resolveApiUrl === "function" ? cfg.resolveApiUrl(path) : path;
    return fetch(url, {
      method: body ? "POST" : "GET", credentials: "include",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (res) {
      if (res.status === 401) stop();
      return res.json().then(function (data) {
        if (!res.ok) { var error = new Error("request_failed"); error.status = res.status; throw error; }
        return data;
      });
    });
  }

  function endpoint(id) { return "/api/chat/learning-group-invitations/" + encodeURIComponent(id); }

  function stop() {
    stopped = true;
    clearInterval(pollTimer);
    Object.keys(entries).forEach(function (id) { clearTimeout(entries[id].timer); });
    root.remove();
    document.body.classList.remove("has-learning-notifications");
  }

  function setOpen(open) {
    inbox.hidden = !open;
    popups.hidden = open;
    bell.setAttribute("aria-expanded", String(open));
  }
  bell.addEventListener("click", function () { setOpen(inbox.hidden); });
  document.addEventListener("click", function (event) {
    if (!root.contains(event.target)) setOpen(false);
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !inbox.hidden) { setOpen(false); bell.focus(); }
  });

  function card(entry) {
    var item = document.createElement("article");
    item.className = "notification-card";
    var title = document.createElement("h3");
    title.textContent = entry.data.name;
    var description = document.createElement("p");
    description.textContent = entry.data.invited_by + " lädt dich zur Lerngruppe für " + entry.data.subject_label + " ein. Möchtest du dabei sein?";
    item.appendChild(title);
    item.appendChild(description);
    var actions = document.createElement("div");
    actions.className = "notification-actions";
    [["accept", "Dabei sein"], ["decline", "Ablehnen"]].forEach(function (option) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-small" + (option[0] === "decline" ? " btn-secondary" : "");
      btn.textContent = option[1];
      btn.disabled = !!entry.busy;
      btn.addEventListener("click", function () { respond(entry, option[0]); });
      actions.appendChild(btn);
    });
    item.appendChild(actions);
    if (entry.error) {
      var error = document.createElement("p");
      error.className = "notification-error";
      error.setAttribute("role", "alert");
      error.textContent = entry.error;
      item.appendChild(error);
    }
    return item;
  }

  function render() {
    var hadFocus = list.contains(document.activeElement) || popups.contains(document.activeElement);
    list.replaceChildren();
    popups.replaceChildren();
    var ids = Object.keys(entries);
    badge.textContent = String(ids.length);
    badge.hidden = !ids.length;
    bell.setAttribute("aria-label", "Benachrichtigungen: " + ids.length + " offene Einladungen");
    ids.forEach(function (id) {
      var entry = entries[id];
      list.appendChild(card(entry));
      if (entry.deadline > Date.now()) popups.appendChild(card(entry));
    });
    if (!ids.length) list.textContent = "Keine offenen Einladungen.";
    if (hadFocus) bell.focus();
  }

  function respond(entry, action) {
    if (entry.busy) return;
    entry.busy = true;
    entry.error = "";
    revision++;
    render();
    api(endpoint(entry.data.id), { action: action }).then(function () {
      clearTimeout(entry.timer);
      delete entries[entry.data.id];
      feedback.textContent = action === "accept" ? "Du bist jetzt Mitglied der Lerngruppe „" + entry.data.name + "“." : "Einladung abgelehnt.";
      document.dispatchEvent(new CustomEvent("learning-group-invitation-answered"));
    }).catch(function (error) {
      if (error.status === 404 || error.status === 409) {
        clearTimeout(entry.timer);
        delete entries[entry.data.id];
        feedback.textContent = "Diese Einladung ist nicht mehr offen.";
      } else {
        entry.error = "Antwort konnte nicht gespeichert werden. Bitte erneut versuchen.";
      }
    }).finally(function () {
      entry.busy = false;
      revision++;
      if (!stopped) render();
    });
  }

  function load() {
    if (loading || stopped || document.hidden) return;
    loading = true;
    var snapshot = revision;
    api("/api/chat/learning-group-invitations").then(function (data) {
      return Promise.all(data.invitations.map(function (invitation) {
        if (invitation.popup_remaining_ms !== null) return invitation;
        return api(endpoint(invitation.id), { action: "seen" }).then(function (seen) {
          invitation.popup_remaining_ms = seen.popup_remaining_ms;
          return invitation;
        }).catch(function () { return null; });
      }));
    }).then(function (invitations) {
      if (stopped || snapshot !== revision) return;
      var changed = false;
      var found = {};
      invitations.forEach(function (invitation) {
        if (!invitation) return;
        found[invitation.id] = true;
        var entry = entries[invitation.id];
        if (!entry) {
          entry = entries[invitation.id] = { data: invitation, deadline: Date.now() + invitation.popup_remaining_ms };
          changed = true;
          if (invitation.popup_remaining_ms > 0) {
            entry.timer = setTimeout(function () {
              entry.deadline = 0;
              if (!stopped) render();
            }, invitation.popup_remaining_ms);
          }
        }
      });
      Object.keys(entries).forEach(function (id) {
        if (!found[id] && !entries[id].busy) {
          clearTimeout(entries[id].timer);
          delete entries[id];
          changed = true;
        }
      });
      if (changed) render();
    }).catch(function () {
      // Keep existing invitations and retry after a temporary connection failure.
    }).finally(function () { loading = false; });
  }
  render();
  var pollTimer = setInterval(load, 5000);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) load(); });
  load();
})();
