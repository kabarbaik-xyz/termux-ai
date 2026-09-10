# Bakmi GM BI Dashboard — Prototype

## How to open
Open `prototype/index.html` in any modern desktop browser (Chrome, Edge, Firefox). No server, build step, or internet connection is required.

## Screens built
- **Login / SSO Entry** (`login.html`) — SSO button, loading spinner, error state, no-permission state. Demo links to cycle through states.
- **Sales Report** (`sales.html`) — KPI cards, stacked bar by category, area→store drill-down table. Includes loading, empty, error, and populated states with demo buttons.
- **Member & Profile Report** (`member.html`) — Total members, new activations, tier distribution, gender breakdown, conversion rate by area. All states included.
- **Engagement Report** (`engagement.html`) — Channel tabs (Banner / Push / Both), metrics grid, campaign drill-down table. All states included.
- **Loyalty Point Report** (`loyalty-point.html`) — KPI cards, donut chart (top-up source), tier balance bar, expired points table with "definition pending" flag. All states included.
- **Loyalty E-Voucher Report** (`loyalty-voucher.html`) — KPI cards, cost vs sales comparison, status breakdown, voucher detail drill-down with labeled cost basis. All states included.
- **Purchase Frequency & Avg Spending** (`sales-frequency.html`) — Backlog screen. Frequency histogram, avg spending panel, segment table. All states included.
- **Avg Point per E-Voucher** (`avg-point-voucher.html`) — Backlog screen. Redeemed vs used comparison, tier breakdown. All states included.

## Styling
All styling is derived from `design-tokens.json` via CSS custom properties in `styles.css`. No invented colors, fonts, or spacing.

## Interactivity
Vanilla JS in `app.js` handles:
- Navigation between screens
- State toggling (loading / empty / error / populated)
- Tab switching on Engagement Report
- Simulated loading delays

## Open questions deliberately left unresolved
- **OQ-3 (TADA attribution):** Sales from Conversion in Engagement is labeled "illustrative / not attributed" rather than wired to a real attribution source.
- **OQ-5 (Pending Member definition):** Registered/Pending split in expired points carries the inline "definition pending" flag.
- **OQ-6 (Voucher cost basis):** Cost Ratio is labeled "face value basis" with a note that it is configurable.
- **OQ-9 (Data refresh cadence):** "Data as of" timestamps are static placeholders; actual cadence is TBD in Phase 0.
- **OQ-10 (Platform):** Prototype is a static web build; Nuxt vs BI platform decision is deferred.
- **Mobile responsiveness (gap #6):** Prototype is desktop-first; responsive breakpoints are minimal and not a commitment.
