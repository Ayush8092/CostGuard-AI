import { CheckCircle2, Database, Clock, RefreshCw } from "lucide-react";
import { useDataset } from "../context/DatasetContext";

const MODE_STYLES = {
  new_analysis: "text-signal-mint bg-signal-mint/10 border-signal-mint/30",
  continuous:   "text-signal-blue bg-signal-blue/10 border-signal-blue/30",
};

export default function AnalysisHistory() {
  const { datasets, activeDataset, switchDataset, loading } = useDataset();

  if (loading) return null;
  if (!datasets.length) return (
    <div className="px-3 py-4">
      <p className="text-[11px] text-text-tertiary text-center">
        No analyses yet.<br />Upload a CSV in Settings.
      </p>
    </div>
  );

  return (
    <div className="px-2 py-3 border-t border-border-subtle">
      <div className="flex items-center gap-2 px-2 mb-2">
        <Database className="w-3 h-3 text-text-tertiary" />
        <span className="text-[11px] text-text-tertiary uppercase tracking-wide">Analysis History</span>
      </div>
      <div className="space-y-1 max-h-48 overflow-y-auto">
        {datasets.map(d => {
          const isActive = activeDataset?.id === d.id;
          return (
            <button
              key={d.id}
              onClick={() => !isActive && d.status === "done" && switchDataset(d.id)}
              disabled={d.status !== "done"}
              className={`w-full text-left px-2 py-2 rounded-md text-xs transition-colors ${
                isActive
                  ? "bg-signal-mint/10 border border-signal-mint/30 text-signal-mint"
                  : d.status === "done"
                  ? "text-text-secondary hover:bg-bg-hover hover:text-text-primary border border-transparent"
                  : "text-text-tertiary border border-transparent opacity-50 cursor-not-allowed"
              }`}
            >
              <div className="flex items-center gap-1.5 mb-0.5">
                {isActive
                  ? <CheckCircle2 className="w-3 h-3 flex-shrink-0" />
                  : d.status === "processing"
                  ? <RefreshCw className="w-3 h-3 flex-shrink-0 animate-spin" />
                  : <div className="w-3 h-3 flex-shrink-0" />
                }
                <span className="truncate font-medium">
                  {d.dataset_name || d.original_filename}
                </span>
              </div>
              <div className="flex items-center gap-2 pl-4.5 text-[10px] text-text-tertiary">
                <span className={`px-1 py-0.5 rounded border text-[10px] ${MODE_STYLES[d.upload_mode] || MODE_STYLES.continuous}`}>
                  {d.upload_mode === "new_analysis" ? "New" : "Continuous"}
                </span>
                {d.row_count && <span>{d.row_count.toLocaleString()} rows</span>}
                {d.status === "processing" && <span className="text-signal-amber">Processing...</span>}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
