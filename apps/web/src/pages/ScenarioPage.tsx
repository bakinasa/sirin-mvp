import { useParams } from "react-router-dom";
import { StageWorkspace } from "../components/StageWorkspace";

export function ScenarioPage() {
  const { projectId } = useParams();
  if (!projectId) return null;
  return (
    <StageWorkspace
      projectId={projectId}
      stageType="scenario_plan"
      title="Сценарий и съёмочный план"
      subtitle="Единый рабочий документ: обучение, диагностика, реквизит и замечания к съёмке."
    />
  );
}
