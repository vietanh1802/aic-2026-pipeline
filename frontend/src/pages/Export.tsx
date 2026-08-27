import { useEffect, useRef, useState } from "react";

import {
  clearAnswers,
  getAnswers,
  previewExport,
  validateExport,
  type AnswerRow,
  type ExportIssue,
} from "../api/answers";
import { API_BASE_URL, ApiRequestError } from "../api/base";
import {
  getBoard,
  listPacks,
  type BoardResponse,
  type BoardTask,
  type RoundPack,
} from "../api/board";
import Button from "../components/Button";
import FramePreview from "../components/FramePreview";
import { startMsAt } from "../helpers/frameIdentity";
import { taskBriefText } from "../helpers/taskBrief";
import { videoUrlAt } from "../helpers/videoSource";
import { useAuthStore } from "../store/authStore";

/**
 * Validate, look at one file, download the round.
 */
export default function ExportPage() {
  const token = useAuthStore((state) => state.token);
  const user = useAuthStore((state) => state.user);
  const [board, setBoard] = useState<BoardResponse | null>(null);
  const [issues, setIssues] = useState<ExportIssue[] | null>(null);
  const [ready, setReady] = useState<boolean | null>(null);
  const [preview, setPreview] = useState<{
    filename: string;
    rows: number;
    content: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Which task's "Xoá sạch" is waiting for a second click.
  const [confirming, setConfirming] = useState<number | null>(null);

  // The task open in the right-hand inspector, and its answers once loaded.
  // Clicking a row in the left list sets this; "▶ Top-1" sets it too and also
  // picks the rank-1 row, since reviewing a query is mostly reviewing its
  // first row — R@1 is a fifth of the score.
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [answers, setAnswers] = useState<AnswerRow[] | null>(null);
  const [answersLoading, setAnswersLoading] = useState(false);
  // The row the player is parked on. Set by a click, never by hovering.
  const [selectedAnswerId, setSelectedAnswerId] = useState<number | null>(
    null
  );
  const [briefExpanded, setBriefExpanded] = useState(false);
  // Pointing at a row previews its still; only a click moves the player.
  // Sweeping the list to compare frames should not yank the video around.
  const [hoveredAnswerId, setHoveredAnswerId] = useState<number | null>(null);

  // The mounted player, so a row click on the same video can seek in place
  // instead of the `src` change that a video swap needs.
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [activeVideoId, setActiveVideoId] = useState("");
  const [videoSrc, setVideoSrc] = useState("");

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
  const selectedTask =
    board?.tasks.find((task) => task.id === selectedTaskId) ?? null;
  const selectedAnswer =
    answers?.find((row) => row.id === selectedAnswerId) ?? null;
  // Only what the pointer is on. Falling back to the clicked row would leave a
  // still permanently parked over the player, which is what it is not for.
  const hoveredAnswer =
    answers?.find((row) => row.id === hoveredAnswerId) ?? null;

  // A different video needs a new `src` — changing it is what makes the
  // browser reload the file. The same video just needs the element's
  // currentTime nudged, which never touches `src` and so never remounts.
  useEffect(() => {
    if (!selectedAnswer) {
      return;
    }
    const seconds =
      startMsAt(selectedAnswer.video_id, selectedAnswer.frames[0] ?? 0) /
      1000;
    if (selectedAnswer.video_id !== activeVideoId) {
      setActiveVideoId(selectedAnswer.video_id);
      setVideoSrc(videoUrlAt(selectedAnswer.video_id, seconds));
      return;
    }
    const element = videoRef.current;
    if (element) {
      element.currentTime = seconds;
    }
  }, [selectedAnswer, activeVideoId]);

  const refreshBoard = async () => {
    setBoard(await getBoard(viewing ?? undefined));
  };

  // Opens the inspector on one task. `focusTop1` also picks its rank-1 row,
  // which is what the "▶ Top-1" button wants — the task and its first row in
  // one click instead of two.
  const selectTask = async (task: BoardTask, focusTop1 = false) => {
    setSelectedTaskId(task.id);
    setSelectedAnswerId(null);
    setBriefExpanded(false);
    setAnswersLoading(true);
    setAnswers(null);
    try {
      const result = await getAnswers(task.id);
      setAnswers(result.answers);
      setError(null);
      if (focusTop1) {
        const top = result.answers[0];
        if (top) {
          setSelectedAnswerId(top.id);
        } else {
          setError(`Task ${task.code} chưa có dòng nào.`);
        }
      }
    } catch (err) {
      setError(
        err instanceof ApiRequestError ? err.message : "Không tải được danh sách"
      );
    } finally {
      setAnswersLoading(false);
    }
  };

  const reviewTop1 = (task: BoardTask) => selectTask(task, true);

  const clear = async (taskId: number) => {
    setBusy(true);
    try {
      const result = await clearAnswers(taskId);
      setConfirming(null);
      setPreview(null);
      // Only the task that was actually cleared loses its inspector state —
      // clearing one query's rows should not blank out another one someone
      // else has open.
      if (selectedTaskId === taskId) {
        setAnswers([]);
        setSelectedAnswerId(null);
      }
      await refreshBoard();
      // Counts moved, so the warnings from before this click are stale.
      setIssues(null);
      setReady(null);
      setError(result.removed === 0 ? "Không có dòng nào để xoá." : null);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Không xoá được");
    } finally {
      setBusy(false);
    }
  };

  const check = async () => {
    if (!packId) return;
    setBusy(true);
    try {
      const result = await validateExport(packId);
      setIssues(result.issues);
      setReady(result.ready);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Không kiểm được");
    } finally {
      setBusy(false);
    }
  };

  const look = async (taskId: number) => {
    try {
      setPreview(await previewExport(taskId));
      setError(null);
    } catch (err) {
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
      anchor.download = `${board?.round?.label ?? "submission"}.zip`;
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
                setIssues(null);
                setReady(null);
                setPreview(null);
                // Task ids from the round left behind mean nothing here.
                setSelectedTaskId(null);
                setAnswers(null);
                setSelectedAnswerId(null);
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
        <span className="ml-auto flex gap-2">
          <Button variant="outline" disabled={busy} onClick={() => void check()}>
            Kiểm tra
          </Button>
          <Button disabled={busy || !packId} onClick={() => void download()}>
            Tải zip
          </Button>
        </span>
      </div>

      {error && <p className="text-[#c64545] text-sm mb-3">{error}</p>}

      {ready !== null && (
        <div className="border border-proto-line rounded-[10px] bg-white mb-5 overflow-hidden">
          <div className="px-4 py-2 bg-proto-soft text-sm">
            {ready ? (
              <b className="text-[#3d7a4d]">Không có cảnh báo nào.</b>
            ) : (
              <b className="text-proto-ink">{issues?.length} cảnh báo</b>
            )}
          </div>
          {issues?.map((issue, index) => (
            <div
              key={index}
              className="px-4 py-1.5 border-t border-proto-line text-sm flex gap-3"
            >
              <span className="font-mono font-bold text-proto-ink w-10">
                {issue.task_code}
              </span>
              <span
                className={
                  issue.severity === "warning"
                    ? "text-[#8a5a15]"
                    : "text-proto-muted"
                }
              >
                {issue.message}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-5">
        <div className="border border-proto-line rounded-[10px] bg-white overflow-hidden">
          <div className="px-4 py-2 bg-proto-soft text-[10px] font-bold uppercase tracking-wide text-proto-muted">
            Các file trong gói
          </div>
          <div className="p-3 max-h-[420px] overflow-y-auto">
            {board?.tasks.map((task) => (
              <div
                key={task.id}
                onClick={() => void selectTask(task)}
                className={`flex items-center gap-2 px-2 py-1.5 border-b border-proto-line last:border-b-0 text-xs flex-wrap cursor-pointer ${
                  task.id === selectedTaskId
                    ? "bg-proto-primary/10"
                    : "hover:bg-proto-soft"
                }`}
              >
                <b className="font-mono text-proto-ink w-8">{task.code}</b>
                <span className="text-[10px] font-bold uppercase text-proto-muted w-12">
                  {task.type === "qa" ? "Q&A" : task.type}
                </span>
                <span className="font-mono text-proto-muted w-14">
                  {task.answer_count} dòng
                </span>

                <span className="ml-auto flex gap-1 items-center">
                  <Button
                    size="xs"
                    variant="outline"
                    onClick={(event) => {
                      event.stopPropagation();
                      void look(task.id);
                    }}
                  >
                    Xem trước
                  </Button>
                  <Button
                    size="xs"
                    variant="outline"
                    disabled={task.answer_count === 0}
                    onClick={(event) => {
                      event.stopPropagation();
                      void reviewTop1(task);
                    }}
                  >
                    ▶ Top-1
                  </Button>

                  {/* Two steps rather than a window.confirm: this throws away
                      the whole query's work for everyone, not just this tab. */}
                  {confirming === task.id ? (
                    <>
                      <button
                        type="button"
                        className="text-[11px] font-bold text-[#c64545] underline"
                        onClick={(event) => {
                          event.stopPropagation();
                          void clear(task.id);
                        }}
                      >
                        Xoá {task.answer_count} dòng?
                      </button>
                      <button
                        type="button"
                        className="text-[11px] text-proto-muted underline"
                        onClick={(event) => {
                          event.stopPropagation();
                          setConfirming(null);
                        }}
                      >
                        Huỷ
                      </button>
                    </>
                  ) : (
                    <Button
                      size="xs"
                      variant="outline"
                      disabled={busy || task.answer_count === 0}
                      onClick={(event) => {
                        event.stopPropagation();
                        setConfirming(task.id);
                      }}
                    >
                      Xoá sạch
                    </Button>
                  )}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Bounded height so the grid rows below actually mean something —
            row 1 (auto) never scrolls, row 2 (minmax(0,1fr)) absorbs the rest
            of the height and is the only thing that scrolls. That keeps the
            video on screen while stepping through the answer list, which is
            the whole point of watching it while reviewing rows. */}
        <div className="border border-proto-line rounded-[10px] bg-white overflow-hidden h-[660px] grid grid-rows-[auto_minmax(0,1fr)]">
          <div>
            <div className="px-4 py-2 bg-proto-soft text-[10px] font-bold uppercase tracking-wide text-proto-muted">
              {selectedTask
                ? `Task ${selectedTask.code} · ${
                    selectedTask.type === "qa" ? "Q&A" : selectedTask.type
                  }`
                : "Xem trước một file"}
            </div>
            <div className="p-3">
              {selectedTask ? (
                <div className="flex flex-col gap-3">
                  {/* The brief, verbatim — never the search screen's TaskBrief,
                      which is laid out for a page with a result grid, not a
                      narrow side panel. */}
                  <div>
                    <p
                      className={`text-[13px] text-proto-ink whitespace-pre-wrap ${
                        briefExpanded ? "" : "line-clamp-3"
                      }`}
                    >
                      {taskBriefText(selectedTask)}
                    </p>
                    {taskBriefText(selectedTask).length > 140 && (
                      <button
                        type="button"
                        className="text-[11px] text-proto-muted underline mt-0.5"
                        onClick={() => setBriefExpanded((value) => !value)}
                      >
                        {briefExpanded ? "Thu gọn" : "Mở rộng"}
                      </button>
                    )}
                  </div>

                  {/* Video and still side by side — the still is the real
                      keyframe and the video is the real position, so a mismatch
                      between the two shows up at a glance.

                      Fixed height, and NO wrapping. This row used to be
                      flex-wrap with a 360x240 still, so on a panel narrower
                      than ~590px the still dropped onto its own line, the
                      top grid row grew to ~570px of the panel's 660, and the
                      answer list underneath was squeezed to about two rows.
                      Both children now size to this row instead of dictating
                      it, so the list always keeps the rest. */}
                  <div className="relative flex gap-3 items-stretch h-[220px]">
                    <div className="flex-1 min-w-0 flex flex-col">
                      {selectedAnswer ? (
                        videoSrc ? (
                          <video
                            ref={videoRef}
                            key={activeVideoId}
                            src={videoSrc}
                            controls
                            autoPlay
                            preload="metadata"
                            className="rounded-[8px] flex-1 min-h-0 w-full object-contain bg-black"
                            onLoadedMetadata={(e) => {
                              if (selectedAnswer) {
                                e.currentTarget.currentTime =
                                  startMsAt(
                                    selectedAnswer.video_id,
                                    selectedAnswer.frames[0] ?? 0
                                  ) / 1000;
                              }
                            }}
                          />
                        ) : (
                          <p className="text-[11.5px] text-proto-muted">
                            Chưa cấu hình kho video (VITE_VIDEO_BASE_URL).
                          </p>
                        )
                      ) : (
                        <div className="rounded-[8px] w-full flex-1 min-h-0 bg-proto-dark flex items-center justify-center">
                          <span className="text-[11px] text-neutral-400 px-2 text-center">
                            {answersLoading
                              ? "Đang tải…"
                              : "Bấm một dòng bên dưới để mở video. Trỏ chuột để xem nhanh ảnh frame."}
                          </span>
                        </div>
                      )}
                      {selectedAnswer && (
                        <div className="text-xs font-mono text-proto-ink mt-1">
                          {selectedAnswer.video_id} · frame{" "}
                          {selectedAnswer.frames[0] ?? 0}
                        </div>
                      )}
                    </div>
                    {/* The still floats over the player instead of sitting
                        beside it. As a sibling it was `h-full aspect-video` —
                        200px tall by 355px wide — while the video only got
                        whatever was left, so the image ended up larger than the
                        thing it was meant to be checked against. It also only
                        appears while the pointer is on a row: the video is what
                        you keep, the still is what you glance at. */}
                    {hoveredAnswer && (
                      <div className="pointer-events-none absolute right-2 top-2 bottom-2 aspect-video overflow-hidden rounded-[6px] shadow-2xl ring-2 ring-white">
                        <FramePreview
                          videoId={hoveredAnswer.video_id}
                          frameIdx={hoveredAnswer.frames[0] ?? 0}
                          size="fill"
                        />
                        <span className="absolute bottom-0 inset-x-0 bg-black/70 text-white font-mono text-[10px] px-1 py-0.5 text-center">
                          #{hoveredAnswer.rank} · frame{" "}
                          {hoveredAnswer.frames[0] ?? 0}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <p className="text-[11.5px] text-proto-muted">
                  Chọn một dòng ở danh sách bên trái để xem cả task, hoặc dùng{" "}
                  <b>▶ Top-1</b> để mở nhanh dòng hạng 1.
                </p>
              )}
            </div>
          </div>

          {/* The answer list. KeyframeImg already sets loading="lazy", so a
              hundred rows here does not fire a hundred requests. min-h-0 is
              what lets a grid row shrink below its content's height instead
              of stretching the grid to fit it — without it overflow-y-auto
              on a grid row does nothing. */}
          <div className="min-h-0 overflow-y-auto px-3 pb-3">
            {selectedTask && (
              <div className="border border-proto-line rounded-[8px] overflow-hidden divide-y divide-proto-line">
                {answersLoading && (
                  <p className="p-3 text-[11.5px] text-proto-muted">
                    Đang tải danh sách…
                  </p>
                )}
                {!answersLoading && answers?.length === 0 && (
                  <p className="p-3 text-[11.5px] text-proto-muted">
                    Chưa có dòng nào.
                  </p>
                )}
                {!answersLoading &&
                  answers?.map((row) => (
                    <div
                      key={row.id}
                      onClick={() => setSelectedAnswerId(row.id)}
                      onMouseEnter={() => setHoveredAnswerId(row.id)}
                      onMouseLeave={() =>
                        setHoveredAnswerId((current) =>
                          current === row.id ? null : current
                        )
                      }
                      className={`flex items-center gap-2 px-2 py-1.5 text-xs cursor-pointer ${
                        row.id === selectedAnswerId
                          ? "bg-proto-primary/10"
                          : "hover:bg-proto-soft"
                      }`}
                    >
                      <FramePreview
                        videoId={row.video_id}
                        frameIdx={row.frames[0] ?? 0}
                      />
                      <b className="font-mono text-proto-ink w-7">
                        #{row.rank}
                      </b>
                      <span className="font-mono text-proto-ink truncate">
                        {row.video_id}
                      </span>
                      <span className="font-mono text-proto-muted ml-auto">
                        frame {row.frames[0] ?? 0}
                      </span>
                    </div>
                  ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* CSV preview is a different job from reviewing frames — full width,
          below the two-column area, not fighting the video for space. */}
      {preview && (
        <div className="border border-proto-line rounded-[10px] bg-white overflow-hidden mt-5 p-3">
          <div className="text-xs font-mono text-proto-ink mb-1">
            {preview.filename} · {preview.rows} dòng
          </div>
          <pre className="text-[11px] font-mono bg-proto-soft border border-proto-line rounded p-2 overflow-x-auto whitespace-pre">
            {preview.content.split("\n").slice(0, 12).join("\n")}
            {preview.content.split("\n").length > 12 ? "\n…" : ""}
          </pre>
        </div>
      )}
    </div>
  );
}
