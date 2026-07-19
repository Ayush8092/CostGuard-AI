import { useEffect, useState } from "react";
import { CheckCircle2, XCircle, BookOpen, TrendingUp, Shield, Zap, ChevronDown, ChevronUp } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { recommendationsApi } from "../api/client";
import { C, TOOLTIP_STYLE } from "../components/ChartColors";
import { LoadingState, ErrorState, EmptyState, PageHeader } from "../components/Status";
import ConfidenceBadge from "../components/ConfidenceBadge";

const TIER_STYLES = {
  High:   { bar: "border-l-signal-red",   badge: "bg-signal-red/10 text-signal-red border-signal-red/30",   color: C.red   },
  Medium: { bar: "border-l-signal-amber", badge: "bg-signal-amber/10 text-signal-amber border-signal-amber/30", color: C.amber },
  Low:    { bar: "border-l-signal-blue",  badge: "bg-signal-blue/10 text-signal-blue border-signal-blue/30",  color: C.blue  },
};
const TIERS = ["High", "Medium", "Low"];

function RecRow({ r, onStatusChange }) {
  const [expanded, setExpanded] = useState(false);
  const ts = TIER_STYLES[r.impact_tier] || TIER_STYLES.Low;

  return (
    <div className={`bg-bg-surface border border-border-subtle border-l-2 ${ts.bar} rounded-lg overflow-hidden`}>
      <div className="p-4 flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-[11px] px-2 py-0.5 rounded border font-medium ${ts.badge}`}>{r.impact_tier} Impact</span>
            <span className="font-data text-sm text-text-primary">{r.action}</span>
            <ConfidenceBadge confidence={r.confidence} />
          </div>
          <p className="text-xs text-text-secondary">{r.reason}</p>
          {r.supporting_rule && (
            <div className="flex items-center gap-1 text-[11px] text-text-tertiary mt-1">
              <BookOpen className="w-3 h-3" />{r.supporting_rule}
            </div>
          )}
          {expanded && (
            <div className="mt-3 pt-3 border-t border-border-subtle text-xs space-y-1 text-text-tertiary font-data">
              <div>Impact score: <span className="text-text-secondary">{r.impact_score?.toFixed(2)}</span></div>
              <div>Resource: <span className="text-text-secondary">{r.resource_id}</span></div>
              <div>Status: <span className="text-text-secondary capitalize">{r.status}</span></div>
            </div>
          )}
        </div>
        <div className="text-right flex-shrink-0">
          <div className="font-data text-xl font-semibold text-signal-mint">${r.estimated_savings?.toLocaleString(undefined,{maximumFractionDigits:0})}<span className="text-xs font-normal text-text-tertiary">/mo</span></div>
          {r.status === "open" ? (
            <div className="flex gap-2 mt-2 justify-end">
              <button onClick={() => onStatusChange(r.id, "accepted")}
                className="flex items-center gap-1 text-xs bg-signal-mint/10 text-signal-mint border border-signal-mint/30 px-2 py-1 rounded hover:bg-signal-mint/20">
                <CheckCircle2 className="w-3.5 h-3.5" /> Accept
              </button>
              <button onClick={() => onStatusChange(r.id, "dismissed")}
                className="flex items-center gap-1 text-xs text-text-tertiary border border-border-subtle px-2 py-1 rounded hover:text-signal-red hover:border-signal-red/30">
                <XCircle className="w-3.5 h-3.5" /> Dismiss
              </button>
            </div>
          ) : (
            <span className="text-xs text-text-tertiary capitalize mt-2 block">{r.status}</span>
          )}
          <button onClick={() => setExpanded(!expanded)} className="text-[11px] text-text-tertiary mt-1 flex items-center gap-0.5 ml-auto">
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {expanded ? "less" : "more"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Recommendations() {
  const [recs, setRecs]   = useState([]);
  const [evalM, setEvalM] = useState(null);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    Promise.all([recommendationsApi.list(), recommendationsApi.evaluation()])
      .then(([rr, er]) => { setRecs(rr.data); setEvalM(er.data); setStatus("ready"); })
      .catch(() => setStatus("error"));
  }, []);

  async function onStatusChange(id, newStatus) {
    await recommendationsApi.updateStatus(id, newStatus);
    setRecs(prev => prev.map(r => r.id === id ? { ...r, status: newStatus } : r));
  }

  if (status === "loading") return <LoadingState />;
  if (status === "error")   return <ErrorState />;

  const openRecs    = recs.filter(r => r.status === "open");
  const acceptedRecs = recs.filter(r => r.status === "accepted");
  const totalSavings = openRecs.reduce((s, r) => s + (r.estimated_savings || 0), 0);
  const avgConfidence = openRecs.length > 0
    ? openRecs.reduce((s, r) => s + (r.confidence || 0), 0) / openRecs.length : 0;

  // Savings by tier chart
  const tierSavings = TIERS.map(tier => ({
    tier,
    savings: recs.filter(r => r.impact_tier === tier).reduce((s, r) => s + (r.estimated_savings || 0), 0),
    count:   recs.filter(r => r.impact_tier === tier).length,
  }));

  return (
    <div>
      <PageHeader title="Recommendations" description="Ranked, grounded cost optimization actions derived from ML model outputs" />
      <div className="px-8 py-6 space-y-6">

        {/* Summary cards */}
        <div className="grid grid-cols-5 gap-4">
          {[
            { label: "Total Recommendations", value: recs.length,                         icon: Zap     },
            { label: "Open",                  value: openRecs.length,    accent: "amber",  icon: Shield  },
            { label: "Accepted",              value: acceptedRecs.length,accent: "mint",   icon: CheckCircle2 },
            { label: "Potential Savings",     value: `$${totalSavings.toLocaleString(undefined,{maximumFractionDigits:0})}/mo`, accent: "mint", icon: TrendingUp },
            { label: "Avg Confidence",        value: `${avgConfidence.toFixed(1)}%`,       icon: Shield  },
          ].map(({ label, value, accent, icon: Icon }) => (
            <div key={label} className="bg-bg-surface border border-border-subtle rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-text-secondary">{label}</span>
                {Icon && <Icon className="w-3.5 h-3.5 text-text-tertiary" />}
              </div>
              <div className={`font-data text-xl font-semibold ${
                accent === "mint" ? "text-signal-mint" : accent === "amber" ? "text-signal-amber" : "text-text-primary"
              }`}>{value}</div>
            </div>
          ))}
        </div>

        {/* Savings by tier chart */}
        <div className="grid grid-cols-2 gap-6">
          <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
            <h2 className="text-sm font-medium text-text-primary mb-4">Savings by Impact Tier</h2>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={tierSavings}>
                <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
                <XAxis dataKey="tier" stroke={C.text} fontSize={11} />
                <YAxis stroke={C.text} fontSize={11} />
                <Tooltip {...TOOLTIP_STYLE} formatter={v => [`$${Number(v).toFixed(0)}`]} />
                <Bar dataKey="savings" name="Monthly Savings ($)" radius={[4,4,0,0]}>
                  {tierSavings.map((e, i) => <Cell key={i} fill={TIER_STYLES[e.tier]?.color || C.blue} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
            <h2 className="text-sm font-medium text-text-primary mb-3">Evaluation Metrics</h2>
            {evalM && (
              <div className="space-y-3">
                <MetricRow label="Total recommendations" value={evalM.total_recommendations} />
                <MetricRow label="Avg monthly savings" value={`$${evalM.avg_estimated_monthly_savings?.toLocaleString()}`} accent />
                <MetricRow label="Avg confidence" value={`${evalM.avg_confidence?.toFixed(1)}%`} accent />
                <div className="pt-3 border-t border-border-subtle text-[11px] text-text-tertiary">
                  Confidence = weighted combination of classifier probability, anomaly score, forecast uncertainty, and data quality score — never LLM confidence.
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Recommendations grouped by tier */}
        {recs.length === 0 ? (
          <EmptyState title="No recommendations yet" message="Run the nightly job to generate recommendations." />
        ) : (
          TIERS.map(tier => {
            const tierRecs = recs.filter(r => r.impact_tier === tier);
            if (!tierRecs.length) return null;
            return (
              <div key={tier}>
                <h2 className="text-xs uppercase text-text-secondary mb-3 flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full`} style={{ background: TIER_STYLES[tier].color }} />
                  {tier} Impact — {tierRecs.length} recommendation{tierRecs.length !== 1 ? "s" : ""}
                </h2>
                <div className="space-y-2">
                  {tierRecs.map(r => <RecRow key={r.id} r={r} onStatusChange={onStatusChange} />)}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function MetricRow({ label, value, accent }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-text-secondary">{label}</span>
      <span className={`font-data font-medium ${accent ? "text-signal-mint" : "text-text-primary"}`}>{value}</span>
    </div>
  );
}
