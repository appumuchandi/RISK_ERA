import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { ApiService } from "../api";

export default function OperationsPage({ api }: { api: ApiService }) {
  const [summary, setSummary] = useState<any>(null);
  const [cases, setCases] = useState<any[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [investigations, setInvestigations] = useState<any[]>([]);
  const [audit, setAudit] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const [sum, casesRes, alertsRes, invRes, auditRes] = await Promise.all([
        api.getOperationsSummary().catch(() => null),
        api.getCases(1, 5, { status: "open" }).catch(() => ({ items: [] })),
        api.listAlerts({ page: 1, page_size: 5, status: "open" } as any).catch(() => ({ items: [] })),
        (api as any).client.get("/api/v1/investigation?page=1&page_size=5").then((r: any) => r.data).catch(() => ({ items: [] })),
        api.getAuditEvents({ page: 1, page_size: 5 }).catch(() => ({ items: [] })),
      ]);
      setSummary(sum);
      setCases((casesRes as any)?.items || []);
      setAlerts((alertsRes as any)?.items || []);
      setInvestigations((invRes as any)?.items || []);
      setAudit((auditRes as any)?.items || []);
    } catch (e: any) {
      setError(e.message || "Unable to load operations");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (loading) {
    return (
      <section className="intel-page">
        <div className="page-head"><h2>Risk Operations</h2></div>
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
        <h3>Unable to load operations</h3>
        <p>{error}</p>
        <button className="btn btn-primary" onClick={load}>Retry</button>
      </div>
    );
  }

  return (
    <section className="intel-page">
      <div className="page-head">
        <div>
          <h2>Risk Operations <span className="badge badge-neutral">Live</span></h2>
          <p className="muted">Priority attention, active alerts, recent investigations and audit activity — all from real PostgreSQL data.</p>
        </div>
        <button className="btn btn-ghost" onClick={load}>Refresh</button>
      </div>

      {summary && (
        <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
          <div className="kpi-card tone-critical" style={{ cursor: "default" }}><div className="kpi-value">{summary.open_alerts ?? 0}</div><div className="kpi-label">Open Alerts</div><div className="kpi-hint">{summary.critical_alerts ?? 0} critical</div></div>
          <div className="kpi-card tone-medium" style={{ cursor: "default" }}><div className="kpi-value">{summary.open_cases ?? 0}</div><div className="kpi-label">Open Cases</div><div className="kpi-hint">{summary.escalated_cases ?? 0} escalated</div></div>
          <div className="kpi-card tone-low" style={{ cursor: "default" }}><div className="kpi-value">{summary.in_progress_alerts ?? 0}</div><div className="kpi-label">In Progress Alerts</div></div>
          <div className="kpi-card tone-medium" style={{ cursor: "default" }}><div className="kpi-value">{summary.alerts_last_24h ?? 0}</div><div className="kpi-label">Last 24h Alerts</div></div>
        </div>
      )}

      <div className="panel">
        <h3>Priority / Attention → Case or Alert → Investigation → Decision → Audit</h3>
        <p className="muted">Follow the operational workflow. Each card links to its workspace.</p>
        <div className="flow" style={{ marginTop: 8 }}>
          <Link to="/alerts" className="flow-step">Alerts</Link><span className="flow-arrow">→</span>
          <Link to="/cases" className="flow-step">Cases</Link><span className="flow-arrow">→</span>
          <Link to="/investigations" className="flow-step">Investigations</Link><span className="flow-arrow">→</span>
          <Link to="/audit" className="flow-step">Audit</Link>
        </div>
      </div>

      <div className="case-grid">
        <div className="panel">
          <h3>Open Cases {cases.length > 0 && <span className="badge badge-neutral">{cases.length}</span>}</h3>
          {cases.length === 0 ? <div className="empty-state">No open cases — all clear. <Link to="/cases" className="link">View all cases</Link></div> : (
            <ul className="activity-list">
              {cases.map((c: any) => (
                <li key={c.id} className="activity-item">
                  <Link to={`/case/${c.id}`} className="link mono">{c.id.slice(0, 8)}…</Link>
                  <span className={`badge status-${c.status}`}>{c.status}</span>
                  <span className="muted" style={{ fontSize: ".68rem" }}>{new Date(c.created_at).toLocaleDateString()}</span>
                </li>
              ))}
            </ul>
          )}
          <Link to="/cases" className="btn btn-ghost btn-sm" style={{ marginTop: 8 }}>View Cases →</Link>
        </div>
        <div className="panel">
          <h3>Active Alerts {alerts.length > 0 && <span className="badge badge-neutral">{alerts.length}</span>}</h3>
          {alerts.length === 0 ? <div className="empty-state">No open alerts — no high-risk transactions pending.</div> : (
            <ul className="activity-list">
              {alerts.map((a: any) => (
                <li key={a.id} className="activity-item">
                  <span className="mono" style={{ fontSize: ".78rem" }}>{a.title?.slice(0, 24) || a.alert_type}</span>
                  <span className={`badge risk-${(a.severity || "medium").toLowerCase()}`}>{a.severity}</span>
                  <span className="muted" style={{ fontSize: ".68rem" }}>P{a.priority}</span>
                </li>
              ))}
            </ul>
          )}
          <Link to="/alerts" className="btn btn-ghost btn-sm" style={{ marginTop: 8 }}>View Alerts →</Link>
        </div>
      </div>

      <div className="case-grid">
        <div className="panel">
          <h3>Recent Investigations</h3>
          {investigations.length === 0 ? <div className="empty-state">No investigations yet — run an investigation from a case.</div> : (
            <ul className="activity-list">
              {investigations.map((inv: any) => (
                <li key={inv.id || inv.investigation_id} className="activity-item">
                  <Link to={`/case/${inv.case_id}`} className="link mono">{String(inv.case_id).slice(0, 8)}…</Link>
                  <span className={`badge ${inv.status === "completed" ? "badge-ok" : "badge-neutral"}`}>{inv.status}</span>
                  <span className="muted" style={{ fontSize: ".68rem" }}>{inv.recommendation || inv.status}</span>
                </li>
              ))}
            </ul>
          )}
          <Link to="/investigations" className="btn btn-ghost btn-sm" style={{ marginTop: 8 }}>View Investigations →</Link>
        </div>
        <div className="panel">
          <h3>Recent Audit Activity</h3>
          {audit.length === 0 ? <div className="empty-state">No recent audit events.</div> : (
            <ul className="activity-list">
              {audit.map((ev: any) => (
                <li key={ev.id} className="activity-item">
                  <span className="mono" style={{ fontSize: ".72rem" }}>{ev.action}</span>
                  <span className="muted" style={{ fontSize: ".68rem" }}>{ev.actor} · {new Date(ev.created_at).toLocaleTimeString()}</span>
                </li>
              ))}
            </ul>
          )}
          <Link to="/audit" className="btn btn-ghost btn-sm" style={{ marginTop: 8 }}>View Audit →</Link>
        </div>
      </div>
    </section>
  );
}
