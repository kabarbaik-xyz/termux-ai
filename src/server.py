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
