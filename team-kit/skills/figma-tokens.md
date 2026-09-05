---
name: figma-tokens
description: Sync Figma variables ↔ design/tokens.json via the FREE REST API (personal access token, Starter plan — no MCP seats) and open a diff PR. Keeps the token file machine-honest.
mode: once
---
1. Get file key from the Figma URL; call REST `GET /v1/files/:key/variables` with the team token (env FIGMA_TOKEN; never committed).
2. Map variables → tokens.json paths (naming convention = identity; mismatches are REPORTED, not auto-renamed).
3. Diff vs current tokens.json: additions/changes/renames/removed — each listed with Figma variable id.
4. Write updated tokens.json (preserve `ref` ids) + regenerate the theme file ([Tailwind SLOT 0.3]).
5. Output the change table for the PR description; flag any component code now referencing removed tokens (grep).
Rules: destructive token removal requires PM sign-off line in the PR. No invented values — only what Figma holds.
