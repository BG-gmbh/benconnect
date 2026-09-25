// Fuegt auf jeder Seite einen einheitlichen Footer mit Links zu Impressum
// und Datenschutzerklaerung ein (Pflichtangaben muessen von jeder Seite aus
// leicht erreichbar sein, s. Paragraph 5 DDG).
(function () {
  var footer = document.createElement("footer");
  footer.className = "site-footer";
  footer.innerHTML =
    '<nav class="site-footer-nav">' +
      '<a href="/impressum.html">Impressum</a>' +
      '<a href="/datenschutz.html">Datenschutz</a>' +
      '<a href="/android.html" data-app-download>Android-App</a>' +
    "</nav>";
  document.body.appendChild(footer);
})();
