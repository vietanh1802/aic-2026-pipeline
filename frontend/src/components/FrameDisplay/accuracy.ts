// The red→yellow→green accuracy ramp, restored and fixed.
//
// Two things were wrong with the version this replaces:
//
// 1. It fed the raw `distance` straight into the ramp. `distance` is already a
//    percentage score (higher = better) and a real ensemble response spans a
//    narrow band — 100.0 down to 86.15 on a measured run — so every tile
//    landed in the green half of the ramp and the colour looked flat.
// 2. The min–max normalisation that would have fixed that was commented out,
//    and it ran the wrong way round: `(max - distance) / (max - min)` dates
//    from when the field really was a distance (lower = better). Restoring it
//    verbatim would paint the best result red.
//
// Normalising against the current result set is what makes the spread legible:
// rank 1 is always full green, the last row is always full red, and everything
// between shows where it actually sits.

export function accuracyPercent(
  distance: number,
  min: number,
  max: number
): number {
  if (!(max > min)) {
    return 100;
  }
  const scaled = ((distance - min) / (max - min)) * 100;
  return Math.min(100, Math.max(0, scaled));
}

export function accuracyColor(percent: number): string {
  const n = Math.min(100, Math.max(0, percent)) / 100;
  let red: number;
  let green: number;
  if (n <= 0.5) {
    red = 255;
    green = Math.round(255 * (n * 2));
  } else {
    red = Math.round(255 * (1 - (n - 0.5) * 2));
    green = 255;
  }
  return `rgb(${red},${green},0)`;
}
