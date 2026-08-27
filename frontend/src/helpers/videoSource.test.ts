import { describe, expect, it } from "vitest";

import { buildKeyframeUrl } from "./videoSource";

describe("buildKeyframeUrl", () => {
  // The deployed layout: images sit on their own CDN host, not on the API.
  // docker-compose.yml sets AIC_IMAGE_BASE_URL=https://aic-frames.umaga.fun
  // while the API answers on https://aic-api.umaga.fun.
  it("puts the name under images/ on the configured base", () => {
    expect(
      buildKeyframeUrl("https://aic-frames.umaga.fun", "L25_V085-0086-30870")
    ).toBe("https://aic-frames.umaga.fun/images/L25_V085-0086-30870.jpg");
  });

  // The local default, matching preprocess.py's IMAGE_BASE_URL.
  it("matches the URL the backend builds for the same frame", () => {
    expect(
      buildKeyframeUrl("http://localhost:8000/static", "K19_V001-0000-29")
    ).toBe("http://localhost:8000/static/images/K19_V001-0000-29.jpg");
  });

  it("does not double the extension when the caller supplied one", () => {
    expect(buildKeyframeUrl("http://x/static", "K19_V001-0000-29.jpg")).toBe(
      "http://x/static/images/K19_V001-0000-29.jpg"
    );
  });

  it("tolerates a trailing slash on the base", () => {
    expect(buildKeyframeUrl("http://x/static/", "K19_V001-0000-29")).toBe(
      "http://x/static/images/K19_V001-0000-29.jpg"
    );
  });

  // Same-origin dev: VITE_API_BASE_URL is empty in .env.local so every call
  // goes through the Vite proxy, which already forwards /static.
  it("produces a same-origin path when the base is just /static", () => {
    expect(buildKeyframeUrl("/static", "K19_V001-0000-29")).toBe(
      "/static/images/K19_V001-0000-29.jpg"
    );
  });

  it("returns an empty string for an empty name", () => {
    expect(buildKeyframeUrl("http://x/static", "")).toBe("");
  });
});
