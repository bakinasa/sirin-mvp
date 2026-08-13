import { PipelineStep } from "./api";

export const STEP_ROUTES: Record<string, string> = {
  brief: "brief",
  profession_map: "profession-map",
  scenario_plan: "scenario",
  export: "exports",
  draft_tz: "profession-map",
  expert_feedback: "profession-map",
  expert_synthesis: "profession-map",
  final_tz: "profession-map",
  scene_breakdown: "scenario",
  production_planning: "scenario",
  storyboard: "scenario",
};

export const VISIBLE_STEPS = new Set(["brief", "profession_map", "scenario_plan", "export"]);

/**
 * TEMP: allow navigation to future steps while we temporarily bypass step locking.
 * Вернуть в `true`, чтобы снова включить блокировку переходов после Approve.
 */
export const STEP_ACCESS_LOCK_ENABLED = false;

export function visiblePipeline(steps: PipelineStep[]): PipelineStep[] {
  return [...steps]
    .filter((s) => VISIBLE_STEPS.has(s.step_type))
    .sort((a, b) => a.order_index - b.order_index);
}

/** First step that is not yet approved/locked = current working step. */
export function getCurrentStepIndex(steps: PipelineStep[]): number {
  const sorted = visiblePipeline(steps);
  const idx = sorted.findIndex(
    (s) => s.status !== "approved" && s.status !== "locked"
  );
  return idx === -1 ? Math.max(0, sorted.length - 1) : idx;
}

/** Past steps + current are open; future steps are locked. */
export function isStepAccessible(steps: PipelineStep[], stepType: string): boolean {
  if (!STEP_ACCESS_LOCK_ENABLED) return true;
  const sorted = visiblePipeline(steps);
  const current = getCurrentStepIndex(steps);
  const idx = sorted.findIndex((s) => s.step_type === stepType);
  if (idx < 0) return false;
  return idx <= current;
}

export function stepPath(projectId: string, stepType: string): string {
  const route = STEP_ROUTES[stepType] || "overview";
  return `/projects/${projectId}/${route}`;
}
