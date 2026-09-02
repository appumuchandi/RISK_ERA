import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import type { ApiService } from "../api";

export const Header = ({ api, onToggleSidebar }: { token: string | null; onLogout: () => void; api: ApiService | null; onToggleSidebar?: () => void }) => {
  const { token, username, role, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [aiOk, setAiOk] = useState<boolean | null>(null);

  const isOverview = location.pathname === "/";
  const isOperations = ["/operations", "/transactions", "/cases", "/customers", "/merchants", "/devices", "/network", "/rules", "/alerts", "/investigations", "/analytics"].some((p) => location.pathname.startsWith(p));
  const isGovernance = ["/audit", "/health"].some((p) => location.pathname.startsWith(p));

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      if (!api) return;
      try {
        await api.health();
        if (!cancelled) setBackendOk(true);
      } catch {
        if (!cancelled) setBackendOk(false);
      }
      try {
        const s = await api.toolsStatus();
        if (!cancelled) setAiOk(!!s?.available);
      } catch {
        if (!cancelled) setAiOk(false);
      }
    };
    check();
    const id = setInterval(check, 30000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [api]);

  const doLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <header className="app-header" role="banner">
      <div className="header-left">
        {token && onToggleSidebar && (
          <button className="sidebar-toggle" onClick={onToggleSidebar} aria-label="Toggle navigation" aria-expanded="false">
            ☰
          </button>
        )}
        <NavLink to="/" className="logo" aria-label="RISK-ERA Home">
          <span className="logo-mark" aria-hidden>◈</span>
          <span className="logo-text">RISK-ERA</span>
          <span className="logo-sub">AI Risk Operations</span>
        </NavLink>
        <span className="demo-badge" title="Synthetic demo data — not real payments">Demo Environment · Synthetic Payment Data</span>
      </div>

      <nav className="header-nav" aria-label="Primary">
        <NavLink to="/" end className={({ isActive }) => (isActive || isOverview ? "nav-link active" : "nav-link")}>Overview</NavLink>
        <NavLink to="/operations" className={() => (isOperations ? "nav-link active" : "nav-link")}>Operations</NavLink>
        <NavLink to="/audit" className={() => (isGovernance ? "nav-link active" : "nav-link")}>Governance</NavLink>
      </nav>

      <div className="header-right">
        <div className="health-indicators" title="Service health">
          <span className="health-item"><span className={`health-dot ${backendOk === null ? "unknown" : backendOk ? "ok" : "bad"}`} />Backend</span>
          <span className="health-item"><span className={`health-dot ${aiOk === null ? "unknown" : aiOk ? "ok" : "bad"}`} />Nemotron</span>
        </div>
        {token ? (
          <div className="user-area">
            <span className="user-meta" title={`${username || "Admin1"} — ${role || "admin"}`}>
              <span className="user-name">{username || "Admin1"}</span>
              <span className="online-dot" aria-hidden />
            </span>
            <button className="btn btn-primary btn-sm logout-btn" onClick={doLogout} aria-label="Logout">Logout</button>
          </div>
        ) : (
          <button className="btn btn-primary btn-sm" onClick={() => navigate("/login")}>Login</button>
        )}
      </div>
    </header>
  );
};
