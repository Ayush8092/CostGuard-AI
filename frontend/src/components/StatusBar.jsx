import { useEffect, useState } from "react";
import api from "../api/client";

export default function StatusBar() {
    const [dbOk, setDbOk] = useState(null);
    const [redisOk, setRedisOk] = useState(null);

useEffect(() => {
  let mounted = true;

  async function check() {
    const [dbResult, redisResult] = await Promise.allSettled([
      api.get("/health/db"),
      api.get("/health/redis"),
    ]);

    if (!mounted) return;

    if (dbResult.status === "fulfilled") {
      setDbOk(dbResult.value.data.status === "ok");
    } else {
      console.warn("DB health check failed:", dbResult.reason);
    }

    if (redisResult.status === "fulfilled") {
      setRedisOk(redisResult.value.data.status === "ok");
    } else {
      console.warn("Redis health check failed:", redisResult.reason);
    }
  }

  check();

  const id = setInterval(check, 30000);

  return () => {
    mounted = false;
    clearInterval(id);
  };
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
