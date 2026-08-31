import { useCallback, useEffect, useState } from "react";

import { getAudit, restoreFromAudit, type AuditEntry } from "../../api/board";
import { ApiRequestError } from "../../api/base";
import Button from "../Button";

/**
 * Ai đã bấm gì, và nút hoàn tác cho những thứ xoá được.
 *
 * Trước đây là một tab con của màn "Vòng". Chuyển xuống cuối màn Evaluation vì
 * đó là nơi người ta đối chiếu bài rồi phát hiện thiếu dòng — và câu hỏi tiếp
 * theo bao giờ cũng là "ai xoá?". Trả lời ngay tại chỗ hơn là bắt đổi màn.
 *
 * Chỉ admin. Endpoint /api/admin/audit chặn ở backend, nên component này gọi
 * cũng vô ích với thành viên thường — chỗ dùng phải tự kiểm vai trò trước.
 */
export default function AuditLog() {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  const reload = useCallback(async () => {
    try {
      setEntries((await getAudit(100)).entries);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Không tải được");
    }
  }, []);

  // Chỉ tải khi mở ra. Đây là 100 dòng nhật ký nằm dưới một màn mà việc chính
  // là so bài — kéo về mỗi lần đổi câu là trả tiền cho thứ không ai nhìn.
  useEffect(() => {
    if (open) void reload();
  }, [open, reload]);

  const restore = async (entry: AuditEntry) => {
    setBusy(true);
    try {
      await restoreFromAudit(entry.id);
      await reload();
      setError(null);
      setNote(`Đã khôi phục ${entry.restorable} dòng.`);
    } catch (err) {
      setNote(null);
      setError(err instanceof ApiRequestError ? err.message : "Thao tác hỏng");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-6 font-baloo">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="text-[12.5px] px-3 py-1 rounded-[7px] border border-proto-line text-proto-muted"
      >
        {open ? "Ẩn nhật ký" : "Nhật ký — ai đã bấm gì"}
      </button>

      {open && (
        <div className="mt-3">
          {error && <p className="text-[#c64545] text-sm mb-2">{error}</p>}
          {note && <p className="text-[#3d7a4d] text-sm mb-2">{note}</p>}

          {entries === null ? (
            <p className="text-sm text-proto-muted">Đang tải…</p>
          ) : entries.length === 0 ? (
            <p className="text-sm text-proto-muted">
              Chưa có gì được ghi lại. Mọi lần nhập, kích hoạt và xoá từ nay sẽ
              nằm ở đây.
            </p>
          ) : (
            <div className="border border-proto-line rounded-[10px] overflow-hidden bg-white">
              {entries.map((entry) => (
                <div
                  key={entry.id}
                  className="flex items-center gap-3 flex-wrap px-3 py-2 border-b border-proto-line last:border-b-0 text-[13px]"
                >
                  <span className="font-mono text-[11.5px] text-proto-muted w-[150px] shrink-0">
                    {entry.at.replace("T", " ").replace("Z", "")}
                  </span>
                  <span className="text-proto-ink w-[110px] shrink-0 truncate">
                    {entry.by.display_name}
                  </span>
                  <span className="text-proto-body flex-1 min-w-[220px]">
                    {entry.summary}
                  </span>
                  {entry.restored_at ? (
                    <span className="text-[11px] text-[#3d7a4d]">
                      đã khôi phục
                    </span>
                  ) : entry.restorable > 0 ? (
                    <Button
                      size="xs"
                      variant="outline"
                      disabled={busy}
                      onClick={() => void restore(entry)}
                    >
                      Khôi phục {entry.restorable} dòng
                    </Button>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
