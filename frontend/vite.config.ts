import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// CI passes these from the VERSION file and the commit being deployed, so the
// UI can name the build it is running. Defaults keep local dev honest.
const appVersion = process.env.VITE_APP_VERSION ?? "0.0.0-dev";
const appCommit = (process.env.VITE_APP_COMMIT ?? "local").slice(0, 7);

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
    __APP_COMMIT__: JSON.stringify(appCommit),
  },
});
