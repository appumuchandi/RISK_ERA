import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { ApiService } from "../api";

type Inv = {
  id: string;
  investigation_id: string;
  case_id: string;
  status: string;
  model_provider?: string;
  model_name?: string;
  recommendation?: string;
  confidence?: number;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
};

export default function InvestigationsPage({ api }: { api: ApiService }) {
  const [items, setItems] = useState<Inv[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (p = page) => {
    try {
      setLoading(true);
      setError(null);
      const params: any = { page: p, page_size: 20 };
      if (status) params.status = status;
      const res: any = await (api as any).client.get("/api/v1/investigation", { params }).then((r: any) => r.data);
      setItems(res.items || []);
      setTotal(res.total || 0);
      setPage(res.page || p);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || "Unable to load investigations");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  return (
    <section className="intel-page">
      <div className="page-head">
        <div>
          <h2>Investigations <span className="badge badge-neutral">Live</span></h2>
          <p className="muted">Real investigation records from the Nemotron workbench — every run is persisted with tool trace and audit.</p>
        </div>
        <button className="btn btn-ghost" onClick={() => load(page)}>Refresh</button>
      </div>

      <div className="panel">
        <div className="toolbar">
          <div className="toolbar-group">
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All Status</option>
              <option value="pending">Pending</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
            </select>
          </div>
          <div className="toolbar-group">
            <span className="muted" style={{ fontSize: ".72rem" }}>{total} total</span>
          </div>
        </div>

        {loading ? (
          <div className="loading-state">Loading investigations…</div>
        ) : error ? (
          <div className="error-state"><p>{error}</p><button className="btn btn-primary" onClick={() => load(page)}>Retry</button></div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            <div style={{ fontWeight: 600 }}>No investigations yet</div>
            <p className="muted">Run an investigation from a case to see it here.</p>
            <Link to="/cases" className="btn btn-primary btn-sm" style={{ marginTop: 8 }}>Go to Cases</Link>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="cases-table">
              <thead><tr><th>Investigation</th><th>Case</th><th>Status</th><th>Recommendation</th><th>Model</th><th>Started</th><th>Duration</th><th></th></tr></thead>
              <tbody>
                {items.map((inv) => (
                  <tr key={inv.id} style={{ cursor: "pointer" }} onClick={() => window.location.assign(`/case/${inv.case_id}`)}>
                    <td className="mono">{inv.id.slice(0, 8)}…</td>
                    <td className="mono"><Link to={`/case/${inv.case_id}`} className="link" onClick={(e) => e.stopPropagation()}>{inv.case_id.slice(0, 8)}…</Link></td>
                    <td><span className={`badge ${inv.status === "completed" ? "badge-ok" : inv.status === "failed" ? "badge-bad" : "badge-neutral"}`}>{inv.status}</span></td>
                    <td><span className={`badge rec-${String(inv.recommendation || "").toLowerCase()}`}>{String(inv.recommendation || "—").toUpperCase()}</span></td>
                    <td style={{ fontSize: ".72rem" }}>{inv.model_name || "—"} {inv.model_provider ? `· ${inv.model_provider}` : ""}</td>
                    <td style={{ fontSize: ".72rem", whiteSpace: "nowrap" }}>{inv.started_at ? new Date(inv.started_at).toLocaleDateString() : "—"}</td>
                    <td style={{ fontSize: ".72rem" }}>{inv.duration_ms ? `${inv.duration_ms}ms` : "—"}</td>
                    <td><Link to={`/case/${inv.case_id}`} className="btn btn-ghost btn-sm" onClick={(e) => e.stopPropagation()}>Open Case</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12, alignItems: "center" }}>
          <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => load(page - 1)}>Prev</button>
          <span className="muted" style={{ fontSize: ".76rem" }}>Page {page}</span>
          <button className="btn btn-ghost btn-sm" disabled={items.length < 20} onClick={() => load(page + 1)}>Next</button>
        </div>
      </div>

      <div className="panel">
        <h3>How investigations work</h3>
        <div className="flow" style={{ justifyContent: "center" }}>
          <span className="flow-step">Case</span><span className="flow-arrow">→</span>
          <span className="flow-step">Run Investigation</span><span className="flow-arrow">→</span>
          <span className="flow-step">6 Stages</span><span className="flow-arrow">→</span>
          <span className="flow-step">Tool Trace</span><span className="flow-arrow">→</span>
          <span className="flow-step">Audit</span>
        </div>
        <p className="muted" style={{ marginTop: 8, fontSize: ".72rem" }}>Every investigation is persisted with evidence grounding and hash-chained audit. No fake records.</p>
      </div>
    </section>
  );
}
