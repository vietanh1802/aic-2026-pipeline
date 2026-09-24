import { useEffect, useState } from "react";

import {
  canSubmitDres,
  describePayload,
  formatMs,
  getDresStatus,
  proposeDresSubmission,
  rejectDresSubmission,
  type DresStatus,
  type DresSubmission,
  type DresTaskType,
} from "../../api/dres";
import { approveWithConfirm } from "../../helpers/dresApprove";
import { useAuthStore } from "../../store/authStore";
import Button from "../Button";

const TYPES: { id: DresTaskType; label: string }[] = [
  { id: "kis", label: "KIS" },
  { id: "qa", label: "Q&A" },
  { id: "trake", label: "TRAKE" },
];

/**
 * "Nộp DRES" trong popup video — đề xuất, hoặc nộp luôn, một bài chung kết.
 *
 * Lấy THỜI ĐIỂM ĐANG PHÁT của trình phát chứ không phải keyframe gần nhất: ở
 * chung kết đáp án là một đoạn trong video gốc, và người dùng đã tua tới đúng
 * khoảnh khắc đó. Mili-giây gửi lên server; server quy ra frame bằng fps BTC.
 *
 * Tách hẳn khỏi SubmitForm/giỏ đáp án: giỏ là danh sách xếp hạng R@k của vòng
 * sơ tuyển, còn đây là MỘT đáp án được chấm ngay — trộn hai luồng thì một cú
 * "Add Answer" quen tay có thể thành một lần nộp −10 điểm.
 *
 * Người được tự gửi (admin, hoặc mọi người khi admin bật chế độ đó) có nút
 * "Nộp ngay": đề xuất rồi duyệt liền, qua cùng hộp xác nhận. Người còn lại chỉ
 * đề xuất và chờ duyệt ở tab DRES.
 */
export default function DresPropose({
  videoId,
  getPlayhead,
  defaultType,
}: {
  videoId: string;
  /** Giây, đọc thẳng currentTime của <video> tại lúc bấm. */
  getPlayhead: () => number;
  defaultType?: DresTaskType;
}) {
  const role = useAuthStore((state) => state.user?.role);
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<DresStatus | null>(null);
  const [type, setType] = useState<DresTaskType>(defaultType ?? "kis");
  const [answer, setAnswer] = useState("");
  const [marks, setMarks] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DresSubmission | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Mốc TRAKE thuộc về một video; trỏ popup sang video khác thì bỏ.
  useEffect(() => {
    setMarks([]);
    setResult(null);
    setError(null);
  }, [videoId]);

  // Đọc chế độ mỗi lần mở khung: admin có thể vừa đổi giữa buổi.
  useEffect(() => {
    if (open) {
      void getDresStatus().then(setStatus).catch(() => undefined);
    }
  }, [open]);

  const canSubmit = canSubmitDres(role, status);
  const nowMs = () => Math.round(getPlayhead() * 1000);

  const propose = async (): Promise<DresSubmission | null> => {
    const times = type === "trake" ? marks : [nowMs()];
    const created = await proposeDresSubmission({
      task_type: type,
      video_id: videoId,
      times_ms: times,
      answer: type === "qa" ? answer : undefined,
    });
    setResult(created);
    if (type === "trake") {
      setMarks([]);
    }
    return created;
  };

  const run = async (sendNow: boolean) => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const created = await propose();
      if (!sendNow || !created) {
        return;
      }
      const sent = await approveWithConfirm(created);
      if (sent) {
        setResult(sent);
      } else {
        // Huỷ ở hộp xác nhận thì rút luôn đề xuất vừa tạo, để nó không nằm
        // trong hàng chờ như thể còn ai đó phải duyệt.
        setResult(await rejectDresSubmission(created.id));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  // Bài đã đề xuất mà chưa gửi (ví dụ gửi lỗi mạng) thì gửi lại từ đây.
  const approveNow = async () => {
    if (!result) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const sent = await approveWithConfirm(result);
      if (sent) {
        setResult(sent);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const ready =
    !busy &&
    (type === "kis" ||
      (type === "qa" && answer.trim().length > 0) ||
      (type === "trake" && marks.length > 0));
  const what =
    type === "trake" ? `TRAKE (${marks.length} mốc)` : `${type === "qa" ? "Q&A" : "KIS"} tại thời điểm đang phát`;

  return (
    <div className="mt-3 rounded-[10px] border-2 border-[#7b1fa2]/40 bg-[#7b1fa2]/5 p-3 font-baloo">
      <button
        type="button"
        className="text-[13px] font-bold text-[#7b1fa2]"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "▾" : "▸"} Nộp DRES (chung kết)
      </button>

      {open && (
        <div className="flex flex-col gap-2 mt-2">
          <div className="flex flex-wrap items-center gap-1">
            {TYPES.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setType(t.id)}
                className={`text-[12px] px-3 py-1 rounded-[7px] border ${
                  type === t.id
                    ? "bg-white border-[#7b1fa2] font-bold text-[#7b1fa2]"
                    : "border-transparent text-proto-muted"
                }`}
              >
                {t.label}
              </button>
            ))}
            <span className="ml-auto text-[11px] text-proto-muted">
              {status?.submit_mode === "everyone"
                ? "Chế độ: mọi người nộp được"
                : "Chế độ: chỉ admin nộp"}
            </span>
          </div>

          {type === "qa" && (
            <input
              className="p-2 rounded-[8px] bg-white border border-proto-line text-sm"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Đáp án Q&A"
            />
          )}

          {type === "trake" && (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setMarks((m) => [...m, nowMs()])}
              >
                + Mốc E{marks.length + 1} tại đây
              </Button>
              {marks.map((ms, i) => (
                <span
                  key={`${i}-${ms}`}
                  className="flex items-center gap-1 text-[12px] px-2 py-0.5 rounded-full bg-white border border-proto-line"
                >
                  E{i + 1} {formatMs(ms)}
                  <button
                    type="button"
                    className="text-proto-muted hover:text-[#c64545]"
                    onClick={() => setMarks((m) => m.filter((_, j) => j !== i))}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2">
            {canSubmit ? (
              <>
                <Button size="sm" variant="danger" disabled={!ready} onClick={() => void run(true)}>
                  Nộp ngay {what}
                </Button>
                <Button size="sm" variant="outline" disabled={!ready} onClick={() => void run(false)}>
                  Chỉ đề xuất
                </Button>
              </>
            ) : (
              <Button size="sm" disabled={!ready} onClick={() => void run(false)}>
                Đề xuất {what}
              </Button>
            )}
            {canSubmit && result && (result.status === "proposed" || result.status === "failed") && (
              <Button size="sm" variant="outline" disabled={busy} onClick={() => void approveNow()}>
                {result.status === "failed" ? "Gửi lại" : "Duyệt & nộp"} #{result.id}
              </Button>
            )}
          </div>

          {result && (
            <div className="text-[12px] flex flex-col gap-0.5">
              <span>
                <b>#{result.id}</b>{" "}
                {result.verdict
                  ? `→ ${result.verdict}`
                  : result.status === "proposed"
                    ? "đã đề xuất — chờ duyệt ở tab DRES"
                    : result.status === "failed"
                      ? `lỗi: ${result.error ?? ""}`
                      : result.status === "rejected"
                        ? "đã huỷ, không gửi"
                        : result.status}
              </span>
              <code className="break-all">{describePayload(result)}</code>
              {result.warnings.map((w) => (
                <span key={w} className="text-[#8a6a0f]">⚠ {w}</span>
              ))}
            </div>
          )}
          {error && <span className="text-[12px] text-[#c64545]">{error}</span>}
        </div>
      )}
    </div>
  );
}
