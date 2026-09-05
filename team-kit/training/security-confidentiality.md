# Training 5.4 — Security & Confidentiality (DevOps owns, all attend)
1. Secrets: never in prompts/repos; env-based; the AI never "needs" a real key to write code.
2. Injection: treat AI-suggested shell/SQL/eval as untrusted input; review data flows, not just syntax.
3. Licensing: generated code inherits license obligations — vendored snippets flagged in PRs; no wholesale copying from tutorials.
4. Client-code-to-cloud policy: classification tiers; which tier may touch cloud models; sensitive tier = local models (termux-ai local mode) or no-AI. Signed by PM + DevOps, posted in AGENTS files.
