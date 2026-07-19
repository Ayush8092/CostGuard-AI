import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, TrendingUp, AlertTriangle, Trash2, Sliders,
  Lightbulb, MessageSquare, FileText, Activity, Settings, LogOut, ShieldCheck,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import StatusBar from "./StatusBar";
import AnalysisHistory from "./AnalysisHistory";

const NAV_ITEMS = [
  { to: "/",               label: "Dashboard",           icon: LayoutDashboard },
  { to: "/forecasting",    label: "Forecasting",         icon: TrendingUp },
  { to: "/anomalies",      label: "Anomaly Detection",   icon: AlertTriangle },
  { to: "/waste",          label: "Waste Classification",icon: Trash2 },
  { to: "/simulator",      label: "Cost Simulator",      icon: Sliders },
  { to: "/recommendations",label: "Recommendations",     icon: Lightbulb },
  { to: "/copilot",        label: "AI Copilot",          icon: MessageSquare },
  { to: "/reports",        label: "Executive Reports",   icon: FileText },
  { to: "/monitoring",     label: "Model Monitoring",    icon: Activity },
  { to: "/settings",       label: "Settings",            icon: Settings },
];

export default function AppShell() {
  const { logout } = useAuth();
  const navigate   = useNavigate();

  function handleLogout() { logout(); navigate("/login"); }

  return (
    <div className="flex h-screen bg-bg-base">
      <aside className="w-60 flex-shrink-0 border-r border-border-subtle bg-bg-surface flex flex-col">
        {/* Logo */}
        <div className="flex items-center gap-2 px-5 py-4 border-b border-border-subtle">
          <ShieldCheck className="w-6 h-6 text-signal-mint" strokeWidth={2} />
          <div>
            <div className="font-semibold text-text-primary text-sm leading-tight">CostGuard AI</div>
            <div className="text-[11px] text-text-tertiary font-data">FinOps Platform</div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="py-3 px-2">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-md text-sm mb-0.5 transition-colors ${
                  isActive
                    ? "bg-bg-raised text-signal-mint"
                    : "text-text-secondary hover:bg-bg-hover hover:text-text-primary"
                }`}
            >
              <Icon className="w-4 h-4 flex-shrink-0" strokeWidth={2} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Analysis History - Feature 4 */}
        <div className="flex-1 overflow-y-auto">
          <AnalysisHistory />
        </div>

        {/* Status bar */}
        <StatusBar />

        {/* Logout */}
        <div className="px-2 pb-3 border-t border-border-subtle pt-2">
          <button onClick={handleLogout}
            className="flex items-center gap-3 px-3 py-2 rounded-md text-sm w-full text-text-secondary hover:bg-bg-hover hover:text-signal-red transition-colors">
            <LogOut className="w-4 h-4" strokeWidth={2} />
            <span>Log out</span>
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
