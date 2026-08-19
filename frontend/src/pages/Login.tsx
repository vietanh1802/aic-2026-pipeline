import { useState } from "react";

import { login } from "../api/auth";
import { ApiRequestError } from "../api/base";
import Button from "../components/Button";
import { useAuthStore } from "../store/authStore";

export default function Login() {
  const signIn = useAuthStore((state) => state.signIn);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await login(username, password);
      signIn(response.token, response.user);
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

  return (
    <main className="min-h-screen grid md:grid-cols-2 bg-proto-canvas font-baloo">
      <section className="hidden md:flex flex-col justify-center gap-4 p-12 bg-proto-card">
        <div className="text-xs font-bold tracking-[.9px] text-proto-muted">
          SCAVENGER
        </div>
        <h1 className="text-3xl text-proto-ink">
          Video moment retrieval, cả nhóm cùng làm.
        </h1>
        <p className="text-sm text-proto-muted max-w-[46ch] leading-relaxed">
          Đăng nhập để mở bảng task, nhận truy vấn, soát khung hình và chốt danh
          sách đáp án trước khi nộp.
        </p>
      </section>

      <form
        onSubmit={submit}
        className="flex flex-col justify-center gap-3 p-12 max-w-[420px] w-full mx-auto"
      >
        <div className="flex flex-col gap-1 mb-3">
          <span className="text-xs text-proto-muted">AI Challenge HCMC 2026</span>
          <b className="text-2xl text-proto-ink">Đăng nhập</b>
        </div>

        <label className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
          Tên đăng nhập
        </label>
        <input
          className="p-3 rounded-[8px] bg-proto-soft border border-proto-line"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
          autoComplete="username"
        />

        <label className="text-[10px] font-bold uppercase tracking-wide text-proto-muted mt-2">
          Mật khẩu
        </label>
        <input
          className="p-3 rounded-[8px] bg-proto-soft border border-proto-line"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />

        {error && <p className="text-[#c64545] text-sm mt-1">{error}</p>}

        <Button
          type="submit"
          fullWidth
          className="mt-4"
          disabled={busy || !username || !password}
        >
          {busy ? "Đang vào…" : "Đăng nhập"}
        </Button>

        <p className="text-xs text-proto-muted mt-2 leading-relaxed">
          Tài khoản do quản trị cấp sẵn. Lần đầu đăng nhập sẽ được yêu cầu đổi
          mật khẩu.
        </p>
      </form>
    </main>
  );
}
