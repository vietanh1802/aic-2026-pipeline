import { describe, expect, it } from "vitest";

import { routeAgreement } from "./index";
import type { SearchResult } from "../../types/api";

function result(routes: SearchResult["routes"]): SearchResult {
  return {
    frame: "L30_V072-0000-1745.jpg",
    name: "L30_V072-0000-1745.jpg",
    url: "",
    distance: 42,
    routes,
  } as SearchResult;
}

describe("routeAgreement", () => {
  it("reports both when BEiT3 and CLIP each found the frame", () => {
    expect(
      routeAgreement(
        result({
          beit3: { rank: 1, score: 0.9 },
          clip: { rank: 3, score: 0.8 },
        })
      )
    ).toBe("both");
  });

  it("reports one when a single model found it", () => {
    expect(routeAgreement(result({ clip: { rank: 3, score: 0.8 } }))).toBe(
      "one"
    );
  });

  it("reports none when routes is absent", () => {
    expect(routeAgreement(result(undefined))).toBe("none");
  });
});
