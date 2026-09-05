/* Tab navigation: scroll to the target section and highlight the tab.
 * Sections stay visible (no hiding) so the artifact viewer never gets lost.
 */
(function () {
  function selectTab(id) {
    document.querySelectorAll(".tabs a").forEach(function (a) {
      a.classList.toggle("active", a.getAttribute("href") === "#" + id);
    });
    var target = document.getElementById(id);
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  document.addEventListener("click", function (ev) {
    var tab = ev.target.closest ? ev.target.closest(".tabs a") : null;
    if (!tab) return;
    ev.preventDefault();
    var id = tab.getAttribute("href").slice(1);
    selectTab(id);
  });

  function applyHash() {
    var id = (window.location.hash || "").replace("#", "");
    if (id && document.getElementById(id)) selectTab(id);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyHash);
  } else {
    applyHash();
  }

  // Auto-fade the AI output banner so the dashboard isn't cluttered.
  var banner = document.querySelector(".ai-output");
  if (banner) {
    setTimeout(function () {
      banner.style.opacity = "0";
      banner.style.transition = "opacity .6s";
    }, 20000);
  }
})();