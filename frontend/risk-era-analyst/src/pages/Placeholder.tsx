import { Link } from "react-router-dom";

type Props = {
  title: string;
  description: string;
  phase: number;
  hint?: string;
  icon?: string;
  actions?: Array<{ label: string; to: string }>;
};

export const Placeholder = ({ title, description, phase, hint, icon = "◈", actions }: Props) => {
  return (
    <section className="placeholder-page">
      <div className="page-head">
        <div>
          <h2 style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span aria-hidden>{icon}</span> {title}
            <span className="badge badge-neutral">Phase {phase} · Upcoming</span>
          </h2>
          <p className="muted">{description}</p>
        </div>
      </div>

      <div className="panel" style={{ textAlign: "center", padding: "24px 20px", maxWidth: 640, margin: "0 auto" }}>
        <div style={{ width: 48, height: 48, borderRadius: 12, background: "var(--bg-elevated)", border: "1px solid var(--border)", display: "grid", placeItems: "center", fontSize: "1.4rem", margin: "0 auto 12px auto" }} aria-hidden>{icon}</div>
        <h3 style={{ margin: "0 0 8px 0", fontSize: "1.05rem" }}>{title} — Coming in Phase {phase}</h3>
        <p className="muted" style={{ maxWidth: 520, margin: "0 auto 8px auto", lineHeight: 1.5, fontSize: ".82rem" }}>{description}</p>
        <p className="muted" style={{ maxWidth: 520, margin: "0 auto 14px auto", lineHeight: 1.4, fontSize: ".74rem" }}>
          {hint || `This module will be powered by real PostgreSQL data via authenticated FastAPI endpoints. No mock data.`}
        </p>
        <span className="badge badge-neutral" style={{ fontSize: ".68rem" }}>Phase {phase} · Not yet implemented</span>
        {actions && actions.length > 0 && (
          <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 14, flexWrap: "wrap" }}>
            {actions.map((a) => (
              <Link key={a.to} to={a.to} className="btn btn-primary btn-sm">
                {a.label}
              </Link>
            ))}
          </div>
        )}
      </div>

      <div className="panel">
        <h3>How this fits the analyst workflow</h3>
        <div className="flow">
          <span className="flow-step">Detect</span>
          <span className="flow-arrow">→</span>
          <span className="flow-step">Investigate</span>
          <span className="flow-arrow">→</span>
          <span className="flow-step">Ground Evidence</span>
          <span className="flow-arrow">→</span>
          <span className="flow-step">Decide</span>
          <span className="flow-arrow">→</span>
          <span className="flow-step">Audit</span>
        </div>
        <p className="muted" style={{ marginTop: 10 }}>
          Return to <Link to="/cases">Cases</Link> or <Link to="/">Executive Overview</Link> to continue with live data.
        </p>
      </div>
    </section>
  );
};

export default Placeholder;
