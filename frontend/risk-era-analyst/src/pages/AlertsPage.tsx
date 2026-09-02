import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { ApiService, AlertItem, OperationsSummary } from "../api";
import DecisionExplanation from "../components/DecisionExplanation";
import { RiskBadge } from "../components/intel/IntelShared";

const SEVERITY_COLOR: Record<string, string> = {
  low: "var(--accent-green)",
  medium: "var(--accent-amber)",
  high: "var(--accent-red)",
  critical: "#b42318",
};

export default function AlertsPage({ api }: { api: ApiService }) {
  const [summary, setSummary] = useState<OperationsSummary | null>(null);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const [priority, setPriority] = useState("");
  const [decision, setDecision] = useState("");
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortOrder, setSortOrder] = useState("desc");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<AlertItem | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [assignee, setAssignee] = useState("");

  const loadSummary = async () => {
    try {
      const s = await api.getOperationsSummary();
      setSummary(s);
    } catch {}
  };

  const loadAlerts = async (p = page) => {
    try {
      setLoading(true);
      setError(null);
      const params: Record<string, unknown> = { page: p, page_size: 20, sort_by: sortBy, sort_order: sortOrder };
      if (status) params.status = status;
      if (severity) params.severity = severity;
      if (priority) params.priority = Number(priority);
      if (decision) params.decision = decision;
      if (search) params.search = search;
      const res = await api.listAlerts(params);
      setAlerts(res.items);
      setTotal(res.total);
      setPage(res.page);
    } catch (e: any) {
      const statusCode = e?.response?.status;
      if (statusCode === 401) setError("Authentication required");
      else setError(e instanceof Error ? e.message : "Unable to load alerts");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSummary();
    loadAlerts(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openDetail = async (alert: AlertItem) => {
    setSelected(alert);
    setDetail(null);
    setDetailLoading(true);
    setActionMsg(null);
    try {
      const d = await api.getAlert(alert.id);
      setDetail(d);
    } catch (e) {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const doStatus = async (newStatus: string) => {
    if (!selected) return;
    try {
      setActionMsg(null);
      await api.updateAlertStatus(selected.id, newStatus);
      setActionMsg(`Status → ${newStatus}`);
      await loadAlerts(page);
      await openDetail({ ...selected, status: newStatus } as AlertItem);
      await loadSummary();
    } catch (e: any) {
      setActionMsg(e?.response?.data?.detail || e.message || "Status update failed");
    }
  };

  const doAssign = async () => {
    if (!selected || !assignee.trim()) return;
    try {
      await api.assignAlert(selected.id, assignee.trim());
      setActionMsg(`Assigned to ${assignee}`);
      setAssignee("");
      await loadAlerts(page);
      await openDetail({ ...selected, assigned_to: assignee } as AlertItem);
    } catch (e: any) {
      setActionMsg(e?.response?.data?.detail || "Assign failed");
    }
  };

  const doResolve = async () => {
    if (!selected) return;
    try {
      await api.resolveAlert(selected.id, "Resolved by analyst");
      setActionMsg("Alert resolved");
      await loadAlerts(page);
      await openDetail({ ...selected, status: "resolved" } as AlertItem);
      await loadSummary();
    } catch (e: any) {
      setActionMsg(e?.response?.data?.detail || "Resolve failed");
    }
  };

  const doDismiss = async () => {
    if (!selected) return;
    try {
      await api.dismissAlert(selected.id, "Dismissed by analyst");
      setActionMsg("Alert dismissed");
      await loadAlerts(page);
      await openDetail({ ...selected, status: "dismissed" } as AlertItem);
      await loadSummary();
    } catch (e: any) {
      setActionMsg(e?.response?.data?.detail || "Dismiss failed");
    }
  };

  const doCreateCase = async () => {
    if (!selected) return;
    try {
      const res = await api.createCaseFromAlert(selected.id);
      setActionMsg(`Case ${res.case_id.slice(0, 8)} linked`);
      await loadAlerts(page);
      const d = await api.getAlert(selected.id);
      setDetail(d);
      setSelected(d as AlertItem);
    } catch (e: any) {
      setActionMsg(e?.response?.data?.detail || "Create case failed");
    }
  };

  const doRunInvestigation = async () => {
    if (!detail?.case_id) {
      setActionMsg("Create a case first");
      return;
    }
    try {
      setActionMsg("Starting investigation…");
      await api.runInvestigation(detail.case_id);
      setActionMsg("Investigation started");
    } catch (e: any) {
      setActionMsg(e?.response?.data?.detail || "Investigation failed");
    }
  };

  if (loading && alerts.length === 0 && !error) {
    return (
      <section className="intel-page">
        <div className="page-head"><h2>Alerts & Operations</h2></div>
        <div className="kpi-grid">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="kpi-card"><div className="skeleton" style={{ height: 22, width: "40%" }} /><div className="skeleton" style={{ height: 12, width: "60%", marginTop: 8 }} /></div>
          ))}
        </div>
        <div className="panel"><div className="skeleton" style={{ height: 160 }} /></div>
      </section>
    );
  }

  if (error) {
    return (
      <div className="error-state">
        <h3>Unable to load alerts</h3><p>{error}</p><button className="btn btn-primary" onClick={() => loadAlerts(page)}>Retry</button>
      </div>
    );
  }

  return (
    <section className="intel-page">
      <div className="page-head">
        <div>
          <h2>Alerts & Operations <span className="badge badge-neutral">Phase 7</span></h2>
          <p className="muted">Operational queue for detected risk events — real alerts generated from RuleEngine decisions, not mock data. Prioritized by severity, risk score and decision.</p>
        </div>
      </div>

      {/* KPI */}
      {summary && (
        <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}>
          <div className="kpi-card tone-critical" style={{ cursor: "default" }}><div className="kpi-value">{summary.critical_alerts}</div><div className="kpi-label">Critical</div></div>
          <div className="kpi-card tone-critical" style={{ cursor: "default" }}><div className="kpi-value">{summary.high_alerts}</div><div className="kpi-label">High</div></div>
          <div className="kpi-card tone-medium" style={{ cursor: "default" }}><div className="kpi-value">{summary.open_alerts}</div><div className="kpi-label">Open</div></div>
          <div className="kpi-card tone-medium" style={{ cursor: "default" }}><div className="kpi-value">{summary.in_progress_alerts}</div><div className="kpi-label">In Progress</div><div className="kpi-hint">{summary.acknowledged_alerts} acknowledged</div></div>
          <div className="kpi-card tone-low" style={{ cursor: "default" }}><div className="kpi-value">{summary.alerts_last_24h}</div><div className="kpi-label">Last 24h</div></div>
          <div className="kpi-card tone-critical" style={{ cursor: "default" }}><div className="kpi-value">{summary.open_cases}</div><div className="kpi-label">Open Cases</div><div className="kpi-hint">{summary.escalated_cases} escalated</div></div>
        </div>
      )}

      <div className="panel">
        <h3>Alert Queue</h3>
        <div className="toolbar">
          <div className="toolbar-group">
            <input placeholder="Search alert, rule, transaction" value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && loadAlerts(1)} style={{ minWidth: 220 }} />
            <button className="btn btn-ghost" onClick={() => loadAlerts(1)}>Search</button>
          </div>
          <div className="toolbar-group">
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All Status</option>
              <option value="open">Open</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="in_progress">In Progress</option>
              <option value="resolved">Resolved</option>
              <option value="dismissed">Dismissed</option>
            </select>
            <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
              <option value="">All Severity</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            <select value={decision} onChange={(e) => setDecision(e.target.value)}>
              <option value="">All Decisions</option>
              <option value="block">Block</option>
              <option value="review">Review</option>
              <option value="allow">Allow</option>
            </select>
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
              <option value="created_at">Created</option>
              <option value="priority">Priority</option>
              <option value="risk_score">Risk</option>
              <option value="severity">Severity</option>
            </select>
            <select value={sortOrder} onChange={(e) => setSortOrder(e.target.value)}>
              <option value="desc">Desc</option>
              <option value="asc">Asc</option>
            </select>
            <button className="btn btn-ghost" onClick={() => { setStatus(""); setSeverity(""); setPriority(""); setDecision(""); setSearch(""); setSortBy("created_at"); setSortOrder("desc"); loadAlerts(1); }}>Clear</button>
            <button className="btn btn-primary" onClick={() => loadAlerts(1)}>Apply</button>
          </div>
        </div>

        {alerts.length === 0 ? (
          <div className="empty-state">No alerts — high-risk transactions will generate alerts automatically. Try clearing filters.</div>
        ) : (
          <div className="table-wrap">
            <table className="cases-table">
              <thead><tr><th>Priority</th><th>Severity</th><th>Alert</th><th>Transaction</th><th>Risk</th><th>Decision</th><th>Rule</th><th>Status</th><th>Created</th><th></th></tr></thead>
              <tbody>
                {alerts.map((a) => (
                  <tr key={a.id} style={{ cursor: "pointer" }} onClick={() => openDetail(a)}>
                    <td><span className="badge badge-neutral" style={{ background: a.priority > 80 ? "var(--accent-red-dim)" : a.priority > 60 ? "var(--accent-amber-dim)" : "var(--bg-secondary)" }}>{a.priority}</span></td>
                    <td><span className="badge" style={{ background: `${SEVERITY_COLOR[a.severity] || "#666"}20`, color: SEVERITY_COLOR[a.severity], borderColor: `${SEVERITY_COLOR[a.severity]}30` }}>{a.severity.toUpperCase()}</span></td>
                    <td style={{ maxWidth: 220, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={a.title}>{a.title}</td>
                    <td className="mono">{a.provider_event_id ? a.provider_event_id.slice(0, 12) : a.transaction_id ? a.transaction_id.slice(0, 8) : "—"}</td>
                    <td><RiskBadge level={a.risk_score && a.risk_score >= 85 ? "critical" : a.risk_score && a.risk_score >= 60 ? "high" : a.risk_score && a.risk_score >= 25 ? "medium" : "low"} /> <span className="muted" style={{ fontSize: ".68rem" }}>{a.risk_score ?? "—"}</span></td>
                    <td><span className={`badge rec-${a.decision.toLowerCase()}`}>{a.decision.toUpperCase()}</span></td>
                    <td className="mono" style={{ fontSize: ".72rem" }}>{a.rule_name || a.alert_type.slice(0, 12)}</td>
                    <td><span className={`badge status-${a.status}`}>{a.status}</span></td>
                    <td style={{ whiteSpace: "nowrap", fontSize: ".72rem" }}>{new Date(a.created_at).toLocaleDateString()}</td>
                    <td><button className="btn btn-ghost btn-sm" onClick={(e) => { e.stopPropagation(); openDetail(a); }}>Open</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12, alignItems: "center" }}>
          <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => loadAlerts(page - 1)}>Prev</button>
          <span className="muted" style={{ fontSize: ".76rem" }}>Page {page} — {total} total</span>
          <button className="btn btn-ghost btn-sm" disabled={alerts.length < 20} onClick={() => loadAlerts(page + 1)}>Next</button>
        </div>
      </div>

      {selected && (
        <div className="panel" style={{ borderColor: "var(--accent-blue)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <h3 style={{ margin: 0 }}>Alert Detail — <span className="mono">{selected.title}</span> <span className={`badge status-${selected.status}`}>{selected.status}</span></h3>
            <button className="btn btn-ghost btn-sm" onClick={() => setSelected(null)}>Close</button>
          </div>
          {detailLoading ? (
            <div className="loading-state">Loading alert detail…</div>
          ) : detail ? (
            <>
              <div className="case-grid" style={{ marginTop: 12 }}>
                <div className="panel" style={{ background: "var(--bg-secondary)" }}>
                  <h4 style={{ margin: "0 0 8px 0", fontSize: ".82rem" }}>Alert Overview</h4>
                  <div className="kv">
                    <dt>Severity</dt><dd><span className="badge" style={{ background: `${SEVERITY_COLOR[detail.severity]}20`, color: SEVERITY_COLOR[detail.severity] }}>{detail.severity.toUpperCase()}</span></dd>
                    <dt>Priority</dt><dd>{detail.priority}</dd>
                    <dt>Status</dt><dd>{detail.status}</dd>
                    <dt>Created</dt><dd>{new Date(detail.created_at).toLocaleString()}</dd>
                    <dt>Assigned</dt><dd>{detail.assigned_to || "Unassigned"}</dd>
                    <dt>Rule</dt><dd className="mono">{detail.rule_name || detail.alert_type}</dd>
                  </div>
                </div>
                <div className="panel" style={{ background: "var(--bg-secondary)" }}>
                  <h4 style={{ margin: "0 0 8px 0", fontSize: ".82rem" }}>Transaction</h4>
                  <div className="kv">
                    <dt>Provider ID</dt><dd className="mono">{detail.provider_event_id || "—"}</dd>
                    <dt>Amount</dt><dd>{detail.transaction ? `${(detail.transaction as any).amount ?? ""} ${ (detail.transaction as any).currency ?? ""}` : "—"}</dd>
                    <dt>Customer</dt><dd className="mono">{detail.customer_label ? <Link to={`/customers/${detail.transaction?.customer_id}`} className="link">{detail.customer_label}</Link> : "—"}</dd>
                    <dt>Merchant</dt><dd>{detail.merchant_name ? <Link to={`/merchants/${detail.transaction?.merchant_id}`} className="link">{detail.merchant_name}</Link> : "—"}</dd>
                    <dt>Device</dt><dd className="mono">{detail.transaction?.device_id ? <Link to={`/devices/${detail.transaction.device_id}`} className="link">{String(detail.transaction.device_id).slice(0, 8)}…</Link> : "—"}</dd>
                  </div>
                </div>
              </div>

              <div className="panel" style={{ background: "var(--bg-secondary)" }}>
                <h4 style={{ margin: "0 0 8px 0", fontSize: ".82rem" }}>Risk</h4>
                <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                  <RiskBadge level={detail.severity === "critical" ? "critical" : detail.risk_score && detail.risk_score >= 60 ? "high" : "medium"} />
                  <span>Score {detail.risk_score ?? "—"}</span>
                  <span className={`badge rec-${detail.decision.toLowerCase()}`}>{detail.decision.toUpperCase()}</span>
                </div>
              </div>

              {detail.transaction_id && (
                <div className="panel">
                  <h4 style={{ margin: "0 0 8px 0", fontSize: ".82rem" }}>Why? — Risk Explanation</h4>
                  <DecisionExplanation api={api} transactionId={detail.transaction_id} />
                </div>
              )}

              <div className="panel">
                <h4 style={{ margin: "0 0 8px 0", fontSize: ".82rem" }}>Operations</h4>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                  <button className="btn btn-ghost btn-sm" disabled={detail.status !== "open"} onClick={() => doStatus("acknowledged")}>Acknowledge</button>
                  <button className="btn btn-ghost btn-sm" disabled={detail.status !== "acknowledged"} onClick={() => doStatus("in_progress")}>Start Progress</button>
                  <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                    <input placeholder="Assign to" value={assignee} onChange={(e) => setAssignee(e.target.value)} style={{ height: 30, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 6, padding: "0 8px", fontSize: ".8rem" }} />
                    <button className="btn btn-ghost btn-sm" onClick={doAssign}>Assign</button>
                  </div>
                  <button className="btn btn-ghost btn-sm" onClick={doCreateCase}>{detail.case_id ? "Open Case" : "Create Case"}</button>
                  {detail.case_id && <Link to={`/case/${detail.case_id}`} className="btn btn-primary btn-sm">Go to Case</Link>}
                  <button className="btn btn-ghost btn-sm" disabled={!detail.case_id} onClick={doRunInvestigation}>Run Investigation</button>
                  <button className="btn btn-ghost btn-sm" disabled={detail.status === "resolved" || detail.status === "dismissed"} onClick={doResolve}>Resolve</button>
                  <button className="btn btn-ghost btn-sm" disabled={detail.status === "resolved" || detail.status === "dismissed"} onClick={doDismiss}>Dismiss</button>
                  {detail.transaction?.customer_id && <Link to={`/network?entity_type=customer&entity_id=${detail.transaction.customer_id}`} className="btn btn-ghost btn-sm">Network</Link>}
                </div>
                {detail.case_id && <div className="muted" style={{ marginTop: 8, fontSize: ".72rem" }}>Linked Case: <Link to={`/case/${detail.case_id}`} className="link mono">{detail.case_id.slice(0, 8)}…</Link></div>}
                {actionMsg && <div className="ok-banner" style={{ marginTop: 8 }}>{actionMsg}</div>}
              </div>
            </>
          ) : (
            <div className="empty-state">No detail</div>
          )}
        </div>
      )}

      <div className="panel">
        <h3>Analyst Workflow</h3>
        <div className="flow" style={{ justifyContent: "center" }}>
          <span className="flow-step">High Priority Alert</span> <span className="flow-arrow">→</span>
          <span className="flow-step">Open Alert</span> <span className="flow-arrow">→</span>
          <span className="flow-step">View Risk Explanation</span> <span className="flow-arrow">→</span>
          <span className="flow-step">Check Entities</span> <span className="flow-arrow">→</span>
          <span className="flow-step">Network</span> <span className="flow-arrow">→</span>
          <span className="flow-step">Create Case</span> <span className="flow-arrow">→</span>
          <span className="flow-step">Investigate</span> <span className="flow-arrow">→</span>
          <span className="flow-step">Resolve</span>
        </div>
      </div>
    </section>
  );
}
