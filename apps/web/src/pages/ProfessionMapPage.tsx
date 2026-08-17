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
      subtitle="До 7 вариантов работ, навыки, точки оценки и укрупнённый сюжет. Это черновик до детального сценария: принимайте или отклоняйте элементы."
      allowAcceptReject
    />
  );
}
