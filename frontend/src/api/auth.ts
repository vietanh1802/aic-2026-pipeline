import { apiFetch } from "./base";
import { useAuthStore } from "../store/authStore";
import type { LoginResponse, MeResponse } from "../types/auth";

export async function login(username: string, password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function changePassword(
  currentPassword: string,
  newPassword: string
): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>("/api/auth/change-password", {
    method: "POST",
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
}

export async function me(): Promise<MeResponse> {
  return apiFetch<MeResponse>("/api/me");
}

/** Clears locally even if the server call fails — a token you cannot reach is
 *  not a session worth pretending to have. */
export async function logout(): Promise<void> {
  try {
    await apiFetch("/api/auth/logout", { method: "POST" });
  } catch {
    // Already dead server-side, or unreachable. Either way, drop it locally.
  } finally {
    useAuthStore.getState().clear();
  }
}
