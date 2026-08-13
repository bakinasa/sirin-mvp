/** Shared enums — keep in sync with apps/api/app/domain/enums.py */

export const StepStatus = {
  DRAFT: "draft",
  AI_GENERATED: "ai_generated",
  UNDER_REVIEW: "under_review",
  NEEDS_REVISION: "needs_revision",
  APPROVED: "approved",
  LOCKED: "locked",
  OUTDATED: "outdated",
} as const;

export const StepType = {
  BRIEF: "brief",
  PROFESSION_MAP: "profession_map",
  SCENARIO_PLAN: "scenario_plan",
  EXPORT: "export",
  DRAFT_TZ: "draft_tz",
  EXPERT_FEEDBACK: "expert_feedback",
  EXPERT_SYNTHESIS: "expert_synthesis",
  FINAL_TZ: "final_tz",
  SCENE_BREAKDOWN: "scene_breakdown",
  PRODUCTION_PLANNING: "production_planning",
  STORYBOARD: "storyboard",
} as const;

export const PIPELINE_ORDER = [
  StepType.BRIEF,
  StepType.PROFESSION_MAP,
  StepType.SCENARIO_PLAN,
  StepType.EXPORT,
] as const;

export const VISIBLE_STEP_TYPES = new Set(PIPELINE_ORDER);
