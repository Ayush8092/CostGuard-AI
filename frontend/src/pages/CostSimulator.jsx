import { useState } from "react";
import { Plus, Trash2, Play, DollarSign, TrendingDown, Zap, Info } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { simulatorApi } from "../api/client";
import { C, TOOLTIP_STYLE } from "../components/ChartColors";
import { PageHeader } from "../components/Status";

export default function CostSimulator() {
  const [actions, setActions] = useState([{ resource_id: "", action_type: "terminate", new_hourly_rate: "" }]);
  const [result, setResult]   = useState(null);
  const [status, setStatus]   = useState("idle");
  const [error, setError]     = useState(null);

  function addAction()           { setActions(a => [...a, { resource_id: "", action_type: "terminate", new_hourly_rate: "" }]); }
  function removeAction(i)       { setActions(a => a.filter((_, idx) => idx !== i)); }
  function updateAction(i, k, v) { setActions(a => a.map((x, idx) => idx === i ? { ...x, [k]: v } : x)); }

  async function runSimulation() {
    const valid = actions.filter(a => a.resource_id.trim());
    if (!valid.length) { setError("Add at least one resource ID."); return; }
    setStatus("loading"); setError(null); setResult(null);
    try {
      const payload = valid.map(a => ({
        resource_id: a.resource_id.trim(),
        action_type: a.action_type,
        new_hourly_rate: a.action_type === "resize" ? parseFloat(a.new_hourly_rate) || 0 : null,
      }));
      const res = await simulatorApi.simulate(payload);
      setResult(res.data);
      setStatus("ready");
    } catch (e) {
      setError(e.response?.data?.detail || "Simulation failed — check resource IDs and try again.");
      setStatus("error");
    }
  }

  const savingsPct = result
    ? ((result.current_monthly_cost - result.projected_monthly_cost) / Math.max(result.current_monthly_cost, 1) * 100)
    : 0;

  const chartData = result ? [
    { label: "Current",   cost: result.current_monthly_cost,   fill: C.red   },
    { label: "Projected", cost: result.projected_monthly_cost, fill: C.mint  },
  ] : [];

  return (
    <div>
      <PageHeader title="Cost Simulator" description="Model the financial impact of terminating or resizing resources before taking action" />
      <div className="px-8 py-6">
        <div className="grid grid-cols-2 gap-8">

          {/* LEFT — Actions builder */}
          <div className="space-y-5">
            <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
              <h2 className="text-sm font-medium text-text-primary mb-1">Hypothetical Actions</h2>
              <p className="text-xs text-text-secondary mb-4">
                Enter resource IDs exactly as they appear in the Waste Classification or Recommendations tab.
              </p>

              <div className="space-y-3">
                {actions.map((action, idx) => (
                  <div key={idx} className="bg-bg-raised border border-border-subtle rounded-lg p-3 space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-text-tertiary w-5">{idx + 1}.</span>
                      <input
                        placeholder="Resource ID (e.g. ec2-dev-003)"
                        value={action.resource_id}
                        onChange={e => updateAction(idx, "resource_id", e.target.value)}
                        className="flex-1 bg-bg-surface border border-border-subtle rounded-md text-xs px-3 py-2 text-text-primary font-data placeholder:text-text-tertiary focus:outline-none focus:border-signal-mint/50"
                      />
                      <button onClick={() => removeAction(idx)} className="text-text-tertiary hover:text-signal-red p-1 transition-colors">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    <div className="flex items-center gap-2 pl-5">
                      <select value={action.action_type} onChange={e => updateAction(idx, "action_type", e.target.value)}
                        className="bg-bg-surface border border-border-subtle rounded-md text-xs px-2 py-1.5 text-text-primary">
                        <option value="terminate">Terminate (remove entirely)</option>
                        <option value="resize">Resize (change hourly rate)</option>
                      </select>
                      {action.action_type === "resize" && (
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs text-text-tertiary">New rate:</span>
                          <input
                            placeholder="$/hr"
                            type="number"
                            step="0.001"
                            min="0"
                            value={action.new_hourly_rate}
                            onChange={e => updateAction(idx, "new_hourly_rate", e.target.value)}
                            className="w-24 bg-bg-surface border border-border-subtle rounded-md text-xs px-2 py-1.5 text-text-primary font-data"
                          />
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex items-center gap-3 mt-4">
                <button onClick={addAction}
                  className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-signal-mint transition-colors">
                  <Plus className="w-3.5 h-3.5" /> Add action
                </button>
                <button onClick={runSimulation} disabled={status === "loading"}
                  className="flex items-center gap-2 bg-signal-mint text-bg-base font-medium text-sm px-4 py-2 rounded-md hover:bg-signal-mintDim transition-colors disabled:opacity-50 ml-auto">
                  <Play className="w-3.5 h-3.5" />
                  {status === "loading" ? "Running..." : "Run Simulation"}
                </button>
              </div>

              {error && (
                <div className="mt-3 bg-signal-red/10 border border-signal-red/30 rounded-md px-3 py-2 text-xs text-signal-red">
                  {error}
                </div>
              )}
            </div>

            {/* How it works */}
            <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <Info className="w-3.5 h-3.5 text-signal-blue" />
                <h3 className="text-xs font-medium text-text-primary">How the simulation works</h3>
              </div>
              <div className="space-y-2 text-[11px] text-text-tertiary">
                <p>• Loads your last 30 days of real billing data from the database</p>
                <p>• For <strong className="text-text-secondary">Terminate</strong>: sets that resource's cost to $0 in the window</p>
                <p>• For <strong className="text-text-secondary">Resize</strong>: recalculates cost using the new hourly rate × actual usage hours</p>
                <p>• Annualizes the adjusted daily average to project monthly cost</p>
                <p className="pt-1 text-[10px] border-t border-border-subtle">
                  Savings formula: <span className="font-data text-text-secondary">(current_hourly_rate − recommended_hourly_rate) × projected_runtime_hours</span>
                </p>
              </div>
            </div>
          </div>

          {/* RIGHT — Results */}
          <div className="space-y-5">
            {status === "idle" && (
              <div className="bg-bg-surface border border-border-subtle rounded-lg p-8 text-center">
                <Zap className="w-8 h-8 text-text-tertiary mx-auto mb-3" />
                <p className="text-sm text-text-secondary">Add actions and run the simulation to see projected cost impact.</p>
              </div>
            )}

            {status === "ready" && result && (
              <>
                {/* Summary KPIs */}
                <div className="grid grid-cols-3 gap-4">
                  {[
                    { label: "Current Monthly Cost",   value: `$${result.current_monthly_cost?.toLocaleString(undefined,{maximumFractionDigits:0})}`, icon: DollarSign, accent: "" },
                    { label: "Projected Monthly Cost", value: `$${result.projected_monthly_cost?.toLocaleString(undefined,{maximumFractionDigits:0})}`, icon: TrendingDown, accent: "blue" },
                    { label: "Monthly Savings",        value: `$${result.savings?.toLocaleString(undefined,{maximumFractionDigits:0})}`, icon: Zap, accent: "mint" },
                  ].map(({ label, value, icon: Icon, accent }) => (
                    <div key={label} className="bg-bg-surface border border-border-subtle rounded-lg p-4">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[11px] text-text-secondary">{label}</span>
                        <Icon className="w-3.5 h-3.5 text-text-tertiary" />
                      </div>
                      <div className={`font-data text-xl font-semibold ${
                        accent === "mint" ? "text-signal-mint" : accent === "blue" ? "text-signal-blue" : "text-text-primary"
                      }`}>{value}</div>
                    </div>
                  ))}
                </div>

                {/* Savings percentage badge */}
                {savingsPct > 0 && (
                  <div className="bg-signal-mint/10 border border-signal-mint/30 rounded-lg p-4 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-signal-mint/20 flex items-center justify-center">
                      <TrendingDown className="w-5 h-5 text-signal-mint" />
                    </div>
                    <div>
                      <div className="font-data text-2xl font-semibold text-signal-mint">{savingsPct.toFixed(1)}% reduction</div>
                      <div className="text-xs text-text-secondary">in projected monthly cloud spend</div>
                    </div>
                  </div>
                )}

                {/* Before/After chart */}
                <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
                  <h3 className="text-sm font-medium text-text-primary mb-4">Before vs After Comparison</h3>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={chartData} barSize={60}>
                      <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
                      <XAxis dataKey="label" stroke={C.text} fontSize={12} />
                      <YAxis stroke={C.text} fontSize={11} tickFormatter={v => `$${v}`} />
                      <Tooltip {...TOOLTIP_STYLE} formatter={v => [`$${Number(v).toLocaleString(undefined,{maximumFractionDigits:0})}`, "Monthly Cost"]} />
                      <Bar dataKey="cost" radius={[6,6,0,0]} name="Monthly Cost ($)">
                        {chartData.map((e, i) => <Cell key={i} fill={e.fill} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {/* Actions applied detail */}
                <div className="bg-bg-surface border border-border-subtle rounded-lg p-5">
                  <h3 className="text-sm font-medium text-text-primary mb-3">Actions Applied</h3>
                  <div className="space-y-2">
                    {result.actions_applied?.map((a, i) => (
                      <div key={i} className={`flex items-start justify-between gap-3 px-3 py-2.5 rounded-md border text-xs ${
                        a.applied ? "bg-signal-mint/5 border-signal-mint/20" : "bg-signal-amber/5 border-signal-amber/20"
                      }`}>
                        <div>
                          <span className="font-data text-text-primary">{a.resource_id}</span>
                          <span className={`ml-2 capitalize ${a.applied ? "text-signal-mint" : "text-signal-amber"}`}>
                            {a.applied ? `✓ ${a.action}` : `⚠ ${a.note}`}
                          </span>
                        </div>
                        {a.applied && (
                          <span className="font-data text-text-tertiary text-[11px] flex-shrink-0">
                            {a.action === "terminate"
                              ? `–$${a.cost_removed_in_window?.toFixed(2)} in window`
                              : `$${a.cost_before_in_window?.toFixed(2)} → $${a.cost_after_in_window?.toFixed(2)}`}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
