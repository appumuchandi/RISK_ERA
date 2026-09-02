import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import type { ApiService, DashboardAnalytics } from "../api";

type Props = { api: ApiService; onNavigate: (p: string) => void };

export const Dashboard = ({ api }: Props) => {
  const navigate = useNavigate();
  const [days, setDays] = useState<number>(30);
  const [data, setData] = useState<DashboardAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [auditValid, setAuditValid] = useState<boolean | null>(null);
  const [priorityCases, setPriorityCases] = useState<Array<{ id: string; status: string; created_at: string; amount?: string }>>([]);
  const [priorityLoading, setPriorityLoading] = useState(false);

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const [analytics, verifyRes] = await Promise.all([
        api.getDashboardAnalytics(days),
        api.verifyAuditChain().catch(() => ({ valid: false })),
      ]);
      setData(analytics);
      setAuditValid((verifyRes as { valid: boolean }).valid ?? null);
      // priority cases — real backend data only
      setPriorityLoading(true);
      try {
        const cRes: any = await api.getCases(1, 5, { status: "open" });
        const items = cRes?.items || [];
        // fetch amount for each to sort by risk (amount) deterministically
        const withAmt = await Promise.all(items.slice(0, 5).map(async (c: any) => {
          try {
            const d: any = await api.getCase(c.id);
            return { id: c.id, status: c.status, created_at: c.created_at, amount: d?.transaction?.amount || "0" };
          } catch { return { id: c.id, status: c.status, created_at: c.created_at, amount: "0" }; }
        }));
        withAmt.sort((a, b) => parseFloat(b.amount || "0") - parseFloat(a.amount || "0"));
        setPriorityCases(withAmt);
      } catch { setPriorityCases([]); } finally { setPriorityLoading(false); }
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || (e instanceof Error ? e.message : "Unable to load risk analytics.");
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days, api]);

  if (loading) {
    return (
      <section className="dashboard">
        <div className="page-head">
          <div>
            <h2>Risk Operations Overview</h2>
            <p className="muted">Real-time fraud and transaction intelligence — <em>Demo Environment · Synthetic Payment Data</em></p>
          </div>
        </div>
        <div className="kpi-grid">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="kpi-card">
              <div className="skeleton" style={{ height: 22, width: "40%" }} />
              <div className="skeleton" style={{ height: 12, width: "60%", marginTop: 8 }} />
            </div>
          ))}
        </div>
        <div className="dashboard-grid">
          <div className="panel"><div className="skeleton" style={{ height: 160 }} /></div>
          <div className="panel"><div className="skeleton" style={{ height: 160 }} /></div>
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <div className="error-state">
        <h3>Unable to load risk analytics.</h3>
        <p>{error}</p>
        <p className="muted">Backend connection required — ensure FastAPI is running</p>
        <button className="btn btn-primary" onClick={load}>Retry</button>
      </div>
    );
  }

  if (!data) {
    return <div className="empty-state">Not enough transaction data for analytics.</div>;
  }

  const fmtAmt = (v: string | number) => {
    const n = typeof v === "string" ? parseFloat(v) : v;
    if (Number.isNaN(n)) return "—";
    return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  };
  const fmtNum = (n: number) => n.toLocaleString("en-IN");

  const ov = data.overview;
  const riskTotal = data.risk_distribution.reduce((a, b) => a + b.count, 0) || 1;
  const decTotal = data.decision_distribution.reduce((a, b) => a + b.count, 0) || 1;

  // For trend sparkline, simple SVG
  const maxTx = Math.max(...data.transaction_trend.map((d) => d.transaction_count), 1);
  const maxVal = Math.max(...data.transaction_trend.map((d) => parseFloat(d.transaction_value)), 1);

  return (
    <section className="dashboard">
      <div className="page-head">
        <div>
          <h2>Risk Operations Overview</h2>
          <p className="muted">Real-time fraud and transaction intelligence — <em>Demo Environment · Synthetic Payment Data</em> — Generated {new Date(data.generated_at).toLocaleString()} · {data.days}D window</p>
        </div>
        <div className="head-actions" style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span className={`badge ${auditValid ? "badge-ok" : auditValid === false ? "badge-bad" : "badge-neutral"}`}>SHA-256 {auditValid === null ? "…" : auditValid ? "VERIFIED" : "BROKEN"}</span>
          <div style={{ display: "flex", gap: 4 }}>
            {[7, 30, 90].map((d) => (
              <button key={d} className={`btn btn-sm ${days === d ? "btn-primary" : "btn-ghost"}`} onClick={() => setDays(d)}>{d}D</button>
            ))}
          </div>
        </div>
      </div>

      {/* Priority Attention — real cases from backend, demo flow entry */}
      <div className="panel" style={{ padding: 16, marginBottom: 16, borderLeft: "3px solid var(--accent-amber)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <h3 style={{ margin: 0, display: "flex", alignItems: "center", gap: 8 }}>Priority Attention <span className="badge badge-neutral">{priorityCases.length ? `${priorityCases.length} open` : "—"}</span> <span className="muted" style={{ fontWeight: 400, fontSize: ".72rem" }}>— Open cases by risk (real PostgreSQL)</span></h3>
          <button className="btn btn-ghost btn-sm" onClick={() => navigate("/cases")}>View all cases →</button>
        </div>
        {priorityLoading ? <div className="loading-state" style={{ margin: "12px 0 0 0" }}>Loading priority cases…</div> : priorityCases.length === 0 ? <div className="empty-state" style={{ marginTop: 12 }}>No open cases — all clear. Seed provides 83 cases via RuleEngine when available.</div> : (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table className="cases-table" style={{ minWidth: 520 }}>
              <thead><tr><th>Case ID</th><th>Amount</th><th>Status</th><th>Created</th><th></th></tr></thead>
              <tbody>{priorityCases.map((c) => {
                const amt = parseFloat(c.amount || "0");
                const risk = amt > 30000 ? "Critical" : amt > 10000 ? "High" : amt > 5000 ? "Medium" : "Low";
                return (
                  <tr key={c.id} style={{ cursor: "pointer" }} onClick={() => navigate(`/case/${c.id}`)}>
                    <td className="mono">CASE-{c.id.slice(0, 8).toUpperCase()}</td>
                    <td>₹{amt.toLocaleString("en-IN")}</td>
                    <td><span className={`badge status-${c.status}`}>{c.status}</span> <span className={`badge risk-${risk.toLowerCase()}`}>{risk}</span></td>
                    <td style={{ fontSize: ".78rem" }} className="muted">{new Date(c.created_at).toLocaleDateString()}</td>
                    <td><button className="btn btn-primary btn-sm" onClick={(e) => { e.stopPropagation(); navigate(`/case/${c.id}`); }}>Open →</button></td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
        )}
      </div>

      {/* KPI ROW */}
      <div className="kpi-grid">
        <div className="kpi-card" style={{ cursor: "default" }}>
          <div className="kpi-value">{fmtNum(ov.total_transactions)}</div>
          <div className="kpi-label">Transactions</div>
          <div className="kpi-hint">{fmtAmt(ov.total_transaction_value)} total</div>
        </div>
        <div className="kpi-card" style={{ cursor: "default" }}>
          <div className="kpi-value">{fmtAmt(ov.total_transaction_value)}</div>
          <div className="kpi-label">Transaction Value</div>
          <div className="kpi-hint">Avg {fmtAmt(ov.average_transaction_value)}</div>
        </div>
        <div className="kpi-card tone-critical" style={{ cursor: "default" }}>
          <div className="kpi-value">{fmtNum(ov.high_risk_transactions + ov.critical_risk_transactions)}</div>
          <div className="kpi-label">High / Critical Risk</div>
          <div className="kpi-hint">{ov.critical_risk_transactions} critical · {ov.high_risk_transactions} high</div>
        </div>
        <div className="kpi-card tone-critical" style={{ cursor: "default" }}>
          <div className="kpi-value">{fmtNum(ov.blocked_transactions)}</div>
          <div className="kpi-label">Blocked</div>
          <div className="kpi-hint">{ov.review_transactions} review · {ov.allowed_transactions} allowed</div>
        </div>
        <div className="kpi-card tone-medium" style={{ cursor: "default" }}>
          <div className="kpi-value">{fmtNum(ov.open_cases)}</div>
          <div className="kpi-label">Open Cases</div>
          <div className="kpi-hint">{ov.in_progress_cases} in progress · {ov.escalated_cases} escalated</div>
        </div>
        <div className="kpi-card tone-low" style={{ cursor: "default" }}>
          <div className="kpi-value">{fmtNum(ov.total_cases)}</div>
          <div className="kpi-label">Total Cases ({days}D)</div>
          <div className="kpi-hint">All cases in window</div>
        </div>
      </div>

      {/* RISK + DECISION */}
      <div className="dashboard-grid">
        <div className="panel">
          <h3>Risk Distribution</h3>
          <p className="muted">Backend RuleEngine — {riskTotal} transactions in {days}D</p>
          <div className="risk-bars">
            {data.risk_distribution.map((r) => (
              <div key={r.risk_level} className="risk-row">
                <span className="risk-label">{r.risk_level}</span>
                <div className="risk-bar"><div className={`risk-fill ${r.risk_level}`} style={{ width: `${r.percentage}%` }} /></div>
                <span className="risk-count">{r.count}</span>
                <span className="muted" style={{ fontSize: ".66rem" }}>{r.percentage}%</span>
              </div>
            ))}
          </div>
        </div>
        <div className="panel">
          <h3>Decision Distribution</h3>
          <p className="muted">BLOCK &gt; REVIEW &gt; ALLOW precedence — {decTotal} decisions</p>
          <div className="risk-bars">
            {data.decision_distribution.map((d) => (
              <div key={d.decision} className="risk-row">
                <span className="risk-label" style={{ textTransform: "capitalize" }}>{d.decision}</span>
                <div className="risk-bar"><div className={`risk-fill ${d.decision === "block" ? "high" : d.decision === "review" ? "medium" : "low"}`} style={{ width: `${d.percentage}%` }} /></div>
                <span className="risk-count">{d.count}</span>
                <span className="muted" style={{ fontSize: ".66rem" }}>{d.percentage}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* TRENDS */}
      <div className="dashboard-grid">
        <div className="panel">
          <h3>Transaction & Risk Trend ({days}D)</h3>
          <p className="muted">Daily volume, high-risk and blocked — {data.transaction_trend.length} days</p>
          {data.transaction_trend.length === 0 ? (
            <div className="empty-state">No transaction trend data</div>
          ) : (
            <>
              <div style={{ overflowX: "auto" }}>
                <svg width="100%" height="100" viewBox="0 0 400 100" style={{ minWidth: 300 }}>
                  {/* grid */}
                  <line x1={30} y1={10} x2={30} y2={80} stroke="var(--border)" strokeWidth={1} />
                  <line x1={30} y1={80} x2={380} y2={80} stroke="var(--border)" strokeWidth={1} />
                  {/* transaction count line */}
                  <polyline
                    fill="none"
                    stroke="var(--accent-blue)"
                    strokeWidth={2}
                    points={data.transaction_trend
                      .map((d, i) => {
                        const x = 30 + (i / Math.max(data.transaction_trend.length - 1, 1)) * 350;
                        const y = 80 - (d.transaction_count / maxTx) * 60;
                        return `${x},${y}`;
                      })
                      .join(" ")}
                  />
                  {/* value line dashed */}
                  <polyline
                    fill="none"
                    stroke="var(--accent-green)"
                    strokeWidth={1.5}
                    strokeDasharray="4 3"
                    points={data.transaction_trend
                      .map((d, i) => {
                        const x = 30 + (i / Math.max(data.transaction_trend.length - 1, 1)) * 350;
                        const y = 80 - (parseFloat(d.transaction_value) / maxVal) * 60;
                        return `${x},${y}`;
                      })
                      .join(" ")}
                  />
                </svg>
              </div>
              <div className="table-wrap" style={{ marginTop: 10 }}>
                <table className="cases-table" style={{ minWidth: 400 }}>
                  <thead><tr><th>Date</th><th>Count</th><th>Value</th><th>High Risk</th><th>Blocked</th></tr></thead>
                  <tbody>
                    {data.transaction_trend.slice(-7).map((r) => (
                      <tr key={r.date}><td>{r.date}</td><td>{r.transaction_count}</td><td>{fmtAmt(r.transaction_value)}</td><td>{r.high_risk_count}</td><td>{r.blocked_count}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
        <div className="panel">
          <h3>Case Trend ({days}D)</h3>
          <p className="muted">Opened, in-progress, resolved, confirmed fraud</p>
          {data.case_trend.length === 0 ? (
            <div className="empty-state">No case trend data</div>
          ) : (
            <div className="table-wrap">
              <table className="cases-table" style={{ minWidth: 400 }}>
                <thead><tr><th>Date</th><th>Opened</th><th>In Progress</th><th>Resolved</th><th>Fraud</th></tr></thead>
                <tbody>
                  {data.case_trend.slice(-7).map((r) => (
                    <tr key={r.date}><td>{r.date}</td><td>{r.opened}</td><td>{r.in_progress}</td><td>{r.resolved}</td><td>{r.confirmed_fraud}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <h4 style={{ margin: "14px 0 6px 0", fontSize: ".78rem", color: "var(--text-secondary)" }}>Top Triggered Rules</h4>
          {data.top_triggered_rules.length === 0 ? (
            <div className="empty-state">No rules triggered in window</div>
          ) : (
            <ul className="signal-list">
              {data.top_triggered_rules.slice(0, 5).map((r) => (
                <li key={r.rule} className="sig-hit" style={{ display: "flex", justifyContent: "space-between" }}>
                  <span className="mono">{r.rule} <span className={`badge rec-${r.action}`}>{r.action}</span></span>
                  <span className="badge badge-neutral">×{r.count}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* RISK CONCENTRATION */}
      <div className="panel">
        <h3>Risk Concentration — Top Entities by High-Risk Activity</h3>
        <p className="muted">Real backend-derived: high-risk count, blocked count, total value, average risk — bounded top 5 per type</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16, marginTop: 12 }}>
          <div>
            <h4 style={{ fontSize: ".82rem", margin: "0 0 8px 0" }}>Customers</h4>
            {data.risk_concentration.customers.length === 0 ? (
              <div className="empty-state">No customer concentration</div>
            ) : (
              <div className="table-wrap">
                <table className="cases-table" style={{ minWidth: 300 }}>
                  <thead><tr><th>Customer</th><th>Txns</th><th>High</th><th>Blocked</th><th>Value</th><th>Risk</th></tr></thead>
                  <tbody>
                    {data.risk_concentration.customers.map((c) => (
                      <tr key={c.id} style={{ cursor: "pointer" }} onClick={() => navigate(`/customers/${c.id}`)}>
                        <td className="mono">{c.label.slice(0, 14)}</td><td>{c.transaction_count}</td><td>{c.high_risk_count}</td><td>{c.blocked_count}</td><td>{fmtAmt(c.total_value)}</td><td><span className={`badge risk-${c.risk_level}`}>{c.risk_level}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <div>
            <h4 style={{ fontSize: ".82rem", margin: "0 0 8px 0" }}>Merchants</h4>
            {data.risk_concentration.merchants.length === 0 ? (
              <div className="empty-state">No merchant concentration</div>
            ) : (
              <div className="table-wrap">
                <table className="cases-table" style={{ minWidth: 300 }}>
                  <thead><tr><th>Merchant</th><th>Txns</th><th>High</th><th>Blocked</th><th>Value</th><th>Risk</th></tr></thead>
                  <tbody>
                    {data.risk_concentration.merchants.map((m) => (
                      <tr key={m.id} style={{ cursor: "pointer" }} onClick={() => navigate(`/merchants/${m.id}`)}>
                        <td>{m.label.slice(0, 14)}</td><td>{m.transaction_count}</td><td>{m.high_risk_count}</td><td>{m.blocked_count}</td><td>{fmtAmt(m.total_value)}</td><td><span className={`badge risk-${m.risk_level}`}>{m.risk_level}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <div>
            <h4 style={{ fontSize: ".82rem", margin: "0 0 8px 0" }}>Devices</h4>
            {data.risk_concentration.devices.length === 0 ? (
              <div className="empty-state">No device concentration</div>
            ) : (
              <div className="table-wrap">
                <table className="cases-table" style={{ minWidth: 300 }}>
                  <thead><tr><th>Device</th><th>Txns</th><th>High</th><th>Blocked</th><th>Value</th><th>Risk</th></tr></thead>
                  <tbody>
                    {data.risk_concentration.devices.map((d) => (
                      <tr key={d.id} style={{ cursor: "pointer" }} onClick={() => navigate(`/devices/${d.id}`)}>
                        <td className="mono">{d.label.slice(0, 12)}</td><td>{d.transaction_count}</td><td>{d.high_risk_count}</td><td>{d.blocked_count}</td><td>{fmtAmt(d.total_value)}</td><td><span className={`badge risk-${d.risk_level}`}>{d.risk_level}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* OPERATIONAL INSIGHTS */}
      <div className="panel">
        <h3>Operational Insights — Backend-Derived</h3>
        <ul className="signal-list">
          <li className="sig-hit">• {ov.high_risk_transactions + ov.critical_risk_transactions} of {ov.total_transactions} transactions are high/critical risk ({ov.total_transactions ? (( (ov.high_risk_transactions + ov.critical_risk_transactions) / ov.total_transactions * 100).toFixed(1)) : 0}%)</li>
          <li className="sig-hit">• Blocked rate {ov.total_transactions ? (ov.blocked_transactions / ov.total_transactions * 100).toFixed(1) : 0}% ({ov.blocked_transactions} blocked) — review rate {(ov.review_transactions / Math.max(ov.total_transactions, 1) * 100).toFixed(1)}%</li>
          <li className="sig-hit">• Open case backlog {ov.open_cases} · in-progress {ov.in_progress_cases} · escalated {ov.escalated_cases}</li>
          {data.top_triggered_rules[0] && <li className="sig-hit">• Most triggered rule: <span className="mono">{data.top_triggered_rules[0].rule}</span> ×{data.top_triggered_rules[0].count} ({data.top_triggered_rules[0].action})</li>}
          {data.risk_concentration.customers[0] && <li className="sig-hit">• Highest risk customer: <Link to={`/customers/${data.risk_concentration.customers[0].id}`} className="link mono">{data.risk_concentration.customers[0].label}</Link> — {data.risk_concentration.customers[0].high_risk_count} high-risk txns</li>}
          {data.risk_concentration.merchants[0] && <li className="sig-hit">• Highest risk merchant: <Link to={`/merchants/${data.risk_concentration.merchants[0].id}`} className="link">{data.risk_concentration.merchants[0].label}</Link> — {data.risk_concentration.merchants[0].blocked_count} blocked</li>}
        </ul>
      </div>

      <div className="panel">
        <h3>Detect → Investigate → Ground → Decide → Audit</h3>
        <div className="flow">
          <span className="flow-step">Suspicious transaction</span>
          <span className="flow-arrow">→</span>
          <span className="flow-step">Risk detected</span>
          <span className="flow-arrow">→</span>
          <span className="flow-step">Case created</span>
          <span className="flow-arrow">→</span>
          <span className="flow-step">AI investigation</span>
          <span className="flow-arrow">→</span>
          <span className="flow-step">Evidence grounding</span>
          <span className="flow-arrow">→</span>
          <span className="flow-step">Analyst decision</span>
          <span className="flow-arrow">→</span>
          <span className="flow-step">SHA-256 audit</span>
        </div>
      </div>
    </section>
  );
};
