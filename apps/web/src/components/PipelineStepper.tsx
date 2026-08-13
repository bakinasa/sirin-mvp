import { Link } from "react-router-dom";
import clsx from "clsx";
import { PipelineStep, STEP_LABELS } from "../lib/api";
import { StatusBadge } from "./StatusBadge";
import {
  getCurrentStepIndex,
  isStepAccessible,
  STEP_ACCESS_LOCK_ENABLED,
  stepPath,
  visiblePipeline,
} from "../lib/pipelineAccess";

export function PipelineStepper({
  projectId,
  steps,
}: {
  projectId: string;
  steps: PipelineStep[];
}) {
  const sorted = visiblePipeline(steps);
  const currentIdx = getCurrentStepIndex(steps);

  return (
    <div className="sticky top-[57px] z-30 -mx-4 mb-6 overflow-x-auto border-b border-neutral-200 bg-white/95 px-4 py-3 backdrop-blur dark:border-neutral-800 dark:bg-neutral-950/95">
      <p className="mb-2 text-xs text-neutral-500">
        {STEP_ACCESS_LOCK_ENABLED
          ? "Доступны пройденные шаги и текущий. Следующие откроются после Approve."
          : "Шаги временно разблокированы для навигации."}
      </p>
      <ol className="flex min-w-max gap-2">
        {sorted.map((s, idx) => {
          const open = isStepAccessible(steps, s.step_type);
          const isCurrent = idx === currentIdx;
          const className = clsx(
            "flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition",
            open
              ? isCurrent
                ? "border-neutral-900 bg-neutral-900 text-white dark:border-white dark:bg-white dark:text-neutral-900"
                : "border-neutral-200 bg-white hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900"
              : "border-neutral-100 bg-neutral-50 opacity-45 dark:border-neutral-800 dark:bg-neutral-900/40"
          );

          const inner = (
            <>
              <span className="text-xs opacity-60">{idx + 1}</span>
              <span className="font-medium">{STEP_LABELS[s.step_type] || s.step_type}</span>
              <StatusBadge status={s.status} />
              {!open && <span className="text-[10px] uppercase tracking-wide">закрыт</span>}
            </>
          );

          return (
            <li key={s.id}>
              {open ? (
                <Link to={stepPath(projectId, s.step_type)} className={className}>
                  {inner}
                </Link>
              ) : (
                <span
                  className={className}
                  title="Сначала утвердите предыдущий шаг"
                >
                  {inner}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
