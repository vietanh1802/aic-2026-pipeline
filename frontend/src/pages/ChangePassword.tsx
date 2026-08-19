import { useState } from "react";

import { changePassword, logout, me } from "../api/auth";
import { ApiRequestError } from "../api/base";
import Button from "../components/Button";
import { useAuthStore } from "../store/authStore";

const MIN_LENGTH = 8;

export default function ChangePassword() {
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const tooShort = next.length > 0 && next.length < MIN_LENGTH;
  const mismatch = confirm.length > 0 && next !== confirm;
  const ready =
    !busy && current && next.length >= MIN_LENGTH && next === confirm;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await changePassword(current, next);
      // The server flipped must_change_password; re-read rather than guess, so
      // the store never disagrees with the backend about what is allowed.
      setUser((await me()).user);
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? err.message
          : "Không kết nối được tới máy chủ"
      );
    } finally {
      setBusy(false);
    }
  };

  const field =
    "p-3 rounded-[8px] bg-proto-soft border border-proto-line";
  const label =
    "text-[10px] font-bold uppercase tracking-wide text-proto-muted mt-2";

  return (
    <main className="min-h-screen flex items-center justify-center bg-proto-canvas font-baloo p-6">
      <form
        onSubmit={submit}
        className="flex flex-col gap-1.5 w-full max-w-[420px]"
      >
        <div className="flex flex-col gap-1 mb-3">
          <span className="text-xs font-bold tracking-[.9px] text-proto-muted">
            SCAVENGER
          </span>
          <b className="text-2xl text-proto-ink">Đặt mật khẩu mới</b>
        </div>

        <p className="text-sm text-proto-muted leading-relaxed mb-2">
          Chào {user?.display_name}. Đổi mật khẩu để mở bảng task và khu làm việc.
        </p>

        <label className={label}>Mật khẩu hiện tại</label>
        <input
          className={field}
          type="password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          autoFocus
          autoComplete="current-password"
        />

        <label className={label}>Mật khẩu mới</label>
        <input
          className={field}
          type="password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          autoComplete="new-password"
        />
        {tooShort && (
          <span className="text-xs text-proto-muted">
            Tối thiểu {MIN_LENGTH} ký tự.
          </span>
        )}

        <label className={label}>Nhập lại mật khẩu mới</label>
        <input
          className={field}
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          autoComplete="new-password"
        />
        {mismatch && (
          <span className="text-xs text-[#c64545]">Hai ô chưa khớp nhau.</span>
        )}

        {error && <p className="text-[#c64545] text-sm mt-1">{error}</p>}

        <Button type="submit" fullWidth className="mt-4" disabled={!ready}>
          {busy ? "Đang lưu…" : "Đổi mật khẩu"}
        </Button>

        <button
          type="button"
          onClick={() => void logout()}
          className="text-xs text-proto-muted underline mt-3 w-fit mx-auto"
        >
          Đăng xuất
        </button>
      </form>
    </main>
  );
}
