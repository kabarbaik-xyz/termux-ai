---
name: commit
description: Write a Conventional Commit message from the current git changes. Use when the user wants to commit.
mode: once
---
Look at the current git changes (`git diff --cached`, or `git diff` / `git status` if nothing is staged).

Write a Conventional Commit message: `type(scope): summary` on the first line, then a short body explaining the why. Types: feat, fix, docs, refactor, test, chore, perf.

Output ONLY the commit message, then suggest the `git commit -m "..."` command. Do not commit yourself.
