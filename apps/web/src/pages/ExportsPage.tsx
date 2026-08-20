import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, PipelineStep } from "../lib/api";
import { PipelineStepper } from "../components/PipelineStepper";
import { downloadDocx, exportDocx } from "../lib/docxExport";

type ExportJob = {
  id: string;
  export_type: string;
  status: string;
  result_content: unknown;
  error_message: string;
};

export function ExportsPage() {
  const { projectId } = useParams();
  const [steps, setSteps] = useState<PipelineStep[]>([]);
  const [job, setJob] = useState<ExportJob | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    api<PipelineStep[]>(`/projects/${projectId}/pipeline`).then(setSteps);
  }, [projectId]);

  async function run(type: "docx_scenario" | "docx_profession_map") {
    if (!projectId) return;
    setBusy(type);
    try {
      const full = await exportDocx(
        projectId,
        type,
        type === "docx_scenario" ? "scenario.docx" : "story.docx"
      );
      setJob(full);
    } finally {
      setBusy(null);
    }
  }

  if (!projectId) return null;

  return (
    <div>
      <PipelineStepper projectId={projectId} steps={steps} />
      <div className="mb-6">
        <h1 className="text-3xl font-semibold tracking-tight">Экспорт</h1>
        <p className="text-sm text-neutral-500">Сюжет и сценарий в формате Word (.docx).</p>
      </div>

      <div className="mb-6 flex flex-wrap gap-3">
        <button
          className="btn-primary"
          disabled={!!busy}
          onClick={() => void run("docx_scenario")}
        >
          {busy === "docx_scenario" ? "Генерация…" : "Скачать сценарий DOCX"}
        </button>
        <button
          className="btn-ghost"
          disabled={!!busy}
          onClick={() => void run("docx_profession_map")}
        >
          {busy === "docx_profession_map" ? "Генерация…" : "Скачать сюжет DOCX"}
        </button>
        {job?.status === "ready" && (
          <button
            className="btn-ghost"
            onClick={() =>
              downloadDocx(
                job.result_content,
                job.export_type === "docx_profession_map" ? "story.docx" : "scenario.docx"
              )
            }
          >
            Скачать снова
          </button>
        )}
      </div>

      {job?.status === "failed" && (
        <div className="panel text-sm text-red-600">Ошибка: {job.error_message}</div>
      )}
    </div>
  );
}
