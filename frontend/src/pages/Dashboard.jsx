import { useEffect, useState } from "react";
import {
  DollarSign, TrendingUp, AlertTriangle, PiggyBank, Server,
  Brain, CheckCircle2, Zap, RefreshCw, Sparkles,
} from "lucide-react";
import {
  LineChart, Line, PieChart, Pie, Cell, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, ComposedChart,
} from "recharts";
import {
  dashboardApi, forecastApi, anomaliesApi, wasteApi,
  recommendationsApi, businessMetricsApi, insightsApi,
} from "../api/client";
import { C, TOOLTIP_STYLE, SERVICE_COLORS } from "../components/ChartColors";
import { LoadingState, ErrorState, PageHeader } from "../components/Status";
import ConfidenceBadge from "../components/ConfidenceBadge";
import { useDataset } from "../context/DatasetContext";

function KpiCard({ label, value, sub, accent = "default", icon: Icon }) {
  const colors = {
    default: "text-text-primary", mint: "text-signal-mint",
    amber: "text-signal-amber", red: "text-signal-red", blue: "text-signal-blue",
  };
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-text-secondary uppercase tracking-wide">{label}</span>
        {Icon && <Icon className="w-4 h-4 text-text-tertiary" strokeWidth={2} />}
      </div>
      <div className={`font-data text-2xl font-semibold ${colors[accent]}`}>{value ?? "—"}</div>
      {sub && <div className="text-xs text-text-tertiary mt-1">{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const { activeDataset } = useDataset();
  const [kpis, setKpis]         = useState(null);
  const [forecast, setForecast] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [waste, setWaste]       = useState([]);
  const [recs, setRecs]         = useState([]);
  const [bm, setBm]             = useState(null);
  const [insight, setInsight]   = useState(null);
  const [insightLoading, setInsightLoading] = useState(false);
  const [status, setStatus]     = useState("loading");

  useEffect(() => {
    setStatus("loading");
    Promise.all([
      dashboardApi.get(),
      forecastApi.get("org_total"),
      anomaliesApi.list(null, 10),
      wasteApi.list(),
      recommendationsApi.list(),
      businessMetricsApi.get(),
    ]).then(([k, f, an, w, r, b]) => {
      setKpis(k.data);
      setForecast(f.data);
      setAnomalies(an.data);
      setWaste(w.data);
      setRecs(r.data);
      setBm(b.data);
      setStatus("ready");
    }).catch(() => setStatus("error"));

    // Load stored executive insight — read from DB, never calls LLM
    insightsApi.active()
      .then(r => setInsight(r.data))
      .catch(() => setInsight(null));
  }, [activeDataset?.id]);  // re-fetch when active dataset changes

  async function regenerateInsight() {
    setInsightLoading(true);
    try {
      const r = await insightsApi.generate(activeDataset?.id || null);
      setInsight(r.data);
    } catch { }
    finally { setInsightLoading(false); }
  }

  if (status === "loading") return <LoadingState label="Loading dashboard..." />;
  if (status === "error")   return <ErrorState />;

  const serviceCosts = Object.entries(
    waste.reduce((acc, r) => { acc[r.service || "Other"] = (acc[r.service || "Other"] || 0) + 1; return acc; }, {})
  ).map(([name, value]) => ({ name, value }));

  const top5 = [...waste].sort((a, b) => b.waste_score - a.waste_score).slice(0, 5);

  const bucketCounts = waste.reduce((acc, w) => {
    acc[w.bucket] = (acc[w.bucket] || 0) + 1; return acc;
  }, {});

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description={activeDataset ? `Active: ${activeDataset.dataset_name || activeDataset.original_filename}` : "Organization-wide cost overview"}
      />

      <div className="px-8 py-6 space-y-6">

        {/* Executive Insights Card (Feature 3) */}
        <div className="bg-gradient-to-r from-bg-surface to-bg-raised border border-signal-mint/30 rounded-lg p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-signal-mint" />
              <span className="text-sm font-medium text-text-primary">Executive Insights</span>
              {insight && (
                <span className="text-[11px] bg-signal-mint/10 text-signal-mint border border-signal-mint/30 rounded px-1.5 py-0.5 font-data">
                  {activeDataset?.dataset_name || "Current Analysis"}
                </span>
              )}
            </div>
            <button
              onClick={regenerateInsight}
              disabled={insightLoading}
              className="flex items-center gap-1.5 text-[11px] text-text-secondary border border-border-subtle rounded px-2 py-1 hover:bg-bg-hover disabled:opacity-50">
              <RefreshCw className={`w-3 h-3 ${insightLoading ? "animate-spin" : ""}`} />
              {insightLoading ? "Generating..." : "Re-run"}
            </button>
          </div>

          {insight ? (
            <p className="text-sm text-text-secondary whitespace-pre-wrap leading-relaxed">
              {insight.insight_text}
            </p>
          ) : (
            <div className="space-y-2">
              {[
                `Cloud spend (30d): $${kpis?.total_spend_30d?.toLocaleString() ?? "—"}`,
                `Active resources: ${kpis?.active_resource_count ?? "—"}`,
                `Anomalies detected: ${kpis?.anomaly_count_30d ?? "—"}`,
                `Potential monthly savings: $${kpis?.savings_identified?.toLocaleString() ?? "—"}`,
              ].map((line, i) => (
                <div key={i} className="flex items-center gap-2 text-sm text-text-secondary">
                  <span className="text-signal-mint">•</span> {line}
                </div>
              ))}
              <p className="text-[11px] text-text-tertiary mt-2">
                Upload a dataset and click "Re-run" to generate AI-written insights.
              </p>
            </div>
          )}
        </div>

        {/* KPI Row */}
        <div className="grid grid-cols-5 gap-4">
          <KpiCard label="Total Spend (30d)"   value={`$${kpis.total_spend_30d?.toLocaleString()}`} icon={DollarSign} />
          <KpiCard label="Monthly Savings"     value={`$${bm?.estimated_monthly_savings?.toLocaleString() ?? "—"}`} accent="mint" icon={PiggyBank} sub="identified by AI" />
          <KpiCard label="Forecast (next)"     value={forecast[0] ? `$${forecast[0].forecast?.toLocaleString()}` : "—"} accent="blue" icon={TrendingUp} />
          <KpiCard label="Anomalies (30d)"     value={kpis.anomaly_count_30d} accent={kpis.anomaly_count_30d > 0 ? "amber" : "default"} icon={AlertTriangle} />
          <KpiCard label="Active Resources"    value={kpis.active_resource_count} icon={Server} sub={`${bm?.optimization_opportunity_rate_pct?.toFixed(1) ?? "—"}% need attention`} />
        </div>

        {/* Business Metrics Row */}
        {bm && (
          <div className="grid grid-cols-4 gap-4">
            <KpiCard label="Waste Coverage"         value={`${bm.waste_detection_coverage_pct?.toFixed(1)}%`} accent="mint" icon={CheckCircle2} sub="resources with recommendation" />
            <KpiCard label="Forecast Error Reduction" value={bm.forecast_error_reduction_pct ? `${bm.forecast_error_reduction_pct?.toFixed(1)}%` : "—"} accent="mint" icon={TrendingUp} sub="vs naive baseline" />
            <KpiCard label="Avg Confidence"         value={`${bm.avg_recommendation_confidence_pct?.toFixed(1)}%`} accent="mint" icon={Brain} sub="ML-derived, not LLM" />
            <KpiCard label="Opportunity Rate"       value={`${bm.optimization_opportunity_rate_pct?.toFixed(1)}%`} accent="amber" icon={Zap} sub="of resources need optimization" />
          </div>
        )}

        {/* Charts Row */}
        <div className="grid grid-cols-2 gap-6">
          <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
            <h2 className="text-sm font-medium text-text-primary mb-4">Cost Trend + Forecast</h2>
            {forecast.length === 0 ? (
              <div className="text-xs text-text-tertiary py-8 text-center">Run nightly job to populate forecasts</div>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <ComposedChart data={forecast}>
                  <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
                  <XAxis dataKey="forecast_date" stroke={C.text} fontSize={10} tickFormatter={v => v?.slice(5)} />
                  <YAxis stroke={C.text} fontSize={10} />
                  <Tooltip {...TOOLTIP_STYLE} />
                  <Area type="monotone" dataKey="ci_upper" stroke="none" fill={C.blue} fillOpacity={0.12} name="CI Upper" />
                  <Area type="monotone" dataKey="ci_lower" stroke="none" fill={C.surface} fillOpacity={1} name="CI Lower" />
                  <Line type="monotone" dataKey="forecast" stroke={C.mint} strokeWidth={2} dot={false} name="Forecast" />
                  <Line type="monotone" dataKey="naive_baseline" stroke={C.text} strokeWidth={1} strokeDasharray="4 4" dot={false} name="Naive" />
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
            <h2 className="text-sm font-medium text-text-primary mb-4">Resources by Service</h2>
            {serviceCosts.length === 0 ? (
              <div className="text-xs text-text-tertiary py-8 text-center">No data yet</div>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie data={serviceCosts} cx="50%" cy="50%" innerRadius={60} outerRadius={90}
                    dataKey="value" nameKey="name" paddingAngle={3}
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    labelLine={{ stroke: C.text }} fontSize={11}>
                    {serviceCosts.map((entry, i) => (
                      <Cell key={i} fill={SERVICE_COLORS[entry.name] || Object.values(SERVICE_COLORS)[i % 4]} />
                    ))}
                  </Pie>
                  <Tooltip {...TOOLTIP_STYLE} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Waste distribution + top 5 */}
        <div className="grid grid-cols-2 gap-6">
          <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
            <h2 className="text-sm font-medium text-text-primary mb-4">Waste Bucket Distribution</h2>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={Object.entries(bucketCounts).map(([name, value]) => ({ name, value }))}>
                <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
                <XAxis dataKey="name" stroke={C.text} fontSize={10} />
                <YAxis stroke={C.text} fontSize={10} />
                <Tooltip {...TOOLTIP_STYLE} />
                <Bar dataKey="value" name="Resources" radius={[4,4,0,0]}>
                  {Object.entries(bucketCounts).map(([name], i) => (
                    <Cell key={i} fill={
                      name === "Healthy" ? C.mint : name === "Underutilized" ? C.blue :
                      name === "Idle" ? C.amber : C.red
                    } />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
            <h2 className="text-sm font-medium text-text-primary mb-4">Top 5 by Waste Score</h2>
            <div className="space-y-3">
              {top5.length === 0 && <div className="text-xs text-text-tertiary py-4 text-center">No data yet</div>}
              {top5.map((r, i) => (
                <div key={i} className="flex items-center justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-data text-text-primary truncate">{r.resource_id}</div>
                    <div className="text-[11px] text-text-tertiary">{r.bucket}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-20 h-1.5 bg-bg-raised rounded-full overflow-hidden">
                      <div className="h-full rounded-full bg-signal-red" style={{ width: `${r.waste_score}%` }} />
                    </div>
                    <span className="font-data text-xs text-signal-red w-8 text-right">{r.waste_score?.toFixed(0)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Recent anomalies */}
        <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
          <h2 className="text-sm font-medium text-text-primary mb-4">Recent Anomalies</h2>
          {anomalies.length === 0 ? (
            <div className="text-xs text-text-tertiary py-4 text-center">No anomalies detected yet</div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border-subtle text-text-tertiary uppercase">
                  <th className="text-left pb-2">Resource</th>
                  <th className="text-left pb-2">Severity</th>
                  <th className="text-left pb-2">Score</th>
                  <th className="text-left pb-2">Date</th>
                </tr>
              </thead>
              <tbody>
                {anomalies.slice(0, 5).map((a, i) => (
                  <tr key={i} className="border-b border-border-subtle last:border-0">
                    <td className="py-2 font-data text-text-primary">{a.resource_id}</td>
                    <td className="py-2">
                      <span className={`px-2 py-0.5 rounded text-[11px] border ${
                        a.severity === "critical" ? "text-signal-red bg-signal-red/10 border-signal-red/30" :
                        a.severity === "high" ? "text-signal-amber bg-signal-amber/10 border-signal-amber/30" :
                        "text-text-secondary bg-bg-raised border-border-subtle"
                      }`}>{a.severity}</span>
                    </td>
                    <td className="py-2 font-data text-text-primary">{a.incident_score?.toFixed(1)}</td>
                    <td className="py-2 text-text-secondary font-data">{a.date?.slice(0,10)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Latest recommendations */}
        <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
          <h2 className="text-sm font-medium text-text-primary mb-4">Latest Recommendations</h2>
          {recs.length === 0 ? (
            <div className="text-xs text-text-tertiary py-4 text-center">No recommendations yet</div>
          ) : (
            <div className="space-y-2">
              {recs.slice(0, 4).map((r, i) => (
                <div key={i} className="flex items-center justify-between gap-4 bg-bg-raised rounded-md px-3 py-2.5">
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-text-primary font-data truncate">{r.action}</div>
                    <div className="text-[11px] text-text-tertiary mt-0.5">{r.reason}</div>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <ConfidenceBadge confidence={r.confidence} />
                    <span className="font-data text-sm text-signal-mint font-semibold">${r.estimated_savings?.toFixed(0)}/mo</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
