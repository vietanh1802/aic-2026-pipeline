import { useCallback, useEffect, useState } from "react";

import {
  activatePack,
  deletePack,
  getAudit,
  listPacks,
  patchPack,
  restoreFromAudit,
  restorePack,
  type AuditEntry,
  type RoundPack,
} from "../api/board";
import { ApiRequestError } from "../api/base";
import Button from "../components/Button";

/**
 * Which round the team is working in, and who changed what.
 *
 * Importing used to decide this by itself and say nothing, so a second import
 * took the live round off every board at once — the "mất toàn bộ task" nobody
 * could explain. Nothing was ever deleted; it was deactivated. Switching rounds
 * is a decision now, made here, in front of the numbers it costs.
 */
export default function Rounds() {
  const [tab, setTab] = useState<"rounds" | "log">("rounds");
  const [packs, setPacks] = useState<RoundPack[] | null>(null);
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Which row is one click from doing something irreversible-looking. Two
  // clicks rather than window.confirm, matching the export screen.
  const [confirming, setConfirming] = useState<
    { kind: "activate" | "delete"; id: number } | null
  >(null);
  const [renaming, setRenaming] = useState<{ id: number; label: string } | null>(
    null
  );

  const reload = useCallback(async () => {
    try {
      const [packsResult, auditResult] = await Promise.all([
        listPacks(),
        getAudit(100),
      ]);
      setPacks(packsResult.packs);
      setEntries(auditResult.entries);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Không tải được");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

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
    <div className="max-w-[1200px] mx-auto p-6 font-baloo">
      <h2 className="text-2xl text-proto-ink mb-1">Vòng thi</h2>
      <p className="text-sm text-proto-muted mb-5">
        Nhập gói chỉ tạo vòng mới, không đụng vào vòng đang thi. Chọn vòng nào
        được dùng ở đây.
      </p>

      <div className="flex gap-1 mb-4">
        {(
          [
            ["rounds", `Vòng${packs ? ` (${packs.length})` : ""}`],
            ["log", "Nhật ký"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`text-[12.5px] px-3 py-1 rounded-[7px] border ${
              tab === id
                ? "bg-proto-cream-strong border-proto-cream-strong text-proto-ink font-semibold"
                : "border-proto-line text-proto-muted"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {error && <p className="text-[#c64545] text-sm mb-2">{error}</p>}
      {note && <p className="text-[#3d7a4d] text-sm mb-2">{note}</p>}

      {tab === "rounds" ? (
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
                    Chưa nhập gói nào. Vào tab Import để thả file zip.
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
      ) : (
        <Log entries={entries} busy={busy} onAct={act} />
      )}
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
        <span className="font-mono">{pack.imported_at.replace("T", " ").replace("Z", "")}</span>
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
                  <b>{live.label}</b> ({live.task_count} task, {live.answer_count}{" "}
                  đáp án) sẽ ngừng hiển thị.
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
            <button
              type="button"
              className="text-[11.5px] font-bold text-[#c64545] underline"
              onClick={() =>
                void onAct(
                  () => deletePack(pack.id),
                  `Đã xoá “${pack.label}”. Khôi phục lại được bất cứ lúc nào.`
                )
              }
            >
              Xoá {pack.task_count} task, {pack.answer_count} đáp án?
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
              <Button
                size="xs"
                disabled={busy}
                onClick={() =>
                  void onAct(
                    () => restorePack(pack.id),
                    `Đã khôi phục “${pack.label}”.`
                  )
                }
              >
                Khôi phục
              </Button>
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
                  // Deleting the round in play would empty every board at once —
                  // the exact failure this screen exists to end. Switch first.
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

function Log({
  entries,
  busy,
  onAct,
}: {
  entries: AuditEntry[] | null;
  busy: boolean;
  onAct: (fn: () => Promise<unknown>, done?: string) => Promise<void>;
}) {
  if (entries === null) {
    return <p className="text-sm text-proto-muted">Đang tải…</p>;
  }
  if (entries.length === 0) {
    return (
      <p className="text-sm text-proto-muted">
        Chưa có gì được ghi lại. Mọi lần nhập, kích hoạt và xoá từ nay sẽ nằm ở
        đây.
      </p>
    );
  }

  return (
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
            <span className="text-[11px] text-[#3d7a4d]">đã khôi phục</span>
          ) : entry.restorable > 0 ? (
            <Button
              size="xs"
              variant="outline"
              disabled={busy}
              onClick={() =>
                void onAct(async () => {
                  const result = await restoreFromAudit(entry.id);
                  return result;
                }, `Đã khôi phục ${entry.restorable} dòng.`)
              }
            >
              Khôi phục {entry.restorable} dòng
            </Button>
          ) : null}
        </div>
      ))}
    </div>
  );
}
