import { Link, useLocation } from "react-router-dom";

const LABELS: Record<string, string> = {
  "": "Executive Overview",
  "operations": "Operations",
  "transactions": "Transactions",
  "cases": "Cases",
  "case": "Case",
  "customers": "Customers",
  "merchants": "Merchants",
  "devices": "Devices",
  "network": "Fraud Network",
  "rules": "Risk Rules",
  "alerts": "Alerts",
  "investigations": "Investigations",
  "analytics": "Analytics",
  "audit": "Audit Center",
  "health": "System Health",
};

export const Breadcrumbs = () => {
  const { pathname } = useLocation();
  const segments = pathname.split("/").filter(Boolean);
  // Special case: /case/:id
  if (segments[0] === "case" && segments[1]) {
    return (
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link to="/" className="crumb">Executive Overview</Link>
        <span className="crumb-sep">›</span>
        <Link to="/cases" className="crumb">Cases</Link>
        <span className="crumb-sep">›</span>
        <span className="crumb current mono">CASE-{segments[1].slice(0, 8).toUpperCase()}</span>
      </nav>
    );
  }
  if (segments.length === 0) {
    return (
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <span className="crumb current">Executive Overview</span>
      </nav>
    );
  }
  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      <Link to="/" className="crumb">Home</Link>
      {segments.map((seg, i) => {
        const isLast = i === segments.length - 1;
        const label = LABELS[seg] || seg;
        const href = "/" + segments.slice(0, i + 1).join("/");
        return (
          <span key={href} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
            <span className="crumb-sep">›</span>
            {isLast ? (
              <span className="crumb current">{label}</span>
            ) : (
              <Link to={href} className="crumb">{label}</Link>
            )}
          </span>
        );
      })}
    </nav>
  );
};

export default Breadcrumbs;
