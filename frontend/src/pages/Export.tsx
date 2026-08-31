import { useEffect, useState } from "react";

import {
  getExportPhase,
  previewExport,
  setExportPhase,
  type ExportPhase,
} from "../api/answers";
import { API_BASE_URL, ApiRequestError } from "../api/base";
import {
  getBoard,
  listPacks,
  type BoardResponse,
  type RoundPack,
} from "../api/board";
import Button from "../components/Button";
import { useAuthStore } from "../store/authStore";

/**
 * Đặt số vòng, xem trước một file, tải cả vòng về.
 *
 * Chỉ có thế. Bốn thứ từng nằm ở đây đã đi chỗ khác hoặc bị bỏ:
 *
 * - Khung video và danh sách dòng: chuyển sang màn Evaluation. Ở đây nó còn
 *   sai nữa là khác — nó gọi getAnswers(task) nên bày bài của CHÍNH NGƯỜI ĐANG
 *   XEM, trong khi file nộp lấy bài của người được chọn. Hai danh sách khác
 *   nhau đặt dưới cái tiêu đề "xem trước file nộp".
 * - Ô chọn bài của ai để nộp: cũng sang Evaluation, vì đó là quyết định đưa ra
 *   khi đang đọ 5 cột bài, không phải khi đang nhìn một dòng trong bảng. Dưới
 *   đây chỉ hiện KẾT QUẢ của lựa chọn đó, không sửa được.
 * - Nút "Xoá sạch": bỏ hẳn. Từ khi mỗi người một danh sách, một cú bấm nhầm
 *   xoá trắng công của một người mà không hoàn tác được từ giao diện. Muốn bỏ
 *   dòng nào thì xoá từng dòng trên cột của mình ở Evaluation.
 * - Nút "Kiểm tra" và bảng cảnh báo: bỏ theo yêu cầu. Trên một gói vừa nhập
 *   nó đổ ra đúng 30 dòng "chưa ai làm — sẽ nộp file rỗng", nhiều tới mức che
 *   mất những cảnh báo thật. Endpoint /api/export/validate vẫn còn ở backend
 *   nhưng không màn nào gọi nữa.
 */
export default function ExportPage() {
  const token = useAuthStore((state) => state.token);
  const user = useAuthStore((state) => state.user);
  const [board, setBoard] = useState<BoardResponse | null>(null);
  const [preview, setPreview] = useState<{
    filename: string;
    rows: number;
    content: string;
  } | null>(null);
  const [previewTaskId, setPreviewTaskId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Số vòng trong tên file nộp, và cái đang gõ trong ô. Tách ra vì `phaseText`
  // được phép ở trạng thái dở dang ("" trong lúc xoá để gõ lại), còn `phase`
  // chỉ giữ giá trị máy chủ đã nhận.
  const [phase, setPhase] = useState<ExportPhase | null>(null);
  const [phaseText, setPhaseText] = useState("");

  // Which round is being exported. Null means the live one — resubmitting a
  // round that has been retired is a real errand, so the picker exists, but the
  // default has to stay the round everyone is actually working in.
  const [viewing, setViewing] = useState<number | null>(null);
  const [rounds, setRounds] = useState<RoundPack[] | null>(null);

  useEffect(() => {
    void getBoard(viewing ?? undefined)
      .then(setBoard)
      .catch(() => undefined);
  }, [viewing]);

  // Admin-only listing; a member just gets the live round and no picker.
  useEffect(() => {
    if (user?.role !== "admin") {
      return;
    }
    void listPacks()
      .then((result) => setRounds(result.packs.filter((p) => !p.deleted_at)))
      .catch(() => undefined);
  }, [user?.role]);

  const packId = board?.round?.id ?? null;

  useEffect(() => {
    if (packId === null) {
      return;
    }
    void getExportPhase(packId)
      .then((result) => {
        setPhase(result);
        setPhaseText(result.phase);
      })
      .catch(() => undefined);
  }, [packId]);

  const savePhase = async (value: string) => {
    if (packId === null) return;
    setBusy(true);
    try {
      const result = await setExportPhase(packId, value);
      setPhase(result);
      setPhaseText(result.phase);
      // Tên file vừa đổi, nên bản xem trước đang hiện là tên cũ.
      setPreview(null);
      setPreviewTaskId(null);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Không đổi được");
    } finally {
      setBusy(false);
    }
  };

  const look = async (taskId: number) => {
    try {
      setPreview(await previewExport(taskId));
      setPreviewTaskId(taskId);
      setError(null);
    } catch (err) {
      setPreview(null);
      setPreviewTaskId(null);
      setError(err instanceof ApiRequestError ? err.message : "Không xem được");
    }
  };

  // The zip is a plain GET, but it still needs the bearer token, so it goes
  // through fetch and a blob rather than a bare link.
  const download = async () => {
    if (!packId) return;
    setBusy(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/export/zip?pack_id=${packId}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!response.ok) {
        throw new ApiRequestError(response.status, `HTTP ${response.status}`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      // LUÔN "submission.zip". Trước đây lấy theo nhãn vòng, nên mỗi vòng ra
      // một tên khác và nhãn tiếng Việt còn kéo theo cả lỗi 500 ở header phía
      // máy chủ. Phải khớp SUBMISSION_ZIP_NAME trong backend/app/routers/
      // export.py — thẻ <a download> luôn thắng header, nên lệch nhau thì tên
      // lưu xuống máy không phải tên máy chủ gửi.
      anchor.download = "submission.zip";
      // Two things this used to get wrong, both of which end in the same
      // symptom: the button works, no error shows, and no file arrives.
      // Firefox ignores click() on an anchor that is not in the document, and
      // revoking the object URL in the same tick can cancel the download
      // before the browser has finished reading the blob out of it. Append,
      // click, then revoke a turn of the event loop later.
      anchor.style.display = "none";
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Không tải được");
    } finally {
      setBusy(false);
    }
  };

  if (board && !board.round) {
    return (
      <div className="max-w-[1200px] mx-auto p-8 font-baloo">
        <h2 className="text-2xl text-proto-ink mb-2">Chưa có gì để xuất</h2>
        <p className="text-sm text-proto-muted">Nhập gói truy vấn trước đã.</p>
      </div>
    );
  }

  const unchosen =
    board?.tasks.filter(
      (task) => task.contributors.length > 0 && task.chosen_author_id === null
    ) ?? [];

  return (
    <div className="max-w-[1200px] mx-auto p-6 font-baloo">
      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <h2 className="text-2xl text-proto-ink">Xuất bài</h2>
        {rounds && rounds.length > 1 ? (
          <label className="flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
              Vòng
            </span>
            <select
              className="px-2 py-1 rounded-[7px] border border-proto-line bg-white text-[13px] text-proto-ink"
              value={viewing ?? ""}
              onChange={(event) => {
                setViewing(event.target.value ? Number(event.target.value) : null);
                setPreview(null);
                setPreviewTaskId(null);
              }}
            >
              <option value="">Vòng đang dùng</option>
              {rounds.map((round) => (
                <option key={round.id} value={round.id}>
                  {round.label}
                  {round.active ? " (đang dùng)" : ""}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <span className="text-xs font-mono text-proto-muted">
            {board?.round?.label}
          </span>
        )}
        {board?.round && !board.round.active && (
          <span className="text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-[#d4a017]/20 text-[#8a6a0f]">
            Vòng đã nghỉ
          </span>
        )}
        <span className="ml-auto flex gap-2 items-center">
          {/* Số vòng. Nằm cạnh nút tải chứ không giấu trong màn quản trị: nó
              quyết định tên của cả 25 file trong gói, và đặt sai thì bài bị
              chấm hỏng mà không có dấu hiệu gì. */}
          <label className="flex items-center gap-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
              Vòng
            </span>
            <input
              value={phaseText}
              disabled={busy || !packId}
              onChange={(event) => setPhaseText(event.target.value)}
              onBlur={() => {
                if (phaseText !== phase?.phase) void savePhase(phaseText);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") event.currentTarget.blur();
              }}
              placeholder="p1"
              title="Số vòng trong tên file của ban tổ chức. Gõ 2 hoặc p2."
              className={`w-14 px-2 py-1 rounded-[7px] border bg-white text-[13px] font-mono text-proto-ink text-center ${
                phase?.guessed ? "border-[#d4a017]" : "border-proto-line"
              }`}
            />
          </label>
          <Button disabled={busy || !packId} onClick={() => void download()}>
            Tải zip
          </Button>
        </span>
      </div>

      {/* Tên file, in ra trước khi tải. Đây mới là thứ chặn được lần mất bài
          thứ hai: "p2" là một con số không nói lên gì, còn một tên file đầy đủ
          thì đối chiếu được ngay với file ban tổ chức phát. */}
      {phase && (
        <div
          className={`rounded-[10px] px-4 py-2 mb-4 text-[13px] border ${
            phase.guessed
              ? "border-[#d4a017] bg-[#d4a017]/10 text-[#8a6a0f]"
              : "border-proto-line bg-white text-proto-body"
          }`}
        >
          Gói tải về tên <b className="font-mono">submission.zip</b>, các file
          bên trong tên{" "}
          <b className="font-mono text-proto-ink">
            {phase.sample_filename ?? `query-${phase.phase}-<mã>-<loại>.csv`}
          </b>
          {phase.guessed && (
            <>
              {" "}
              — <b>gói này không ghi số vòng</b> nên đang tạm lấy{" "}
              <b className="font-mono">{phase.phase}</b>. Đối chiếu với tên file
              ban tổ chức phát rồi sửa ô <b>Vòng</b> ở trên nếu lệch.
            </>
          )}
        </div>
      )}

      {error && <p className="text-[#c64545] text-sm mb-3">{error}</p>}

      {/* Câu có người làm mà chưa ai quyết định lấy bài của ai thì xuất ra file
          rỗng. Nói ngay từ đầu trang, vì đây là lý do hay gặp nhất khiến bài
          nộp thiếu câu — và chỉ ra đúng chỗ sửa được. */}
      {unchosen.length > 0 && (
        <div className="border border-[#d4a017] bg-[#d4a017]/10 rounded-[10px] px-4 py-2 mb-4 text-[13px] text-[#8a6a0f]">
          <b>{unchosen.length} câu</b> có người làm nhưng chưa chọn nộp bài của
          ai:{" "}
          <span className="font-mono">
            {unchosen.map((task) => task.code).join(", ")}
          </span>
          . Sang tab <b>Evaluation</b> để chọn.
        </div>
      )}

      {/* Bảng cảnh báo đã bỏ cùng nút "Kiểm tra" — xem chú thích đầu file.
          Hai thứ thật sự chặn được bài nộp hỏng vẫn còn: dải vàng liệt kê câu
          có người làm mà chưa chọn nộp bài của ai, và chính nút Tải zip từ
          chối với đúng mã câu khi gặp trường hợp đó. */}

      {/* Danh sách bên trái, nội dung file bên phải, cùng một hàng và cùng
          chiều cao. Trước đây khung xem trước nằm DƯỚI danh sách 25 câu, nên
          bấm "Xem trước" xong là phải cuộn xuống mới thấy, rồi cuộn ngược lên
          mới bấm được câu tiếp — mà so file này với file kia mới là việc chính
          của màn này. items-start để cột nào ngắn hơn thì dừng ở đó, không bị
          kéo dài theo cột kia. */}
      <div className="grid lg:grid-cols-[1fr_440px] gap-5 items-start">
        <div className="border border-proto-line rounded-[10px] bg-white overflow-hidden">
          <div className="px-4 py-2 bg-proto-soft text-[10px] font-bold uppercase tracking-wide text-proto-muted flex gap-4">
            <span className="flex-1">Các file trong gói</span>
            <span className="w-32">Nộp bài của</span>
            <span className="w-24"></span>
          </div>
          <div className="p-3 max-h-[560px] overflow-y-auto">
            {board?.tasks.map((task) => {
              const chosen =
                task.contributors.find((c) => c.id === task.chosen_author_id) ??
                null;
              return (
                <div
                  key={task.id}
                  className={`flex items-center gap-4 px-2 py-1.5 border-b border-proto-line last:border-b-0 text-xs ${
                    task.id === previewTaskId ? "bg-proto-primary/10" : ""
                  }`}
                >
                  <span className="flex-1 flex items-center gap-2 min-w-0">
                    <b className="font-mono text-proto-ink w-8">{task.code}</b>
                    <span className="text-[10px] font-bold uppercase text-proto-muted w-12">
                      {task.type === "qa" ? "Q&A" : task.type}
                    </span>
                    <span className="font-mono text-proto-muted">
                      {/* Số dòng của người được chọn, không phải tổng của cả
                          nhóm: file nộp chỉ chứa bài của một người, nên tổng
                          cộng ở đây là con số không nói lên điều gì. */}
                      {chosen ? `${chosen.count} dòng` : "—"}
                    </span>
                  </span>

                  <span className="w-32 truncate">
                    {task.contributors.length === 0 ? (
                      <span className="text-proto-line">chưa ai làm</span>
                    ) : chosen ? (
                      <b className="text-[#3d7a4d]">{chosen.display_name}</b>
                    ) : (
                      <span className="text-[#c64545]">— chưa chọn —</span>
                    )}
                  </span>

                  <span className="w-24 flex justify-end">
                    <Button
                      size="xs"
                      variant="outline"
                      onClick={() => void look(task.id)}
                    >
                      Xem trước
                    </Button>
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Luôn chiếm chỗ, kể cả khi chưa chọn file nào. Chỉ hiện khi có
            preview thì lần bấm đầu tiên sẽ làm cả bảng bên trái co lại đúng
            lúc con trỏ vừa rời khỏi nút — nhìn như trang bị giật. */}
        <div className="border border-proto-line rounded-[10px] bg-white overflow-hidden">
          <div className="px-4 py-2 bg-proto-soft text-[10px] font-bold uppercase tracking-wide text-proto-muted">
            {preview ? (
              <span className="font-mono normal-case tracking-normal text-[11px] text-proto-ink">
                {preview.filename} · {preview.rows} dòng
              </span>
            ) : (
              "Nội dung file"
            )}
          </div>
          <div className="p-3">
            {preview ? (
              // Cả file, không cắt 12 dòng như trước: cột này giờ cao bằng
              // danh sách bên trái, nên chỗ đủ để cuộn xem hết — mà xem hết
              // mới biết dòng cuối có đúng không.
              <pre className="text-[11px] font-mono bg-proto-soft border border-proto-line rounded p-2 overflow-auto whitespace-pre max-h-[516px]">
                {preview.content.trimEnd()}
              </pre>
            ) : (
              <p className="text-[11.5px] text-proto-muted">
                Bấm <b>Xem trước</b> ở một câu bên trái để đọc đúng nội dung
                file sẽ nằm trong zip.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
