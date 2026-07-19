import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, Eye, EyeOff, TrendingDown, Brain, AlertTriangle, Zap } from "lucide-react";
import { useAuth } from "../context/AuthContext";

const FEATURES = [
  { icon: TrendingDown, title: "ML Cost Forecasting",     desc: "XGBoost quantile regression with confidence intervals" },
  { icon: AlertTriangle, title: "Anomaly Detection",      desc: "Multi-dimensional Isolation Forest — 5 signal dimensions" },
  { icon: Brain,         title: "AI FinOps Copilot",      desc: "Grounded LLM answers citing real billing data" },
  { icon: Zap,           title: "Waste Classification",   desc: "4-bucket scoring with SHAP explanations" },
];

export default function Login() {
  const [mode, setMode]         = useState("login");
  const [orgName, setOrgName]   = useState("");
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [error, setError]       = useState(null);
  const [loading, setLoading]   = useState(false);
  const { login, signup }       = useAuth();
  const navigate                = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (mode === "signup" && !orgName.trim()) { setError("Organization name is required."); return; }
    if (password.length < 8) { setError("Password must be at least 8 characters."); return; }
    setLoading(true);
    try {
      if (mode === "login") await login(email, password);
      else await signup(orgName, email, password, null);
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.detail || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-bg-base flex">
      {/* Left panel — branding */}
      <div className="hidden lg:flex flex-col justify-between w-1/2 bg-bg-surface border-r border-border-subtle p-12">
        <div>
          <div className="flex items-center gap-3 mb-12">
            <div className="w-10 h-10 rounded-xl bg-signal-mint/20 border border-signal-mint/30 flex items-center justify-center">
              <ShieldCheck className="w-6 h-6 text-signal-mint" />
            </div>
            <div>
              <div className="font-semibold text-text-primary text-lg leading-tight">CostGuard AI</div>
              <div className="text-xs text-text-tertiary font-data">FinOps Platform</div>
            </div>
          </div>

          <h1 className="text-3xl font-semibold text-text-primary leading-tight mb-4">
            AI-powered cloud cost<br />optimization at scale
          </h1>
          <p className="text-text-secondary text-sm leading-relaxed mb-10">
            Real ML models, grounded LLM recommendations, and actionable insights —
            all running at $0 on free-tier infrastructure.
          </p>

          <div className="space-y-5">
            {FEATURES.map(({ icon: Icon, title, desc }) => (
              <div key={title} className="flex items-start gap-4">
                <div className="w-9 h-9 rounded-lg bg-signal-mint/10 border border-signal-mint/20 flex items-center justify-center flex-shrink-0">
                  <Icon className="w-4 h-4 text-signal-mint" />
                </div>
                <div>
                  <div className="text-sm font-medium text-text-primary">{title}</div>
                  <div className="text-xs text-text-tertiary mt-0.5">{desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Stats strip */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Forecast Error Reduction", value: "~65%" },
            { label: "Avg Recommendation Confidence", value: "~92%" },
            { label: "Waste Detection Coverage", value: "~95%" },
          ].map(({ label, value }) => (
            <div key={label} className="bg-bg-raised border border-border-subtle rounded-lg p-3 text-center">
              <div className="font-data text-xl font-semibold text-signal-mint">{value}</div>
              <div className="text-[11px] text-text-tertiary mt-0.5">{label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Right panel — form */}
      <div className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          {/* Mobile logo */}
          <div className="flex items-center gap-2 justify-center mb-8 lg:hidden">
            <ShieldCheck className="w-7 h-7 text-signal-mint" />
            <span className="text-lg font-semibold text-text-primary">CostGuard AI</span>
          </div>

          <div className="mb-6">
            <h2 className="text-xl font-semibold text-text-primary">
              {mode === "login" ? "Welcome back" : "Create your account"}
            </h2>
            <p className="text-sm text-text-secondary mt-1">
              {mode === "login" ? "Sign in to your organization" : "Set up your FinOps workspace"}
            </p>
          </div>

          {/* Mode toggle */}
          <div className="flex gap-1 mb-6 bg-bg-surface border border-border-subtle rounded-lg p-1">
            {["login", "signup"].map(m => (
              <button key={m} onClick={() => { setMode(m); setError(null); }}
                className={`flex-1 text-sm py-2 rounded-md transition-colors font-medium ${
                  mode === m ? "bg-bg-raised text-text-primary" : "text-text-secondary hover:text-text-primary"
                }`}>
                {m === "login" ? "Log in" : "Sign up"}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === "signup" && (
              <div>
                <label className="text-xs text-text-secondary mb-1 block">Organization name</label>
                <input
                  placeholder="Acme Corp"
                  value={orgName}
                  onChange={e => setOrgName(e.target.value)}
                  required
                  className="w-full bg-bg-surface border border-border-subtle rounded-lg text-sm px-3 py-2.5 text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-signal-mint/50 transition-colors"
                />
              </div>
            )}

            <div>
              <label className="text-xs text-text-secondary mb-1 block">Email address</label>
              <input
                type="email"
                placeholder="you@company.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                className="w-full bg-bg-surface border border-border-subtle rounded-lg text-sm px-3 py-2.5 text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-signal-mint/50 transition-colors"
              />
            </div>

            <div>
              <label className="text-xs text-text-secondary mb-1 block">Password</label>
              <div className="relative">
                <input
                  type={showPass ? "text" : "password"}
                  placeholder="••••••••"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  minLength={8}
                  className="w-full bg-bg-surface border border-border-subtle rounded-lg text-sm px-3 py-2.5 pr-10 text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-signal-mint/50 transition-colors"
                />
                <button type="button" onClick={() => setShowPass(!showPass)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary hover:text-text-secondary">
                  {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {mode === "signup" && (
                <div className="mt-1.5 flex gap-1">
                  {[1,2,3,4].map(i => (
                    <div key={i} className={`h-1 flex-1 rounded-full transition-colors ${
                      password.length >= i * 3 ? (password.length >= 10 ? "bg-signal-mint" : "bg-signal-amber") : "bg-bg-raised"
                    }`} />
                  ))}
                </div>
              )}
            </div>

            {error && (
              <div className="bg-signal-red/10 border border-signal-red/30 rounded-lg px-3 py-2.5 text-xs text-signal-red">
                {error}
              </div>
            )}

            <button type="submit" disabled={loading}
              className="w-full bg-signal-mint text-bg-base font-semibold text-sm py-2.5 rounded-lg hover:bg-signal-mintDim transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
              {loading ? "Please wait..." : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>

          {/* Demo credentials hint */}
          <div className="mt-6 bg-bg-surface border border-border-subtle rounded-lg p-3">
            <div className="text-[11px] text-text-tertiary mb-1 font-medium">Demo credentials (after seeding)</div>
            <div className="font-data text-[11px] text-text-secondary space-y-0.5">
              <div>Email: <span className="text-text-primary">admin@costguard.demo</span></div>
              <div>Password: <span className="text-text-primary">CostGuard2024!</span></div>
            </div>
          </div>

          <p className="text-center text-[11px] text-text-tertiary mt-6">
            {mode === "login" ? "Don't have an account? " : "Already have an account? "}
            <button onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(null); }}
              className="text-signal-mint hover:underline">
              {mode === "login" ? "Sign up" : "Sign in"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
