import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { ApiService, DashboardAnalytics } from "../api";

export default function AnalyticsPage({ api }: { api: ApiService }) {
  const [data, setData] = useState<DashboardAnalytics | null>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getDashboardAnalytics(days);
      setData(res);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || "Unable to load analytics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days]);

  if (loading) {
    return (
      <section className="intel-page">
        <div className="page-head"><h2>Analytics</h2></div>
        <div className="kpi-grid">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="kpi-card"><div className="skeleton" style={{ height: 18, width: "60%" }} /></div>
          ))}
        </div>
        <div className="panel"><div className="skeleton" style={{ height: 160 }} /></div>
      </section>
    );
  }

  if (error) {
    return (
      <div className="error-state">
        <h3>Unable to load analytics</h3>
        <p>{error}</p>
        <button className="btn btn-primary" onClick={load}>Retry</button>
      </div>
    );
  }

  if (!data) return <div className="empty-state">No analytics data — not enough transactions.</div>;

  const fmtAmt = (v: string | number) => {
    const n = typeof v === "string" ? parseFloat(v) : v;
    return isNaN(n) ? "—" : `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  };

  return (
    <section className="intel-page">
      <div className="page-head">
        <div>
          <h2>Analytics <span className="badge badge-neutral">Synthetic Demo Data</span></h2>
          <p className="muted">Backend-derived fraud intelligence — transaction volume, risk distribution, case and alert trends, all calculated from PostgreSQL via RuleEngine.</p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {[7, 30, 90].map((d) => (
            <button key={d} className={`btn btn-sm ${days === d ? "btn-primary" : "btn-ghost"}`} onClick={() => setDays(d)}>{d}D</button>
          ))}
        </div>
      </div>

      <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
        <div className="kpi-card" style={{ cursor: "default" }}><div className="kpi-value">{data.overview.total_transactions}</div><div className="kpi-label">Transactions</div><div className="kpi-hint">{fmtAmt(data.overview.total_transaction_value)}</div></div>
        <div className="kpi-card tone-critical" style={{ cursor: "default" }}><div className="kpi-value">{data.overview.high_risk_transactions + data.overview.critical_risk_transactions}</div><div className="kpi-label">High Risk</div></div>
        <div className="kpi-card" style={{ cursor: "default" }}><div className="kpi-value">{data.overview.total_cases}</div><div className="kpi-label">Cases</div></div>
        <div className="kpi-card" style={{ cursor: "default" }}><div className="kpi-value">{data.overview.blocked_transactions}</div><div className="kpi-label">Blocked</div></div>
      </div>

      <div className="dashboard-grid">
        <div className="panel">
          <h3>Risk Distribution</h3>
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

      <div className="panel">
        <h3>Transaction Trend ({days}D)</h3>
        <div className="table-wrap">
          <table className="cases-table" style={{ minWidth: 400 }}>
            <thead><tr><th>Date</th><th>Count</th><th>Value</th><th>High Risk</th><th>Blocked</th></tr></thead>
            <tbody>
              {data.transaction_trend.slice(-7).map((r) => (
                <tr key={r.date}><td>{r.date}</td><td>{r.transaction_count}</td><td>{fmtAmt(r.transaction_value)}</td><td>{r.high_risk_count}</td><td>{r.blocked_count}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <h3>Case Trend</h3>
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
      </div>

      <div className="panel">
        <h3>Top Triggered Rules</h3>
        {data.top_triggered_rules.length === 0 ? <div className="empty-state">No rules triggered in window</div> : (
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

      <div className="panel">
        <h3>Risk Concentration</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16, marginTop: 12 }}>
          <div>
            <h4 style={{ fontSize: ".82rem", margin: "0 0 8px 0" }}>Customers</h4>
            {data.risk_concentration.customers.length === 0 ? <div className="empty-state">No data</div> : (
              <ul className="activity-list">
                {data.risk_concentration.customers.slice(0, 5).map((c) => (
                  <li key={c.id} className="activity-item">
                    <Link to={`/customers/${c.id}`} className="link mono">{c.label.slice(0, 12)}</Link>
                    <span className="muted">{c.high_risk_count} high · {c.transaction_count} txns</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h4 style={{ fontSize: ".82rem", margin: "0 0 8px 0" }}>Merchants</h4>
            {data.risk_concentration.merchants.length === 0 ? <div className="empty-state">No data</div> : (
              <ul className="activity-list">
                {data.risk_concentration.merchants.slice(0, 5).map((m) => (
                  <li key={m.id} className="activity-item">
                    <Link to={`/merchants/${m.id}`} className="link">{m.label.slice(0, 12)}</Link>
                    <span className="muted">{m.high_risk_count} high</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h4 style={{ fontSize: ".82rem", margin: "0 0 8px 0" }}>Devices</h4>
            {data.risk_concentration.devices.length === 0 ? <div className="empty-state">No data</div> : (
              <ul className="activity-list">
                {data.risk_concentration.devices.slice(0, 5).map((d) => (
                  <li key={d.id} className="activity-item">
                    <Link to={`/devices/${d.id}`} className="link mono">{d.label.slice(0, 12)}</Link>
                    <span className="muted">{d.high_risk_count} high</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
