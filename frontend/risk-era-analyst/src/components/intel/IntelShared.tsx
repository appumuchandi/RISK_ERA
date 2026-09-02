import type { ReactNode } from "react";
import { Link } from "react-router-dom";

export const fmtAmt = (v: string | number | null | undefined, cur = "₹") => {
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${cur}${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
};

export const fmtDate = (s?: string | null) => (s ? new Date(s).toLocaleString() : "—");
export const fmtDay = (s?: string | null) => (s ? new Date(s).toLocaleDateString() : "—");

export const RiskBadge = ({ level }: { level?: string | null }) => (
  <span className={`badge risk-${(level || "low").toLowerCase()}`}>{(level || "low").toUpperCase()}</span>
);

export const DecisionBadge = ({ decision }: { decision?: string | null }) => {
  const d = (decision || "allow").toLowerCase();
  return <span className={`badge rec-${d}`}>{d.toUpperCase()}</span>;
};

export const StatCard = ({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: string; tone?: string }) => (
  <div className={`kpi-card ${tone ? `tone-${tone}` : ""}`} style={{ cursor: "default" }}>
    <div className="kpi-value">{value}</div>
    <div className="kpi-label">{label}</div>
    {hint && <div className="kpi-hint">{hint}</div>}
  </div>
);

export const KV = ({ rows }: { rows: Array<[string, ReactNode, boolean?]> }) => (
  <dl className="kv">
    {rows.map(([k, v, mono], i) => (
      <span key={i} style={{ display: "contents" }}>
        <dt>{k}</dt>
        <dd className={mono ? "mono" : ""}>{v}</dd>
      </span>
    ))}
  </dl>
);

export const PageLoading = ({ title }: { title: string }) => (
  <section>
    <div className="page-head"><h2>{title}</h2></div>
    <div className="panel"><div className="skeleton-grid">
      <div className="skeleton" style={{ height: 18, width: "45%" }} />
      <div className="skeleton" style={{ height: 18, width: "70%" }} />
      <div className="skeleton" style={{ height: 18, width: "55%" }} />
    </div></div>
  </section>
);

export const PageError = ({ title, message, onRetry }: { title: string; message: string; onRetry: () => void }) => (
  <section>
    <div className="page-head"><h2>{title}</h2></div>
    <div className="error-state">
      <h3>Unable to load {title.toLowerCase()} data</h3>
      <p>{message}</p>
      <button className="btn btn-primary" onClick={onRetry}>Retry</button>
    </div>
  </section>
);

export const CaseChips = ({ cases }: { cases: { total: number; open: number; in_progress: number; escalated: number; closed_approved: number; closed_denied: number } }) => (
  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
    <span className="badge badge-neutral">{cases.total} total</span>
    {cases.open > 0 && <span className="badge status-open">{cases.open} open</span>}
    {cases.in_progress > 0 && <span className="badge status-in_progress">{cases.in_progress} in progress</span>}
    {cases.escalated > 0 && <span className="badge status-escalated">{cases.escalated} escalated</span>}
    {cases.closed_approved > 0 && <span className="badge badge-ok">{cases.closed_approved} approved</span>}
    {cases.closed_denied > 0 && <span className="badge badge-bad">{cases.closed_denied} denied</span>}
    {cases.total === 0 && <span className="muted">No linked cases</span>}
  </div>
);

type RecentTxn = {
  id: string; provider_event_id: string; amount: string; currency: string; status: string;
  merchant_name: string | null; merchant_id: string; device_id: string | null;
  risk_score: number; risk_level: string; decision: string; triggered_rules: string[];
  created_at: string; has_case: boolean; case_id: string | null;
};

export const RecentTxnsTable = ({ items }: { items: RecentTxn[]; linkTxn?: boolean }) => (
  <div className="table-wrap">
    <table className="cases-table">
      <thead>
        <tr>
          <th>Transaction</th><th>Amount</th><th>Merchant</th><th>Risk</th><th>Decision</th><th>Rules</th><th>When</th><th></th>
        </tr>
      </thead>
      <tbody>
        {items.map((t) => (
          <tr key={t.id}>
            <td className="mono" title={t.provider_event_id}>{t.provider_event_id.slice(0, 16)}</td>
            <td>{fmtAmt(t.amount, t.currency === "INR" ? "₹" : `${t.currency} `)}</td>
            <td>
              {t.merchant_name ? <Link to={`/merchants/${t.merchant_id}`} className="link">{t.merchant_name}</Link> : "—"}
            </td>
            <td><RiskBadge level={t.risk_level} /> <span className="muted" style={{ fontSize: ".72rem" }}>{t.risk_score}</span></td>
            <td><DecisionBadge decision={t.decision} /></td>
            <td className="muted" style={{ fontSize: ".74rem", maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis" }} title={t.triggered_rules.join(", ")}>
              {t.triggered_rules.length ? t.triggered_rules.slice(0, 2).join(", ") + (t.triggered_rules.length > 2 ? ` +${t.triggered_rules.length - 2}` : "") : "—"}
            </td>
            <td style={{ whiteSpace: "nowrap" }}>{fmtDay(t.created_at)}</td>
            <td>{t.has_case && t.case_id && <Link to={`/case/${t.case_id}`} className="btn btn-ghost btn-sm">Case</Link>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export const TriggeredRulesPanel = ({ rules }: { rules: Array<{ rule_name: string; count: number; action: string; example_transaction_id: string | null }>; frequency: Record<string, number> }) => (
  <div>
    {rules.length === 0 ? (
      <div className="empty-state">No rules triggered across associated transactions</div>
    ) : (
      <ul className="signal-list" style={{ gap: 8 }}>
        {rules.map((r) => (
          <li key={r.rule_name} className="sig-hit" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span>
              <span className="mono">{r.rule_name}</span>{" "}
              <DecisionBadge decision={r.action} />
            </span>
            <span className="badge badge-neutral">×{freqLbl(r.count)}</span>
          </li>
        ))}
      </ul>
    )}
  </div>
);

const freqLbl = (n: number) => `${n} trigger${n === 1 ? "" : "s"}`;
