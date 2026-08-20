import { BlockDocument } from "./api";

export type UnansweredExpertQuestion = {
  title: string;
  description: string;
  why_needed: string;
};

const ASSESSMENT_SECTION_IDS = new Set([
  "assessment_points",
  "skills",
  "evaluated_skills",
  "errors",
]);

export function isAssessmentSection(sectionId?: string): boolean {
  return !!sectionId && ASSESSMENT_SECTION_IDS.has(sectionId);
}

export function getUnansweredExpertQuestions(content: unknown): UnansweredExpertQuestion[] {
  if (!content || typeof content !== "object") return [];
  const doc = content as BlockDocument;
  const section = (doc.sections || []).find((s) => s.id === "expert_questions");
  if (!section?.items?.length) return [];

  return section.items
    .filter((item) => !String(item.answer || "").trim())
    .map((item) => ({
      title: String(item.title || "Без названия"),
      description: String(item.description || ""),
      why_needed: String(item.why_needed || ""),
    }));
}

export function syncSectionIdAfterArtifact(
  sections: { id: string }[],
  currentSectionId: string
): string {
  const ids = new Set(sections.map((s) => s.id));
  if (currentSectionId && ids.has(currentSectionId)) return currentSectionId;

  if (currentSectionId && isAssessmentSection(currentSectionId)) {
    if (ids.has("assessment_points")) return "assessment_points";
    if (ids.has("skills")) return "skills";
  }

  return sections[0]?.id || currentSectionId;
}
