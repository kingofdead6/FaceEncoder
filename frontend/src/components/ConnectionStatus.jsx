/** Small live indicator of backend reachability (fed by the health probe). */
import { useApp } from "../context/AppContext";

export default function ConnectionStatus() {
  const { backendUp } = useApp();
  return (
    <span
      className={`chip ${backendUp ? "text-ok border-ok/30" : "text-danger border-danger/40"}`}
      role="status"
      aria-live="polite"
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${backendUp ? "bg-ok" : "bg-danger"}`}
        aria-hidden="true"
      />
      {backendUp ? "Backend online" : "Backend offline"}
    </span>
  );
}
