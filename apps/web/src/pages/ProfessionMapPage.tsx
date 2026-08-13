import { useParams } from "react-router-dom";
import { StageWorkspace } from "../components/StageWorkspace";

export function ProfessionMapPage() {
  const { projectId } = useParams();
  if (!projectId) return null;
  return (
    <StageWorkspace
      projectId={projectId}
      stageType="profession_map"
      title="Карта профессии"
      subtitle="Вид работ, навыки, точки оценки и вопросы экспертам. Обсуждайте с AI, принимайте или отклоняйте элементы."
      allowAcceptReject
    />
  );
}
