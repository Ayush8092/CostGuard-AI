import { useState, useRef, useEffect } from "react";
import { Send, Wrench, BookOpen, AlertCircle, Brain, Sparkles, ChevronDown, ChevronUp } from "lucide-react";
import { copilotApi } from "../api/client";
import { PageHeader } from "../components/Status";

const SUGGESTED = [
  "Why did my bill increase?",
  "Which instances should I terminate?",
  "Show idle resources",
  "Compare last month vs this month",
  "Which VM had the highest network usage?",
  "Forecast EC2 cost for next week",
];

function UserBubble({ text }) {
  return (
    <div className="flex justify-end">
      <div className="bg-bg-raised border border-border-subtle rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm text-text-primary max-w-xl">
        {text}
      </div>
    </div>
  );
}

function AssistantBubble({ msg }) {
  const [traceOpen, setTraceOpen] = useState(false);
  return (
    <div className="flex gap-3 max-w-3xl">
      <div className="w-7 h-7 rounded-full bg-signal-mint/20 border border-signal-mint/30 flex items-center justify-center flex-shrink-0 mt-0.5">
        <Brain className="w-3.5 h-3.5 text-signal-mint" />
      </div>
      <div className="flex-1 space-y-2">
        {msg.is_stub && (
          <div className="flex items-center gap-2 text-[11px] text-signal-amber bg-signal-amber/10 border border-signal-amber/30 rounded-md px-3 py-1.5">
            <AlertCircle className="w-3 h-3 flex-shrink-0" />
            Stub mode — set GROQ_API_KEY or GEMINI_API_KEY in .env for live AI answers
          </div>
        )}

        <div className="bg-bg-surface border border-border-subtle rounded-2xl rounded-tl-sm px-4 py-3">
          <p className="text-sm text-text-primary whitespace-pre-wrap leading-relaxed">{msg.answer}</p>
        </div>

        {/* Tool trace */}
        {msg.tool_trace?.length > 0 && (
          <div className="bg-bg-raised border border-border-subtle rounded-lg overflow-hidden">
            <button onClick={() => setTraceOpen(!traceOpen)}
              className="w-full flex items-center justify-between px-3 py-2 text-xs text-text-tertiary hover:text-text-secondary">
              <span className="flex items-center gap-1.5">
                <Wrench className="w-3 h-3" />
                Tool trace ({msg.tool_trace.length} steps) — intent: <span className="text-text-secondary font-data">{msg.intent}</span>
              </span>
              {traceOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
            {traceOpen && (
              <div className="px-3 pb-3 space-y-1 border-t border-border-subtle pt-2">
                {msg.tool_trace.map((step, i) => (
                  <div key={i} className="flex items-start gap-2 text-[11px] font-data text-text-tertiary">
                    <span className="text-signal-mint mt-0.5">→</span>
                    <span>{step}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Citations */}
        {msg.citations?.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {msg.citations.map(c => (
              <span key={c.chunk_id}
                className="flex items-center gap-1 text-[11px] bg-bg-raised border border-border-subtle rounded-full px-2.5 py-1 text-text-secondary">
                <BookOpen className="w-3 h-3 text-signal-blue" />
                {c.title}
                <span className="text-text-tertiary font-data">{(c.similarity_score * 100).toFixed(0)}%</span>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ErrorBubble({ text }) {
  return (
    <div className="flex gap-3">
      <div className="w-7 h-7 rounded-full bg-signal-red/20 border border-signal-red/30 flex items-center justify-center flex-shrink-0">
        <AlertCircle className="w-3.5 h-3.5 text-signal-red" />
      </div>
      <div className="bg-signal-red/10 border border-signal-red/30 rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm text-signal-red max-w-xl">
        {text}
      </div>
    </div>
  );
}

export default function Copilot() {
  const [messages, setMessages] = useState([]);
  const [input, setInput]       = useState("");
  const [loading, setLoading]   = useState(false);
  const scrollRef = useRef(null);
  const inputRef  = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(question) {
    const q = (question || input).trim();
    if (!q || loading) return;
    setInput("");
    setMessages(prev => [...prev, { role: "user", text: q }]);
    setLoading(true);
    try {
      const res = await copilotApi.ask(q);
      setMessages(prev => [...prev, { role: "assistant", ...res.data }]);
    } catch (err) {
      const detail = err.response?.data?.detail || "Something went wrong. Please try again.";
      setMessages(prev => [...prev, { role: "error", text: detail }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  }

  return (
    <div className="flex flex-col h-screen">
      <PageHeader title="AI Copilot"
        description="Ask anything about your cloud costs — grounded in real ML outputs and knowledge base citations, never fabricated" />

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto px-8 py-6">
        {messages.length === 0 && (
          <div className="max-w-3xl mx-auto">
            {/* Welcome card */}
            <div className="bg-bg-surface border border-border-subtle rounded-xl p-6 mb-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-full bg-signal-mint/20 border border-signal-mint/30 flex items-center justify-center">
                  <Sparkles className="w-5 h-5 text-signal-mint" />
                </div>
                <div>
                  <div className="text-sm font-medium text-text-primary">CostGuard AI Copilot</div>
                  <div className="text-xs text-text-tertiary">Grounded in your real billing data and ML model outputs</div>
                </div>
              </div>
              <p className="text-sm text-text-secondary leading-relaxed">
                Ask me anything about your cloud costs. Every answer cites the exact data source it used — 
                no invented numbers, no hallucinations. I can explain anomalies, forecast costs, identify waste, 
                compare time periods, and recommend optimizations.
              </p>
            </div>

            {/* Suggested questions */}
            <div className="mb-4">
              <p className="text-xs text-text-secondary mb-3">Try asking:</p>
              <div className="flex flex-wrap gap-2">
                {SUGGESTED.map(q => (
                  <button key={q} onClick={() => send(q)}
                    className="text-xs bg-bg-surface border border-border-subtle rounded-full px-3 py-1.5 text-text-secondary hover:text-text-primary hover:border-signal-mint/40 hover:bg-bg-hover transition-colors">
                    {q}
                  </button>
                ))}
              </div>
            </div>

            {/* Capability cards */}
            <div className="grid grid-cols-3 gap-3">
              {[
                { icon: "📊", title: "Data queries",    desc: "Spend breakdowns, period comparisons, resource rankings" },
                { icon: "🔍", title: "Anomaly insight", desc: "Why costs spiked, which resources are behaving unusually" },
                { icon: "💡", title: "Optimization",    desc: "Which instances to terminate, resize, or right-size" },
              ].map(c => (
                <div key={c.title} className="bg-bg-surface border border-border-subtle rounded-lg p-3">
                  <div className="text-lg mb-1">{c.icon}</div>
                  <div className="text-xs font-medium text-text-primary mb-0.5">{c.title}</div>
                  <div className="text-[11px] text-text-tertiary">{c.desc}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="max-w-3xl mx-auto space-y-4">
          {messages.map((m, i) => (
            m.role === "user"       ? <UserBubble key={i} text={m.text} /> :
            m.role === "error"      ? <ErrorBubble key={i} text={m.text} /> :
            m.role === "assistant"  ? <AssistantBubble key={i} msg={m} /> : null
          ))}

          {loading && (
            <div className="flex gap-3">
              <div className="w-7 h-7 rounded-full bg-signal-mint/20 border border-signal-mint/30 flex items-center justify-center flex-shrink-0">
                <Brain className="w-3.5 h-3.5 text-signal-mint animate-pulse" />
              </div>
              <div className="bg-bg-surface border border-border-subtle rounded-2xl rounded-tl-sm px-4 py-3">
                <div className="flex gap-1 items-center h-5">
                  <span className="w-1.5 h-1.5 bg-text-tertiary rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-1.5 h-1.5 bg-text-tertiary rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-1.5 h-1.5 bg-text-tertiary rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              </div>
            </div>
          )}
          <div ref={scrollRef} />
        </div>
      </div>

      {/* Input bar */}
      <div className="border-t border-border-subtle bg-bg-surface px-8 py-4">
        <div className="max-w-3xl mx-auto flex gap-3">
          <textarea
            ref={inputRef}
            rows={1}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask about your cloud costs... (Enter to send, Shift+Enter for new line)"
            className="flex-1 bg-bg-raised border border-border-subtle rounded-xl text-sm px-4 py-2.5 text-text-primary placeholder:text-text-tertiary resize-none focus:outline-none focus:border-signal-mint/50 transition-colors"
            style={{ minHeight: "42px", maxHeight: "120px" }}
          />
          <button onClick={() => send()} disabled={loading || !input.trim()}
            className="bg-signal-mint text-bg-base px-4 rounded-xl hover:bg-signal-mintDim transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center">
            <Send className="w-4 h-4" />
          </button>
        </div>
        <p className="max-w-3xl mx-auto text-[11px] text-text-tertiary mt-2">
          Every answer cites its data source. The LLM only narrates numbers from your real billing data — it never invents figures.
        </p>
      </div>
    </div>
  );
}
