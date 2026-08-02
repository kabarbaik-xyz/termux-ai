# ══ termux_ai.fileio ══ (fragment; merged by build.py)
class FileReader:
    TEXT_EXTS = {
        ".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm", ".py", ".sh", ".bash",
        ".js", ".jsx", ".ts", ".tsx", ".c", ".cpp", ".h", ".cs", ".java", ".go", ".rs",
        ".rb", ".php", ".swift", ".kt", ".css", ".scss", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    }

    @staticmethod
    def read(path, max_chars=20000):
        p = os.path.expanduser(path)
        if not os.path.exists(p): return f"Error: File not found at path '{p}'"
        ext = os.path.splitext(p)[1].lower()
        try:
            if ext in FileReader.TEXT_EXTS:
                with open(p, "r", encoding="utf-8", errors="ignore") as f: return f.read()[:max_chars]
            elif ext == ".pdf":
                if shutil.which("pdftotext"):
                    r = subprocess.run(["pdftotext", "-layout", p, "-"], capture_output=True, text=True, timeout=15)
                    return r.stdout[:max_chars] if r.returncode == 0 else "[Error reading PDF]"
                return "[Error: pdftotext not found. Run: pkg install poppler]"
            elif ext == ".docx": return FileReader._read_docx(p)[:max_chars]
            elif ext == ".pptx": return FileReader._read_pptx(p)[:max_chars]
            elif ext == ".xlsx": return FileReader._read_xlsx(p)[:max_chars]
            else: return f"[Unsupported file type: {ext}]"
        except Exception as e: return f"[Error reading {p}: {e}]"

    @staticmethod
    def _read_docx(path):
        with zipfile.ZipFile(path) as z: xml = z.read("word/document.xml").decode("utf-8")
        xml = xml.replace("</w:p>", "\n").replace("<w:br/>", "\n")
        return html.unescape("".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml, re.DOTALL))).strip()

    @staticmethod
    def _read_pptx(path):
        texts = []
        with zipfile.ZipFile(path) as z:
            slides = sorted([n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")], key=lambda x: int(re.search(r"slide(\d+)", x).group(1)))
            for slide in slides:
                xml = z.read(slide).decode("utf-8").replace("</a:p>", "\n")
                t = "".join(re.findall(r"<a:t[^>]*>(.*?)</a:t>", xml, re.DOTALL))
                if t: texts.append(f"--- Slide {re.search(r'slide(\d+)', slide).group(1)} ---\n" + html.unescape(t))
        return "\n\n".join(texts).strip()

    @staticmethod
    def _read_xlsx(path):
        """Reconstruct the worksheet table: resolve shared strings / inline
        strings / numbers per cell, honour sparse columns via the cell ref
        (e.g. 'C3'), and emit pipe-delimited rows so the data shape survives."""
        import xml.etree.ElementTree as ET
        def ln(tag): return tag.rsplit("}", 1)[-1]
        def kids(el, name): return [c for c in el.iter() if ln(c.tag) == name]
        try:
            z = zipfile.ZipFile(path)
        except Exception as e:
            return "[Error opening xlsx: %s]" % e
        names = z.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            try:
                root = ET.fromstring(z.read("xl/sharedStrings.xml"))
                for si in kids(root, "si"):
                    shared.append("".join((t.text or "") for t in si.iter() if ln(t.tag) == "t"))
            except Exception:
                pass
        sheets = [n for n in names if re.match(r"^xl/worksheets/sheet\d+\.xml$", n)]
        sheets.sort(key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
        out = []
        for sname in sheets:
            try:
                root = ET.fromstring(z.read(sname))
            except Exception:
                continue
            def cidx(ref):
                m = re.match(r"([A-Z]+)", ref or "")
                if not m: return 0
                n = 0
                for ch in m.group(1): n = n * 26 + (ord(ch) - 64)
                return n - 1
            rows_out = []
            for row in kids(root, "row"):
                cells = []
                for c in list(row):
                    if ln(c.tag) != "c": continue
                    t_attr = c.get("t")
                    v = next((x for x in c if ln(x.tag) == "v"), None)
                    isn = next((x for x in c if ln(x.tag) == "is"), None)
                    if t_attr == "s" and v is not None:
                        try: val = shared[int(v.text)]
                        except Exception: val = ""
                    elif t_attr == "inlineStr" and isn is not None:
                        val = "".join((tt.text or "") for tt in isn.iter() if ln(tt.tag) == "t")
                    elif v is not None:
                        val = v.text
                    else:
                        val = ""
                    idx = cidx(c.get("r", ""))
                    while len(cells) <= idx: cells.append("")
                    if idx < len(cells): cells[idx] = val
                if any(cells):
                    rows_out.append(" | ".join(cells))
            if rows_out:
                out.append("### %s (%d rows)" % (sname, len(rows_out)))
                out.extend(rows_out)
        return "\n".join(out).strip() or "[No data found in xlsx]"
