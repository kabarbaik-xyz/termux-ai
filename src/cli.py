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
                "  cat error.log | ai \"explain\"    # pipe stdin into the prompt\n"),
    )
    parser.add_argument("prompt", nargs="?", default=None,
                        help="one-shot prompt; omit to start the interactive REPL")
    parser.add_argument("-m", "--model", default=None, metavar="MODEL",
                        help="override the active model for this run")
    parser.add_argument("-c", "--command", default=None, metavar="TASK",
                        help="generate a shell command for TASK (confirm & run in a TTY; print only when piped)")
    parser.add_argument("-j", "--json", action="store_true",
                        help="ask the model to answer with JSON only")
    args = parser.parse_args()

    app = App()
    app._override_model(args.model)

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
