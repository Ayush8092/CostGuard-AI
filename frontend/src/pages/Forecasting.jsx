import { useEffect, useState } from "react";
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend, BarChart, Bar,
} from "recharts";
import { TrendingUp, Target, BarChart2, Clock } from "lucide-react";
import { forecastApi, monitoringApi } from "../api/client";
import { C, TOOLTIP_STYLE, SERVICE_COLORS } from "../components/ChartColors";
import { LoadingState, ErrorState, EmptyState, PageHeader } from "../components/Status";

const SERVICES = ["EC2", "S3", "RDS", "Lambda"];

function MetricCard({ label, value, sub, accent, icon: Icon }) {
  const color = accent === "mint" ? "text-signal-mint" : accent === "amber" ? "text-signal-amber" : "text-text-primary";
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-text-secondary">{label}</span>
        {Icon && <Icon className="w-3.5 h-3.5 text-text-tertiary" />}
      </div>
      <div className={`font-data text-xl font-semibold ${color}`}>{value ?? "—"}</div>
      {sub && <div className="text-[11px] text-text-tertiary mt-0.5">{sub}</div>}
    </div>
  );
}

export default function Forecasting() {
  const [level, setLevel] = useState("org_total");
  const [service, setService] = useState("EC2");
  const [data, setData] = useState([]);
  const [allServices, setAllServices] = useState({});
  const [metrics, setMetrics] = useState(null);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    setStatus("loading");
    Promise.all([
      forecastApi.get(level, level === "per_service" ? service : null),
      monitoringApi.registry("forecast"),
      // Load all services for comparison bar chart
      ...SERVICES.map(s => forecastApi.get("per_service", s).catch(() => null)),
    ]).then(([forecastRes, registryRes, ...svcResponses]) => {
      setData(forecastRes.data);
      setMetrics(registryRes.data?.[0]?.evaluation_metrics ?? null);
      const svcData = {};
      SERVICES.forEach((s, i) => {
        if (svcResponses[i]) svcData[s] = svcResponses[i].data;
      });
      setAllServices(svcData);
      setStatus("ready");
    }).catch(() => setStatus("error"));
  }, [level, service]);

  // Build comparison bar chart data — latest forecast value per service
  const svcComparison = SERVICES.map(s => ({
    service: s,
    forecast: allServices[s]?.[0]?.forecast ?? 0,
    ci_lower: allServices[s]?.[0]?.ci_lower ?? 0,
    ci_upper: allServices[s]?.[0]?.ci_upper ?? 0,
  }));

  // Compute CI width as uncertainty proxy
  const ciWidth = data.length > 0
    ? ((data[data.length - 1]?.ci_upper - data[data.length - 1]?.ci_lower) / Math.max(data[data.length - 1]?.forecast, 1) * 100).toFixed(1)
    : null;

  const lastForecast = data[data.length - 1];

  return (
    <div>
      <PageHeader title="Forecasting" description="Hierarchical cost forecasts — XGBoost quantile regression">
        <div className="flex gap-2">
          <select value={level} onChange={e => setLevel(e.target.value)}
            className="bg-bg-raised border border-border-subtle rounded-md text-sm px-3 py-1.5 text-text-primary">
            <option value="org_total">Org total</option>
            <option value="per_service">Per service</option>
          </select>
          {level === "per_service" && (
            <select value={service} onChange={e => setService(e.target.value)}
              className="bg-bg-raised border border-border-subtle rounded-md text-sm px-3 py-1.5 text-text-primary">
              {SERVICES.map(s => <option key={s}>{s}</option>)}
            </select>
          )}
        </div>
      </PageHeader>

      <div className="px-8 py-6 space-y-6">
        {/* Model metrics row */}
        {metrics && (
          <div className="grid grid-cols-6 gap-4">
            <MetricCard label="Model MAPE" value={`${metrics.mape}%`} accent="mint" icon={Target} sub="lower is better" />
            <MetricCard label="Naive MAPE" value={`${metrics.naive_mape}%`} sub="persistence baseline" />
            <MetricCard label="Error Reduction" value={`${metrics.error_reduction_pct?.toFixed(1)}%`} accent="mint" icon={TrendingUp} sub="vs naive baseline" />
            <MetricCard label="MAE" value={`$${metrics.mae}`} icon={BarChart2} />
            <MetricCard label="RMSE" value={`$${metrics.rmse}`} />
            <MetricCard label="CI Width" value={ciWidth ? `±${ciWidth}%` : "—"} sub="forecast uncertainty" icon={Clock} />
          </div>
        )}

        {/* Main forecast chart */}
        <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
          <h2 className="text-sm font-medium text-text-primary mb-4">
            {level === "org_total" ? "Organization Total Forecast" : `${service} Forecast`}
            {lastForecast && (
              <span className="ml-3 text-xs text-text-tertiary font-data">
                Next: ${lastForecast.forecast?.toFixed(2)} [{lastForecast.ci_lower?.toFixed(2)} – {lastForecast.ci_upper?.toFixed(2)}]
              </span>
            )}
          </h2>
          {status === "loading" && <LoadingState />}
          {status === "error" && <ErrorState />}
          {status === "ready" && data.length === 0 && <EmptyState title="No forecast data yet" message="Run the nightly job to generate forecasts." />}
          {status === "ready" && data.length > 0 && (
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
                <XAxis dataKey="forecast_date" stroke={C.text} fontSize={10} tickFormatter={v => v?.slice(5)} />
                <YAxis stroke={C.text} fontSize={10} />
                <Tooltip {...TOOLTIP_STYLE} formatter={(v, name) => [`$${Number(v).toFixed(2)}`, name]} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Area type="monotone" dataKey="ci_upper" stroke="none" fill={C.blue} fillOpacity={0.12} name="CI Upper" />
                <Area type="monotone" dataKey="ci_lower" stroke="none" fill={C.surface} fillOpacity={1} name="CI Lower" />
                <Line type="monotone" dataKey="forecast" stroke={C.mint} strokeWidth={2.5} dot={false} name="Forecast" />
                <Line type="monotone" dataKey="naive_baseline" stroke={C.text} strokeWidth={1.5} strokeDasharray="4 4" dot={false} name="Naive Baseline" />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Forecast by service comparison */}
        <div className="grid grid-cols-2 gap-6">
          <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
            <h2 className="text-sm font-medium text-text-primary mb-4">Forecast by Service</h2>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={svcComparison}>
                <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
                <XAxis dataKey="service" stroke={C.text} fontSize={11} />
                <YAxis stroke={C.text} fontSize={11} />
                <Tooltip {...TOOLTIP_STYLE} formatter={v => [`$${Number(v).toFixed(2)}`]} />
                <Bar dataKey="forecast" name="Forecast" radius={[4,4,0,0]}>
                  {svcComparison.map((entry, i) => (
                    <rect key={i} fill={SERVICE_COLORS[entry.service] || C.blue} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
            <h2 className="text-sm font-medium text-text-primary mb-3">Forecast Horizon Details</h2>
            <div className="space-y-3">
              {data.slice(-5).map((row, i) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <span className="text-text-secondary font-data">{row.forecast_date?.slice(0, 10)}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-text-tertiary font-data">[{row.ci_lower?.toFixed(1)} –</span>
                    <span className="text-signal-mint font-data font-semibold">${row.forecast?.toFixed(2)}</span>
                    <span className="text-text-tertiary font-data">– {row.ci_upper?.toFixed(1)}]</span>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 pt-4 border-t border-border-subtle">
              <p className="text-[11px] text-text-tertiary">
                Algorithm: XGBoost quantile regression (5th/50th/95th percentile). CI width reflects
                in-sample residual spread calibrated for out-of-sample coverage.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
