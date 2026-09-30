(function () {
  if (document.getElementById("learning-notifications")) return;
  var entries = {};
  var loading = false;
  var revision = 0;
  var stopped = false;
  var ratingData = { open: [], rated: [] };
  var ratingNodes = {};
  var ratingsLoading = false;
  var ratingsRevision = 0;
  var ratedKey = "";
  var root = document.createElement("aside");
  root.id = "learning-notifications";
  root.className = "learning-notifications";
  root.setAttribute("aria-label", "Benachrichtigungen");
  root.innerHTML = '<button type="button" class="notification-bell" aria-label="Benachrichtigungen" aria-expanded="false" aria-controls="notification-inbox">' +
    '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg>' +
    '<span class="notification-count" hidden></span></button>' +
    '<section id="notification-inbox" class="notification-inbox" aria-label="Einladungen und Bewertungen" hidden>' +
    '<h2>Einladungen zu Lerngruppen</h2><div class="notification-list"></div>' +
    '<h2 class="rating-section-title">Offene Bewertungen <span class="open-rating-count"></span></h2>' +
    '<p class="rating-load-error" role="status"></p><div class="open-rating-list"></div>' +
    '<details class="rated-section"><summary>Bewertet <span class="rated-count"></span></summary><div class="rated-list"></div></details></section>' +
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

  var openRatings = root.querySelector(".open-rating-list");
  var ratedList = root.querySelector(".rated-list");

  function updateBadge() {
    var invitations = Object.keys(entries).length;
    var count = invitations + ratingData.open.length;
    badge.textContent = String(count);
    badge.hidden = !count;
    bell.setAttribute("aria-label", "Benachrichtigungen: " + invitations +
      " offene Einladungen, " + ratingData.open.length + " offene Bewertungen");
  }

  function ratingCard(row, completed) {
    var item = document.createElement("article");
    item.className = "notification-card rating-card";
    var title = document.createElement("h3");
    title.textContent = row.subject_label || "Termin";
    var description = document.createElement("p");
    description.textContent = [row.appointment, row.location].filter(Boolean).join(" · ") || "Abgeschlossener Termin";
    item.append(title, description);
    if (completed) {
      var result = document.createElement("p");
      result.textContent = row.rating + "/5 Sterne" + (row.comment ? " · " + row.comment : "");
      item.appendChild(result);
      return item;
    }
    var form = document.createElement("form");
    var selectLabel = document.createElement("label");
    selectLabel.textContent = "Sterne";
    var select = document.createElement("select");
    select.name = "rating";
    for (var n = 5; n >= 1; n--) {
      var option = document.createElement("option");
      option.value = String(n);
      option.textContent = n + (n === 1 ? " Stern" : " Sterne");
      select.appendChild(option);
    }
    selectLabel.appendChild(select);
    var commentLabel = document.createElement("label");
    var hint = document.createElement("span");
    var comment = document.createElement("textarea");
    comment.name = "comment";
    comment.rows = 2;
    comment.maxLength = 2000;
    commentLabel.append(hint, comment);
    function updateHint() {
      comment.required = Number(select.value) < 4;
      hint.textContent = comment.required ? "Kommentar (Pflicht bei 1–3 Sternen)" : "Kommentar (optional)";
    }
    select.addEventListener("change", updateHint);
    updateHint();
    var error = document.createElement("p");
    error.className = "notification-error";
    error.setAttribute("role", "alert");
    var submit = document.createElement("button");
    submit.type = "submit";
    submit.className = "btn btn-small";
    submit.textContent = "Bewertung speichern";
    form.append(selectLabel, commentLabel, error, submit);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (submit.disabled) return;
      var stars = Number(select.value);
      var text = comment.value.trim();
      if (stars < 4 && !text) {
        error.textContent = "Bei 1–3 Sternen bitte einen Kommentar eingeben.";
        comment.focus();
        return;
      }
      error.textContent = "";
      submit.disabled = select.disabled = comment.disabled = true;
      ratingsRevision++;
      api("/api/ratings/" + encodeURIComponent(row.id), {rating: stars, comment: text}).then(function () {
        ratingsRevision++;
        ratingData.open = ratingData.open.filter(function (r) { return r.id !== row.id; });
        ratingData.rated = ratingData.rated.filter(function (r) { return r.id !== row.id; });
        ratingData.rated.unshift(Object.assign({}, row, {rating: stars, comment: text}));
        renderRatings();
        feedback.textContent = "Bewertung gespeichert. Du findest sie unter Bewertet.";
        document.dispatchEvent(new CustomEvent("appointment-rating-saved"));
      }).catch(function () {
        ratingsRevision++;
        error.textContent = "Bewertung konnte nicht gespeichert werden. Bitte erneut versuchen.";
      }).finally(function () { submit.disabled = select.disabled = comment.disabled = false; });
    });
    item.appendChild(form);
    return item;
  }

  function renderRatings() {
    var focused = openRatings.contains(document.activeElement);
    var empty = openRatings.querySelector(".rating-empty");
    if (empty) empty.remove();
    var ids = {};
    ratingData.open.forEach(function (row) {
      ids[row.id] = true;
      if (!ratingNodes[row.id]) {
        ratingNodes[row.id] = ratingCard(row, false);
        openRatings.appendChild(ratingNodes[row.id]);
      }
    });
    Object.keys(ratingNodes).forEach(function (id) {
      if (!ids[id]) { ratingNodes[id].remove(); delete ratingNodes[id]; }
    });
    if (!ratingData.open.length) {
      var none = document.createElement("p");
      none.className = "rating-empty";
      none.textContent = "Keine offenen Bewertungen.";
      openRatings.appendChild(none);
    }
    root.querySelector(".open-rating-count").textContent = "(" + ratingData.open.length + ")";
    root.querySelector(".rated-count").textContent = "(" + ratingData.rated.length + ")";
    var key = JSON.stringify(ratingData.rated);
    if (key !== ratedKey) {
      ratedKey = key;
      ratedList.replaceChildren();
      ratingData.rated.forEach(function (row) { ratedList.appendChild(ratingCard(row, true)); });
      if (!ratingData.rated.length) ratedList.textContent = "Noch keine Bewertung abgegeben.";
    }
    updateBadge();
    if (focused && !openRatings.contains(document.activeElement)) root.querySelector(".rated-section summary").focus();
  }

  function loadRatings() {
    if (ratingsLoading || stopped || document.hidden) return;
    ratingsLoading = true;
    var snapshot = ratingsRevision;
    api("/api/ratings").then(function (data) {
      if (stopped || snapshot !== ratingsRevision) return;
      if (!Array.isArray(data.open) || !Array.isArray(data.rated)) throw new Error("invalid_response");
      ratingData = data;
      root.querySelector(".rating-load-error").textContent = "";
      renderRatings();
    }).catch(function () {
      root.querySelector(".rating-load-error").textContent = "Bewertungen konnten nicht geladen werden. Erneuter Versuch folgt automatisch.";
    }).finally(function () { ratingsLoading = false; });
  }

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
    updateBadge();
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
  var pollTimer = setInterval(function () { load(); loadRatings(); }, 5000);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) { load(); loadRatings(); } });
  document.addEventListener("appointment-rating-saved", loadRatings);
  renderRatings();
  load();
  loadRatings();
})();
