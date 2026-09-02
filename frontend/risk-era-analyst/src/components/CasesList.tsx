import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { ApiService, CaseItem } from "../api";

export const CasesList = ({ api }: { api: ApiService }) => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = useState<CaseItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [details, setDetails] = useState<Record<string, { amount: string; provider_event_id: string; evidence_count: number }>>({});

  const statusFilter = searchParams.get("status") || "";
  const q = searchParams.get("q") || "";
  const riskFilter = searchParams.get("risk") || "all"; // all | low | medium | high | critical
  const sortBy = searchParams.get("sort") || "recent";

  const [localQ, setLocalQ] = useState(q);

  useEffect(() => setLocalQ(q), [q]);

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const params: Record<string, string | number | undefined> = {};
      if (statusFilter) params.status = statusFilter;
      // backend doesn't have risk filter; we do client side
      const res = await api.getCases(1, 100, params);
      const list: CaseItem[] = (res as unknown as { items: CaseItem[] }).items || [];
      setItems(list);
      setTotal((res as unknown as { total: number }).total ?? list.length);
      // fetch details for risk/amount & evidence_count for display
      const ids = list.slice(0, 30).map((c) => c.id);
      const map: typeof details = {};
      await Promise.all(
        ids.map(async (id) => {
          try {
            const d = await api.getCase(id);
            map[id] = {
              amount: (d.transaction as { amount?: string })?.amount || "0",
              provider_event_id: (d.transaction as { provider_event_id?: string })?.provider_event_id || id.slice(0, 8),
              evidence_count: d.evidence_count ?? 0,
            };
          } catch {
            map[id] = { amount: "0", provider_event_id: id.slice(0, 8), evidence_count: 0 };
          }
        })
      );
      setDetails(map);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unable to connect to RISK-ERA backend");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const filtered = useMemo(() => {
    let out = [...items];
    if (localQ) {
      const needle = localQ.toLowerCase();
      out = out.filter((c) => {
        const d = details[c.id];
        return c.id.toLowerCase().includes(needle) || c.status.toLowerCase().includes(needle) || (d?.provider_event_id || "").toLowerCase().includes(needle);
      });
    }
    if (riskFilter !== "all") {
      out = out.filter((c) => {
        const amt = parseFloat(details[c.id]?.amount || "0");
        if (riskFilter === "critical") return c.status === "escalated" || amt > 30000;
        if (riskFilter === "high") return amt > 10000;
        if (riskFilter === "medium") return amt > 5000 || c.status === "in_progress";
        if (riskFilter === "low") return amt <= 5000 && c.status !== "escalated";
        return true;
      });
    }
    if (sortBy === "risk") {
      out.sort((a, b) => parseFloat(details[b.id]?.amount || "0") - parseFloat(details[a.id]?.amount || "0"));
    } else {
      out.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    }
    return out;
  }, [items, localQ, riskFilter, sortBy, details]);

  const applyQ = () => {
    const p = new URLSearchParams(searchParams);
    if (localQ) p.set("q", localQ);
    else p.delete("q");
    setSearchParams(p, { replace: true });
  };

  if (loading) return <div className="loading-state">Loading risk operations…</div>;
  if (error)
    return (
      <div className="error-state">
        <h3>Unable to connect to RISK-ERA backend</h3>
        <p>{error}</p>
        <button className="btn btn-primary" onClick={load}>Retry</button>
      </div>
    );

  return (
    <section className="cases-page">
      <div className="page-head">
        <h2>Cases <span className="muted">· {total} total · Demo Environment · Synthetic Payment Data</span></h2>
      </div>

      <div className="toolbar">
        <div className="toolbar-group">
          <input placeholder="Search case ID / provider event" value={localQ} onChange={(e) => setLocalQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && applyQ()} />
          <button className="btn btn-ghost" onClick={applyQ}>Search</button>
        </div>
        <div className="toolbar-group">
          <select value={statusFilter} onChange={(e) => { const p = new URLSearchParams(searchParams); if (e.target.value) p.set("status", e.target.value); else p.delete("status"); setSearchParams(p); }}>
            <option value="">All statuses</option>
            <option value="open">Open</option>
            <option value="in_progress">In Progress</option>
            <option value="escalated">Escalated</option>
            <option value="closed_approved">Closed Approved</option>
            <option value="closed_denied">Closed Denied</option>
          </select>
          <select value={riskFilter} onChange={(e) => { const p = new URLSearchParams(searchParams); p.set("risk", e.target.value); setSearchParams(p); }}>
            <option value="all">All risk</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <select value={sortBy} onChange={(e) => { const p = new URLSearchParams(searchParams); p.set("sort", e.target.value); setSearchParams(p); }}>
            <option value="recent">Sort: Recent</option>
            <option value="risk">Sort: Risk</option>
          </select>
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="empty-state">No cases available — run <code>python seed_demo_data.py</code> to populate demo data</div>
      ) : (
        <div className="table-wrap">
          <table className="cases-table">
            <thead>
              <tr>
                <th>Case ID</th>
                <th>Transaction</th>
                <th>Amount</th>
                <th>Risk</th>
                <th>Status</th>
                <th>AI</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => {
                const d = details[c.id];
                const amt = d ? parseFloat(d.amount) : 0;
                const risk: string = c.status === "escalated" || amt > 30000 ? "Critical" : amt > 10000 ? "High" : amt > 5000 ? "Medium" : "Low";
                const evidenceNote = d ? `${d.evidence_count} evidence` : "—";
                return (
                  <tr key={c.id} className={`row-risk-${risk.toLowerCase()}`} onClick={() => navigate(`/case/${c.id}`)} style={{ cursor: "pointer" }}>
                    <td className="mono">{c.id.slice(0, 8)}</td>
                    <td className="mono">{d?.provider_event_id?.slice(0, 12) || c.transaction_id.slice(0, 8)}</td>
                    <td>₹{amt.toLocaleString("en-IN")}</td>
                    <td><span className={`badge risk-${risk.toLowerCase()}`}>{risk}</span></td>
                    <td><span className={`badge status-${c.status}`}>{c.status}</span></td>
                    <td><span className="muted">{evidenceNote}</span></td>
                    <td>{new Date(c.created_at).toLocaleDateString()}</td>
                    <td><button className="btn btn-primary btn-sm" onClick={(e) => { e.stopPropagation(); navigate(`/case/${c.id}`); }}>Open</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};
