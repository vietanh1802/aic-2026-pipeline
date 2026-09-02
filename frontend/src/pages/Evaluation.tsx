import { useEffect, useRef, useState } from "react";

import { deleteAnswer, patchAnswer, reorderAnswer } from "../api/answers";
import { ApiRequestError } from "../api/base";
import {
  answersByAuthor,
  getBoard,
  setChosenAuthor,
  type AnswerRowLite,
  type BoardResponse,
  type BoardTask,
  type Person,
} from "../api/board";
import Button from "../components/Button";
import FramePreview from "../components/FramePreview";
import { startMsAt } from "../helpers/frameIdentity";
import { taskBriefText } from "../helpers/taskBrief";
import { videoUrlAt } from "../helpers/videoSource";
import { useAuthStore } from "../store/authStore";

/** One person's whole list for the open task. */
interface AuthorGroup {
  author: Person;
  count: number;
  answers: AnswerRowLite[];
}

/** Dòng đang được mở xem, và nó thuộc cột của ai. */
interface Picked {
  authorId: number;
  row: AnswerRowLite;
  /**
   * Mốc thứ mấy TRONG dòng đó, cho câu TRAKE.
   *
   * Một dòng TRAKE mang 4 mốc của cùng một video và bốn mốc đó là bốn thời
   * điểm khác nhau. Không có trường này thì video luôn nhảy về mốc 1 và ba mốc
   * còn lại không xem được — mà chấm TRAKE là chấm cả bốn.
   */
  frameAt: number;
}

/**
 * So sánh bài của cả nhóm cho một câu, rồi chọn bài để nộp.
 *
 * Khác Export ở chỗ: Export chỉ cho xem trước file sẽ nộp, còn đây là chỗ ngồi
 * đọ bài. Mỗi người một cột, đặt cạnh nhau, bấm vào dòng nào thì khung ảnh và
 * đoạn video của dòng đó hiện lên ở trên.
 *
 * Không có nút xoá sạch. Ai cũng sửa được bài của CHÍNH MÌNH — kéo đổi thứ tự,
 * xoá từng dòng — và không đụng được vào bài của người khác. Ranh giới đó do
 * backend giữ (mọi endpoint ghi đều khoá vào user đang đăng nhập), phần dưới
 * chỉ giấu nút đi cho khỏi bấm nhầm.
 */
export default function EvaluationPage() {
  const me = useAuthStore((state) => state.user);
  const [board, setBoard] = useState<BoardResponse | null>(null);
  const [taskId, setTaskId] = useState<number | null>(null);
  const [groups, setGroups] = useState<AuthorGroup[] | null>(null);
  const [chosenId, setChosenId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [briefExpanded, setBriefExpanded] = useState(false);

  /**
   * Dòng đang mở, do BẤM mà ra — không phải do con trỏ đi ngang.
   *
   * Cách cũ chạy theo `onMouseEnter` với độ trễ 180ms. Con trỏ đi từ cột này
   * sang cột kia là quét qua cả chục dòng, mỗi lần dừng lại quá 180ms là một
   * video mới được tải và bắt đầu chạy — chưa kể chỉ nhích chuột lúc đọc cũng
   * làm khung bên trên đổi mất thứ đang xem.
   */
  const [picked, setPicked] = useState<Picked | null>(null);

  // Kéo thả trong cột của mình: dòng đang cầm và chỗ sắp thả.
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);

  // Đáp án chữ đang gõ dở, theo id dòng. Chỉ giữ những ô ĐÃ bị sửa: ô nào
  // không có ở đây thì đọc thẳng từ máy chủ, nên một lần tải lại giữa chừng
  // không nuốt mất chữ người khác vừa gõ.
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const draftOf = (row: AnswerRowLite) => drafts[row.id] ?? row.answer_text ?? "";

  const saveText = async (row: AnswerRowLite) => {
    const next = draftOf(row);
    if (next === (row.answer_text ?? "")) {
      return;
    }
    await act(() =>
      patchAnswer(row.id, { answer_text: next, version: row.version })
    );
    // Bỏ bản nháp sau khi máy chủ nhận: từ đây giá trị thật mới là giá trị
    // hiển thị. Giữ lại thì lần tải sau sẽ bị bản nháp cũ đè lên.
    setDrafts((current) => {
      const copy = { ...current };
      delete copy[row.id];
      return copy;
    });
  };

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [activeVideoId, setActiveVideoId] = useState("");
  const [videoSrc, setVideoSrc] = useState("");

  useEffect(() => {
    void getBoard()
      .then(setBoard)
      .catch(() => undefined);
  }, []);

  const load = async (id: number) => {
    setLoading(true);
    try {
      const result = await answersByAuthor(id);
      setGroups(result.groups);
      setChosenId(result.chosen_author_id);
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiRequestError ? err.message : "Không tải được bài"
      );
    } finally {
      setLoading(false);
    }
  };

  const openTask = (id: number) => {
    setTaskId(id);
    setGroups(null);
    setBriefExpanded(false);
    setPicked(null);
    void load(id);
  };

  // Video khác thì phải đổi `src` — chính việc đổi src mới khiến trình duyệt
  // tải file mới. Cùng một video thì chỉ cần đẩy currentTime, không đụng src
  // nên khung hình không chớp và không phải tải lại.
  useEffect(() => {
    if (!picked) {
      return;
    }
    const seconds =
      startMsAt(
        picked.row.video_id,
        picked.row.frames[picked.frameAt] ?? 0
      ) / 1000;
    if (picked.row.video_id !== activeVideoId) {
      setActiveVideoId(picked.row.video_id);
      setVideoSrc(videoUrlAt(picked.row.video_id, seconds));
      return;
    }
    const element = videoRef.current;
    if (element) {
      element.currentTime = seconds;
    }
  }, [picked, activeVideoId]);

  const act = async (fn: () => Promise<unknown>) => {
    if (taskId === null) return;
    setBusy(true);
    try {
      await fn();
      await load(taskId);
      setBoard(await getBoard());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Thao tác hỏng");
    } finally {
      setBusy(false);
    }
  };

  /**
   * Thả dòng thứ `from` vào chỗ dòng thứ `to`, trong cột của chính mình.
   *
   * Kéo xuống thì neo SAU dòng đích, kéo lên thì neo TRƯỚC — dùng nhầm một
   * chiều thì dòng vẫn nhúc nhích nên rất khó nhận ra là sai.
   */
  const dropRow = async (rows: AnswerRowLite[], from: number, to: number) => {
    if (from === to || from < 0 || to < 0 || to >= rows.length) {
      return;
    }
    const moved = rows[from];
    const anchor = rows[to];
    await act(() =>
      reorderAnswer(
        taskId as number,
        from < to
          ? { answer_id: moved.id, after_id: anchor.id }
          : { answer_id: moved.id, before_id: anchor.id }
      )
    );
  };

  const task: BoardTask | null =
    board?.tasks.find((t) => t.id === taskId) ?? null;

  if (board && !board.round) {
    return (
      <div className="max-w-[1200px] mx-auto p-8 font-baloo">
        <h2 className="text-2xl text-proto-ink mb-2">Chưa có gói truy vấn</h2>
        <p className="text-sm text-proto-muted">
          Nhập gói truy vấn của vòng thi trước đã.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-[1600px] mx-auto p-6 font-baloo">
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <h2 className="text-2xl text-proto-ink">Đối chiếu bài</h2>
        <span className="text-xs font-mono text-proto-muted">
          {board?.round?.label}
        </span>
        <span className="text-sm text-proto-muted ml-auto">
          Bấm vào một dòng để xem khung ảnh và đoạn video của dòng đó
        </span>
      </div>

      {/* Chọn câu. Một dải ngang chứ không phải cột dọc: 5 cột bài bên dưới
          cần trọn chiều ngang, mà một danh sách 25 câu thì chỉ chiếm hai
          hàng. Số trong ngoặc là số người đã làm câu đó — câu chỉ một người
          làm thì chẳng có gì để đối chiếu. */}
      <div className="flex flex-wrap gap-1 mb-4">
        {board?.tasks.map((t) => {
          const open = t.id === taskId;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => openTask(t.id)}
              title={taskBriefText(t)}
              className={`text-[12px] px-2.5 py-1 rounded-[7px] border font-mono ${
                open
                  ? "bg-proto-cream-strong border-proto-cream-strong text-proto-ink font-bold"
                  : t.contributors.length === 0
                  ? "border-proto-line text-proto-line"
                  : "border-proto-line text-proto-muted"
              }`}
            >
              {t.code}
              <span className="ml-1 text-[10px]">
                ({t.contributors.length})
              </span>
              {t.chosen_author_id !== null && (
                <span className="ml-1 text-[#3d7a4d]">✓</span>
              )}
            </button>
          );
        })}
      </div>

      {error && <p className="text-[#c64545] text-sm mb-3">{error}</p>}

      {!task ? (
        <p className="text-sm text-proto-muted">
          Chọn một câu ở trên để bày bài của cả nhóm ra cạnh nhau.
        </p>
      ) : (
        <>
          {/* Đề bài bên trái, video bên phải, và cả khối GHIM lại khi cuộn.
              Nằm ở trên thôi thì chưa đủ: cột bài dài hơn màn hình, nên vừa
              kéo xuống soi ảnh là đề bài lẫn video đều trôi mất — đúng lúc cần
              chúng nhất, vì soi ảnh là để đối chiếu với đề.

              `-mx-6 px-6` kéo nền ra sát mép trong của khung `p-6` bên ngoài,
              nếu không thì các dòng bên dưới sẽ lộ ra ở hai bên khi trượt qua.
              z-20 đủ để nằm trên lưới bài mà vẫn dưới popup video. */}
          {/* 25 / 75, nghiêng hẳn về phía video.
              Trước đó lần lượt là `[1fr_520px]` rồi `[2fr_3fr]` (40/60).
              Cùng một lý do đẩy tỉ lệ đi mỗi lần: đề bài là vài dòng chữ đọc
              một lần rồi thôi, còn khung bên phải phải chứa CẢ video lẫn ảnh
              keyframe cạnh nhau — mỗi phần trăm lấy được của cột trái thì bên
              phải chia đôi, nên nó đáng giá gấp đôi ở đó. */}
          <div className="sticky top-[var(--nav-h)] z-20 bg-proto-canvas -mx-6 px-6 pt-1 pb-3 grid md:grid-cols-[1fr_3fr] gap-4 items-start">
            <div className="border border-proto-line rounded-[10px] bg-white p-3">
              <div className="flex items-center gap-2 mb-1">
                <b className="font-mono text-proto-ink">{task.code}</b>
                <span className="text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-proto-dark text-proto-canvas">
                  {task.type === "qa" ? "Q&A" : task.type.toUpperCase()}
                </span>
              </div>
              <p
                className={`text-[13px] text-proto-ink whitespace-pre-wrap ${
                  briefExpanded ? "" : "line-clamp-4"
                }`}
              >
                {taskBriefText(task)}
              </p>
              {taskBriefText(task).length > 180 && (
                <button
                  type="button"
                  className="text-[11px] text-proto-muted underline mt-1"
                  onClick={() => setBriefExpanded((value) => !value)}
                >
                  {briefExpanded ? "Thu gọn" : "Mở rộng"}
                </button>
              )}
            </div>

            <div className="border border-proto-line rounded-[10px] bg-white p-3">
              {picked ? (
                videoSrc ? (
                  <>
                    {/* Video BÊN CẠNH khung ảnh, không phải thay cho nó.
                        Video chạy tới một mốc thời gian tính từ số frame và
                        fps, nên nó chỉ ở GẦN đúng chỗ; còn ảnh keyframe là
                        đúng cái người kia đã chọn. Đối chiếu hai bài mà chỉ có
                        video thì phải bấm dừng, dò tới lui rồi mới so được. */}
                    {/* Hai ô BẰNG NHAU: `flex-1 basis-0` chia đôi chỗ bất kể
                        nội dung bên trong rộng bao nhiêu, và cùng `aspect-video`
                        nên hai khung khớp nhau từng điểm ảnh.

                        Trước đây video chiếm phần còn lại còn ảnh bị ép vào
                        `w-[36%]`, tức ảnh nhỏ hơn video khoảng ba lần. Nhưng
                        việc ở màn này là SO hai thứ đó với nhau, mà so hai ảnh
                        lệch cỡ nhau thì mắt không làm được — nhất là khi ảnh
                        keyframe mới là cái đúng, còn video chỉ chạy tới gần
                        đúng chỗ.

                        `aspect-video` thay cho `h-[300px]` cũ: chiều cao cố
                        định thì hai ô cao bằng nhau nhưng rộng khác nhau, và
                        cái nào cũng thừa dải đen. */}
                    <div className="flex gap-2 items-start">
                      <div className="flex-1 basis-0 min-w-0">
                        <video
                          ref={videoRef}
                          key={activeVideoId}
                          src={videoSrc}
                          controls
                          autoPlay
                          muted
                          preload="metadata"
                          className="rounded-[8px] w-full aspect-video object-contain bg-black"
                          onLoadedMetadata={(event) => {
                            event.currentTarget.currentTime =
                              startMsAt(
                                picked.row.video_id,
                                picked.row.frames[picked.frameAt] ?? 0
                              ) / 1000;
                          }}
                        />
                        {/* Nhãn cho cả hai ô, không chỉ ô ảnh. Hai khung giờ
                            giống hệt nhau nên phải nói cái nào là cái nào — và
                            nói luôn cái khác biệt đáng nhớ: video tua theo mốc
                            thời gian tính từ fps nên chỉ ở GẦN đúng chỗ. */}
                        <span className="block text-[10px] font-mono text-proto-muted mt-0.5 text-center">
                          video quanh mốc
                        </span>
                      </div>
                      <div className="flex-1 basis-0 min-w-0">
                        {/* aspect-video chứ không phải chiều cao cố định:
                            FramePreview cắt ảnh theo khung (object-cover), nên
                            khung sai tỉ lệ sẽ cắt mất hai mép. */}
                        <span className="block w-full aspect-video">
                          <FramePreview
                            videoId={picked.row.video_id}
                            frameIdx={picked.row.frames[picked.frameAt] ?? 0}
                            size="fill"
                          />
                        </span>
                        <span className="block text-[10px] font-mono text-proto-muted mt-0.5 text-center">
                          khung đã chọn
                        </span>
                      </div>
                    </div>
                    <div className="text-xs font-mono text-proto-ink mt-1 flex gap-2 items-center">
                      <b>
                        {groups?.find((g) => g.author.id === picked.authorId)
                          ?.author.display_name ?? "—"}
                      </b>
                      <span className="text-proto-muted">
                        #{picked.row.rank}
                      </span>
                      <span>{picked.row.video_id}</span>
                      <span className="text-proto-muted ml-auto">
                        frame {picked.row.frames[picked.frameAt] ?? 0}
                      </span>
                    </div>

                    {/* Cả 4 mốc TRAKE, bày thẳng dưới video. Trỏ vào ảnh nào
                        thì video nhảy tới mốc đó — chấm TRAKE là chấm cả bốn,
                        nên xem được một mốc rồi đoán ba mốc kia là vô nghĩa.
                        Ảnh to hơn ảnh trong cột vì đây là chỗ để NHÌN. */}
                    {task.type === "trake" && picked.row.frames.length > 1 && (
                      <div className="flex gap-1.5 mt-2">
                        {picked.row.frames.map((frame, at) => (
                          <button
                            key={at}
                            type="button"
                            onClick={() =>
                              setPicked({
                                authorId: picked.authorId,
                                row: picked.row,
                                frameAt: at,
                              })
                            }
                            className={`flex-1 min-w-0 rounded-[6px] overflow-hidden border-2 cursor-pointer ${
                              at === picked.frameAt
                                ? "border-proto-primary-active"
                                : "border-transparent hover:border-proto-line"
                            }`}
                            title={`${
                              task.event_labels[at] ?? `Mốc ${at + 1}`
                            } — bấm để nhảy tới frame ${frame}`}
                          >
                            {/* Chiều cao đặt ở khung bọc, không ở ảnh: size
                                "fill" sinh h-full, mà h-full trong một thẻ cha
                                cao tự động thì ảnh sập xuống 0. */}
                            <span className="block w-full h-[72px]">
                              <FramePreview
                                videoId={picked.row.video_id}
                                frameIdx={frame}
                                size="fill"
                              />
                            </span>
                            <span className="block text-[10px] font-mono text-proto-muted truncate px-0.5">
                              <b className="text-proto-primary-active">E{at + 1}</b> {frame}
                            </span>
                          </button>
                        ))}
                      </div>
                    )}

                    {/* Đáp án chữ, ngay dưới video. Với câu Q&A thì đây mới là
                        thứ được chấm — mã video và số frame chỉ chứng minh nó
                        lấy từ đâu. Đọc ở đây thay vì phải dò lại trong cột. */}
                    {task.type === "qa" && (
                      <div className="mt-2 px-2 py-1.5 rounded-[6px] bg-proto-soft border border-proto-line">
                        <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted block">
                          Đáp án
                        </span>
                        <span className="text-[15px] text-proto-ink break-words">
                          {picked.row.answer_text?.trim() || (
                            <i className="text-proto-line text-[13px]">
                              chưa điền đáp án
                            </i>
                          )}
                        </span>
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-[11.5px] text-proto-muted">
                    Chưa cấu hình kho video (VITE_VIDEO_BASE_URL).
                  </p>
                )
              ) : (
                <div className="rounded-[8px] w-full h-[300px] bg-proto-dark flex items-center justify-center">
                  <span className="text-[11px] text-neutral-400 px-4 text-center">
                    Bấm vào một dòng bên dưới để xem khung ảnh và đoạn video
                    người đó chọn.
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Các cột bài. Cuộn ngang khi đông người: thà kéo ngang còn hơn ép
              5 cột vào chiều rộng màn hình rồi cột nào cũng hẹp tới mức không
              đọc nổi tên video. */}
          {loading && (
            <p className="text-sm text-proto-muted">Đang tải bài…</p>
          )}
          {!loading && groups?.length === 0 && (
            <p className="text-sm text-proto-muted">
              Chưa ai làm câu này.
            </p>
          )}
          {!loading && groups && groups.length > 0 && (
            <div className="flex gap-3 overflow-x-auto pb-2">
              {groups.map((group) => {
                const isMine = group.author.id === me?.id;
                const isChosen = group.author.id === chosenId;
                return (
                  <div
                    key={group.author.id}
                    // Rộng theo loại câu, vì mỗi loại phải bày ra thứ khác
                    // nhau: Q&A cần chỗ cho một địa danh đầy đủ, TRAKE cần chỗ
                    // cho 4 ảnh cạnh nhau đủ to để phân biệt. Ép cả ba về một
                    // bề rộng thì loại nào cũng chật hoặc thừa.
                    className={`shrink-0 ${
                      task.type === "qa"
                        ? "w-[380px]"
                        : task.type === "trake"
                        ? "w-[420px]"
                        : "w-[300px]"
                    } border rounded-[10px] bg-white overflow-hidden ${
                      isChosen
                        ? "border-[#3d7a4d] ring-1 ring-[#3d7a4d]"
                        : "border-proto-line"
                    }`}
                  >
                    <div className="px-3 py-2 bg-proto-soft flex items-center gap-2">
                      <b className="text-[13px] text-proto-ink truncate">
                        {group.author.display_name}
                      </b>
                      {isMine && (
                        <span className="text-[9.5px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-proto-cream-strong text-proto-ink">
                          bạn
                        </span>
                      )}
                      <span className="font-mono text-[11px] text-proto-muted ml-auto">
                        {group.count} dòng
                      </span>
                    </div>

                    {/* Chọn bài để nộp. Đặt ngay đầu cột vì quyết định này
                        được đưa ra khi đang nhìn vào cột đó, không phải khi
                        đang nhìn một ô select ở màn khác. */}
                    <div className="px-3 py-1.5 border-b border-proto-line">
                      {isChosen ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() =>
                            void act(() => setChosenAuthor(task.id, null))
                          }
                          className="text-[11.5px] font-bold text-[#3d7a4d] underline decoration-dotted"
                          title="Bấm để bỏ chọn"
                        >
                          ✓ Bài này sẽ được nộp
                        </button>
                      ) : (
                        <Button
                          size="xs"
                          variant="outline"
                          disabled={busy}
                          onClick={() =>
                            void act(() =>
                              setChosenAuthor(task.id, group.author.id)
                            )
                          }
                        >
                          Chọn nộp bài này
                        </Button>
                      )}
                    </div>

                    <div className="max-h-[520px] overflow-y-auto p-1.5">
                      {group.answers.length === 0 && (
                        <p className="p-2 text-[11.5px] text-proto-muted">
                          Chưa có dòng nào.
                        </p>
                      )}
                      {group.answers.map((row, index) => (
                        <div
                          key={row.id}
                          // Chỉ cột của mình mới kéo được. Cột người khác kéo
                          // thả sẽ ném 403 từ backend — chặn ngay ở đây cho
                          // người dùng khỏi tưởng mình vừa sửa được gì.
                          draggable={isMine && !busy}
                          onDragStart={(event) => {
                            const element = event.target as HTMLElement;
                            // Cả input nữa, không chỉ button: bôi đen chữ
                            // trong ô đáp án mà lại khởi động kéo dòng thì
                            // không sửa được đáp án Q&A.
                            if (element.closest("button,input,textarea")) {
                              event.preventDefault();
                              return;
                            }
                            setDragIndex(index);
                            event.dataTransfer.effectAllowed = "move";
                            // Firefox không khởi động drag nếu dataTransfer rỗng.
                            event.dataTransfer.setData(
                              "text/plain",
                              String(row.id)
                            );
                          }}
                          onDragOver={(event) => {
                            if (!isMine || dragIndex === null) return;
                            event.preventDefault(); // thiếu thì onDrop không chạy
                            event.dataTransfer.dropEffect = "move";
                            if (overIndex !== index) setOverIndex(index);
                          }}
                          onDrop={(event) => {
                            event.preventDefault();
                            const from = dragIndex;
                            setDragIndex(null);
                            setOverIndex(null);
                            if (isMine && from !== null) {
                              void dropRow(group.answers, from, index);
                            }
                          }}
                          onDragEnd={() => {
                            setDragIndex(null);
                            setOverIndex(null);
                          }}
                          onClick={(event) => {
                            // Bấm vào nút xoá hay ô đáp án thì không phải là
                            // "mở dòng này ra xem" — cùng cái bảo vệ mà
                            // onDragStart đang dùng.
                            const element = event.target as HTMLElement;
                            if (element.closest("button,input,textarea")) {
                              return;
                            }
                            setPicked({
                              authorId: group.author.id,
                              row,
                              frameAt: 0,
                            });
                          }}
                          className={`cursor-pointer flex flex-col gap-0.5 px-1.5 py-1 mb-0.5 rounded-[6px] border text-[11.5px] ${
                            isMine ? "cursor-grab active:cursor-grabbing" : ""
                          } ${
                            picked?.row.id === row.id
                              ? "border-proto-primary-active bg-proto-primary/10"
                              : "border-transparent hover:bg-proto-soft"
                          } ${dragIndex === index && isMine ? "opacity-40" : ""} ${
                            overIndex === index &&
                            isMine &&
                            dragIndex !== null &&
                            dragIndex !== index
                              ? dragIndex < index
                                ? "border-b-2 border-b-proto-primary-active"
                                : "border-t-2 border-t-proto-primary-active"
                              : ""
                          }`}
                        >
                          <div className="flex items-center gap-1.5">
                            {/* TRAKE bày cả 4 mốc thành một dải riêng bên
                                dưới, nên hàng này không lặp lại ảnh mốc 1. */}
                            {task.type !== "trake" && (
                              <FramePreview
                                videoId={row.video_id}
                                frameIdx={row.frames[0] ?? 0}
                              />
                            )}
                            <b className="font-mono text-proto-ink w-6 shrink-0">
                              {row.rank}
                            </b>
                            <span className="font-mono text-proto-ink truncate">
                              {row.video_id}
                            </span>
                            {task.type !== "trake" && (
                              <span className="font-mono text-proto-muted ml-auto shrink-0">
                                {row.frames.join(",")}
                              </span>
                            )}
                            {isMine && (
                              <button
                                type="button"
                                disabled={busy}
                                title="Xoá dòng này khỏi bài của bạn"
                                onClick={() =>
                                  void act(() => deleteAnswer(row.id))
                                }
                                className="shrink-0 ml-auto px-1 text-[#c64545] font-bold leading-none"
                              >
                                ×
                              </button>
                            )}
                          </div>

                          {/* Cả 4 mốc TRAKE ngay trong cột. Trước đây chỉ hiện
                              ảnh của mốc 1 với một chuỗi số — mà một dòng TRAKE
                              chỉ đúng khi CẢ BỐN mốc đúng, nên nhìn một ảnh
                              không đủ để so bài của hai người. Trỏ vào ảnh nào
                              thì video ở trên nhảy tới đúng mốc đó. */}
                          {task.type === "trake" && (
                            <div className="flex gap-1">
                              {row.frames.map((frame, at) => (
                                // <button> chứ không <span>: đây là thứ bấm
                                // được, nên nó phải bấm được cả bằng bàn phím
                                // và phải đọc ra là nút với trình đọc màn hình.
                                <button
                                  key={at}
                                  type="button"
                                  onClick={(event) => {
                                    // Dòng cha cũng bắt click; không chặn thì
                                    // handler của dòng chạy sau và kéo mốc về
                                    // E1, đúng cái mốc vừa cố tình bỏ qua.
                                    event.stopPropagation();
                                    setPicked({
                                      authorId: group.author.id,
                                      row,
                                      frameAt: at,
                                    });
                                  }}
                                  title={`${
                                    task.event_labels[at] ?? `Mốc ${at + 1}`
                                  } — bấm để nhảy tới frame ${frame}`}
                                  className={`flex-1 min-w-0 rounded-[4px] overflow-hidden border cursor-pointer ${
                                    picked?.row.id === row.id &&
                                    picked.frameAt === at
                                      ? "border-proto-primary-active"
                                      : "border-transparent hover:border-proto-line"
                                  }`}
                                >
                                  <span className="block w-full h-[56px]">
                                    <FramePreview
                                      videoId={row.video_id}
                                      frameIdx={frame}
                                      size="fill"
                                    />
                                  </span>
                                  <span className="block text-[9.5px] font-mono text-proto-muted truncate text-center">
                                    <b className="text-proto-primary-active">E{at + 1}</b>{" "}
                                    {frame}
                                  </span>
                                </button>
                              ))}
                            </div>
                          )}

                          {/* Đáp án chữ. Chỉ câu Q&A mới có, và ở loại câu đó
                              thì ĐÂY mới là thứ được chấm — mã video với số
                              frame chỉ để chứng minh đáp án lấy từ đâu. Không
                              hiện nó ra thì cả trang này vô dụng với Q&A: năm
                              cột trông giống hệt nhau. */}
                          {task.type === "qa" &&
                            (isMine ? (
                              <input
                                value={draftOf(row)}
                                disabled={busy}
                                placeholder="đáp án…"
                                onChange={(event) =>
                                  setDrafts((current) => ({
                                    ...current,
                                    [row.id]: event.target.value,
                                  }))
                                }
                                onBlur={() => void saveText(row)}
                                onKeyDown={(event) => {
                                  if (event.key === "Enter") {
                                    event.currentTarget.blur();
                                  }
                                }}
                                className={`w-full px-1.5 py-0.5 rounded-[4px] border bg-white text-[12px] text-proto-ink ${
                                  drafts[row.id] !== undefined
                                    ? "border-proto-primary-active"
                                    : "border-proto-line"
                                }`}
                              />
                            ) : (
                              <span
                                className="px-1.5 py-0.5 text-[12px] text-proto-ink break-words"
                                title={row.answer_text ?? ""}
                              >
                                {row.answer_text?.trim() || (
                                  <i className="text-proto-line">
                                    chưa điền đáp án
                                  </i>
                                )}
                              </span>
                            ))}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Ai cũng chỉnh được bài của mình, nên phải nói rõ vì sao cột người
              khác không kéo được — nếu không thì trông như trang bị lỗi. */}
          <p className="text-[11.5px] text-proto-muted mt-2">
            Bạn kéo thả và xoá dòng được trên cột của mình. Cột của người khác
            chỉ để xem — bài của họ do họ sửa.
          </p>
        </>
      )}

      {/* Nhật ký đã bỏ khỏi màn này. Nó liệt kê thao tác quản trị — nhập gói,
          kích hoạt, xoá — trong khi chỗ này là nơi đọ bài. Thứ người ta thật
          sự cần lần lại ở đây là LỊCH SỬ TÌM KIẾM, và cái đó nằm trong bảng
          "Cả nhóm đang tìm câu này" ở màn Search. */}
    </div>
  );
}
