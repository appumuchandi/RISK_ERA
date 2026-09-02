import { useEffect, useState, useMemo } from "react";
import { Link } from "react-router-dom";
import type { ApiService, NetworkGraphResponse, NetworkNode } from "../api";
import { RiskBadge } from "../components/intel/IntelShared";

type EntityType = "customer" | "merchant" | "device" | "transaction" | "case";

const TYPE_LABEL: Record<EntityType, string> = {
  customer: "Customer",
  merchant: "Merchant",
  device: "Device",
  transaction: "Transaction",
  case: "Case",
};

const TYPE_ICON: Record<string, string> = {
  customer: "◐",
  merchant: "⬢",
  device: "⬣",
  transaction: "⇄",
  case: "▣",
};

const RISK_COLOR: Record<string, string> = {
  low: "var(--accent-green)",
  medium: "var(--accent-amber)",
  high: "var(--accent-red)",
  critical: "#b42318",
};

export default function NetworkPage({ api }: { api: ApiService }) {
  const [entityType, setEntityType] = useState<EntityType>("customer");
  const [search, setSearch] = useState("");
  const [options, setOptions] = useState<Array<{ id: string; label: string }>>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [selectedLabel, setSelectedLabel] = useState<string>("");
  const [hops, setHops] = useState<number>(2);
  const [graph, setGraph] = useState<NetworkGraphResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState<NetworkNode | null>(null);

  // Search entities
  useEffect(() => {
    if (!search || search.length < 1) {
      setOptions([]);
      return;
    }
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        setSearchLoading(true);
        let opts: Array<{ id: string; label: string }> = [];
        if (entityType === "customer") {
          const res: any = await api.listCustomers({ page: 1, page_size: 10, search });
          opts = (res.items || []).map((c: any) => ({ id: c.customer_id, label: c.external_id }));
        } else if (entityType === "merchant") {
          const res: any = await api.listMerchants({ page: 1, page_size: 10, search });
          opts = (res.items || []).map((m: any) => ({ id: m.merchant_id, label: `${m.name} (${m.category_code})` }));
        } else if (entityType === "device") {
          const res: any = await api.listDevices({ page: 1, page_size: 10, search });
          opts = (res.items || []).map((d: any) => ({ id: d.device_id, label: `${d.fingerprint_hash.slice(0, 12)}… ${d.ip || ""}` }));
        } else if (entityType === "transaction") {
          const res: any = await api.getTransactions({ search, page_size: 10 } as any);
          opts = (res.items || []).map((tx: any) => ({ id: tx.id, label: tx.provider_event_id }));
        } else if (entityType === "case") {
          const res: any = await api.getCases(1, 10, search ? { q: search } : {});
          // CasesList uses different shape, but getCases returns items with id
          const items = res.items || res.cases || [];
          opts = items.slice(0, 10).map((c: any) => ({ id: c.id, label: `Case ${c.id.slice(0, 8)} — ${c.status}` }));
        }
        if (!cancelled) setOptions(opts.slice(0, 10));
      } catch (e) {
        if (!cancelled) setOptions([]);
      } finally {
        if (!cancelled) setSearchLoading(false);
      }
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [search, entityType, api]);

  const loadGraph = async (id?: string, hop?: number) => {
    const effId = id ?? selectedId;
    const effHops = hop ?? hops;
    if (!effId) {
      setError("Select an entity to analyze network");
      return;
    }
    try {
      setLoading(true);
      setError(null);
      setSelectedNode(null);
      const data = await api.getNetworkGraph({ entity_type: entityType, entity_id: effId, hops: effHops });
      setGraph(data);
      setSelectedNode(data.root);
    } catch (e: any) {
      const status = e?.response?.status;
      if (status === 404) setError("Entity not found — it may have been removed or ID is incorrect");
      else if (status === 422) setError("Invalid request — check entity type, ID format or hops (1-3)");
      else if (status === 401) setError("Authentication required — please login again");
      else setError(e instanceof Error ? e.message : "Unable to load network data");
      setGraph(null);
    } finally {
      setLoading(false);
    }
  };

  const insights = useMemo(() => {
    if (!graph) return [];
    const arr: string[] = [];
    arr.push(`${graph.stats.node_count} entities connected`);
    if (graph.stats.customer_count) arr.push(`${graph.stats.customer_count} customers`);
    if (graph.stats.device_count) arr.push(`${graph.stats.device_count} devices`);
    if (graph.stats.merchant_count) arr.push(`${graph.stats.merchant_count} merchants`);
    if (graph.stats.transaction_count) arr.push(`${graph.stats.transaction_count} supporting transactions`);
    if (graph.stats.case_count) arr.push(`${graph.stats.case_count} supporting cases`);
    // derived insights
    // simple neutral insight: if multiple customers and single device shared
    if (graph.stats.customer_count > 1 && graph.stats.device_count >= 1) {
      // check if any device connects multiple customers (we can infer via graph: device node with multiple transaction edges)
      // For now, generic
      const shared = graph.stats.customer_count > graph.stats.device_count ? `${graph.stats.customer_count} customers share ${graph.stats.device_count} device(s)` : null;
      if (shared) arr.push(shared);
    }
    if (graph.stats.merchant_count && graph.stats.customer_count > 5) {
      arr.push(`${graph.stats.customer_count} customers observed across ${graph.stats.merchant_count} merchants`);
    }
    return arr.slice(0, 6);
  }, [graph]);

  // SVG layout: polar coordinates per hop
  const layout = useMemo(() => {
    if (!graph) return null;
    const width = 800;
    const height = 460;
    const cx = width / 2;
    const cy = height / 2;
    // group nodes by hop
    const byHop: Record<number, typeof graph.nodes> = {};
    graph.nodes.forEach((n) => {
      if (!byHop[n.hop]) byHop[n.hop] = [];
      byHop[n.hop]!.push(n);
    });
    // sort each hop by type then id for determinism
    Object.values(byHop).forEach((arr) => arr.sort((a, b) => (a.type + a.id).localeCompare(b.type + b.id)));
    const positions = new Map<string, { x: number; y: number }>();
    // root at center
    const root = graph.root;
    positions.set(root.id, { x: cx, y: cy });
    const maxHop = graph.stats.max_hop || hops;
    const radii = [0, 110, 190, 260]; // per hop
    for (let h = 1; h <= maxHop; h++) {
      const nodesAtHop = byHop[h] || [];
      const n = nodesAtHop.length;
      if (n === 0) continue;
      const radius = radii[h] || 260;
      nodesAtHop.forEach((node, idx) => {
        if (node.id === root.id) return;
        const angle = (idx / Math.max(n, 1)) * 2 * Math.PI - Math.PI / 2;
        // add slight jitter for overlapping
        const jitter = (idx % 2 === 0 ? 6 : -6);
        const x = cx + Math.cos(angle) * (radius + jitter);
        const y = cy + Math.sin(angle) * (radius + jitter);
        positions.set(node.id, { x, y });
      });
    }
    // also ensure any isolated nodes not in byHop (like hop 0 root already)
    graph.nodes.forEach((n) => {
      if (!positions.has(n.id)) {
        positions.set(n.id, { x: cx, y: cy });
      }
    });
    return { width, height, positions, byHop };
  }, [graph, hops]);

  if (loading && !graph) {
    return (
      <section className="intel-page">
        <div className="page-head">
          <h2>Fraud Network Intelligence</h2>
        </div>
        <div className="loading-state">Building network…</div>
        <div className="panel" style={{ marginTop: 12 }}>
          <div className="skeleton" style={{ height: 18, width: "60%" }} />
          <div className="skeleton" style={{ height: 120, marginTop: 12 }} />
        </div>
      </section>
    );
  }

  return (
    <section className="intel-page network-page">
      <div className="page-head">
        <div>
          <h2>Fraud Network Intelligence <span className="badge badge-neutral">Phase 4</span></h2>
          <p className="muted">
            Explore entity relationships — Customer ↔ Device ↔ Merchant ↔ Transaction ↔ Case. Traverse up to 3 hops from any entity, see supporting transactions/cases and risk signals. All connections are derived from real foreign-key relationships, not inferred fraud.
          </p>
        </div>
      </div>

      <div className="panel">
        <h3>Entity selector</h3>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <div className="toolbar-group" style={{ flex: "1 1 160px" }}>
            <select value={entityType} onChange={(e) => { setEntityType(e.target.value as EntityType); setOptions([]); setSearch(""); setSelectedId(""); setSelectedLabel(""); setGraph(null); }}>
              <option value="customer">Customer</option>
              <option value="merchant">Merchant</option>
              <option value="device">Device</option>
              <option value="transaction">Transaction</option>
              <option value="case">Case</option>
            </select>
          </div>
          <div className="toolbar-group" style={{ flex: "2 1 260px", position: "relative" }}>
            <input
              placeholder={`Search ${TYPE_LABEL[entityType]} (e.g., ${entityType === "customer" ? "external ID" : entityType === "merchant" ? "name or MCC" : "fingerprint/IP"})`}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {searchLoading && <span className="muted" style={{ position: "absolute", right: 10, top: 9, fontSize: ".68rem" }}>Searching…</span>}
            {options.length > 0 && (
              <div style={{ position: "absolute", top: 38, left: 0, right: 0, background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, zIndex: 20, maxHeight: 220, overflowY: "auto" }}>
                {options.map((o) => (
                  <button
                    key={o.id}
                    onClick={() => { setSelectedId(o.id); setSelectedLabel(o.label); setSearch(o.label); setOptions([]); }}
                    className="btn btn-ghost"
                    style={{ width: "100%", justifyContent: "flex-start", border: "none", borderRadius: 0, height: 36, fontSize: ".82rem" }}
                  >
                    <span className="mono" style={{ flex: 1, textAlign: "left", overflow: "hidden", textOverflow: "ellipsis" }}>{o.label}</span>
                    <span className="muted" style={{ fontSize: ".68rem", marginLeft: 8 }}>{o.id.slice(0, 8)}…</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="toolbar-group">
            <select value={hops} onChange={(e) => setHops(Number(e.target.value))} title="Hop depth">
              <option value={1}>1 Hop</option>
              <option value={2}>2 Hops</option>
              <option value={3}>3 Hops</option>
            </select>
          </div>
          <div className="toolbar-group">
            <button className="btn btn-primary" disabled={!selectedId || loading} onClick={() => loadGraph()}>
              {loading ? "Building…" : "Analyze Network"}
            </button>
          </div>
        </div>
        {selectedId && (
          <div className="muted" style={{ marginTop: 8, fontSize: ".72rem" }}>
            Selected: <span className="mono">{selectedLabel}</span> <span className="muted">· {selectedId.slice(0, 8)}…</span> <span className="badge badge-neutral">{TYPE_LABEL[entityType]}</span>
            <button className="btn btn-ghost btn-sm" style={{ marginLeft: 8 }} onClick={() => { setSelectedId(""); setSelectedLabel(""); setSearch(""); setGraph(null); }}>Clear</button>
          </div>
        )}
      </div>

      {error && (
        <div className="error-state">
          <h3>Unable to load network data.</h3>
          <p>{error}</p>
          <button className="btn btn-primary" onClick={() => loadGraph()}>Retry</button>
        </div>
      )}

      {!graph && !error && !loading && (
        <div className="empty-state">Select an entity and hop depth, then Analyze Network to explore connections. No connected entities found until a query is run.</div>
      )}

      {graph && layout && (
        <>
          <div className="panel">
            <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
              <h3 style={{ margin: 0 }}>Network Graph — {graph.stats.node_count} entities, {graph.stats.edge_count} connections (max hop {graph.stats.max_hop})</h3>
              <span className="muted" style={{ fontSize: ".72rem" }}>Root: {graph.root.label} · {graph.root.type} · hop 0</span>
            </div>

            <div className="table-wrap" style={{ padding: 0, border: "none", background: "transparent" }}>
              <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
                <svg width={layout.width} height={layout.height} viewBox={`0 0 ${layout.width} ${layout.height}`} style={{ width: "100%", minWidth: 500, height: "auto", background: "var(--bg-secondary)", borderRadius: 10, border: "1px solid var(--border)" }}>
                  {/* edges */}
                  {graph.edges.map((e, idx) => {
                    const s = layout.positions.get(e.source);
                    const t = layout.positions.get(e.target);
                    if (!s || !t) return null;
                    return (
                      <g key={idx}>
                        <line x1={s.x} y1={s.y} x2={t.x} y2={t.y} stroke="var(--border-light)" strokeWidth={1.2} opacity={0.9} />
                        {/* edge label midpoint (small) */}
                        {/* <text x={(s.x + t.x) / 2} y={(s.y + t.y) / 2 - 4} fontSize={6} fill="var(--text-muted)" textAnchor="middle">{e.label}</text> */}
                      </g>
                    );
                  })}
                  {/* nodes */}
                  {graph.nodes.map((n) => {
                    const pos = layout.positions.get(n.id);
                    if (!pos) return null;
                    const color = RISK_COLOR[n.risk_level] || RISK_COLOR.low;
                    const isRoot = n.id === graph.root.id;
                    const isSelected = selectedNode?.id === n.id;
                    return (
                      <g key={n.id} onClick={() => setSelectedNode(n)} style={{ cursor: "pointer" }}>
                        <circle cx={pos.x} cy={pos.y} r={isRoot ? 18 : 13} fill={color} stroke={isSelected ? "#fff" : "var(--border)"} strokeWidth={isSelected ? 2 : 1} opacity={0.95} />
                        <text x={pos.x} y={pos.y} textAnchor="middle" dy={4} fontSize={isRoot ? 10 : 9} fill="#fff" fontWeight={700} pointerEvents="none">
                          {TYPE_ICON[n.type] || "●"}
                        </text>
                        <text x={pos.x} y={pos.y + (isRoot ? 28 : 22)} textAnchor="middle" fontSize={7} fill="var(--text-secondary)" style={{ fontFamily: "ui-monospace, monospace", maxWidth: 80 }} pointerEvents="none">
                          {n.label.length > 14 ? n.label.slice(0, 12) + "…" : n.label}
                        </text>
                        <text x={pos.x} y={pos.y + (isRoot ? 36 : 30)} textAnchor="middle" fontSize={6} fill="var(--text-muted)" pointerEvents="none">
                          {n.type} · hop {n.hop} · {n.risk_level}
                        </text>
                      </g>
                    );
                  })}
                </svg>
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 10, alignItems: "center" }}>
              <span className="muted" style={{ fontSize: ".72rem" }}>Legend:</span>
              {["low", "medium", "high", "critical"].map((lvl) => (
                <span key={lvl} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: ".72rem" }}>
                  <span style={{ width: 12, height: 12, borderRadius: "50%", background: RISK_COLOR[lvl], border: "1px solid var(--border)", display: "inline-block" }} /> {lvl}
                </span>
              ))}
              <span className="muted" style={{ marginLeft: 8, fontSize: ".72rem" }}>○ Customer ◐ Merchant ⬣ Device ⇄ Transaction ▣ Case</span>
            </div>
          </div>

          <div className="case-grid">
            <div className="panel">
              <h3>Summary statistics</h3>
              <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: 8, marginBottom: 0 }}>
                <div className="stat" style={{ padding: 10 }}><div className="stat-value">{graph.stats.node_count}</div><div className="stat-label">Entities</div></div>
                <div className="stat" style={{ padding: 10 }}><div className="stat-value">{graph.stats.edge_count}</div><div className="stat-label">Connections</div></div>
                <div className="stat" style={{ padding: 10 }}><div className="stat-value">{graph.stats.customer_count}</div><div className="stat-label">Customers</div></div>
                <div className="stat" style={{ padding: 10 }}><div className="stat-value">{graph.stats.device_count}</div><div className="stat-label">Devices</div></div>
                <div className="stat" style={{ padding: 10 }}><div className="stat-value">{graph.stats.merchant_count}</div><div className="stat-label">Merchants</div></div>
                <div className="stat" style={{ padding: 10 }}><div className="stat-value">{graph.stats.transaction_count}</div><div className="stat-label">Transactions</div></div>
                <div className="stat" style={{ padding: 10 }}><div className="stat-value">{graph.stats.case_count}</div><div className="stat-label">Cases</div></div>
              </div>
              {insights.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <h4 style={{ margin: "8px 0 6px 0", fontSize: ".76rem", color: "var(--text-secondary)" }}>Insights (backend-derived)</h4>
                  <ul className="signal-list">
                    {insights.map((ins, i) => (
                      <li key={i} className="sig-hit">• {ins}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            <div className="panel">
              <h3>Node details {selectedNode ? `— ${selectedNode.type} · ${selectedNode.label}` : ""}</h3>
              {!selectedNode ? (
                <div className="empty-state">Click a node in the graph to see details.</div>
              ) : (
                <>
                  <dl className="kv">
                    <dt>Type</dt><dd><span className="badge badge-neutral">{selectedNode.type}</span> <span className="muted">{TYPE_ICON[selectedNode.type]}</span></dd>
                    <dt>Label</dt><dd className="mono">{selectedNode.label}</dd>
                    <dt>ID</dt><dd className="mono">{selectedNode.id.slice(0, 12)}…</dd>
                    <dt>Hop</dt><dd>{selectedNode.hop}</dd>
                    <dt>Risk</dt><dd><RiskBadge level={selectedNode.risk_level} /> <span className="muted" style={{ marginLeft: 6 }}>{selectedNode.risk_score ?? "—"}</span></dd>
                  </dl>
                  <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {selectedNode.type === "customer" && <Link to={`/customers/${selectedNode.id}`} className="btn btn-ghost btn-sm">Open Customer →</Link>}
                    {selectedNode.type === "merchant" && <Link to={`/merchants/${selectedNode.id}`} className="btn btn-ghost btn-sm">Open Merchant →</Link>}
                    {selectedNode.type === "device" && <Link to={`/devices/${selectedNode.id}`} className="btn btn-ghost btn-sm">Open Device →</Link>}
                    {selectedNode.type === "case" && <Link to={`/case/${selectedNode.id}`} className="btn btn-ghost btn-sm">Open Case →</Link>}
                    {selectedNode.type === "transaction" && <span className="muted" style={{ fontSize: ".72rem", alignSelf: "center" }}>Transaction: {selectedNode.provider_event_id || selectedNode.id.slice(0, 8)}</span>}
                  </div>
                  <h4 style={{ margin: "14px 0 6px 0", fontSize: ".76rem", color: "var(--text-secondary)" }}>Connected edges ({graph.edges.filter((e) => e.source === selectedNode.id || e.target === selectedNode.id).length})</h4>
                  <ul className="activity-list">
                    {graph.edges.filter((e) => e.source === selectedNode.id || e.target === selectedNode.id).slice(0, 8).map((e, i) => (
                      <li key={i} className="activity-item" style={{ fontSize: ".76rem" }}>
                        <span className="activity-action">{e.label} <span className="muted">· {e.relationship}</span> <span className="mono" style={{ fontSize: ".68rem" }}>{e.source.slice(0, 6)} ↔ {e.target.slice(0, 6)}</span></span>
                        <span className="activity-ts">{e.supporting_transaction_ids.length} txn · {e.supporting_case_ids.length} case</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </div>

          <div className="panel">
            <h3>Relationships</h3>
            {graph.edges.length === 0 ? (
              <div className="empty-state">No connected entities found — try increasing hops to 3 or select a different root.</div>
            ) : (
              <div className="table-wrap">
                <table className="cases-table">
                  <thead><tr><th>Source</th><th>Target</th><th>Relationship</th><th>Supporting Txn</th><th>Supporting Case</th></tr></thead>
                  <tbody>
                    {graph.edges.slice(0, 20).map((e, i) => (
                      <tr key={i}>
                        <td className="mono">{e.source.slice(0, 8)}…</td>
                        <td className="mono">{e.target.slice(0, 8)}…</td>
                        <td><span className="badge badge-neutral">{e.relationship}</span> <span style={{ fontSize: ".72rem" }}>{e.label}</span></td>
                        <td className="mono" style={{ fontSize: ".72rem" }}>{e.supporting_transaction_ids.map((id) => id.slice(0, 6)).join(", ") || "—"}</td>
                        <td className="mono" style={{ fontSize: ".72rem" }}>{e.supporting_case_ids.map((id) => id.slice(0, 6)).join(", ") || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {graph.edges.length > 20 && <div className="muted" style={{ marginTop: 6, fontSize: ".72rem" }}>Showing 20 of {graph.edges.length} relationships.</div>}
          </div>
        </>
      )}
    </section>
  );
}
