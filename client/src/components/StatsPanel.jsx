/**
 * StatsPanel — live pipeline telemetry.
 *
 * Tiles for the headline numbers, a custom SVG sparkline of recent FPS
 * (no chart library needed), and context chips (resolution, uptime, engine).
 */
import { FiActivity, FiClock, FiCpu, FiUsers } from "react-icons/fi";
import { useApp } from "../context/AppContext";

function Sparkline({ values, height = 36 }) {
  if (!values.length) {
    return <div className="h-9 w-full rounded-lg bg-panel2" aria-hidden="true" />;
  }
  const max = Math.max(30, ...values);
  const points = values
    .map((v, i) => {
      const x = values.length > 1 ? (i / (values.length - 1)) * 100 : 0;
      const y = height - 2 - (v / max) * (height - 6);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  return (
    <svg
      viewBox={`0 0 100 ${height}`}
      preserveAspectRatio="none"
      className="h-9 w-full"
      role="img"
      aria-label="FPS over the last minute"
    >
      <defs>
        <linearGradient id="sparkStroke" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#22d3ee" />
          <stop offset="1" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>
      <polyline
        points={points}
        fill="none"
        stroke="url(#sparkStroke)"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function Tile({ label, value, suffix }) {
  return (
    <div className="rounded-xl border border-edge bg-panel2 p-3">
      <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">{label}</p>
      <p className="mt-1 font-display text-2xl font-semibold text-ink">
        {value}
        {suffix && <span className="ml-1 text-sm font-normal text-muted">{suffix}</span>}
      </p>
    </div>
  );
}

function formatUptime(seconds = 0) {
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}:${String(sec).padStart(2, "0")}`;
}

export default function StatsPanel() {
  const { stats, fpsHistory, status } = useApp();
  const s = stats ?? {};

  return (
    <section className="panel p-5" aria-label="Statistics">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-display text-base font-semibold">Pipeline statistics</h2>
        <span className="chip">
          <FiActivity aria-hidden="true" />
          {status.running ? "processing" : "idle"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Tile label="Processing" value={Math.round(s.fps ?? 0)} suffix="fps" />
        <Tile label="Latency" value={s.latency_ms ?? 0} suffix="ms" />
        <Tile label="Detections" value={s.detections ?? 0} />
        <Tile label="Frames" value={(s.frames_total ?? 0).toLocaleString()} />
      </div>

      <div className="mt-4">
        <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
          FPS · last 60 samples
        </p>
        <Sparkline values={fpsHistory} />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <span className="chip">
          <FiClock aria-hidden="true" /> {formatUptime(s.uptime_s)}
        </span>
        {s.resolution && <span className="chip">{s.resolution}</span>}
        <span className="chip">
          <FiCpu aria-hidden="true" /> {s.cuda ? "CUDA" : "CPU"}
        </span>
        <span className="chip">
          <FiUsers aria-hidden="true" /> {s.ws_clients ?? 0} viewer{(s.ws_clients ?? 0) === 1 ? "" : "s"}
        </span>
        {s.capture_fps != null && <span className="chip">capture {Math.round(s.capture_fps)} fps</span>}
      </div>
    </section>
  );
}
