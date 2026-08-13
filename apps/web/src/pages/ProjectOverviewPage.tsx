import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, PipelineStep, Project, STEP_LABELS } from "../lib/api";
import { PipelineStepper } from "../components/PipelineStepper";
import { StatusBadge } from "../components/StatusBadge";
import { isStepAccessible, stepPath, getCurrentStepIndex } from "../lib/pipelineAccess";

export function ProjectOverviewPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [steps, setSteps] = useState<PipelineStep[]>([]);
  const [metrics, setMetrics] = useState<{
    total_runs: number;
    regenerations: number;
    manual_edits: number;
    total_cost: number;
    avg_latency_ms: number;
  } | null>(null);

  useEffect(() => {
    if (!projectId) return;
    Promise.all([
      api<Project>(`/projects/${projectId}`),
      api<PipelineStep[]>(`/projects/${projectId}/pipeline`),
      api<typeof metrics>(`/projects/${projectId}/metrics`),
    ]).then(([p, s, m]) => {
      setProject(p);
      setSteps(s);
      setMetrics(m);
    });
  }, [projectId]);

  async function remove() {
    if (!projectId || !project) return;
    if (!confirm(`Удалить проект «${project.title}»?`)) return;
    await api(`/projects/${projectId}`, { method: "DELETE" });
    navigate("/");
  }

  if (!project || !projectId) return <div className="panel">Загрузка…</div>;

  const sorted = [...steps].sort((a, b) => a.order_index - b.order_index);
  const currentIdx = getCurrentStepIndex(steps);
  const current = sorted[currentIdx];

  return (
    <div>
      <PipelineStepper projectId={projectId} steps={steps} />
      <div className="space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{project.title}</h1>
            <p className="mt-2 text-neutral-600 dark:text-neutral-300">
              {[project.client_name, project.profession, project.delivery_format]
                .filter(Boolean)
                .join(" · ") || "Метаданные пока не заполнены"}
            </p>
          </div>
          <button className="btn-danger" onClick={remove}>
            Удалить проект
          </button>
        </div>

        {current && (
          <div className="rounded-lg border border-neutral-900 bg-neutral-900 px-4 py-3 text-sm text-white dark:border-white dark:bg-white dark:text-neutral-900">
            Сейчас активен шаг:{" "}
            <strong>{STEP_LABELS[current.step_type] || current.step_type}</strong>
            <Link className="ml-3 underline" to={stepPath(projectId, current.step_type)}>
              Перейти
            </Link>
          </div>
        )}

        <div className="grid gap-4 md:grid-cols-4">
          {[
            ["AI-запуски", metrics?.total_runs ?? "—"],
            ["Регенерации", metrics?.regenerations ?? "—"],
            ["Ручные правки", metrics?.manual_edits ?? "—"],
            ["Стоимость ≈", metrics ? `$${metrics.total_cost.toFixed(4)}` : "—"],
          ].map(([k, v]) => (
            <div key={k as string} className="panel">
              <p className="label">{k as string}</p>
              <p className="text-2xl font-semibold">{v as string | number}</p>
            </div>
          ))}
        </div>

        <div className="panel">
          <h2 className="mb-4 text-lg font-semibold">Пайплайн</h2>
          <ul className="space-y-2">
            {sorted.map((s, idx) => {
              const open = isStepAccessible(steps, s.step_type);
              return (
                <li
                  key={s.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-neutral-200 px-3 py-2 dark:border-neutral-700"
                >
                  <span>
                    {idx + 1}. {STEP_LABELS[s.step_type] || s.step_type}
                  </span>
                  <div className="flex items-center gap-3">
                    <StatusBadge status={s.status} />
                    {open ? (
                      <Link
                        className="text-sm font-medium underline"
                        to={stepPath(projectId, s.step_type)}
                      >
                        открыть
                      </Link>
                    ) : (
                      <span className="text-xs text-neutral-400">сначала утвердите прошлый шаг</span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}
