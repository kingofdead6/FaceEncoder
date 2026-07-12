/** Human-readable reference for the browser-capture API. */
import { FiExternalLink } from "react-icons/fi";

const ENDPOINTS = [
  { method: "GET", path: "/api/health", desc: "Liveness probe and active browser-stream count." },
  { method: "GET", path: "/api/settings", desc: "Current privacy-processing settings." },
  { method: "PUT", path: "/api/settings", desc: "Partially update privacy-processing settings." },
  { method: "GET", path: "/api/settings/blur-types", desc: "The supported blur-algorithm catalogue." },
  { method: "GET", path: "/api/stats", desc: "Latest processing FPS, latency, detections, and frames." },
  { method: "WS", path: "/ws/stream", desc: "Send browser JPEG frames; receive processed JPEG frames and stats." },
];

const METHOD_CLS = {
  GET: "text-signal border-signal/40",
  PUT: "text-warn border-warn/40",
  WS: "text-ok border-ok/40",
};

export default function ApiDocs() {
  return (
    <div className="fade-in mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <h1 className="font-display text-2xl font-semibold tracking-tight">API reference</h1>
      <p className="mt-2 max-w-2xl text-sm text-muted">
        The browser owns camera permission and capture. The backend only receives frames for
        privacy processing and returns the processed result.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        <a className="btn-ghost text-xs" href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
          Open Swagger UI <FiExternalLink aria-hidden="true" />
        </a>
      </div>

      <div className="panel mt-6 overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-edge bg-panel2 font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
              <th className="px-4 py-3">Method</th>
              <th className="px-4 py-3">Path</th>
              <th className="px-4 py-3">Description</th>
            </tr>
          </thead>
          <tbody>
            {ENDPOINTS.map((endpoint) => (
              <tr key={`${endpoint.method}-${endpoint.path}`} className="border-b border-edge last:border-0">
                <td className="px-4 py-3"><span className={`chip ${METHOD_CLS[endpoint.method]}`}>{endpoint.method}</span></td>
                <td className="px-4 py-3 font-mono text-xs text-signal">{endpoint.path}</td>
                <td className="px-4 py-3 text-muted">{endpoint.desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel mt-6 p-5">
        <h2 className="font-display text-base font-semibold">WebSocket protocol</h2>
        <p className="mt-2 text-sm text-muted">
          Send one binary JPEG frame. The server responds with one binary processed JPEG, followed
          by a text message such as <code className="font-mono text-xs">{'{"type":"stats","fps":30}'}</code>.
        </p>
      </div>
    </div>
  );
}
