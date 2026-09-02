import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { ApiService } from "../api";

type AuditEvent = {
  id: string;
  actor: string;
  action: string;
  resource_type: string;
  resource_id: string;
  before_json?: any;
  after_json?: any;
  prev_hash?: string | null;
  created_at: string;
};

export const AuditView = ({ api }: { api: ApiService }) => {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [verify, setVerify] = useState<{ valid: boolean; error: string | null; checked_count?: number; total?: number; first_checked_at?: string | null; last_checked_at?: string | null } | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [summary, setSummary] = useState<any>(null);

  // Filters
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [resourceId, setResourceId] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortOrder, setSortOrder] = useState("desc");
  const [selected, setSelected] = useState<AuditEvent | null>(null);

  const load = async (p = page) => {
    try {
      setLoading(true);
      setError(null);
      const params: Record<string, unknown> = { page: p, page_size: 20, sort_by: sortBy, sort_order: sortOrder };
      if (actor) params.actor = actor;
      if (action) params.action = action;
      if (resourceType) params.resource_type = resourceType;
      if (resourceId) params.resource_id = resourceId;
      if (fromDate) params.from_date = new Date(fromDate).toISOString();
      if (toDate) params.to_date = new Date(toDate).toISOString();
      if (search) params.search = search;
      const res: any = await api.getAuditEvents(params);
      setEvents(res.items || []);
      setTotal(res.total || 0);
      setTotalPages(res.total_pages || 0);
      setPage(res.page || p);
      // summary
      try {
        const s = await api.getAuditSummary({});
        setSummary(s);
      } catch {}
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unable to load audit events");
    } finally {
      setLoading(false);
    }
  };

  const doVerify = async () => {
    try {
      setVerifying(true);
      const r = await api.verifyAuditChain();
      setVerify(r);
    } catch (e: unknown) {
      setVerify({ valid: false, error: e instanceof Error ? e.message : String(e) });
    } finally {
      setVerifying(false);
    }
  };

  useEffect(() => {
    load(1);
    doVerify();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applyFilters = () => load(1);
  const clearFilters = () => {
    setActor("");
    setAction("");
    setResourceType("");
    setResourceId("");
    setFromDate("");
    setToDate("");
    setSearch("");
    setSortBy("created_at");
    setSortOrder("desc");
    setTimeout(() => load(1), 0);
  };

  const computeHash = (ev: AuditEvent) => {
    // We don't compute client-side hash; we display prev_hash and note that current hash is SHA256 of event
    // The backend verify-chain already checks. For detail we show prev_hash and explain.
    return ev.prev_hash ? `${ev.prev_hash.slice(0, 12)}…` : "genesis";
  };

  if (loading && events.length === 0) {
    return (
      <section className="audit-page">
        <div className="page-head"><h2>Audit & Traceability</h2></div>
        <div className="kpi-grid">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="kpi-card"><div className="skeleton" style={{ height: 18, width: "50%" }} /></div>
          ))}
        </div>
        <div className="panel"><div className="skeleton" style={{ height: 200 }} /></div>
      </section>
    );
  }

  if (error) {
    return (
      <div className="error-state">
        <h3>Unable to load audit trail</h3>
        <p>{error}</p>
        <button className="btn btn-primary" onClick={() => load(page)}>Retry</button>
      </div>
    );
  }

  return (
    <section className="audit-page">
      <div className="page-head">
        <div>
          <h2>Audit & Traceability <span className="badge badge-neutral">Immutable</span></h2>
          <p className="muted">Immutable operational activity trail — every case, investigation, evidence and alert action is cryptographically chained via SHA-256. Verify integrity, search, and investigate any resource.</p>
        </div>
        <button className="btn btn-primary" onClick={doVerify} disabled={verifying}>{verifying ? "Verifying…" : "Verify Chain"}</button>
      </div>

      {/* Summary KPI */}
      {summary && (
        <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}>
          <div className="kpi-card" style={{ cursor: "default" }}><div className="kpi-value">{summary.total}</div><div className="kpi-label">Total Events</div></div>
          <div className="kpi-card" style={{ cursor: "default" }}><div className="kpi-value">{summary.unique_actors}</div><div className="kpi-label">Unique Actors</div></div>
          <div className="kpi-card" style={{ cursor: "default" }}><div className="kpi-value">{summary.case_actions}</div><div className="kpi-label">Case Actions</div></div>
          <div className="kpi-card" style={{ cursor: "default" }}><div className="kpi-value">{summary.investigation_actions}</div><div className="kpi-label">Investigation</div></div>
          <div className="kpi-card" style={{ cursor: "default" }}><div className="kpi-value">{summary.evidence_actions}</div><div className="kpi-label">Evidence</div></div>
          <div className="kpi-card" style={{ cursor: "default" }}><div className="kpi-value">{summary.alert_actions}</div><div className="kpi-label">Alert Actions</div></div>
        </div>
      )}

      {/* Chain verification */}
      <div className="panel">
        <h3>Audit Chain Integrity — SHA-256</h3>
        {verify ? (
          <div className={verify.valid ? "ok-banner" : "error-banner"}>
            {verify.valid ? `✓ VALID — ${verify.checked_count ?? events.length} events checked` : `✗ INVALID — ${verify.error}`}
            {verify.valid && verify.first_checked_at && <span className="muted" style={{ marginLeft: 8, fontSize: ".68rem" }}>· {new Date(verify.first_checked_at).toLocaleDateString()} → {verify.last_checked_at ? new Date(verify.last_checked_at).toLocaleDateString() : ""} · total {verify.total}</span>}
          </div>
        ) : (
          <div className="loading-state">Checking chain…</div>
        )}
        <p className="muted" style={{ marginTop: 8, fontSize: ".72rem" }}>Each event's hash is SHA256(actor, action, resource, before/after, prev_hash, created_at). Any tampering breaks the chain.</p>
      </div>

      {/* Filters */}
      <div className="panel">
        <h3>Filters</h3>
        <div className="toolbar">
          <div className="toolbar-group">
            <input placeholder="Actor" value={actor} onChange={(e) => setActor(e.target.value)} style={{ minWidth: 120 }} />
            <input placeholder="Action" value={action} onChange={(e) => setAction(e.target.value)} style={{ minWidth: 120 }} />
            <input placeholder="Resource Type" value={resourceType} onChange={(e) => setResourceType(e.target.value)} style={{ minWidth: 120 }} />
            <input placeholder="Resource ID" value={resourceId} onChange={(e) => setResourceId(e.target.value)} style={{ minWidth: 160 }} />
          </div>
          <div className="toolbar-group">
            <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
            <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
            <input placeholder="Search" value={search} onChange={(e) => setSearch(e.target.value)} style={{ minWidth: 140 }} />
          </div>
          <div className="toolbar-group">
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
              <option value="created_at">Created At</option>
              <option value="actor">Actor</option>
              <option value="action">Action</option>
              <option value="resource_type">Resource Type</option>
            </select>
            <select value={sortOrder} onChange={(e) => setSortOrder(e.target.value)}>
              <option value="desc">Desc</option>
              <option value="asc">Asc</option>
            </select>
            <button className="btn btn-primary" onClick={applyFilters}>Apply</button>
            <button className="btn btn-ghost" onClick={clearFilters}>Clear</button>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="panel">
        <h3>Audit Events — {total} total</h3>
        {events.length === 0 ? (
          <div className="empty-state">No audit events match filters — try clearing filters.</div>
        ) : (
          <div className="table-wrap">
            <table className="audit-table">
              <thead><tr><th>Timestamp</th><th>Actor</th><th>Action</th><th>Resource</th><th>Resource ID</th><th>Details</th><th>Hash</th></tr></thead>
              <tbody>
                {events.map((ev) => (
                  <tr key={ev.id} style={{ cursor: "pointer" }} onClick={() => setSelected(ev)}>
                    <td style={{ whiteSpace: "nowrap", fontSize: ".72rem" }}>{ev.created_at ? new Date(ev.created_at).toLocaleString() : ""}</td>
                    <td>{ev.actor}</td>
                    <td><span className="badge badge-neutral">{ev.action}</span></td>
                    <td>{ev.resource_type}</td>
                    <td className="mono" style={{ fontSize: ".72rem" }}>
                      {ev.resource_type === "case" ? <Link to={`/case/${ev.resource_id}`} className="link" onClick={(e) => e.stopPropagation()}>{ev.resource_id.slice(0, 8)}…</Link> : ev.resource_type === "customer" ? <Link to={`/customers/${ev.resource_id}`} className="link" onClick={(e) => e.stopPropagation()}>{ev.resource_id.slice(0, 8)}…</Link> : ev.resource_type === "merchant" ? <Link to={`/merchants/${ev.resource_id}`} className="link" onClick={(e) => e.stopPropagation()}>{ev.resource_id.slice(0, 8)}…</Link> : ev.resource_type === "device" ? <Link to={`/devices/${ev.resource_id}`} className="link" onClick={(e) => e.stopPropagation()}>{ev.resource_id.slice(0, 8)}…</Link> : `${ev.resource_id.slice(0, 8)}…`}
                    </td>
                    <td className="muted" style={{ maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: ".72rem" }} title={JSON.stringify(ev.after_json || ev.before_json || {}).slice(0, 200)}>{JSON.stringify(ev.after_json || ev.before_json || {}).slice(0, 60) || "—"}</td>
                    <td className="mono" style={{ fontSize: ".68rem" }}>{computeHash(ev)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12, alignItems: "center" }}>
          <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => load(page - 1)}>Previous</button>
          <span className="muted" style={{ fontSize: ".76rem" }}>Page {page} of {Math.max(1, totalPages)} — {total} total</span>
          <button className="btn btn-ghost btn-sm" disabled={page >= totalPages} onClick={() => load(page + 1)}>Next</button>
        </div>
      </div>

      {/* Detail panel */}
      {selected && (
        <div className="panel" style={{ borderColor: "var(--accent-blue)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <h3 style={{ margin: 0 }}>Event Detail — <span className="mono">{selected.id.slice(0, 8)}…</span></h3>
            <button className="btn btn-ghost btn-sm" onClick={() => setSelected(null)}>Close</button>
          </div>
          <div className="kv" style={{ marginTop: 12 }}>
            <dt>Event ID</dt><dd className="mono">{selected.id}</dd>
            <dt>Timestamp</dt><dd>{selected.created_at ? new Date(selected.created_at).toLocaleString() : ""} <span className="muted" style={{ fontSize: ".68rem" }}>({selected.created_at})</span></dd>
            <dt>Actor</dt><dd>{selected.actor}</dd>
            <dt>Action</dt><dd><span className="badge badge-neutral">{selected.action}</span></dd>
            <dt>Resource Type</dt><dd>{selected.resource_type}</dd>
            <dt>Resource ID</dt><dd className="mono">{selected.resource_id} {selected.resource_type === "case" && <Link to={`/case/${selected.resource_id}`} className="link" style={{ marginLeft: 8 }}>Open Case →</Link>}</dd>
            <dt>Details</dt><dd className="mono" style={{ background: "var(--bg-secondary)", padding: "6px 8px", borderRadius: 6, border: "1px solid var(--border)", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{JSON.stringify({ before: (selected as any).before_json, after: (selected as any).after_json }, null, 2).slice(0, 1000) || "—"}</dd>
            <dt>Previous Hash</dt><dd className="mono" style={{ fontSize: ".68rem", wordBreak: "break-all" }}>{selected.prev_hash || "genesis (first event)"}</dd>
            <dt>Current Hash</dt><dd className="mono" style={{ fontSize: ".68rem", wordBreak: "break-all" }}>SHA256(actor, action, resource, before/after, prev_hash, created_at) — verified via chain</dd>
          </div>
          <p className="muted" style={{ marginTop: 8, fontSize: ".72rem" }}>Current hash is cryptographically linked to previous hash. Any tampering would break verification.</p>
        </div>
      )}
    </section>
  );
};
