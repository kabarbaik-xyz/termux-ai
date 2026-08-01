# ══ termux_ai.termux_api ══ (fragment; merged by build.py)
class TermuxAPI:
    @staticmethod
    def available(cmd): return shutil.which(cmd) is not None

    @staticmethod
    def speak(text):
        if TermuxAPI.available("termux-tts-speak"):
            try: subprocess.run(["termux-tts-speak", text[:1000]], timeout=15); return True
            except Exception: return False
        return False

    @staticmethod
    def copy(text):
        if TermuxAPI.available("termux-clipboard-set"):
            try: subprocess.run(["termux-clipboard-set"], input=text, text=True, timeout=5); return True
            except Exception: return False
        return False

    @staticmethod
    def paste():
        if TermuxAPI.available("termux-clipboard-get"):
            try:
                r = subprocess.run(["termux-clipboard-get"], capture_output=True, text=True, timeout=5)
                return r.stdout
            except Exception: return None
        return None

    @staticmethod
    def share(text):
        if TermuxAPI.available("termux-share"):
            try: subprocess.run(["termux-share", "-a", "send"], input=text, text=True, timeout=10); return True
            except Exception: return False
        return False

    @staticmethod
    def status():
        return {
            "tts": TermuxAPI.available("termux-tts-speak"),
            "clipboard": TermuxAPI.available("termux-clipboard-set"),
            "share": TermuxAPI.available("termux-share"),
        }
