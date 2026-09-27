// frontend/src/components/FrameDisplay/GroupBadge.tsx

/**
 * "N khung": this card stands for N frames of its video, because the "one card
 * per video" option folded them into the card showing the best one.
 *
 * Only for N > 1 - a video with a single frame has nothing folded into it, and a
 * "1 khung" chip on most cards would be noise. Sits in the card's name row, at
 * the right, so it adds no height. The chip style is the pin chip's (proto-primary
 * on a light tint) because both say "this is about the video, not the frame".
 */
export default function GroupBadge({ count }: { count: number }) {
  if (count <= 1) {
    return null;
  }
  return (
    <span
      className="ml-auto shrink-0 rounded-full border border-proto-primary bg-proto-primary/10 px-1.5 text-[10px] font-bold leading-4 text-proto-primary-active"
      title={`Video này có ${count} khung trong kết quả. Mở video để xem các khung khác.`}
    >
      {count} khung
    </span>
  );
}
