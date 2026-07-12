/**
 * ControlsPanel — every user-tunable pipeline setting.
 *
 * Each control writes through the optimistic updateSettings action; the
 * strength slider debounces so dragging emits at most one request per 250 ms.
 */
import { useEffect, useRef, useState } from "react";
import { FiEye, FiPlay, FiRepeat, FiSquare } from "react-icons/fi";
import { BsPersonBoundingBox } from "react-icons/bs";
import { IoHandLeftOutline } from "react-icons/io5";
import { useApp } from "../context/AppContext";
import BlurSelector from "./BlurSelector";

function SectionLabel({ children }) {
  return (
    <p className="mb-2 font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">
      {children}
    </p>
  );
}

function Toggle({ label, icon: Icon, checked, onChange }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`seg flex w-full items-center justify-between ${checked ? "seg-active" : ""}`}
      aria-pressed={checked}
    >
      <span className="flex items-center gap-2">
        <Icon aria-hidden="true" />
        {label}
      </span>
      <span
        className={`relative h-4 w-7 rounded-full transition-colors ${
          checked ? "bg-signal" : "bg-edge"
        }`}
        aria-hidden="true"
      >
        <span
          className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${
            checked ? "left-3.5" : "left-0.5"
          }`}
        />
      </span>
    </button>
  );
}

const REGION_HINTS = {
  face: {
    outside: "Faces stay sharp — everything around them is blurred.",
    inside: "Faces themselves are blurred (classic anonymisation).",
  },
  hand: {
    outside: "The hand rectangle stays sharp — the rest is blurred.",
    inside: "Only the hand rectangle is blurred.",
  },
};

export default function ControlsPanel() {
  const { status, settings, busy, startCamera, stopCamera, updateSettings } = useApp();

  // Debounced strength slider: local value for instant feedback,
  // one PUT at most every 250 ms while dragging.
  const [strength, setStrength] = useState(settings.strength);
  const debounceRef = useRef(null);
  useEffect(() => setStrength(settings.strength), [settings.strength]);
  useEffect(() => () => clearTimeout(debounceRef.current), []);

  const onStrength = (value) => {
    setStrength(value);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => updateSettings({ strength: value }), 250);
  };

  return (
    <aside className="panel flex flex-col gap-6 p-5" aria-label="Controls">
      {/* Camera lifecycle */}
      <div>
        <SectionLabel>Camera</SectionLabel>
        {status.running ? (
          <button type="button" className="btn-danger w-full" onClick={stopCamera} disabled={busy}>
            <FiSquare aria-hidden="true" /> Stop camera
          </button>
        ) : (
          <button type="button" className="btn-primary w-full" onClick={startCamera} disabled={busy}>
            <FiPlay aria-hidden="true" /> Start camera
          </button>
        )}
      </div>

      {/* Mode */}
      <div>
        <SectionLabel>Mode</SectionLabel>
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => updateSettings({ mode: "face" })}
            className={`seg flex flex-col items-start gap-1 p-3 text-left ${
              settings.mode === "face" ? "seg-active" : ""
            }`}
            aria-pressed={settings.mode === "face"}
          >
            <BsPersonBoundingBox className="text-lg" aria-hidden="true" />
            <span className="font-semibold text-ink">Face privacy</span>
            <span className="text-xs leading-snug">Faces sharp, background blurred.</span>
          </button>
          <button
            type="button"
            onClick={() => updateSettings({ mode: "hand" })}
            className={`seg flex flex-col items-start gap-1 p-3 text-left ${
              settings.mode === "hand" ? "seg-active" : ""
            }`}
            aria-pressed={settings.mode === "hand"}
          >
            <IoHandLeftOutline className="text-lg" aria-hidden="true" />
            <span className="font-semibold text-ink">Hand privacy</span>
            <span className="text-xs leading-snug">Rectangle around both hands.</span>
          </button>
        </div>
      </div>

      {/* Region */}
      <div>
        <SectionLabel>Blur region</SectionLabel>
        <div className="grid grid-cols-2 gap-2" role="group" aria-label="Blur region">
          <button
            type="button"
            onClick={() => updateSettings({ region: "outside" })}
            className={`seg ${settings.region === "outside" ? "seg-active" : ""}`}
            aria-pressed={settings.region === "outside"}
          >
            Blur outside
          </button>
          <button
            type="button"
            onClick={() => updateSettings({ region: "inside" })}
            className={`seg ${settings.region === "inside" ? "seg-active" : ""}`}
            aria-pressed={settings.region === "inside"}
          >
            Blur inside
          </button>
        </div>
        <p className="mt-2 text-xs text-muted">{REGION_HINTS[settings.mode][settings.region]}</p>
      </div>

      {/* Blur algorithm */}
      <div>
        <SectionLabel>Blur algorithm</SectionLabel>
        <BlurSelector />
      </div>

      {/* Strength */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <SectionLabel>Blur strength</SectionLabel>
          <span className="chip text-signal border-signal/30">{strength}</span>
        </div>
        <input
          type="range"
          min="1"
          max="100"
          value={strength}
          onChange={(e) => onStrength(Number(e.target.value))}
          className="vs-range"
          style={{ backgroundSize: `${strength}% 100%` }}
          aria-label="Blur strength"
        />
        <div className="mt-1 flex justify-between font-mono text-[10px] text-muted">
          <span>subtle</span>
          <span>maximum</span>
        </div>
      </div>

      {/* Toggles */}
      <div className="flex flex-col gap-2">
        <SectionLabel>Overlay</SectionLabel>
        <Toggle
          label="Show detections"
          icon={FiEye}
          checked={settings.show_detections}
          onChange={(v) => updateSettings({ show_detections: v })}
        />
        <Toggle
          label="Mirror image"
          icon={FiRepeat}
          checked={settings.mirror}
          onChange={(v) => updateSettings({ mirror: v })}
        />
      </div>
    </aside>
  );
}
