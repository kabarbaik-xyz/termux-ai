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
        texts = []
        with zipfile.ZipFile(path) as z:
            if "xl/sharedStrings.xml" not in z.namelist(): return "[No text data found in xlsx]"
            xml = z.read("xl/sharedStrings.xml").decode("utf-8")
            for s in re.findall(r"<si>(.*?)</si>", xml, re.DOTALL):
                texts.append(html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", s, re.DOTALL))))
        return "\n".join(texts).strip()
