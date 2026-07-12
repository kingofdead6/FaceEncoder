/**
 * useStream — low-latency WebSocket video consumer.
 *
 * Performance model: the hook never calls setState per frame. Each binary
 * JPEG becomes an object URL written straight onto an <img> DOM node through
 * a ref, so React re-renders zero times at 30–60 FPS. Interleaved JSON text
 * messages carry stats and are forwarded to a callback (kept in a ref so a
 * changing callback identity never tears the socket down).
 *
 * Old object URLs are revoked on a short delay — revoking immediately can
 * abort a frame that is still decoding.
 */
import { useEffect, useRef, useState } from "react";
import { streamUrl } from "../api/client";

export function useStream(enabled, onStats) {
  const imgRef = useRef(null);
  const onStatsRef = useRef(onStats);
  onStatsRef.current = onStats;

  // idle | connecting | open | closed
  const [wsState, setWsState] = useState("idle");

  useEffect(() => {
    if (!enabled) {
      setWsState("idle");
      return undefined;
    }

    let ws = null;
    let alive = true;
    let retryTimer = null;
    let lastUrl = null;

    const connect = () => {
      if (!alive) return;
      setWsState("connecting");
      ws = new WebSocket(streamUrl());
      ws.binaryType = "blob";

      ws.onopen = () => alive && setWsState("open");

      ws.onmessage = (e) => {
        if (!alive) return;

        // Text frame → stats / status JSON.
        if (typeof e.data === "string") {
          try {
            const msg = JSON.parse(e.data);
            if (msg.type === "stats") onStatsRef.current?.(msg);
          } catch {
            /* malformed message — ignore */
          }
          return;
        }

        // Binary frame → one JPEG image.
        const url = URL.createObjectURL(e.data);
        const img = imgRef.current;
        if (!img) {
          URL.revokeObjectURL(url);
          return;
        }
        const prev = lastUrl;
        lastUrl = url;
        img.src = url;
        if (prev) setTimeout(() => URL.revokeObjectURL(prev), 300);
      };

      ws.onerror = () => {
        try {
          ws.close();
        } catch {
          /* already closing */
        }
      };

      ws.onclose = () => {
        if (alive) {
          setWsState("closed");
          retryTimer = setTimeout(connect, 1200); // auto-reconnect
        }
      };
    };

    connect();

    return () => {
      alive = false;
      clearTimeout(retryTimer);
      try {
        if (ws) {
          ws.onclose = null;
          ws.close();
        }
      } catch {
        /* noop */
      }
      if (lastUrl) URL.revokeObjectURL(lastUrl);
    };
  }, [enabled]);

  return { imgRef, wsState };
}
