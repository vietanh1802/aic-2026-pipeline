/**
 * Reading "which frame do you mean" out of whatever a teammate pasted.
 *
 * Three things get pasted in practice: a video and a frame with a space
 * between them, the same with a dash, and a whole keyframe filename copied off
 * a result tile. All three are the video id followed by one or two numbers, so
 * they parse as one rule rather than three.
 */
const VIDEO = /^[LK]\d{2}_V\d{3}/;

export interface FrameRef {
  videoId: string;
  frameIdx: number;
}

/** Null for anything that is not one of the three forms. */
export function parseFrameRef(input: string): FrameRef | null {
  // A fractional frame is a mistake, not a rounding job, so strip only a real
  // file extension: letters, not digits.
  const text = input.trim().replace(/\.[a-z]+$/i, "");
  const match = VIDEO.exec(text);
  if (!match) {
    return null;
  }
  const videoId = match[0];

  const rest = text.slice(videoId.length).replace(/^[\s\-_]+/, "");
  const parts = rest.split(/[\s\-_]+/).filter((part) => part !== "");
  // One number is the frame; two are scene and frame, and the frame is the one
  // that matters. Three would be a filename shape nobody writes.
  if (parts.length === 0 || parts.length > 2) {
    return null;
  }
  if (!parts.every((part) => /^\d+$/.test(part))) {
    return null;
  }

  return { videoId, frameIdx: Number(parts[parts.length - 1]) };
}
