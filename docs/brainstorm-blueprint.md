# Blueprint: F&B Recipe & Prime Cost Management SaaS ("RecipeCosting")

**Goal:** A fast, multi-tenant SaaS for F&B owners to compute exact menu item prime costs (ingredients with yield loss, sub-recipes, batch scaling, direct labor, gas/utilities, and packaging) to set profitable retail prices.

## Context
- **Target Audience:** Multi-tenant SaaS for independent restaurant, cafe, bar, and cloud kitchen owners.
- **Key Pain Point:** Inaccurate menu pricing due to ignoring yield loss (trimming/shrinkage), batch preparation sub-recipes, overheads (labor/gas), and supplier price fluctuations.
- **Constraints & Deployment:** Fast and lightweight stack suited for Zeabur deployment (Next.js / TypeScript / PostgreSQL / Drizzle ORM).
- **Out of Scope for v1:** Inventory POS integration, live stock tracking/deduction, automated invoice OCR scanning.

## Core Costing Engine Formulas
1. **Raw Ingredient Cost:** `(Purchase Price / Purchase Unit Qty) * (1 / Yield Factor %) * Recipe Qty`
2. **Sub-Recipe (Prep Item) Cost per Unit:** `Total Batch Prep Cost / Net Batch Yield Qty`
3. **Overhead Allocation:** `(Labor Rate/Min * Prep Mins) + (Utility Rate/Min * Cooking Mins) + Packaging Cost`
4. **Base Cost (COGS / Portion):** `(Sum of Raw + Sub-recipe Ingredients + Overheads) / Batch Portion Count`
5. **Target Retail Price:** `Base Cost / (1 - Target Margin %)`

## Structure (expand me)
- **1. Multi-Tenant & Auth Architecture** — Tenant (Business/Store) isolation, user roles (Owner, Chef, Manager), Supabase Auth or NextAuth.
- **2. Master Data Management (Items & Units)** — Ingredients, raw materials, supplier price history, unit conversions (e.g., 1 kg = 1000 g, 1 bottle = 750 ml).
- **3. Yield Loss & Conversion Engine** — Waste/trimming percentage per item, net vs gross weight calculation.
- **4. Overheads & Resources Master** — Hourly labor rates, gas/electric burn rates per minute, fixed packaging items.
- **5. Sub-Recipe & Batch Engine** — Nested prep recipes (e.g., Syrups, Sauces, Stocks) used as ingredients in final menu items.
- **6. Menu Recipe Builder & Scaling** — Batch-to-portion scaling, visual ingredient builder, real-time COGS calculation, margin analyzer.
- **7. Pricing & Profitability Dashboard** — Target margin simulator, food cost percentage alerts, price suggestion matrix.
- **8. Deployment & Infra (Zeabur)** — Next.js Standalone Docker build, Zeabur PostgreSQL database, environment variables, CI/CD setup.

## Key Decisions
- **Framework:** Next.js (App Router, Server Actions, Tailwind CSS, Shadcn UI) for fast fullstack execution and light serverless/container footprint.
- **Database & ORM:** PostgreSQL on Zeabur with Drizzle ORM for lightweight, zero-overhead type-safe query performance.
- **Multi-Tenancy Strategy:** Single database with `tenant_id` foreign keys and strict Row-Level Security / middleware checks.
- **Sub-Recipe Recursion:** Support up to 3 levels of nested prep recipes to prevent circular dependencies while keeping calculations simple.
- **Yield Loss Calculation:** Store `yield_percentage` (0-100%) on the ingredient master, overridable at the specific recipe line-item level.

## Data Schema Summary
- `tenants` (id, name, currency, created_at)
- `units` (id, tenant_id, name, code, symbol, type: mass/volume/count)
- `unit_conversions` (from_unit_id, to_unit_id, factor)
- `items` (id, tenant_id, name, category, purchase_unit_id, default_price, yield_percentage)
- `resources` (id, tenant_id, name, type: labor/gas/electric/packaging, cost_per_unit, unit_name)
- `recipes` (id, tenant_id, name, category, is_sub_recipe, batch_yield_qty, batch_unit_id, portion_count, prep_time_mins, cook_time_mins)
- `recipe_ingredients` (recipe_id, item_id / child_recipe_id, quantity, unit_id, custom_yield_percentage)
- `recipe_resources` (recipe_id, resource_id, quantity)

## Open Questions
- Should multi-currency support be built into v1 or kept single-currency per tenant?
- Do users need supplier price history logs to track inflation over time in v1?

## Hand-off
Paste this to the cloud model: "Expand docs/brainstorm-blueprint.md into a full Software Architecture Document (SAD) and step-by-step Implementation Plan for a Next.js + PostgreSQL app on Zeabur. Keep the decisions and structure; write the complete code schemas and API specifications."
