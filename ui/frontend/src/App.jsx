import { useState, useEffect, useRef, useCallback } from "react";

// ─── Types ───────────────────────────────────────────────────────────────────

const ACTION_COLORS = {
  block: "#ff2d2d",
  alert: "#ffaa00",
  allow: "#00e676",
};
const GUARD_ICONS = { prompt: "⌨", rag: "📄", tool: "⚙" };
const CATEGORY_COLORS = {
  injection: "#ff6b6b",
  extraction: "#ffa94d",
  jailbreak: "#cc5de8",
  anomaly: "#4dabf7",
  mcp_poisoning: "#f06595",
  blocked_tool: "#ff2d2d",
  param_injection: "#ff8787",
  rate_limit: "#ffd43b",
  sequence_abuse: "#e599f7",
  rag_poisoning: "#ff8787",
  clean: "#51cf66",
};

// ─── Hooks ───────────────────────────────────────────────────────────────────

function useAnzenData() {
  const [events, setEvents] = useState([]);
  const [paused, setPaused] = useState(false);
  const [wsStatus, setWsStatus] = useState("disconnected"); // "live" | "disconnected"
  const pausedRef = useRef(false);

  useEffect(() => { pausedRef.current = paused; }, [paused]);

  // Fetch persisted events on mount
  useEffect(() => {
    const apiUrl = import.meta?.env?.VITE_API_URL || "";
    fetch(`${apiUrl}/api/events?limit=100`)
      .then(r => r.json())
      .then(data => {
        if (Array.isArray(data)) setEvents(data);
      })
      .catch(() => { });
  }, []);

  // WebSocket for real-time events with auto-reconnect
  useEffect(() => {
    const _loc = window.location;
    const wsUrl = import.meta?.env?.VITE_WS_URL || `${_loc.protocol === "https:" ? "wss:" : "ws:"}//${_loc.host}/api/ws`;
    let ws;
    let reconnectTimeout;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 10;
    const baseDelay = 1000; // 1 second

    const connectWs = () => {
      try {
        ws = new WebSocket(wsUrl);
        ws.onopen = () => {
          setWsStatus("live");
          reconnectAttempts = 0; // reset on successful connection
        };
        ws.onclose = () => {
          setWsStatus("disconnected");
          // Auto-reconnect with exponential backoff
          if (reconnectAttempts < maxReconnectAttempts) {
            const delay = baseDelay * Math.pow(2, reconnectAttempts);
            reconnectTimeout = setTimeout(() => {
              reconnectAttempts++;
              connectWs();
            }, delay);
          }
        };
        ws.onerror = () => setWsStatus("disconnected");
        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data);
            if (msg.type === "event" && !pausedRef.current) {
              setEvents(prev => [msg.data, ...prev].slice(0, 500));
            }
          } catch { }
        };
      } catch { }
    };

    connectWs();

    return () => {
      clearTimeout(reconnectTimeout);
      ws?.close();
    };
  }, []);

  const stats = useStats(events);
  const exportEvents = async (format) => {
    const apiUrl = import.meta?.env?.VITE_API_URL || "";
    const r = await fetch(`${apiUrl}/api/events?limit=10000`);
    if (!r.ok) return;
    const data = await r.json();
    if (!Array.isArray(data)) return;
    const ts = new Date().toISOString().slice(0, 10);
    if (format === "json") {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `anzen-events-${ts}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
    } else {
      const headers = ["timestamp", "event_id", "session_id", "guard_type", "action", "category", "risk_score", "confidence", "explanation", "input_text", "latency_ms"];
      const escape = (v) => (v == null ? "" : String(v).replace(/"/g, '""'));
      const row = (e) => headers.map((h) => `"${escape(e[h])}"`).join(",");
      const csv = [headers.join(","), ...data.map(row)].join("\n");
      const blob = new Blob([csv], { type: "text/csv" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `anzen-events-${ts}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
    }
  };
  return { events, paused, setPaused, wsStatus, stats, exportEvents };
}

function useStats(events) {
  const total = events.length;
  const blocked = events.filter(e => e.action === "block").length;
  const alerted = events.filter(e => e.action === "alert").length;
  const avgRisk = total ? (events.reduce((s, e) => s + e.risk_score, 0) / total) : 0;
  const avgLat = total ? (events.reduce((s, e) => s + e.latency_ms, 0) / total) : 0;

  const byCategory = {};
  const byGuard = {};
  events.forEach(e => {
    byCategory[e.category] = (byCategory[e.category] || 0) + 1;
    byGuard[e.guard_type] = (byGuard[e.guard_type] || 0) + 1;
  });

  const trend = events.slice(0, 40).reverse().map(e => e.risk_score);
  return { total, blocked, alerted, avgRisk, avgLat, byCategory, byGuard, trend };
}

// ─── Components ──────────────────────────────────────────────────────────────

function Scanline() {
  return (
    <div style={{
      position: "fixed", inset: 0, pointerEvents: "none", zIndex: 9999,
      background: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px)",
    }} />
  );
}

function RiskMeter({ score }) {
  const color = score > 0.85 ? "#ff2d2d" : score > 0.5 ? "#ffaa00" : "#00e676";
  const pct = Math.round(score * 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{
        width: 60, height: 5, background: "#1a1a1a", borderRadius: 2, overflow: "hidden"
      }}>
        <div style={{
          width: `${pct}%`, height: "100%", background: color,
          borderRadius: 2, transition: "width 0.3s ease",
          boxShadow: score > 0.5 ? `0 0 6px ${color}` : "none",
        }} />
      </div>
      <span style={{ fontFamily: "monospace", fontSize: 11, color, minWidth: 30 }}>{pct}%</span>
    </div>
  );
}

function Sparkline({ values, color = "#00e676", width = 100, height = 28 }) {
  if (!values.length) return null;
  const max = Math.max(...values, 0.01);
  const step = (width - 4) / Math.max(values.length - 1, 1);
  const pts = values.map((v, i) =>
    `${2 + i * step},${2 + (1 - v / max) * (height - 4)}`
  ).join(" ");
  return (
    <svg width={width} height={height}>
      <defs>
        <linearGradient id="sg" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5"
        strokeLinejoin="round" strokeLinecap="round" opacity="0.85" />
    </svg>
  );
}

function StatBlock({ label, value, sub, trend, accent = "#00e676", mono = true }) {
  return (
    <div style={{
      background: "#0c0c0c", border: "1px solid #1e1e1e",
      borderTop: `2px solid ${accent}`,
      padding: "16px 20px", display: "flex", flexDirection: "column", gap: 6,
      position: "relative",
    }}>
      <span style={{ fontSize: 10, color: "#444", textTransform: "uppercase", letterSpacing: "0.12em" }}>
        {label}
      </span>
      <span style={{
        fontSize: 30, fontWeight: 700, lineHeight: 1,
        color: "#e8e8e8",
        fontFamily: mono ? "'IBM Plex Mono','Fira Code',monospace" : "inherit",
      }}>
        {value}
      </span>
      {sub && <span style={{ fontSize: 10, color: "#555" }}>{sub}</span>}
      {trend && <Sparkline values={trend} color={accent} />}
    </div>
  );
}

function ActionBadge({ action }) {
  const c = ACTION_COLORS[action] || "#555";
  return (
    <span style={{
      background: `${c}15`, border: `1px solid ${c}50`,
      color: c, fontSize: 9, fontWeight: 700, fontFamily: "monospace",
      padding: "2px 7px", borderRadius: 2,
      textTransform: "uppercase", letterSpacing: "0.1em",
      display: "inline-flex", alignItems: "center", gap: 4,
    }}>
      <span style={{
        width: 5, height: 5, borderRadius: "50%", background: c,
        boxShadow: action === "block" ? `0 0 5px ${c}` : "none",
        display: "inline-block",
      }} />
      {action}
    </span>
  );
}

function CategoryTag({ category }) {
  const c = CATEGORY_COLORS[category] || "#888";
  return (
    <span style={{
      color: c, fontSize: 9, fontWeight: 700, fontFamily: "monospace",
      textTransform: "uppercase", letterSpacing: "0.08em",
      background: `${c}12`, border: `1px solid ${c}30`,
      padding: "2px 6px", borderRadius: 2,
    }}>
      {category.replace(/_/g, " ")}
    </span>
  );
}

function GuardIcon({ type }) {
  const icons = { prompt: "[ ]", rag: "{ }", tool: "< >" };
  const colors = { prompt: "#4dabf7", rag: "#ffa94d", tool: "#a9e34b" };
  return (
    <span style={{
      fontFamily: "monospace", fontSize: 10, color: colors[type] || "#666",
      fontWeight: 700, letterSpacing: "-0.05em",
    }}>
      {icons[type] || "..."}
    </span>
  );
}

function EventRow({ event, selected, onClick }) {
  const ts = new Date(event.timestamp);
  const timeStr = ts.toLocaleTimeString(navigator.language || "en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const isBlocked = event.action === "block";

  return (
    <div onClick={() => onClick(event)} style={{
      display: "grid",
      gridTemplateColumns: "72px 36px 70px 90px 1fr 130px",
      gap: 12, alignItems: "center",
      padding: "8px 16px",
      borderBottom: "1px solid #111",
      background: selected ? "#141414" : isBlocked ? "#ff2d2d08" : "transparent",
      borderLeft: selected ? "2px solid #00e676" : "2px solid transparent",
      cursor: "pointer",
      transition: "background 0.1s",
    }}>
      <span style={{ fontFamily: "monospace", fontSize: 10, color: "#444" }}>{timeStr}</span>
      <GuardIcon type={event.guard_type} />
      <CategoryTag category={event.category} />
      <span style={{ fontFamily: "monospace", fontSize: 9, color: "#555" }}>
        {event.session_id}
      </span>
      <span style={{
        fontSize: 11, color: "#999",
        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
      }}>
        {event.input_text || "—"}
      </span>
      <div style={{ display: "flex", alignItems: "center", gap: 10, justifyContent: "flex-end" }}>
        <ActionBadge action={event.action} />
        <RiskMeter score={event.risk_score} />
      </div>
    </div>
  );
}

function EventDetail({ event, onClose }) {
  if (!event) return (
    <div style={{
      flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
      color: "#2a2a2a", fontSize: 12, fontFamily: "monospace",
      border: "1px solid #1a1a1a", background: "#0a0a0a",
    }}>
      SELECT AN EVENT
    </div>
  );

  const rows = [
    ["EVENT ID", event.event_id],
    ["SESSION", event.session_id],
    ["GUARD", event.guard_type.toUpperCase()],
    ["CATEGORY", event.category],
    ["RISK SCORE", `${(event.risk_score * 100).toFixed(1)}%`],
    ["CONFIDENCE", `${(event.confidence * 100).toFixed(1)}%`],
    ["LAYER", `Layer ${event.layer}`],
    ["LATENCY", `${event.latency_ms.toFixed(1)}ms`],
    ["CUMULATIVE", event.cumulative_risk?.toFixed(2)],
    ["ACTION", event.action.toUpperCase()],
  ];

  const ac = ACTION_COLORS[event.action] || "#555";

  return (
    <div style={{
      background: "#0a0a0a", border: "1px solid #1e1e1e",
      borderTop: `2px solid ${ac}`,
      padding: 20, display: "flex", flexDirection: "column", gap: 16,
      fontFamily: "monospace",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 10, color: "#555", letterSpacing: "0.12em" }}>EVENT DETAIL</span>
        <button onClick={onClose} style={{
          background: "none", border: "1px solid #2a2a2a", color: "#555",
          cursor: "pointer", fontSize: 12, padding: "2px 8px", borderRadius: 2,
          fontFamily: "monospace",
        }}>X</button>
      </div>

      {/* Input text */}
      <div>
        <div style={{ fontSize: 9, color: "#444", marginBottom: 6, letterSpacing: "0.1em" }}>INPUT</div>
        <div style={{
          background: "#111", border: "1px solid #1e1e1e",
          padding: "10px 12px", fontSize: 11, color: "#ccc",
          lineHeight: 1.7, wordBreak: "break-word",
          borderLeft: `2px solid ${ac}`,
        }}>
          {event.input_text || "—"}
        </div>
      </div>

      {/* Explanation */}
      <div>
        <div style={{ fontSize: 9, color: "#444", marginBottom: 6, letterSpacing: "0.1em" }}>EXPLANATION</div>
        <div style={{ fontSize: 11, color: "#888", lineHeight: 1.6 }}>
          {event.explanation}
        </div>
      </div>

      {/* Risk bar */}
      <div>
        <div style={{ fontSize: 9, color: "#444", marginBottom: 6, letterSpacing: "0.1em" }}>RISK SCORE</div>
        <div style={{ background: "#111", height: 8, borderRadius: 1, overflow: "hidden" }}>
          <div style={{
            width: `${event.risk_score * 100}%`, height: "100%",
            background: ac,
            boxShadow: `0 0 8px ${ac}`,
            transition: "width 0.4s ease",
          }} />
        </div>
      </div>

      {/* Fields grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 16px" }}>
        {rows.map(([k, v]) => (
          <div key={k}>
            <div style={{ fontSize: 9, color: "#3a3a3a", letterSpacing: "0.1em", marginBottom: 2 }}>{k}</div>
            <div style={{ fontSize: 11, color: "#888" }}>{v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CategoryBreakdown({ byCategory }) {
  const entries = Object.entries(byCategory)
    .filter(([k]) => k !== "clean")
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);
  const maxVal = Math.max(...entries.map(e => e[1]), 1);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {entries.map(([cat, count]) => {
        const c = CATEGORY_COLORS[cat] || "#555";
        return (
          <div key={cat} style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{
              width: 90, fontSize: 9, color: c, textTransform: "uppercase",
              letterSpacing: "0.07em", fontWeight: 700, fontFamily: "monospace",
            }}>
              {cat.replace(/_/g, " ")}
            </span>
            <div style={{ flex: 1, height: 4, background: "#1a1a1a", borderRadius: 1 }}>
              <div style={{
                width: `${(count / maxVal) * 100}%`, height: "100%",
                background: c, borderRadius: 1, opacity: 0.8,
                transition: "width 0.5s ease",
                boxShadow: count > maxVal * 0.6 ? `0 0 6px ${c}` : "none",
              }} />
            </div>
            <span style={{ fontFamily: "monospace", fontSize: 10, color: "#444", minWidth: 24, textAlign: "right" }}>
              {count}
            </span>
          </div>
        );
      })}
      {entries.length === 0 && (
        <span style={{ fontSize: 10, color: "#333", fontFamily: "monospace" }}>NO THREATS DETECTED</span>
      )}
    </div>
  );
}

function SessionsPanel({ events }) {
  const bySession = {};
  events.forEach(e => {
    if (!bySession[e.session_id]) bySession[e.session_id] = {
      id: e.session_id, total: 0, blocked: 0, maxRisk: 0
    };
    bySession[e.session_id].total++;
    if (e.action === "block") bySession[e.session_id].blocked++;
    bySession[e.session_id].maxRisk = Math.max(bySession[e.session_id].maxRisk, e.risk_score);
  });

  const sessions = Object.values(bySession)
    .sort((a, b) => b.maxRisk - a.maxRisk)
    .slice(0, 8);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {sessions.map(s => {
        const risk = s.maxRisk;
        const c = risk > 0.85 ? "#ff2d2d" : risk > 0.5 ? "#ffaa00" : "#00e676";
        return (
          <div key={s.id} style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "5px 10px",
            background: s.blocked > 0 ? "#ff2d2d08" : "transparent",
            border: "1px solid",
            borderColor: s.blocked > 0 ? "#ff2d2d20" : "#151515",
            borderRadius: 2,
          }}>
            <span style={{ fontFamily: "monospace", fontSize: 10, color: "#555", flex: 1 }}>
              {s.id}
            </span>
            <span style={{ fontFamily: "monospace", fontSize: 9, color: "#444" }}>
              {s.total} evt
            </span>
            {s.blocked > 0 && (
              <span style={{ fontFamily: "monospace", fontSize: 9, color: "#ff2d2d" }}>
                {s.blocked} blk
              </span>
            )}
            <span style={{
              fontFamily: "monospace", fontSize: 9, color: c,
              fontWeight: 700,
            }}>
              {Math.round(risk * 100)}%
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const { events, paused, setPaused, wsStatus, stats, exportEvents } = useAnzenData();
  const [selected, setSelected] = useState(null);
  const [filterAction, setFilterAction] = useState("all");
  const [filterGuard, setFilterGuard] = useState("all");
  const [activeTab, setActiveTab] = useState("stream"); // stream | sessions | breakdown
  const [tick, setTick] = useState(0);

  // Clock tick
  useEffect(() => {
    const i = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(i);
  }, []);

  const filtered = events.filter(e => {
    if (filterAction !== "all" && e.action !== filterAction) return false;
    if (filterGuard !== "all" && e.guard_type !== filterGuard) return false;
    return true;
  });

  const wsColor = wsStatus === "live" ? "#00e676" : wsStatus === "demo" ? "#ffaa00" : "#ff2d2d";
  const wsLabel = wsStatus === "live" ? "LIVE" : wsStatus === "demo" ? "DEMO" : "OFFLINE";

  const btnBase = {
    background: "none", border: "1px solid #1e1e1e", color: "#444",
    fontSize: 9, padding: "3px 9px", cursor: "pointer",
    fontFamily: "monospace", textTransform: "uppercase", letterSpacing: "0.1em",
    borderRadius: 2, transition: "all 0.15s",
  };
  const btnActive = { ...btnBase, background: "#1a1a1a", borderColor: "#333", color: "#aaa" };

  return (
    <div style={{
      minHeight: "100vh",
      background: "#080808",
      color: "#cccccc",
      fontFamily: "'IBM Plex Mono','Fira Code','Cascadia Code',monospace",
      display: "flex", flexDirection: "column",
    }}>
      <Scanline />

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: #0a0a0a; }
        ::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 2px; }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
        @keyframes slideDown { from{opacity:0;transform:translateY(-6px)} to{opacity:1;transform:translateY(0)} }
        @keyframes glow { 0%,100%{box-shadow:0 0 4px #ff2d2d} 50%{box-shadow:0 0 12px #ff2d2d,0 0 24px #ff2d2d40} }
      `}</style>

      {/* ── Topbar ────────────────────────────────────────────────────────── */}
      <div style={{
        height: 48, background: "#080808",
        borderBottom: "1px solid #1a1a1a",
        display: "flex", alignItems: "center",
        padding: "0 20px", gap: 20,
        position: "sticky", top: 0, zIndex: 100,
      }}>
        {/* Logo */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <svg width="22" height="22" viewBox="0 0 22 22">
            <polygon points="11,1 21,6.5 21,15.5 11,21 1,15.5 1,6.5"
              fill="none" stroke="#00e676" strokeWidth="1.5" />
            <polygon points="11,5 17,8.5 17,13.5 11,17 5,13.5 5,8.5"
              fill="#00e676" opacity="0.15" />
            <circle cx="11" cy="11" r="2.5" fill="#00e676" />
          </svg>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#e8e8e8", letterSpacing: "0.08em" }}>
              <span style={{ color: "#00e676" }}>ANZEN</span>
            </div>
            <div style={{ fontSize: 8, color: "#333", letterSpacing: "0.15em" }}>
              OPEN-SOURCE SECURITY LAYER FOR AGENTIC AI
            </div>
          </div>
        </div>

        <div style={{ width: 1, height: 24, background: "#1a1a1a" }} />

        {/* WS status */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{
            width: 6, height: 6, borderRadius: "50%",
            background: wsColor,
            boxShadow: wsStatus === "live" ? `0 0 6px ${wsColor}` : "none",
            animation: wsStatus === "live" ? "blink 2s infinite" : "none",
          }} />
          <span style={{ fontSize: 9, color: wsColor, letterSpacing: "0.12em" }}>{wsLabel}</span>
        </div>

        {/* Event counts */}
        <div style={{ display: "flex", gap: 16 }}>
          {[
            ["BLOCKED", stats.blocked, "#ff2d2d"],
            ["ALERTED", stats.alerted, "#ffaa00"],
            ["TOTAL", stats.total, "#444"],
          ].map(([l, v, c]) => (
            <div key={l} style={{ display: "flex", gap: 5, alignItems: "baseline" }}>
              <span style={{ fontSize: 16, fontWeight: 700, color: c }}>{v}</span>
              <span style={{ fontSize: 8, color: "#333", letterSpacing: "0.1em" }}>{l}</span>
            </div>
          ))}
        </div>

        <div style={{ flex: 1 }} />

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button
            onClick={() => exportEvents("json")}
            style={{
              background: "none", border: "1px solid #1e1e1e", color: "#666",
              fontSize: 9, padding: "4px 10px", cursor: "pointer",
              fontFamily: "monospace", textTransform: "uppercase", letterSpacing: "0.1em",
              borderRadius: 2,
            }}
            title="Export all events as JSON"
          >
            Export JSON
          </button>
          <button
            onClick={() => exportEvents("csv")}
            style={{
              background: "none", border: "1px solid #1e1e1e", color: "#666",
              fontSize: 9, padding: "4px 10px", cursor: "pointer",
              fontFamily: "monospace", textTransform: "uppercase", letterSpacing: "0.1em",
              borderRadius: 2,
            }}
            title="Export all events as CSV"
          >
            Export CSV
          </button>
        </div>

        <span style={{ fontSize: 9, color: "#333", letterSpacing: "0.1em" }}>
          {new Date().toLocaleTimeString(navigator.language || "en-US")}
        </span>
      </div>

      {/* ── Stat row ──────────────────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 1, background: "#111" }}>
        <StatBlock
          label="Blocked"
          value={stats.blocked}
          sub={`${stats.total ? ((stats.blocked / stats.total) * 100).toFixed(1) : 0}% block rate`}
          accent="#ff2d2d"
        />
        <StatBlock
          label="Alerted"
          value={stats.alerted}
          sub="requires review"
          accent="#ffaa00"
        />
        <StatBlock
          label="Avg Risk"
          value={(stats.avgRisk * 100).toFixed(1) + "%"}
          trend={stats.trend}
          accent="#00e676"
        />
        <StatBlock
          label="Avg Latency"
          value={stats.avgLat.toFixed(1) + "ms"}
          sub="classification time"
          accent="#4dabf7"
        />
        <StatBlock
          label="Events"
          value={stats.total}
          sub="this session"
          accent="#555"
        />
      </div>

      {/* ── Main grid ─────────────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 300px", gap: 1, background: "#111" }}>

        {/* Left — event stream */}
        <div style={{
          background: "#080808",
          display: "flex", flexDirection: "column",
        }}>
          {/* Stream toolbar */}
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "10px 16px",
            borderBottom: "1px solid #111",
            background: "#0a0a0a",
          }}>
            <span style={{ fontSize: 9, color: "#333", letterSpacing: "0.12em", marginRight: 4 }}>
              ACTION
            </span>
            {["all", "block", "alert", "allow"].map(f => (
              <button key={f} onClick={() => setFilterAction(f)}
                style={filterAction === f ? btnActive : btnBase}>
                {f}
              </button>
            ))}
            <div style={{ width: 1, height: 14, background: "#1e1e1e", margin: "0 4px" }} />
            <span style={{ fontSize: 9, color: "#333", letterSpacing: "0.12em" }}>GUARD</span>
            {["all", "prompt", "rag", "tool"].map(f => (
              <button key={f} onClick={() => setFilterGuard(f)}
                style={filterGuard === f ? btnActive : btnBase}>
                {f}
              </button>
            ))}
            <div style={{ flex: 1 }} />
            <span style={{ fontSize: 9, color: "#2a2a2a", fontFamily: "monospace" }}>
              {filtered.length} events
            </span>
          </div>

          {/* Column headers */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "72px 36px 70px 90px 1fr 130px",
            gap: 12, padding: "6px 16px",
            borderBottom: "1px solid #111",
            background: "#090909",
          }}>
            {["TIME", "GUARD", "CATEGORY", "SESSION", "MESSAGE", "RISK"].map(h => (
              <span key={h} style={{
                fontSize: 8, color: "#2a2a2a",
                textTransform: "uppercase", letterSpacing: "0.12em",
              }}>{h}</span>
            ))}
          </div>

          {/* Rows */}
          <div style={{ overflowY: "auto", flex: 1 }}>
            {filtered.slice(0, 100).map(event => (
              <div key={event.event_id} style={{ animation: "slideDown 0.2s ease" }}>
                <EventRow
                  event={event}
                  selected={selected?.event_id === event.event_id}
                  onClick={setSelected}
                />
              </div>
            ))}
            {filtered.length === 0 && (
              <div style={{
                padding: 40, textAlign: "center",
                color: "#222", fontSize: 10, fontFamily: "monospace",
              }}>
                NO EVENTS MATCH FILTER
              </div>
            )}
          </div>
        </div>

        {/* Right panel */}
        <div style={{
          background: "#080808",
          display: "flex", flexDirection: "column", gap: 1,
        }}>

          {/* Tab bar */}
          <div style={{
            display: "flex", borderBottom: "1px solid #111",
            background: "#0a0a0a",
          }}>
            {[["stream", "DETAIL"], ["sessions", "SESSIONS"], ["breakdown", "THREATS"]].map(([t, l]) => (
              <button key={t} onClick={() => setActiveTab(t)} style={{
                ...btnBase,
                flex: 1, border: "none", borderBottom: `2px solid ${activeTab === t ? "#00e676" : "transparent"}`,
                borderRadius: 0, padding: "10px 0",
                color: activeTab === t ? "#00e676" : "#333",
                background: "none",
              }}>{l}</button>
            ))}
          </div>

          <div style={{ flex: 1, padding: 16, overflowY: "auto" }}>
            {activeTab === "stream" && (
              <EventDetail event={selected} onClose={() => setSelected(null)} />
            )}
            {activeTab === "sessions" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <span style={{ fontSize: 9, color: "#333", letterSpacing: "0.12em" }}>
                  ACTIVE SESSIONS
                </span>
                <SessionsPanel events={events} />
              </div>
            )}
            {activeTab === "breakdown" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div>
                  <span style={{ fontSize: 9, color: "#333", letterSpacing: "0.12em", display: "block", marginBottom: 12 }}>
                    ATTACK CATEGORIES
                  </span>
                  <CategoryBreakdown byCategory={stats.byCategory} />
                </div>
                <div style={{ height: 1, background: "#111" }} />
                <div>
                  <span style={{ fontSize: 9, color: "#333", letterSpacing: "0.12em", display: "block", marginBottom: 12 }}>
                    BY GUARD TYPE
                  </span>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {Object.entries(stats.byGuard).map(([g, c]) => (
                      <div key={g} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <GuardIcon type={g} />
                        <span style={{ fontSize: 9, color: "#555", textTransform: "uppercase", letterSpacing: "0.08em" }}>{g}</span>
                        <span style={{ fontFamily: "monospace", fontSize: 11, color: "#888" }}>{c}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Footer ────────────────────────────────────────────────────────── */}
      <div style={{
        height: 28, borderTop: "1px solid #111",
        background: "#060606",
        display: "flex", alignItems: "center",
        padding: "0 16px", gap: 20,
        fontSize: 8, color: "#2a2a2a",
        letterSpacing: "0.1em",
      }}>
        <span>ANZEN v0.1.0</span>
        <span>·</span>
        <span>APACHE 2.0 · OPEN SOURCE · SELF-HOSTED</span>
        <span>·</span>
        <span>LAYER 1: REGEX · LAYER 2: MINILM · &lt;20MS</span>
        <div style={{ flex: 1 }} />
        <span style={{ color: "#1a1a1a" }}>
          YOUR AI STACK. YOUR DATA. YOUR RULES.
        </span>
      </div>
    </div>
  );
}
