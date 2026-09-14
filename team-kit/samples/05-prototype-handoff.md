# Prototype Handoff — v1 (pre-client-meeting)
Preview: https://kirimkilat-proto.netlify.app (PR deploy, free tier)
## What's REAL
All 5 SC screens per UX Spec v1 · full states included (empty/loading/error/populated — demo these explicitly) · tokens from design-tokens.json (Enterprise Light, client accent) · one HTML per screen + shared styles.css · inline SVG icon family · SVG bar chart from chart palette · **auto-adaptive desktop AND mobile** (open on your phone first).
## What's FAKE
Data: 12 seeded parcels (realistic resi format KK-XXXXXX) · auth: any agent code logs in · email: logged to console, not sent · status store is in-memory JS.
## QA (release-blocking ugly test)
Passed at 360 / 768 / 1024 / 1280 (nav drawer, table scroll wrapper, single-column dashboard, no horizontal overflow) · every interactive element has hover + 2px focus ring + disabled · contrast ≥ 4.5:1 body · numbers tabular-nums · charts only palette colors · no default-browser styling anywhere.
## Known gaps
No i18n (ID copy hardcoded) · no real API (mocked per TSD envelope shape) · monthly-report chart static (no drill-down).
## Meeting script
1. Phone demo SC-01→02 (the win) · 2. show error state on purpose · 3. agent flow SC-03→04 + status-update drawer · 4. capture every reaction → docs/inbox/.