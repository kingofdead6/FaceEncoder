/** 3-column grid of the nine blur algorithms served by the backend catalogue. */
import { useApp } from "../context/AppContext";

export default function BlurSelector() {
  const { blurTypes, settings, updateSettings } = useApp();

  if (!blurTypes.length) {
    return <p className="text-xs text-muted">Loading blur catalogue…</p>;
  }

  return (
    <div className="grid grid-cols-3 gap-2" role="group" aria-label="Blur algorithm">
      {blurTypes.map((b) => (
        <button
          key={b.id}
          type="button"
          title={b.desc}
          onClick={() => updateSettings({ blur_type: b.id })}
          className={`seg px-2 py-2 text-center text-xs font-medium ${
            settings.blur_type === b.id ? "seg-active" : ""
          }`}
          aria-pressed={settings.blur_type === b.id}
        >
          {b.label}
        </button>
      ))}
    </div>
  );
}
