<!-- DOC: ux-spec | feature=<name> | version=v__ | date=__ | sources=[PRD v__] | upstream=docs/prd/prd.md -->
# UX Spec — <Project / Feature>
Language: <EN/ID — match client>

## 1. Scope & Assumptions (one paragraph — PRD version; Mode chosen: PRODUCT-ALIGNED [Power BI / Looker Studio / Tableau / Shopify / WordPress…] or CUSTOM with direction [Enterprise Light / restrained Glass / official design-system]; one-line rationale; assumptions where PRD was silent)
## 2. User Flows (one Mermaid per primary journey — decision points + error/edge paths, not just happy path)
## 3. Screen Inventory
| Screen | Purpose | PRD requirement(s) | Key components | Priority |
|--------|---------|--------------------|----------------|----------|
|        |         |                    |                | must/should/could |
## 4. Per-Screen Wireframe Description (regions top-to-bottom, named from the component vocabulary — Topbar/Sidebar/Slicer bar/KPI scorecard/Data table/Card/Form panel/Tabs/Drawer/Dialog/Toast/Skeleton/Empty state; empty/loading/error/populated states per screen; product's native components when Mode A)
## 5. Visual System (Mode A: the product theme being mirrored — chrome, color language, typography, density. Mode B: type-hierarchy map, color discipline, 8pt rhythm/density, elevation, component states, icon family, data-viz hygiene; desktop AND mobile behavior of each screen)
## 6. Design Tokens (uses existing design-tokens.json — do not restate; only note deviations or the backfill from the Enterprise-Light recipe)
## 7. Assumptions & Decisions (3–7 numbered — what was assumed, the decision, one-line rationale; always include Mode/direction + any token instantiation; no open questions)
Golden rules: no screen without a PRD requirement · diagrams over prose · spec only, no code · desktop AND mobile are both first-class.
