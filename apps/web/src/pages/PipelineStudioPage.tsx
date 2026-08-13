import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, Artifact, PipelineStep, STEP_LABELS } from "../lib/api";
import { PipelineStepper } from "../components/PipelineStepper";
import { PromptPanel } from "../components/PromptPanel";
import { ModelSelector } from "../components/ModelSelector";
import { ArtifactEditor } from "../components/ArtifactEditor";

type RunResult = {
  id: string;
  status: string;
  model_name: string;
  provider_name?: string;
  estimated_cost: number | null;
  error_message: string;
};

/** Shared studio shell for AI pipeline steps with Prompt Panel + Model Selector. */
export function PipelineStudioPage() {
  const { projectId, stepType = "draft_tz" } = useParams();
  const [steps, setSteps] = useState<PipelineStep[]>([]);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [operatorPrompt, setOperatorPrompt] = useState("");
  const [primaryId, setPrimaryId] = useState("");
  const [fallbackId, setFallbackId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [lastRun, setLastRun] = useState<RunResult | null>(null);

  const reload = useCallback(async () => {
    if (!projectId) return;
    const [s, arts] = await Promise.all([
      api<PipelineStep[]>(`/projects/${projectId}/pipeline`),
      api<Artifact[]>(`/projects/${projectId}/artifacts?step_type=${stepType}`),
    ]);
    setSteps(s);
    setArtifact(arts[0] || null);
  }, [projectId, stepType]);

  useEffect(() => {
    reload().catch(console.error);
  }, [reload]);

  async function run() {
    setBusy(true);
    setError("");
    setLastRun(null);
    try {
      const result = await api<RunResult>(`/projects/${projectId}/pipeline/run`, {
        method: "POST",
        body: JSON.stringify({
          step_type: stepType,
          operator_prompt: operatorPrompt,
          primary_model_id: primaryId || null,
          fallback_model_id: fallbackId || null,
        }),
      });
      setLastRun(result);
      await reload();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!projectId) return null;

  const isMockRun = lastRun?.model_name === "mock-local" || lastRun?.provider_name === "mock";
  const artifactIsMock =
    !!artifact &&
    typeof artifact.content === "object" &&
    artifact.content !== null &&
    (artifact.content as { _mock?: boolean })._mock === true;

  return (
    <div>
      <PipelineStepper projectId={projectId} steps={steps} />
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">
            {STEP_LABELS[stepType] || stepType}
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-neutral-600 dark:text-neutral-300">
            ИИ получит данные проекта и Brief. «Бесплатная модель» ≠ «без ключа»: ключ провайдера
            всё равно нужен. Без ключа система покажет заглушку по вашим данным, а не ответ нейросети.
          </p>
          {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
        </div>
        <button className="btn-primary" disabled={busy} onClick={run}>
          {busy ? "Генерация…" : "Запустить AI"}
        </button>
      </div>

      {(isMockRun || artifactIsMock) && (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-100">
          <p className="font-semibold">Сработала заглушка (mock), не настоящая нейросеть</p>
          <p className="mt-1">
            {lastRun?.error_message
              ? `Причина: ${lastRun.error_message}`
              : "Не удалось вызвать модель — обычно нет API-ключа у выбранного провайдера."}
          </p>
          <p className="mt-1">
            Выберите модель OpenRouter (или другого провайдера), добавьте ключ в{" "}
            <Link className="font-semibold underline" to="/models">
              Модели
            </Link>
            , проверьте ключ (должно быть OK) и снова нажмите «Запустить AI».
          </p>
        </div>
      )}

      {lastRun && !isMockRun && (
        <p className="mb-4 text-xs text-neutral-500">
          OK · {lastRun.provider_name || "provider"} / {lastRun.model_name} · cost≈
          {lastRun.estimated_cost ?? 0}
        </p>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="space-y-4">
          <PromptPanel
            projectId={projectId}
            stepType={stepType}
            value={operatorPrompt}
            onChange={setOperatorPrompt}
          />
          <ModelSelector
            primaryId={primaryId}
            fallbackId={fallbackId}
            onPrimary={setPrimaryId}
            onFallback={setFallbackId}
          />
        </div>
        <ArtifactEditor
          artifact={artifact}
          onUpdated={() => reload()}
          runMeta={
            lastRun
              ? {
                  model_name: lastRun.model_name,
                  provider_name: lastRun.provider_name,
                  error_message: lastRun.error_message,
                }
              : null
          }
        />
      </div>
    </div>
  );
}
