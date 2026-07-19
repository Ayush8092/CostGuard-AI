import { useEffect, useState } from "react";
import { RefreshCw, CheckCircle2, XCircle, Clock, Database, Cpu, BarChart2, Calendar } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } from "recharts";
import { monitoringApi } from "../api/client";
import { C, TOOLTIP_STYLE } from "../components/ChartColors";
import { LoadingState, ErrorState, EmptyState, PageHeader } from "../components/Status";

function MetricCard({ label, value, sub, accent, icon: Icon }) {
  const color = accent === "mint" ? "text-signal-mint" : accent === "red" ? "text-signal-red" : accent === "amber" ? "text-signal-amber" : "text-text-primary";
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

const MODEL_COLORS = { forecast: C.mint, anomaly: C.amber, waste_classifier: C.blue };

export default function ModelMonitoring() {
  const [registry, setRegistry] = useState([]);
  const [loadTest, setLoadTest]  = useState(null);
  const [status, setStatus]      = useState("loading");
  const [retraining, setRetraining] = useState(false);
  const [retrainMsg, setRetrainMsg] = useState(null);

  function load() {
    setStatus("loading");
    Promise.all([monitoringApi.registry(), monitoringApi.loadTestSummary()])
      .then(([rr, lr]) => { setRegistry(rr.data); setLoadTest(lr.data); setStatus("ready"); })
      .catch(() => setStatus("error"));
  }

  useEffect(load, []);

  async function triggerRetrain() {
    setRetraining(true); setRetrainMsg(null);
    try {
      await monitoringApi.triggerRetrain();
      setRetrainMsg("Retraining triggered successfully. Refresh in a few minutes.");
      load();
    } catch (e) {
      setRetrainMsg("Retrain failed — check backend logs.");
    } finally {
      setRetraining(false);
    }
  }

  if (status === "loading") return <LoadingState />;
  if (status === "error")   return <ErrorState />;

  const activeModels = registry.filter(m => m.is_active);
  const forecast  = activeModels.find(m => m.model_type === "forecast");
  const anomaly   = activeModels.find(m => m.model_type === "anomaly");
  const waste     = activeModels.find(m => m.model_type === "waste_classifier");

  // Build performance history chart from registry (all versions, not just active)
  const forecastHistory = registry
    .filter(m => m.model_type === "forecast" && m.evaluation_metrics?.mape)
    .slice(0, 8).reverse()
    .map((m, i) => ({ v: `v${i+1}`, mape: m.evaluation_metrics.mape, naive: m.evaluation_metrics.naive_mape }));

  const wasteHistory = registry
    .filter(m => m.model_type === "waste_classifier" && m.evaluation_metrics?.f1_macro)
    .slice(0, 8).reverse()
    .map((m, i) => ({ v: `v${i+1}`, f1: m.evaluation_metrics.f1_macro, accuracy: m.evaluation_metrics.accuracy }));

  // Next scheduled retraining — every Sunday, compute days until next Sunday
  const now = new Date();
  const daysUntilSunday = (7 - now.getDay()) % 7 || 7;
  const nextRetrain = new Date(now); nextRetrain.setDate(now.getDate() + daysUntilSunday);

  return (
    <div>
      <PageHeader title="Model Monitoring" description="Drift detection, model registry, training history, and load test results">
        <div className="flex items-center gap-3">
          {retrainMsg && <span className="text-xs text-signal-mint">{retrainMsg}</span>}
          <button onClick={triggerRetrain} disabled={retraining}
            className="flex items-center gap-2 text-sm bg-bg-raised border border-border-subtle rounded-md px-3 py-1.5 text-text-primary hover:bg-bg-hover disabled:opacity-50">
            <RefreshCw className={`w-3.5 h-3.5 ${retraining ? "animate-spin" : ""}`} />
            Trigger Retrain
          </button>
        </div>
      </PageHeader>

      <div className="px-8 py-6 space-y-6">

        {/* System status strip */}
        <div className="grid grid-cols-4 gap-4">
          <MetricCard label="Active Models" value={activeModels.length} sub="of 3 model types" accent={activeModels.length === 3 ? "mint" : "amber"} icon={Database} />
          <MetricCard label="Next Scheduled Retrain" value={`${daysUntilSunday}d`} sub={`${nextRetrain.toDateString()}`} icon={Calendar} />
          <MetricCard label="Last Trained"
            value={activeModels[0]?.training_date ? new Date(activeModels[0].training_date).toLocaleDateString() : "—"}
            sub="most recent model" icon={Clock} />
          <MetricCard label="Retraining Policy"
            value="PSI > 0.2 or Weekly"
            sub="drift detection active" accent="mint" icon={BarChart2} />
        </div>

        {/* Per-model detail cards */}
        <div className="grid grid-cols-3 gap-5">
          {/* Forecast model */}
          <ModelDetailCard
            title="Forecasting Model"
            model={forecast}
            color={C.mint}
            metrics={[
              { label: "Algorithm", value: "XGBoost Quantile Regression" },
              { label: "MAPE", value: forecast?.evaluation_metrics?.mape != null ? `${forecast.evaluation_metrics.mape}%` : "—", accent: true },
              { label: "RMSE", value: forecast?.evaluation_metrics?.rmse != null ? `$${forecast.evaluation_metrics.rmse}` : "—" },
              { label: "Naive MAPE", value: forecast?.evaluation_metrics?.naive_mape != null ? `${forecast.evaluation_metrics.naive_mape}%` : "—" },
              { label: "Error Reduction", value: forecast?.evaluation_metrics?.error_reduction_pct != null ? `${forecast.evaluation_metrics.error_reduction_pct?.toFixed(1)}%` : "—", accent: true },
              { label: "Dataset Version", value: forecast?.dataset_version || "—" },
            ]}
          />

          {/* Anomaly model */}
          <ModelDetailCard
            title="Anomaly Detector"
            model={anomaly}
            color={C.amber}
            metrics={[
              { label: "Algorithm", value: "Isolation Forest (per-dimension)" },
              { label: "Dimensions Trained", value: anomaly?.evaluation_metrics?.dimensions_trained ?? "—", accent: true },
              { label: "Contamination", value: anomaly?.hyperparameters?.contamination != null ? `${(anomaly.hyperparameters.contamination * 100).toFixed(0)}%` : "—" },
              { label: "Estimators", value: anomaly?.hyperparameters?.n_estimators ?? "—" },
              { label: "Evaluation", value: "Unsupervised (real data)" },
              { label: "Dataset Version", value: anomaly?.dataset_version || "—" },
            ]}
          />

          {/* Waste classifier */}
          <ModelDetailCard
            title="Waste Classifier"
            model={waste}
            color={C.blue}
            metrics={[
              { label: "Algorithm", value: "Random Forest + sklearn Pipeline" },
              { label: "Accuracy", value: waste?.evaluation_metrics?.accuracy != null ? `${(waste.evaluation_metrics.accuracy * 100).toFixed(1)}%` : "—", accent: true },
              { label: "Macro F1", value: waste?.evaluation_metrics?.f1_macro != null ? `${(waste.evaluation_metrics.f1_macro * 100).toFixed(1)}%` : "—", accent: true },
              { label: "Precision", value: waste?.evaluation_metrics?.precision_macro != null ? `${(waste.evaluation_metrics.precision_macro * 100).toFixed(1)}%` : "—" },
              { label: "Recall", value: waste?.evaluation_metrics?.recall_macro != null ? `${(waste.evaluation_metrics.recall_macro * 100).toFixed(1)}%` : "—" },
              { label: "Dataset Version", value: waste?.dataset_version || "—" },
            ]}
          />
        </div>

        {/* Performance history charts */}
        {forecastHistory.length > 0 && (
          <div className="grid grid-cols-2 gap-6">
            <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
              <h2 className="text-sm font-medium text-text-primary mb-4">Forecast MAPE History</h2>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={forecastHistory}>
                  <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
                  <XAxis dataKey="v" stroke={C.text} fontSize={10} />
                  <YAxis stroke={C.text} fontSize={10} unit="%" />
                  <Tooltip {...TOOLTIP_STYLE} formatter={v => [`${v}%`]} />
                  <Line type="monotone" dataKey="mape" stroke={C.mint} strokeWidth={2} dot name="Model MAPE" />
                  <Line type="monotone" dataKey="naive" stroke={C.text} strokeWidth={1.5} strokeDasharray="4 4" dot={false} name="Naive MAPE" />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
              <h2 className="text-sm font-medium text-text-primary mb-4">Waste Classifier F1 History</h2>
              {wasteHistory.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={wasteHistory}>
                    <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
                    <XAxis dataKey="v" stroke={C.text} fontSize={10} />
                    <YAxis stroke={C.text} fontSize={10} domain={[0, 1]} />
                    <Tooltip {...TOOLTIP_STYLE} formatter={v => [Number(v).toFixed(3)]} />
                    <Bar dataKey="f1" fill={C.blue} name="F1 Macro" radius={[4,4,0,0]} />
                    <Bar dataKey="accuracy" fill={C.mint} name="Accuracy" radius={[4,4,0,0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="text-xs text-text-tertiary py-8 text-center">Only one training run so far — history will appear after weekly retraining</div>
              )}
            </div>
          </div>
        )}

        {/* Full model registry table */}
        <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
          <div className="px-5 py-3 border-b border-border-subtle">
            <h2 className="text-sm font-medium text-text-primary">Model Registry — All Versions</h2>
          </div>
          {registry.length === 0 ? (
            <EmptyState title="No models registered yet" message="Run the nightly job to train and register models." />
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border-subtle text-text-secondary uppercase text-[11px]">
                  <th className="text-left px-4 py-3">Model Type</th>
                  <th className="text-left px-4 py-3">Version</th>
                  <th className="text-left px-4 py-3">Training Date</th>
                  <th className="text-left px-4 py-3">Key Metrics</th>
                  <th className="text-left px-4 py-3">Dataset</th>
                  <th className="text-left px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {registry.map(m => (
                  <tr key={m.id} className="border-b border-border-subtle last:border-0 hover:bg-bg-hover">
                    <td className="px-4 py-3">
                      <span className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full" style={{ background: MODEL_COLORS[m.model_type] || C.text }} />
                        <span className="capitalize text-text-primary">{m.model_type?.replace("_", " ")}</span>
                      </span>
                    </td>
                    <td className="px-4 py-3 font-data text-text-secondary">{m.version?.slice(0, 24)}</td>
                    <td className="px-4 py-3 font-data text-text-secondary">
                      {m.training_date ? new Date(m.training_date).toLocaleString() : "—"}
                    </td>
                    <td className="px-4 py-3 font-data text-text-tertiary">
                      {m.evaluation_metrics
                        ? Object.entries(m.evaluation_metrics).slice(0, 3).map(([k, v]) =>
                            `${k}=${typeof v === "number" ? v.toFixed(3) : v}`
                          ).join(" · ")
                        : "—"}
                    </td>
                    <td className="px-4 py-3 font-data text-text-tertiary">{m.dataset_version || "—"}</td>
                    <td className="px-4 py-3">
                      {m.is_active
                        ? <span className="flex items-center gap-1 text-signal-mint"><CheckCircle2 className="w-3.5 h-3.5" /> Active</span>
                        : <span className="flex items-center gap-1 text-text-tertiary"><XCircle className="w-3.5 h-3.5" /> Inactive</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Load test results */}
        <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
          <h2 className="text-sm font-medium text-text-primary mb-4">Load Test Results (200 concurrent users)</h2>
          {!loadTest?.available ? (
            <div>
              <div className="text-xs text-text-tertiary mb-3">{loadTest?.note || "No load test results available."}</div>
              <div className="bg-bg-raised rounded-md p-4 font-data text-xs text-text-tertiary">
                <div className="mb-2 text-text-secondary">Run the load test:</div>
                <div>cd backend</div>
                <div>locust -f tests/locustfile.py --host http://localhost --users 200 --spawn-rate 10 --run-time 60s --headless --csv load_test_results</div>
                <div>python tests/summarize_load_test.py --stats load_test_results_stats.csv --out /app/data/load_test_results.json</div>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-5 gap-4">
              {[
                { label: "Avg Latency",     value: `${loadTest.avg_latency_ms}ms`,  accent: loadTest.avg_latency_ms < 200 ? "mint" : "amber" },
                { label: "p95 Latency",     value: `${loadTest.p95_latency_ms}ms`,  accent: loadTest.p95_latency_ms < 500 ? "mint" : "red" },
                { label: "p99 Latency",     value: `${loadTest.p99_latency_ms}ms`  },
                { label: "Requests/sec",    value: loadTest.requests_per_sec,       accent: "mint" },
                { label: "Error Rate",      value: `${loadTest.error_rate_pct}%`,   accent: loadTest.error_rate_pct < 1 ? "mint" : "red",
                  sub: loadTest.pass ? "✓ PASS (<1%)" : "✗ FAIL" },
              ].map(({ label, value, accent, sub }) => (
                <div key={label} className="bg-bg-raised rounded-lg p-3 border border-border-subtle">
                  <div className="text-[11px] text-text-secondary mb-1">{label}</div>
                  <div className={`font-data text-lg font-semibold ${
                    accent === "mint" ? "text-signal-mint" : accent === "red" ? "text-signal-red" : accent === "amber" ? "text-signal-amber" : "text-text-primary"
                  }`}>{value}</div>
                  {sub && <div className="text-[11px] text-text-tertiary mt-0.5">{sub}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ModelDetailCard({ title, model, color, metrics }) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
          <span className="text-sm font-medium text-text-primary">{title}</span>
        </div>
        {model?.is_active
          ? <span className="text-[11px] text-signal-mint flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Active</span>
          : <span className="text-[11px] text-signal-amber">Not trained yet</span>}
      </div>
      <div className="p-4 space-y-2.5">
        {model ? (
          <>
            {metrics.map(({ label, value, accent }) => (
              <div key={label} className="flex items-center justify-between text-xs">
                <span className="text-text-tertiary">{label}</span>
                <span className={`font-data font-medium ${accent ? "text-signal-mint" : "text-text-secondary"}`}>{value}</span>
              </div>
            ))}
            <div className="pt-2 border-t border-border-subtle text-[11px] text-text-tertiary font-data">
              Last trained: {model.training_date ? new Date(model.training_date).toLocaleString() : "—"}
            </div>
          </>
        ) : (
          <div className="text-xs text-text-tertiary py-4 text-center">No active version. Run retraining.</div>
        )}
      </div>
    </div>
  );
}
