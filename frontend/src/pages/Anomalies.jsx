import { useEffect, useState } from "react";
import { AlertTriangle, Info, Activity } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, LineChart, Line,
} from "recharts";
import { anomaliesApi } from "../api/client";
import { C, TOOLTIP_STYLE } from "../components/ChartColors";
import { LoadingState, ErrorState, EmptyState, PageHeader } from "../components/Status";

const SEV = {
  critical: "text-signal-red bg-signal-red/10 border-signal-red/30",
  high:     "text-signal-amber bg-signal-amber/10 border-signal-amber/30",
  medium:   "text-signal-blue bg-signal-blue/10 border-signal-blue/30",
  low:      "text-text-secondary bg-bg-raised border-border-subtle",
};
const SEV_COLOR = { critical: C.red, high: C.amber, medium: C.blue, low: C.text };

export default function Anomalies() {
  const [anomalies, setAnomalies] = useState([]);
  const [sevFilter, setSevFilter] = useState(null);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    setStatus("loading");
    anomaliesApi.list(sevFilter, 200)
      .then(r => { setAnomalies(r.data); setStatus("ready"); })
      .catch(() => setStatus("error"));
  }, [sevFilter]);

  const filtered = sevFilter ? anomalies.filter(a => a.severity === sevFilter) : anomalies;

  // Severity summary counts
  const counts = anomalies.reduce((acc, a) => { acc[a.severity] = (acc[a.severity] || 0) + 1; return acc; }, {});

  // Anomalies by service distribution
  const byService = Object.entries(
    anomalies.reduce((acc, a) => {
      const svc = a.dimension_scores ? Object.keys(a.dimension_scores)[0] || "unknown" : "unknown";
      acc[a.resource_id?.split("-")[0]?.toUpperCase() || "OTHER"] =
        (acc[a.resource_id?.split("-")[0]?.toUpperCase() || "OTHER"] || 0) + 1;
      return acc;
    }, {})
  ).map(([name, value]) => ({ name, value }));

  // Score distribution buckets
  const scoreDistribution = [
    { range: "0-20",  count: anomalies.filter(a => a.incident_score < 20).length },
    { range: "20-30", count: anomalies.filter(a => a.incident_score >= 20 && a.incident_score < 30).length },
    { range: "30-40", count: anomalies.filter(a => a.incident_score >= 30 && a.incident_score < 40).length },
    { range: "40-50", count: anomalies.filter(a => a.incident_score >= 40 && a.incident_score < 50).length },
    { range: "50+",   count: anomalies.filter(a => a.incident_score >= 50).length },
  ];

  // Most affected resources
  const topResources = Object.entries(
    anomalies.reduce((acc, a) => { acc[a.resource_id] = (acc[a.resource_id] || 0) + 1; return acc; }, {})
  ).sort((a, b) => b[1] - a[1]).slice(0, 5);

  const hasRealData = anomalies.some(a => !a.is_ground_truth_eval);

  return (
    <div>
      <PageHeader title="Anomaly Detection" description="Multi-dimensional cost, CPU, memory, network and disk anomaly scoring">
        <select value={sevFilter ?? ""} onChange={e => setSevFilter(e.target.value || null)}
          className="bg-bg-raised border border-border-subtle rounded-md text-sm px-3 py-1.5 text-text-primary">
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </PageHeader>

      <div className="px-8 py-6 space-y-6">
        {hasRealData && (
          <div className="flex items-start gap-2 bg-signal-blue/10 border border-signal-blue/30 rounded-lg px-4 py-3 text-sm text-text-secondary">
            <Info className="w-4 h-4 text-signal-blue flex-shrink-0 mt-0.5" />
            <span>Runs <strong className="text-text-primary">unsupervised</strong> on real data — candidates flagged for human review. Precision/recall accuracy is only reported against the synthetic demo dataset where ground truth is known.</span>
          </div>
        )}

        {/* Severity count cards */}
        <div className="grid grid-cols-4 gap-4">
          {["critical","high","medium","low"].map(sev => (
            <button key={sev} onClick={() => setSevFilter(sevFilter === sev ? null : sev)}
              className={`text-left rounded-lg border p-4 transition-colors ${sevFilter === sev ? SEV[sev] : "border-border-subtle bg-bg-surface hover:bg-bg-hover"}`}>
              <div className="flex items-center gap-2 mb-1">
                <AlertTriangle className="w-3.5 h-3.5" strokeWidth={2} />
                <span className="text-xs capitalize">{sev}</span>
              </div>
              <div className="font-data text-2xl font-semibold text-text-primary">{counts[sev] || 0}</div>
              <div className="text-[11px] text-text-tertiary mt-0.5">anomalies</div>
            </button>
          ))}
        </div>

        {/* Charts row */}
        <div className="grid grid-cols-3 gap-6">
          <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
            <h2 className="text-sm font-medium text-text-primary mb-4">Score Distribution</h2>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={scoreDistribution}>
                <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
                <XAxis dataKey="range" stroke={C.text} fontSize={10} />
                <YAxis stroke={C.text} fontSize={10} />
                <Tooltip {...TOOLTIP_STYLE} />
                <Bar dataKey="count" fill={C.amber} name="Anomalies" radius={[3,3,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
            <h2 className="text-sm font-medium text-text-primary mb-4">By Resource Type</h2>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={byService} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
                <XAxis type="number" stroke={C.text} fontSize={10} />
                <YAxis type="category" dataKey="name" stroke={C.text} fontSize={10} width={50} />
                <Tooltip {...TOOLTIP_STYLE} />
                <Bar dataKey="value" fill={C.blue} name="Count" radius={[0,3,3,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
            <h2 className="text-sm font-medium text-text-primary mb-3">Most Affected Resources</h2>
            <div className="space-y-3">
              {topResources.length === 0 && <div className="text-xs text-text-tertiary py-4 text-center">No data yet</div>}
              {topResources.map(([rid, count], i) => (
                <div key={i} className="flex items-center justify-between gap-2">
                  <span className="text-xs font-data text-text-primary truncate flex-1">{rid}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-16 h-1.5 bg-bg-raised rounded-full overflow-hidden">
                      <div className="h-full bg-signal-amber rounded-full" style={{ width: `${(count / topResources[0][1]) * 100}%` }} />
                    </div>
                    <span className="text-xs font-data text-signal-amber w-4">{count}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Main anomalies table */}
        {status === "loading" && <LoadingState />}
        {status === "error" && <ErrorState />}
        {status === "ready" && filtered.length === 0 && <EmptyState title="No anomalies flagged" message="The nightly job will populate this after analyzing recent data." />}
        {status === "ready" && filtered.length > 0 && (
          <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-subtle text-text-secondary text-xs uppercase">
                  <th className="text-left px-4 py-3">Resource</th>
                  <th className="text-left px-4 py-3">Date</th>
                  <th className="text-left px-4 py-3">Severity</th>
                  <th className="text-left px-4 py-3">Incident Score</th>
                  <th className="text-left px-4 py-3">Dimension Breakdown</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a, i) => (
                  <tr key={i} className="border-b border-border-subtle last:border-0 hover:bg-bg-hover">
                    <td className="px-4 py-3 font-data text-text-primary text-xs">{a.resource_id}</td>
                    <td className="px-4 py-3 text-text-secondary font-data text-xs">{a.date?.slice(0,10)}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border ${SEV[a.severity] || SEV.low}`}>
                        <AlertTriangle className="w-3 h-3" />{a.severity}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-bg-raised rounded-full overflow-hidden">
                          <div className="h-full rounded-full" style={{
                            width: `${Math.min(a.incident_score * 2, 100)}%`,
                            background: SEV_COLOR[a.severity] || C.text,
                          }} />
                        </div>
                        <span className="font-data text-xs text-text-primary">{a.incident_score?.toFixed(1)}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-3 text-xs font-data text-text-tertiary flex-wrap">
                        {Object.entries(a.dimension_scores || {}).map(([dim, score]) => (
                          <span key={dim}>
                            {dim.replace("_avg_pct","").replace("_io","")}: <span className="text-text-secondary">{score != null ? score.toFixed(0) : "—"}</span>
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
