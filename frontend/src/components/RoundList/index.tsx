import { useCallback, useEffect, useState } from "react";

import {
  activatePack,
  deletePack,
  listPacks,
  patchPack,
  type RoundPack,
} from "../../api/board";
import { ApiRequestError } from "../../api/base";
import Button from "../Button";

/**
 * Các vòng đã nhập, và vòng nào đang được dùng.
 *
 * Trước đây là màn "Vòng" riêng. Gộp xuống dưới màn Import vì hai việc luôn đi
 * liền nhau: nhập gói xong thì việc kế tiếp là kích hoạt nó, mà trước đó phải
 * chuyển tab mới thấy kết quả của lần nhập vừa rồi.
 *
 * Xoá là VĨNH VIỄN — nút "Khôi phục" đã bỏ. Hai thứ chặn mất bài vẫn còn:
 * không xoá được vòng đang thi, và mỗi lần xoá đều ghi vào nhật ký kèm số task
 * và số đáp án đã mất.
 *
 * Nhập gói KHÔNG tự đổi vòng đang thi. Ngày trước nó tự đổi và không nói gì,
 * nên lần nhập thứ hai gạt vòng đang thi khỏi mọi màn hình — đúng vụ "mất toàn
 * bộ task" không ai giải thích được. Chẳng có gì bị xoá cả, chỉ bị ngừng kích
 * hoạt. Giờ đổi vòng là một quyết định, bấm ở đây, trước mặt những con số nó
 * đánh đổi.
 *
 * @param reloadToken đổi giá trị để buộc tải lại — màn Import tăng nó sau mỗi
 *   lần nhập xong, để vòng mới hiện ra ngay bên dưới.
 */
export default function RoundList({
  reloadToken = 0,
}: {
  reloadToken?: number;
}) {
  const [packs, setPacks] = useState<RoundPack[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Hàng nào đang cách một cú bấm nữa là làm chuyện khó lùi. Hai bước thay cho
  // window.confirm, giống màn Export.
  const [confirming, setConfirming] = useState<
    { kind: "activate" | "delete"; id: number } | null
  >(null);
  const [renaming, setRenaming] = useState<{ id: number; label: string } | null>(
    null
  );

  const reload = useCallback(async () => {
    try {
      setPacks((await listPacks()).packs);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Không tải được");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload, reloadToken]);

  const act = async (fn: () => Promise<unknown>, done?: string) => {
    setBusy(true);
    try {
      await fn();
      await reload();
      setConfirming(null);
      setRenaming(null);
      setError(null);
      setNote(done ?? null);
    } catch (err) {
      setNote(null);
      setError(err instanceof ApiRequestError ? err.message : "Thao tác hỏng");
    } finally {
      setBusy(false);
    }
  };

  const live = packs?.find((pack) => pack.active) ?? null;

  return (
    <div className="font-baloo">
      <h3 className="text-lg text-proto-ink mb-1">
        Các vòng đã nhập{packs ? ` (${packs.length})` : ""}
      </h3>
      <p className="text-sm text-proto-muted mb-3">
        Nhập gói chỉ tạo vòng mới, không đụng vào vòng đang thi. Chọn vòng nào
        được dùng ở đây.
      </p>

      {error && <p className="text-[#c64545] text-sm mb-2">{error}</p>}
      {note && <p className="text-[#3d7a4d] text-sm mb-2">{note}</p>}

      <div className="border border-proto-line rounded-[10px] overflow-hidden bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-proto-soft text-[10px] uppercase tracking-wide text-proto-muted">
              <th className="text-left px-3 py-2">Vòng</th>
              <th className="text-left px-3 py-2 w-40">Nhập lúc</th>
              <th className="text-right px-3 py-2 w-16">Task</th>
              <th className="text-right px-3 py-2 w-20">Đáp án</th>
              <th className="text-left px-3 py-2 w-28">Trạng thái</th>
              <th className="px-3 py-2 w-[300px]"></th>
            </tr>
          </thead>
          <tbody>
            {packs?.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-proto-muted">
                  Chưa nhập gói nào. Thả file zip ở khung phía trên.
                </td>
              </tr>
            )}
            {packs?.map((pack) => (
              <Row
                key={pack.id}
                pack={pack}
                live={live}
                busy={busy}
                confirming={confirming}
                renaming={renaming}
                onConfirm={setConfirming}
                onRename={setRenaming}
                onAct={act}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Row({
  pack,
  live,
  busy,
  confirming,
  renaming,
  onConfirm,
  onRename,
  onAct,
}: {
  pack: RoundPack;
  live: RoundPack | null;
  busy: boolean;
  confirming: { kind: "activate" | "delete"; id: number } | null;
  renaming: { id: number; label: string } | null;
  onConfirm: (value: { kind: "activate" | "delete"; id: number } | null) => void;
  onRename: (value: { id: number; label: string } | null) => void;
  onAct: (fn: () => Promise<unknown>, done?: string) => Promise<void>;
}) {
  const deleted = pack.deleted_at !== null;
  const askingActivate =
    confirming?.kind === "activate" && confirming.id === pack.id;
  const askingDelete = confirming?.kind === "delete" && confirming.id === pack.id;
  const editing = renaming?.id === pack.id;

  return (
    <tr
      className={`border-t border-proto-line align-top ${
        deleted ? "opacity-55" : ""
      }`}
    >
      <td className="px-3 py-2">
        {editing ? (
          <input
            autoFocus
            className="w-full p-1.5 rounded-[6px] bg-proto-soft border border-proto-line text-proto-ink"
            value={renaming.label}
            onChange={(e) => onRename({ id: pack.id, label: e.target.value })}
            onKeyDown={(e) => {
              if (e.key === "Escape") onRename(null);
              if (e.key === "Enter") {
                void onAct(
                  () => patchPack(pack.id, { round_label: renaming.label }),
                  "Đã đổi tên."
                );
              }
            }}
          />
        ) : (
          <>
            <b className="text-proto-ink">{pack.label}</b>
            <span className="block text-[11px] text-proto-muted font-mono truncate">
              {pack.source_filename}
            </span>
          </>
        )}
      </td>
      <td className="px-3 py-2 text-proto-muted text-[12px]">
        <span className="font-mono">
          {pack.imported_at.replace("T", " ").replace("Z", "")}
        </span>
        <span className="block">{pack.imported_by?.display_name ?? "—"}</span>
      </td>
      <td className="px-3 py-2 text-right font-mono tabular-nums">
        {pack.task_count}
      </td>
      <td className="px-3 py-2 text-right font-mono tabular-nums">
        {pack.answer_count}
      </td>
      <td className="px-3 py-2">
        {deleted ? (
          <span className="text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-[#c64545]/15 text-[#8f3030]">
            Đã xoá
          </span>
        ) : pack.active ? (
          <span className="text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-[#5db872]/20 text-[#3d7a4d]">
            Đang dùng
          </span>
        ) : (
          <span className="text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-proto-cream-strong text-proto-muted">
            Chưa dùng
          </span>
        )}
      </td>
      <td className="px-3 py-2 text-right">
        {editing ? (
          <span className="inline-flex gap-2 items-center">
            <Button
              size="xs"
              disabled={busy}
              onClick={() =>
                void onAct(
                  () => patchPack(pack.id, { round_label: renaming.label }),
                  "Đã đổi tên."
                )
              }
            >
              Lưu
            </Button>
            <button
              type="button"
              className="text-[11px] text-proto-muted underline"
              onClick={() => onRename(null)}
            >
              Huỷ
            </button>
          </span>
        ) : askingActivate ? (
          <span className="inline-flex flex-col items-end gap-1">
            <span className="text-[11.5px] text-proto-body text-right">
              {live && live.id !== pack.id ? (
                <>
                  <b>{live.label}</b> ({live.task_count} task,{" "}
                  {live.answer_count} đáp án) sẽ ngừng hiển thị.
                </>
              ) : (
                "Vòng này sẽ thành vòng đang dùng."
              )}
            </span>
            <span className="inline-flex gap-2 items-center">
              <Button
                size="xs"
                disabled={busy}
                onClick={() =>
                  void onAct(
                    () => activatePack(pack.id),
                    `Đang dùng vòng “${pack.label}”.`
                  )
                }
              >
                Kích hoạt “{pack.label}”
              </Button>
              <button
                type="button"
                className="text-[11px] text-proto-muted underline"
                onClick={() => onConfirm(null)}
              >
                Huỷ
              </button>
            </span>
          </span>
        ) : askingDelete ? (
          <span className="inline-flex gap-2 items-center">
            {/* Nói thẳng là mất hẳn. Trước đây câu xác nhận hứa "khôi phục lại
                được bất cứ lúc nào" — giữ nguyên chữ đó sau khi bỏ nút khôi
                phục là nói dối người dùng ngay tại nút nguy hiểm nhất màn. */}
            <button
              type="button"
              className="text-[11.5px] font-bold text-[#c64545] underline"
              onClick={() =>
                void onAct(
                  () => deletePack(pack.id),
                  `Đã xoá vĩnh viễn “${pack.label}”.`
                )
              }
            >
              Xoá vĩnh viễn {pack.task_count} task, {pack.answer_count} đáp án?
            </button>
            <button
              type="button"
              className="text-[11px] text-proto-muted underline"
              onClick={() => onConfirm(null)}
            >
              Huỷ
            </button>
          </span>
        ) : (
          <span className="inline-flex gap-1.5 items-center">
            {deleted ? (
              // Vòng bị xoá mềm TRƯỚC khi bỏ tính năng này. Danh sách mặc định
              // không trả chúng về nữa nên nhánh này gần như không chạy tới;
              // giữ lại để nếu ai gọi API kèm include_deleted thì bảng vẫn vẽ
              // ra được, thay vì hiện một hàng có nút bấm không làm gì.
              <span className="text-[11px] text-proto-muted">
                đã xoá từ trước
              </span>
            ) : (
              <>
                {!pack.active && (
                  <Button
                    size="xs"
                    disabled={busy}
                    onClick={() => onConfirm({ kind: "activate", id: pack.id })}
                  >
                    Kích hoạt
                  </Button>
                )}
                <Button
                  size="xs"
                  variant="outline"
                  disabled={busy}
                  onClick={() => onRename({ id: pack.id, label: pack.label })}
                >
                  Đổi tên
                </Button>
                <Button
                  size="xs"
                  variant="outline"
                  // Xoá vòng đang thi sẽ làm trống mọi bảng cùng lúc — đúng sự
                  // cố mà màn này sinh ra để chấm dứt. Đổi vòng trước đã.
                  disabled={busy || pack.active}
                  title={
                    pack.active
                      ? "Đây là vòng đang dùng. Kích hoạt vòng khác trước."
                      : undefined
                  }
                  onClick={() => onConfirm({ kind: "delete", id: pack.id })}
                >
                  Xoá
                </Button>
              </>
            )}
          </span>
        )}
      </td>
    </tr>
  );
}
