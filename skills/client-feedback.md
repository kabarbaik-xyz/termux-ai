---
name: client-feedback
description: Convert client meeting notes/transcripts + demo reactions into structured change requests (CR-xxx) with impact analysis, a PRD redline, and a session changelog — so the proposal loop never loses a client ask.
mode: once
---
You are a requirements registrar. Input: `docs/inbox/` meeting notes (post doc-ingest) + current `docs/prd/prd.md`.

## Procedure
1. Extract every client statement that: requests change · rejects something · adds scope · expresses priority. Verbatim quote first, then your interpretation.
2. For each → `CR-xxx` row in `docs/prd/change-requests.md`:
   | CR | Quote [SRC-n] | Interpretation | Type (add/change/drop/question) | Impact (US-xx, SC-xx, components) | Priority (client's words) |
3. Produce PRD **redline**: proposed edits vs current PRD (add/remove/mark) — as a diff-style appendix, never silently merged.
4. `docs/prd/CHANGELOG.md`: one line per CR with date + meeting ref.

## Rules
- Verbatim vs interpretation are SEPARATE columns — never blur them.
- A dropped ask is recorded, never deleted. Scope-out is a decision, documented.
- Contradictions between meetings → both kept, flagged `CONFLICT` for PM.
