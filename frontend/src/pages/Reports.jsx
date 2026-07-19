import { useEffect, useState } from "react";
import { Calendar, Download, Mail, TrendingUp, AlertTriangle, PiggyBank, Server, FileText, DollarSign } from "lucide-react";
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { reportsApi } from "../api/client";
import { C, TOOLTIP_STYLE } from "../components/ChartColors";
import { LoadingState, ErrorState, EmptyState, PageHeader } from "../components/Status";

function MetricBlock({ label, value, sub, accent, icon: Icon }) {
  const color = accent === "mint" ? "text-signal-mint" : accent === "red" ? "text-signal-red" : accent === "amber" ? "text-signal-amber" : "text-text-primary";
  return (
    <div className="bg-bg-raised rounded-lg p-4 border border-border-subtle">
      <div className="flex items-center gap-1.5 mb-1">
        {Icon && <Icon className="w-3.5 h-3.5 text-text-tertiary" />}
        <span className="text-xs text-text-secondary">{label}</span>
      </div>
      <div className={`font-data text-xl font-semibold ${color}`}>{value ?? "—"}</div>
      {sub && <div className="text-[11px] text-text-tertiary mt-0.5">{sub}</div>}
    </div>
  );
}

function downloadCSV(report) {
  const rows = [
    ["Metric", "Value"],
    ["Period", `${report.period_start} to ${report.period_end}`],
    ...Object.entries(report.metrics_snapshot).map(([k, v]) => [k, JSON.stringify(v)]),
  ];
  const csv = rows.map(r => r.join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `costguard_report_${report.period_start}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function downloadJSON(report) {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `costguard_report_${report.period_start}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function Reports() {
  const [reports, setReports] = useState([]);
  const [selected, setSelected] = useState(null);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    reportsApi.list()
      .then(r => { setReports(r.data); setSelected(r.data[0] || null); setStatus("ready"); })
      .catch(() => setStatus("error"));
  }, []);

  if (status === "loading") return <LoadingState />;
  if (status === "error") return <ErrorState />;

  const snap = selected?.metrics_snapshot || {};

  // Build a spend trend from reports history
  const spendTrend = reports.slice().reverse().map(r => ({
    period: r.period_start?.slice(5),
    spend: r.metrics_snapshot?.this_week_total_cost || 0,
    prior: r.metrics_snapshot?.prior_week_total_cost || 0,
  }));

  // Top services from snapshot
  const topServices = snap.top_services_by_cost
    ? Object.entries(snap.top_services_by_cost).map(([name, cost]) => ({ name, cost })).sort((a,b) => b.cost - a.cost)
    : [];

  const pctChange = snap.pct_change_vs_prior_week;
  const pctColor = pctChange > 0 ? "text-signal-red" : "text-signal-mint";

  return (
    <div>
      <PageHeader title="Executive Reports" description="AI-generated weekly summaries grounded in real metrics only" />
      <div className="px-8 py-6">
        <div className="grid grid-cols-4 gap-6">

          {/* Report history list */}
          <div className="col-span-1">
            <h2 className="text-xs uppercase text-text-secondary mb-3">Report History</h2>
            {reports.length === 0 ? (
              <EmptyState title="No reports yet" message="Generated weekly by the scheduled job." />
            ) : (
              <div className="space-y-1.5">
                {reports.map(r => (
                  <button key={r.id} onClick={() => setSelected(r)}
                    className={`w-full text-left flex items-center gap-2 px-3 py-2.5 rounded-md text-sm border transition-colors ${
                      selected?.id === r.id
                        ? "bg-bg-raised border-signal-mint text-text-primary"
                        : "border-border-subtle text-text-secondary hover:bg-bg-hover"
                    }`}>
                    <Calendar className="w-3.5 h-3.5 flex-shrink-0" />
                    <div>
                      <div className="font-data text-xs">{r.period_start}</div>
                      <div className="text-[11px] text-text-tertiary">to {r.period_end}</div>
                    </div>
                  </button>
                ))}
              </div>
            )}

            {/* Spend trend mini chart */}
            {spendTrend.length > 1 && (
              <div className="mt-6">
                <h3 className="text-xs text-text-secondary mb-2">Weekly Spend Trend</h3>
                <ResponsiveContainer width="100%" height={100}>
                  <LineChart data={spendTrend}>
                    <XAxis dataKey="period" hide />
                    <YAxis hide />
                    <Tooltip {...TOOLTIP_STYLE} formatter={v => [`$${Number(v).toFixed(2)}`]} />
                    <Line type="monotone" dataKey="spend" stroke={C.mint} strokeWidth={2} dot={false} name="This week" />
                    <Line type="monotone" dataKey="prior" stroke={C.text} strokeWidth={1} strokeDasharray="3 3" dot={false} name="Prior week" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Report detail */}
          <div className="col-span-3">
            {!selected ? (
              <EmptyState title="Select a report" />
            ) : (
              <div className="space-y-5">
                {/* Header + download buttons */}
                <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h2 className="text-base font-semibold text-text-primary">
                        Weekly Executive Summary
                      </h2>
                      <p className="text-xs text-text-tertiary font-data mt-0.5">
                        {selected.period_start} — {selected.period_end}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <button onClick={() => downloadCSV(selected)}
                        className="flex items-center gap-1.5 text-xs bg-bg-raised border border-border-subtle rounded-md px-3 py-1.5 text-text-secondary hover:text-text-primary hover:bg-bg-hover">
                        <Download className="w-3.5 h-3.5" /> Download CSV
                      </button>
                      <button onClick={() => downloadJSON(selected)}
                        className="flex items-center gap-1.5 text-xs bg-bg-raised border border-border-subtle rounded-md px-3 py-1.5 text-text-secondary hover:text-text-primary hover:bg-bg-hover">
                        <FileText className="w-3.5 h-3.5" /> Download JSON
                      </button>
                      <button onClick={() => {
                        const subject = encodeURIComponent(`CostGuard Weekly Report ${selected.period_start}`);
                        const body = encodeURIComponent(selected.narrative);
                        window.open(`mailto:?subject=${subject}&body=${body}`);
                      }}
                        className="flex items-center gap-1.5 text-xs bg-signal-mint/10 border border-signal-mint/30 rounded-md px-3 py-1.5 text-signal-mint hover:bg-signal-mint/20">
                        <Mail className="w-3.5 h-3.5" /> Email Report
                      </button>
                    </div>
                  </div>

                  {/* Narrative */}
                  <p className="text-sm text-text-secondary whitespace-pre-wrap leading-relaxed">
                    {selected.narrative}
                  </p>
                </div>

                {/* KPI metrics grid */}
                <div className="grid grid-cols-4 gap-4">
                  <MetricBlock label="Total Spend" value={snap.this_week_total_cost != null ? `$${snap.this_week_total_cost?.toLocaleString()}` : "—"} accent="default" icon={DollarSign} />
                  <MetricBlock label="vs Prior Week"
                    value={pctChange != null ? `${pctChange > 0 ? "+" : ""}${pctChange?.toFixed(1)}%` : "—"}
                    accent={pctChange > 0 ? "red" : "mint"} icon={TrendingUp}
                    sub={snap.prior_week_total_cost != null ? `Prior: $${snap.prior_week_total_cost?.toLocaleString()}` : null} />
                  <MetricBlock label="Active Resources" value={snap.active_resource_count} icon={Server} />
                  <MetricBlock label="Anomalies" value={snap.anomaly_count_this_week ?? snap.anomalies_by_severity ? Object.values(snap.anomalies_by_severity || {}).reduce((a,b) => a+b, 0) : "—"} accent="amber" icon={AlertTriangle} />
                </div>

                {/* Waste + savings row */}
                {snap.waste_bucket_counts && (
                  <div className="grid grid-cols-5 gap-4">
                    {Object.entries(snap.waste_bucket_counts).map(([bucket, count]) => (
                      <MetricBlock key={bucket} label={bucket} value={count}
                        accent={bucket === "Critical Waste" ? "red" : bucket === "Idle" ? "amber" : bucket === "Healthy" ? "mint" : "default"}
                        icon={bucket.includes("Waste") || bucket === "Idle" ? PiggyBank : CheckIcon} />
                    ))}
                  </div>
                )}

                {/* Charts row */}
                {topServices.length > 0 && (
                  <div className="grid grid-cols-2 gap-5">
                    <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
                      <h3 className="text-xs font-medium text-text-primary mb-3">Top Services by Cost</h3>
                      <ResponsiveContainer width="100%" height={160}>
                        <BarChart data={topServices} layout="vertical">
                          <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
                          <XAxis type="number" stroke={C.text} fontSize={10} />
                          <YAxis type="category" dataKey="name" stroke={C.text} fontSize={10} width={80} />
                          <Tooltip {...TOOLTIP_STYLE} formatter={v => [`$${Number(v).toFixed(2)}`]} />
                          <Bar dataKey="cost" fill={C.mint} radius={[0,3,3,0]} name="Cost ($)" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                    <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
                      <h3 className="text-xs font-medium text-text-primary mb-3">Anomalies by Severity</h3>
                      {snap.anomalies_by_severity ? (
                        <ResponsiveContainer width="100%" height={160}>
                          <BarChart data={Object.entries(snap.anomalies_by_severity).map(([k,v]) => ({ sev: k, count: v }))}>
                            <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
                            <XAxis dataKey="sev" stroke={C.text} fontSize={10} />
                            <YAxis stroke={C.text} fontSize={10} />
                            <Tooltip {...TOOLTIP_STYLE} />
                            <Bar dataKey="count" radius={[4,4,0,0]} name="Count">
                              {Object.entries(snap.anomalies_by_severity).map(([k], i) => (
                                <Cell key={i} fill={k === "critical" ? C.red : k === "high" ? C.amber : C.blue} />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      ) : (
                        <div className="text-xs text-text-tertiary py-6 text-center">No anomaly breakdown in this report</div>
                      )}
                    </div>
                  </div>
                )}

                {/* Raw metrics toggle */}
                <details className="bg-bg-surface border border-border-subtle rounded-lg">
                  <summary className="px-4 py-3 text-xs text-text-secondary cursor-pointer hover:text-text-primary">
                    View raw metrics snapshot (auditable source of truth for this narrative)
                  </summary>
                  <pre className="px-4 pb-4 font-data text-[11px] text-text-tertiary overflow-x-auto">
                    {JSON.stringify(snap, null, 2)}
                  </pre>
                </details>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function CheckIcon(props) {
  return <svg {...props} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M20 6L9 17l-5-5"/></svg>;
}
