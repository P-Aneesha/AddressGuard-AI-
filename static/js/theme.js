/* Light / dark theme switch shared by every page.
   The initial theme is set by an inline script in each page's <head> (saved
   choice, else the system preference) so the page never flashes the wrong theme. */
(function () {
  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    var toggle = document.getElementById("themeToggle");
    if (!toggle) return;
    // The label names the theme the button switches to.
    toggle.innerHTML = theme === "light"
      ? '<span aria-hidden="true">☾</span><span class="theme-label">Dark</span>'
      : '<span aria-hidden="true">☀</span><span class="theme-label">Light</span>';
    toggle.title = theme === "light" ? "Switch to dark theme" : "Switch to light theme";
    toggle.setAttribute("aria-label", toggle.title);
  }

  applyTheme(document.documentElement.dataset.theme === "light" ? "light" : "dark");

  var toggle = document.getElementById("themeToggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
      applyTheme(next);
      try { localStorage.setItem("ag-theme", next); } catch (_) {}
    });
  }
})();
