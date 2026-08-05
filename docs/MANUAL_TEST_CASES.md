# Manual Test Cases — Termux AI (CLI)

> **Versi**: v7.0.0
> **Tujuan**: Dokumen panduan pengujian manual (exploratory & regression) untuk aplikasi CLI "Termux AI".
> **Cakupan**: positive, negative, dan *edge cases* untuk seluruh modul fungsional.
> **Cara pakai**: Jalankan setiap test case secara berurutan. Catat hasil di kolom **Pass/Fail/Blocked** beserta catatan.

## Daftar Isi
1. [Instalasi & Build](#1-instalasi--build)
2. [CLI & Argumen](#2-cli--argumen)
3. [Backend & Koneksi](#3-backend--koneksi)
4. [Konfigurasi](#4-konfigurasi)
5. [Slash Commands](#5-slash-commands)
6. [Streaming & UI](#6-streaming--ui)
7. [Mode Tools (Build & Plan) & Keamanan](#7-mode-tools-build--plan--keamanan)
8. [Riwayat Chat & Database](#8-riwayat-chat--database)
9. [Skill System](#9-skill-system)
10. [File Attachment](#10-file-attachment)
11. [fetch_url & Keamanan SSRF](#11-fetch_url--keamanan-ssrf)
12. [Compact & Manajemen Konteks](#12-compact--manajemen-konteks)
13. [Ollama Server Manager](#13-ollama-server-manager)
14. [TTS, Copy, Share & Fitur Termux](#14-tts-copy-share--fitur-termux)
15. [Edge Cases & Robustness](#15-edge-cases--robustness)

---

## 1. Instalasi & Build

| ID | Skenario | Langkah | Expected Result | Status |
|----|----------|---------|-----------------|--------|
| INST-01 | Build artefak `ai` dari source | Jalankan `python3 build.py` di root proyek | File `ai` ter-generate, executable, tanpa error | |
| INST-02 | Build dengan modul hilang | Hapus sementara salah satu file di `src/`, lalu build | Error yang jelas menunjukkan file hilang | |
| INST-03 | Validasi freshness (pre-commit hook) | `git commit` setelah mengubah `src/*.py` tanpa rebuild | Hook menolak commit, minta rebuild | |
| INST-04 | Urutan modul benar | Cek isi `ai`; pastikan tidak ada `import` antar-modul `src/` | Tidak ada ImportError saat menjalankan `./ai` | |
| INST-05 | Permission executable | `ls -la ai` setelah build | File memiliki flag `+x` | |
| INST-06 | Dependensi nol | Jalankan di environment Python bersih (tanpa pip packages) | Berjalan normal; hanya stdlib | |

---

## 2. CLI & Argumen

| ID | Skenario | Langkah | Expected Result | Status |
|----|----------|---------|-----------------|--------|
| CLI-01 | One-shot prompt | `./ai "apa itu Python"` | Jawaban singkat dicetak, program keluar | |
| CLI-02 | Mode interaktif | `./ai` tanpa argumen | Prompt REPL muncul (`> `), menunggu input | |
| CLI-03 | Pilih model | `./ai -m llama3.2 "halo"` | Menggunakan model yang ditentukan | |
| CLI-04 | Generate command shell | `./ai -c "cari semua file py"` | Hanya output command shell, bukan narasi | |
| CLI-05 | Output JSON | `./ai -j "apa itu 1+1"` | Output JSON valid dengan field yang relevan | |
| CLI-06 | Continue session terakhir | `./ai --continue "lanjut"` | Melanjutkan percakapan sebelumnya | |
| CLI-07 | Pipe dari stdin | `echo "test" \| ./ai` | Membaca input dari pipe sebagai prompt | |
| CLI-08 | Argumen tidak dikenal | `./ai --tidak-ada` | Pesan error argparse yang jelas, exit code ≠ 0 | |
| CLI-09 | Prompt kosong (satu kata) | `./ai ""` | Tidak crash; error atau abaikan dengan anggun | |
| CLI-10 | Tanpa backend terkonfigurasi | Hapus config, jalankan `./ai "hi"` | Pesan yang memandu setup (mis. `/setup`) | |

---

## 3. Backend & Koneksi

| ID | Skenario | Langkah | Expected Result | Status |
|----|----------|---------|-----------------|--------|
| BE-01 | Ollama default | `./ai "halo"` dengan ollama running | Balasan diterima dari model lokal | |
| BE-02 | OpenAI backend | Set `backend=openai` + API key, lalu chat | Balasan dari OpenAI API | |
| BE-03 | Anthropic backend | Set `backend=anthropic` + key | Balasan dari Claude | |
| BE-04 | Groq backend | Set `backend=groq` + key | Balasan dari Groq | |
| BE-05 | OpenRouter backend | Set `backend=openrouter` + key | Balasan dari OpenRouter | |
| BE-06 | API key via env | Set `OPENAI_API_KEY` env, tanpa profile config | Backend membaca key dari env | |
| BE-07 | API key via profile config | Set `api_keys.openai` di config.json | Dipakai sebagai prioritas atas env | |
| BE-08 | Retry pada transient error | Simulasikan HTTP 429/500/502/503/504 | Retry hingga 3x dengan exponential backoff (0.5s×2^n) | |
| BE-09 | Non-retryable error | Simulasikan HTTP 401/403 | Langsung gagal, pesan auth error | |
| BE-10 | Backend tidak dikenal | Set `backend=tidakada` | `BackendError` atau pesan yang jelas | |
| BE-11 | Ollama tidak running | Matikan ollama, lalu chat | Pesan koneksitas/panduan `/server` | |
| BE-12 | Network timeout | Simulasikan koneksi lambat/gangguan | Timeout terdeteksi, error terbaca pengguna | |

---

## 4. Konfigurasi

| ID | Skenario | Langkah | Expected Result | Status |
|----|----------|---------|-----------------|--------|
| CFG-01 | Baca config default | Jalankan `./ai` pertama kali (config belum ada) | Membuat `~/.config/termux-ai/config.json` dengan DEFAULTS | |
| CFG-02 | Ubah nilai via `/config set` | `/config set temperature 0.2` | Nilai tersimpan & terbaca di config.json | |
| CFG-03 | Set nested path | `/config set backends.ollama.model qwen2.5:3b` | Path bersarang diperbarui | |
| CFG-04 | Config corrupt | Tulis JSON rusak di config.json, jalankan | Warning ditampilkan, fallback ke defaults | |
| CFG-05 | Migrasi cap v2 | Config lama dengan `max_tokens=4096` | Auto-bump ke 8192, flag `_cap_v2=True` | |
| CFG-06 | Migrasi tidak overwrite custom | `max_tokens` custom (mis. 2000) | Tidak diubah oleh migrasi | |
| CFG-07 | File permission aman | Cek mode config.json | File config hanya readable oleh owner (0600) | |
| CFG-08 | `/status` menampilkan config | `/status` | Menampilkan config, API key di-mask | |
| CFG-09 | `/config` (tanpa argumen) | `/config` | Menampilkan semua nilai config (key di-mask) | |
| CFG-10 | System prompt override | Set `system_instruction`, lalu chat | Persona custom dipakai; TOOL_RULES tetap di-append | |

---

## 5. Slash Commands

### 5.1 Manajemen Sesi & Riwayat

| ID | Command | Langkah | Expected Result | Status |
|----|---------|---------|-----------------|--------|
| CMD-01 | `/new` | Jalankan di REPL | Sesi baru dimulai, `cid` di-reset | |
| CMD-02 | `/continue` | Setelah `/new` | Melanjutkan sesi terakhir | |
| CMD-03 | `/show` | Setelah beberapa pesan | Menampilkan isi percakapan aktif | |
| CMD-04 | `/history` | Setelah beberapa sesi | Daftar percakapan muncul (paginated) | |
| CMD-05 | `/load <id>` | `/load 3` | Memuat percakapan dengan ID tersebut | |
| CMD-06 | `/load <id>` tidak ada | `/load 9999` | Pesan "not found", tidak crash | |
| CMD-07 | `/rename <nama>` | `/rename "tes-regex"` | Judul percakapan berubah | |
| CMD-08 | `/save` | `/save` | Menandai percakapan sebagai tersimpan | |
| CMD-09 | `/unsave` | `/unsave` | Menghapus flag tersimpan | |
| CMD-10 | `/sessions` | `/sessions` | Menampilkan daftar sesi tersimpan | |
| CMD-11 | `/delete <id>` | `/delete 2` | Percakapan dihapus permanen | |
| CMD-12 | `/search <kata>` | `/search python` | Menemukan percakapan yang cocok | |
| CMD-13 | `/export <file>` | `/export chat.txt` | File berisi transkrip percakapan dibuat | |
| CMD-14 | `/import <file>` | `/import chat.txt` | Percakapan dimuat dari file | |
| CMD-15 | `/prune` | `/prune` (dengan `prune_days` di-set) | Menghapus percakapan lama sesuai kebijakan | |
| CMD-16 | `/undo` | Setelah pasangan Q&A | Menghapus pasangan user+assistant terakhir | |

### 5.2 Toggle & Mode

| ID | Command | Fungsi | Expected Result | Status |
|----|---------|--------|-----------------|--------|
| CMD-17 | `/tools` | Toggle Build/Plan mode | `tools_enabled` berubah (Write+Read vs Read-only) | |
| CMD-18 | `/strategy` | Toggle strategy-first | `strategy_first` berubah, plan dibuat dulu | |
| CMD-19 | `/think` | Toggle extended thinking | `extended_thinking` aktif (Anthropic-only) | |
| CMD-20 | `/multi` | Toggle multi-line input | Input multi-baris aktif/non-aktif | |
| CMD-21 | `/expand` | Toggle expand output | Long blocks di-expand/folded | |
| CMD-22 | `/fold` | Fold long blocks | Output panjang di-fold sesuai config | |

### 5.3 Backend & Model

| ID | Command | Fungsi | Expected Result | Status |
|----|---------|--------|-----------------|--------|
| CMD-23 | `/backends` | Daftar backend | Menampilkan backend yang tersedia | |
| CMD-24 | `/backend <nama>` | Ganti backend | Backend aktif berubah | |
| CMD-25 | `/model <nama>` | Ganti model | Model pada profil berubah | |
| CMD-26 | `/profile <nama>` | Ganti profil | Profil aktif berubah | |
| CMD-27 | `/setup` | Setup wizard | Memandu konfigurasi awal | |

### 5.4 Utilitas

| ID | Command | Fungsi | Expected Result | Status |
|----|---------|--------|-----------------|--------|
| CMD-28 | `/system` | Lihat/edit system prompt | Menampilkan/izinkan edit system prompt | |
| CMD-29 | `/config` | Lihat/edit config | Menampilkan config (masked) | |
| CMD-30 | `/tokens` | Lihat pemakaian token | Menampilkan token usage per-model | |
| CMD-31 | `/cost` | Estimasi biaya | Menampilkan estimasi biaya/token | |
| CMD-32 | `/copy` | Copy reply terakhir | Reply terakhir tersalin ke clipboard | |
| CMD-33 | `/paste` | Tempel clipboard | Isi clipboard di-paste sebagai input | |
| CMD-34 | `/speak` | TTS reply | Reply dibacakan via TTS (Termux) | |
| CMD-35 | `/share` | Share reply | Dialog share Termux muncul | |
| CMD-36 | `/last` | Tampilkan reply terakhir | Menampilkan `last_reply` | |
| CMD-37 | `/clear` | Bersihkan layar | Layar terminal dibersihkan | |
| CMD-38 | `/help` | Daftar bantuan | Menampilkan semua command tersedia | |
| CMD-39 | `/exit` / `/quit` | Keluar | Program keluar dengan bersih (db ditutup) | |
| CMD-40 | `/regen` | Regenerasi reply | Menghasilkan ulang reply untuk prompt terakhir | |
| CMD-41 | `/retry` | Retry request terakhir | Mengulang request terakhir | |
| CMD-42 | `/diff` | Tampilkan diff perubahan | Menampilkan perubahan file | |
| CMD-43 | Command tidak dikenal | `/tidakada` | Pesan "unknown command", tidak crash | |

---

## 6. Streaming & UI

| ID | Skenario | Langkah | Expected Result | Status |
|----|----------|---------|-----------------|--------|
| UI-01 | Streaming token aktif | Kirim prompt dengan `stream=True` | Token muncul bertahap (bukan sekaligus) | |
| UI-02 | Spinner saat menunggu | Aktifkan TTY, kirim prompt | Spinner animasi berputar saat menunggu | |
| UI-03 | Spinner berhenti saat reply | Tunggu reply selesai | Spinner berhenti sebelum output dicetak | |
| UI-04 | Spinner berhenti saat konfirmasi tool | Backend minta persetujuan tool saat spinner jalan | Spinner berhenti sebelum prompt konfirmasi | |
| UI-05 | Empty reply | Simulasikan reply kosong | Spinner tetap berhenti; tidak stacking | |
| UI-06 | Reply panjang | Kirim prompt yang menghasilkan output panjang | Output ter-fold bila `fold_long_blocks=True` | |
| UI-07 | Non-TTY (pipe) | Jalankan `./ai "halo" \| cat` | Tanpa spinner/ANSI, output plain | |
| UI-08 | Multi-line toggle | `/multi` lalu ketik input multiline | Input multi-baris diterima | |
| UI-09 | Unicode/emoji | Kirim prompt dengan emoji | Emoji dirender dengan benar | |
| UI-10 | `AI_DEBUG=1` | Set env, picu error | Full traceback ditampilkan | |
| UI-11 | `AI_DEBUG` tidak diset | Picu error | Pesan error ringkas, tanpa traceback | |

---

## 7. Mode Tools (Build & Plan) & Keamanan

### 7.1 Mode Tools Umum

| ID | Skenario | Langkah | Expected Result | Status |
|----|----------|---------|-----------------|--------|
| TOOL-01 | Build mode (Write+Read) | `/tools` ON, minta model tulis file | Tool `write_file` dijalankan (dengan konfirmasi) | |
| TOOL-02 | Plan mode (Read-only) | `/tools` OFF | Hanya `read_file`/`list_files`/`search_files`/`fetch_url` | |
| TOOL-03 | Auto-execute safe tools | Model panggil `read_file` | Dijalankan otomatis tanpa konfirmasi | |
| TOOL-04 | Batch confirmation | Model usulkan banyak tool | Konfirmasi batch dengan opsi y/n/a | |
| TOOL-05 | Auto-continue ('a') | Pilih 'a' saat konfirmasi | Prompt konfirmasi tidak muncul lagi sesi ini | |
| TOOL-06 | Confirm 'n' | Pilih 'n' | Tool ditolak, model diberi tahu | |
| TOOL-07 | Iteration safety limit | Paksa loop >10 iterasi | Prompt peringatan di iterasi ke-10 | |
| TOOL-08 | Failure stop (3x gagal) | Paksa 3 tool gagal berturut-turut | Loop berhenti otomatis | |
| TOOL-09 | `max_iterations` cap | Set `max_iterations=100`, paksa loop | Berhenti di 100 iterasi | |

### 7.2 Keamanan — Plan Mode Allowlist (S1, S2, S4)

| ID | Skenario | Input | Expected Result | Status |
|----|----------|-------|-----------------|--------|
| SEC-01 | Newline injection (S1) | `ls\ntouch x.txt` | **Blocked**, file tidak dibuat | |
| SEC-02 | CR injection (S1) | `ls\rrm -rf x` | **Blocked** | |
| SEC-03 | NUL injection (S1) | `ls\x00rm -rf x` | **Blocked** | |
| SEC-04 | Semicolon | `ls; rm -rf x` | **Blocked** | |
| SEC-05 | Redirect | `echo hi > /tmp/f` | **Blocked**, file tidak dibuat | |
| SEC-06 | `&&` / `\|\|` | `ls && rm -rf x` | **Blocked** | |
| SEC-07 | Command substitution | `cat $(rm -rf x)` | **Blocked** | |
| SEC-08 | Backtick subst | `` cat `rm -rf x` `` | **Blocked** | |
| SEC-09 | Interpreter (S2) | `python3 -c '...'` | **Blocked** | |
| SEC-10 | Interpreter node | `node -e '...'` | **Blocked** | |
| SEC-11 | Interpreter lain | `go run`, `java`, `lua`, `ruby`, `php`, `perl` | **Blocked** | |
| SEC-12 | Wrapper sudo/doas | `sudo ls`, `doas ls` | **Blocked** | |
| SEC-13 | Mutating binary | `rm -rf x`, `touch x`, `chmod` | **Blocked** | |
| SEC-14 | find mutation (S4) | `find . -delete` / `-exec rm` | **Blocked** | |
| SEC-15 | sort/date mutation (S4) | `sort -o out.txt f` / `date -s` | **Blocked** | |
| SEC-16 | git mutation (S4) | `git reset --hard` / `git push` | **Blocked** | |
| SEC-17 | Pipe dengan mutating | `git status \| rm -rf x` | **Blocked** | |
| SEC-18 | xargs di pipe | `ls \| xargs rm` | **Blocked** | |
| SEC-19 | Read-only allowed | `ls`, `cat`, `grep -rn foo .` | **Allowed & berjalan** | |
| SEC-20 | Pipe read-only | `grep foo a.txt \| sort \| uniq` | **Allowed & berjalan** | |

### 7.3 Keamanan — write_file Sandbox (S3)

| ID | Skenario | Langkah | Expected Result | Status |
|----|----------|---------|-----------------|--------|
| SEC-21 | Write di dalam CWD | `write_file` path `ok.txt` | Berhasil, file dibuat | |
| SEC-22 | Symlink escape (S3) | Buat symlink ke luar, write via symlink | **Error**, file luar tidak dibuat | |
| SEC-23 | `..` escape | `write_file` path `../pwn.txt` | **Error**, file luar tidak dibuat | |
| SEC-24 | Output cap Plan | `cat /dev/zero` di Plan mode | Output di-cap, pesan "output capped" | |
| SEC-25 | Timeout Plan | `sleep 5` dengan timeout 1s | "timed out", proses terbunuh | |
| SEC-26 | Build mode real shell | Mode Build, `echo x; touch y` | Berjalan (shell asli, setelah konfirmasi) | |
| SEC-27 | Build timeout kill group | `sleep 60` di Build mode | "timed out", process group terbunuh | |
| SEC-28 | clone_repo Build-only | `clone_repo` di Plan mode | Pesan "Build mode" required | |
| SEC-29 | clone_repo non-https | `clone_repo git@...` di Build | Pesan error https required | |

---

## 8. Riwayat Chat & Database

| ID | Skenario | Langkah | Expected Result | Status |
|----|----------|---------|-----------------|--------|
| DB-01 | Simpan percakapan baru | Kirim prompt baru | DB row baru dibuat | |
| DB-02 | Undo normal pair | `undo_last_msg_pair` setelah Q&A | Menghapus 2 baris (user+assistant) | |
| DB-03 | Undo orphan user prompt | User prompt terakhir tanpa reply | Menghapus 1 baris saja | |
| DB-04 | Undo solo user | Hanya 1 user msg | Menghapus 1 baris | |
| DB-05 | Undo kosong | Percakapan kosong | Return 0, tidak error | |
| DB-06 | Token per model | Simpan pesan dengan model berbeda | `get_tokens_by_model` akurat per-model | |
| DB-07 | Conv token total | Simpan beberapa pesan | `get_conv_tokens` = total token percakapan | |
| DB-08 | Rename percakapan | `rename_conv` | Judul diperbarui | |
| DB-09 | Clear messages | `clear_conv_msgs` | Pesan dihapus, percakapan tetap ada | |
| DB-10 | Urutan pesan | Simpan 5 pesan | `get_msgs` urut ascending | |
| DB-11 | Limit pesan | `get_msgs(limit=2)` | Hanya 2 pesan terbaru | |
| DB-12 | DB ditutup saat exit | `/exit` | atexit handler menutup koneksi DB | |
| DB-13 | DB file lokasi | Cek `~/.config/termux-ai/` | `ai_history.db` ada di config dir | |

---

## 9. Skill System

| ID | Skenario | Langkah | Expected Result | Status |
|----|----------|---------|-----------------|--------|
| SK-01 | Valid skill name | `Skills.valid_name("code-review")` | `True` | |
| SK-02 | Invalid skill name | `Skills.valid_name("Bad Name!")`, `""`, `-lead`, `under_score` | `False` | |
| SK-03 | Parse frontmatter | Skill `.md` dengan YAML frontmatter | Meta & body ter-parse benar | |
| SK-04 | Parse tanpa frontmatter | Skill `.md` plain | Defaults: `mode=once`, name dari filename | |
| SK-05 | Description dengan colon | `description: time: 5pm` | Ter-parse penuh tanpa terpotong | |
| SK-06 | Seed default skills | `/skill seed` | 10 skill default dibuat (review, commit, python, dll.) | |
| SK-07 | Seed tidak overwrite | `/skill seed` kedua kali | Return empty, skill existing tidak ditimpa | |
| SK-08 | List skills | `/skill list` | Menampilkan skill tersedia | |
| SK-09 | Run skill | `/skill review` | Skill dijalankan pada prompt | |
| SK-10 | Toggle skill | `/skill toggle` | Mengubah status skill (session) | |
| SK-11 | Show skill detail | `/skill show review` | Menampilkan isi skill | |
| SK-12 | Edit skill | `/skill edit review` | Membuka editor untuk skill | |
| SK-13 | New skill | `/skill new myskill` | Membuat skill baru | |
| SK-14 | Skill direktori (pack) | Skill dalam folder dengan `SKILL.md` | Terdeteksi dan dapat di-list | |
| SK-15 | Hidden skill excluded | Skill dengan `disable-model-invocation: true` | Tidak muncul di catalog model | |
| SK-16 | Catalog format | `Skills.catalog()` | Berisi `<available-skills>`, `path=`, instruksi `read_file` | |
| SK-17 | Load skill tidak ada | `/skill load nope` | Return `(None, None)`, tidak crash | |
| SK-18 | Skill autoload | Set `skill_autoload=True` | Skill otomatis aktif per sesi | |

---

## 10. File Attachment

| ID | Skenario | Langkah | Expected Result | Status |
|----|----------|---------|-----------------|--------|
| ATT-01 | `@path` attachment | Prompt `lihat @a.py` | Konten a.py ter-attach sebagai "File:" | |
| ATT-02 | `./path` | Prompt `lihat ./b.txt` | Konten b.txt ter-attach | |
| ATT-03 | `~/path` tilde | Prompt `baca ~/notes.md` | Konten terbaca dari HOME | |
| ATT-04 | File tidak ada | Prompt `lihat @/nope.py` | Dibiarkan apa adanya, tidak ada "File:" | |
| ATT-05 | Attachment direktori | Prompt `review ./pkg` | Direktori di-scan, "Directory:" muncul | |
| ATT-06 | Skip ignore dirs | Direktori berisi `.git`/`node_modules` | File di dir tersebut dilewati | |
| ATT-07 | Attachment disabled | `attach_files=False` | `@path` dibiarkan apa adanya | |
| ATT-08 | File besar | Lampirkan file > `max_file_chars` | Konten di-truncate/potong | |
| ATT-09 | Banyak file sekaligus | Prompt dengan beberapa `@file` | Semua file ter-attach | |

---

## 11. fetch_url & Keamanan SSRF

| ID | Skenario | Langkah | Expected Result | Status |
|----|----------|---------|-----------------|--------|
| FU-01 | Fetch HTML | fetch URL http(s) publik | HTML di-strip ke teks bersih | |
| FU-02 | Strip tag & script | Fetch halaman dengan `<script>` | Script & tag HTML dihilangkan | |
| FU-03 | Entity unescape | Fetch HTML dengan `&amp;` | Tersaji sebagai `&` | |
| FU-04 | Reject non-http | fetch `ftp://` / `example.com` | Pesan "must start with http" | |
| FU-05 | Block private IP (SSRF) | fetch `http://127.0.0.1` | Pesan "SSRF" / diblokir | |
| FU-06 | Block localhost | fetch `http://localhost` | Pesan "SSRF" / diblokir | |
| FU-07 | Block private range | fetch `http://10.0.0.1` | Pesan "SSRF" / diblokir | |
| FU-08 | Allow private via env | Set `AI_FETCH_ALLOW_PRIVATE=1`, fetch local | Diperbolehkan | |
| FU-09 | GitHub token | Set `GITHUB_TOKEN`, fetch `api.github.com` | Header `Authorization: token ...` terkirim | |
| FU-10 | No token host lain | Set `GITHUB_TOKEN`, fetch host lain | Header Authorization **tidak** dikirim | |
| FU-11 | Output cap | Fetch halaman sangat besar | Output di-cap sesuai batas | |

---

## 12. Compact & Manajemen Konteks

| ID | Skenario | Langkah | Expected Result | Status |
|----|----------|---------|-----------------|--------|
| CMP-01 | Compact manual | `/compact` setelah beberapa pesan | Riwayat diganti summary; pesan terakhir dipertahankan | |
| CMP-02 | Compact butuh lebih banyak pesan | `/compact` dengan pesan sedikit | Return `False`, pesan "needs more messages" | |
| CMP-03 | Summary sebagai first msg | Setelah compact | Summary menjadi pesan pertama | |
| CMP-04 | Retain recent messages | Setelah compact | N pesan terakhir dipertahankan (`compact_keep_recent`) | |
| CMP-05 | Auto-compact | Set `auto_compact=True`, panjang percakapan | Compact otomatis saat ambang terlampaui | |
| CMP-06 | Context window budget | Set `context_window` kecil | Manajemen konteks menghormati batas | |
| CMP-07 | Iteration history budget | Loop tool yang panjang | Budget `iteration_history_budget` dihormati | |

---

## 13. Ollama Server Manager

| ID | Skenario | Langkah | Expected Result | Status |
|----|----------|---------|-----------------|--------|
| SRV-01 | `/server` (usage) | `/server` tanpa argumen | Menampilkan usage/cara pakai | |
| SRV-02 | `/server pull <model>` | `/server pull qwen2.5:3b` | Model ter-download via `ollama pull` | |
| SRV-03 | Pull binary hilang | ollama tidak terinstall, `/server pull` | Hint install, tidak crash | |
| SRV-04 | `/server models` | Server running | Menampilkan daftar model | |
| SRV-05 | Auto-start server | `/server models` saat server mati | `ollama serve` auto-start, lalu list | |
| SRV-06 | Refresh list setelah pull | Setelah pull sukses | `ollama list` di-refresh | |
| SRV-07 | Unknown action | `/server bogus` | Pesan "unknown action", tidak crash | |
| SRV-08 | PID file management | Cek `server.pid` saat running | PID file mencatat proses server | |

---

## 14. TTS, Copy, Share & Fitur Termux

| ID | Skenario | Langkah | Expected Result | Status |
|----|----------|---------|-----------------|--------|
| TX-01 | `/speak` TTS | `/speak` reply | `termux-tts-speak` membacakan reply | |
| TX-02 | TTS replies auto | Set `tts_replies=True` | Setiap reply otomatis dibacakan | |
| TX-03 | `/copy` clipboard | `/copy` | `termux-clipboard-set` dipanggil | |
| TX-04 | `/paste` clipboard | `/paste` | `termux-clipboard-get` dipanggil | |
| TX-05 | `/share` | `/share` | Dialog share Termux muncul | |
| TX-06 | Termux API tidak ada | Termux:API belum terinstall | Pesan error/hint yang jelas, tidak crash | |
| TX-07 | Non-Termux env | Jalankan di Linux desktop biasa | Fitur Termux degrade gracefully | |

---

## 15. Edge Cases & Robustness

| ID | Skenario | Langkah | Expected Result | Status |
|----|----------|---------|-----------------|--------|
| EG-01 | Prompt sangat panjang | Input prompt > context window | Ditangani: truncate/compact/error yang jelas | |
| EG-02 | Input biner/random bytes | Pipe byte non-UTF8 | Tidak crash; decode error ditangani | |
| EG-03 | Ctrl+C saat streaming | Kirim SIGINT mid-reply | Berhenti bersih, spinner berhenti, DB konsisten | |
| EG-04 | Ctrl+D (EOF) | Tekan Ctrl+D di REPL | Keluar dengan bersih | |
| EG-05 | Disk penuh saat save config | Tulis ke disk penuh | OSError ditangani, tidak crash | |
| EG-06 | Permission denied config dir | Config dir read-only | Pesan error, fallback memori | |
| EG-07 | Locale non-UTF8 | `LANG=C`, kirim unicode | Tidak crash (encoding fallback) | |
| EG-08 | Sesi paralel | Buka 2 instance sekaligus | DB locking ditangani, tidak korup | |
| EG-09 | Auto-resume | Restart app, sesi sebelumnya | `auto_resume=True` melanjutkan otomatis | |
| EG-10 | Repeat limit | Model mengulang tool sama 3x | `repeat_limit=3` memicu penghentian | |
| EG-11 | Re-read limit | Model re-read file 3x | `re_read_limit=3` memicu penghentian | |
| EG-12 | Gather-first | `gather_first=True` | Model mengumpulkan info dulu sebelum act | |
| EG-13 | Continue every N | Set `continue_every=10` | Konfirmasi lanjut muncul tiap 10 iterasi | |
| EG-14 | Max auto-continue | Set `max_auto_continue=2` | Auto-continue berhenti setelah 2x | |
| EG-15 | Concurrent tool calls | Model usulkan beberapa tool sekaligus | Semua dievaluasi/dikonfirmasi batch | |
| EG-16 | Tool argumen invalid | Model kirim tool dengan args hilang | Error ditangani, tidak crash | |
| EG-17 | Empty stdin + no arg | `echo -n \| ./ai` | Masuk mode interaktif atau handle gracefully | |
| EG-18 | README/HELP fallback | `./ai --help` | Menampilkan help text | |

---

## Ringkasan Eksekusi

| Kategori | Jumlah TC | Pass | Fail | Blocked |
|----------|-----------|------|------|---------|
| 1. Instalasi & Build | 6 | | | |
| 2. CLI & Argumen | 10 | | | |
| 3. Backend & Koneksi | 12 | | | |
| 4. Konfigurasi | 10 | | | |
| 5. Slash Commands | 43 | | | |
| 6. Streaming & UI | 11 | | | |
| 7. Tools & Keamanan | 29 | | | |
| 8. Riwayat & Database | 13 | | | |
| 9. Skill System | 18 | | | |
| 10. File Attachment | 9 | | | |
| 11. fetch_url & SSRF | 11 | | | |
| 12. Compact & Konteks | 7 | | | |
| 13. Ollama Server | 8 | | | |
| 14. TTS/Copy/Share | 7 | | | |
| 15. Edge Cases | 18 | | | |
| **TOTAL** | **212** | | | |

---

## Catatan Lingkungan Pengujian

- **OS**: Android (Termux)
- **Python**: 3.x (stdlib only, zero-dependency)
- **Backends diperlukan**: Ollama (lokal), minimal satu cloud API (OpenAI/Anthropic/Groq/OpenRouter) dengan key valid
- **Termux:API**: untuk fitur TTS/clipboard/share
- **Akses jaringan**: untuk fetch_url & cloud backends
- **Mode TTY vs non-TTY**: beberapa TC memerlukan terminal interaktif (spinner, REPL)

> Untuk automasi regresi yang sudah ada, lihat `tests/test_security.py` (Plan-mode allowlist, sandbox write, executor) dan `tests/test_units.py` (Database, attachment, compact, skills, server, fetch_url, spinner).
