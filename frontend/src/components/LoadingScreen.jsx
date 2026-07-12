/** Full-screen boot splash: spinning iris ring around the aperture mark. */
export default function LoadingScreen() {
  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-5 bg-surface">
      <div className="relative h-20 w-20" aria-hidden="true">
        <svg viewBox="0 0 80 80" className="absolute inset-0">
          <circle cx="40" cy="40" r="14" fill="#8B5CF6" />
          <circle cx="40" cy="40" r="26" fill="none" stroke="#22D3EE" strokeWidth="3" opacity="0.35" />
        </svg>
        <svg viewBox="0 0 80 80" className="iris-ring absolute inset-0">
          <circle
            cx="40"
            cy="40"
            r="34"
            fill="none"
            stroke="#22D3EE"
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray="42 172"
          />
        </svg>
      </div>
      <div className="text-center">
        <p className="font-display text-xl font-semibold tracking-tight">
          Vision<span className="text-signal">Shield</span>
        </p>
        <p className="mt-1 text-sm text-muted" role="status">
          Warming up the control room…
        </p>
      </div>
    </div>
  );
}
