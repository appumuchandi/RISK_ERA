import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import type { ApiService, CaseDetail } from "../api";
import DecisionExplanation from "./DecisionExplanation";
import { RiskBadge } from "./intel/IntelShared";

const STAGE_NAMES = [
  "Retrieve transaction context",
  "Evaluate risk signals",
  "Retrieve supporting evidence",
  "Analyze with Nemotron",
  "Ground findings",
  "Generate recommendation",
];

export const CaseInvestigation = ({ api }: { api: ApiService }) => {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [workbench, setWorkbench] = useState<any>(null);
  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [running, setRunning] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [assignee, setAssignee] = useState("");
  const [newStatus, setNewStatus] = useState("");

  const load = async () => {
    if (!caseId) return;
    try {
      setLoading(true);
      setError(null);
      // Try workbench first
      try {
        const wb = await api.getWorkbench(caseId);
        setWorkbench(wb);
        // Also set caseDetail from workbench case
        if (wb.case) {
          setCaseDetail({
            id: wb.case.id,
            transaction_id: wb.case.transaction_id,
            status: wb.case.status,
            assignee: wb.case.assignee,
            created_at: wb.case.created_at,
            updated_at: wb.case.updated_at,
            transaction: wb.transaction,
            evidence_count: wb.evidence?.length || 0,
            evidence: wb.evidence,
          } as any);
        }
      } catch (e: any) {
        // fallback to old method
        const c = await api.getCase(caseId);
        setCaseDetail(c);
        setWorkbench(null);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unable to load case");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  const runInvestigation = async () => {
    if (!caseId || running) return;
    setRunning(true);
    setActionMsg(null);
    setActionErr(null);
    try {
      await api.runInvestigation(caseId);
      setActionMsg("Investigation started — refreshing…");
      setTimeout(() => load(), 1200);
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e.message || "Investigation failed";
      setActionErr(detail);
    } finally {
      setRunning(false);
    }
  };

  const handleAssign = async () => {
    if (!assignee.trim() || !caseId) return;
    try {
      setActionErr(null);
      // Use existing cases API assign
      await api.client.patch(`/api/v1/cases/${caseId}/assign`, { assignee: assignee.trim() });
      setActionMsg(`Assigned to ${assignee}`);
      setAssignee("");
      load();
    } catch (e: any) {
      setActionErr(e?.response?.data?.detail || "Assign failed");
    }
  };

  const handleStatusChange = async () => {
    if (!newStatus || !caseId) return;
    try {
      setActionErr(null);
      await api.client.patch(`/api/v1/cases/${caseId}/status`, { status: newStatus });
      setActionMsg(`Status → ${newStatus}`);
      load();
    } catch (e: any) {
      setActionErr(e?.response?.data?.detail || "Status change failed");
    }
  };

  if (loading) return <div className="loading-state">Loading investigation workbench…</div>;
  if (error && !caseDetail) return <div className="error-state"><h3>Unable to load case</h3><p>{error}</p><button className="btn btn-primary" onClick={load}>Retry</button><button className="btn btn-ghost" onClick={() => navigate("/cases")}>Back to Cases</button></div>;
  if (!caseDetail) return <div className="empty-state">No case available</div>;

  const txn = workbench?.transaction || (caseDetail as any).transaction || {};
  const inv = workbench?.investigation;
  const stages = workbench?.stages || STAGE_NAMES.map((name) => ({ name, status: "pending" as string, result: null, error: null }));
  const evidence = workbench?.evidence || [];
  const timeline = workbench?.timeline || [];
  const related = workbench?.related_entities || {};
  const risk = workbench?.risk || {};
  const summary = workbench?.summary;

  const riskScore = risk.risk_score ?? "";
  const riskLevel = risk.risk_level || "low";
  const decision = risk.decision || "allow";
  const providerEvent = txn.provider_event_id || (txn as any).provider_event_id || caseDetail.transaction_id.slice(0, 8);
  const amount = txn.amount || (txn as any).amount || "0";

  return (
    <section className="case-page">
      <button className="btn btn-ghost" onClick={() => navigate("/cases")}>← Back to Cases</button>

      {/* A. Header — analyst workstation: risk → decision → status → investigation */}
      <div className="case-header" style={{ marginTop: 8 }}>
        <h2 style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          CASE-{caseDetail.id.slice(0, 8).toUpperCase()}
          <span className={`badge risk-${riskLevel}`} title="Risk level from RuleEngine">{riskLevel.toUpperCase()}</span>
          <span className={`badge rec-${decision}`} title="RuleEngine decision">{decision.toUpperCase()}</span>
          <span className={`badge status-${caseDetail.status}`} title="Case status">{caseDetail.status}</span>
          {inv && <span className={`badge ${inv.status === "completed" ? "badge-ok" : inv.status === "failed" ? "badge-bad" : "badge-neutral"}`} title="Investigation status">{inv.status}</span>}
        </h2>
        <p className="muted">Demo Environment · Synthetic Payment Data — not real customer/payment data · Last updated {caseDetail.updated_at ? new Date(caseDetail.updated_at).toLocaleString() : new Date(caseDetail.created_at).toLocaleString()}</p>
        <div className="kv" style={{ marginTop: 8 }}>
          <dt>Customer</dt><dd className="mono">{related.customer_id ? <Link to={`/customers/${related.customer_id}`} className="link">{related.customer_id.slice(0, 8)}…</Link> : (txn as any).customer_id ? <Link to={`/customers/${(txn as any).customer_id}`} className="link">{String((txn as any).customer_id).slice(0, 8)}…</Link> : "—"}</dd>
          <dt>Merchant</dt><dd>{related.merchant_id ? <Link to={`/merchants/${related.merchant_id}`} className="link">{related.merchant_id.slice(0, 8)}…</Link> : (txn as any).merchant_id ? <Link to={`/merchants/${(txn as any).merchant_id}`} className="link">{String((txn as any).merchant_id).slice(0, 8)}…</Link> : "—"}</dd>
          <dt>Device</dt><dd className="mono">{related.device_id ? <Link to={`/devices/${related.device_id}`} className="link">{related.device_id.slice(0, 8)}…</Link> : (txn as any).device_id ? <Link to={`/devices/${(txn as any).device_id}`} className="link">{String((txn as any).device_id).slice(0, 8)}…</Link> : "new-device"}</dd>
          <dt>Transaction</dt><dd className="mono">{providerEvent} · ₹{parseFloat(String(amount)).toLocaleString("en-IN")} · {riskScore ? `${riskScore}` : ""} <RiskBadge level={riskLevel} /></dd>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
          <button className="btn btn-primary" onClick={runInvestigation} disabled={running}>{running ? "Running…" : inv ? "Re-run Investigation" : "Run Investigation"}</button>
          <button className="btn btn-ghost" onClick={load}>Refresh</button>
          {related.alert_id && <Link to={`/alerts`} className="btn btn-ghost">Open Alert</Link>}
          <Link to={`/network`} className="btn btn-ghost">Open Network</Link>
        </div>
        {actionMsg && <div className="ok-banner" style={{ marginTop: 8 }}>{actionMsg}</div>}
        {actionErr && <div className="error-banner">{actionErr}</div>}
        {error && <div className="error-banner">{error}</div>}
      </div>

      {/* B. Progress */}
      <div className="panel" style={{ marginTop: 16 }}>
        <h3>Investigation Progress — 6 Stages</h3>
        <div className="progress-steps">
          {stages.map((s: any, idx: number) => (
            <div key={s.name} className={`step ${s.status === "completed" ? "done" : s.status === "running" ? "active" : s.status === "failed" ? "bad" : ""}`}>
              <span className="step-dot">{s.status === "completed" ? "✓" : s.status === "failed" ? "!" : idx + 1}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: ".76rem" }}>{s.name}</div>
                <div className="muted" style={{ fontSize: ".66rem" }}>{s.status} {s.duration_ms ? `· ${s.duration_ms}ms` : ""} {s.start_time ? `· ${new Date(s.start_time).toLocaleTimeString()}` : ""}</div>
                {s.result && <div style={{ fontSize: ".68rem", marginTop: 2 }}>{s.result}</div>}
                {s.error && <div style={{ fontSize: ".68rem", color: "var(--accent-red)" }}>{s.error}</div>}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* C. Summary */}
      <div className="panel">
        <h3>Executive Investigation Summary</h3>
        {!inv ? (
          <div className="empty-state">No investigation has been run for this case.</div>
        ) : (
          <div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
              <span className={`badge rec-${String(inv.recommendation || "").toLowerCase()}`}>{String(inv.recommendation || "pending").toUpperCase()}</span>
              <span>Confidence {(typeof inv.confidence === "number" ? (inv.confidence > 1 ? inv.confidence : inv.confidence * 100) : 0).toFixed(0)}%</span>
              <span className="muted">{inv.model_available ? `Nemotron ${inv.model_name} available` : "Deterministic fallback — Nemotron unavailable"}</span>
              {!inv.model_available && <span className="badge badge-warn">Fallback</span>}
            </div>
            <div className="kv">
              <dt>Conclusion</dt><dd>{summary?.risk_assessment || inv.risk_assessment || "—"}</dd>
              <dt>Risk Assessment</dt><dd>{summary?.risk_assessment || inv.risk_assessment || "—"}</dd>
              <dt>Recommended Action</dt><dd><span className={`badge rec-${String(inv.recommendation || "").toLowerCase()}`}>{String(inv.recommendation || "").toUpperCase()}</span></dd>
              <dt>Reasoning Summary</dt><dd>{summary?.reasoning_summary || inv.reasoning_summary || "Additional evidence required"}</dd>
            </div>
          </div>
        )}
      </div>

      {/* D. Why risky */}
      <div className="panel">
        <h3>Why is this transaction risky? <span className="muted" style={{ fontWeight: 400 }}>— RuleEngine Decision Transparency</span></h3>
        {caseDetail.transaction_id ? <DecisionExplanation api={api} transactionId={caseDetail.transaction_id} /> : <div className="empty-state">No transaction linked</div>}
      </div>

      {/* E. Evidence — grounding status from real investigation data */}
      <div className="panel">
        <h3>Evidence Workspace — {evidence.length} items {evidence.length === 0 ? <span className="badge badge-warn">Evidence Exceptions</span> : inv ? <span className="badge badge-neutral">{(inv.evidence_references||[]).length} valid · {(inv.missing_evidence||[]).length} missing</span> : <span className="badge badge-neutral">Awaiting investigation</span>}</h3>
        <p className="muted" style={{ fontSize: ".72rem", marginTop: 4 }}>Grounding: <span className="badge badge-ok" style={{ fontSize: ".62rem" }}>Valid</span> exists &amp; supports finding · <span className="badge badge-bad" style={{ fontSize: ".62rem" }}>Missing</span> referenced but not found · <span className="badge badge-warn" style={{ fontSize: ".62rem" }}>Referenced</span> linked but not yet validated · Derived from Investigation.evidence_references / missing_evidence</p>
        {evidence.length === 0 ? (
          <div className="empty-state">No evidence grounded yet — run investigation to retrieve transaction/customer/device context</div>
        ) : (
          <div className="table-wrap">
            <table className="cases-table">
              <thead><tr><th>Evidence ID</th><th>Type</th><th>Source</th><th>Timestamp</th><th>Grounding</th></tr></thead>
              <tbody>
                {evidence.map((ev: any) => {
                  const idStr = String(ev.id);
                  const isMissing = inv && Array.isArray(inv.missing_evidence) && inv.missing_evidence.includes(idStr);
                  const isValid = inv && Array.isArray(inv.evidence_references) && inv.evidence_references.includes(idStr);
                  let grounding: { label: string; cls: string } = { label: "Referenced", cls: "badge-warn" };
                  if (isValid) grounding = { label: "Valid", cls: "badge-ok" };
                  else if (isMissing) grounding = { label: "Missing", cls: "badge-bad" };
                  else if (!inv) grounding = { label: "Pending", cls: "badge-neutral" };
                  return (
                    <tr key={ev.id}>
                      <td className="mono">{idStr.slice(0, 8)}</td>
                      <td>{ev.source_type}</td>
                      <td className="muted" title={String(ev.source_id)}>{String(ev.source_id).slice(0, 12)}</td>
                      <td style={{ fontSize: ".72rem" }}>{ev.created_at ? new Date(ev.created_at).toLocaleString() : ev.retrieved_at ? new Date(ev.retrieved_at).toLocaleString() : "—"}</td>
                      <td><span className={`badge ${grounding.cls}`}>{grounding.label}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* F. Tool Trace */}
      <div className="panel">
        <h3>Tool Execution Trace — Observability</h3>
        {!inv || !inv.tool_calls || inv.tool_calls.length === 0 ? (
          <div className="empty-state">No tool calls recorded yet — run investigation to see trace.</div>
        ) : (
          <div className="trace">
            <ul>
              {(Array.isArray(inv.tool_calls) ? inv.tool_calls : []).map((tc: any, idx: number) => (
                <li key={idx} style={{ borderLeft: `3px solid ${tc.result && JSON.parse(tc.result || "{}").success === false ? "var(--accent-red)" : "var(--accent-green)"}`, paddingLeft: 8 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                    <strong className="mono" style={{ fontSize: ".72rem" }}>{tc.function?.name || tc.name || `Tool ${idx + 1}`}</strong>
                    <span className={`badge ${tc.result && JSON.parse(tc.result || "{}").success === false ? "badge-bad" : "badge-ok"}`}>{tc.result && JSON.parse(tc.result || "{}").success === false ? "failed" : "completed"}</span>
                  </div>
                  <div className="muted" style={{ fontSize: ".68rem", marginTop: 4, whiteSpace: "pre-wrap", maxHeight: 80, overflowY: "auto" }}>
                    Input: {tc.function?.arguments ? String(tc.function.arguments).slice(0, 200) : "—"}
                  </div>
                  <div className="muted" style={{ fontSize: ".68rem", whiteSpace: "pre-wrap", maxHeight: 80, overflowY: "auto" }}>
                    Output: {tc.result ? String(tc.result).slice(0, 300) : "—"}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
        {/* Fallback to frontend simulated trace if no persisted tool_calls but we have inv */}
        {inv && (!inv.tool_calls || inv.tool_calls.length === 0) && inv.status === "completed" && (
          <p className="muted" style={{ marginTop: 8, fontSize: ".72rem" }}>Investigation completed via deterministic fallback — tool trace not available (model unavailable).</p>
        )}
      </div>

      {/* G. Timeline */}
      <div className="panel">
        <h3>Investigation Timeline — Real Persisted Events</h3>
        {timeline.length === 0 ? (
          <div className="empty-state">No timeline events yet.</div>
        ) : (
          <ul className="activity-list">
            {timeline.slice(0, 20).map((ev: any, idx: number) => (
              <li key={idx} className="activity-item">
                <span className="activity-action"><span className="badge badge-neutral" style={{ fontSize: ".6rem" }}>{ev.event}</span> {ev.detail}</span>
                <span className="activity-ts">{ev.timestamp ? new Date(ev.timestamp).toLocaleString() : ""} · {ev.actor}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* H. Analyst Decision — clearly distinguish from AI recommendation */}
      <div className="panel" style={{ borderLeft: "3px solid var(--accent-primary)" }}>
        <h3>Analyst Decision <span className="muted" style={{ fontWeight: 400, fontSize: ".72rem" }}>— Overrides AI recommendation · Creates audit event</span></h3>
        <p className="muted" style={{ fontSize: ".72rem", marginTop: 2 }}>AI previously recommended <span className={`badge rec-${String(inv?.recommendation||"pending").toLowerCase()}`}>{String(inv?.recommendation||"pending").toUpperCase()}</span> {inv ? `(${((typeof inv.confidence==="number"? (inv.confidence>1?inv.confidence:inv.confidence*100):0).toFixed(0))}%)` : ""} — analyst action is authoritative and hash-chained.</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 10 }}>
          <input placeholder="Assign to analyst" value={assignee} onChange={(e) => setAssignee(e.target.value)} style={{ height: 32, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 6, padding: "0 8px", fontSize: ".82rem", minWidth: 160 }} />
          <button className="btn btn-ghost btn-sm" onClick={handleAssign}>Assign Case</button>
          <select value={newStatus} onChange={(e) => setNewStatus(e.target.value)} style={{ height: 32, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 6, padding: "0 8px", fontSize: ".82rem" }}>
            <option value="">Change status…</option>
            <option value="open">Open</option>
            <option value="in_progress">In Progress</option>
            <option value="escalated">Escalated</option>
            <option value="closed_approved">Closed Approved</option>
            <option value="closed_denied">Closed Denied</option>
          </select>
          <button className="btn btn-ghost btn-sm" onClick={handleStatusChange}>Update Status</button>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
          <Link to={`/network?entity_type=transaction&entity_id=${caseDetail.transaction_id}`} className="btn btn-ghost btn-sm">Fraud Network</Link>
          {related.customer_id && <Link to={`/customers/${related.customer_id}`} className="btn btn-ghost btn-sm">Customer {related.customer_id.slice(0, 8)}…</Link>}
          {related.merchant_id && <Link to={`/merchants/${related.merchant_id}`} className="btn btn-ghost btn-sm">Merchant {related.merchant_id.slice(0, 8)}…</Link>}
          {related.device_id && <Link to={`/devices/${related.device_id}`} className="btn btn-ghost btn-sm">Device {related.device_id.slice(0, 8)}…</Link>}
          {related.alert_id && <Link to={`/alerts`} className="btn btn-ghost btn-sm">Alert {related.alert_id.slice(0, 8)}…</Link>}
          <Link to={`/rules`} className="btn btn-ghost btn-sm">Rules</Link>
          {caseDetail.transaction_id && <Link to={`/transactions`} className="btn btn-ghost btn-sm">Transactions</Link>}
        </div>
        {actionMsg && <div className="ok-banner" style={{ marginTop: 8 }}>{actionMsg}</div>}
        {actionErr && <div className="error-banner">{actionErr}</div>}
      </div>
    </section>
  );
};
