// types/api.ts
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

export interface SearchResponse {
  total_results: number;
  returned_results: number;
  results: SearchResult[];
  query_type: string;
  processing_time: number;
  max_distance: number;
  // true nếu backend đang chạy demo mode (chưa có beit3.index/clip.index thật)
  demo_mode?: boolean;
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
  demo?: boolean;
  error?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Status / health — khớp system_status() trong preprocess.py
// ─────────────────────────────────────────────────────────────────────────────

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

const API_BASE_URL =
  (import.meta as { env?: { VITE_API_BASE_URL?: string } }).env
    ?.VITE_API_BASE_URL || "http://localhost:8000";

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
    useRerank = true
  ): Promise<SearchResponse> {
    return this.post<SearchResponse>("/ensemble-search", {
      query,
      limit,
      top_m: topM,
      use_rerank: useRerank,
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
