(function () {
  var params = new URLSearchParams(window.location.search);
  var code = params.get("flash");
  if (!code) return;

  var messages = {
    invalid: "Benutzername oder Passwort falsch.",
    shortuser: "Benutzername mindestens 3 Zeichen.",
    shortpass: "Passwort mindestens 6 Zeichen.",
    mismatch: "Passwörter stimmen nicht überein.",
    taken: "Dieser Benutzername ist schon vergeben.",
    logout: "Du bist ausgeloggt.",
    needlogin: "Bitte zuerst einloggen.",
    levels: "Bitte für jedes Fach Pro, Mittel oder Noob wählen.",
    invalid_class: "Bitte eine gültige Klasse eintragen (maximal 20 Zeichen).",
    saved: "Einstellungen gespeichert.",
    register_disabled: "Öffentliche Registrierung ist ausgeschaltet. Bitte Administrator oder Einladungscode.",
    admin_only: "Nur für Lehrer und Administratoren.",
    user_created: "Nutzer wurde angelegt.",
    setup_done: "Admin-Konto festgelegt. Du bist eingeloggt.",
    bad_invite: "Ungültiger oder bereits benutzter Code.",
    redeem_ok: "Konto erstellt. Willkommen!",
    bad_contact_email: "Bitte eine gültige E-Mail-Adresse eintragen.",
    notify_no_email: "Für Laden-Benachrichtigungen bitte eine E-Mail angeben oder die Option abwählen.",
    pwd_incomplete:
      "Zum Passwortwechsel bitte aktuelles Passwort, neues Passwort und Wiederholung ausfüllen.",
    pwd_current_wrong: "Das aktuelle Passwort ist falsch.",
    banned: "Dein Konto wurde gesperrt. Bitte den Admin kontaktieren.",
    account_deleted: "Dein Konto wurde gelöscht.",
    consent_required: "Bitte der Übermittlung an OpenAI zustimmen, oder manuell eintragen.",
    level_quiz_required: "Bitte beantworte zuerst die Fragen zur neuen Fach-Stufe.",
    level_quiz_failed: "Die neue Fach-Stufe wurde nicht gespeichert. Dafür waren noch nicht genug Antworten richtig.",
    level_quiz_unavailable: "Die Fragen für diese Fach-Stufe sind gerade nicht verfügbar.",
  };

  var text = messages[code];
  if (code === "banned") {
    var custom = (params.get("flash_msg") || "").trim();
    if (custom) text = custom;
  }
  if (!text) return;

  var ul = document.getElementById("flash-banner");
  if (!ul) return;

  var li = document.createElement("li");
  var cls =
    code === "saved" || code === "user_created" || code === "setup_done" || code === "redeem_ok" || code === "account_deleted"
      ? "flash-success"
      : code === "logout" || code === "register_disabled"
        ? "flash-info"
        : code === "needlogin"
          ? "flash-warning"
          : "flash-error";
  li.className = cls;
  li.textContent = text;
  ul.appendChild(li);

  try {
    var u = new URL(window.location.href);
    u.searchParams.delete("flash");
    u.searchParams.delete("flash_msg");
    window.history.replaceState({}, "", u.pathname + u.search);
  } catch (e) {}
})();
