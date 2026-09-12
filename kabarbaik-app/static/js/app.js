/* KabarBaik app UX layer: tabs, toasts, live stage console (SSE), confirms. */
(function () {
  /* ── Real tabs (show/hide, hash deep-links) ─────────────────────── */
  var SECTIONS = ["flow", "console", "docs", "inbox", "feedback", "tokens"];
  function showTab(id) {
    SECTIONS.forEach(function (s) {
      var el = document.getElementById(s);
      if (el) el.hidden = (s !== id);
    });
    document.querySelectorAll("[data-tabs] a").forEach(function (a) {
      a.classList.toggle("active", a.getAttribute("href") === "#" + id);
    });
  }
  document.addEventListener("click", function (ev) {
    var tab = ev.target.closest ? ev.target.closest("[data-tabs] a") : null;
    if (!tab) return;
    ev.preventDefault();
    showTab(tab.getAttribute("href").slice(1));
  });
  var hash = (window.location.hash || "").replace("#", "");
  if (hash && SECTIONS.indexOf(hash) >= 0) showTab(hash); else showTab("flow");
  // output panel (POST path) lives outside tabs — leave visible.

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
  try {
    var q = new URLSearchParams(window.location.search);
    if (q.get("msg")) {
      toast(q.get("msg"), q.get("kind") || "ok", 5000);
      if (window.history.replaceState)
        window.history.replaceState({}, "", window.location.pathname + window.location.hash);
    }
  } catch (e) {}

  /* ── Live stage console over SSE ────────────────────────────────── */
  var consoleEl = document.getElementById("console");
  var consoleState = document.getElementById("console-state");

  function consoleOpen() {
    showTab("console");
    if (consoleEl) consoleEl.textContent = "";
  }
  function consoleAppend(text, cls) {
    if (!consoleEl) return;
    var line = document.createElement("span");
    if (cls) line.className = cls;
    line.textContent = text + "\n";
    consoleEl.appendChild(line);
    consoleEl.scrollTop = consoleEl.scrollHeight;
  }

  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    if (!form.matches || !form.matches('form[action*="/stage/"]')) return;
    if (!window.EventSource) return;   // very old browser: native POST fallback

    ev.preventDefault();
    var url = form.getAttribute("action") + "/stream";
    var step = form.closest(".flow-step");
    var label = step ? (step.querySelector(".step-label") || {}).textContent : "stage";

    document.querySelectorAll('form[action*="/stage/"] button').forEach(function (b) { b.disabled = true; });
    if (step) step.classList.add("running");

    consoleOpen();
    consoleAppend("▶ " + label + " — connecting…", "st");
    if (consoleState) consoleState.textContent = "· " + label + " running";

    var start = Date.now();
    var tick = setInterval(function () {
      if (consoleState) {
        var s = Math.floor((Date.now() - start) / 1000);
        consoleState.textContent = "· " + label + " running " +
          Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
      }
    }, 1000);

    var es = new EventSource(url);
    var sawDone = false;
    es.onmessage = function (m) {
      var ev2;
      try { ev2 = JSON.parse(m.data); } catch (e) { return; }
      if (ev2.type === "line") consoleAppend(ev2.text);
      else if (ev2.type === "status") consoleAppend(ev2.text, "st");
      else if (ev2.type === "done") {
        sawDone = true;
        clearInterval(tick); es.close();
        consoleAppend((ev2.ok ? "✓ " : "✗ ") + (ev2.message || ""), ev2.ok ? "done" : "err");
        if (consoleState) consoleState.textContent = ev2.ok ? "· finished ✓" : "· finished ✗";
        toast(label + (ev2.ok ? " — stage completed" : " — finished (see console)"),
              ev2.ok ? "ok" : "err", 6000);
        setTimeout(function () { window.location.reload(); }, 1600);
      }
    };
    es.onerror = function () {
      if (sawDone) return;   // EventSource fires error after close() in some browsers
      clearInterval(tick); es.close();
      consoleAppend("✗ stream closed unexpectedly — falling back to form submit", "err");
      form.submit();   // synchronous fallback completes the run server-side
    };
  });

  /* ── Confirm destructive actions ────────────────────────────────── */
  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    if (form.matches('form[action*="/admin/reset"]') || form.matches("form[data-confirm]")) {
      var msg = form.dataset.confirm || "This cannot be undone. Continue?";
      if (!window.confirm(msg)) ev.preventDefault();
    }
  });

  // success toast after a completed POST-path run
  var done = document.querySelector("[data-ran-stage]");
  if (done) toast("Stage finished — " + (done.dataset.ranOk === "1" ? "succeeded" : "check the stage log"), "ok", 6000);

  var aiOut = document.querySelector(".ai-output");
  if (aiOut) setTimeout(function () { aiOut.style.opacity = "0"; aiOut.style.transition = "opacity .6s"; }, 20000);
})();
