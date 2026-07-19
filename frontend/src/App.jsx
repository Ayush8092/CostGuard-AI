import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { DatasetProvider } from "./context/DatasetContext";
import AppShell from "./components/AppShell";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Forecasting from "./pages/Forecasting";
import Anomalies from "./pages/Anomalies";
import WasteClassification from "./pages/WasteClassification";
import CostSimulator from "./pages/CostSimulator";
import Recommendations from "./pages/Recommendations";
import Copilot from "./pages/Copilot";
import Reports from "./pages/Reports";
import ModelMonitoring from "./pages/ModelMonitoring";
import Settings from "./pages/Settings";

function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={
        <ProtectedRoute>
          <DatasetProvider>
            <AppShell />
          </DatasetProvider>
        </ProtectedRoute>
      }>
        <Route index                   element={<Dashboard />} />
        <Route path="forecasting"      element={<Forecasting />} />
        <Route path="anomalies"        element={<Anomalies />} />
        <Route path="waste"            element={<WasteClassification />} />
        <Route path="simulator"        element={<CostSimulator />} />
        <Route path="recommendations"  element={<Recommendations />} />
        <Route path="copilot"          element={<Copilot />} />
        <Route path="reports"          element={<Reports />} />
        <Route path="monitoring"       element={<ModelMonitoring />} />
        <Route path="settings"         element={<Settings />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}
