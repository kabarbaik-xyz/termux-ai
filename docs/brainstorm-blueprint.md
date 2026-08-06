# Blueprint: F&B Recipe & Prime Cost Management SaaS ("RecipeCosting")

**Goal:** A fast, multi-tenant SaaS for F&B owners to compute exact menu item prime costs (ingredients with yield loss, sub-recipes, batch scaling, direct labor, gas/utilities, and packaging) to set profitable retail prices.

## Context
- **Target Audience:** Multi-tenant SaaS for independent restaurant, cafe, bar, and cloud kitchen owners.
- **Key Pain Point:** Inaccurate menu pricing due to ignoring yield loss (trimming/shrinkage), batch preparation sub-recipes, overheads (labor/gas), and supplier price fluctuations.
- **Constraints & Deployment:** Fast and lightweight stack suited for Zeabur deployment (Next.js App Router / TypeScript / PostgreSQL / Drizzle ORM / Tailwind CSS + Shadcn UI).
- **Out of Scope for v1:** Inventory POS integration, live stock tracking/deduction, automated invoice OCR scanning.

## Core Costing Engine Formulas
1. **Raw Ingredient Effective Cost:** `(Purchase Price / Purchase Unit Qty) * (1 / (Yield Factor % / 100)) * Recipe Qty`
2. **Sub-Recipe (Prep Item) Cost per Unit:** `Total Batch Prep Cost / Net Batch Yield Qty`
3. **Overhead Allocation:** `(Labor Rate/Min * Prep Mins) + (Utility Rate/Min * Cooking Mins) + Packaging Cost`
4. **Base Cost (COGS / Portion):** `(Sum of Raw + Sub-recipe Ingredients + Overheads) / Batch Portion Count`
5. **Target Retail Price & Gross Margin:** `Suggested Retail Price = Base Cost / (1 - Target Margin %)`

## Structure (expand me)
- **1. Multi-Tenant & Auth Architecture** — Tenant (Business/Store) isolation, user roles (Owner, Chef, Manager), Auth via NextAuth / Supabase Auth.
- **2. Master Data Management (Items & Units)** — Ingredients, raw materials, supplier price history, unit conversions (e.g., 1 kg = 1000 g, 1 L = 1000 ml, 1 oz = 29.5735 ml).
- **3. Yield Loss & Conversion Engine** — Waste/trimming percentage per item, net vs gross weight calculation.
- **4. Overheads & Resources Master** — Hourly labor rates, gas/electric burn rates per minute, fixed packaging items.
- **5. Sub-Recipe & Batch Engine** — Nested prep recipes (e.g., Syrups, Sauces, Stocks) used as ingredients in final menu items.
- **6. Menu Recipe Builder & Scaling** — Batch-to-portion scaling, visual ingredient builder, real-time COGS calculation, margin analyzer.
- **7. Pricing & Profitability Dashboard** — Target margin simulator, food cost percentage alerts, price suggestion matrix.
- **8. Deployment & Infra (Zeabur)** — Next.js Standalone Docker build, Zeabur PostgreSQL database, environment variables, CI/CD setup.

## Key Decisions
- **Framework:** Next.js (App Router, Server Actions, Tailwind CSS, Shadcn UI) for fast fullstack execution and light serverless/container footprint.
- **Database & ORM:** PostgreSQL on Zeabur with Drizzle ORM for lightweight, zero-overhead type-safe query performance.
- **Multi-Tenancy Strategy:** Single database with `tenant_id` foreign keys and strict middleware/query context checking.
- **Sub-Recipe Recursion:** Support up to 3 levels of nested prep recipes with circular dependency detection.
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

---

## Agentic AI Execution Directives (Instructions for AI Coding Agent)

An agentic AI assistant executing this blueprint MUST follow this strict step-by-step phased execution plan:

### Phase 1: Environment & Foundation Setup
1. **Initialize Project:**
   ```bash
   npx create-next-app@latest . --typescript --tailwind --eslint --app --src-dir --import-alias "@/*"
   npx shadcn@latest init
   npm install drizzle-orm postgres @clerk/nextjs lucide-react clsx tailwind-merge zuck-js
   npm install -D drizzle-kit dotenv
   ```
2. **Configure Database Connection:**
   - Create `src/db/index.ts` connecting to `process.env.DATABASE_URL` via `postgres` driver.
   - Create `drizzle.config.ts` targeting `./src/db/schema.ts`.

### Phase 2: Schema Definition (`src/db/schema.ts`)
1. Implement Drizzle ORM schemas with UUID primary keys and `tenant_id` on all tenant-specific tables.
2. Build relations using Drizzle `relations()` for nested recipe ingredient fetching.

### Phase 3: Pure Costing & Conversion Engine Core (`src/lib/costing-engine.ts`)
1. Write pure, zero-dependency unit-testable calculation functions:
   - `convertUnit(qty: number, fromUnit: string, toUnit: string, conversions: Conversion[]): number`
   - `calculateItemEffectiveCost(item: Item, lineQty: number, customYield?: number): number`
   - `calculateRecipeCost(recipeId: string, depth = 0): Promise<RecipeCostBreakdown>`
2. Implement recursion limit check (`depth > 3` throws `CircularDependencyError`).

### Phase 4: Server Actions & API Layer
1. `src/actions/items.ts`: CRUD for Raw Ingredients with yield % and unit prices.
2. `src/actions/resources.ts`: CRUD for Labor rates (cost/min), Gas/Electric burn rates, Packaging.
3. `src/actions/recipes.ts`: CRUD for Sub-recipes and Final Menu Recipes. Must auto-trigger recalculation of parent recipes when a sub-recipe ingredient price updates.

### Phase 5: UI & Interactive Recipe Builder Component
1. Build `RecipeBuilder` client component:
   - Interactive line-item table for adding raw materials + sub-recipes.
   - Real-time gross weight, net weight, yield loss preview, labor/gas overhead fields.
   - Live Target Gross Margin Slider (e.g. 70% target margin -> live updates Suggested Retail Price).

### Phase 6: Zeabur Deployment Configuration
1. Add `Dockerfile` for Next.js Standalone mode:
   ```dockerfile
   FROM node:20-alpine AS builder
   WORKDIR /app
   COPY package*.json ./
   RUN npm ci
   COPY . .
   ENV NEXT_TELEMETRY_DISABLED 1
   RUN npm run build

   FROM node:20-alpine AS runner
   WORKDIR /app
   ENV NODE_ENV production
   COPY --from=builder /app/public ./public
   COPY --from=builder /app/.next/standalone ./
   COPY --from=builder /app/.next/static ./.next/static
   EXPOSE 3000
   CMD ["node", "server.js"]
   ```
2. Set `output: 'standalone'` in `next.config.js`.

---

## Hand-off Instructions for AI Agent
Paste this prompt to your AI coding agent:
> "Read `docs/brainstorm-blueprint.md`. Execute Phase 1 through Phase 6 step-by-step. Build the complete Drizzle database schema, unit conversion engine, costing calculation functions, Next.js server actions, and UI screens for the F&B Prime Cost SaaS."
