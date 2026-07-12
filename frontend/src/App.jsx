/** Root component: routing shell, splash gate, global toasts. */
import { Route, Routes } from "react-router-dom";
import Navbar from "./components/Navbar";
import Toasts from "./components/Toasts";
import LoadingScreen from "./components/LoadingScreen";
import Dashboard from "./pages/Dashboard";
import ApiDocs from "./pages/ApiDocs";
import { useApp } from "./context/AppContext";

export default function App() {
  const { booted } = useApp();

  if (!booted) return <LoadingScreen />;

  return (
    <div className="flex min-h-screen flex-col">
      <Navbar />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/api-docs" element={<ApiDocs />} />
        </Routes>
      </main>
      <footer className="border-t border-edge px-4 py-4 text-center font-mono text-[11px] text-muted">
        VisionShield v1.0 — real-time privacy pipeline · FastAPI + MediaPipe + OpenCV + React
      </footer>
      <Toasts />
    </div>
  );
}
