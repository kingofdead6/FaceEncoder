/** Browser-camera capture and duplex processed-video stream. */
import { useEffect, useRef, useState } from "react";
import { streamUrl } from "../api/client";

export function useStream(enabled, onStats) {
  const videoRef = useRef(null);
  const imgRef = useRef(null);
  const onStatsRef = useRef(onStats);
  onStatsRef.current = onStats;
  const [wsState, setWsState] = useState("idle");

  useEffect(() => {
    if (!enabled) {
      setWsState("idle");
      return undefined;
    }

    let alive = true;
    let ws = null;
    let retryTimer = null;
    let captureTimer = null;
    let mediaStream = null;
    let lastUrl = null;
    let sending = false;
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d", { alpha: false });

    const scheduleFrame = () => {
      clearTimeout(captureTimer);
      captureTimer = setTimeout(sendFrame, 33);
    };

    const sendFrame = () => {
      const video = videoRef.current;
      if (!alive || sending || !video || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || !ws || ws.readyState !== WebSocket.OPEN) {
        if (alive && ws?.readyState === WebSocket.OPEN) scheduleFrame();
        return;
      }
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      if (!canvas.width || !canvas.height) {
        scheduleFrame();
        return;
      }
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      sending = true;
      canvas.toBlob((blob) => {
        if (!alive || !blob || !ws || ws.readyState !== WebSocket.OPEN) {
          sending = false;
          if (alive) scheduleFrame();
          return;
        }
        ws.send(blob);
      }, "image/jpeg", 0.8);
    };

    const connect = () => {
      if (!alive) return;
      setWsState("connecting");
      ws = new WebSocket(streamUrl());
      ws.binaryType = "blob";
      ws.onopen = () => {
        if (!alive) return;
        setWsState("open");
        scheduleFrame();
      };
      ws.onmessage = (event) => {
        if (!alive) return;
        if (typeof event.data === "string") {
          try {
            const message = JSON.parse(event.data);
            if (message.type === "stats") onStatsRef.current?.(message);
            if (message.type === "error") {
              sending = false;
              setWsState("error");
              captureTimer = setTimeout(sendFrame, 1000);
            }
          } catch {
            // Ignore malformed control messages.
          }
          return;
        }
        const url = URL.createObjectURL(event.data);
        const previous = lastUrl;
        lastUrl = url;
        if (imgRef.current) imgRef.current.src = url;
        else URL.revokeObjectURL(url);
        if (previous) setTimeout(() => URL.revokeObjectURL(previous), 300);
        sending = false;
        setWsState("open");
        scheduleFrame();
      };
      ws.onerror = () => ws?.close();
      ws.onclose = () => {
        sending = false;
        if (alive) {
          setWsState("closed");
          retryTimer = setTimeout(connect, 1200);
        }
      };
    };

    const start = async () => {
      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
          audio: false,
        });
        if (!alive) {
          mediaStream.getTracks().forEach((track) => track.stop());
          return;
        }
        const video = videoRef.current;
        if (!video) throw new Error("Camera preview is unavailable.");
        video.srcObject = mediaStream;
        await video.play();
        connect();
      } catch {
        if (alive) setWsState("camera-error");
      }
    };

    start();
    return () => {
      alive = false;
      clearTimeout(retryTimer);
      clearTimeout(captureTimer);
      try { ws?.close(); } catch { /* already closed */ }
      mediaStream?.getTracks().forEach((track) => track.stop());
      if (videoRef.current) videoRef.current.srcObject = null;
      if (lastUrl) URL.revokeObjectURL(lastUrl);
    };
  }, [enabled]);

  return { videoRef, imgRef, wsState };
}
