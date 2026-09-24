// frontend/src/types/api.ts
//
// Khớp với backend/app/main.py + preprocess.py hiện tại (arXiv 2504.08384).
// Đã BỎ hoàn toàn các hàm gọi endpoint cũ: searchByText, searchByTextNoAgent,
// searchByFaiss, searchByOCR, searchByCombined, filterSearch — toàn bộ trỏ tới
// endpoint /text-search, /faiss-search, /ocr-search, /combined-search,
// /filter-search đã bị xóa khỏi main.py (xem docstring đầu file main.py:
// "Đã BỎ toàn bộ endpoint cũ... thất bại im lặng").
//
// Thay bằng 3 endpoint thật đang tồn tại: /ensemble-search, /single-search,
// /temporal-search — cùng /status và /health.

// ─────────────────────────────────────────────────────────────────────────────
//  Response types — khớp SearchResultEx / SearchResponseEx trong main.py
// ─────────────────────────────────────────────────────────────────────────────

export interface RouteInfo {
  rank: number;
  score: number;
}

export interface SearchResult {
  frame: string;
  distance: number;
  url: string;
  name: string;
  // Các trường mở rộng — optional, để tương thích ngược nếu backend cũ hơn
  // (hoặc demo mode) không trả đủ. Xem SearchResultEx trong main.py.
  video?: string;
  frame_idx?: number;
  timestamp?: string;
  // routes: model nào tìm ra frame này, xếp hạng bao nhiêu trong model đó.
  // Dòng nào có mặt cả "beit3" lẫn "clip" đáng tin hơn dòng chỉ có 1 model.
  routes?: Record<string, RouteInfo>;
  // Ảnh đã tải về chưa. Index phủ đủ 868k frame nhưng ảnh tải riêng theo ZIP,
  // nên false là bình thường → FrameDisplay vẽ placeholder.
  has_image?: boolean;
  demo?: boolean;
}

/**
 * One source's (asr or ocr) best result for a video — matches backend's
 * SourceMatch dataclass (backend/app/text_signal.py). match_frame/match_type
 * are null when location is "none".
 */
export interface SourceMatch {
  match_frame: string | null;
  match_type: "exact" | "normalized" | null;
  location: "here" | "elsewhere" | "none";
}

/**
 * Per-video text-signal annotation — matches backend's VideoAnnotation
 * dataclass (backend/app/text_signal.py). Purely additive: it never removes
 * a result or changes a rank, see SearchResponse.video_annotations below.
 *
 * Stage C replaced the old flat `sources`/`snippets` arrays with per-source
 * SourceMatch objects naming the actual frame that matched (and whether it
 * is one already on screen) — components reading the old shape (notably
 * TextSignalBadge) need a matching rewrite; see Stage C's report.
 */
export interface VideoAnnotation {
  matched: boolean;
  score: number;
  mode: string;
  asr: SourceMatch;
  ocr: SourceMatch;
}

/**
 * Modes of the two independent text filters. Match the backend's TextMatchMode
 * (ASR) and OcrFilterMode (OCR) in backend/app/text_signal.py: OCR has no BM25
 * index, so it has no "bm25" (the backend answers HTTP 422 to it).
 */
export type AsrFilterMode = "substring" | "regex" | "bm25";
export type OcrFilterMode = "substring" | "regex";

/**
 * The text-filter part of the /ensemble-search request: an ASR filter and an
 * OCR filter, each with its own mode. When either string is non-empty the
 * backend uses these and ignores the legacy text_filter / text_filter_mode
 * (still accepted, so an older frontend keeps working). Both strings are capped
 * at 200 characters (TEXT_FILTER_MAX_CHARS); a longer one fails the whole search.
 */
export interface TextFilterRequestFields {
  asr_filter?: string;
  asr_filter_mode?: AsrFilterMode;
  ocr_filter?: string;
  ocr_filter_mode?: OcrFilterMode;
}

export interface SearchResponse {
  total_results: number;
  returned_results: number;
  results: SearchResult[];
  query_type: string;
  processing_time: number;
  max_distance: number;
  // true nếu backend đang chạy demo mode (chưa có beit3.index/clip.index thật)
  demo_mode?: boolean;
  // Present only on /ensemble-search when a text filter was non-empty — keyed
  // by video_id. No frame is ever dropped because of this; see main.py.
  video_annotations?: Record<string, VideoAnnotation>;
  // True when ANY text filter is active (split or the legacy single one).
  text_filter_active?: boolean;
  // The active source's mode, or "mixed" when both filters are used.
  text_filter_mode?: string;
  // Independent ASR / OCR filters: which sources ran, and with which mode.
  asr_filter_active?: boolean;
  ocr_filter_active?: boolean;
  asr_filter_mode?: AsrFilterMode | null;
  ocr_filter_mode?: OcrFilterMode | null;
}

/** One OCR text hit. Same shape as SearchResult, so the grid is reused. */
export interface OcrSearchResult extends SearchResult {
  /** What Vintern read on this frame - read it directly, no need to open it. */
  ocr_text?: string;
  /** The frame holds the WHOLE typed phrase, not its words scattered about. */
  exact_phrase?: boolean;
  matched_words?: number;
  total_words?: number;
}

export interface OcrSearchResponse extends SearchResponse {
  results: OcrSearchResult[];
  /** Images holding the typed phrase verbatim. */
  phrase_matches: number;
  /**
   * Images holding every word, each as a whole word - also the size of the
   * result. The number to watch: measured over the 25 preliminary queries
   * (notebook 78), <= 4 puts the right video first 6 times out of 6, while
   * >= 142 gets it right only 1 in 6 - meaning type more text rather than
   * paging through 500 images.
   */
  all_word_matches: number;
  /** Total frames carrying text - the denominator for everything above. */
  searched_frames: number;
}

export interface TemporalCandidate {
  name: string;
  url: string;
  frame_idx?: number;
  timestamp?: string;
  score?: number;
}

export interface TemporalSearchResult {
  video?: string;
  start_frame?: string;
  end_frame?: string;
  start_ts?: string;
  end_ts?: string;
  start_frame_idx?: number;
  end_frame_idx?: number;
  combined_score?: number;
  start_url?: string;
  end_url?: string;
  n_left?: number;
  n_right?: number;
  // MỚI — paper Figure 4c "Boundary Selection": danh sách ứng viên trái/phải
  // để người dùng tự điều chỉnh nếu cặp đề xuất chưa đúng ý ("Users can
  // review these suggestions and adjust them if necessary").
  left_candidates?: TemporalCandidate[];
  right_candidates?: TemporalCandidate[];
  demo?: boolean;
  error?: string;
}

// TRAKE — tổng quát hóa Alg.4 từ 2 điểm (start/end) lên N sự kiện tuần tự.
// Khớp TrakeEvent/TrakeSearchResponse trong main.py.
export interface TrakeEvent {
  name: string;
  url: string;
  frame_idx?: number;
  timestamp?: string;
  score?: number;
  candidates?: TemporalCandidate[];
}

export interface TrakeSearchResult {
  video?: string;
  events?: TrakeEvent[];
  combined_score?: number;
  error?: string;
}

// Auto-discovery — không cần anchor_name thủ công. Mỗi phần tử là 1 video
// ứng viên, discovery_score = TẦN SUẤT (bao nhiêu query khớp video này, số
// nguyên), discovery_score_sum = tổng điểm các query đã khớp (tie-break).
// Khác combined_score (điểm thật sau khi chạy đủ thuật toán cho video đó).
export interface TemporalCandidateResult extends TemporalSearchResult {
  discovery_score?: number;
  discovery_score_sum?: number;
}

export interface TrakeCandidateResult extends TrakeSearchResult {
  discovery_score?: number;
  discovery_score_sum?: number;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Status / health — khớp system_status() trong preprocess.py
// ─────────────────────────────────────────────────────────────────────────────

export interface OcrStatus {
  ready: boolean;
  files_present: boolean;
  with_marks_path: string;
  no_marks_path: string;
  total_frames?: number;
  frames_with_text?: number;
  load_seconds?: number;
}

export interface AsrTextStatus {
  ready: boolean;
  files_present: boolean;
  file_path: string;
  entries_loaded: number;
  load_seconds: number;
}

export interface TextSignalStatus {
  bm25_ready: boolean;
  bm25_unavailable_reason: string | null;
  bm25_release_dir: string;
  bm25_documents: number;
}

export interface SystemStatus {
  demo_mode: boolean;
  device: string;
  index_dir: string;
  image_base_url: string;
  pipeline_order: string;
  files: Record<string, boolean>;
  vectors: { beit3: number; clip: number };
  keyframes: number;
  videos: number;
  models: { fine_grained: string; coarse_grained: string };
  ensemble_weights: Record<string, number>;
  // Optional: present on every real /status response (see main.py's status()),
  // marked optional here only so older mocked responses in tests don't break.
  ocr?: OcrStatus;
  asr_text?: AsrTextStatus;
  text_signal?: TextSignalStatus;
}

export type WarmupState = "cold" | "warming" | "ready" | "failed";

export interface WarmupStatus {
  state: WarmupState;
  seconds: number | null;
  error: string | null;
}

export interface HealthResponse {
  ok: boolean;
  warmup: WarmupStatus;
}

export interface ApiError {
  detail: string;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Model dùng cho /single-search và /temporal-search
// ─────────────────────────────────────────────────────────────────────────────

export type ModelName = "beit3" | "clip";

// ─────────────────────────────────────────────────────────────────────────────
//  Submit (chưa có endpoint /submit ở backend — xem docs/KIEN_TRUC_PIPELINE.md
//  mục "Bước 12 — Xuất file nộp", vẫn là TODO). Giữ type + hàm gọi sẵn để
//  SubmitForm không phải sửa gì khi backend bổ sung /submit sau này, nhưng gọi
//  bây giờ sẽ nhận 404 — không dùng cho tới khi có xác nhận endpoint tồn tại.
// ─────────────────────────────────────────────────────────────────────────────

export interface ResultSubmit {
  values: number[];
  result: SearchResult;
  answer: string;
  src: string;
}

export interface SubmitRespond {
  code: string;
  message: string;
}

// ─────────────────────────────────────────────────────────────────────────────
//  API client
// ─────────────────────────────────────────────────────────────────────────────

// `??`, not `||`, and matching api/base.ts.
//
// An empty VITE_API_BASE_URL is a meaningful value: it means "same origin", so
// requests go through the dev server and get proxied to whatever AIC_DEV_API
// points at (see vite.config.ts). `||` treated that as unset and substituted
// localhost:8000, which meant the collaboration API proxied correctly while
// every search call here went to a backend nobody was running.
const API_BASE_URL =
  (import.meta as { env?: { VITE_API_BASE_URL?: string } }).env
    ?.VITE_API_BASE_URL ?? "http://localhost:8000";

class VideoSearchApi {
  private async handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      const error: ApiError = await response.json();
      throw new Error(
        error.detail || `HTTP ${response.status}: ${response.statusText}`
      );
    }
    return response.json();
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return this.handleResponse<T>(response);
  }

  /**
   * Alg.3 — search → rerank từng model (Alg.2) → ensemble.
   * Endpoint chính, dùng cho search bình thường trên UI.
   */
  async ensembleSearch(
    query: string,
    limit = 100,
    topM = 50,
    useRerank = true,
    textFilter?: TextFilterRequestFields
  ): Promise<SearchResponse> {
    // The text filter is sent as the four asr_filter / ocr_filter fields, and
    // only when at least one is set (the caller passes undefined otherwise).
    // Previous version sent the single legacy pair on every request:
    //   text_filter: textFilter,
    //   text_filter_mode: textFilterMode,
    // The backend still accepts it, but this client no longer sends it.
    return this.post<SearchResponse>("/ensemble-search", {
      query,
      limit,
      top_m: topM,
      use_rerank: useRerank,
      ...(textFilter ?? {}),
    });
  }

  /**
   * Chạy một model duy nhất (beit3 hoặc clip) — phục vụ so sánh model đơn
   * với ensemble (thí nghiệm Q4 trong docs/KIEN_TRUC_PIPELINE.md).
   */
  async singleSearch(
    query: string,
    model: ModelName,
    limit = 100,
    topM = 50,
    useRerank = true
  ): Promise<SearchResponse> {
    return this.post<SearchResponse>("/single-search", {
      query,
      model,
      limit,
      top_m: topM,
      use_rerank: useRerank,
    });
  }

  /**
   * Search by TEXT ON SCREEN - pure lexical route, no model involved, not
   * blended with the visual route.
   *
   * @param stripDiacritics strip diacritics from both sides before comparing.
   *   On, it also catches OCR diacritic errors (`HỂ THAO` ~ `THỂ THAO`); off,
   *   it matches more precisely.
   * @param video narrow to one batch (`"L25"`) or one video (`"L25_V041"`).
   */
  async ocrSearch(
    query: string,
    limit = 100,
    stripDiacritics = true,
    video?: string
  ): Promise<OcrSearchResponse> {
    return this.post<OcrSearchResponse>("/ocr-search", {
      query,
      limit,
      strip_diacritics: stripDiacritics,
      ...(video ? { video } : {}),
    });
  }

  /** OCR text for one frame - shown even for frames from the visual route. */
  async ocrText(name: string): Promise<{ name: string; ocr_text: string }> {
    const response = await fetch(
      `${API_BASE_URL}/ocr-text/${encodeURIComponent(name)}`
    );
    return this.handleResponse<{ name: string; ocr_text: string }>(response);
  }

  /**
   * Alg.4 — cặp frame bắt đầu/kết thúc quanh 1 keyframe neo (anchor_name lấy
   * từ trường `name` của 1 SearchResult đã có trong tay, thường là kết quả
   * người dùng vừa chọn từ ensembleSearch/singleSearch).
   */
  async temporalSearch(
    queryStart: string,
    queryEnd: string,
    anchorName: string,
    options?: {
      gapC?: number;
      maxFrames?: number;
      simThr?: number;
      model?: ModelName;
    }
  ): Promise<TemporalSearchResult> {
    return this.post<TemporalSearchResult>("/temporal-search", {
      query_start: queryStart,
      query_end: queryEnd,
      anchor_name: anchorName,
      gap_c: options?.gapC ?? 20,
      max_frames: options?.maxFrames ?? 20,
      sim_thr: options?.simThr ?? 0.1,
      model: options?.model ?? "clip",
    });
  }

  /**
   * Bản KHÔNG CẦN anchor_name — tự động khám phá video ứng viên. Nhận 1
   * chuỗi thô (khung nhập giữ nguyên 1 field), tách thành 2 đoạn (start/end)
   * Ở BACKEND theo dấu "." — xem preprocess._split_query_text().
   */
  async temporalSearchText(
    query: string,
    options?: {
      topM?: number;
      topVideos?: number;
      gapC?: number;
      maxFrames?: number;
      simThr?: number;
      model?: ModelName;
    }
  ): Promise<{ results?: TemporalCandidateResult[]; error?: string }> {
    return this.post("/temporal-search-text", {
      query,
      top_m: options?.topM ?? 50,
      top_videos: options?.topVideos ?? 5,
      gap_c: options?.gapC ?? 20,
      max_frames: options?.maxFrames ?? 20,
      sim_thr: options?.simThr ?? 0.1,
      model: options?.model ?? "clip",
    });
  }

  /**
   * TRAKE — tự động khám phá video ứng viên cho N sự kiện tuần tự. Nhận 1
   * chuỗi thô, tách thành N đoạn (N>=2) Ở BACKEND theo dấu ".".
   */
  async trakeSearchText(
    query: string,
    options?: {
      topM?: number;
      topVideos?: number;
      gapC?: number;
      minScore?: number;
      model?: ModelName;
    }
  ): Promise<{ results?: TrakeCandidateResult[]; error?: string }> {
    return this.post("/trake-search-text", {
      query,
      top_m: options?.topM ?? 50,
      top_videos: options?.topVideos ?? 5,
      gap_c: options?.gapC ?? 60,
      min_score: options?.minScore ?? 0.1,
      model: options?.model ?? "clip",
    });
  }

  async getStatus(): Promise<SystemStatus> {
    const response = await fetch(`${API_BASE_URL}/status`);
    return this.handleResponse<SystemStatus>(response);
  }

  async getHealth(): Promise<HealthResponse> {
    const response = await fetch(`${API_BASE_URL}/health`);
    return this.handleResponse<HealthResponse>(response);
  }
}

class ResultSubmitApi {
  private async handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      const error: ApiError = await response.json();
      throw new Error(
        error.detail || `HTTP ${response.status}: ${response.statusText}`
      );
    }
    return response.json();
  }

  /** Chưa có /submit ở backend — xem comment ở ResultSubmit phía trên. */
  async submit(
    values: number[],
    result: SearchResult,
    answer: string,
    src: string
  ): Promise<SubmitRespond> {
    const response = await fetch(`${API_BASE_URL}/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values, result, answer, src }),
    });
    return this.handleResponse<SubmitRespond>(response);
  }
}

export const resultSubmitApi = new ResultSubmitApi();
export const videoSearchApi = new VideoSearchApi();