/** ApiDocs — human-readable endpoint reference mirroring docs/API.md. */
import { FiExternalLink } from "react-icons/fi";

const ENDPOINTS = [
  { method: "GET", path: "/api/health", desc: "Liveness probe: app name, version, camera state." },
  { method: "GET", path: "/api/camera/status", desc: "Camera lifecycle status (running, index, resolution, uptime)." },
  { method: "POST", path: "/api/camera/start", desc: "Open the webcam and start processing. Body: { camera_index? }." },
  { method: "POST", path: "/api/camera/stop", desc: "Stop processing and release the device. Idempotent." },
  { method: "GET", path: "/api/settings", desc: "Current pipeline settings (mode, blur, strength, region, toggles)." },
  { method: "PUT", path: "/api/settings", desc: "Partial settings update — send only the fields you change." },
  { method: "GET", path: "/api/settings/blur-types", desc: "Catalogue of the nine blur algorithms with labels." },
  { method: "GET", path: "/api/stats", desc: "Live statistics: FPS, latency, detections, frames, uptime." },
  { method: "GET", path: "/api/stream/snapshot", desc: "One current processed frame as image/jpeg (204 when idle)." },
  { method: "GET", path: "/api/stream/mjpeg", desc: "MJPEG fallback stream — plays inside a plain <img> tag." },
  { method: "WS", path: "/ws/stream", desc: "Primary stream: binary JPEG frames + JSON stats messages." },
];

const METHOD_CLS = {
  GET: "text-signal border-signal/40",
  POST: "text-iris border-iris/40",
  PUT: "text-warn border-warn/40",
  WS: "text-ok border-ok/40",
};

export default function ApiDocs() {
  return (
    <div className="fade-in mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <h1 className="font-display text-2xl font-semibold tracking-tight">API reference</h1>
      <p className="mt-2 max-w-2xl text-sm text-muted">
        Everything the interface does goes through these endpoints, so anything you can click
        here you can also script. Interactive Swagger docs are served by the backend itself.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        <a
          className="btn-ghost text-xs"
          href="http://localhost:8000/docs"
          target="_blank"
          rel="noreferrer"
        >
          Open Swagger UI <FiExternalLink aria-hidden="true" />
        </a>
        <a
          className="btn-ghost text-xs"
          href="http://localhost:8000/api/health"
          target="_blank"
          rel="noreferrer"
        >
          Try /api/health <FiExternalLink aria-hidden="true" />
        </a>
      </div>

      <div className="panel mt-6 overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-edge bg-panel2 font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
              <th className="px-4 py-3">Method</th>
              <th className="px-4 py-3">Path</th>
              <th className="hidden px-4 py-3 sm:table-cell">Description</th>
            </tr>
          </thead>
          <tbody>
            {ENDPOINTS.map((e) => (
              <tr key={e.method + e.path} className="border-b border-edge/60 last:border-0">
                <td className="px-4 py-3">
                  <span className={`chip ${METHOD_CLS[e.method]}`}>{e.method}</span>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-ink">{e.path}</td>
                <td className="hidden px-4 py-3 text-muted sm:table-cell">{e.desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel mt-6 p-5">
        <h2 className="font-display text-base font-semibold">WebSocket protocol</h2>
        <p className="mt-2 text-sm text-muted">
          Connect to <code className="font-mono text-signal">/ws/stream</code>. The server pushes
          two message kinds — check the frame type on arrival:
        </p>
        <ul className="mt-3 space-y-2 text-sm text-muted">
          <li>
            <span className="chip mr-2 text-signal border-signal/40">binary</span>
            one complete JPEG-encoded video frame — decode straight into an image.
          </li>
          <li>
            <span className="chip mr-2 text-ok border-ok/40">text</span>
            JSON: <code className="font-mono text-xs">{'{"type":"stats", fps, latency_ms, …}'}</code>{" "}
            roughly twice a second, or{" "}
            <code className="font-mono text-xs">{'{"type":"status","running":false}'}</code> while idle.
          </li>
        </ul>
      </div>
    </div>
  );
}
