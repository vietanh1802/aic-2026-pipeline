import type { SearchResult } from "../types/api";

export const formatResultByVideoID = (results: SearchResult[]) => {
  const grouped: Record<string, SearchResult[]> = {};
  console.log(results);
  results.forEach((item) => {
    const videoId = item.name.match(/[LK]\d+_V\d+/);
    const key = videoId ? videoId[0] : "unknown";
    if (!grouped[key]) {
      grouped[key] = [];
    }
    grouped[key].push(item);
  });

  const sortedKeys = Object.keys(grouped).sort((a, b) => {
    const matchA = a.match(/[LK](\d+)_V(\d+)/);
    const matchB = b.match(/[LK](\d+)_V(\d+)/);

    if (!matchA || !matchB) return a.localeCompare(b);

    const [, lA, vA] = matchA.map(Number);
    const [, lB, vB] = matchB.map(Number);

    if (lA !== lB) return lA - lB;
    return vA - vB;
  });

  const sortedGrouped: Record<string, SearchResult[]> = {};
  sortedKeys.forEach((key) => {
    sortedGrouped[key] = grouped[key];
  });

  return sortedGrouped;
};
