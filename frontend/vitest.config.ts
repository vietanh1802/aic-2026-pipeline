import { defineConfig } from "vitest/config";

// Separate from vite.config.ts on purpose. Vitest 2 bundles its own Vite, and
// importing defineConfig from "vitest/config" into the build config makes the
// two Vite copies' plugin types collide. Tests here are arithmetic on frame
// numbers, so they need neither the React nor the Tailwind plugin.
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
