import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setIsLoading(true);
    try {
      await login(username, password);
      navigate("/", { replace: true });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Login failed";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    setIsLoading(true);
    try {
      const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
      const resp = await fetch(`${API_BASE}/api/v1/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, email, password, confirm_password: confirmPassword, name: name || undefined }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.detail || "Registration failed");
      }
      setSuccess("Account created successfully. Please sign in.");
      setMode("signin");
      setPassword("");
      setConfirmPassword("");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Registration failed";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <span style={{ width: 36, height: 36, borderRadius: 10, background: "var(--accent-primary)", color: "#fff", display: "grid", placeItems: "center", fontSize: "1.1rem" }} aria-hidden>◈</span>
          <div>
            <h2 style={{ margin: 0 }}>RISK-ERA</h2>
            <div className="muted" style={{ fontSize: ".72rem", letterSpacing: ".06em", textTransform: "uppercase", fontWeight: 600 }}>Analyst Workspace</div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, margin: "14px 0 12px 0", background: "var(--bg-elevated)", padding: 4, borderRadius: 12, border: "1px solid var(--border)" }}>
          <button
            type="button"
            onClick={() => { setMode("signin"); setError(null); setSuccess(null); }}
            className={mode === "signin" ? "btn btn-primary" : "btn btn-ghost"}
            style={{ flex: 1, height: 36, borderRadius: 8 }}
            aria-pressed={mode === "signin"}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => { setMode("signup"); setError(null); setSuccess(null); }}
            className={mode === "signup" ? "btn btn-primary" : "btn btn-ghost"}
            style={{ flex: 1, height: 36, borderRadius: 8 }}
            aria-pressed={mode === "signup"}
          >
            Sign Up
          </button>
        </div>
        <p className="muted" style={{ marginBottom: 4, fontSize: ".82rem" }}>{mode === "signin" ? "Sign in to access the risk operations workspace." : "Create your analyst account."}</p>
        <p className="muted" style={{ fontSize: ".72rem", marginBottom: 12, lineHeight: 1.4 }}>Demo Environment · Synthetic Payment Data — not real customer/payment data</p>
        {error && <div className="error-banner" role="alert">{error}</div>}
        {success && <div className="ok-banner" role="status">{success}</div>}
        {mode === "signin" ? (
          <form onSubmit={handleLogin} className="login-form">
            <label>Username or Email<input value={username} onChange={(e) => setUsername(e.target.value)} required autoComplete="username" /></label>
            <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" /></label>
            <button type="submit" disabled={isLoading} className="btn btn-primary block">{isLoading ? "Signing in…" : "Sign In"}</button>
          </form>
        ) : (
          <form onSubmit={handleSignup} className="login-form">
            <label>Username<input value={username} onChange={(e) => setUsername(e.target.value)} required autoComplete="username" placeholder="e.g., jdoe" /></label>
            <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" placeholder="you@example.com" /></label>
            <label>Display Name (optional)<input value={name} onChange={(e) => setName(e.target.value)} placeholder="Jane Doe" /></label>
            <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="new-password" placeholder="At least 8 characters" /></label>
            <label>Confirm Password<input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required autoComplete="new-password" /></label>
            <button type="submit" disabled={isLoading} className="btn btn-primary block">{isLoading ? "Creating account…" : "Create Account"}</button>
          </form>
        )}
      </div>
    </div>
  );
}
