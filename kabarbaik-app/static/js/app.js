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

  /* ── Live stage console over SSE ──────────────────────────────────
   * The run lives SERVER-SIDE (background task). The EventSource merely
   * attaches: events replay from the server buffer (Last-Event-ID), so
   * refreshes and auto-reconnects are seamless and never duplicate runs. */
  var consoleEl = document.getElementById("console-log");
  var consoleState = document.getElementById("console-state");

  function consoleReset() {
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

  var activeStream = null;   // {es, label, tick, sawAny, reloads}

  function openStream(url, label) {
    consoleReset();
    consoleAppend("▶ " + label + " — connecting…", "st");
    if (consoleState) consoleState.textContent = "· " + label + " running";

    var start = Date.now();
    var tick = setInterval(function () {
      if (consoleState && activeStream) {
        var s = Math.floor((Date.now() - start) / 1000);
        consoleState.textContent = "· " + activeStream.label + " running " +
          Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
      }
    }, 1000);

    var st = { es: null, label: label, tick: tick, sawAny: false, reloads: false };
    activeStream = st;

    var es = new EventSource(url);
    st.es = es;
    es.onmessage = function (m) {
      var ev;
      try { ev = JSON.parse(m.data); } catch (e) { return; }
      st.sawAny = true;
      if (ev.type === "line") consoleAppend(ev.text);
      else if (ev.type === "status") consoleAppend(ev.text, "st");
      else if (ev.type === "done") {
        clearInterval(tick); es.close(); activeStream = null;
        consoleAppend((ev.ok ? "✓ " : "✗ ") + (ev.message || ""), ev.ok ? "done" : "err");
        if (consoleState) consoleState.textContent = ev.ok ? "· finished ✓" : "· finished ✗";
        toast(label + (ev.ok ? " — stage completed" : " — finished (see console)"),
              ev.ok ? "ok" : "err", 6000);
        setTimeout(function () { window.location.reload(); }, 1800);
      }
    };
    es.onerror = function () {
      // EventSource auto-reconnects (server replays from Last-Event-ID).
      // Only report trouble; NEVER fall back to a form submit — the run
      // continues server-side and any reconnect picks it up again.
      if (!st.sawAny) consoleAppend("… connection hiccup — retrying", "err");
      if (es.readyState === EventSource.CLOSED && activeStream === st) {
        clearInterval(tick); activeStream = null;
        consoleAppend("✗ stream closed — the run continues on the server. "
                      + "Reload this page to re-attach.", "err");
      }
    };
  }

  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    if (!form.matches || !form.matches('form[action*="/stage/"]')) return;
    if (!window.EventSource) return;   // ancient browser: native POST fallback

    ev.preventDefault();
    if (activeStream) return;          // already streaming a run

    var url = form.getAttribute("action") + "/stream";
    var step = form.closest(".flow-step");
    var label = step ? (step.querySelector(".step-label") || {}).textContent : "stage";

    document.querySelectorAll('form[action*="/stage/"] button').forEach(function (b) { b.disabled = true; });
    if (step) step.classList.add("running");
    openStream(url, label);
  });

  // A run already active when the page loads → auto re-attach + replay.
  var live = document.getElementById("live-run");
  if (live && window.EventSource && !activeStream) {
    var pidMatch = /\/projects\/(\d+)/.exec(window.location.pathname);
    if (pidMatch) {
      var stageName = live.dataset.stage;
      document.querySelectorAll(".flow-step").forEach(function (stp) {
        var lbl = stp.querySelector(".step-label");
        if (lbl && lbl.textContent.trim() === stageName) stp.classList.add("running");
      });
      // find the stage index from the first matching form action
      var idx = null;
      document.querySelectorAll('form[action*="/stage/"]').forEach(function (f) {
        var im = /\/stage\/(\d+)/.exec(f.getAttribute("action") || "");
        if (im && idx === null) {
          var stp = f.closest(".flow-step");
          var lbl = stp && stp.querySelector(".step-label");
          if (lbl && lbl.textContent.trim() === stageName) idx = im[1];
        }
      });
      if (idx !== null) {
        document.querySelectorAll('form[action*="/stage/"] button').forEach(function (b) { b.disabled = true; });
        openStream("/projects/" + pidMatch[1] + "/stage/" + idx + "/stream", stageName);
      }
    }
  }

  /* ── Confirm destructive actions ────────────────────────────────── */
  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    if (form.matches('form[action*="/admin/reset"]') || form.matches("form[data-confirm]")) {
      var msg = form.dataset.confirm || "This cannot be undone. Continue?";
      if (!window.confirm(msg)) ev.preventDefault();
    }
  });

  var done = document.querySelector("[data-ran-stage]");
  if (done) toast("Stage finished — " + (done.dataset.ranOk === "1" ? "succeeded" : "check the stage log"), "ok", 6000);

  var aiOut = document.querySelector(".ai-output");
  if (aiOut) setTimeout(function () { aiOut.style.opacity = "0"; aiOut.style.transition = "opacity .6s"; }, 20000);
})();
