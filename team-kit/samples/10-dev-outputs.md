# Dev outputs (excerpts the team will recognize)
## 1. Component — TrackingLookup.vue (head)
<!-- SC-01 · US-101 -->
<script setup lang="ts">
const props = defineProps<{ busy?: boolean }>()   // loading state from useFetch status
// states: busy→skeleton · error→inline retry · empty-input→validation · success→emit('found', resi)
</script>
<template>
  <form>… <input aria-label="Nomor resi" /> …</form>   <!-- tokens only: rounded-radius.md text-size.body -->
</template>
## 2. Playwright — tracking.spec.ts (states = UX Spec matrix, verbatim)
test('SC-02 unknown resi → inline error + retry', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Nomor resi').fill('KK-999999');
  await page.getByRole('button', { name: 'Lacak' }).click();
  await expect(page.getByText('Resi tidak ditemukan')).toBeVisible();   // error state
  await page.getByLabel('Nomor resi').fill('KK-100001');                 // retry, input kept
});
## 3. figma-tokens PR description
+ color/primary #0F6FFF → color.brand (rename, Figma var v9) · + space/4 … tokens-only audit: clean
## 4. Commit / PR
feat(US-101): track lookup with all SC-02 states — 318 lines · 1 screenshot · CI green
