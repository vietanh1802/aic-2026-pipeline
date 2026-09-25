import { defineConfig } from "vitest/config";

// Separate from vite.config.ts on purpose. Vitest 2 bundles its own Vite, and
// importing defineConfig from "vitest/config" into the build config makes the
// two Vite copies' plugin types collide. Tests here are arithmetic on frame
// numbers, so they need neither the React nor the Tailwind plugin.
export default defineConfig({
  // keyframe_index.json is 10.5 MB since the 2026-09-25 dataset (983,931
  // frames). Vitest 2's Vite 5 turns an imported JSON into an object literal
  // by default, and transforming that one module ran the GitHub runner's
  // vitest out of heap (exit 134). JSON.parse("…") yields the same object at
  // a fraction of the transform cost — Vite 6 does this by default above 10 kB.
  json: { stringify: true },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
