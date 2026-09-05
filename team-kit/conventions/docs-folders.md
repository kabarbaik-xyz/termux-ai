# Docs Folder Convention
```
docs/
  inbox/            # raw incoming (anything, any format) — doc-ingest consumes
  discovery/        # normalized sources + discovery.md + index.md
  brd/  prd/        # versioned docs + change-requests.md + CHANGELOG.md
  prototype/        # preview URLs, handoff notes
  proposal/         # proposal-vN.md
  tsd/  sad/        # + ADRs (ADR-xxx.md, one per decision)
  plan/             # backlog.md (epics/stories) + traceability matrix
```
Rules: version in the DOC header comment, not the filename · superseded versions move to `archive/` · every file's header lists `sources=[SRC-n]` and `upstream=` · inbox is emptied by ingestion, never edited by hand.
