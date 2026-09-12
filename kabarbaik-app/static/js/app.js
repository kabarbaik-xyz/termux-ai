/* KabarBaik app UX layer: toasts (?msg=), stage-run feedback, confirms. */
(function () {
  /* ── Toasts ─────────────────────────────────────────────────────── */
  function toast(text, kind, ttl) {
    var box = document.getElementById("toasts");
    if (!box) return;
    var el = document.createElement("div");
    el.className = "toast " + (kind || "ok");
    var span = document.createElement("span");
    span.textContent = text;
    var x = document.createElement("button");
    x.className = "close"; x.setAttribute("aria-label", "dismiss"); x.textContent = "×";
    x.onclick = function () { el.remove(); };
    el.appendChild(span); el.appendChild(x);
    box.appendChild(el);
    setTimeout(function () { el.style.opacity = "0"; el.style.transition = "opacity .4s"; }, ttl || 4200);
    setTimeout(function () { el.remove(); }, (ttl || 4200) + 450);
  }
  window.kbToast = toast;

  // flash from redirects (?msg=...&kind=ok|err)
  try {
    var q = new URLSearchParams(window.location.search);
    if (q.get("msg")) {
      toast(q.get("msg"), q.get("kind") || "ok", 5000);
      if (window.history.replaceState) {
        window.history.replaceState({}, "", window.location.pathname + window.location.hash);
      }
    }
  } catch (e) { /* old browsers: toast already skipped */ }

  /* ── Stage runs: lock UI + running banner with elapsed timer ───── */
  var STAGE_FORM_SEL = 'form[action*="/stage/"]';
  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    if (!form.matches || !form.matches(STAGE_FORM_SEL)) return;

    var step = form.closest(".flow-step");
    var label = step ? (step.querySelector(".step-label") || {}).textContent : "stage";
    var btn = form.querySelector("button");

    // lock every stage button on the page
    document.querySelectorAll(STAGE_FORM_SEL + " button").forEach(function (b) { b.disabled = true; });

    if (step) step.classList.add("running");
    if (btn) { btn.disabled = true; var t = btn.textContent; btn.innerHTML = '<span class="spin"></span> Running…'; btn.dataset.label = t; }

    var banner = document.createElement("div");
    banner.className = "run-banner";
    banner.innerHTML = '<span class="spin"></span><span>Running <strong></strong> — the AI writes files; ' +
      'this can take 1–15 minutes.</span><span class="elapsed">0:00</span>';
    banner.querySelector("strong").textContent = label;
    document.body.appendChild(banner);

    var start = Date.now();
    var el = banner.querySelector(".elapsed");
    var timer = setInterval(function () {
      var s = Math.floor((Date.now() - start) / 1000);
      el.textContent = Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
    }, 1000);

    // let the native submit proceed; on beforeunload (page swap) stop the timer
    window.addEventListener("pagehide", function () { clearInterval(timer); });
  });

  /* ── Confirm destructive actions ────────────────────────────────── */
  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    if (form.matches('form[action*="/admin/reset"]') || form.matches("form[data-confirm]")) {
      var msg = form.dataset.confirm || "This cannot be undone. Continue?";
      if (!window.confirm(msg)) ev.preventDefault();
    }
  });

  // success toast after a completed stage run (page re-rendered w/ ran_stage)
  var done = document.querySelector("[data-ran-stage]");
  if (done) {
    toast("Stage finished — " + (done.dataset.ranOk === "1" ? "succeeded" : "finished (check the stage log)"), "ok", 6000);
  }

  // auto-fade the long AI output panel
  var banner = document.querySelector(".ai-output");
  if (banner) {
    setTimeout(function () {
      banner.style.opacity = "0"; banner.style.transition = "opacity .6s";
    }, 20000);
  }

  /* ── Tab navigation (scroll + highlight) ────────────────────────── */
  function selectTab(id) {
    document.querySelectorAll(".tabs a").forEach(function (a) {
      a.classList.toggle("active", a.getAttribute("href") === "#" + id);
    });
    var target = document.getElementById(id);
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  document.addEventListener("click", function (ev) {
    var tab = ev.target.closest ? ev.target.closest(".tabs a") : null;
    if (!tab) return;
    ev.preventDefault();
    selectTab(tab.getAttribute("href").slice(1));
  });
  (function applyHash() {
    var id = (window.location.hash || "").replace("#", "");
    if (id && document.getElementById(id)) selectTab(id);
  })();
})();
