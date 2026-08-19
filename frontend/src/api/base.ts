import type { ApiError } from "../types/api";
import { useAuthStore } from "../store/authStore";

// harness_check.py finds frontend calls by matching the literal
// `${API_BASE_URL}` inside a template string. Keep that shape in every request
// or the api-contract check silently stops seeing them.
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiRequestError extends Error {
  readonly status: number;
  /**
   * The whole parsed error body, not just its `detail`.
   *
   * Several 409s in this API carry the information the UI needs to recover:
   * a claim conflict returns the current `owner` (§7.5), a stale answer PATCH
   * returns the `current` row (§7.7), an uncached video returns `state` and
   * `progress` (§7.8). An earlier version of this class kept only `detail` and
   * dropped the rest, which would have made every one of those unimplementable
   * without anyone noticing until the screen was built.
   */
  readonly body: unknown;

  constructor(status: number, message: string, body: unknown = undefined) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.body = body;
  }
}

/** Parses the body once, turning any non-2xx into ApiRequestError. */
export async function readResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return (await response.json()) as T;
  }

  let detail = `HTTP ${response.status}: ${response.statusText}`;
  let body: unknown;
  try {
    body = await response.json();
    const parsed = body as ApiError;
    if (parsed?.detail) {
      detail = parsed.detail;
    }
  } catch {
    // A proxy or a crash can return HTML. Keep the status line we already have.
  }
  throw new ApiRequestError(response.status, detail, body);
}

/**
 * Every authenticated request. Adds the bearer token, sets the JSON content
 * type when there is a body, and treats a 401 as the end of the session rather
 * than as one call's error — so no screen has to check for it individually.
 *
 * The URL is built with no slash after `${API_BASE_URL}`, which is exactly why
 * harness_check.py's CALL_RE requires one: this line must not be read as a call
 * to the empty path. The checker finds these calls through the literal path
 * each caller passes in.
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { token } = useAuthStore.getState();
  const headers = new Headers(init.headers);

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  // Never set it for FormData: the browser has to supply the multipart
  // boundary itself, and an explicit Content-Type strips it.
  const isForm = typeof FormData !== "undefined" && init.body instanceof FormData;
  if (init.body && !isForm && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  if (response.status === 401) {
    useAuthStore.getState().clear();
  }
  return readResponse<T>(response);
}
