export default function ConfidenceBadge({ confidence, size = "sm" }) {
  const pct = typeof confidence === "number" ? confidence : parseFloat(confidence) || 0;
  let color = "text-signal-red bg-signal-red/10 border-signal-red/30";
  if (pct >= 80) color = "text-signal-mint bg-signal-mint/10 border-signal-mint/30";
  else if (pct >= 50) color = "text-signal-amber bg-signal-amber/10 border-signal-amber/30";
  const sz = size === "sm" ? "text-[11px] px-1.5 py-0.5" : "text-xs px-2 py-1";
  return (
    <span className={`inline-flex items-center gap-1 rounded border font-data ${color} ${sz}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {pct.toFixed(0)}% conf
    </span>
  );
}
