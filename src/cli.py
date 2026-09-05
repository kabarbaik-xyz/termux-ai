# ══ termux_ai.cli ══ (fragment; merged by build.py)
def main():
    import argparse
    parser = argparse.ArgumentParser(
        prog="ai",
        description="Termux AI CLI \u2014 interactive chat, one-shot, and command generator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=("examples:\n"
                "  ai                              # interactive REPL\n"
                "  ai \"explain quicksort\"          # one-shot question\n"
                "  ai -m gpt-4o \"what is TCP?\"     # override model\n"
                "  ai -c \"compress folder to tar\"  # generate a shell command\n"
                "  ai -j \"list 3 fruits\"           # ask for JSON\n"
                "  cat error.log | ai \"explain\"    # pipe stdin into the prompt\n"
                "  ai \"build a simple website\" --skill fullstack --tools on --process off\n"),
    )
    parser.add_argument("prompt", nargs="?", default=None,
                        help="one-shot prompt; omit to start the interactive REPL")
    parser.add_argument("-m", "--model", default=None, metavar="MODEL",
                        help="override the active model for this run")
    parser.add_argument("-c", "--command", default=None, metavar="TASK",
                        help="generate a shell command for TASK (confirm & run in a TTY; print only when piped)")
    parser.add_argument("-j", "--json", action="store_true",
                        help="ask the model to answer with JSON only")
    parser.add_argument("-C", "--continue", dest="resume_continue", action="store_true",
                        help="resume this project's last session before the REPL")
    parser.add_argument("-S", "--session", dest="session_name", default=None, metavar="NAME",
                        help="create-or-resume a named session (e.g. ai -S webproject)")
    parser.add_argument("--new", dest="resume_new", action="store_true",
                        help="start a fresh session (do not resume)")
    parser.add_argument("-l", "--load", dest="load_cid", default=None, metavar="ID",
                        help="load a saved session by id before the REPL")
    parser.add_argument("-s", "--skill", default=None, metavar="NAME[,NAME...]",
                        help="activate comma-separated skill(s) for this run, e.g. --skill fullstack,pentest")
    parser.add_argument("--tools", choices=["on", "off"], default=None,
                        help="force Build (on) or Plan/off mode for this run (default: config tools_enabled)")
    parser.add_argument("--process", choices=["on", "off", "auto"], default=None,
                        help="override tool-call display for this run: on=compact, off=full, auto")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="auto-approve tool actions (write_file/commands) in non-interactive runs; same as AI_APPROVE=1")
    args = parser.parse_args()

    app = App()
    app._override_model(args.model)
    if args.yes:
        app._auto_approve_all = True
    # Per-run overrides (in-memory only; use /config set to persist).
    if args.tools:
        app.cfg.set("tools_enabled", args.tools == "on", save=False)
    if args.process:
        app.cfg.set("compact_process", args.process, save=False)
    if args.skill is not None:
        if not app._apply_skill_args(args.skill):   # missing skill -> warn+confirm; decline exits
            sys.exit(0)
    if args.load_cid:
        app._resume_mode = "load"; app._resume_arg = args.load_cid
    elif args.session_name:
        app._resume_mode = "session"; app._resume_arg = args.session_name
    elif args.resume_new: app._resume_mode = "new"
    elif args.resume_continue: app._resume_mode = "continue"

    stdin_data = app._read_stdin()

    if args.command:
        sys.exit(app.command_gen(args.command, stdin_data))
    if args.json:
        app.json_oneshot(args.prompt, stdin_data)
        sys.exit(1 if app._errored else 0)
    if args.prompt is not None or stdin_data is not None:
        app.oneshot(args.prompt or "", stdin_data)
        sys.exit(1 if app._errored else 0)
    # No prompt, no stdin: start the interactive REPL (needs a TTY).
    if not IS_TTY:
        parser.print_help()
        sys.exit(0)
    app.main_loop()


if __name__ == "__main__":
    main()
