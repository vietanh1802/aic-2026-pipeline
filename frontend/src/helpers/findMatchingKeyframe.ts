export function findMatchingKeyframes(
  prefix: string,
  frameNum: number,
  keyframes: string[]
): { smaller?: string; larger?: string } {
  // Filter keyframes with matching prefix
  const matchingKeyframes = keyframes
    .map((kf) => {
      const parts = kf.split("-");
      return {
        prefix: parts.slice(0, -1).join("-"),
        num: parseInt(parts[parts.length - 1], 10),
        original: kf,
      };
    })
    .filter((kf) => kf.prefix === prefix);

  let smaller: { num: number; original: string } | null = null;
  let larger: { num: number; original: string } | null = null;

  for (const kf of matchingKeyframes) {
    if (kf.num <= frameNum) {
      if (!smaller || kf.num > smaller.num) {
        smaller = kf;
      }
    }
    if (kf.num >= frameNum) {
      if (!larger || kf.num < larger.num) {
        larger = kf;
      }
    }
  }

  return {
    smaller: smaller?.original,
    larger: larger?.original,
  };
}
