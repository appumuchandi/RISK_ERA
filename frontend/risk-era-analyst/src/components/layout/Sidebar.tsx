import { NavLink } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";

type NavItem = {
  label: string;
  path: string;
  icon: string;
  phase?: number;
  adminOnly?: boolean;
  exact?: boolean;
};

const NAV: NavItem[] = [
  { label: "Executive Overview", path: "/", icon: "◈", exact: true, phase: 1 },
  { label: "Operations", path: "/operations", icon: "◉", phase: 7 },
  { label: "Transactions", path: "/transactions", icon: "⇄", phase: 2 },
  { label: "Cases", path: "/cases", icon: "▣", phase: 1 },
  { label: "Customers", path: "/customers", icon: "◐", phase: 3 },
  { label: "Merchants", path: "/merchants", icon: "⬢", phase: 3 },
  { label: "Devices", path: "/devices", icon: "⬣", phase: 3 },
  { label: "Fraud Network", path: "/network", icon: "⬔", phase: 4 },
  { label: "Rules", path: "/rules", icon: "⚙", phase: 6 },
  { label: "Alerts", path: "/alerts", icon: "⚠", phase: 7 },
  { label: "Investigations", path: "/investigations", icon: "⬢", phase: 8 },
  { label: "Analytics", path: "/analytics", icon: "▤", phase: 9 },
  { label: "Audit Center", path: "/audit", icon: "⎙", phase: 10 },
  { label: "System Health", path: "/health", icon: "⬡", phase: 11 },
];

export const Sidebar = ({ collapsed, onClose }: { collapsed?: boolean; onClose?: () => void }) => {
  const { role } = useAuth();
  const isAdmin = role === "admin";

  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`} aria-label="Primary navigation">
      <nav className="sidebar-nav" aria-label="Product navigation">
        <div className="sidebar-section-label">Risk Intelligence</div>
        {NAV.slice(0, 8).map((item) => {
          if (item.adminOnly && !isAdmin) return null;
          const isAvailable = ["/", "/cases", "/audit", "/customers", "/merchants", "/devices", "/network", "/rules", "/transactions", "/operations"].includes(item.path);
          return (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.exact}
              onClick={onClose}
              className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""} ${!isAvailable ? "upcoming" : ""}`}
              title={isAvailable ? item.label : `${item.label} — Phase ${item.phase} upcoming`}
            >
              <span className="sidebar-icon" aria-hidden>{item.icon}</span>
              <span className="sidebar-label">{item.label}</span>
              {!isAvailable && <span className="sidebar-badge">Soon</span>}
            </NavLink>
          );
        })}
        <div className="sidebar-section-label">Operations</div>
        {NAV.slice(8, 12).map((item) => {
          const isAvailable = ["/audit", "/rules", "/alerts", "/investigations", "/analytics"].includes(item.path);
          return (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={onClose}
              className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""} ${!isAvailable ? "upcoming" : ""}`}
              title={isAvailable ? item.label : `${item.label} — Phase ${item.phase} upcoming`}
            >
              <span className="sidebar-icon" aria-hidden>{item.icon}</span>
              <span className="sidebar-label">{item.label}</span>
              {!isAvailable && <span className="sidebar-badge">Soon</span>}
            </NavLink>
          );
        })}
        <div className="sidebar-section-label">Governance</div>
        {NAV.slice(12).map((item) => {
          const isAvailable = ["/audit", "/health"].includes(item.path);
          return (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={onClose}
              className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""} ${!isAvailable ? "upcoming" : ""}`}
              title={isAvailable ? item.label : `${item.label} — Phase ${item.phase} upcoming`}
            >
              <span className="sidebar-icon" aria-hidden>{item.icon}</span>
              <span className="sidebar-label">{item.label}</span>
              {!isAvailable && <span className="sidebar-badge">Soon</span>}
            </NavLink>
          );
        })}
      </nav>
      <div className="sidebar-footer">
        <div className="sidebar-user-hint">
          <span className="muted" style={{ fontSize: ".68rem" }}>Role: {role || "analyst"}</span>
          <span className="muted" style={{ fontSize: ".62rem", display: "block", marginTop: 4, lineHeight: 1.3 }}>Demo · Synthetic Data<br/>Detect → Investigate → Audit</span>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
