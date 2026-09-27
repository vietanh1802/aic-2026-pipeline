/**
 * Result-count banner for the on-screen-text (OCR) route.
 *
 * Shows THREE counts rather than one, because they say three different things
 * and the operator needs all three to decide what to do next:
 *
 *   phrase    images holding the typed phrase verbatim  <- the one to trust
 *   allWords  images holding every word, scattered - the size of the result
 *
 * `allWords` is the one to watch. Measured over the 25 preliminary-round
 * queries (notebook 78_Vanh_tim_bang_chu):
 *
 *   <= 4 images   -> the right video comes back FIRST, 6 times out of 6
 *   >= 142 images -> right only 1 time in 6
 *
 * So when that number is large this banner tells the operator outright to type
 * more text, instead of letting them page through 500 images before realising
 * the phrase was too common. That is the whole reason this component exists —
 * counting alone was already handled by ResultInfoAndSort.
 */

export interface OcrCounts {
  phrase: number;
  allWords: number;
  searched: number;
}

interface Props {
  counts: OcrCounts;
  /** How many rows are actually on screen — to flag truncation by "Show Top". */
  shown: number;
}

const numberFormat = new Intl.NumberFormat("vi-VN");

export default function OcrCountBanner({ counts, shown }: Props) {
  const { phrase, allWords, searched } = counts;

  // Thresholds come from the measurements above, not from taste: <= 4 is the
  // band measured right 6/6, > 100 the band measured right 1/6. In between
  // stays neutral.
  const band =
    allWords === 0 ? "empty" : allWords <= 4 ? "tight" : allWords > 100 ? "broad" : "mid";

  const palette = {
    tight: "border-green-500 bg-green-50 text-green-900",
    mid: "border-amber-400 bg-amber-50 text-amber-900",
    broad: "border-red-400 bg-red-50 text-red-900",
    empty: "border-proto-line bg-proto-soft text-proto-muted",
  }[band];

  const advice = {
    tight:
      "Cụm từ rất đặc trưng — video đúng gần như chắc chắn nằm ngay đầu danh sách.",
    mid: "Cụm từ khá đặc trưng. Lướt vài chục ảnh đầu là đủ.",
    broad:
      "Cụm từ quá phổ biến. GÕ THÊM CHỮ cho đặc trưng hơn, đừng lật hết danh sách.",
    empty:
      "Không frame nào có đủ các từ này. Thử gõ ngắn lại, hoặc bật ô “Bỏ dấu”.",
  }[band];

  return (
    <div
      className={`mx-auto mt-2 max-w-[98%] rounded-md border px-4 py-2 font-baloo text-sm ${palette}`}
    >
      <div className="flex flex-row flex-wrap items-center gap-x-6 gap-y-1">
        <span>
          <span className="font-bold">{numberFormat.format(phrase)}</span> ảnh
          chứa nguyên cụm
        </span>
        <span>
          <span className="font-bold">{numberFormat.format(allWords)}</span> ảnh
          chứa đủ mọi từ
        </span>
        <span className="opacity-70">
          trên {numberFormat.format(searched)} keyframe có chữ
        </span>
        {shown < allWords && (
          <span className="opacity-70">
            — đang hiện {numberFormat.format(shown)}
          </span>
        )}
      </div>
      <div className="mt-1 text-xs">{advice}</div>
    </div>
  );
}
