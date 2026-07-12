/**
 * VideoViewer — the signature element of the interface.
 *
 * A viewfinder-styled viewport: corner brackets, a LIVE pulse, an FPS chip,
 * and a slow scan shimmer while streaming. The <img> element receives frames
 * directly from useStream via a ref, so streaming never re-renders React.
 */
import { FiCameraOff, FiLoader, FiWifiOff } from "react-icons/fi";
import { useApp } from "../context/AppContext";
import { useStream } from "../hooks/useStream";

function Corners() {
  return (
    <>
      <span className="viewfinder-corner left-2 top-2 rounded-tl-md border-l-2 border-t-2" />
      <span className="viewfinder-corner right-2 top-2 rounded-tr-md border-r-2 border-t-2" />
      <span className="viewfinder-corner bottom-2 left-2 rounded-bl-md border-b-2 border-l-2" />
      <span className="viewfinder-corner bottom-2 right-2 rounded-br-md border-b-2 border-r-2" />
    </>
  );
}

export default function VideoViewer() {
  const { status, stats, settings, backendUp, ingestStats } = useApp();
  const { videoRef, imgRef, wsState } = useStream(status.running, ingestStats);

  const live = status.running && wsState === "open";

  return (
    <section className="panel relative overflow-hidden" aria-label="Live video">
      <div className="relative aspect-video w-full bg-[#05070d]">
        {/* Stream target — always mounted while running so the ref exists
            before the first frame arrives. */}
        {status.running && <video ref={videoRef} muted playsInline className="hidden" aria-hidden="true" />}
        {status.running && (
          <img
            ref={imgRef}
            src="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="
            alt="Processed live stream"
            className="absolute inset-0 h-full w-full object-contain"
            draggable="false"
          />
        )}

        {/* Idle / connecting states */}
        {!status.running && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-center">
            {backendUp ? (
              <>
                <FiCameraOff className="text-4xl text-muted" aria-hidden="true" />
                <p className="font-display text-lg text-ink">Camera is off</p>
                <p className="max-w-xs text-sm text-muted">
                  Press <span className="text-signal">Start camera</span> to open the live
                  privacy-processed stream.
                </p>
              </>
            ) : (
              <>
                <FiWifiOff className="text-4xl text-danger" aria-hidden="true" />
                <p className="font-display text-lg text-ink">Backend offline</p>
                <p className="max-w-xs text-sm text-muted">
                  Start the API with <code className="font-mono text-signal">uvicorn app.main:app</code>{" "}
                  then this panel reconnects automatically.
                </p>
              </>
            )}
          </div>
        )}
        {status.running && wsState !== "open" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
            <FiLoader className="iris-ring text-3xl text-signal" aria-hidden="true" />
            <p className="text-sm text-muted">
              {wsState === "closed" ? "Stream dropped — reconnecting…" : "Connecting to stream…"}
            </p>
          </div>
        )}

        {/* Viewfinder chrome */}
        <Corners />
        {live && <div className="scanline" aria-hidden="true" />}

        {/* Top overlays */}
        <div className="absolute left-3 top-3 flex items-center gap-2">
          <span
            className={`chip ${live ? "border-danger/40 text-danger" : "text-muted"}`}
            aria-live="polite"
          >
            <span
              className={`h-2 w-2 rounded-full ${live ? "pulse-dot bg-danger" : "bg-edge"}`}
              aria-hidden="true"
            />
            {live ? "LIVE" : "STANDBY"}
          </span>
        </div>
        <div className="absolute right-3 top-3 flex items-center gap-2">
          {live && (
            <span className="chip text-signal border-signal/30">
              {Math.round(stats?.fps ?? 0)} FPS
            </span>
          )}
        </div>

        {/* Bottom overlays */}
        {live && (
          <div className="absolute bottom-3 left-3 right-3 flex flex-wrap items-center gap-2">
            <span className="chip capitalize">{settings.mode} mode</span>
            <span className="chip capitalize">{settings.blur_type}</span>
            <span className="chip">{settings.region === "outside" ? "Blur outside" : "Blur inside"}</span>
            <span className="chip ml-auto">{stats?.latency_ms ?? 0} ms</span>
          </div>
        )}
      </div>
    </section>
  );
}
