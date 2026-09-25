import { useCallback, useEffect, useState, type ReactNode } from "react";

import {
  canSubmitDres,
  describePayload,
  formatMs,
  getDresCurrentTask,
  getDresEvaluations,
  getDresStatus,
  listDresSubmissions,
  putDresConfig,
  putDresEvaluation,
  putDresSubmitMode,
  rejectDresSubmission,
  type DresSubmitMode,
  type DresEvaluation,
  type DresStatus,
  type DresSubmission,
  type DresTask,
} from "../api/dres";
import Button from "../components/Button";
import { approveWithConfirm } from "../helpers/dresApprove";
import { useAuthStore } from "../store/authStore";

// Câu chung kết chỉ 4–5 phút và mất 10 điểm mỗi phút chờ, nên hàng chờ duyệt
// phải hiện gần như ngay. 3 giây: đủ nhanh, và cả đội 6 máy cũng chỉ 2 req/s.
const POLL_MS = 3000;

const VERDICT_STYLE: Record<string, string> = {
  CORRECT: "bg-[#2f8a4f] text-white",
  WRONG: "bg-[#c64545] text-white",
  INDETERMINATE: "bg-[#d4a017] text-white",
  UNDECIDABLE: "bg-proto-muted text-white",
};

const STATUS_LABEL: Record<string, string> = {
  proposed: "Chờ duyệt",
  sending: "Đang gửi…",
  sent: "Đã gửi",
  failed: "Lỗi — chưa chắc đã tới DRES",
  rejected: "Đã từ chối",
};

function timeOf(iso: string | null): string {
  return iso ? new Date(iso).toLocaleTimeString("vi-VN") : "";
}

/**
 * Màn DRES: câu đang chạy, hàng chờ duyệt, lịch sử nộp của cả đội.
 *
 * Mọi người thấy cùng một danh sách — để hai người không đi đề xuất hai đáp án
 * khác nhau cho cùng một câu mà không biết nhau. Chỉ admin thấy ô tài khoản và
 * công tắc chế độ. Hai nút Duyệt/Từ chối hiện theo chế độ: chỉ admin, hoặc mọi
 * người khi admin bật "Mọi người nộp được" (server cũng khoá theo đúng chế độ
 * đó, đây chỉ là không bày ra nút bấm vô ích).
 */
export default function DresPage({
  onOpenVideo,
}: {
  onOpenVideo: (videoId: string, frameIdx: number) => void;
}) {
  const role = useAuthStore((state) => state.user?.role);
  const isAdmin = role === "admin";
  const [status, setStatus] = useState<DresStatus | null>(null);
  const [task, setTask] = useState<DresTask | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);
  const [submissions, setSubmissions] = useState<DresSubmission[]>([]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [nextStatus, list] = await Promise.all([
        getDresStatus(),
        listDresSubmissions(100),
      ]);
      setStatus(nextStatus);
      setSubmissions(list.submissions);
      if (nextStatus.configured) {
        try {
          setTask((await getDresCurrentTask()).task);
          setTaskError(null);
        } catch (error) {
          setTask(null);
          setTaskError(error instanceof Error ? error.message : String(error));
        }
      }
    } catch {
      // Lần sau cách 3 giây; một lần hỏng không đáng một thông báo.
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const act = async (id: number, action: () => Promise<unknown>) => {
    setBusyId(id);
    setActionError(null);
    try {
      await action();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyId(null);
      void refresh();
    }
  };

  const canSubmit = canSubmitDres(role, status);
  const pending = submissions.filter(
    (s) => s.status === "proposed" || s.status === "failed" || s.status === "sending"
  );
  const done = submissions.filter((s) => !pending.includes(s));

  return (
    <main className="max-w-[1100px] mx-auto p-5 font-baloo flex flex-col gap-4">
      <section className="flex flex-wrap items-center gap-x-6 gap-y-1 p-4 rounded-[10px] border border-proto-line bg-proto-soft">
        {!status ? (
          <span className="text-proto-muted text-sm">Đang tải…</span>
        ) : !status.configured ? (
          <span className="text-sm text-[#c64545]">
            Chưa có tài khoản DRES{isAdmin ? " — nhập ở khung bên dưới." : " — nhờ admin nhập."}
          </span>
        ) : (
          <>
            <span className="text-sm">
              <b>{status.username}</b>{" "}
              <span className="text-proto-muted">@ {status.base_url}</span>
            </span>
            <span className="text-sm">
              Evaluation:{" "}
              <b>{status.evaluation_name ?? "chưa chọn"}</b>
            </span>
            <span className="text-sm">
              Chế độ:{" "}
              <b className={status.submit_mode === "everyone" ? "text-[#c64545]" : ""}>
                {status.submit_mode === "everyone" ? "mọi người nộp được" : "chỉ admin nộp"}
              </b>
            </span>
            <span className="text-sm">
              Câu đang chạy:{" "}
              {task ? (
                <b className="text-proto-primary-active">
                  {task.name} · {task.taskType}
                  {task.duration ? ` · ${task.duration}s` : ""}
                </b>
              ) : (
                <span className="text-proto-muted">{taskError ?? "không có"}</span>
              )}
            </span>
          </>
        )}
      </section>

      {isAdmin && status?.configured && (
        <SubmitModeSwitch
          mode={status.submit_mode}
          onChanged={(next) => {
            setStatus(next);
            void refresh();
          }}
        />
      )}

      {isAdmin && (
        <DresConfigCard
          status={status}
          onSaved={(next) => {
            setStatus(next);
            void refresh();
          }}
        />
      )}

      {actionError && (
        <p className="text-sm text-[#c64545] px-1">{actionError}</p>
      )}

      <section className="flex flex-col gap-2">
        <h2 className="text-[13px] font-bold uppercase tracking-wide text-proto-muted">
          Chờ duyệt ({pending.length})
        </h2>
        {pending.length === 0 && (
          <p className="text-sm text-proto-muted">
            Chưa có đề xuất nào. Đề xuất từ popup video, mục "Nộp DRES".
          </p>
        )}
        {pending.map((s) => (
          <SubmissionRow
            key={s.id}
            submission={s}
            currentTaskName={task?.name ?? null}
            onOpenVideo={onOpenVideo}
          >
            {canSubmit && s.status !== "sending" && (
              <div className="flex gap-2">
                <Button
                  size="sm"
                  disabled={busyId !== null}
                  onClick={() => void act(s.id, () => approveWithConfirm(s))}
                >
                  {s.status === "failed" ? "Gửi lại" : "Duyệt & nộp"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busyId !== null}
                  onClick={() => void act(s.id, () => rejectDresSubmission(s.id))}
                >
                  Từ chối
                </Button>
              </div>
            )}
          </SubmissionRow>
        ))}
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-[13px] font-bold uppercase tracking-wide text-proto-muted">
          Lịch sử ({done.length})
        </h2>
        {done.map((s) => (
          <SubmissionRow
            key={s.id}
            submission={s}
            currentTaskName={task?.name ?? null}
            onOpenVideo={onOpenVideo}
          />
        ))}
      </section>
    </main>
  );
}

function SubmissionRow({
  submission: s,
  currentTaskName,
  onOpenVideo,
  children,
}: {
  submission: DresSubmission;
  currentTaskName: string | null;
  onOpenVideo: (videoId: string, frameIdx: number) => void;
  children?: ReactNode;
}) {
  const staleTask =
    s.status === "proposed" &&
    s.dres_task_name !== null &&
    currentTaskName !== null &&
    s.dres_task_name !== currentTaskName;
  return (
    <div className="flex flex-col gap-1.5 p-3 rounded-[10px] border border-proto-line bg-white">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
        <b className="font-mono">#{s.id}</b>
        <span className="px-2 py-0.5 rounded-full bg-proto-soft font-bold text-[11px]">
          {s.task_type.toUpperCase()}
        </span>
        {s.verdict ? (
          <span className={`px-2 py-0.5 rounded-full font-bold text-[11px] ${VERDICT_STYLE[s.verdict] ?? ""}`}>
            {s.verdict}
          </span>
        ) : (
          <span className={s.status === "failed" ? "text-[#c64545]" : "text-proto-muted"}>
            {STATUS_LABEL[s.status]}
          </span>
        )}
        <span className="text-proto-muted">
          {s.proposed_by_name} · {timeOf(s.created_at)}
          {s.reviewed_by_name ? ` → ${s.reviewed_by_name} · ${timeOf(s.reviewed_at)}` : ""}
        </span>
        {s.dres_task_name && (
          <span className={staleTask ? "text-[#c64545] font-bold" : "text-proto-muted"}>
            câu {s.dres_task_name}
            {staleTask ? " — DRES ĐÃ SANG CÂU KHÁC" : ""}
          </span>
        )}
        <button
          type="button"
          className="ml-auto text-[12px] underline text-proto-primary-active"
          onClick={() => onOpenVideo(s.video_id, s.frames[0])}
        >
          Xem khung
        </button>
      </div>
      <code className="text-[13px] break-all bg-proto-soft rounded-[6px] px-2 py-1">
        {describePayload(s)}
      </code>
      <span className="text-[12px] text-proto-muted">
        {s.video_id} · {s.times_ms.map(formatMs).join(", ")} · frame {s.frames.join(", ")}
      </span>
      {s.warnings.map((w) => (
        <span key={w} className="text-[12px] text-[#8a6a0f]">
          ⚠ {w}
        </span>
      ))}
      {(s.error || s.dres_description) && (
        <span className={`text-[12px] ${s.error ? "text-[#c64545]" : "text-proto-muted"}`}>
          DRES: {s.error ?? s.dres_description}
        </span>
      )}
      {children}
    </div>
  );
}

/**
 * Công tắc "ai được nộp". Để ngoài khung tài khoản (luôn mở, không cần bấm ▸):
 * đây là thứ admin có thể muốn đổi GIỮA buổi thi, ví dụ mở cho mọi người khi
 * mình đang bận soát một câu khác.
 */
function SubmitModeSwitch({
  mode,
  onChanged,
}: {
  mode: DresSubmitMode;
  onChanged: (status: DresStatus) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const options: { id: DresSubmitMode; label: string; hint: string }[] = [
    {
      id: "admin_only",
      label: "Chỉ admin nộp",
      hint: "thành viên đề xuất, admin soát rồi mới gửi",
    },
    {
      id: "everyone",
      label: "Mọi người nộp được",
      hint: "ai tìm ra thì tự gửi luôn — nhanh hơn, mất lớp soát thứ hai",
    },
  ];
  const choose = (next: DresSubmitMode) => {
    if (next === mode) {
      return;
    }
    if (
      next === "everyone" &&
      !window.confirm(
        "Cho mọi thành viên tự gửi bài lên DRES?\n\nMỗi lần nộp sai trừ 10 điểm của cả đội."
      )
    ) {
      return;
    }
    setError(null);
    void putDresSubmitMode(next)
      .then(onChanged)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };
  return (
    <section className="flex flex-wrap items-center gap-x-5 gap-y-1 px-4 py-3 rounded-[10px] border border-proto-line bg-white">
      <span className="text-[13px] font-bold uppercase tracking-wide text-proto-muted">
        Ai được nộp
      </span>
      {options.map((o) => (
        <label key={o.id} className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="radio"
            name="dres-submit-mode"
            checked={mode === o.id}
            onChange={() => choose(o.id)}
          />
          <b>{o.label}</b>
          <span className="text-proto-muted text-[12px]">{o.hint}</span>
        </label>
      ))}
      {error && <span className="text-sm text-[#c64545]">{error}</span>}
    </section>
  );
}

function DresConfigCard({
  status,
  onSaved,
}: {
  status: DresStatus | null;
  onSaved: (status: DresStatus) => void;
}) {
  const [open, setOpen] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [evaluations, setEvaluations] = useState<DresEvaluation[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // Mở sẵn khi chưa cấu hình — đó là việc duy nhất admin làm được ở màn này.
  useEffect(() => {
    if (status && !status.configured) {
      setOpen(true);
    }
    if (status) {
      setBaseUrl((current) => current || status.base_url);
      setUsername((current) => current || status.username || "");
    }
  }, [status]);

  const save = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const saved = await putDresConfig({ base_url: baseUrl, username, password });
      setPassword("");
      setEvaluations(saved.evaluations);
      setMessage(
        saved.evaluation_name
          ? `Đăng nhập được. Đã chọn evaluation "${saved.evaluation_name}".`
          : saved.evaluations.length === 0
            ? "Đăng nhập được. DRES chưa mở evaluation nào cho đội."
            : "Đăng nhập được. Chọn evaluation bên dưới."
      );
      onSaved(saved);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const loadEvaluations = async () => {
    setMessage(null);
    try {
      setEvaluations((await getDresEvaluations()).evaluations);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  };

  const field = "p-2 rounded-[8px] bg-proto-soft border border-proto-line text-sm";
  return (
    <section className="p-4 rounded-[10px] border border-proto-line bg-white flex flex-col gap-2">
      <button
        type="button"
        className="text-left text-[13px] font-bold uppercase tracking-wide text-proto-muted"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "▾" : "▸"} Tài khoản DRES (admin)
      </button>
      {open && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <input className={field} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://eventretrieval.one" />
            <input className={field} value={username} onChange={(e) => setUsername(e.target.value)}
              placeholder="username đội" autoComplete="off" />
            <input className={field} type="password" value={password}
              onChange={(e) => setPassword(e.target.value)} autoComplete="new-password"
              placeholder={status?.configured ? "để trống = giữ mật khẩu cũ" : "mật khẩu"} />
          </div>
          <div className="flex flex-wrap gap-2 items-center">
            <Button size="sm" disabled={busy || !baseUrl || !username} onClick={() => void save()}>
              {busy ? "Đang đăng nhập…" : "Lưu & đăng nhập"}
            </Button>
            {status?.configured && (
              <Button size="sm" variant="outline" onClick={() => void loadEvaluations()}>
                Tải danh sách evaluation
              </Button>
            )}
            {message && <span className="text-sm text-proto-muted">{message}</span>}
          </div>
          {evaluations.length > 0 && (
            <div className="flex flex-col gap-1">
              {evaluations.map((ev) => (
                <label key={ev.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="dres-evaluation"
                    checked={status?.evaluation_id === ev.id}
                    onChange={() =>
                      void putDresEvaluation(ev.id)
                        .then(onSaved)
                        .catch((error) => setMessage(error instanceof Error ? error.message : String(error)))
                    }
                  />
                  <b>{ev.name}</b>
                  <span className="text-proto-muted">{ev.status} · {ev.type}</span>
                </label>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
