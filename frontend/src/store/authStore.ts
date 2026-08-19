import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { AuthUser } from "../types/auth";

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  signIn: (token: string, user: AuthUser) => void;
  setUser: (user: AuthUser) => void;
  clear: () => void;
}

/**
 * Persisted to localStorage so a reload does not log you out mid-round.
 *
 * The token is the only credential the browser holds, and it is the whole
 * session — anything that can read localStorage can act as you. That is the
 * accepted trade for a five-person tool on a private VPS; it is written down
 * here so the next person changing it knows it was a choice.
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      signIn: (token, user) => set({ token, user }),
      setUser: (user) => set({ user }),
      clear: () => set({ token: null, user: null }),
    }),
    { name: "scavenger-auth" }
  )
);
