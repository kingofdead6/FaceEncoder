
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL || "https://faceencoder.onrender.com";

export const http = axios.create({
  baseURL: API_BASE,
  timeout: 10_000,
  headers: { "Content-Type": "application/json" },
});

/** Extract a human-readable message from any axios error. */
export function errorMessage(err) {
  return (
    err?.response?.data?.detail ||
    err?.message ||
    "Something went wrong while talking to the backend."
  );
}

/** Build the WebSocket URL for the live stream, honouring VITE_API_URL. */
export function streamUrl() {
  if (API_BASE) {
    return API_BASE.replace(/^http/, "ws").replace(/\/$/, "") + "/ws/stream";
  }
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws/stream`;
}

/* ------------------------------------------------------------------ *
 *  Endpoint helpers                                                  *
 * ------------------------------------------------------------------ */
export const api = {
  health: () => http.get("/api/health").then((r) => r.data),
  getSettings: () => http.get("/api/settings").then((r) => r.data),
  updateSettings: (partial) => http.put("/api/settings", partial).then((r) => r.data),
  blurTypes: () => http.get("/api/settings/blur-types").then((r) => r.data),
  stats: () => http.get("/api/stats").then((r) => r.data),
};
