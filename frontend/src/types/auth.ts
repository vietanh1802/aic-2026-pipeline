// Types for the collaboration layer.
//
// Deliberately a separate file from types/api.ts: that one mirrors the search
// endpoints and must stay byte-identical to staging, so nothing about
// collaboration is allowed to land in it.

export interface AuthUser {
  id: number;
  username: string;
  display_name: string;
  role: "admin" | "member";
  /** While true, the backend answers 403 to everything except /api/me. */
  must_change_password: boolean;
  disabled?: boolean;
}

export interface LoginResponse {
  token: string;
  user: AuthUser;
}

/** Setting keys contain dots, so this stays a record rather than an interface. */
export type PublicSettings = Record<string, string | number | boolean>;

export interface MeResponse {
  user: AuthUser;
  settings: PublicSettings;
  server_time: string;
}
