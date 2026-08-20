import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// CI passes these from the VERSION file and the commit being deployed, so the
// UI can name the build it is running. Defaults keep local dev honest.
const appVersion = process.env.VITE_APP_VERSION ?? "0.0.0-dev";
const appCommit = (process.env.VITE_APP_COMMIT ?? "local").slice(0, 7);

// Set AIC_DEV_API to run the UI here against an API somewhere else:
//
//   AIC_DEV_API=https://aic-api.umaga.fun npm run dev
//
// Nobody can run the backend on a laptop — it wants ~16 GB of indexes plus a
// 10.2 GB CLIP checkpoint — so the alternative is testing the UI against a
// backend that answers. Going through the dev server rather than calling the
// API directly is what makes that possible at all: the API pins CORS to the
// deployed frontend's origin, so a browser on localhost gets no
// access-control-allow-origin back and every call fails. Proxied, the requests
// are same-origin and CORS never applies.
//
// Unset, there is no proxy and nothing about `npm run dev` changes.
const devApi = process.env.AIC_DEV_API;
const forward = devApi
  ? { target: devApi, changeOrigin: true, secure: true }
  : null;

// One regex covers -search, -search-candidates and -search-text: Vite reads a
// key starting with ^ as a regex and does not anchor the end.
const proxy = forward
  ? {
      "/api": forward,
      "/health": forward,
      "/status": forward,
      "/static": forward,
      "^/(ensemble|single|temporal|trake)-search": forward,
    }
  : undefined;

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
    __APP_COMMIT__: JSON.stringify(appCommit),
  },
  server: { proxy },
});
