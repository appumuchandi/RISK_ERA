import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import type { ApiService, MerchantListItem, MerchantProfile } from "../api";
import { fmtAmt, fmtDate, fmtDay, RiskBadge, StatCard, KV, PageLoading, PageError, CaseChips, RecentTxnsTable, TriggeredRulesPanel } from "../components/intel/IntelShared";

export const MerchantsPage = ({ api }: { api: ApiService }) => {
  const navigate = useNavigate();
  const [items, setItems] = useState<MerchantListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (p = page, q = search) => {
    try {
      setLoading(true); setError(null);
      const res = await api.listMerchants({ page: p, page_size: 20, search: q || undefined });
      setItems(res.items); setTotal(res.total); setTotalPages(res.total_pages ?? Math.ceil(res.total / 20)); setPage(p);
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to load merchants"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(1, ""); }, []);

  if (error) return <PageError title="Merchant Intelligence" message={error} onRetry={() => load(page)} />;

  return (
    <section className="intel-page">
      <div className="page-head">
        <div>
          <h2>Merchant Intelligence <span className="muted">· {total} merchants</span></h2>
          <p className="muted">Volume, block rate, rule triggers and connected customers/devices — synthetic demo data</p>
        </div>
      </div>
      <div className="toolbar">
        <div className="toolbar-group">
          <input placeholder="Search merchant name or MCC" value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load(1, search)} />
          <button className="btn btn-ghost" onClick={() => load(1, search)}>Search</button>
        </div>
      </div>
      {loading ? <PageLoading title="" /> : items.length === 0 ? <div className="empty-state">No merchants found</div> : (
        <div className="table-wrap">
          <table className="cases-table">
            <thead>
              <tr><th>Merchant</th><th>MCC</th><th>Transactions</th><th>Volume</th><th>Risk</th><th>Avg Score</th><th>Customers</th><th>Devices</th><th>Cases</th><th></th></tr>
            </thead>
            <tbody>
              {items.map((m) => (
                <tr key={m.merchant_id} style={{ cursor: "pointer" }} onClick={() => navigate(`/merchants/${m.merchant_id}`)}>
                  <td>{m.name}</td>
                  <td className="mono">{m.category_code}</td>
                  <td>{m.total_transactions}</td>
                  <td>{fmtAmt(m.total_volume)}</td>
                  <td><RiskBadge level={m.risk_level_computed} /></td>
                  <td className="muted">{m.average_risk_score}</td>
                  <td>{m.unique_customers}</td>
                  <td>{m.unique_devices}</td>
                  <td>{m.total_cases}</td>
                  <td><button className="btn btn-ghost btn-sm" onClick={(e) => { e.stopPropagation(); navigate(`/merchants/${m.merchant_id}`); }}>Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12, alignItems: "center" }}>
        <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => load(page - 1)}>Prev</button>
        <span className="muted" style={{ fontSize: ".76rem" }}>Page {totalPages === 0 ? 1 : page} of {Math.max(1, totalPages)}</span>
        <button className="btn btn-ghost btn-sm" disabled={page >= totalPages || items.length < 20} onClick={() => load(page + 1)}>Next</button>
      </div>
    </section>
  );
};

export const MerchantDetailPage = ({ api, id }: { api: ApiService; id: string }) => {
  const navigate = useNavigate();
  const [data, setData] = useState<MerchantProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      setLoading(true); setError(null);
      setData(await api.getMerchantProfile(id));
    } catch (e) {
      const r = (e as { response?: { status?: number } }).response;
      setError(r?.status === 404 ? "Merchant not found" : e instanceof Error ? e.message : "Unable to load merchant");
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [id]);

  if (loading) return <PageLoading title="Merchant Intelligence" />;
  if (error) return <PageError title="Merchant Intelligence" message={error} onRetry={load} />;
  if (!data) return null;

  const distTotal = data.allowed_count + data.review_count + data.blocked_count || 1;
  return (
    <section className="intel-page">
      <div className="page-head">
        <div>
          <h2 style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate("/merchants")}>← Merchants</button>
            {data.name}
            <RiskBadge level={data.risk_level} />
            <span className="badge badge-neutral mono">ECC {data.category_code}</span>
          </h2>
          <p className="muted">Merchant risk profile from transactions, customers, devices and case data</p>
        </div>
      </div>

      <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
        <StatCard label="Transactions" value={data.total_transactions} />
        <StatCard label="Volume" value={fmtAmt(data.total_volume)} />
        <StatCard label="Avg Risk Score" value={data.average_risk_score} hint={`max ${data.max_risk_score}`} tone={data.risk_level === "critical" || data.risk_level === "high" ? "critical" : "low"} />
        <StatCard label="Review / Blocked" value={`${data.review_count} / ${data.blocked_count}`} tone={data.blocked_count > 0 ? "critical" : "medium"} />
        <StatCard label="Cases" value={data.cases.total} tone={data.cases.open > 0 ? "medium" : "low"} />
      </div>

      <div className="case-grid">
        <div className="panel">
          <h3>1 — Merchant Overview</h3>
          <KV rows={[
            ["Merchant", data.name],
            ["Category Code", data.category_code],
            ["Declared Risk", data.risk_level_merchant],
            ["Created", fmtDate(data.created_at)],
          ]} />
        </div>
        <div className="panel">
          <h3>2 — Risk Summary</h3>
          <KV rows={[
            ["Computed Risk Level", <RiskBadge level={data.risk_level} />, false],
            ["Average Risk Score", data.average_risk_score],
            ["Maximum Risk Score", data.max_risk_score],
            ["Declared Level", data.risk_level_merchant],
          ]} />
          <p className="muted" style={{ marginTop: 8, lineHeight: 1.4 }}>{data.risk_explanation}</p>
        </div>
      </div>

      <div className="case-grid">
        <div className="panel">
          <h3>3 — Transaction Volume</h3>
          <KV rows={[
            ["Total Transactions", data.total_transactions],
            ["Total Volume", fmtAmt(data.total_volume)],
            ["Average Amount", fmtAmt(data.average_amount)],
            ["Min Amount", fmtAmt(data.min_amount)],
            ["Max Amount", fmtAmt(data.max_amount)],
            ["First Activity", fmtDate(data.first_activity)],
            ["Last Activity", fmtDate(data.last_activity)],
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
            ["Unique Rules", Object.keys(data.triggered_rule_frequency).length],
          ]} />
          <h4 style={{ margin: "10px 0 6px 0", fontSize: ".76rem", color: "var(--text-secondary)" }}>Top Triggered Rules</h4>
          <TriggeredRulesPanel rules={data.top_triggered_rules} frequency={data.triggered_rule_frequency} />
        </div>
      </div>

      <div className="case-grid">
        <div className="panel">
          <h3>5 — Customer Relationships ({data.unique_customers})</h3>
          {data.recent_customers.length === 0 ? <div className="empty-state">No customers</div> : (
            <ul className="activity-list">
              {data.recent_customers.map((c) => (
                <li key={c.customer_id} className="activity-item">
                  <span className="activity-action"><Link to={`/customers/${c.customer_id}`} className="link mono">{c.external_id}</Link> <span className="muted">· tier {c.risk_tier}</span></span>
                  <span className="activity-ts">{fmtDay(c.last_used)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="panel">
          <h3>6 — Device Relationships ({data.unique_devices})</h3>
          {data.recent_devices.length === 0 ? <div className="empty-state">No devices</div> : (
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
        {data.recent_transactions.length === 0 ? <div className="empty-state">No transactions</div> : <RecentTxnsTable items={data.recent_transactions} />}
      </div>

      <div className="panel">
        <h3>9 — Risk Explanation</h3>
        <p style={{ margin: 0, lineHeight: 1.5 }}>{data.risk_explanation}</p>
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

export default MerchantsPage;
