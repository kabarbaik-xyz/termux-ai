/* WYSIWYG editor bootstrapping (CKEditor 5 classic build from CDN).
 * Annotate <textarea class="rte" data-editor> to upgrade it into a rich-text
 * editor. On submit, the editor's HTML is written back into the textarea.
 * If the CDN is unreachable we silently keep the plain textarea (graceful).
 */
(function () {
  var CDN = "https://cdn.ckeditor.com/ckeditor5/44.0.0/classic/ckeditor.js";

  function syncEditor(editor, textarea) {
    try { textarea.value = editor.getData(); } catch (e) { /* keep raw text */ }
  }

  var instances = [];

  function initAll() {
    var areas = Array.prototype.slice.call(document.querySelectorAll(".rte[data-editor]"));
    if (!areas.length) return;
    if (typeof window.CKEDITOR === "undefined") {
      var s = document.createElement("script");
      s.src = CDN;
      s.onload = function () {
        areas.forEach(initOne);
        // keep the textarea in sync right before any form submit
        document.addEventListener("submit", function () {
          instances.forEach(function (rec) { syncEditor(rec.editor, rec.area); });
        });
      };
      document.head.appendChild(s);
    } else {
      areas.forEach(initOne);
    }
  }

  function initOne(area) {
    window.CKEDITOR.ClassicEditor.create(area, {
      toolbar: {
        items: [
          "heading", "|", "bold", "italic", "underline", "strikethrough", "|",
          "bulletedList", "numberedList", "indent", "outdent", "|",
          "blockQuote", "codeBlock", "link", "insertTable", "|",
          "undo", "redo",
        ],
      },
      heading: { options: [
        { model: "paragraph", title: "Paragraph", class: "ck-heading_paragraph" },
        { model: "heading1", view: "h2", title: "Heading 1", class: "ck-heading_heading1" },
        { model: "heading2", view: "h3", title: "Heading 2", class: "ck-heading_heading2" },
        { model: "heading3", view: "h4", title: "Heading 3", class: "ck-heading_heading3" },
      ]},
      table: {
        contentToolbar: ["tableColumn", "tableRow", "mergeTableCells", "tableCellProperties", "tableProperties"],
      },
    }).then(function (editor) {
      instances.push({ editor: editor, area: area });
    }).catch(function () { /* leave plain textarea */ });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();