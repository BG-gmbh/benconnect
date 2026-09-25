(function () {
  var cfg = window.APP_CONFIG || {};
  cfg.isAndroidApp = /(?:^|\s)BenConnectAndroid\/\d+(?:\.\d+)*(?:\s|$)/.test(navigator.userAgent);
  document.documentElement.classList.toggle("android-app", cfg.isAndroidApp);
  // Ein Render-Service liefert Frontend und API unter derselben Origin aus
  // (Flask serviert flutter_app/docs direkt), daher same-origin per Default.
  // Ueberschreibbar via window.APP_CONFIG = { apiBaseUrl: "…" }.
  function detectApiBase() {
    return "";
  }
  var defaultApiBase = detectApiBase();
  cfg.apiBaseUrl = cfg.apiBaseUrl || defaultApiBase;

  function normalizeBase(value) {
    if (!value) return "";
    return String(value).replace(/\/$/, "");
  }

  function normalizePath(value) {
    if (!value) return "";
    var text = String(value).trim();
    if (!text) return "";
    if (/^https?:\/\//.test(text)) return text;
    if (text.charAt(0) === "/") return text;
    if (text.charAt(0) === ".") {
      return "/" + text.replace(/^\.\/+/, "");
    }
    return "/" + text;
  }

  cfg.apiBaseUrl = normalizeBase(cfg.apiBaseUrl || defaultApiBase);

  cfg.resolveApiUrl = function (path) {
    var normalizedPath = normalizePath(path);
    if (!normalizedPath) return cfg.apiBaseUrl || "";
    if (/^https?:\/\//.test(normalizedPath)) return normalizedPath;
    if (!cfg.apiBaseUrl) return normalizedPath;
    return cfg.apiBaseUrl + normalizedPath;
  };

  cfg.resolveSitePath = function (path) {
    if (!path) return path;
    if (/^https?:\/\//.test(path)) return path;
    if (path.charAt(0) === "/") return "." + path;
    return path;
  };

  var originalFetch = window.fetch;
  if (originalFetch) {
    window.fetch = function (input, init) {
      if (typeof input === "string" && input.charAt(0) === "/") {
        input = cfg.resolveApiUrl(input);
      }
      return originalFetch.call(this, input, init);
    };
  }

  function rewriteDom() {
    var nodes = Array.prototype.slice.call(document.querySelectorAll("a[href^='/'], link[href^='/'], script[src^='/'], img[src^='/']"));
    nodes.forEach(function (node) {
      var attr = node.tagName === "LINK" || node.tagName === "SCRIPT" || node.tagName === "IMG" ? "href" : "src";
      var value = node.getAttribute(attr);
      if (value && value.charAt(0) === "/") {
        node.setAttribute(attr, cfg.resolveSitePath(value));
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", rewriteDom);
  } else {
    rewriteDom();
  }

  window.APP_CONFIG = cfg;
})();
