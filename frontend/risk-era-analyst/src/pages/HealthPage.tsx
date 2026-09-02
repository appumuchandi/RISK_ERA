import { useEffect, useState } from "react";
import type { ApiService } from "../api";

type HealthStatus = "healthy" | "warning" | "unavailable" | "checking";

type Check = {
  name: string;
  description: string;
  status: HealthStatus;
  latency?: number;
  details?: string;
  timestamp?: string;
};

export default function HealthPage({ api }: { api: ApiService }) {
  const [checks, setChecks] = useState<Check[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const start = Date.now();
      const results: Check[] = [];

      // Backend health (public)
      try {
        const h = await api.health();
        results.push({
          name: "Backend API",
          description: "FastAPI service availability",
          status: h.status === "healthy" ? "healthy" : "warning",
          latency: Date.now() - start,
          details: `${h.service || "RISK-ERA"} · ${h.environment || "unknown"}`,
          timestamp: new Date().toISOString(),
        });
      } catch (e: any) {
        results.push({ name: "Backend API", description: "FastAPI service availability", status: "unavailable", details: e.message || "Unable to reach backend", timestamp: new Date().toISOString() });
      }

      // Database via /ready
      try {
        const r = await api.ready();
        const dbHealthy = r.database === "healthy";
        results.push({
          name: "PostgreSQL Database",
          description: "Primary datastore and audit chain persistence",
          status: dbHealthy ? "healthy" : "unavailable",
          details: `Database: ${r.database} · Nemotron: ${r.nemotron}`,
          timestamp: new Date().toISOString(),
        });
      } catch (e: any) {
        results.push({ name: "PostgreSQL Database", description: "Primary datastore", status: "unavailable", details: e.message, timestamp: new Date().toISOString() });
      }

      // Authentication
      try {
        await api.client.get("/api/v1/auth/me");
        results.push({ name: "Authentication", description: "JWT Bearer validation", status: "healthy", details: "Token valid · analyst session", timestamp: new Date().toISOString() });
      } catch (e: any) {
        const s = e?.response?.status;
        if (s === 401) results.push({ name: "Authentication", description: "JWT Bearer validation", status: "warning", details: "Session requires login", timestamp: new Date().toISOString() });
        else results.push({ name: "Authentication", description: "JWT Bearer validation", status: "unavailable", details: e.message, timestamp: new Date().toISOString() });
      }

      // Investigation tools
      try {
        const t = await api.toolsStatus();
        results.push({
          name: "Investigation Tools",
          description: "Controlled tool orchestration (transaction history, customer profile, device activity)",
          status: t.available ? "healthy" : "warning",
          details: `${t.tools?.length || 3} tools · ${t.available ? "available" : "unavailable"}`,
          timestamp: new Date().toISOString(),
        });
      } catch (e: any) {
        results.push({ name: "Investigation Tools", description: "Controlled tool orchestration", status: "unavailable", details: e.message, timestamp: new Date().toISOString() });
      }

      // Audit chain
      try {
        const v = await api.verifyAuditChain();
        results.push({
          name: "Audit Chain",
          description: "SHA-256 hash chain integrity",
          status: v.valid ? "healthy" : "unavailable",
          details: v.valid ? `Valid · ${v.checked_count ?? "—"} events checked` : `Invalid: ${v.error}`,
          timestamp: new Date().toISOString(),
        });
      } catch (e: any) {
        results.push({ name: "Audit Chain", description: "SHA-256 hash chain", status: "unavailable", details: e.message, timestamp: new Date().toISOString() });
      }

      // API aggregate
      const allHealthy = results.every((r) => r.status === "healthy");
      const anyUnavailable = results.some((r) => r.status === "unavailable");
      results.unshift({
        name: "Overall System",
        description: "Aggregated health from all subsystems",
        status: allHealthy ? "healthy" : anyUnavailable ? "unavailable" : "warning",
        details: allHealthy ? "All subsystems healthy" : anyUnavailable ? "One or more subsystems unavailable" : "Degraded",
        timestamp: new Date().toISOString(),
      });

      setChecks(results);
      setLastUpdated(new Date().toISOString());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unable to load health status");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [api]);

  if (loading) {
    return (
      <section className="intel-page">
        <div className="page-head"><h2>System Health</h2></div>
        <div className="kpi-grid">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="kpi-card"><div className="skeleton" style={{ height: 18, width: "60%" }} /></div>
          ))}
        </div>
        <div className="panel"><div className="skeleton" style={{ height: 120 }} /></div>
      </section>
    );
  }

  if (error) {
    return (
      <div className="error-state">
        <h3>Unable to load system health</h3>
        <p>{error}</p>
        <p className="muted">Check that the Risk-Era backend is running and try again.</p>
        <button className="btn btn-primary" onClick={load}>Retry</button>
      </div>
    );
  }

  const overall = checks[0];

  return (
    <section className="intel-page">
      <div className="page-head">
        <div>
          <h2>System Health <span className={`badge ${overall.status === "healthy" ? "badge-ok" : overall.status === "warning" ? "badge-warn" : "badge-bad"}`}>{overall.status.toUpperCase()}</span></h2>
          <p className="muted">Operational observability — API, database, authentication, investigation tools and audit chain. No secrets are exposed. Last checked {lastUpdated ? new Date(lastUpdated).toLocaleString() : "—"}</p>
        </div>
        <button className="btn btn-primary" onClick={load}>Refresh</button>
      </div>

      <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
        {checks.slice(0, 6).map((c) => (
          <div key={c.name} className={`kpi-card ${c.status === "healthy" ? "tone-low" : c.status === "warning" ? "tone-medium" : "tone-critical"}`} style={{ cursor: "default" }}>
            <div className="kpi-value" style={{ fontSize: "1.1rem", display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 10, height: 10, borderRadius: "50%", background: c.status === "healthy" ? "var(--accent-green)" : c.status === "warning" ? "var(--accent-amber)" : "var(--accent-red)", display: "inline-block" }} />
              {c.name}
            </div>
            <div className="kpi-label" style={{ textTransform: "none", fontSize: ".74rem" }}>{c.status.toUpperCase()} {c.latency ? `· ${c.latency}ms` : ""}</div>
            <div className="kpi-hint" style={{ whiteSpace: "normal", overflow: "visible", textOverflow: "clip", lineHeight: 1.3 }}>{c.details}</div>
          </div>
        ))}
      </div>

      <div className="panel">
        <h3>Health Checks — Real Backend-Derived</h3>
        <p className="muted">Each check is performed against live backend endpoints. No fabricated health states.</p>
        <div className="table-wrap">
          <table className="cases-table">
            <thead><tr><th>Subsystem</th><th>Status</th><th>Details</th><th>Latency</th><th>Checked</th></tr></thead>
            <tbody>
              {checks.map((c) => (
                <tr key={c.name}>
                  <td style={{ fontWeight: 600 }}>{c.name}<br /><span className="muted" style={{ fontSize: ".68rem" }}>{c.description}</span></td>
                  <td><span className={`badge ${c.status === "healthy" ? "badge-ok" : c.status === "warning" ? "badge-warn" : "badge-bad"}`}>{c.status.toUpperCase()}</span></td>
                  <td style={{ maxWidth: 320, whiteSpace: "normal", wordBreak: "break-word", fontSize: ".8rem" }}>{c.details}</td>
                  <td>{c.latency ? `${c.latency}ms` : "—"}</td>
                  <td style={{ fontSize: ".72rem", whiteSpace: "nowrap" }}>{c.timestamp ? new Date(c.timestamp).toLocaleTimeString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <h3>Operational Guidance</h3>
        <ul className="signal-list">
          <li className="sig-hit">• Healthy: All subsystems responding, audit chain valid, tools available</li>
          <li className="sig-hit">• Warning: Degraded — check authentication or non-critical tool availability</li>
          <li className="sig-hit">• Unavailable: Backend, database or audit chain failure — investigate immediately</li>
          <li className="sig-hit">• No secrets, API keys or JWTs are displayed on this page</li>
        </ul>
        <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="btn btn-ghost btn-sm" onClick={load}>Refresh Health</button>
          <a href="/api/v1/audit/verify-chain" target="_blank" rel="noreferrer" className="btn btn-ghost btn-sm">View Raw Verify Response</a>
        </div>
      </div>
    </section>
  );
}
