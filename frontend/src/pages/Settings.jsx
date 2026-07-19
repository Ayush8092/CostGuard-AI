import { useState, useRef, useCallback, useEffect } from "react";
import { Upload, CheckCircle2, XCircle, Cloud, Database, Server, RefreshCw, AlertTriangle, Trash2, History, Zap } from "lucide-react";
import { datasetsApi, insightsApi } from "../api/client";
import { useDataset } from "../context/DatasetContext";
import { PageHeader } from "../components/Status";

function SectionCard({ title, children }) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
      <div className="px-5 py-3 border-b border-border-subtle">
        <h2 className="text-sm font-medium text-text-primary">{title}</h2>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function SchemaTag({ label }) {
  return (
    <span className="inline-block bg-bg-raised border border-border-subtle rounded px-2 py-0.5 text-[11px] font-data text-text-secondary mr-1 mb-1">
      {label}
    </span>
  );
}

// ── Reset Confirmation Dialog ─────────────────────────────────────────────
function ResetDialog({ onConfirm, onCancel, loading }) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 px-4">
      <div className="bg-bg-surface border border-signal-red/40 rounded-xl p-6 max-w-md w-full shadow-2xl">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-signal-red/20 border border-signal-red/30 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5 text-signal-red" />
          </div>
          <h3 className="text-base font-semibold text-text-primary">Reset Current Analysis?</h3>
        </div>
        <div className="bg-bg-raised border border-border-subtle rounded-lg p-4 mb-5 text-xs text-text-secondary space-y-1.5">
          <p>This will permanently remove:</p>
          <ul className="space-y-1 pl-2">
            {["All uploaded datasets", "All analysis results", "All forecasts", "All anomaly detections", "All recommendations", "All cached AI insights"].map(item => (
              <li key={item} className="flex items-center gap-2">
                <span className="w-1 h-1 rounded-full bg-signal-red flex-shrink-0" />
                {item}
              </li>
            ))}
          </ul>
          <p className="pt-2 border-t border-border-subtle text-text-tertiary">
            Previously downloaded/exported reports are not affected.
          </p>
        </div>
        <div className="flex gap-3">
          <button onClick={onCancel} disabled={loading}
            className="flex-1 text-sm border border-border-subtle rounded-lg py-2.5 text-text-secondary hover:bg-bg-hover transition-colors">
            Cancel
          </button>
          <button onClick={onConfirm} disabled={loading}
            className="flex-1 text-sm bg-signal-red text-white rounded-lg py-2.5 font-medium hover:bg-signal-red/80 transition-colors disabled:opacity-50 flex items-center justify-center gap-2">
            {loading ? <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Resetting...</> : "Reset"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Analysis Mode selector ─────────────────────────────────────────────────
function AnalysisModeCard({ mode, selected, onSelect }) {
  const isNew = mode === "new_analysis";
  return (
    <button onClick={() => onSelect(mode)}
      className={`text-left p-4 rounded-lg border-2 transition-all w-full ${
        selected
          ? isNew
            ? "border-signal-mint bg-signal-mint/5"
            : "border-signal-blue bg-signal-blue/5"
          : "border-border-subtle hover:border-border bg-bg-raised"
      }`}>
      <div className="flex items-center gap-2 mb-1.5">
        <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
          selected
            ? isNew ? "border-signal-mint" : "border-signal-blue"
            : "border-text-tertiary"
        }`}>
          {selected && <div className={`w-2 h-2 rounded-full ${isNew ? "bg-signal-mint" : "bg-signal-blue"}`} />}
        </div>
        <span className="text-sm font-medium text-text-primary">
          {isNew ? "New Analysis" : "Continuous Monitoring"}
        </span>
      </div>
      <p className="text-xs text-text-tertiary pl-6">
        {isNew
          ? "Analyze this dataset independently. Previous results are preserved but this becomes the active view."
          : "Merge into historical cloud usage. Continues timeline, updates forecasts, and monitors drift."}
      </p>
    </button>
  );
}

export default function Settings() {
  const { datasets, activeDataset, refresh, switchDataset } = useDataset();

  // Upload state
  const [uploadMode, setUploadMode]       = useState("continuous");
  const [datasetName, setDatasetName]     = useState("");
  const [uploadState, setUploadState]     = useState(null);
  const [processing, setProcessing]       = useState(false);
  const fileInputRef = useRef(null);
  const pollRef      = useRef(null);

  // Reset dialog
  const [showReset, setShowReset]         = useState(false);
  const [resetLoading, setResetLoading]   = useState(false);
  const [resetResult, setResetResult]     = useState(null);

  // Insight generation
  const [generatingInsight, setGeneratingInsight] = useState(false);
  const [insightMsg, setInsightMsg]       = useState(null);

  useEffect(() => () => clearInterval(pollRef.current), []);

  const pollStatus = useCallback((datasetId) => {
    pollRef.current = setInterval(async () => {
      try {
        const res = await datasetsApi.status(datasetId);
        setUploadState(res.data);
        if (res.data.status === "done" || res.data.status === "failed") {
          clearInterval(pollRef.current);
          setProcessing(false);
          if (res.data.status === "done") {
            refresh();
            // Auto-generate executive insight for new_analysis
            if (uploadMode === "new_analysis") {
              setTimeout(() => generateInsight(datasetId), 2000);
            }
          }
        }
      } catch { clearInterval(pollRef.current); setProcessing(false); }
    }, 1500);
  }, [refresh, uploadMode]);

  async function handleFileSelect(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setProcessing(true);
    setUploadState({ status: "uploading", progress_pct: 0 });
    setInsightMsg(null);
    try {
      const name = datasetName.trim() || file.name;
      const res = await datasetsApi.upload(file, uploadMode, name);
      setUploadState({ status: "queued", progress_pct: 5 });
      pollStatus(res.data.dataset_id);
    } catch (err) {
      setUploadState({ status: "failed", error_message: err.response?.data?.detail || "Upload failed" });
      setProcessing(false);
    }
    e.target.value = "";
  }

  async function generateInsight(datasetId = null) {
    setGeneratingInsight(true);
    setInsightMsg(null);
    try {
      await insightsApi.generate(datasetId || activeDataset?.id);
      setInsightMsg("Executive Insights generated and saved to Dashboard.");
    } catch (e) {
      setInsightMsg(`Insight generation failed: ${e.response?.data?.detail || e.message}`);
    } finally {
      setGeneratingInsight(false);
    }
  }

  async function handleReset() {
    setResetLoading(true);
    try {
      const res = await datasetsApi.reset();
      setResetResult(res.data);
      setShowReset(false);
      refresh();
      setUploadState(null);
    } catch (e) {
      setResetResult({ message: e.response?.data?.detail || "Reset failed" });
      setShowReset(false);
    } finally {
      setResetLoading(false);
    }
  }

  const progressColor = uploadState?.status === "done" ? "bg-signal-mint"
    : uploadState?.status === "failed" ? "bg-signal-red" : "bg-signal-blue";

  return (
    <div>
      <PageHeader title="Settings" description="Dataset management, analysis history, and system configuration" />

      {showReset && (
        <ResetDialog
          onConfirm={handleReset}
          onCancel={() => setShowReset(false)}
          loading={resetLoading}
        />
      )}

      <div className="px-8 py-6 space-y-6 max-w-4xl">

        {/* Active dataset banner */}
        {activeDataset && (
          <div className="bg-signal-mint/10 border border-signal-mint/30 rounded-lg px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-signal-mint" />
              <span className="text-sm text-text-primary font-medium">Active Analysis:</span>
              <span className="text-sm text-signal-mint font-data">{activeDataset.dataset_name || activeDataset.original_filename}</span>
              <span className="text-[11px] text-text-tertiary">({activeDataset.row_count?.toLocaleString()} rows)</span>
            </div>
            <span className="text-[11px] text-text-tertiary">{activeDataset.upload_mode === "new_analysis" ? "New Analysis" : "Continuous"}</span>
          </div>
        )}

        {/* Upload section */}
        <SectionCard title="Upload Billing Data">
          <p className="text-xs text-text-secondary mb-5">
            Required columns: <span className="font-data text-text-primary">date, service, resource_id, cost</span>.
            Optional: <span className="font-data text-text-primary">cpu_avg_pct, memory_avg_pct, instance_type, region</span>.
          </p>

          {/* Dataset name */}
          <div className="mb-4">
            <label className="text-xs text-text-secondary mb-1 block">Analysis name (optional)</label>
            <input
              value={datasetName}
              onChange={e => setDatasetName(e.target.value)}
              placeholder="e.g. AWS June 2024, Production Q2..."
              className="w-full bg-bg-raised border border-border-subtle rounded-lg text-sm px-3 py-2 text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-signal-mint/50"
            />
          </div>

          {/* Analysis Mode selector */}
          <div className="mb-5">
            <label className="text-xs text-text-secondary mb-2 block">Analysis Mode</label>
            <div className="grid grid-cols-2 gap-3">
              <AnalysisModeCard mode="new_analysis"  selected={uploadMode === "new_analysis"}  onSelect={setUploadMode} />
              <AnalysisModeCard mode="continuous"    selected={uploadMode === "continuous"}    onSelect={setUploadMode} />
            </div>
          </div>

          {/* Drop zone */}
          <div
            onClick={() => !processing && fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-lg p-7 text-center transition-colors ${
              processing
                ? "border-border-subtle cursor-not-allowed opacity-60"
                : "border-border-subtle hover:border-signal-mint/50 cursor-pointer"
            }`}>
            <Upload className="w-6 h-6 text-text-tertiary mx-auto mb-2" />
            <p className="text-sm text-text-secondary">Click to select a CSV file</p>
            <p className="text-xs text-text-tertiary mt-1">Supports standard, AWS CUR, and custom header formats</p>
            <input ref={fileInputRef} type="file" accept=".csv" className="hidden" onChange={handleFileSelect} />
          </div>

          {/* Upload progress */}
          {uploadState && (
            <div className="mt-4 bg-bg-raised border border-border-subtle rounded-lg p-4">
              {uploadState.status === "done" ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-signal-mint text-sm font-medium">
                    <CheckCircle2 className="w-4 h-4" /> Upload complete
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { label: "Rows processed",  value: uploadState.row_count?.toLocaleString() },
                      { label: "Columns mapped",  value: Object.keys(uploadState.column_mapping || {}).length || "—" },
                      { label: "Validation",      value: "Passed ✓" },
                    ].map(({ label, value }) => (
                      <div key={label} className="bg-bg-surface rounded p-2 border border-border-subtle">
                        <div className="text-[11px] text-text-tertiary mb-0.5">{label}</div>
                        <div className="text-xs font-data text-text-primary font-medium">{value ?? "—"}</div>
                      </div>
                    ))}
                  </div>
                  {uploadState.column_mapping && (
                    <div>
                      <div className="text-[11px] text-text-secondary mb-1">Detected schema:</div>
                      <div>{Object.entries(uploadState.column_mapping).map(([k, v]) => (
                        <SchemaTag key={k} label={`${k} → ${v}`} />
                      ))}</div>
                    </div>
                  )}
                  {insightMsg && (
                    <div className="text-xs text-signal-mint flex items-center gap-1.5">
                      <Zap className="w-3 h-3" /> {insightMsg}
                    </div>
                  )}
                </div>
              ) : uploadState.status === "failed" ? (
                <div className="flex items-center gap-2 text-signal-red text-sm">
                  <XCircle className="w-4 h-4" /> {uploadState.error_message}
                </div>
              ) : (
                <div>
                  <div className="flex justify-between text-xs text-text-secondary mb-2">
                    <span className="flex items-center gap-1.5">
                      <RefreshCw className="w-3 h-3 animate-spin" />
                      {uploadState.status === "queued" ? "Queued..." : "Processing..."}
                    </span>
                    <span className="font-data">{uploadState.progress_pct || 0}%</span>
                  </div>
                  <div className="h-2 bg-bg-raised rounded-full overflow-hidden border border-border-subtle">
                    <div className={`h-full rounded-full transition-all duration-500 ${progressColor}`}
                      style={{ width: `${uploadState.progress_pct || 0}%` }} />
                  </div>
                </div>
              )}
            </div>
          )}
        </SectionCard>

        {/* Analysis History */}
        <SectionCard title="Analysis History">
          {!datasets.length ? (
            <div className="text-xs text-text-tertiary text-center py-4">No analyses yet.</div>
          ) : (
            <div className="space-y-2">
              {datasets.map(d => {
                const isActive = activeDataset?.id === d.id;
                return (
                  <div key={d.id} className={`flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg border ${
                    isActive ? "border-signal-mint/40 bg-signal-mint/5" : "border-border-subtle bg-bg-raised"
                  }`}>
                    <div className="flex items-center gap-2 min-w-0">
                      {isActive
                        ? <CheckCircle2 className="w-3.5 h-3.5 text-signal-mint flex-shrink-0" />
                        : <History className="w-3.5 h-3.5 text-text-tertiary flex-shrink-0" />}
                      <div className="min-w-0">
                        <div className="text-xs font-medium text-text-primary truncate">
                          {d.dataset_name || d.original_filename}
                        </div>
                        <div className="text-[11px] text-text-tertiary font-data">
                          {d.row_count?.toLocaleString()} rows · {new Date(d.created_at).toLocaleDateString()}
                          {" · "}{d.upload_mode === "new_analysis" ? "New Analysis" : "Continuous"}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {!isActive && d.status === "done" && (
                        <button onClick={() => switchDataset(d.id)}
                          className="text-[11px] text-signal-mint border border-signal-mint/30 rounded px-2 py-1 hover:bg-signal-mint/10">
                          Switch
                        </button>
                      )}
                      {d.status === "done" && (
                        <button
                          onClick={async () => { setInsightMsg(null); await generateInsight(d.id); }}
                          disabled={generatingInsight}
                          className="text-[11px] text-text-secondary border border-border-subtle rounded px-2 py-1 hover:bg-bg-hover disabled:opacity-50 flex items-center gap-1">
                          <Zap className="w-3 h-3" />
                          {generatingInsight ? "..." : "Re-run Insights"}
                        </button>
                      )}
                      {isActive && <span className="text-[11px] text-signal-mint font-medium">Active</span>}
                      {d.status === "processing" && (
                        <span className="text-[11px] text-signal-amber flex items-center gap-1">
                          <RefreshCw className="w-3 h-3 animate-spin" /> Processing
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </SectionCard>

        {/* Reset Analysis */}
        <SectionCard title="Reset Analysis">
          <div className="flex items-start gap-4">
            <div className="flex-1">
              <p className="text-xs text-text-secondary mb-3">
                Removes all uploaded datasets, analysis results, forecasts, anomalies, recommendations,
                and cached AI insights for your organization. Previously downloaded reports are not affected.
              </p>
              {resetResult && (
                <div className="bg-bg-raised border border-border-subtle rounded-lg p-3 mb-3 text-xs text-text-secondary space-y-0.5">
                  <div className="font-medium text-text-primary mb-1">{resetResult.message}</div>
                  {resetResult.deleted_datasets !== undefined && (
                    <>
                      <div>Datasets removed: <span className="font-data">{resetResult.deleted_datasets}</span></div>
                      <div>Forecasts removed: <span className="font-data">{resetResult.deleted_forecasts}</span></div>
                      <div>Anomalies removed: <span className="font-data">{resetResult.deleted_anomalies}</span></div>
                      <div>Recommendations removed: <span className="font-data">{resetResult.deleted_recommendations}</span></div>
                    </>
                  )}
                </div>
              )}
              <button onClick={() => setShowReset(true)}
                className="flex items-center gap-2 text-sm text-signal-red border border-signal-red/30 bg-signal-red/10 rounded-lg px-4 py-2.5 hover:bg-signal-red/20 transition-colors">
                <Trash2 className="w-4 h-4" />
                Reset Analysis
              </button>
            </div>
          </div>
        </SectionCard>

        {/* Supported formats */}
        <SectionCard title="Supported CSV Formats">
          <div className="grid grid-cols-3 gap-4">
            {[
              { name: "Standard", desc: "Direct column names", headers: ["date","service","resource_id","cost","cpu_avg_pct"], badge: "Recommended", c: "text-signal-mint border-signal-mint/30 bg-signal-mint/10" },
              { name: "AWS CUR", desc: "AWS Cost & Usage Report", headers: ["UsageStartDate","ProductName","LineItemResourceId","UnblendedCost"], badge: "Auto-detected", c: "text-signal-blue border-signal-blue/30 bg-signal-blue/10" },
              { name: "Minimal", desc: "No utilization columns", headers: ["date","service","resource_id","cost"], badge: "Graceful degradation", c: "text-signal-amber border-signal-amber/30 bg-signal-amber/10" },
            ].map(f => (
              <div key={f.name} className="bg-bg-raised border border-border-subtle rounded-lg p-4">
                <div className="flex items-start justify-between mb-2">
                  <span className="text-xs font-medium text-text-primary">{f.name}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded border ${f.c}`}>{f.badge}</span>
                </div>
                <p className="text-[11px] text-text-tertiary mb-2">{f.desc}</p>
                <div>{f.headers.map(h => <SchemaTag key={h} label={h} />)}</div>
              </div>
            ))}
          </div>
        </SectionCard>

        {/* System info */}
        <SectionCard title="System Configuration">
          <div className="grid grid-cols-3 gap-4">
            {[
              { icon: Database, label: "Database",     value: "Neon PostgreSQL",      sub: "Free hosted tier" },
              { icon: Server,   label: "Cache",        value: "Upstash Redis",         sub: "TLS auto-enabled" },
              { icon: Cloud,    label: "LLM Provider", value: "Gemini → Groq (auto)",  sub: "Free-tier fallback" },
            ].map(({ icon: Icon, label, value, sub }) => (
              <div key={label} className="flex items-start gap-3 bg-bg-raised border border-border-subtle rounded-lg p-4">
                <div className="w-8 h-8 rounded bg-signal-mint/10 border border-signal-mint/20 flex items-center justify-center flex-shrink-0">
                  <Icon className="w-4 h-4 text-signal-mint" />
                </div>
                <div>
                  <div className="text-[11px] text-text-tertiary">{label}</div>
                  <div className="text-xs font-medium text-text-primary">{value}</div>
                  <div className="text-[11px] text-text-tertiary">{sub}</div>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
