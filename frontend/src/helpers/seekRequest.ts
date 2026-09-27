// frontend/src/helpers/seekRequest.ts

/**
 * "Seek there" as an event, not as a value.
 *
 * The popup seeks by a state value: `startAt` changes, `jumpTo` follows, an
 * effect on [jumpTo] moves the player. A value only fires on CHANGE, so pressing
 * a candidate block, scrubbing away with the native bar, and pressing the same
 * block again does nothing the second time - `setStartAt` gets the value it
 * already holds and React bails out. Every existing seek path has that
 * limitation; it only became visible once there was a control you press twice.
 *
 * A request carries an `id` next to the target, and the effect that consumes it
 * runs on the request OBJECT, so a new request fires it even for the same time.
 * Nothing else about seeking changes: startAt and the jumpTo effect are untouched.
 */
export interface SeekRequest {
  /** Where to seek, in seconds. */
  timeS: number;
  /** 1, 2, 3 ... so two requests for the same target are still two requests. */
  id: number;
}

export function nextSeekRequest(previous: SeekRequest | null, timeS: number): SeekRequest {
  return { timeS, id: (previous?.id ?? 0) + 1 };
}

/**
 * Whether the player has to move to reach `targetS`. Half a frame of tolerance,
 * so a target the player is already on is left alone and a single-frame step
 * still lands - the same test the jumpTo effect in VideoDisplay applies. fps
 * falls back to 25 when unknown, as there.
 */
export function needsSeek(currentTimeS: number, targetS: number, fps: number): boolean {
  return Math.abs(currentTimeS - targetS) > 0.5 / (fps || 25);
}
