(function () {
  var supportedActions = ["/login", "/register", "/setup", "/profile", "/logout", "/einladung"];

  var invitationInput = document.querySelector('form[action="/einladung"] input[name="code"]');
  var invitationCode = new URLSearchParams(window.location.search).get("code");
  if (invitationInput && invitationCode && !invitationInput.value) {
    invitationInput.value = invitationCode;
  }

  function normalizeAction(action) {
    if (!action) return "";
    var text = String(action).trim();
    if (!text) return "";
    if (/^https?:\/\//.test(text)) return text;
    if (text.charAt(0) === ".") {
      return "/" + text.replace(/^\.\/+/, "");
    }
    return text;
  }

  function getApiUrl(path) {
    var cfg = window.APP_CONFIG || {};
    if (typeof cfg.resolveApiUrl === "function") return cfg.resolveApiUrl(path);
    return path;
  }

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form || form.tagName !== "FORM") return;
    var action = normalizeAction(form.getAttribute("action") || "");
    if (supportedActions.indexOf(action) === -1) return;
    event.preventDefault();

    var method = (form.getAttribute("method") || "get").toUpperCase();
    var body = null;
    var headers = {};
    if (method === "GET") {
      body = null;
    } else if (form.enctype === "multipart/form-data") {
      body = new FormData(form);
    } else {
      body = new FormData(form);
    }

    fetch(getApiUrl(action), {
      method: method,
      credentials: "include",
      body: body,
      headers: headers,
    })
      .then(function (response) {
        var location = response.headers.get("Location");
        if (location) {
          window.location.assign(location);
          return;
        }
        if (response.redirected && response.url) {
          window.location.assign(response.url);
          return;
        }
        if (response.ok) {
          window.location.reload();
          return;
        }
        return response.text().then(function (text) {
          if (text) {
            document.open();
            document.write(text);
            document.close();
          }
        });
      })
      .catch(function () {
        window.location.reload();
      });
  });
})();
