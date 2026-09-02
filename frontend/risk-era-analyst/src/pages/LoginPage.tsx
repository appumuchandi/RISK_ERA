import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("Admin1");
  const [password, setPassword] = useState("Admin@1234");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
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

  return (
    <div className="login-page">
      <div className="login-card">
        <h2>RISK-ERA Analyst Login</h2>
        <p className="muted">Demo Environment · Synthetic Payment Data — not real customer/payment data</p>
        <div className="demo-creds">
          <strong>Demo credentials:</strong> Admin1 / Admin@1234 &nbsp;|&nbsp; analyst / analyst123 &nbsp;|&nbsp; admin / admin123
        </div>
        {error && <div className="error-banner">{error}</div>}
        <form onSubmit={handleLogin} className="login-form">
          <label>Username<input value={username} onChange={(e) => setUsername(e.target.value)} required /></label>
          <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          <button type="submit" disabled={isLoading} className="btn btn-primary block">{isLoading ? "Signing in…" : "Sign In"}</button>
        </form>
      </div>
    </div>
  );
}
