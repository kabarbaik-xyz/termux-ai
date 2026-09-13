/* Document viewer/editor.
 * doc-link anchors carry data-path="<folder>/<file>". Clicking loads the
 * artifact via GET /docs/read, renders it, and offers Edit (markdown
 * textarea) → Save (POST /docs/save).
 */
(function () {
  var viewer = document.getElementById("doc-viewer");
  var titleEl = document.getElementById("doc-title");
  var bodyEl = document.getElementById("doc-body");
  var editorEl = document.getElementById("doc-editor");
  var btnEdit = document.getElementById("btn-toggle-edit");
  var btnSave = document.getElementById("btn-save-doc");
  var pid = null;
  var currentPath = null;

  function findPid() {
    if (pid != null) return pid;
    var m = window.location.pathname.match(/\/projects\/(\d+)/);
    pid = m ? m[1] : "0";
    return pid;
  }

  function showEditor(markdown) {
    editorEl.value = markdown;
    editorEl.classList.remove("hidden");
    bodyEl.classList.add("hidden");
    btnEdit.classList.add("hidden");
    btnSave.classList.remove("hidden");
  }

  /* Upgrade ```mermaid fenced blocks (rendered as <pre><code
   * class="language-mermaid">) into live diagrams. Mermaid is vendored
   * locally (no CDN) — if it failed to load, blocks stay as code. */
  function renderMermaid(scope) {
    if (!window.mermaid) return;
    var blocks = (scope || bodyEl).querySelectorAll("pre > code.language-mermaid");
    if (!blocks.length) return;
    var nodes = [];
    blocks.forEach(function (code) {
      var div = document.createElement("div");
      div.className = "mermaid";
      div.textContent = code.textContent;   // raw source, entities intact
      code.parentNode.replaceChild(div, code);
      nodes.push(div);
    });
    try {
      window.mermaid.run({ nodes: nodes })["catch"](function () {});
    } catch (e) { /* leave source visible */ }
  }

  function showView(html) {
    bodyEl.innerHTML = html;
    renderMermaid();
    bodyEl.classList.remove("hidden");
    editorEl.classList.add("hidden");
    btnEdit.classList.remove("hidden");
    btnSave.classList.add("hidden");
  }

  document.addEventListener("click", function (ev) {
    var link = ev.target.closest ? ev.target.closest("a.doc-link") : null;
    if (!link) return;
    ev.preventDefault();
    var path = link.getAttribute("data-path");
    fetch("/docs/read?pid=" + findPid() + "&path=" + encodeURIComponent(path))
      .then(function (r) { if (!r.ok) throw new Error("not found"); return r.json(); })
      .then(function (doc) {
        currentPath = path;
        titleEl.textContent = doc.name;
        viewer.classList.remove("hidden");
        showView(doc.html);
        if (window.location.hash !== "#docs") window.location.hash = "#docs";
      })
      .catch(function (e) { alert("Could not load document: " + e.message); });
  });

  if (btnEdit) btnEdit.addEventListener("click", function () {
    showEditor(document.getElementById("doc-editor").value || editorEl.dataset.raw || "");
  });

  if (btnSave) btnSave.addEventListener("click", function () {
    var form = new FormData();
    form.append("markdown", editorEl.value);
    if (!currentPath) return;
    fetch("/docs/save?pid=" + findPid() + "&path=" + encodeURIComponent(currentPath), {
      method: "POST",
      body: form,
    })
      .then(function (r) { return r.json(); })
      .then(function () {
        fetch("/docs/read?pid=" + findPid() + "&path=" + encodeURIComponent(currentPath))
          .then(function (r) { return r.json(); })
          .then(function (doc) { showView(doc.html); })
          .catch(function () { showView("<p>saved</p>"); });
      })
      .catch(function (e) { alert("Save failed: " + e.message); });
  });

  // Carry the raw markdown over between edit/view toggles.
  document.addEventListener("click", function (ev) {
    var link = ev.target.closest ? ev.target.closest("a.doc-link") : null;
    if (link) {
      fetch("/docs/read?pid=" + findPid() + "&path=" + encodeURIComponent(link.getAttribute("data-path")))
        .then(function (r) { return r.json(); })
        .then(function (doc) { editorEl.dataset.raw = doc.markdown; })
        .catch(function () {});
    }
  });
})();