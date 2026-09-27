import { useState } from "react";

import {
  DEFAULT_PATTERN,
  commitPack,
  previewPack,
  type PreviewResponse,
  type PreviewedFile,
} from "../api/board";
import { ApiRequestError } from "../api/base";
import Button from "../components/Button";
import RoundList from "../components/RoundList";

/**
 * Drop the archive, look at what came out, commit.
 *
 * Preview writes nothing, so the middle step is where a wrong regex or a
 * mis-inferred Q&A question gets caught — which is the whole point of having a
 * middle step. The pattern is a field rather than a constant because the
 * organizer has not frozen the filename format.
 *
 * Committing creates the round and stops there. It used to also make the new
 * round the live one, which is how a second import could take the round being
 * competed in off every board at once. Going live is a separate decision, made
 * on the rounds screen in front of the numbers it costs.
 */
export default function ImportPack() {
  // Nhập xong thì tăng số này để danh sách vòng bên dưới tải lại — vòng vừa
  // tạo phải hiện ra ngay, không phải bấm F5 mới thấy.
  const [roundsToken, setRoundsToken] = useState(0);
  const [pattern, setPattern] = useState(DEFAULT_PATTERN);
  const [label, setLabel] = useState("Vòng 1");
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const upload = async (file: File) => {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const next = await previewPack(file, pattern);
      setPreview(next);
      setEdits({});
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Không đọc được file");
    } finally {
      setBusy(false);
    }
  };

  const commit = async () => {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      const result = await commitPack({
        preview_token: preview.preview_token,
        round_label: label,
        filename_pattern: pattern,
        source_filename: preview.source_filename,
        edits: Object.entries(edits).map(([filename, count]) => ({
          filename,
          n_events: Number(count) >= 1 ? Number(count) : null,
        })),
      });
      // No automatic jump to the board any more. The new round is not active,
      // so the board would still be showing the old one — which reads exactly
      // like the import having done nothing. Say what happened and where to go.
      setDone(
        `Đã tạo ${result.tasks_created} task ở vòng “${result.round_label}”` +
          (result.skipped ? `, bỏ qua ${result.skipped} file` : "") +
          " — chưa kích hoạt."
      );
      setPreview(null);
      setRoundsToken((value) => value + 1);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Không lưu được");
    } finally {
      setBusy(false);
    }
  };

  const matched = preview?.files.filter((f) => f.matched) ?? [];
  const skipped = preview?.files.filter((f) => !f.matched) ?? [];

  // Câu TRAKE chưa gõ số mốc. Backend cũng từ chối, nhưng để nó từ chối thì
  // người dùng bấm xong mới biết, và thông báo lỗi chỉ nêu tên file — còn ở
  // đây khoanh đỏ được đúng ô phải điền.
  const missingEvents = matched.filter(
    (file) => file.type === "trake" && !(Number(edits[file.filename]) >= 1)
  );

  return (
    <div className="max-w-[1200px] mx-auto p-6 font-baloo">
      <h2 className="text-2xl text-proto-ink mb-1">Nhập gói truy vấn</h2>
      <p className="text-sm text-proto-muted mb-5">
        Thả file zip của ban tổ chức. Bước xem trước không ghi gì vào cơ sở dữ
        liệu — sửa xong mới bấm tạo task.
      </p>

      <div className="flex gap-3 flex-wrap items-end mb-4">
        <label className="flex flex-col gap-1 flex-1 min-w-[320px]">
          <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
            Mẫu tên file (regex)
          </span>
          <input
            className="p-2.5 rounded-[8px] bg-proto-soft border border-proto-line font-mono text-xs"
            value={pattern}
            onChange={(e) => setPattern(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 w-[180px]">
          <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
            Tên vòng
          </span>
          <input
            className="p-2.5 rounded-[8px] bg-proto-soft border border-proto-line"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
        </label>
      </div>

      <label
        className="block border-2 border-dashed border-proto-line rounded-[10px] p-8 text-center cursor-pointer bg-proto-soft hover:border-proto-primary"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const file = e.dataTransfer.files[0];
          if (file) void upload(file);
        }}
      >
        <input
          type="file"
          accept=".zip"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void upload(file);
          }}
        />
        <span className="text-sm text-proto-muted">
          {busy ? "Đang đọc…" : "Kéo file .zip vào đây, hoặc bấm để chọn"}
        </span>
      </label>

      {error && <p className="text-[#c64545] text-sm mt-3">{error}</p>}
      {done && (
        <div className="flex items-center gap-3 flex-wrap mt-4 px-4 py-3 rounded-[10px] border border-[#5db872] bg-[#5db872]/10">
          <span className="text-sm text-[#3d7a4d]">{done}</span>
          {/* Nút "Sang màn Vòng" đã bỏ — bảng vòng giờ nằm ngay bên
              dưới, không còn màn nào để sang. */}
          <span className="ml-auto text-[12.5px] text-proto-muted">
            Kích hoạt ở bảng bên dưới.
          </span>
        </div>
      )}

      {preview && (
        <>
          <div className="flex items-center gap-3 mt-6 mb-2 flex-wrap">
            <b className="text-proto-ink">{matched.length} file khớp</b>
            {skipped.length > 0 && (
              <span className="text-sm text-proto-muted">
                {skipped.length} file bỏ qua
              </span>
            )}
            {missingEvents.length > 0 && (
              <span className="text-sm text-[#c64545]">
                Còn {missingEvents.length} câu TRAKE chưa có số mốc
              </span>
            )}
            <span className="ml-auto">
              {/* Chặn ở đây thay vì để lỗi nổ sau khi bấm: một câu TRAKE
                  không có số mốc sẽ xuất ra đúng một cột frame như câu KIS,
                  bốn mốc thành một, không cảnh báo nào. */}
              <Button
                onClick={() => void commit()}
                disabled={busy || !matched.length || missingEvents.length > 0}
              >
                Tạo {matched.length} task
              </Button>
            </span>
          </div>

          <div className="border border-proto-line rounded-[10px] overflow-hidden bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-proto-soft text-[10px] uppercase tracking-wide text-proto-muted">
                  <th className="text-left px-3 py-2 w-16">Mã</th>
                  <th className="text-left px-3 py-2 w-20">Loại</th>
                  <th className="text-left px-3 py-2">Đề bài</th>
                  {/* Tiêu đề cũ là "Suy ra" — đúng khi cột đó bày thứ trình
                      đọc đoán ra. Giờ nó là chỗ người nhập điền. */}
                  <th className="text-left px-3 py-2 w-[180px]">Cần điền</th>
                </tr>
              </thead>
              <tbody>
                {matched.map((file) => (
                  <Row
                    key={file.filename}
                    file={file}
                    edited={edits[file.filename]}
                    onEdit={(value) =>
                      setEdits((prev) => ({ ...prev, [file.filename]: value }))
                    }
                  />
                ))}
                {skipped.map((file) => (
                  <tr key={file.filename} className="border-t border-proto-line opacity-60">
                    <td className="px-3 py-2 text-proto-muted" colSpan={2}>
                      <span className="font-mono text-xs">{file.filename}</span>
                    </td>
                    <td className="px-3 py-2 text-proto-muted text-xs" colSpan={2}>
                      bỏ qua — {file.error}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Danh sách vòng, gộp từ màn "Vòng" cũ. Hai việc luôn đi liền nhau:
          nhập gói xong thì việc kế tiếp là kích hoạt nó. Tách hai màn buộc
          người dùng chuyển tab mới thấy kết quả của lần nhập vừa rồi. */}
      <div className="mt-8 pt-6 border-t border-proto-line">
        <RoundList reloadToken={roundsToken} />
      </div>
    </div>
  );
}

function Row({
  file,
  edited,
  onEdit,
}: {
  file: PreviewedFile;
  /** Số mốc đang gõ, dạng chữ vì ô có thể trống giữa chừng. */
  edited?: string;
  onEdit: (value: string) => void;
}) {
  return (
    <tr className="border-t border-proto-line align-top">
      <td className="px-3 py-2 font-mono font-bold text-proto-ink">{file.code}</td>
      <td className="px-3 py-2">
        <span className="text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-proto-dark text-proto-canvas">
          {file.type === "qa" ? "Q&A" : file.type?.toUpperCase()}
        </span>
      </td>
      {/* Nguyên văn, xuống dòng giữ nguyên: các mốc của câu TRAKE nằm ở đây
          chứ không còn ở cột bên phải, nên gộp chúng thành một đoạn liền là
          làm khó chính người đang phải đếm chúng. Không kẹp `line-clamp` nữa
          vì lý do đó. */}
      <td className="px-3 py-2 text-proto-body">
        <span className="whitespace-pre-wrap">{file.query_text}</span>
        {file.warnings.map((warning) => (
          <span
            key={warning}
            className="block text-[11px] text-[#c64545] mt-1 bg-[#c64545]/8 rounded px-2 py-0.5"
          >
            ⚠ {warning}
          </span>
        ))}
      </td>
      {/* Ô sửa câu hỏi Q&A đã bỏ. Nó sửa lại thứ trình đọc ĐOÁN ra — câu cuối
          có dấu "?" — mà giờ không còn ai đoán: đề bài Q&A vào nguyên văn và
          nằm trọn ở cột bên trái.

          Cột này giờ chỉ còn một việc, và là việc duy nhất không đọc được từ
          chữ: câu TRAKE có mấy mốc. */}
      <td className="px-3 py-2 text-xs text-proto-muted">
        {file.type === "trake" ? (
          <label className="flex flex-col gap-1">
            <span className="font-bold text-proto-ink">Số mốc *</span>
            <input
              type="number"
              min={1}
              max={20}
              className={`w-20 p-1.5 rounded-[6px] bg-proto-soft border text-proto-ink font-mono text-right ${
                edited && Number(edited) >= 1
                  ? "border-proto-line"
                  : "border-[#c64545]"
              }`}
              value={edited ?? ""}
              placeholder="?"
              onChange={(e) => onEdit(e.target.value)}
            />
            <span className="text-[10.5px] leading-tight">
              Đếm trong đề bài bên trái
            </span>
          </label>
        ) : (
          <span>{file.lines} dòng</span>
        )}
      </td>
    </tr>
  );
}
