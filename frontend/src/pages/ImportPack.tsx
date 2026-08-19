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

/**
 * Drop the archive, look at what came out, commit.
 *
 * Preview writes nothing, so the middle step is where a wrong regex or a
 * mis-inferred Q&A question gets caught — which is the whole point of having a
 * middle step. The pattern is a field rather than a constant because the
 * organizer has not frozen the filename format.
 */
export default function ImportPack({
  onImported,
}: {
  onImported: () => void;
}) {
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
        edits: Object.entries(edits).map(([filename, question_text]) => ({
          filename,
          question_text,
        })),
      });
      setDone(
        `Đã tạo ${result.tasks_created} task, bỏ qua ${result.skipped} file.`
      );
      setPreview(null);
      onImported();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Không lưu được");
    } finally {
      setBusy(false);
    }
  };

  const matched = preview?.files.filter((f) => f.matched) ?? [];
  const skipped = preview?.files.filter((f) => !f.matched) ?? [];

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
      {done && <p className="text-[#3d7a4d] text-sm mt-3">{done}</p>}

      {preview && (
        <>
          <div className="flex items-center gap-3 mt-6 mb-2 flex-wrap">
            <b className="text-proto-ink">{matched.length} file khớp</b>
            {skipped.length > 0 && (
              <span className="text-sm text-proto-muted">
                {skipped.length} file bỏ qua
              </span>
            )}
            <span className="ml-auto">
              <Button onClick={() => void commit()} disabled={busy || !matched.length}>
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
                  <th className="text-left px-3 py-2 w-[280px]">Suy ra</th>
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
    </div>
  );
}

function Row({
  file,
  edited,
  onEdit,
}: {
  file: PreviewedFile;
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
      <td className="px-3 py-2 text-proto-body">
        <span className="line-clamp-2">{file.query_text}</span>
        {file.warnings.map((warning) => (
          <span
            key={warning}
            className="block text-[11px] text-[#c64545] mt-1 bg-[#c64545]/8 rounded px-2 py-0.5"
          >
            ⚠ {warning}
          </span>
        ))}
      </td>
      <td className="px-3 py-2 text-xs text-proto-muted">
        {file.type === "qa" ? (
          <>
            <span className="block mb-1">Câu hỏi (sửa được):</span>
            <input
              className="w-full p-1.5 rounded-[6px] bg-proto-soft border border-proto-line text-proto-ink"
              value={edited ?? file.question_text ?? ""}
              placeholder="không tách được câu hỏi"
              onChange={(e) => onEdit(e.target.value)}
            />
          </>
        ) : file.type === "trake" ? (
          <>
            <b className="text-proto-ink">{file.n_events} mốc</b>
            <ol className="list-none mt-1 space-y-0.5">
              {file.event_labels.map((label, index) => (
                <li key={index} className="truncate">
                  <b className="text-[#a9583e]">E{index + 1}</b> {label}
                </li>
              ))}
            </ol>
          </>
        ) : (
          <span>{file.lines} dòng</span>
        )}
      </td>
    </tr>
  );
}
