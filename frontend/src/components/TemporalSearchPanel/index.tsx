"use client";
// components/TemporalSearchPanel/index.tsx
//
// Alg.4 UI — bám sát Section 3.6.1 + Figure 4b/4c của paper (arXiv 2504.08384):
//
//   "We assume that the initially retrieved and reranked input frame
//    corresponds to the correct reference frame" — anchor là 1 keyframe do
//    NGƯỜI DÙNG tự chọn từ kết quả search đã có (Figure 4a → 4b), không phải
//    danh sách hệ thống tự sinh.
//
//   "users provide two separate textual descriptions (Figure 4b): one
//    describing the start of the moment and another describing the end...
//    the system suggests a start frame and an end frame"
//
//   "(c) Boundary Selection... the system highlights the proposed start
//    frame in green and the proposed end frame in red. Users can review
//    these suggestions and adjust them if necessary to refine the moment
//    boundaries."
//
// Component này KHÔNG thay thế search cũ — mở như 1 panel phụ, kích hoạt từ
// nút "Dùng làm mốc" trên mỗi kết quả search sẵn có (xem FrameDisplay).

import { useState } from "react";
import Button from "../Button";
import { videoSearchApi } from "../../types/api";
import KeyframeImg from "../KeyframeImg";
import type { TemporalSearchResult, TemporalCandidate } from "../../types/api";

interface TemporalSearchPanelProps {
  anchorName: string;
  anchorUrl: string;
  onClose: () => void;
}

export default function TemporalSearchPanel({
  anchorName,
  anchorUrl,
  onClose,
}: TemporalSearchPanelProps) {
  const [queryStart, setQueryStart] = useState("");
  const [queryEnd, setQueryEnd] = useState("");
  const [gapC, setGapC] = useState(20);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<TemporalSearchResult | null>(null);
  // Frame đang hiển thị làm start/end — khởi tạo từ kết quả thuật toán đề
  // xuất, nhưng người dùng bấm vào 1 candidate khác thì đổi qua đây. Đây
  // chính là bước "review and adjust" paper mô tả ở Figure 4c.
  const [pickedStart, setPickedStart] = useState<TemporalCandidate | null>(null);
  const [pickedEnd,   setPickedEnd]   = useState<TemporalCandidate | null>(null);

  const doTemporalSearch = async () => {
    if (!queryStart.trim() || !queryEnd.trim()) return;
    setIsLoading(true);
    try {
      const res = await videoSearchApi.temporalSearch(
        queryStart,
        queryEnd,
        anchorName,
        { gapC }
      );
      setResult(res);
      if (res.start_frame && res.start_url) {
        setPickedStart({ name: res.start_frame, url: res.start_url,
                         frame_idx: res.start_frame_idx, timestamp: res.start_ts });
      }
      if (res.end_frame && res.end_url) {
        setPickedEnd({ name: res.end_frame, url: res.end_url,
                       frame_idx: res.end_frame_idx, timestamp: res.end_ts });
      }
    } catch (err) {
      console.error("Temporal search failed:", err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[999] bg-black/40 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-y-auto p-6 font-baloo">
        <div className="flex justify-between items-center mb-4">
          <h2 className="font-bold text-lg">
            Temporal Search (Alg.4) — mốc: {anchorName}
          </h2>
          <button
            className="text-[#c64545] hover:bg-[#c64545]/15 rounded-full px-3 py-1 font-bold"
            onClick={onClose}
          >
            X
          </button>
        </div>

        {/* Anchor đang dùng — chính là frame người dùng đã chọn từ search trước đó */}
        <div className="flex items-center gap-x-3 mb-4 p-2 bg-proto-soft border border-proto-line rounded-lg">
          <KeyframeImg
            src={anchorUrl}
            alt="anchor"
            className="w-24 h-14 object-cover rounded shrink-0"
          />
          <div className="text-sm text-proto-muted">
            Mốc tham chiếu (frame đã chọn từ kết quả search) — theo paper:
            &quot;initially retrieved and reranked input frame corresponds to
            the correct reference frame&quot;.
          </div>
        </div>

        {/* 2 mini-query — Figure 4b */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
          <div>
            <label className="font-bold text-sm block mb-1">
              Mô tả điểm BẮT ĐẦU (query_1)
            </label>
            <input
              value={queryStart}
              onChange={(e) => setQueryStart(e.target.value)}
              placeholder="vd: người bắt đầu bước lên sân khấu"
              className="p-2 w-full rounded-[8px] border border-proto-line bg-proto-soft"
            />
          </div>
          <div>
            <label className="font-bold text-sm block mb-1">
              Mô tả điểm KẾT THÚC (query_2)
            </label>
            <input
              value={queryEnd}
              onChange={(e) => setQueryEnd(e.target.value)}
              placeholder="vd: khán giả vỗ tay sau bài phát biểu"
              className="p-2 w-full rounded-[8px] border border-proto-line bg-proto-soft"
            />
          </div>
        </div>

        <button
          type="button"
          className="block text-sm text-proto-primary-active underline mb-3 w-fit"
          onClick={() => setShowAdvanced((v) => !v)}
        >
          {showAdvanced ? "Ẩn" : "Hiện"} tham số nâng cao (gap_C)
        </button>
        {showAdvanced && (
          <div className="mb-3 flex items-center gap-x-2">
            <label className="text-sm font-bold">
              gap_C (giây, khoảng cách tối đa giữa 2 điểm):
            </label>
            <input
              type="number"
              value={gapC}
              onChange={(e) => setGapC(Number(e.target.value))}
              className="p-1 w-20 rounded-[8px] border border-proto-line bg-proto-soft"
            />
          </div>
        )}

        <Button onClick={doTemporalSearch} className="mb-4">
          {isLoading ? "Đang tìm..." : "Tìm khoảng thời gian"}
        </Button>

        {result?.error && (
          <div className="text-[#c64545] text-sm mb-3">{result.error}</div>
        )}

        {/* Boundary Selection — Figure 4c: viền xanh lá = start, viền đỏ = end */}
        {pickedStart && pickedEnd && (
          <div>
            <div className="grid grid-cols-2 gap-4 mb-3">
              <div>
                <p className="font-bold text-sm mb-1 text-[#3d7a4d]">
                  Frame BẮT ĐẦU (viền xanh lá)
                </p>
                <KeyframeImg
                  src={pickedStart.url}
                  alt="start"
                  className="w-full aspect-[3/2] object-cover rounded border-4 border-[#5db872]"
                />
                <p className="text-xs text-proto-muted mt-1">
                  {pickedStart.name} · {pickedStart.timestamp}
                </p>
              </div>
              <div>
                <p className="font-bold text-sm mb-1 text-[#8f3030]">
                  Frame KẾT THÚC (viền đỏ)
                </p>
                <KeyframeImg
                  src={pickedEnd.url}
                  alt="end"
                  className="w-full aspect-[3/2] object-cover rounded border-4 border-[#c64545]"
                />
                <p className="text-xs text-proto-muted mt-1">
                  {pickedEnd.name} · {pickedEnd.timestamp}
                </p>
              </div>
            </div>
            <p className="text-sm text-proto-muted mb-2">
              Điểm gộp: {result?.combined_score} — Nếu chưa đúng ý, bấm 1 frame
              khác trong danh sách ứng viên bên dưới để thay thế (paper: &quot;Users
              can review these suggestions and adjust them if necessary&quot;).
            </p>

            {/* Candidate carousels — đúng bước "review and adjust" */}
            {result?.left_candidates && result.left_candidates.length > 0 && (
              <div className="mb-3">
                <p className="font-bold text-sm mb-1">
                  Ứng viên khác cho điểm bắt đầu ({result.left_candidates.length})
                </p>
                <div className="flex gap-x-2 overflow-x-auto pb-2">
                  {result.left_candidates.map((c) => (
                    <KeyframeImg
                      key={c.name}
                      src={c.url}
                      alt={c.name}
                      title={`${c.name} · điểm ${c.score}`}
                      onClick={() => setPickedStart(c)}
                      className={`w-20 h-12 object-cover rounded cursor-pointer flex-shrink-0 ${
                        pickedStart.name === c.name
                          ? "border-4 border-[#5db872]"
                          : "border-2 border-proto-line hover:border-[#5db872]"
                      }`}
                    />
                  ))}
                </div>
              </div>
            )}
            {result?.right_candidates && result.right_candidates.length > 0 && (
              <div>
                <p className="font-bold text-sm mb-1">
                  Ứng viên khác cho điểm kết thúc ({result.right_candidates.length})
                </p>
                <div className="flex gap-x-2 overflow-x-auto pb-2">
                  {result.right_candidates.map((c) => (
                    <KeyframeImg
                      key={c.name}
                      src={c.url}
                      alt={c.name}
                      title={`${c.name} · điểm ${c.score}`}
                      onClick={() => setPickedEnd(c)}
                      className={`w-20 h-12 object-cover rounded cursor-pointer flex-shrink-0 ${
                        pickedEnd.name === c.name
                          ? "border-4 border-[#c64545]"
                          : "border-2 border-proto-line hover:border-[#c64545]"
                      }`}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}