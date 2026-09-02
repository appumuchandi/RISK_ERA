import "./style.css";
import { Routes, Route, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Header } from "./components/Header";
import Sidebar from "./components/layout/Sidebar";
import Breadcrumbs from "./components/layout/Breadcrumbs";
import { Dashboard } from "./components/Dashboard";
import { CasesList } from "./components/CasesList";
import { CaseInvestigation } from "./components/CaseInvestigation";
import { AuditView } from "./components/AuditView";
import LoginPage from "./pages/LoginPage";
import CustomersPage, { CustomerDetailPage } from "./pages/CustomersPage";
import MerchantsPage, { MerchantDetailPage } from "./pages/MerchantsPage";
import DevicesPage, { DeviceDetailPage } from "./pages/DevicesPage";
import NetworkPage from "./pages/NetworkPage";
import RulesPage from "./pages/RulesPage";
import AlertsPage from "./pages/AlertsPage";
import HealthPage from "./pages/HealthPage";
import Assistant from "./components/Assistant";
import OperationsPage from "./pages/OperationsPage";
import TransactionsPage from "./pages/TransactionsPage";
import InvestigationsPage from "./pages/InvestigationsPage";
import AnalyticsPage from "./pages/AnalyticsPage";
import { useAuth } from "./contexts/AuthContext";
import { ApiService } from "./api";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { token, isLoading } = useAuth();
  if (isLoading) return <div className="loading-state">Loading risk operations…</div>;
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function RouteParamDetail({ kind, api }: { kind: "customer" | "merchant" | "device"; api: ApiService }) {
  const { id } = useParams<{ id: string }>();
  if (!id) return <div className="error-state">Missing identifier</div>;
  if (kind === "customer") return <CustomerDetailPage api={api} id={id} />;
  if (kind === "merchant") return <MerchantDetailPage api={api} id={id} />;
  return <DeviceDetailPage api={api} id={id} />;
}

export default function App() {
  const { token, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const api = useMemo(() => new ApiService(token), [token]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const isLogin = location.pathname === "/login";

  const toggleSidebar = () => setSidebarOpen((o) => !o);
  const closeSidebar = () => setSidebarOpen(false);

  if (isLogin) {
    return (
      <div className="app-shell">
        <Header token={token} onLogout={logout} api={api} onToggleSidebar={toggleSidebar} />
        <main className="main-content" style={{ maxWidth: 1400, margin: "0 auto" }}>
          <Routes>
            <Route path="/login" element={token ? <Navigate to="/" replace /> : <LoginPage />} />
            <Route path="*" element={<Navigate to={token ? "/" : "/login"} replace />} />
          </Routes>
        </main>
        <footer className="app-footer">RISK-ERA — Independent AI Risk Investigation Platform · Demo Environment · Synthetic Payment Data · Detect → Investigate → Ground → Decide → Audit</footer>
      </div>
    );
  }

  return (
    <div className="app-shell with-sidebar">
      <Header token={token} onLogout={logout} api={api} onToggleSidebar={toggleSidebar} />
      <div className="shell-body">
        {token && (
          <>
            <div className={`sidebar-overlay ${sidebarOpen ? "open" : ""}`} onClick={closeSidebar} aria-hidden={!sidebarOpen} />
            <div className={`sidebar-drawer ${sidebarOpen ? "open" : ""}`}>
              <Sidebar onClose={closeSidebar} />
            </div>
            <div className="sidebar-desktop">
              <Sidebar />
            </div>
          </>
        )}
        <div className="content-area">
          {token && <Breadcrumbs />}
          <main className="main-content">
            <Routes>
              <Route path="/login" element={token ? <Navigate to="/" replace /> : <LoginPage />} />
              <Route path="/" element={<RequireAuth><Dashboard api={api} onNavigate={(p) => navigate(p)} /></RequireAuth>} />
              <Route path="/cases" element={<RequireAuth><CasesList api={api} /></RequireAuth>} />
              <Route path="/case/:caseId" element={<RequireAuth><CaseInvestigation api={api} /></RequireAuth>} />
              <Route path="/audit" element={<RequireAuth><AuditView api={api} /></RequireAuth>} />

              <Route path="/transactions" element={<RequireAuth><TransactionsPage api={api} /></RequireAuth>} />

              {/* Phase 3 — Customer/Merchant/Device intelligence (live) */}
              <Route path="/customers" element={<RequireAuth><CustomersPage api={api} /></RequireAuth>} />
              <Route path="/customers/:id" element={<RequireAuth><RouteParamDetail kind="customer" api={api} /></RequireAuth>} />
              <Route path="/merchants" element={<RequireAuth><MerchantsPage api={api} /></RequireAuth>} />
              <Route path="/merchants/:id" element={<RequireAuth><RouteParamDetail kind="merchant" api={api} /></RequireAuth>} />
              <Route path="/devices" element={<RequireAuth><DevicesPage api={api} /></RequireAuth>} />
              <Route path="/devices/:id" element={<RequireAuth><RouteParamDetail kind="device" api={api} /></RequireAuth>} />
              <Route path="/network" element={<RequireAuth><NetworkPage api={api} /></RequireAuth>} />
              <Route path="/rules" element={<RequireAuth><RulesPage api={api} /></RequireAuth>} />
              <Route path="/alerts" element={<RequireAuth><AlertsPage api={api} /></RequireAuth>} />
              <Route path="/operations" element={<RequireAuth><OperationsPage api={api} /></RequireAuth>} />
              <Route path="/investigations" element={<RequireAuth><InvestigationsPage api={api} /></RequireAuth>} />
              <Route path="/analytics" element={<RequireAuth><AnalyticsPage api={api} /></RequireAuth>} />
              <Route path="/health" element={<RequireAuth><HealthPage api={api} /></RequireAuth>} />

              <Route path="*" element={<Navigate to={token ? "/" : "/login"} replace />} />
            </Routes>
          </main>
          <footer className="app-footer">RISK-ERA — Independent AI Risk Investigation Platform · Demo Environment · Synthetic Payment Data · Detect → Investigate → Ground → Decide → Audit</footer>
        </div>
      </div>
      <Assistant api={api} />
    </div>
  );
}
