import { useEffect, useState } from "react";
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { Trash2, DollarSign, CheckCircle2 } from "lucide-react";
import { wasteApi, recommendationsApi } from "../api/client";
import { C, TOOLTIP_STYLE } from "../components/ChartColors";
import { LoadingState, ErrorState, EmptyState, PageHeader } from "../components/Status";

const BUCKET_STYLES = {
  "Healthy":       { border: "border-signal-mint",  text: "text-signal-mint",  bg: "bg-signal-mint/10",  color: C.mint  },
  "Underutilized": { border: "border-signal-blue",  text: "text-signal-blue",  bg: "bg-signal-blue/10",  color: C.blue  },
  "Idle":          { border: "border-signal-amber", text: "text-signal-amber", bg: "bg-signal-amber/10", color: C.amber },
  "Critical Waste":{ border: "border-signal-red",   text: "text-signal-red",   bg: "bg-signal-red/10",   color: C.red   },
};
const BUCKETS = Object.keys(BUCKET_STYLES);

export default function WasteClassification() {
  const [resources, setResources]   = useState([]);
  const [recs, setRecs]             = useState([]);
  const [bucketFilter, setBucketFilter] = useState(null);
  const [selected, setSelected]     = useState(null);
  const [status, setStatus]         = useState("loading");

  useEffect(() => {
    setStatus("loading");
    Promise.all([wasteApi.list(), recommendationsApi.list()])
      .then(([wr, rr]) => { setResources(wr.data); setRecs(rr.data); setStatus("ready"); })
      .catch(() => setStatus("error"));
  }, []);

  const displayed = bucketFilter ? resources.filter(r => r.bucket === bucketFilter) : resources;

  const counts = BUCKETS.reduce((a, b) => {
    a[b] = resources.filter(r => r.bucket === b).length; return a;
  }, {});

  const pieData = BUCKETS.filter(b => counts[b] > 0).map(b => ({
    name: b, value: counts[b], color: BUCKET_STYLES[b].color,
  }));

  // Savings estimate per bucket
  const recsByResource = recs.reduce((acc, r) => { acc[r.resource_id] = r; return acc; }, {});
  const totalSavings = recs.reduce((s, r) => s + (r.estimated_savings || 0), 0);
  const idleSavings  = recs.filter(r => {
    const res = resources.find(x => x.resource_id === r.resource_id);
    return res && (res.bucket === "Idle" || res.bucket === "Critical Waste");
  }).reduce((s, r) => s + (r.estimated_savings || 0), 0);

  // Waste score distribution bar chart
  const scoreRanges = [
    { range: "0-25 Healthy",  count: resources.filter(r => r.waste_score < 25).length,  fill: C.mint  },
    { range: "25-50 Under",   count: resources.filter(r => r.waste_score >= 25 && r.waste_score < 50).length, fill: C.blue  },
    { range: "50-75 Idle",    count: resources.filter(r => r.waste_score >= 50 && r.waste_score < 75).length, fill: C.amber },
    { range: "75-100 Critical",count: resources.filter(r => r.waste_score >= 75).length, fill: C.red   },
  ];

  return (
    <div>
      <PageHeader title="Waste Classification" description="Resource categorization by composite waste score formula" />
      <div className="px-8 py-6 space-y-6">

        {/* 4 bucket cards */}
        <div className="grid grid-cols-4 gap-4">
          {BUCKETS.map(bucket => {
            const s = BUCKET_STYLES[bucket];
            const active = bucketFilter === bucket;
            return (
              <button key={bucket} onClick={() => setBucketFilter(active ? null : bucket)}
                className={`text-left rounded-lg border-2 p-4 transition-all ${active ? `${s.border} ${s.bg}` : "border-border-subtle bg-bg-surface hover:bg-bg-hover"}`}>
                <div className={`text-xs mb-1 ${active ? s.text : "text-text-secondary"}`}>{bucket}</div>
                <div className="font-data text-3xl font-semibold text-text-primary">{counts[bucket]}</div>
                <div className="text-[11px] text-text-tertiary mt-1">resources</div>
              </button>
            );
          })}
        </div>

        {/* Savings estimate cards */}
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
            <div className="text-xs text-text-secondary mb-1 flex items-center gap-1"><DollarSign className="w-3 h-3" /> Total Savings Identified</div>
            <div className="font-data text-2xl font-semibold text-signal-mint">${totalSavings.toLocaleString(undefined, {maximumFractionDigits: 0})}/mo</div>
            <div className="text-[11px] text-text-tertiary mt-1">across {recs.length} open recommendations</div>
          </div>
          <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
            <div className="text-xs text-text-secondary mb-1 flex items-center gap-1"><Trash2 className="w-3 h-3" /> From Idle/Critical Resources</div>
            <div className="font-data text-2xl font-semibold text-signal-red">${idleSavings.toLocaleString(undefined, {maximumFractionDigits: 0})}/mo</div>
            <div className="text-[11px] text-text-tertiary mt-1">{(counts["Idle"] || 0) + (counts["Critical Waste"] || 0)} resources flagged</div>
          </div>
          <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
            <div className="text-xs text-text-secondary mb-1 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Healthy Resources</div>
            <div className="font-data text-2xl font-semibold text-signal-mint">{counts["Healthy"] || 0}</div>
            <div className="text-[11px] text-text-tertiary mt-1">no action needed</div>
          </div>
        </div>

        {/* Charts row */}
        <div className="grid grid-cols-2 gap-6">
          {/* Donut chart */}
          <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
            <h2 className="text-sm font-medium text-text-primary mb-4">Waste Category Breakdown</h2>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={85}
                  dataKey="value" nameKey="name" paddingAngle={4}
                  label={({ name, percent }) => `${name.split(" ")[0]} ${(percent*100).toFixed(0)}%`}
                  labelLine={{ stroke: C.text }} fontSize={11}>
                  {pieData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Pie>
                <Tooltip {...TOOLTIP_STYLE} />
              </PieChart>
            </ResponsiveContainer>
          </div>

          {/* Score distribution bar */}
          <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
            <h2 className="text-sm font-medium text-text-primary mb-4">Waste Score Distribution</h2>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={scoreRanges}>
                <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
                <XAxis dataKey="range" stroke={C.text} fontSize={9} />
                <YAxis stroke={C.text} fontSize={10} />
                <Tooltip {...TOOLTIP_STYLE} />
                <Bar dataKey="count" name="Resources" radius={[4,4,0,0]}>
                  {scoreRanges.map((e, i) => <Cell key={i} fill={e.fill} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Table + SHAP panel */}
        <div className="grid grid-cols-3 gap-6">
          <div className="col-span-2 bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
            {status === "loading" && <LoadingState />}
            {status === "error"   && <ErrorState />}
            {status === "ready" && displayed.length === 0 && <EmptyState />}
            {status === "ready" && displayed.length > 0 && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-subtle text-text-secondary text-xs uppercase">
                    <th className="text-left px-4 py-3">Resource</th>
                    <th className="text-left px-4 py-3">Bucket</th>
                    <th className="text-left px-4 py-3">Waste Score</th>
                    <th className="text-left px-4 py-3">Savings</th>
                  </tr>
                </thead>
                <tbody>
                  {displayed.map((r, i) => {
                    const s = BUCKET_STYLES[r.bucket] || {};
                    const rec = recsByResource[r.resource_id];
                    return (
                      <tr key={i} onClick={() => setSelected(r)}
                        className={`border-b border-border-subtle last:border-0 cursor-pointer hover:bg-bg-hover ${selected?.resource_id === r.resource_id ? "bg-bg-raised" : ""}`}>
                        <td className="px-4 py-3 font-data text-text-primary text-xs">{r.resource_id}</td>
                        <td className="px-4 py-3">
                          <span className={`text-xs px-2 py-0.5 rounded border ${s.bg} ${s.border} ${s.text}`}>{r.bucket}</span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div className="w-16 h-1.5 bg-bg-raised rounded-full overflow-hidden">
                              <div className="h-full rounded-full" style={{ width: `${r.waste_score}%`, background: s.color }} />
                            </div>
                            <span className="font-data text-xs text-text-primary">{r.waste_score?.toFixed(1)}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 font-data text-xs text-signal-mint">
                          {rec ? `$${rec.estimated_savings?.toFixed(0)}/mo` : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* SHAP panel */}
          <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
            <h3 className="text-sm font-medium text-text-primary mb-3">SHAP Explanation</h3>
            {!selected ? (
              <p className="text-xs text-text-tertiary">Click a resource row to see what drove its classification.</p>
            ) : selected.shap_top_features && Object.keys(selected.shap_top_features).length > 0 ? (
              <div>
                <div className="text-xs text-text-secondary mb-3 font-data">{selected.resource_id}</div>
                <div className="space-y-2.5">
                  {Object.entries(selected.shap_top_features).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).map(([feat, val]) => (
                    <div key={feat}>
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="text-text-secondary">{feat.replace(/_/g," ")}</span>
                        <span className={`font-data ${val > 0 ? "text-signal-red" : "text-signal-mint"}`}>
                          {val > 0 ? "+" : ""}{val.toFixed(3)}
                        </span>
                      </div>
                      <div className="h-1.5 bg-bg-raised rounded-full overflow-hidden">
                        <div className="h-full rounded-full transition-all"
                          style={{ width: `${Math.min(Math.abs(val) * 200, 100)}%`, background: val > 0 ? C.red : C.mint }} />
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-4 pt-3 border-t border-border-subtle text-[11px] text-text-tertiary">
                  Positive = increases waste score. Negative = decreases waste score.
                </div>
              </div>
            ) : (
              <p className="text-xs text-text-tertiary">No SHAP data for this resource. Run the nightly job to generate explanations.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
