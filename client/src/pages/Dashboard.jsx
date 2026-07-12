/** Dashboard — the control room: viewport + telemetry on the left, controls on the right. */
import ControlsPanel from "../components/ControlsPanel";
import StatsPanel from "../components/StatsPanel";
import VideoViewer from "../components/VideoViewer";

export default function Dashboard() {
  return (
    <div className="fade-in mx-auto grid max-w-7xl gap-5 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="flex min-w-0 flex-col gap-5">
        <VideoViewer />
        <StatsPanel />
      </div>
      <ControlsPanel />
    </div>
  );
}
