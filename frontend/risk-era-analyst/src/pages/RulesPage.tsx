import { useEffect, useState } from "react";
import type { ApiService, RuleDetail } from "../api";
import { PageLoading, PageError } from "../components/intel/IntelShared";

export default function RulesPage({ api }: { api: ApiService }) {
  const [items, setItems] = useState<RuleDetail[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [action, setAction] = useState<string>("");
  const [enabled, setEnabled] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<RuleDetail | null>(null);
  const [summary, setSummary] = useState<{ total: number; enabled: number; block: number; review: number; allow: number } | null>(null);

  const load = async (p = page) => {
    try {
      setLoading(true);
      setError(null);
      const params: Record<string, unknown> = { page: p, page_size: 20 };
      if (search) params.search = search;
      if (action) params.action = action;
      if (enabled !== "") params.enabled = enabled === "true";
      const res = await api.getRules(params);
      setItems(res.items);
      setTotal(res.total);
      setPage(res.page);
      // summary: fetch all with large page to compute (since total small)
      if (!summary || p === 1) {
        try {
          const all = await api.getRules({ page: 1, page_size: 100 });
          const s = { total: all.total, enabled: 0, block: 0, review: 0, allow: 0 };
          all.items.forEach((r: RuleDetail) => {
            if (r.enabled) s.enabled += 1;
            if (r.action.toLowerCase() === "block") s.block += 1;
            else if (r.action.toLowerCase() === "review") s.review += 1;
            else s.allow += 1;
          });
          setSummary(s);
        } catch {}
      }
    } catch (e: any) {
      const status = e?.response?.status;
      if (status === 401) setError("Authentication required");
      else setError(e instanceof Error ? e.message : "Unable to load rules");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onSearch = () => load(1);

  if (loading && items.length === 0) return <PageLoading title="Rules & Decision Transparency" />;
  if (error) return <PageError title="Rules & Decision Transparency" message={error} onRetry={() => load(page)} />;

  return (
    <section className="intel-page">
      <div className="page-head">
        <div>
          <h2>Rules & Decision Transparency <span className="badge badge-neutral">Phase 6</span></h2>
          <p className="muted">Inspect the rules responsible for transaction decisions — every decision is explained via the single RuleEngine source of truth. No fabricated risk.</p>
        </div>
      </div>

      {/* Summary */}
      {summary && (
        <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}>
          <div className="kpi-card" style={{ cursor: "default" }}><div className="kpi-value">{summary.total}</div><div className="kpi-label">Total Rules</div></div>
          <div className="kpi-card tone-low" style={{ cursor: "default" }}><div className="kpi-value">{summary.enabled}</div><div className="kpi-label">Enabled</div></div>
          <div className="kpi-card tone-critical" style={{ cursor: "default" }}><div className="kpi-value">{summary.block}</div><div className="kpi-label">BLOCK</div></div>
          <div className="kpi-card tone-medium" style={{ cursor: "default" }}><div className="kpi-value">{summary.review}</div><div className="kpi-label">REVIEW</div></div>
          <div className="kpi-card tone-low" style={{ cursor: "default" }}><div className="kpi-value">{summary.allow}</div><div className="kpi-label">ALLOW</div></div>
        </div>
      )}

      <div className="panel">
        <h3>Rule Table</h3>
        <div className="toolbar">
          <div className="toolbar-group">
            <input placeholder="Search rule name or condition" value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && onSearch()} />
            <button className="btn btn-ghost" onClick={onSearch}>Search</button>
          </div>
          <div className="toolbar-group">
            <select value={action} onChange={(e) => { const v = e.target.value; setAction(v); load(1); }}>
              <option value="">All Actions</option>
              <option value="block">BLOCK</option>
              <option value="review">REVIEW</option>
              <option value="allow">ALLOW</option>
            </select>
            <select value={enabled} onChange={(e) => { const v = e.target.value; setEnabled(v); load(1); }}>
              <option value="">All Status</option>
              <option value="true">Enabled</option>
              <option value="false">Disabled</option>
            </select>
          </div>
        </div>

        {items.length === 0 ? (
          <div className="empty-state">No rules found — adjust filters or seed rules.</div>
        ) : (
          <div className="table-wrap">
            <table className="cases-table">
              <thead><tr><th>Rule</th><th>Action</th><th>Priority</th><th>Status</th><th>Condition</th><th></th></tr></thead>
              <tbody>
                {items.map((r) => (
                  <tr key={r.id} style={{ cursor: "pointer" }} onClick={() => setSelected(r)}>
                    <td><span className="mono" style={{ fontWeight: 600 }}>{r.name}</span><br /><span className="muted" style={{ fontSize: ".68rem" }}>{r.id.slice(0, 8)}…</span></td>
                    <td><span className={`badge rec-${r.action.toLowerCase()}`}>{r.action.toUpperCase()}</span></td>
                    <td>{r.priority}</td>
                    <td>{r.enabled ? <span className="badge badge-ok">Enabled</span> : <span className="badge badge-neutral">Disabled</span>}</td>
                    <td className="mono" style={{ maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.condition}>{r.condition}</td>
                    <td><button className="btn btn-ghost btn-sm" onClick={(e) => { e.stopPropagation(); setSelected(r); }}>View</button></td>
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
        <div className="panel" style={{ borderColor: "var(--accent-blue)", background: "var(--bg-elevated)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <h3 style={{ margin: 0 }}>Rule Detail — <span className="mono">{selected.name}</span></h3>
            <button className="btn btn-ghost btn-sm" onClick={() => setSelected(null)}>Close</button>
          </div>
          <div className="kv" style={{ marginTop: 12 }}>
            <dt>Name</dt><dd className="mono">{selected.name}</dd>
            <dt>Description</dt><dd>{selected.description || "— (no description stored, see condition)"}</dd>
            <dt>Action</dt><dd><span className={`badge rec-${selected.action.toLowerCase()}`}>{selected.action.toUpperCase()}</span></dd>
            <dt>Priority</dt><dd>{selected.priority}</dd>
            <dt>Status</dt><dd>{selected.enabled ? "Enabled" : "Disabled"}</dd>
            <dt>Condition</dt><dd className="mono" style={{ background: "var(--bg-secondary)", padding: "6px 8px", borderRadius: 6, border: "1px solid var(--border)" }}>{selected.condition}</dd>
            <dt>Created</dt><dd>{selected.created_at ? new Date(selected.created_at).toLocaleString() : "—"}</dd>
            <dt>Version</dt><dd>{selected.version}</dd>
            <dt>ID</dt><dd className="mono">{selected.id}</dd>
          </div>
          <p className="muted" style={{ marginTop: 10, fontSize: ".72rem" }}>This rule is evaluated by the single RuleEngine source of truth. Priority {selected.priority} determines evaluation order, action precedence BLOCK &gt; REVIEW &gt; ALLOW determines final decision.</p>
        </div>
      )}

      <div className="panel">
        <h3>Decision Transparency — How it works</h3>
        <div className="flow" style={{ justifyContent: "center" }}>
          <span className="flow-step">Factors</span>
          <span className="flow-arrow">→</span>
          <span className="flow-step">Rule Evaluation</span>
          <span className="flow-arrow">→</span>
          <span className="flow-step">Risk Score</span>
          <span className="flow-arrow">→</span>
          <span className="flow-step">Final Decision</span>
        </div>
        <p className="muted" style={{ marginTop: 8 }}>Use "Why this decision?" on any transaction to see the exact triggered rules and precedence reasoning.</p>
      </div>
    </section>
  );
}
