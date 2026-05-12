import { FormEvent, useState } from "react";
import { ApiError } from "../api/client";
import { useAppState } from "../state/appState";

type Mode = "login" | "register";

export function AuthPage() {
  const {
    connectionState,
    lastError,
    login,
    register,
    workspace,
  } = useAppState();
  const [mode, setMode] = useState<Mode>("login");
  const [identifier, setIdentifier] = useState("whiteone");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      if (mode === "login") {
        await login(identifier.trim(), password);
      } else {
        await register(username.trim(), email.trim() || null, password);
      }
    } catch (authError) {
      setError(authError instanceof ApiError || authError instanceof Error ? authError.message : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-shell">
      <section className="auth-panel">
        <div className="auth-brand">
          <div className="brand-icon">
            <span className="icon icon-lg">radar</span>
          </div>
          <div>
            <h1>OneRadar</h1>
            <p>{workspace?.workspace_name ?? "Private Reader"}</p>
          </div>
        </div>

        <div className="auth-tabs" role="tablist" aria-label="账号入口">
          <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
            登录
          </button>
          <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>
            注册
          </button>
        </div>

        <form className="stack" onSubmit={(event) => void handleAuth(event)}>
          {mode === "login" ? (
            <label className="field">
              <span>用户名或邮箱</span>
              <input
                className="input"
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
                autoComplete="username"
              />
            </label>
          ) : (
            <>
              <label className="field">
                <span>用户名</span>
                <input className="input" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
              </label>
              <label className="field">
                <span>邮箱</span>
                <input className="input" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" />
              </label>
            </>
          )}

          <label className="field">
            <span>密码</span>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </label>

          <button className="btn btn-primary auth-submit" type="submit" disabled={busy || !password || (mode === "login" ? !identifier.trim() : !username.trim())}>
            <span className="icon icon-sm">{busy ? "sync" : mode === "login" ? "login" : "person_add"}</span>
            {busy ? "处理中…" : mode === "login" ? "进入工作区" : "创建账号"}
          </button>
        </form>

        <div className="auth-status">
          <span className={`chip ${connectionState === "connected" ? "chip-success" : connectionState === "checking" ? "chip-primary" : "chip-neutral"}`}>
            <span className="icon icon-sm">{connectionState === "connected" ? "check_circle" : "radio_button_unchecked"}</span>
            {connectionState === "connected" ? "服务端已连接" : connectionState === "checking" ? "检测中" : "等待连接"}
          </span>
        </div>
        {message && <div className="feedback feedback-success">{message}</div>}
        {(error || lastError) && <div className="feedback feedback-error">{error ?? lastError}</div>}
      </section>
    </div>
  );
}
