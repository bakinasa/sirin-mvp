import { useParams } from "react-router-dom";
import { StageWorkspace } from "../components/StageWorkspace";

export function ProfessionMapPage() {
  const { projectId } = useParams();
  if (!projectId) return null;
  return (
    <StageWorkspace
      projectId={projectId}
      stageType="profession_map"
      title="Сюжет и точки оценки"
      subtitle="Все виды работ из материалов проекта, навыки, точки оценки и вопросы экспертам. Это черновик до детального сценария."
      allowAcceptReject
    />
  );
}
