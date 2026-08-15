# ══ termux_ai.server ══ (fragment; merged by build.py)
class ServerManager:
    @staticmethod
    def _pid_alive(pid_file):
        """True if the PID recorded in pid_file is a live process."""
        try:
            pid = int(pid_file.read_text().strip().split(",")[0])
            os.kill(pid, 0)
            return True
        except (OSError, ValueError):
            return False

    @staticmethod
    def _installed():
        """True if the `ollama` binary is on PATH."""
        return shutil.which("ollama") is not None

    @staticmethod
    def _require_ollama():
        """Print an install hint and return False when ollama is missing."""
        if not ServerManager._installed():
            hint = ollama_hint()
            if IS_TERMUX:
                hint += " [ollama-backend-vulkan]"
            print(f"{C.RED}ollama is not installed. Install it with: {hint}{C.RESET}")
            return False
        return True

    @staticmethod
    def _ensure_running():
        """Start the local server if it isn't up. Returns True when it is."""
        if PID_FILE.exists() and ServerManager._pid_alive(PID_FILE):
            return True
        ServerManager.manage("start")
        return PID_FILE.exists() and ServerManager._pid_alive(PID_FILE)

    @staticmethod
    def _run(argv):
        """Run an ollama CLI subcommand, inheriting the terminal so progress bars render."""
        try:
            subprocess.run(argv)
        except KeyboardInterrupt:
            print(f"{C.YELLOW}Interrupted.{C.RESET}")
        except Exception as e:
            print(f"{C.RED}Failed to run {' '.join(argv)}: {e}{C.RESET}")

    @staticmethod
    def pull(model):
        """ollama pull <model> in the foreground (progress bar shown). Returns
        the model name on success, else None."""
        if not ServerManager._require_ollama():
            return None
        if not ServerManager._ensure_running():
            return None
        print(f"{C.CYAN}Pulling {C.BOLD}{model}{C.RESET}{C.CYAN} ... (keep the screen on; large models take a while){C.RESET}")
        try:
            rc = subprocess.run(["ollama", "pull", model]).returncode
        except KeyboardInterrupt:
            print(f"{C.YELLOW}Interrupted.{C.RESET}")
            return None
        if rc == 0:
            ServerManager.models()
            return model
        print(f"{C.RED}Pull failed (exit {rc}). Check the model name (e.g. qwen2.5:3b) and your network.{C.RESET}")
        return None

    @staticmethod
    def models():
        """List locally installed models."""
        if not ServerManager._require_ollama(): return
        ServerManager._ensure_running()
        print(f"{C.BOLD}Installed models:{C.RESET}")
        ServerManager._run(["ollama", "list"])

    @staticmethod
    def search(query):
        """Search the Ollama registry."""
        if not ServerManager._require_ollama(): return
        ServerManager._ensure_running()
        print(f"{C.BOLD}Registry results for '{query}':{C.RESET}")
        ServerManager._run(["ollama", "search", query])

    @staticmethod
    def show(model):
        """Show details for a model."""
        if not ServerManager._require_ollama(): return
        ServerManager._ensure_running()
        ServerManager._run(["ollama", "show", model])

    @staticmethod
    def rm(model):
        """Remove a model (frees its storage)."""
        if not ServerManager._require_ollama(): return
        ServerManager._ensure_running()
        ServerManager._run(["ollama", "rm", model])
        ServerManager.models()

    @staticmethod
    def manage(action, engine="ollama"):
        if action == "start":
            if PID_FILE.exists():
                if ServerManager._pid_alive(PID_FILE):
                    print(f"{C.YELLOW}Server may already be running (PID file present). Use '/server stop' first.{C.RESET}"); return
                PID_FILE.unlink()  # stale PID file from a crashed/killed server
            if engine == "ollama": cmd = ["ollama", "serve"]
            else: print(f"{C.RED}Invalid engine. Use 'ollama'.{C.RESET}"); return
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                PID_FILE.write_text(f"{proc.pid},{engine}")
                _secure_file(PID_FILE)
                print(f"{C.GREEN}Started {engine} server in background (PID: {proc.pid}).{C.RESET}")
            except Exception as e: print(f"{C.RED}Failed to start server: {e}{C.RESET}")
        elif action == "stop":
            if not PID_FILE.exists(): print(f"{C.YELLOW}No running server process found.{C.RESET}"); return
            try:
                content = PID_FILE.read_text().strip().split(",")
                pid, eng = int(content[0]), content[1]
                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass  # already dead
                print(f"{C.GREEN}Stopped background {eng} server (PID: {pid}).{C.RESET}")
            except Exception as e: print(f"{C.RED}Error stopping server: {e}{C.RESET}")
            finally:
                if PID_FILE.exists(): PID_FILE.unlink()
        elif action == "status":
            if not PID_FILE.exists(): print(f"{C.YELLOW}Local server status: Stopped{C.RESET}"); return
            if not ServerManager._pid_alive(PID_FILE):
                print(f"{C.RED}Local server status: Dead. Cleaning PID file.{C.RESET}")
                PID_FILE.unlink(); return
            content = PID_FILE.read_text().strip().split(",")
            print(f"{C.GREEN}Local server status: Running ({content[1]}, PID: {content[0]}){C.RESET}")
