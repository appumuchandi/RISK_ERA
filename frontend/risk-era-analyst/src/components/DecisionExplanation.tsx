import { useEffect, useState } from "react";
import type { ApiService, RiskExplainResponse } from "../api";
import { RiskBadge } from "./intel/IntelShared";

export const DecisionExplanation = ({ api, transactionId }: { api: ApiService; transactionId: string }) => {
  const [data, setData] = useState<RiskExplainResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getTransactionRiskExplanation(transactionId);
      setData(res);
    } catch (e: any) {
      const status = e?.response?.status;
      if (status === 404) setError("Transaction not found");
      else if (status === 401) setError("Authentication required");
      else setError(e instanceof Error ? e.message : "Unable to load explanation");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (transactionId) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [transactionId]);

  if (loading) return <div className="loading-state">Loading decision explanation…</div>;
  if (error) return <div className="error-state"><p>{error}</p><button className="btn btn-primary" onClick={load}>Retry</button></div>;
  if (!data) return <div className="empty-state">No explanation available</div>;

  const sb = data.score_breakdown as Record<string, unknown>;

  return (
    <div className="decision-explanation" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* HEADER: Decision */}
      <div className="panel" style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span className="muted" style={{ fontSize: ".72rem", textTransform: "uppercase", letterSpacing: ".06em" }}>Final Decision</span>
          <span className={`badge rec-${data.decision.toLowerCase()}`} style={{ fontSize: ".82rem", padding: "6px 12px" }}>{data.decision.toUpperCase()}</span>
          <RiskBadge level={data.risk_level} />
          <span className="muted">Score {data.risk_score}</span>
        </div>
        <p className="muted" style={{ margin: "8px 0 0 0", lineHeight: 1.5 }}>{data.decision_reason}</p>
      </div>

      {/* FACTORS */}
      <div className="panel">
        <h4 style={{ margin: "0 0 8px 0", fontSize: ".82rem" }}>Input Factors</h4>
        <div className="kv" style={{ gridTemplateColumns: "140px 1fr" }}>
          <dt>Amount</dt><dd className="mono">{String(data.factors.amount)} {String(data.factors.currency)}</dd>
          <dt>Customer Tier</dt><dd>{String(data.factors.customer_risk_tier)}</dd>
          <dt>KYC Status</dt><dd>{String(data.factors.customer_kyc_status)}</dd>
          <dt>Device Risk</dt><dd className="mono">{String(data.factors.device_risk_score ?? "not available")}</dd>
          <dt>Merchant MCC</dt><dd className="mono">{String(data.factors.merchant_category_code)}</dd>
          <dt>Merchant Risk</dt><dd>{String(data.factors.merchant_risk_level)}</dd>
          <dt>Currency</dt><dd>{String(data.factors.currency)}</dd>
        </div>
        <div style={{ marginTop: 8, fontSize: ".72rem" }} className="muted">Transaction {String(data.provider_event_id).slice(0, 16)} · {String(data.transaction_id).slice(0, 8)}…</div>
      </div>

      {/* TRIGGERED RULES */}
      <div className="panel">
        <h4 style={{ margin: "0 0 8px 0", fontSize: ".82rem" }}>Triggered Rules ({data.triggered_rules.length})</h4>
        {data.triggered_rules.length === 0 ? (
          <div className="empty-state">No configured rule triggered for this transaction. Default decision is ALLOW.</div>
        ) : (
          <ul className="signal-list" style={{ gap: 8 }}>
            {data.triggered_rules.map((r) => (
              <li key={r.rule_id} className="sig-hit" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap", border: "1px solid var(--border)", padding: "8px 10px", borderRadius: 8, background: "var(--bg-secondary)" }}>
                <span><span className={`badge rec-${r.action.toLowerCase()}`}>{r.action.toUpperCase()}</span> <span className="mono" style={{ fontWeight: 600 }}>{r.rule_name}</span> <span className="muted" style={{ fontSize: ".68rem" }}>P{r.priority}</span></span>
                <span className="muted" style={{ fontSize: ".72rem" }}>✓ Matched</span>
                <div style={{ width: "100%", fontSize: ".72rem", color: "var(--text-secondary)", marginTop: 4 }} className="mono">{r.dsl_expression}</div>
                <div style={{ width: "100%", fontSize: ".72rem", color: "var(--text-muted)" }}>{r.explanation}</div>
              </li>
            ))}
          </ul>
        )}
        <h4 style={{ margin: "14px 0 6px 0", fontSize: ".76rem", color: "var(--text-secondary)" }}>Evaluated Rules ({data.evaluated_rules.length})</h4>
        <ul className="signal-list" style={{ gap: 6, maxHeight: 220, overflowY: "auto" }}>
          {data.evaluated_rules.map((r) => (
            <li key={r.rule_id} className={r.matched ? "sig-hit" : "sig-miss"} style={{ fontSize: ".72rem", display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span><span className={`badge ${r.matched ? `rec-${r.action.toLowerCase()}` : "badge-neutral"}`} style={{ fontSize: ".6rem" }}>{r.action.toUpperCase()}</span> {r.rule_name}</span>
              <span>{r.matched ? "✓" : "○"}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* SCORE BREAKDOWN */}
      <div className="panel">
        <h4 style={{ margin: "0 0 8px 0", fontSize: ".82rem" }}>Risk Score Breakdown</h4>
        <div className="kv" style={{ gridTemplateColumns: "160px 1fr" }}>
          <dt>Base Score</dt><dd>{String(sb.base_score ?? "—")}</dd>
          <dt>Amount Factor</dt><dd>{String(sb.amount_factor ?? "—")} (amount {String(sb.amount ?? "")})</dd>
          <dt>Customer Factor</dt><dd>{String(sb.customer_factor ?? "—")} (tier {String(sb.customer_risk_tier ?? "")})</dd>
          <dt>Device Factor</dt><dd>{String(sb.device_factor ?? "—")} (score {String(sb.device_risk_score ?? "null")})</dd>
          <dt>Merchant Factor</dt><dd>{String(sb.merchant_factor ?? "—")} (level {String(sb.merchant_risk_level ?? "")})</dd>
          <dt>Final Score</dt><dd style={{ fontWeight: 800 }}>{String(sb.final_score ?? data.risk_score)} <RiskBadge level={data.risk_level} /></dd>
        </div>
        <p className="muted" style={{ marginTop: 8, fontSize: ".66rem" }}>{String(sb.formula ?? "")}</p>
      </div>

      {/* PRECEDENCE */}
      <div className="panel" style={{ background: "var(--bg-secondary)", textAlign: "center" }}>
        <div className="flow" style={{ justifyContent: "center" }}>
          <span className="flow-step" style={{ background: data.decision.toLowerCase() === "block" ? "var(--accent-red-dim)" : "var(--bg-card)" }}>BLOCK</span>
          <span className="flow-arrow">›</span>
          <span className="flow-step" style={{ background: data.decision.toLowerCase() === "review" ? "var(--accent-amber-dim)" : "var(--bg-card)" }}>REVIEW</span>
          <span className="flow-arrow">›</span>
          <span className="flow-step" style={{ background: data.decision.toLowerCase() === "allow" ? "var(--accent-green-dim)" : "var(--bg-card)" }}>ALLOW</span>
        </div>
        <p className="muted" style={{ marginTop: 8, fontSize: ".72rem" }}>Precedence BLOCK &gt; REVIEW &gt; ALLOW</p>
      </div>
    </div>
  );
};

export default DecisionExplanation;
