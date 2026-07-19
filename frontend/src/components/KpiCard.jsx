export default function KpiCard({ label, value, sublabel, accent = "default", icon: Icon, trend }) {
  const colors = {
    default: "text-text-primary",
    mint:    "text-signal-mint",
    amber:   "text-signal-amber",
    red:     "text-signal-red",
    blue:    "text-signal-blue",
  };
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-text-secondary uppercase tracking-wide">{label}</span>
        {Icon && <Icon className="w-4 h-4 text-text-tertiary" strokeWidth={2} />}
      </div>
      <div className={`font-data text-2xl font-semibold ${colors[accent]}`}>{value ?? "—"}</div>
      {sublabel && <div className="text-xs text-text-tertiary mt-1">{sublabel}</div>}
      {trend !== undefined && trend !== null && (
        <div className={`text-xs mt-1 font-data ${trend > 0 ? "text-signal-red" : "text-signal-mint"}`}>
          {trend > 0 ? "▲" : "▼"} {Math.abs(trend).toFixed(1)}% vs prior period
        </div>
      )}
    </div>
  );
}
