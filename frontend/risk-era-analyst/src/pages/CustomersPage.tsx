import React, { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import type { ApiService, CustomerListItem, CustomerProfile } from "../api";
import { fmtAmt, fmtDate, fmtDay, RiskBadge, StatCard, KV, PageLoading, PageError, CaseChips, RecentTxnsTable, TriggeredRulesPanel } from "../components/intel/IntelShared";

export const CustomersPage = ({ api }: { api: ApiService }) => (
  <EntityListPage
    title="Customer Intelligence"
    subtitle="Real customer risk profiles derived from transaction, case and rule data — Demo Environment · Synthetic Payment Data"
    searchPlaceholder="Search customer external ID"
    loadList={(params) => api.listCustomers(params)}
    renderRow={(c: CustomerListItem) => ({
      id: c.customer_id,
      cells: [
        <span className="mono" title={c.external_id}>{c.external_id}</span>,
        c.total_transactions,
        fmtAmt(c.total_amount),
        <RiskBadge level={c.risk_level} />,
        <span className="muted">{c.average_risk_score}</span>,
        `${c.unique_merchants} / ${c.unique_devices}`,
        c.total_cases,
      ],
    })}
    headers={["Customer", "Transactions", "Volume", "Risk", "Avg Score", "Merchants / Devices", "Cases"]}
  />
);

export const CustomerDetailPage = ({ api, id }: { api: ApiService; id: string }) => {
  const navigate = useNavigate();
  const [data, setData] = useState<CustomerProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      setLoading(true); setError(null);
      setData(await api.getCustomerProfile(id));
    } catch (e) {
      const msg = (e as { response?: { status?: number; data?: { detail?: string } } })?.response;
      setError(msg?.status === 404 ? "Customer not found" : (e instanceof Error ? e.message : "Unable to load customer"));
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [id]);

  if (loading) return <PageLoading title="Customer Intelligence" />;
  if (error) return <PageError title="Customer Intelligence" message={error} onRetry={load} />;
  if (!data) return null;

  const distTotal = data.allowed_count + data.review_count + data.blocked_count || 1;
  return (
    <section className="intel-page">
      <div className="page-head">
        <div>
          <h2 style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate("/customers")}>← Customers</button>
            <span className="mono">{data.external_id}</span>
            <RiskBadge level={data.risk_level} />
          </h2>
          <p className="muted">Customer risk profile · joined with transactions, rules, cases · synthetic demo data</p>
        </div>
      </div>

      <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
        <StatCard label="Total Transactions" value={data.total_transactions} hint="all time" />
        <StatCard label="Total Volume" value={fmtAmt(data.total_amount)} />
        <StatCard label="Avg Risk Score" value={data.average_risk_score} hint={`max ${data.max_risk_score}`} tone={data.risk_level === "critical" || data.risk_level === "high" ? "critical" : "low"} />
        <StatCard label="Review / Blocked" value={`${data.review_count} / ${data.blocked_count}`} hint={`${data.allowed_count} allowed`} tone={data.blocked_count > 0 ? "critical" : "medium"} />
        <StatCard label="Cases" value={data.cases.total} hint={`${data.cases.open} open`} tone={data.cases.open > 0 ? "medium" : "low"} />
      </div>

      <div className="case-grid">
        <div className="panel">
          <h3>1 — Identity</h3>
          <KV rows={[
            ["Customer ID", data.customer_id, true],
            ["External ID", data.external_id, true],
            ["Risk Tier", data.risk_tier],
            ["KYC Status", data.kyc_status],
            ["Account Created", fmtDate(data.created_at)],
          ]} />
        </div>
        <div className="panel">
          <h3>2 — Risk Summary</h3>
          <KV rows={[
            ["Risk Level", <RiskBadge level={data.risk_level} />, false],
            ["Average Risk Score", data.average_risk_score],
            ["Maximum Risk Score", data.max_risk_score],
            ["Risk Tier (declared)", data.risk_tier],
            ["KYC Status", data.kyc_status],
          ]} />
          <div style={{ marginTop: 8 }} className="muted" title={data.risk_explanation}>{data.risk_explanation.slice(0, 160)}</div>
        </div>
      </div>

      <div className="case-grid">
        <div className="panel">
          <h3>3 — Transaction Statistics</h3>
          <KV rows={[
            ["Total Transactions", data.total_transactions],
            ["Total Amount", fmtAmt(data.total_amount)],
            ["Average Amount", fmtAmt(data.average_amount)],
            ["Min Amount", fmtAmt(data.min_amount)],
            ["Max Amount", fmtAmt(data.max_amount)],
            ["First Transaction", fmtDate(data.first_transaction_at)],
            ["Last Transaction", fmtDate(data.last_transaction_at)],
          ]} />
        </div>
        <div className="panel">
          <h3>4 — Risk Distribution</h3>
          <div className="risk-bars" style={{ marginBottom: 10 }}>
            <div className="risk-row"><span className="risk-label">Allowed</span><div className="risk-bar"><div className="risk-fill low" style={{ width: `${Math.round((data.allowed_count / distTotal) * 100)}%` }} /></div><span className="risk-count">{data.allowed_count}</span></div>
            <div className="risk-row"><span className="risk-label">Review</span><div className="risk-bar"><div className="risk-fill medium" style={{ width: `${Math.round((data.review_count / distTotal) * 100)}%` }} /></div><span className="risk-count">{data.review_count}</span></div>
            <div className="risk-row"><span className="risk-label">Blocked</span><div className="risk-bar"><div className="risk-fill high" style={{ width: `${Math.round((data.blocked_count / distTotal) * 100)}%` }} /></div><span className="risk-count">{data.blocked_count}</span></div>
          </div>
          <KV rows={[
            ["Flagged (status)", data.flagged_count],
            ["Failed (status)", data.failed_count],
            ["Unique Rules Triggered", Object.keys(data.triggered_rule_frequency).length],
          ]} />
          <div style={{ marginTop: 8 }}>
            <TriggeredRulesPanel rules={data.top_triggered_rules} frequency={data.triggered_rule_frequency} />
          </div>
        </div>
      </div>

      <div className="case-grid">
        <div className="panel">
          <h3>5 — Merchant Relationships ({data.unique_merchants})</h3>
          {data.recent_merchants.length === 0 ? <div className="empty-state">No merchants used</div> : (
            <ul className="activity-list">
              {data.recent_merchants.map((m) => (
                <li key={m.merchant_id} className="activity-item">
                  <span className="activity-action"><Link to={`/merchants/${m.merchant_id}`} className="link">{m.name}</Link> <span className="muted">· {m.category_code}</span></span>
                  <span className="activity-ts">{fmtDay(m.last_used)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="panel">
          <h3>6 — Device Relationships ({data.unique_devices})</h3>
          {data.recent_devices.length === 0 ? <div className="empty-state">No devices recorded</div> : (
            <ul className="activity-list">
              {data.recent_devices.map((d) => (
                <li key={d.device_id} className="activity-item">
                  <span className="activity-action"><Link to={`/devices/${d.device_id}`} className="link mono">{d.fingerprint_hash.slice(0, 14)}…</Link> <span className="muted">{d.ip || ""}</span></span>
                  <span className="activity-ts">{fmtDay(d.last_used)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="panel">
        <h3>7 — Cases</h3>
        <CaseChips cases={data.cases} />
        <div className="muted" style={{ marginTop: 6, fontSize: ".72rem" }}>open {data.cases.open} · in_progress {data.cases.in_progress} · escalated {data.cases.escalated} · approved {data.cases.closed_approved} · denied {data.cases.closed_denied}</div>
      </div>

      <div className="panel">
        <h3>8 — Recent Transactions ({data.recent_transactions.length})</h3>
        {data.recent_transactions.length === 0 ? <div className="empty-state">No transactions yet</div> : <RecentTxnsTable items={data.recent_transactions} />}
      </div>

      <div className="panel">
        <h3>9 — Risk Explanation</h3>
        <p style={{ margin: 0, lineHeight: 1.5 }}>{data.risk_explanation}</p>
        <h4 style={{ margin: "10px 0 6px 0", fontSize: ".78rem", color: "var(--text-secondary)" }}>Top Triggered Rules</h4>
        <TriggeredRulesPanel rules={data.top_triggered_rules} frequency={data.triggered_rule_frequency} />
        {data.supporting_transaction_ids.length > 0 && (
          <>
            <h4 style={{ margin: "12px 0 6px 0", fontSize: ".78rem", color: "var(--text-secondary)" }}>Supporting Transaction IDs</h4>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {data.supporting_transaction_ids.map((tid) => (
                <span key={tid} className="mono muted" style={{ fontSize: ".68rem", background: "var(--bg-secondary)", border: "1px solid var(--border)", padding: "2px 6px", borderRadius: 6 }} title={tid}>{tid.slice(0, 8)}…</span>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
};

export default CustomersPage;

type ListRow = { id: string; cells: (string | number | React.ReactElement)[] };
export function EntityListPage<T>({ title, subtitle, searchPlaceholder, loadList, renderRow, headers }: {
  title: string;
  subtitle: string;
  searchPlaceholder: string;
  loadList: (p: Record<string, unknown>) => Promise<{ items: T[]; total: number; total_pages: number }>;
  renderRow: (item: T) => ListRow;
  headers: string[];
}) {
  const navigate = useNavigate();
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (p = page, q = search) => {
    try {
      setLoading(true); setError(null);
      const res = await loadList({ page: p, page_size: 20, search: q || undefined });
      setItems(res.items); setTotal(res.total); setTotalPages(res.total_pages ?? Math.ceil(res.total / 20));
      setPage(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load data");
    } finally { setLoading(false); }
  };
  useEffect(() => { load(1, ""); }, []);

  if (error) return <PageError title={title} message={error} onRetry={() => load(page)} />;

  return (
    <section className="intel-page">
      <div className="page-head">
        <div>
          <h2>{title} <span className="muted">· {total} records</span></h2>
          <p className="muted">{subtitle}</p>
        </div>
      </div>
      <div className="toolbar">
        <div className="toolbar-group">
          <input placeholder={searchPlaceholder} value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load(1, search)} />
          <button className="btn btn-ghost" onClick={() => load(1, search)}>Search</button>
        </div>
      </div>
      {loading ? <PageLoading title="" /> : items.length === 0 ? (
        <div className="empty-state">No results — adjust search or ingest more transactions</div>
      ) : (
        <div className="table-wrap">
          <table className="cases-table">
            <thead><tr>{headers.map((h) => <th key={h}>{h}</th>)}<th></th></tr></thead>
            <tbody>
              {items.map((raw) => {
                const row = renderRow(raw);
                return (
                  <tr key={row.id} style={{ cursor: "pointer" }} onClick={() => navigate(`${window.location.pathname}/${row.id}`)}>
                    {row.cells.map((c, i) => <td key={i}>{c}</td>)}
                    <td><button className="btn btn-ghost btn-sm" onClick={(e) => { e.stopPropagation(); navigate(`${window.location.pathname}/${row.id}`); }}>Open</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12, alignItems: "center" }}>
        <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => load(page - 1)}>Prev</button>
        <span className="muted" style={{ alignSelf: "center", fontSize: ".76rem" }}>Page {totalPages === 0 ? 1 : page} of {Math.max(1, totalPages)}</span>
        <button className="btn btn-ghost btn-sm" disabled={page >= totalPages || items.length < 20} onClick={() => load(page + 1)}>Next</button>
      </div>
    </section>
  );
}
