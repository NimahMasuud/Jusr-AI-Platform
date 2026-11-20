import { apiRequest } from "./apiClient";

export interface DemoClockState {
  active: boolean;
  offsetMinutes: number;
  now: string;
  banner: string | null;
}

export function getDemoClock() {
  return apiRequest<DemoClockState>("/api/demo/clock");
}

export function advanceDemoClock(minutes: number) {
  return apiRequest<DemoClockState & { jobs: Record<string, unknown> }>(
    "/api/demo/clock/advance",
    { method: "POST", body: JSON.stringify({ minutes }) }
  );
}

export function resetDemoClock() {
  return apiRequest<DemoClockState>("/api/demo/clock/reset", {
    method: "POST",
  });
}
