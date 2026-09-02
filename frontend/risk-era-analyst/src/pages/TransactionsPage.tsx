import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { ApiService, TransactionListItem } from "../api";
import { RiskBadge } from "../components/intel/IntelShared";
import DecisionExplanation from "../components/DecisionExplanation";

export default function TransactionsPage({ api }: { api: ApiService }) {
  const [items, setItems] = useState<TransactionListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [risk, setRisk] = useState("");
  const [decision, setDecision] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortOrder, setSortOrder] = useState("desc");
  const [selected, setSelected] = useState<TransactionListItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (p = page) => {
    try {
      setLoading(true);
      setError(null);
      const params: any = { page: p, page_size: 20, sort_by: sortBy, sort_order: sortOrder };
      if (search) params.search = search;
      if (risk) params.risk = risk;
      if (decision) params.status = decision; // decision maps to status for demo
      const res = await api.getTransactions(params);
      setItems(res.items);
      setTotal(res.total);
      setPage(res.page);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || "Unable to load transactions");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [risk, decision, sortBy, sortOrder]);

  return (
    <section className="intel-page">
      <div className="page-head">
        <div>
          <h2>Transaction Intelligence <span className="badge badge-neutral">Live</span></h2>
          <p className="muted">Search, filter and understand transaction risk — every row is a real PostgreSQL transaction with RuleEngine risk.</p>
        </div>
        <button className="btn btn-ghost" onClick={() => load(1)}>Refresh</button>
      </div>

      <div className="panel">
        <div className="toolbar">
          <div className="toolbar-group" style={{ flex: "2 1 280px" }}>
            <input placeholder="Search provider event" value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load(1)} />
            <button className="btn btn-ghost" onClick={() => load(1)}>Search</button>
          </div>
          <div className="toolbar-group">
            <select value={risk} onChange={(e) => setRisk(e.target.value)}>
              <option value="">All Risk</option>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
            <select value={decision} onChange={(e) => setDecision(e.target.value)}>
              <option value="">All Status</option>
              <option value="flagged">Flagged</option>
              <option value="failed">Failed</option>
              <option value="authorized">Authorized</option>
            </select>
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
              <option value="created_at">Date</option>
              <option value="amount">Amount</option>
              <option value="risk_score">Risk</option>
            </select>
            <select value={sortOrder} onChange={(e) => setSortOrder(e.target.value)}>
              <option value="desc">Desc</option>
              <option value="asc">Asc</option>
            </select>
          </div>
        </div>

        {loading ? (
          <div className="loading-state">Loading transactions…</div>
        ) : error ? (
          <div className="error-state"><p>{error}</p><button className="btn btn-primary" onClick={() => load(page)}>Retry</button></div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            <div style={{ fontWeight: 600 }}>No transactions found</div>
            <p className="muted">We couldn't find transactions matching your current filters.</p>
            <button className="btn btn-ghost btn-sm" onClick={() => { setSearch(""); setRisk(""); setDecision(""); load(1); }}>Clear Filters</button>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="cases-table">
              <thead><tr><th>Provider Event</th><th>Amount</th><th>Customer</th><th>Merchant</th><th>Risk</th><th>Decision</th><th>Case</th><th>Date</th><th></th></tr></thead>
              <tbody>
                {items.map((t) => (
                  <tr key={t.id} style={{ cursor: "pointer" }} onClick={() => setSelected(t)}>
                    <td className="mono">{t.provider_event_id.slice(0, 12)}…</td>
                    <td>₹{parseFloat(t.amount).toLocaleString("en-IN")} <span className="muted" style={{ fontSize: ".68rem" }}>{t.currency}</span></td>
                    <td className="mono">{t.customer_external_id ? <Link to={`/customers/${t.customer_id}`} className="link" onClick={(e) => e.stopPropagation()}>{t.customer_external_id.slice(0, 10)}</Link> : t.customer_id.slice(0, 8)}</td>
                    <td>{t.merchant_name ? <Link to={`/merchants/${t.merchant_id}`} className="link" onClick={(e) => e.stopPropagation()}>{t.merchant_name}</Link> : t.merchant_id.slice(0, 8)}</td>
                    <td><RiskBadge level={t.risk_level} /> <span className="muted" style={{ fontSize: ".68rem" }}>{t.risk_score}</span></td>
                    <td><span className={`badge rec-${t.decision.toLowerCase()}`}>{t.decision.toUpperCase()}</span></td>
                    <td>{t.has_case && t.case_id ? <Link to={`/case/${t.case_id}`} className="link" onClick={(e) => e.stopPropagation()}>Case</Link> : <span className="muted">—</span>}</td>
                    <td style={{ fontSize: ".72rem", whiteSpace: "nowrap" }}>{new Date(t.created_at).toLocaleDateString()}</td>
                    <td><button className="btn btn-ghost btn-sm" onClick={(e) => { e.stopPropagation(); setSelected(t); }}>View</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12, alignItems: "center" }}>
          <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => load(page - 1)}>Prev</button>
          <span className="muted" style={{ fontSize: ".76rem" }}>Page {page} — {total} total</span>
          <button className="btn btn-ghost btn-sm" disabled={items.length < 20} onClick={() => load(page + 1)}>Next</button>
        </div>
      </div>

      {selected && (
        <div className="panel" style={{ borderColor: "var(--accent-primary)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <h3 style={{ margin: 0 }}>Transaction Detail — <span className="mono">{selected.provider_event_id}</span> <RiskBadge level={selected.risk_level} /></h3>
            <button className="btn btn-ghost btn-sm" onClick={() => setSelected(null)}>Close</button>
          </div>
          <div className="case-grid" style={{ marginTop: 12 }}>
            <div className="panel" style={{ background: "var(--bg-elevated)" }}>
              <h4 style={{ margin: "0 0 8px 0", fontSize: ".82rem" }}>Transaction</h4>
              <div className="kv">
                <dt>ID</dt><dd className="mono">{selected.id}</dd>
                <dt>Provider Event</dt><dd className="mono">{selected.provider_event_id}</dd>
                <dt>Amount</dt><dd>₹{selected.amount} {selected.currency}</dd>
                <dt>Status</dt><dd>{selected.status}</dd>
                <dt>Created</dt><dd>{new Date(selected.created_at).toLocaleString()}</dd>
              </div>
            </div>
            <div className="panel" style={{ background: "var(--bg-elevated)" }}>
              <h4 style={{ margin: "0 0 8px 0", fontSize: ".82rem" }}>Entities</h4>
              <div className="kv">
                <dt>Customer</dt><dd><Link to={`/customers/${selected.customer_id}`} className="link mono">{selected.customer_external_id || selected.customer_id.slice(0, 8)}</Link></dd>
                <dt>Merchant</dt><dd><Link to={`/merchants/${selected.merchant_id}`} className="link">{selected.merchant_name || selected.merchant_id.slice(0, 8)}</Link></dd>
                <dt>Device</dt><dd>{selected.device_id ? <Link to={`/devices/${selected.device_id}`} className="link mono">{selected.device_id.slice(0, 8)}…</Link> : "—"}</dd>
                <dt>Case</dt><dd>{selected.has_case && selected.case_id ? <Link to={`/case/${selected.case_id}`} className="link">Open Case</Link> : "No case"}</dd>
              </div>
            </div>
          </div>
          <div style={{ marginTop: 12 }}>
            <h4 style={{ margin: "0 0 8px 0", fontSize: ".82rem" }}>Why was this transaction flagged?</h4>
            <DecisionExplanation api={api} transactionId={selected.id} />
          </div>
        </div>
      )}
    </section>
  );
}
