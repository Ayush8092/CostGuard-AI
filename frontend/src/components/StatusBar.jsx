import { useEffect, useState } from "react";
// import api from "../api/client";

export default function StatusBar() {
    const [dbOk, setDbOk] = useState(null);
    const [redisOk, setRedisOk] = useState(null);

useEffect(() => {
  const BACKEND_URL =
    import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

  function check() {
    fetch(`${BACKEND_URL}/health/db`)
      .then((r) => r.json())
      .then((data) => setDbOk(data.status === "ok"))
      .catch(() => setDbOk(false));

    fetch(`${BACKEND_URL}/health/redis`)
      .then((r) => r.json())
      .then((data) => setRedisOk(data.status === "ok"))
      .catch(() => setRedisOk(false));
  }

  check();

  const id = setInterval(check, 30000);

  return () => clearInterval(id);
}, []);
  const Dot = ({ ok, label, note }) => (
    <div className="flex items-center gap-1.5 text-[11px]" title={note}>
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
        ok === null ? "bg-text-tertiary animate-pulse" :
        ok ? "bg-signal-mint" : "bg-signal-red"
      }`} />
      <span className="text-text-tertiary">{label}</span>
      <span className={
        ok === null ? "text-text-tertiary" :
        ok ? "text-signal-mint" : "text-signal-red"
      }>
        {ok === null ? "..." : ok ? "OK" : "ERR"}
      </span>
    </div>
  );

  return (
    <div className="px-4 py-3 border-t border-border-subtle space-y-1.5">
      <Dot
        ok={dbOk}
        label="Database"
        note={dbOk === false ? "Postgres connection failed — check DATABASE_URL_OVERRIDE in .env" : "Neon PostgreSQL"}
      />
      <Dot
        ok={redisOk}
        label="Redis Cache"
        note={
          redisOk === false
            ? "Redis unavailable — app works fine without it, cache disabled"
            : "Upstash Redis"
        }
      />
      <div className="flex items-center gap-1.5 text-[11px]">
        <span className="w-1.5 h-1.5 rounded-full bg-signal-mint animate-pulse flex-shrink-0" />
        <span className="text-text-tertiary">Worker</span>
        <span className="text-signal-mint">Running</span>
      </div>
      {/* Show helpful note when Redis is down but app is still working */}
      {redisOk === false && (
        <div className="text-[10px] text-text-tertiary leading-tight pt-1 border-t border-border-subtle">
          Redis ERR = no caching only.<br />All features still work.
        </div>
      )}
    </div>
  );
}
