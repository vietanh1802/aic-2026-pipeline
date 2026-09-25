// frontend/src/App.tsx

import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import FrameDisplay from "./components/FrameDisplay";
import ProjectDescription from "./components/ProjectDescription";
import QueryInput from "./components/QueryInput";
import TaskBrief from "./components/TaskBrief";
import OcrCountBanner from "./components/OcrCountBanner";
import { useIsQueryStore, useSearchStore } from "./store/useSearchStore";
import { useQueryStore, type SearchType } from "./store/queryStore";
import { usePopupStore } from "./store/popupStore";
import { useHealthStore } from "./store/healthStore";
import VideoPopup from "./components/VideoPopUp";
import TemporalSearchPanel from "./components/TemporalSearchPanel";
import { videoSearchApi } from "./types/api";
import {
  TemporalCandidates,
  TrakeCandidates,
} from "./components/CandidateResults";
import type {
  EventPick,
  TrakeSwapMap,
} from "./components/CandidateResults/types";
import {
  frameIdFromName,
  frameIndexFromResult,
  startMsAt,
  videoIdFromFrame,
} from "./helpers/frameIdentity";
import { splitQueryParts } from "./helpers/candidates";
import { filterByFocus } from "./helpers/focusFilter";
import { buildGridResults } from "./helpers/groupResults";
import { isOcrResults } from "./helpers/candidateStripView";
import { buildTextFilterParams, hasTextFilter } from "./helpers/textFilter";
import { sourcesSearched } from "./helpers/textSignalView";
import { eventWindowFields, type MarkedRange } from "./helpers/basketMath";
import { nearestKeyframeFor } from "./helpers/keyframes";
import { keyframeUrl } from "./helpers/videoSource";
import { addAnswer } from "./api/answers";
import type { BoardTask } from "./api/board";
import { type SearchState } from "./api/searchState";
import SearchHistory from "./components/SearchHistory";
import { recordSearchState } from "./helpers/searchStateRecorder";
import { usePickedFrameStore } from "./store/pickedFrameStore";
import { useAutofillStore } from "./store/autofillStore";
import type {
  ModelName,
  SearchResult,
  TemporalCandidateResult,
  TrakeCandidateResult,
} from "./types/api";
import KeyframeFPS from "./mapping/fps_map.json";

// Moved to helpers/frameIdentity.ts (same body) so FrameDisplay's timestamp
// fallback and the candidate-strip helper share one copy instead of three.
// function frameIndexFromResult(result: SearchResult): number {
//   if (typeof result.frame_idx === "number") {
//     return result.frame_idx;
//   }
//   return Number(result.frame.match(/-(\d+)\.jpg$/)?.[1] ?? 0);
// }

function startMsFromResult(result: SearchResult): number {
  return startMsAt(videoIdFromFrame(result.frame), frameIndexFromResult(result));
}

function App({
  activeTask = null,
  rowsPerQuery = 100,
  onBasketChanged,
  view = "search",
  onLeaveHistory,
}: {
  /** The task claimed on the board, if any. Read-only context for the search. */
  activeTask?: BoardTask | null;
  /** From the round the task belongs to; threaded down to the popup's answer panel. */
  rowsPerQuery?: number;
  onBasketChanged?: () => void;
  /** "history" thay lưới kết quả bằng bảng lịch sử của câu đang mở. */
  view?: "search" | "history";
  /** Quay về màn Search sau khi lấy một truy vấn cũ ra chạy lại. */
  onLeaveHistory?: () => void;
} = {}) {
  const results = useSearchStore((state) => state.results);
  const maxDistance = useSearchStore((state) => state.maxDistance);
  const setSummary = useSearchStore((state) => state.setSummary);
  const focusVideos = useSearchStore((state) => state.focusVideos);
  const toggleFocusVideo = useSearchStore((state) => state.toggleFocusVideo);
  const clearFocus = useSearchStore((state) => state.clearFocus);
  const showOnlyPinned = useSearchStore((state) => state.showOnlyPinned);
  const toggleShowOnlyPinned = useSearchStore((state) => state.toggleShowOnlyPinned);
  const onePerVideo = useSearchStore((state) => state.onePerVideo);
  const toggleOnePerVideo = useSearchStore((state) => state.toggleOnePerVideo);
  // resultLimit/topM/useRerank/ocrStripDiacritics/singleModel từng được đăng ký
  // ở đây và doSearch đọc qua closure. Giờ doSearch đọc thẳng từ store, vì nó
  // còn được gọi ngay sau khi áp truy vấn của người khác vào store — closure
  // lúc đó vẫn giữ giá trị cũ và sẽ chạy sai tham số. Chỉ hai cái dưới đây còn
  // ở lại, vì phần render thật sự đọc chúng.
  const searchType = useQueryStore((state) => state.searchType);
  /**
   * Tuyến trả về TỪNG KHUNG ẢNH (ensemble / single / OCR), khác với
   * temporal/TRAKE trả về từng VIDEO ứng viên.
   *
   * Lưới ảnh đọc `useSearchStore.results`, mà temporal/TRAKE không ghi vào đó —
   * nên chạy TRAKE xong màn hình vẫn còn nguyên lưới ảnh của lượt tìm TRƯỚC,
   * nằm ngay dưới danh sách ứng viên TRAKE như thể chúng là kết quả của cùng
   * một lượt.
   */
  const isFrameRoute = searchType !== "temporal" && searchType !== "trake";
  // Khung đang được khoanh đỏ trong lưới, và chép từ ai (null nếu tự chọn).
  const pickedFrame = usePickedFrameStore((state) => state.frame);
  const pickedFrom = usePickedFrameStore((state) => state.from);
  const [showPopup, setShowPopup] = useState<boolean>(false);
  const [videoUrl, setVideoUrl] = useState<string>("");
  const [startTime, setStartTime] = useState<number>(0);
  const [frameId, setframeId] = useState<string>("");

  const queryText = useQueryStore((state) => state.queryText);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Trạng thái backend giờ do <ApiStatus/> trên thanh điều hướng hỏi và ghi
  // vào store; ở đây chỉ đọc, để khoá nút Search khi index chưa nạp xong. Tự
  // hỏi lại lần nữa sẽ thành hai vòng lặp gọi /health mỗi 5 giây và hai chỗ có
  // thể hiện hai trạng thái khác nhau cùng lúc.
  const backendHealth = useHealthStore((state) => state.health);
  const isSearchDisabled = backendHealth.status !== "ready";

  // ── Temporal Search (Alg.4) — anchor do người dùng tự chọn từ kết quả
  // search đã có (paper: "the initially retrieved and reranked input frame
  // corresponds to the correct reference frame"), kích hoạt qua nút "⏱"
  // trên FrameDisplay. Không thay thế gì của search thường (ensemble/single).
  const [showTemporalPanel, setShowTemporalPanel] = useState(false);
  const [temporalAnchor, setTemporalAnchor] = useState<{
    name: string;
    url: string;
  } | null>(null);

  // Đề bài của BTC là văn bản chỉ đọc; ô search bên dưới là chữ người dùng tự
  // gõ. Hai thứ không bao giờ trộn vào nhau — xem spec §6.2.
  // KIS and Q&A only. TRAKE used to land here too and submitted
  // `Array.from({length: n_events}, () => frame)` — N copies of one frame,
  // which is the right shape carrying meaningless content. A TRAKE row is
  // assembled on the TRAKE search line instead, where all N moments exist.
  const handleAddToBasket = async (result: SearchResult) => {
    if (!activeTask) {
      console.warn("[basket] Chưa mở task nào từ bảng Board.");
      return;
    }
    const video = videoIdFromFrame(result.frame);
    const frameIdx = frameIndexFromResult(result);
    try {
      await addAnswer(activeTask.id, {
        video_id: video,
        frames: [frameIdx],
      });
      onBasketChanged?.();
      // Bỏ một khung vào giỏ LÀ chọn khung đó — tín hiệu mạnh nhất trong cả
      // lượt tìm, mạnh hơn cả mở video ra xem.
      //
      // Trước đây chỉ nút 🔍 (mở video) mới ghi lại, nên người nào bấm thẳng
      // "+" thì `picked_frame` vẫn là null. Đồng đội bấm "Coi X làm" sau đó
      // thấy đúng lưới kết quả của X nhưng KHÔNG có thẻ nào được khoanh đỏ —
      // không phải vòng khoanh mờ, mà là chẳng có khung nào để khoanh.
      recordState({ name: result.name, video, frameIdx });
      usePickedFrameStore.getState().set(result.name);
    } catch (err) {
      console.error("Không thêm được vào giỏ:", err);
    }
  };

  const handleUseAsAnchor = (result: SearchResult) => {
    setTemporalAnchor({ name: result.name, url: result.url });
    setShowTemporalPanel(true);
  };

  // Alg.3 (ensemble) hoặc chạy 1 model đơn (Q4) — khớp đúng /ensemble-search
  // và /single-search hiện có trong main.py. Không còn text-search/faiss-
  // search/combined-search/ocr-search/filter-search — các endpoint đó đã bị
  // xóa khỏi backend (xem docstring main.py).
  // Kết quả Temporal/TRAKE — khác shape với SearchResult[] (mỗi phần tử là 1
  // VIDEO ứng viên, bên trong có N frame), nên lưu state riêng thay vì dùng
  // chung useSearchStore. CHƯA có component hiển thị — tạm console.log để
  // xác nhận data đúng, phần hiển thị (danh sách card video ứng viên) làm
  // sau, đây là bước "chỉ thêm mode search" theo đúng yêu cầu.
  const [temporalCandidates, setTemporalCandidates] = useState<
    TemporalCandidateResult[]
  >([]);
  const [trakeCandidates, setTrakeCandidates] = useState<
    TrakeCandidateResult[]
  >([]);

  // The OCR route's three counts. Kept out of useSearchStore because that
  // store is shared with the visual route, which has no notion of "how many
  // images contain this text".
  const [ocrCounts, setOcrCounts] = useState<{
    phrase: number;
    allWords: number;
    searched: number;
  } | null>(null);

  // Bộ lọc route track nhận ra từ câu (groups/colors/directions/speeds).
  // Nằm ngoài store vì cùng lý do ocrCounts: chỉ route này có khái niệm này.
  // Operator nhìn một cái là biết route hiểu đúng ý mình chưa.
  const [trackParsed, setTrackParsed] = useState<
    Record<string, string[]> | null
  >(null);

  // ── TRAKE line ───────────────────────────────────────────────────────────
  // Which frame each event of each card is currently standing on, when it is
  // not the one the DP chose. Held here rather than inside TrakeCard because
  // the video popup below writes into it: scrubbing to a frame and pressing
  // "Chốt cho E2" has to land back in that cell.
  const [trakeSwaps, setTrakeSwaps] = useState<TrakeSwapMap>({});
  // Mốc nào đã được chốt vào giỏ, theo thẻ và theo chỉ số sự kiện.
  //
  // Trước đây cờ này là state cục bộ trong TrakeCard, và đúng chừng nào chỉ có
  // một đường chốt — cái nút trên ô. Giờ có hai: nút trên ô, và "Chốt cho E1"
  // trong popup video. Để cờ nằm trong thẻ thì đường thứ hai ghi một dòng vào
  // giỏ mà cái ô vẫn hiện "+ Chốt" như chưa có gì xảy ra, mời người dùng bấm
  // thêm lần nữa và tạo dòng trùng.
  const [trakePicked, setTrakePicked] = useState<Record<string, Record<number, boolean>>>({});

  const markTrakePicked = (cardKey: string, index: number) =>
    setTrakePicked((current) => ({
      ...current,
      [cardKey]: { ...(current[cardKey] ?? {}), [index]: true },
    }));

  // Hai đầu người dùng ghim cho từng mốc, theo thẻ rồi tới chỉ số sự kiện.
  //
  // Dòng đáp án TRAKE chỉ chở được `video` + `frame_1..frame_N` — bảng answers
  // không có cột nào cho một khoảng, và file nộp cũng chỉ có từng ấy cột. Nên
  // khoảng không đi vào dòng; nó đi vào ô "từ … đến …" của bảng Điền tự động,
  // nơi nó quyết định các dòng rải sau nằm ở đâu.
  //
  // Giữ ở App chứ không ở popup: popup đóng lại giữa hai mốc, mà bốn khoảng
  // của bốn mốc chỉ được dùng tới lúc bấm "Chọn" — sau cả bốn lần đóng.
  const [trakeEventRanges, setTrakeEventRanges] = useState<
    Record<string, Record<number, MarkedRange>>
  >({});
  const patchTuning = useAutofillStore((state) => state.patch);

  // Set while the popup is open on one event, so the submit button says which
  // moment it is pinning instead of "Add Answer".
  const [trakeSlot, setTrakeSlot] = useState<{
    cardKey: string;
    index: number;
    label: string;
    total: number;
  } | null>(null);

  // A popup asked for from outside App — a basket row, the goto-frame box.
  // The paths already inside App set this state directly and do not go
  // through the store.
  const popupRequest = usePopupStore((state) => state.request);
  const clearPopupRequest = usePopupStore((state) => state.clear);

  useEffect(() => {
    if (!popupRequest) {
      return;
    }
    const { videoId, frameIdx } = popupRequest;
    // No keyframe name to take an id from, so the header shows the frame
    // number itself — the same thing a hand-pinned TRAKE moment shows.
    setframeId(String(frameIdx));
    setVideoUrl(videoId);
    setStartTime(startMsAt(videoId, frameIdx));
    setTrakeSlot(null);
    setShowPopup(true);
    clearPopupRequest();
  }, [popupRequest, clearPopupRequest]);

  const swapTrakeEvent = (
    cardKey: string,
    index: number,
    pick: EventPick
  ) => {
    setTrakeSwaps((prev) => ({
      ...prev,
      [cardKey]: { ...(prev[cardKey] ?? {}), [index]: pick },
    }));
  };

  const resetTrakeEvent = (cardKey: string, index: number) => {
    setTrakeSwaps((prev) => {
      const card = prev[cardKey];
      if (!card || !(index in card)) {
        return prev;
      }
      const next = { ...card };
      delete next[index];
      return { ...prev, [cardKey]: next };
    });
  };

  const openTrakeEvent = (
    cardKey: string,
    index: number,
    pick: EventPick,
    video: string
  ) => {
    const frame = pick.frame_idx ?? 0;
    // splitQueryParts rather than the `queryParts` below: this runs from a
    // click, and reading the value straight off current state keeps the two
    // declarations independent of each other's order.
    const labels = splitQueryParts(queryText);
    setframeId(pick.name ? frameIdFromName(pick.name) : String(frame));
    setVideoUrl(video);
    setStartTime(startMsAt(video, frame));
    // Ô mốc CHỈ dành cho câu TRAKE. Trước đây đặt cho mọi loại câu:
    //
    //     setTrakeSlot({ cardKey, index, label: ..., total: ... });
    //
    // Với câu KIS/Q&A thì đó là sai mô hình. Tuyến TRAKE ở đó chỉ là một CÁCH
    // TÌM — kể một chuỗi hành động để lọc ra đúng video — chứ không đổi hình
    // dạng đáp án: một dòng vẫn là một frame, y như ensemble. Đặt ô mốc vào
    // biến popup thành một thứ khác hẳn: nút đổi thành "Chốt cho E1", chốt
    // xong thì nút biến mất, và cả đường Add Answer quen thuộc — ghim hai đầu,
    // nộp khung giữa, giỏ tự gợi ý bước để rải 99 dòng — không đi qua được.
    //
    // Bỏ trống ô mốc thì popup mở ra đúng như bấm một thẻ ensemble. Khác biệt
    // của TRAKE search dừng lại ở màn kết quả.
    if (activeTask?.type === "trake") {
      setTrakeSlot({
        cardKey,
        index,
        label: labels[index] ?? `E${index + 1}`,
        total: activeTask?.n_events ?? labels.length,
      });
    } else {
      setTrakeSlot(null);
    }
    setShowPopup(true);
  };

  // ── TRAKE search dùng cho câu KIS / Q&A ─────────────────────────────────
  //
  // Tuyến TRAKE trả về VIDEO ứng viên kèm N mốc, và nó là cách mô tả mạnh nhất
  // đang có: kể một chuỗi hành động thì lọc ra đúng video, trong khi một câu tả
  // tĩnh thì không. Nhưng nút duy nhất trên thẻ lại nộp cả hàng N mốc thành một
  // dòng — chỉ hợp lệ với câu TRAKE — nên với câu KIS/Q&A cả màn kết quả không
  // có đường nào vào giỏ, dù người dùng đã nhìn thấy đúng khoảnh khắc cần.
  //
  // Ở đây mỗi mốc là MỘT ứng viên độc lập: chốt mốc nào thì mốc đó thành một
  // dòng một frame, đúng hình dạng đáp án KIS/Q&A.
  const [trakeQaText, setTrakeQaText] = useState<string>("");

  const commitTrakeFrame = async (video: string, frameIdx: number) => {
    if (!activeTask) {
      console.warn("[basket] Chưa mở task nào từ bảng Board.");
      return;
    }
    try {
      await addAnswer(activeTask.id, {
        video_id: video,
        frames: [frameIdx],
        // Q&A chấm bằng ĐÁP ÁN CHỮ, nên một dòng chốt frame mà bỏ trống chữ là
        // một dòng chắc chắn không được điểm. Ô chữ nằm trên đầu danh sách ứng
        // viên vì cả câu chỉ có một đáp án — chỉ khung hình là thay đổi.
        answer_text: activeTask.type === "qa" ? trakeQaText.trim() || null : null,
      });
      onBasketChanged?.();
    } catch (err) {
      console.error("Không thêm được mốc TRAKE vào giỏ:", err);
    }
  };

  // The whole line, as one row. Fires only when every event has a frame.
  const commitTrakeRow = async (
    video: string,
    frames: number[],
    cardKey?: string
  ) => {
    if (!activeTask) {
      console.warn("[basket] Chưa mở task nào từ bảng Board.");
      return;
    }
    try {
      await addAnswer(activeTask.id, { video_id: video, frames });
      // Đổ hai đầu đã ghim của từng mốc vào ô "từ/đến" của Điền tự động, ngay
      // sau khi dòng đã nằm trong giỏ. Sau chứ không trước: hàng chưa vào giỏ
      // thì chưa có mốc gốc nào để rải quanh, và ghi sẵn vào bảng đó chỉ tạo
      // ra một cấu hình trỏ vào chỗ trống.
      //
      // Mốc nào người dùng không ghim thì KHÔNG ghi gì: ô đó tự rơi về "lo =
      // hi = khung gốc", tức hành động đứng yên. Điền một khoảng bịa vào chỗ
      // họ chưa xem là dựng ra thông tin họ chưa hề đưa.
      const marks = cardKey ? trakeEventRanges[cardKey] : undefined;
      if (marks) {
        const { eventLo, eventHi } = eventWindowFields(marks);
        if (Object.keys(eventLo).length > 0) {
          patchTuning(activeTask.id, activeTask.type, { eventLo, eventHi });
        }
      }
      onBasketChanged?.();
    } catch (err) {
      console.error("Không thêm được dòng TRAKE vào giỏ:", err);
    }
  };

  // Ghi trạng thái tìm. Thân hàm nằm ở helpers/searchStateRecorder vì màn
  // popup video cũng phải gọi nó — chốt khung sau khi tua tới lui là một lần
  // "tìm ra" y như bấm thẳng trên thẻ, mà đường đó nằm ở cây component khác.
  const recordState = (picked?: {
    name?: string | null;
    video: string;
    frameIdx: number;
  }) => recordSearchState(activeTask?.id, picked);

  /**
   * @param options.record false khi lần chạy này là để XEM LẠI bài người khác.
   *   Ghi vào đây sẽ biến truy vấn của họ thành truy vấn của mình trên bảng
   *   chung — cả nhóm nhìn vào tưởng hai người tự nghĩ ra cùng một câu.
   */
  const doSearch = async (options?: { record?: boolean }) => {
    if (isSearchDisabled) {
      console.warn(`[health] Search blocked: ${backendHealth.message}`);
      return;
    }
    if (options?.record !== false) {
      // Truy vấn mới nghĩa là bộ kết quả mới, nên khung đang khoanh không còn
      // nằm trong đó — bỏ khoanh, nếu không vòng đỏ sẽ trôi sang một thẻ không
      // liên quan hoặc trỏ vào chỗ trống.
      usePickedFrameStore.getState().set(null);
      recordState();
    }
    // Mọi nhánh bên dưới đọc từ store, không đọc const ở đầu component — xem
    // lý do ở currentStateInput.
    const {
      queryText,
      searchType,
      resultLimit,
      topM,
      useRerank,
      singleModel,
      ocrStripDiacritics,
      asrFilter,
      asrFilterMode,
      ocrFilter,
      ocrFilterMode,
    } = useQueryStore.getState();
    // The two text filters (ASR and OCR) are sent only with the ensemble search
    // and only when at least one has text, from this snapshot like every other
    // parameter, so editing a field while the search runs cannot change it.
    const textFilterFields = { asrFilter, asrFilterMode, ocrFilter, ocrFilterMode };
    setIsLoading(true);
    // Annotations from the PREVIOUS search must not linger onto results from
    // a route that never sets them (single/temporal/trake/ocr) or a fresh
    // ensemble search with no filter active.
    useSearchStore.getState().setVideoAnnotations(null);
    // Đồng hồ cho hai tuyến temporal/TRAKE: backend chỉ trả processing_time ở
    // các tuyến ảnh, nên ở đó đo bằng đồng hồ trình duyệt (có tính cả thời gian
    // truyền, chênh không đáng kể so với vài giây chạy DP).
    const startedAt = performance.now();
    const elapsed = () => (performance.now() - startedAt) / 1000;
    setSummary(null);
    try {
      if (searchType === "temporal") {
        // topVideos: mặc định 5 quá ít khi video ứng viên trùng lặp/gần
        // giống nhau — tăng lên 20 (không thêm control UI nào, giữ nguyên
        // khung nhập). Chi phí: mỗi candidate chạy 1 lần temporal_search()
        // đầy đủ (bidirectional expansion, tối đa ~40 score_frame()/video) —
        // 20 video vẫn rẻ, không đáng lo hiệu năng.
        const res = await videoSearchApi.temporalSearchText(queryText, {
          topVideos: 20,
        });
        if (res.error) {
          console.error("Temporal search text error:", res.error);
          setTemporalCandidates([]);
        } else {
          setTemporalCandidates(res.results ?? []);
        }
        setSummary({
          count: res.error ? 0 : (res.results ?? []).length,
          unit: "videos",
          seconds: elapsed(),
        });
        return;
      }
      if (searchType === "trake") {
        // Cùng lý do như temporal ở trên. TRAKE tốn hơn 1 chút mỗi video
        // (DP O(N×F²) thay vì bidirectional expansion) nhưng F~vài trăm
        // frame/video, N<=5 nên vẫn rất nhanh — 20 vẫn an toàn.
        const res = await videoSearchApi.trakeSearchText(queryText, {
          topVideos: 20,
        });
        // Lượt tìm mới thì dấu "đã chốt" của lượt trước hết nghĩa: thẻ được
        // định danh bằng video + hạng, nên cùng video ở cùng hạng sẽ mang lại
        // dấu cũ trên một mốc chưa hề vào giỏ.
        setTrakePicked({});
        if (res.error) {
          console.error("TRAKE search text error:", res.error);
          setTrakeCandidates([]);
        } else {
          setTrakeCandidates(res.results ?? []);
        }
        setSummary({
          count: res.error ? 0 : (res.results ?? []).length,
          unit: "videos",
          seconds: elapsed(),
        });
        return;
      }

      if (searchType === "ocr") {
        // Pure lexical route - no model call, no blending with the visual
        // route. Results share the SearchResult shape, so they go straight
        // into useSearchStore and the existing grid renders them as-is.
        const res = await videoSearchApi.ocrSearch(
          queryText,
          Number(resultLimit),
          ocrStripDiacritics
        );
        useSearchStore.getState().setTotalTime(res.processing_time);
        useSearchStore.getState().setResults(res.results);
        useSearchStore.getState().setMaxDistance(res.max_distance);
        setOcrCounts({
          phrase: res.phrase_matches,
          allWords: res.all_word_matches,
          searched: res.searched_frames,
        });
        setSummary({
          count: res.results.length,
          unit: "frames",
          seconds: res.processing_time,
        });
        return;
      }

      if (searchType === "track") {
        // Route track batch 2 (camera giao thông): lọc theo vật thể + màu +
        // hướng + tốc độ. Không model, không trộn với route thị giác —
        // CLIP/BEiT3 không mã hoá được chuyển động.
        const res = await videoSearchApi.trackSearch(
          queryText,
          Number(resultLimit)
        );
        useSearchStore.getState().setTotalTime(res.processing_time);
        useSearchStore.getState().setResults(res.results);
        useSearchStore.getState().setMaxDistance(res.max_distance);
        setTrackParsed(res.parsed ?? null);
        setSummary({
          count: res.results.length,
          unit: "frames",
          seconds: res.processing_time,
        });
        return;
      }

      const response =
        searchType === "single"
          ? await videoSearchApi.singleSearch(
              queryText,
              singleModel,
              Number(resultLimit),
              topM,
              useRerank
            )
          : await videoSearchApi.ensembleSearch(
              queryText,
              Number(resultLimit),
              topM,
              useRerank,
              hasTextFilter(textFilterFields)
                ? buildTextFilterParams(textFilterFields)
                : undefined
            );
      useSearchStore.getState().setTotalTime(response.processing_time);
      useSearchStore.getState().setResults(response.results);
      useSearchStore.getState().setMaxDistance(response.max_distance);
      // Old call, kept for the record: stored the annotations alone, so the popover
      // could only ask the LIVE filter boxes which sources had run - wrong when a
      // box is edited while the search is still in flight.
      //   useSearchStore.getState().setVideoAnnotations(response.video_annotations ?? null);
      // sourcesSearched reads the same textFilterFields snapshot the request was
      // built from, so "not searched" always describes the search that is on screen.
      useSearchStore
        .getState()
        .setVideoAnnotations(response.video_annotations ?? null, sourcesSearched(textFilterFields));
      setSummary({
        count: response.results.length,
        unit: "frames",
        seconds: response.processing_time,
      });
      // Backend không còn demo_mode (đã bỏ chế độ sinh dữ liệu giả); thay bằng
      // has_image để biết bộ ảnh trên máy đã phủ hết kết quả chưa.
      const missing = response.results.filter(
        (r) => r.has_image === false
      ).length;
      if (missing > 0) {
        console.warn(
          `[frames] ${missing}/${response.results.length} kết quả chưa có ảnh ` +
            `trên đĩa → hiển thị placeholder. Tải thêm ZIP frame để đầy đủ.`
        );
      }
    } catch (err) {
      console.error("Search failed:", err);
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Lấy trạng thái của một người khác làm trạng thái của MÌNH.
   *
   * Không phải "xem nhờ rồi trả lại". Sau khi bấm, truy vấn, tham số và khung
   * đã chọn của họ trở thành của bạn — kể cả trên bảng chung, nên đồng đội
   * thấy bạn đang ở cùng chỗ với họ. Vì thế không có dải "đang xem" và cũng
   * chẳng có gì để "thoát".
   *
   * Chạy lại truy vấn chứ không chép danh sách kết quả: cùng truy vấn, cùng
   * tham số, cùng index thì ra cùng kết quả, nên chép lại chỉ là nhân bản thứ
   * tính lại được trong một giây rưỡi.
   */
  const applyPeerState = (state: SearchState) => {
    const q = useQueryStore.getState();
    q.setQueryText(state.query_text);
    q.setSearchType(state.search_type as SearchType);
    // Từng tham số một, và chỉ khi có mặt: bản ghi cũ có thể thiếu trường mới
    // thêm, mà ghi đè bằng undefined sẽ xoá mất cấu hình đang dùng.
    if (state.params.resultLimit) q.setResultLimit(state.params.resultLimit);
    if (typeof state.params.topM === "number") q.setTopM(state.params.topM);
    if (typeof state.params.useRerank === "boolean") {
      q.setUseRerank(state.params.useRerank);
    }
    if (state.params.singleModel) {
      q.setSingleModel(state.params.singleModel as ModelName);
    }
    if (typeof state.params.ocrStripDiacritics === "boolean") {
      q.setOcrStripDiacritics(state.params.ocrStripDiacritics);
    }
    usePickedFrameStore
      .getState()
      .set(state.picked_frame, state.user.display_name);
    // Ghi ngay, kèm đúng khung họ đã chọn: từ giây này trạng thái đó là của
    // mình. Ghi TRƯỚC doSearch và gọi doSearch với record:false, vì nhánh ghi
    // trong doSearch luôn xoá khung đang chọn — nó phục vụ một truy vấn mới,
    // không phải một trạng thái vừa chép về.
    if (state.picked_video && state.picked_frame && state.picked_frame_idx !== null) {
      recordState({
        name: state.picked_frame,
        video: state.picked_video,
        frameIdx: state.picked_frame_idx,
      });
    } else {
      recordState();
    }
    void doSearch({ record: false });
  };

  const { hasQueried, setHasQueried } = useIsQueryStore();
  useEffect(() => {
    if (!hasQueried && queryText && isLoading) {
      setHasQueried(true);
    }
  }, [results, hasQueried, setHasQueried, queryText, isLoading]);

  // A text filter found relevant for one task's video content has no bearing
  // on the next task — clear both filters (ASR and OCR) back to defaults
  // whenever a different task opens. Translate/Expand deliberately do NOT do
  // this (they only touch queryText), so this effect is scoped to just these
  // four fields.
  useEffect(() => {
    const query = useQueryStore.getState();
    query.setAsrFilter("");
    query.setAsrFilterMode("substring");
    query.setOcrFilter("");
    query.setOcrFilterMode("substring");
  }, [activeTask?.id]);

  // Everything below renders `shownResults`, never `results`, so the grid, the
  // grouping and the count all agree about what is on screen.
  //
  // Pinning (focusVideos) and narrowing the grid (showOnlyPinned) used to be
  // the same action: filterByFocus ran the moment focusVideos was non-empty,
  // so pinning one video removed every other video's card -- including its
  // own pin button -- before a second pin was ever possible. filterByFocus
  // now only runs when showOnlyPinned is explicitly on; pinning by itself
  // just marks cards (see the focusVideos.includes check FrameDisplay uses
  // for card styling) without touching what is on screen.
  //
  // Memoised because it feeds the grouping effect's dependency array. Unmemoised,
  // filterByFocus hands back a fresh array on every render whenever a focus is
  // active, so the effect re-ran and re-set groupedResult forever.
  const shownResults = useMemo(
    () => (showOnlyPinned ? filterByFocus(results, focusVideos) : results),
    [results, focusVideos, showOnlyPinned]
  );

  // "Mỗi video một thẻ" (onePerVideo, default off): one card per video, its best
  // frame. Grouped AFTER shownResults, so the pin filter still narrows first, and
  // over the whole list, not the visible page. Never on OCR results (their
  // `distance` is a word count; detected from the data, as the popup strip does)
  // and never on the temporal/TRAKE routes (isFrameRoute is false there).
  //
  // A memo, not an effect that sets state: the grouping effect this file used to
  // have re-ran forever on an unmemoised dependency. With the option off,
  // buildGridResults hands back `shownResults` itself, so `gridResults` IS
  // shownResults and everything below behaves exactly as before.
  const resultsAreOcr = useMemo(() => isOcrResults(results), [results]);
  const groupingAllowed = isFrameRoute && !resultsAreOcr;
  const grid = useMemo(
    () => buildGridResults(shownResults, onePerVideo, groupingAllowed),
    [shownResults, onePerVideo, groupingAllowed]
  );
  const gridResults = grid.cards;

  // Show Top can be 500 (2000 on the OCR route) and that is deliberate — the
  // frame you want may rank 300th, and you cannot pick what you cannot see.
  // What is NOT affordable is painting all of them at once: each keyframe is a
  // full 1280x720 JPEG, ~145 KB on the wire and ~3.5 MB decoded, so 345 tiles
  // is roughly 49 MB of download and a gigabyte of image memory. So the search
  // keeps its reach and the grid pages: a screenful at a time, more as you get
  // to the bottom.
  const PAGE_SIZE = 100;
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const moreRef = useRef<HTMLDivElement | null>(null);

  // A new result set, a change of filter, or flipping the one-card-per-video
  // option starts the window over: visibleCount counts CARDS, and the list that
  // pages is the grid list (grouped or not). Was keyed on [shownResults], which
  // is the same array whenever the option is off.
  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [gridResults]);

  // Was: shownResults.slice(0, visibleCount)
  const visibleResults = useMemo(
    () => gridResults.slice(0, visibleCount),
    [gridResults, visibleCount]
  );
  // Was: visibleCount < shownResults.length
  const hasMore = visibleCount < gridResults.length;

  // Grow when the sentinel scrolls into view. The button below it does the same
  // thing on click, so a browser that never fires this is still fully usable.
  useEffect(() => {
    const node = moreRef.current;
    if (!node || !hasMore) {
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setVisibleCount((count) => count + PAGE_SIZE);
      }
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, visibleCount]);

  // Nhãn E1…EN là chính các đoạn người dùng gõ, tách đúng luật của
  // preprocess.py:_split_query_text.
  const queryParts = splitQueryParts(queryText);


  // Esc đóng lớp lịch sử. Đăng ký ở đây chứ không trong SearchHistory: lớp phủ
  // do component này dựng, nên nó cũng phải là chỗ gỡ.
  useEffect(() => {
    if (view !== "history") {
      return;
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onLeaveHistory?.();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [view, onLeaveHistory]);

  const openVideoAt = (videoId: string, frameIdx: number) => {
    setframeId(String(frameIdx));
    setVideoUrl(videoId);
    setStartTime(startMsAt(videoId, frameIdx));
    setTrakeSlot(null);
    setShowPopup(true);
  };

  return (
    // pl-[368px] chừa chỗ cho cột nhập truy vấn cố định bên trái (360px + p-2).
    // Hai con số này phải đi cùng nhau; đổi một cái mà quên cái kia thì hoặc
    // cột đè lên ảnh, hoặc thừa một dải trắng dọc suốt trang.
    <div className="relative min-h-screen bg-proto-canvas p-2 pl-[368px]">
      {/* Khối header cũ — logo "Scavenger", chữ VQF, badge phiên bản, ô "Tới
          frame" và badge trạng thái API — đã tháo khỏi đây.

          Nó cao gần 90px (Header dùng `my-9`) và chỉ có ở màn Search, tức là
          ăn mất gần một hàng kết quả mỗi lần tìm. Ba thứ có việc thật đã lên
          thanh điều hướng chung, nơi chúng dùng được ở mọi màn; logo và chữ
          VQF thì không gắn hành động nào nên bỏ hẳn. */}

      {/* Đề bài của task đang mở — nguyên văn, chỉ đọc, không bao giờ dịch.
          Pin lên đỉnh khung nhìn: cuộn qua cả trăm kết quả vẫn còn thấy đề. */}
      {activeTask && <TaskBrief task={activeTask} />}

      {/* Bảng "Cả nhóm đang tìm câu này" đã bỏ. Nó chỉ hiện truy vấn ĐANG gõ
          của từng người, mà bảng Lịch sử trên thanh nav hiện đúng những dòng
          đó cộng thêm mọi truy vấn cũ — hai bảng chồng nhau, bảng ở đây lại
          ngốn một khối ngay dưới đề bài, đúng chỗ hàng kết quả đầu tiên. */}

      {/* Project Description (only when no results) */}
      {!hasQueried && !activeTask && (
        <div className="max-w-4xl mx-auto mt-10">
          <ProjectDescription />
        </div>
      )}
      {/* Gated on the video rather than on `result`: a TRAKE event opens the
          same popup without there being a SearchResult behind it. */}
      {showPopup && videoUrl !== "" && (
        <VideoPopup
          activeTask={activeTask}
          rowsPerQuery={rowsPerQuery}
          onBasketChanged={onBasketChanged}
          videoId={videoUrl}
          frameId={frameId}
          startAt={startTime}
          onClose={() => {
            setShowPopup(false);
            setTrakeSlot(null);
          }}
          setStartAt={setStartTime}
          trakeSlot={
            trakeSlot && {
              cardKey: trakeSlot.cardKey,
              index: trakeSlot.index,
              label: trakeSlot.label,
              total: trakeSlot.total,
              onCommit: (frame, range) => {
                // Ô mốc từng để trống ảnh ở đây (`url: ""`), và thẻ TRAKE rơi
                // vào nhánh nền đen chỉ in con số — tức là vừa dừng video ở
                // đúng khoảnh khắc mình muốn thì ô đó lại là chỗ DUY NHẤT trên
                // màn hình không cho nhìn thấy nó.
                //
                // Một frame bất kỳ không có file ảnh riêng, nên lấy keyframe
                // gần nhất làm ảnh đại diện — đúng thứ FramePreview và giỏ đã
                // làm cho mọi dòng đáp án. `frame_idx` vẫn là số đã chốt, và
                // `name` vẫn là nhãn chốt tay chứ không phải tên keyframe: đặt
                // tên keyframe vào đây sẽ khiến dải "cách khớp khác" khoanh
                // nhầm một ứng viên mà người dùng không hề chọn.
                const near = nearestKeyframeFor(videoUrl, frame);
                swapTrakeEvent(trakeSlot.cardKey, trakeSlot.index, {
                  name: `${videoUrl} · frame ${frame}`,
                  url: near ? keyframeUrl(near.name) : "",
                  frame_idx: frame,
                  timestamp: "",
                  byHand: true,
                });
                // Hai đầu vừa ghim cho riêng mốc này, cất nguyên như đã ghim.
                // Việc sắp thứ tự và loại bỏ cửa sổ đóng để `eventWindowFields`
                // làm một chỗ, lúc đổ vào giỏ — chia đôi luật ra hai nơi là
                // cách chắc chắn để hai nơi lệch nhau.
                if (range) {
                  const slot = trakeSlot;
                  setTrakeEventRanges((current) => ({
                    ...current,
                    [slot.cardKey]: {
                      ...(current[slot.cardKey] ?? {}),
                      [slot.index]: range,
                    },
                  }));
                }

                // Nhánh "với KIS/Q&A thì mốc này đi thẳng vào giỏ" đã bỏ, cùng
                // với đoạn giữ popup mở cho riêng nhánh đó:
                //
                //     if (activeTask && activeTask.type !== "trake") {
                //       void commitTrakeFrame(videoUrl, frame);
                //       markTrakePicked(trakeSlot.cardKey, trakeSlot.index);
                //     }
                //
                // Không còn đường nào chạy tới: `openTrakeEvent` chỉ đặt ô mốc
                // cho câu TRAKE, nên `onCommit` giờ chỉ chạy ở đó. Câu KIS/Q&A
                // vào giỏ bằng chính nút Add Answer của popup thường, y như
                // ensemble. `commitTrakeFrame` vẫn còn việc — nút "+ Chốt"
                // trên từng ô của thẻ vẫn gọi nó.
                //
                // Đóng popup: chốt xong một ô thì việc kế tiếp là mở ô E2, mà
                // ô đó nằm trên thẻ phía sau — popup đứng chắn đúng đường đi.
                setShowPopup(false);
                setTrakeSlot(null);
              },
            }
          }
        />
      )}

      {/* Temporal Search Panel — Alg.4, mở khi bấm "⏱" trên 1 kết quả search */}
      {showTemporalPanel && temporalAnchor && (
        <TemporalSearchPanel
          anchorName={temporalAnchor.name}
          anchorUrl={temporalAnchor.url}
          onClose={() => setShowTemporalPanel(false)}
        />
      )}

      {isFrameRoute && focusVideos.length > 0 && (
        <div className="max-w-[98%] mx-auto mb-2 flex flex-wrap items-center gap-1.5 font-baloo">
          <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
            Đang soi
          </span>
          {focusVideos.map((video) => (
            <span
              key={video}
              className="flex items-center gap-1 rounded-full border border-proto-primary bg-proto-primary/10 pl-2.5 text-[12px] font-mono text-proto-primary-active"
            >
              {video}
              <button
                type="button"
                title={`Bỏ lọc ${video}`}
                onClick={() => toggleFocusVideo(video)}
                className="flex h-10 w-10 items-center justify-center font-bold"
              >
                ×
              </button>
            </span>
          ))}
          <button
            type="button"
            onClick={clearFocus}
            className="text-[12px] px-2.5 py-1 rounded-[7px] border border-proto-line text-proto-muted"
          >
            Xoá lọc
          </button>
          {/* Ghim (focusVideos) chỉ đánh dấu -- nó không còn tự lọc lưới, vì
              lọc ngay lập tức từng xoá luôn thẻ + nút ghim của video thứ hai
              trước khi kịp bấm. Bấm nút này mới thật sự thu hẹp lưới. */}
          <button
            type="button"
            onClick={toggleShowOnlyPinned}
            title={
              showOnlyPinned
                ? "Hiện lại tất cả kết quả"
                : "Chỉ hiện các video đã ghim"
            }
            className={`text-[12px] px-2.5 py-1 rounded-[7px] border font-bold ${
              showOnlyPinned
                ? "bg-proto-primary border-proto-primary text-white"
                : "border-proto-line text-proto-muted"
            }`}
          >
            {showOnlyPinned ? "Đang lọc · Hiện tất cả" : "Chỉ hiện video đã ghim"}
          </button>
        </div>
      )}

      {hasQueried && searchType === "ocr" && ocrCounts && (
        <div className="max-w-[98%] mx-auto mb-2">
          <OcrCountBanner counts={ocrCounts} shown={results.length} />
        </div>
      )}

      {hasQueried && searchType === "track" && trackParsed && (
        <div className="max-w-[98%] mx-auto mb-2">
          <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-2 text-sm text-blue-900 flex flex-wrap gap-x-6 gap-y-1">
            <span className="font-semibold">Route track hiểu câu là:</span>
            {(["groups", "colors", "directions", "speeds"] as const).map(
              (k) =>
                trackParsed[k] && (
                  <span key={k}>
                    {k === "groups"
                      ? "đối tượng"
                      : k === "colors"
                        ? "màu"
                        : k === "directions"
                          ? "hướng"
                          : "tốc độ"}
                    :{" "}
                    <span className="font-mono">
                      {trackParsed[k].join(" | ")}
                    </span>
                  </span>
                )
            )}
          </div>
        </div>
      )}

      {/* Toggle for the one-card-per-video view. Its own row above the grid, not
          in the pin chip row (that row only exists while videos are pinned), and
          only where grouping is allowed. The nav bar's "N khung" is the size of
          the search and does not change; while grouped, the count of cards is
          shown here instead. Same button style as "Chỉ hiện video đã ghim". */}
      {groupingAllowed && hasQueried && results.length > 0 && (
        <div className="max-w-[98%] mx-auto mb-2 flex flex-wrap items-center gap-1.5 font-baloo">
          <button
            type="button"
            onClick={toggleOnePerVideo}
            aria-pressed={onePerVideo}
            title="Gộp mỗi video thành một thẻ (khung điểm cao nhất). Mở video để xem các khung khác."
            className={`text-[12px] px-2.5 py-1 rounded-[7px] border font-bold ${
              onePerVideo
                ? "bg-proto-primary border-proto-primary text-white"
                : "border-proto-line text-proto-muted"
            }`}
          >
            {onePerVideo ? "Đang gộp · Hiện tất cả khung" : "Mỗi video một thẻ"}
          </button>
          {onePerVideo && (
            <span className="text-[12px] text-proto-muted">
              <b className="font-mono text-proto-ink">{gridResults.length}</b> video ·{" "}
              <b className="font-mono text-proto-ink">{shownResults.length}</b> khung
            </span>
          )}
        </div>
      )}

      {/* Dòng "50 kết quả · 1.8s" đã lên thanh điều hướng. Ở đây nó là một
          khung riêng cao 40px nằm giữa đề bài và lưới ảnh, đẩy hàng kết quả
          đầu tiên xuống mà chỉ để nói hai con số. Thanh nav đọc thẳng từ
          useSearchStore nên không phải luồn state lên. */}


      {/* Tuyến OCR đọc CHỮ chứ không nhìn ảnh, nên thẻ phải rộng hơn: 240px
          vừa đủ cho ảnh nhưng không đủ cho một đoạn chữ. 360px cho khoảng gấp
          rưỡi số chữ trên mỗi dòng, mà vẫn còn 3-4 cột trên màn hình thường.
          Tuyến ảnh giữ nguyên 240px — ở đó chữ chỉ là tên file với timestamp. */}
      {isFrameRoute && (isLoading || hasQueried) && (
        <div
          className={`max-w-[98%] mx-auto grid gap-6 ${
            searchType === "ocr"
              ? "grid-cols-[repeat(auto-fill,minmax(360px,1fr))]"
              : "grid-cols-[repeat(auto-fill,minmax(240px,1fr))]"
          }`}
        >
          <FrameDisplay
            results={visibleResults}
            maxDistance={maxDistance}
            isLoading={isLoading}
            onUseAsAnchor={handleUseAsAnchor}
            onAddToBasket={
              activeTask && activeTask.type !== "trake"
                ? handleAddToBasket
                : undefined
            }
            onToggleFocus={toggleFocusVideo}
            focusVideos={focusVideos}
            // Khung bạn (hoặc người bạn đang coi) đã bấm vào. Trước đây hai
            // dòng này chỉ có ở lưới "nhóm theo Video ID", nên ở chế độ mặc
            // định không thẻ nào được khoanh - đó là lý do vòng đỏ "không thấy
            // đâu". Lưới kia bỏ rồi, nên chúng về đúng chỗ duy nhất còn lại.
            highlightFrame={pickedFrame ?? undefined}
            highlightLabel={pickedFrom ?? undefined}
            // Present only while grouped. Spread rather than passed as
            // `groupInfoByFrame={undefined}`, so with the option off FrameDisplay
            // receives the very same props as before this option existed.
            {...(grid.groupInfoByFrame
              ? { groupInfoByFrame: grid.groupInfoByFrame }
              : {})}
            onClick={(result) => {
              setframeId(frameIdFromName(result.name));
              setVideoUrl(videoIdFromFrame(result.frame));
              setStartTime(startMsFromResult(result));
              setShowPopup(true);
            }}
          />
        </div>
      )}

      {/* Paging sentinel. Scrolling here loads the next page; the button does
          the same on click, so this still works if IntersectionObserver never
          fires. Both views read `visibleResults`, so the grouped list is
          bounded too. */}
      {isFrameRoute && hasQueried && !isLoading && hasMore && (
        <div
          ref={moreRef}
          className="max-w-[98%] mx-auto mt-6 flex items-center justify-center"
        >
          <button
            type="button"
            onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}
            className="text-[12.5px] px-4 py-2 rounded-[8px] border border-proto-line bg-white text-proto-body"
          >
            Xem thêm — đang hiện {visibleResults.length}/{gridResults.length}
          </button>
        </div>
      )}
      {/* mb-[280px] → mb-10. Khoảng trống đó chừa chỗ cho thanh nhập nổi ở
          đáy màn hình; thanh đó chuyển sang cột trái nên không còn gì che
          hàng kết quả cuối. Vẫn để một khoảng thở cuối trang. */}
      <div className="mb-10" />

      {/* Lưới "nhóm theo Video ID" đã bỏ cùng với ô Sorted By.

          Nó dựng lại toàn bộ lưới một lần nữa, chỉ khác là bọc mỗi video trong
          một khung riêng — gần hai trăm dòng JSX gần như trùng lặp, cho một
          cách sắp xếp mà thứ tự theo độ khớp vốn đã tốt hơn: R@k chấm k dòng
          đầu, mà nhóm theo video thì đẩy kết quả tốt nhất xuống giữa danh
          sách. Nút 🎯 trên từng thẻ vẫn lọc theo video như cũ. */}

      {/* Temporal Search Results — Alg.4 text-query path */}
      {(isLoading || (hasQueried && searchType === "temporal")) && (
        <div className="max-w-[98%] mx-auto mb-10 px-4">
          {isLoading ? (
            <p className="text-sm text-proto-muted animate-pulse">
              Đang tìm kiếm…
            </p>
          ) : temporalCandidates.length === 0 ? (
            <p className="text-sm text-proto-muted">Không tìm thấy kết quả.</p>
          ) : (
            <TemporalCandidates
              results={temporalCandidates}
              parts={queryParts}
              fpsOf={(video) =>
                (KeyframeFPS as Record<string, number>)[video ?? ""] ?? 0
              }
            />
          )}
        </div>
      )}

      {/* TRAKE Search Results */}
      {(isLoading || (hasQueried && searchType === "trake")) && (
        <div className="max-w-[98%] mx-auto mb-10 px-4">
          {isLoading ? (
            <p className="text-sm text-proto-muted animate-pulse">
              Đang tìm kiếm…
            </p>
          ) : trakeCandidates.length === 0 ? (
            <p className="text-sm text-proto-muted">Không tìm thấy kết quả.</p>
          ) : (
            <>
              {/* Nút "Điền N video vào giỏ" đã bỏ. Nó đổ thẳng cả danh
                  sách ứng viên vào giỏ theo đúng thứ hạng thuật toán, nhưng
                  TRAKE chấm theo TỪNG mốc — một dòng sai video là mất trắng cả
                  dòng, mà đổ hàng loạt thì hai chục dòng đầu đều là hai chục
                  video khác nhau, không dòng nào được soi trước khi nộp. Chốt
                  từng dòng bằng nút trên mỗi thẻ, rồi rải các dòng còn lại
                  bằng "+ Điền tự động" trong giỏ. */}
              <TrakeCandidates
                results={trakeCandidates}
                parts={queryParts}
                swaps={trakeSwaps}
                onSwap={swapTrakeEvent}
                onOpenEvent={openTrakeEvent}
                onCommit={
                  activeTask?.type === "trake" ? commitTrakeRow : undefined
                }
                // Chốt từng mốc chỉ có nghĩa khi dòng đáp án mang MỘT frame.
                // Câu TRAKE thì một dòng thiếu mốc là một dòng sai, nên ở đó
                // vẫn chỉ có nút nộp cả hàng phía trên.
                onPickOne={
                  activeTask && activeTask.type !== "trake"
                    ? commitTrakeFrame
                    : undefined
                }
                picked={trakePicked}
                onPicked={markTrakePicked}
                qaAnswer={activeTask?.type === "qa" ? trakeQaText : undefined}
                onQaAnswer={activeTask?.type === "qa" ? setTrakeQaText : undefined}
                onResetSlot={resetTrakeEvent}
              />
            </>
          )}
        </div>
      )}

      {/* Lịch sử tìm — một lớp CHỒNG LÊN màn Search, không phải một trang
          thay thế nó.

          Trang riêng thì bấm vào là mất hết kết quả đang xem, mà lịch sử là
          thứ người ta liếc qua để quyết định "có nên thử lại câu này không" —
          quyết định đó dựa vào chính đám kết quả đang có. Đóng lớp này ra là
          thấy lại nguyên trạng, không phải search lại.

          Bấm nền tối hoặc phím Esc cũng đóng, vì một hộp chỉ đóng được bằng
          đúng một nút ở góc là thứ hay làm người ta mắc kẹt. */}
      {view === "history" && activeTask && (
        <div
          className="fixed inset-0 z-[999] bg-black/40 flex items-start justify-center p-4 pt-16"
          onClick={() => onLeaveHistory?.()}
        >
          <div
            className="bg-proto-canvas rounded-xl shadow-2xl w-full max-w-5xl max-h-[85vh] overflow-y-auto font-baloo relative"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => onLeaveHistory?.()}
              title="Đóng (Esc)"
              className="absolute top-3 right-3 z-10 flex h-9 w-9 items-center justify-center rounded-full text-[#c64545] hover:bg-[#c64545]/15 font-bold text-lg"
            >
              ×
            </button>
            <SearchHistory
              taskId={activeTask.id}
              taskCode={activeTask.code}
              onOpenState={(state) => {
                applyPeerState(state);
                // Chạy lại xong thì kết quả nằm ở lưới phía sau, nên đóng lớp
                // này ra cho thấy.
                onLeaveHistory?.();
              }}
              onOpenVideo={openVideoAt}
            />
          </div>
        </div>
      )}

      {/* Ô nhập truy vấn — cột trái cố định.
          Bề rộng phải khớp `pl-[368px]` ở thẻ bọc ngoài cùng (360 + p-2).

          Trước đây nó là một thanh nổi giữa đáy màn hình
          (`max-w-[900px] fixed bottom-6 left-1/2 -translate-x-1/2`). Thanh đó
          nằm ĐÈ lên lưới kết quả, nên mỗi khối kết quả phải chừa `mb-[280px]`
          để hàng cuối không bị nó che — 280px trống dưới mọi trang, và mở cụm
          "Tuỳ chọn" ra thì thanh cao thêm và che nhiều hơn nữa.

          Cột trái thì không đè lên gì: nó chiếm chỗ của chính nó, ảnh nằm
          trọn phần còn lại. Đổi lại ô nhập hẹp hơn, và đó là lý do ô chữ
          thành nhiều dòng — xem QueryInput. */}
      <div className="fixed left-0 top-[var(--nav-h)] bottom-0 w-[360px] z-40 overflow-y-auto bg-white border-r border-proto-line shadow-lg">
        <QueryInput
          doSearch={doSearch}
          disabled={isSearchDisabled || isLoading}
        />
      </div>
    </div>
  );
}

export default App;