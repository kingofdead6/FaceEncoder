/**
 * Global application state.
 *
 * One provider owns everything the UI needs: pipeline settings, camera
 * status, live stats, theme, and toast notifications. Settings updates are
 * optimistic — the UI flips instantly and rolls back with a toast if the
 * backend rejects the change.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { api, errorMessage } from "../api/client";

const AppContext = createContext(null);
let toastSeq = 0;

export function AppProvider({ children }) {
  const [booted, setBooted] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem("vs-theme") || "dark");
  const [backendUp, setBackendUp] = useState(true);
  const [busy, setBusy] = useState(false);

  const [status, setStatus] = useState({
    running: false,
    camera_index: null,
    capture_resolution: "browser",
    uptime_s: 0,
    error: null,
  });
  const [settings, setSettings] = useState({
    mode: "face",
    blur_type: "gaussian",
    strength: 55,
    region: "outside",
    show_detections: false,
    mirror: true,
  });
  const [blurTypes, setBlurTypes] = useState([]);
  const [stats, setStats] = useState(null);
  const [fpsHistory, setFpsHistory] = useState([]);
  const [toasts, setToasts] = useState([]);
  const lastCamError = useRef(null);

  /* ---------------- theme ---------------- */
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("vs-theme", theme);
  }, [theme]);

  /* ---------------- toasts ---------------- */
  const pushToast = useCallback((variant, message) => {
    const id = ++toastSeq;
    setToasts((t) => [...t.slice(-3), { id, variant, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);
  const dismissToast = useCallback(
    (id) => setToasts((t) => t.filter((x) => x.id !== id)),
    []
  );

  /* ---------------- stats ingestion (WS + polling share this) ---------------- */
  const ingestStats = useCallback((s) => {
    setStats(s);
    if (typeof s?.fps === "number") {
      setFpsHistory((h) => [...h.slice(-59), s.fps]);
    }
  }, []);

  /* ---------------- boot: load everything in parallel ---------------- */
  useEffect(() => {
    let alive = true;
    const t0 = Date.now();
    (async () => {
      try {
        const [se, bt] = await Promise.all([api.getSettings(), api.blurTypes()]);
        if (!alive) return;
        setSettings(se);
        setBlurTypes(bt);
        setBackendUp(true);
      } catch {
        if (!alive) return;
        setBackendUp(false);
        pushToast(
          "error",
          "Cannot reach the backend at /api. Start it with: uvicorn app.main:app"
        );
      } finally {
        // Keep the loading screen up just long enough to feel intentional.
        const wait = Math.max(0, 700 - (Date.now() - t0));
        setTimeout(() => alive && setBooted(true), wait);
      }
    })();
    return () => {
      alive = false;
    };
  }, [pushToast]);

  /* ---------------- background health probe ---------------- */
  useEffect(() => {
    const t = setInterval(async () => {
      try {
        await api.health();
        setBackendUp(true);
      } catch {
        setBackendUp(false);
      }
    }, 8000);
    return () => clearInterval(t);
  }, []);

  /* ---------------- status/stats fallback poll while running ---------------- */
  useEffect(() => {
    if (!status.running) return undefined;
    const t = setInterval(async () => {
      try {
        const s = await api.stats();
        ingestStats(s);
        if (st.error && st.error !== lastCamError.current) {
          lastCamError.current = st.error;
          pushToast("error", st.error);
        }
      } catch {
        /* transient — the health probe owns connectivity state */
      }
    }, 3000);
    return () => clearInterval(t);
  }, [status.running, ingestStats, pushToast]);

  /* ---------------- actions ---------------- */
  const startCamera = useCallback(async () => {
    setBusy(true);
    try {
      setStatus((current) => ({ ...current, running: true, error: null }));
      lastCamError.current = null;
      pushToast("info", "Requesting browser camera access");
    } catch (e) {
      pushToast("error", errorMessage(e));
    } finally {
      setBusy(false);
    }
  }, [pushToast]);

  const stopCamera = useCallback(async () => {
    setBusy(true);
    try {
      setStatus((current) => ({ ...current, running: false, uptime_s: 0, error: null }));
      setStats(null);
      setFpsHistory([]);
      pushToast("info", "Camera stopped");
    } catch (e) {
      pushToast("error", errorMessage(e));
    } finally {
      setBusy(false);
    }
  }, [pushToast]);

  const updateSettings = useCallback(
    async (partial) => {
      const prev = settings;
      setSettings((s) => ({ ...s, ...partial })); // optimistic
      try {
        const se = await api.updateSettings(partial);
        setSettings(se);
      } catch (e) {
        setSettings(prev); // rollback
        pushToast("error", errorMessage(e));
      }
    },
    [settings, pushToast]
  );

  const value = useMemo(
    () => ({
      booted,
      theme,
      setTheme,
      backendUp,
      busy,
      status,
      settings,
      blurTypes,
      stats,
      fpsHistory,
      toasts,
      pushToast,
      dismissToast,
      ingestStats,
      startCamera,
      stopCamera,
      updateSettings,
    }),
    [
      booted,
      theme,
      backendUp,
      busy,
      status,
      settings,
      blurTypes,
      stats,
      fpsHistory,
      toasts,
      pushToast,
      dismissToast,
      ingestStats,
      startCamera,
      stopCamera,
      updateSettings,
    ]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

/** Hook: access the app store from any component. */
export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <AppProvider>");
  return ctx;
}
