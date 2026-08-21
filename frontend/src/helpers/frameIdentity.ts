/**
 * Turning a keyframe's identity into the three things the video popup needs.
 *
 * These lived inside App.tsx, which was fine while the search grid was the only
 * caller. TRAKE results open the same popup from a different component, so a
 * second copy would be two places to fix the next time a filename changes shape.
 */
import KeyframeFPS from "../mapping/fps_map.json";

/** "L26_V194-0012-004707.jpg" -> "L26_V194" */
export function videoIdFromFrame(frame: string): string {
  return frame.match(/^([LK]\d{2}_V\d{3})/)?.[1] ?? "";
}

/** "L26_V194-0012-004707.jpg" -> "0012-004707" */
export function frameIdFromName(name: string): string {
  const baseName = name.replace(/\.[^/.]+$/, "");
  return baseName.split("-").slice(1).join("-");
}

/** 0 when the video is missing from fps_map.json — callers must check. */
export function fpsOf(videoId: string): number {
  return (KeyframeFPS as Record<string, number | undefined>)[videoId] ?? 0;
}

/**
 * Where the popup should open, in milliseconds.
 *
 * Returns 0 for an unknown fps rather than NaN: opening at the start with the
 * frame number on screen is recoverable, a NaN seek is not.
 */
export function startMsAt(videoId: string, frameIdx: number): number {
  const fps = fpsOf(videoId);
  if (!fps || !Number.isFinite(frameIdx)) {
    return 0;
  }
  return (frameIdx / fps) * 1000;
}
