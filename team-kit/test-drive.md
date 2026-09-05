# Test Drive — termux-ai through the whole flow
Reproduce the KirimKilat samples live. ~30 min. Run in a scratch project dir.

## 0. Setup (once)
```bash
mkdir -p kirimkilat-test/docs/inbox && cd kirimkilat-test
cp -r <path-to>/team-kit/skills/* ~/.config/termux-ai/skills/   # install house skills
cat > docs/inbox/brief.md <<'BRIEF'
Dari: Budi Santoso <budi@kirimkilat.co.id>
Subjek: Kebutuhan sistem tracking & dashboard

Kami jasa kurir dengan 20 agen di 3 kota. Saat ini operasional pakai Excel,
pelanggan sering telepon untuk tanya posisi paket — kami butuh:
1. Pelanggan bisa lacak paket dari website pakai nomor resi
2. Notifikasi ke pelanggan saat status berubah
3. Dashboard untuk agen update status paket
4. Laporan bulanan sederhana untuk manajemen
Target live sebelum Lebaran (Desember). Budget terbatas, yang penting
fitur 1 dulu jalan. Notifikasi WhatsApp kalau bisa, email dulu tidak apa-apa.
BRIEF
```
Every command below runs ONE-SHOT in this dir. (Interactive alternative: start `ai` here once, then use `/skill <name>` per phase — same prompts.)

## 1. doc-ingest → normalized source + index
```
ai "Process every file in docs/inbox/ into docs/discovery/: normalized markdown with an SRC header (id, file, received date) and an index.md table. Flag anything ambiguous under Open questions." --skill doc-ingest --tools on
```
✓ Check: `docs/discovery/brief.md` has `<!-- SRC: id=SRC-1 ... -->`; `docs/discovery/index.md` lists it.

## 2. discovery → discovery.md
```
ai "Read docs/discovery/ sources and produce docs/discovery/discovery.md per the skill: goals, stakeholders, pains mapped to goals, scope IN/OUT, assumptions marked ASSUMED, numbered OPEN QUESTIONS with who-to-ask, glossary. Cite [SRC-n] everywhere. Respond in English, keep client quotes verbatim in Indonesian." --skill discovery --tools on
```
✓ Check: OPEN QUESTIONS present with ≥4 rows (incl. WhatsApp budget + resi format); every claim cites [SRC-1].

## 3. BRD + PRD
```
ai "From docs/discovery/discovery.md produce docs/brd/brd.md using the BRD template (BO-x objectives with success metrics + sources, pains, scope, constraints)." --tools on
```
```
ai "From docs/brd/brd.md produce docs/prd/prd.md using the PRD template: user stories US-101+ with given/when/then acceptance criteria, priorities, screen column SC-xx (placeholder names ok)." --tools on
```
✓ Check: US-101 = track by resi (P0) with ≥3 testable ACs; header cites upstream brd v1.

## 4. UX Spec
```
ai "Produce docs/ux-spec/ux-spec.md for the tracking core from docs/prd/prd.md: screen inventory SC-01.. mapping US-IDs, one Mermaid flow per journey (including the unknown-resi off-ramp), the full 5-states matrix per screen, component mapping with new components registered." --tools on
```
✓ Check: states matrix has an Error cell for SC-02 saying inline retry (this drives everything downstream).

## 5. Prototype (webapp) — BUILD mode, needs Node on this machine
```
ai "MODE prototype. Scaffold a Nuxt app implementing every screen in docs/ux-spec/ux-spec.md with ALL states from the matrix, tokens-only styling (create design/tokens.json first), seeded realistic parcels (KK-XXXXXX format), mobile-first. Then write docs/prototype/handoff.md listing what is real vs fake." --skill webapp --tools on --process off
```
✓ Check: pages carry `<!-- SC-xx · US-xxx -->` comments; the unknown-resi error state works in the browser.

## 6. client-feedback (paste a meeting note)
Put this in docs/inbox/mtg2.md, then:
```
ai "Process docs/inbox/mtg2.md against docs/prd/prd.md per the skill: CR table (verbatim quote vs interpretation, type, impact on US/SC, priority), PRD redline appendix, changelog line." --skill client-feedback --tools on
```
✓ Check: CR rows carry verbatim ID quotes; no silent merge — redline only.
Sample mtg2.md content to paste:
```
Klien: email cukup untuk sekarang, WhatsApp nanti saja.
Laporan: kalau bisa download CSV sudah cukup.
Tanya: kalau Lebaran telat gimana?
```

## 7. proposal
```
ai "Draft docs/proposal/proposal-v1.md from docs/prd/ (latest), docs/prototype/handoff.md and docs/discovery/: exec summary, understanding with [SRC] citations, solution overview with Mermaid, RFP compliance matrix (the 4 client asks), phased delivery with range estimates tied to assumptions, risks with triggers, [PRICING — HUMAN OWNED] placeholder." --skill proposal --tools on
```
✓ Check: compliance matrix honestly marks WA as deferred; pricing is a placeholder.

## 8. TSD/SAD
```
ai "From the agreed proposal + prd produce docs/tsd/tsd.md and docs/sad/sad.md per the skill: unified API envelope + endpoint table (API-xxx), data model, container view, ADR-001/ADR-002 with reversal triggers, and the doc-sync impact map." --skill tsd-sad --tools on
```
✓ Check: one envelope for Go+Python; ADRs cite [SRC-1]/CR-001.

## 9. epic-breakdown
```
ai "Break docs/prd + docs/tsd into docs/plan/backlog.md: epics E-01.., stories US-xxx (AC refs, SC, components, deps, estimate S/M/L, role), and the traceability matrix (PRD req → US → SC → component → test). List any requirement without a story as a loud gap." --skill epic-breakdown --tools on
```
✓ Check: traceability table complete; no orphan US without SC.

## 10. (optional, needs FIGMA_TOKEN + a real file) figma-tokens
```
ai "Sync Figma variables from file <FILE_KEY> into design/tokens.json per the figma-tokens skill; output the diff table for a PR description." --skill figma-tokens --tools on
```

## Scorecard
Phase passes when its ✓-check holds AND the IDs chain: SRC-1 → BO-1 → US-101 → SC-01/02 → component comment → spec file. Any break in the chain = skill gap → note it for the retro (governance.md).
