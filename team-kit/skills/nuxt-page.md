---
name: nuxt-page
description: House recipe for Nuxt pages/routes — SSR data rules, meta/SEO, the full states discipline, navigation and guards. FE standard for every route.
mode: session
---
Prereq: US-xx + SC-xx with UX Spec entry.
1. `pages/…` route matching UX Spec flow; name the route in a top comment `<!-- SC-xx · US-xxx -->`.
2. Data: `useFetch`/`useAsyncData` (SSR-safe) against the unified envelope; handle `error.code` from the registry — map to the page's error state, never swallow.
3. All 5 states rendered (skeleton loaders for loading; actionable empty state with next step, never blank).
4. `useHead`/meta: title, description, OG — from PRD language, not invented.
5. Guards: auth/no-permission per PRD; redirect target per UX Spec flow.
6. Mobile-first mark-up; test the flow at 375px in the Playwright spec.
7. Links/CTAs match the UX Spec flow diagram — no invented navigation.
