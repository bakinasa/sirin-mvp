import { CommentThread, DocItem } from "../lib/api";
import { StatusBadge } from "./StatusBadge";
import { StringListEditor } from "./SceneCard";

type ErrorRow = { error: string; correct: string; visual_cues: string[] };

type Props = {
  item: DocItem;
  selected: boolean;
  readOnly: boolean;
  allowAcceptReject: boolean;
  commentThreads?: CommentThread[];
  onResolveComment?: (id: string) => void;
  onSelect: () => void;
  onChange: (item: DocItem) => void;
  onAccept: () => void;
  onReject: () => void;
};

/** Same editing pattern as SceneCard: patch via `{ ...item, ...next }` from current props. */
function asErrors(value: unknown): ErrorRow[] {
  if (!Array.isArray(value)) return [];
  return value.map((r) => {
    const row = (r && typeof r === "object" ? r : {}) as Record<string, unknown>;
    return {
      error: String(row.error ?? row.error_observation ?? ""),
      correct: String(row.correct ?? row.correct_observation ?? ""),
      visual_cues: Array.isArray(row.visual_cues)
        ? (row.visual_cues as unknown[]).map((x) => String(x ?? ""))
        : typeof row.visual_cues === "string" && row.visual_cues
          ? [String(row.visual_cues)]
          : [],
    };
  });
}

function migrateFlatErrors(item: DocItem): ErrorRow[] {
  const fromArray = asErrors(item.errors);
  if (fromArray.length > 0) return fromArray;
  const hasFlat =
    item.error_observation != null ||
    item.correct_observation != null ||
    item.visual_cues != null;
  if (!hasFlat) return [];
  return [
    {
      error: String(item.error_observation ?? ""),
      correct: String(item.correct_observation ?? ""),
      visual_cues: Array.isArray(item.visual_cues)
        ? (item.visual_cues as unknown[]).map((x) => String(x ?? ""))
        : typeof item.visual_cues === "string" && item.visual_cues
          ? [item.visual_cues]
          : [],
    },
  ];
}

export function AssessmentCard({
  item,
  selected,
  readOnly,
  allowAcceptReject,
  commentThreads,
  onResolveComment,
  onSelect,
  onChange,
  onAccept,
  onReject,
}: Props) {
  const rows = migrateFlatErrors(item);

  function patch(next: Partial<DocItem>) {
    onChange({ ...item, ...next });
  }

  function withErrors(errors: ErrorRow[]): DocItem {
    const {
      error_observation: _e,
      correct_observation: _c,
      visual_cues: _v,
      ...rest
    } = item as DocItem & Record<string, unknown>;
    void _e;
    void _c;
    void _v;
    return { ...rest, errors } as DocItem;
  }

  function updateError(index: number, field: keyof ErrorRow, value: string | string[]) {
    const next = migrateFlatErrors(item);
    next[index] = { ...next[index], [field]: value };
    onChange(withErrors(next));
  }

  function addError() {
    onChange(withErrors([...migrateFlatErrors(item), { error: "", correct: "", visual_cues: [] }]));
  }

  function removeError(index: number) {
    onChange(withErrors(migrateFlatErrors(item).filter((_, i) => i !== index)));
  }

  return (
    <article
      className={`panel cursor-pointer space-y-3 ${selected ? "ring-2 ring-neutral-900 dark:ring-white" : ""}`}
      onClick={onSelect}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <label className="label text-xs">Вид работ</label>
          <input
            className="input font-semibold"
            disabled={readOnly}
            value={String(item.title || "")}
            onChange={(e) => patch({ title: e.target.value })}
            onClick={(e) => e.stopPropagation()}
            placeholder="Название вида работ"
          />
          {selected && (
            <p className="mt-0.5 text-xs text-neutral-500">
              Выбрано: точечная правка (вкладка «Блок») и комментарий справа относятся к этой карточке.
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {item.status && <StatusBadge status={String(item.status)} />}
          {allowAcceptReject && (
            <>
              <button
                type="button"
                className="btn-ghost px-2 py-1 text-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  onAccept();
                }}
              >
                Принять
              </button>
              <button
                type="button"
                className="btn-ghost px-2 py-1 text-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  onReject();
                }}
              >
                Отклонить
              </button>
            </>
          )}
        </div>
      </div>

      <div onClick={(e) => e.stopPropagation()}>
        <label className="label text-xs">Контекст</label>
        <textarea
          className="input min-h-[56px]"
          disabled={readOnly}
          value={String(item.description ?? "")}
          onChange={(e) => patch({ description: e.target.value })}
          placeholder="Краткий контекст вида работ"
        />
      </div>

      <div onClick={(e) => e.stopPropagation()}>
        <div className="mb-1 flex items-center justify-between">
          <label className="label text-xs">Ошибки и правильные действия</label>
          {!readOnly && (
            <button type="button" className="btn-ghost px-2 py-0.5 text-xs" onClick={addError}>
              + ошибка
            </button>
          )}
        </div>
        <div className="overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-700">
          <table className="min-w-full text-left text-xs">
            <thead className="bg-neutral-50 dark:bg-neutral-900">
              <tr>
                <th className="px-2 py-1.5 font-medium">Ошибка</th>
                <th className="px-2 py-1.5 font-medium">Правильно</th>
                <th className="px-2 py-1.5 font-medium">Визуальные признаки</th>
                {!readOnly && <th className="w-8 px-1 py-1.5" />}
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td className="px-2 py-2 text-neutral-400" colSpan={readOnly ? 3 : 4}>
                    Нет ошибок. Добавьте строку.
                  </td>
                </tr>
              )}
              {rows.map((row, idx) => (
                <tr key={idx} className="border-t border-neutral-200 dark:border-neutral-800">
                  <td className="px-1 py-1 align-top">
                    <textarea
                      className="input min-h-[52px] text-xs"
                      disabled={readOnly}
                      placeholder="Что именно сделано неправильно"
                      value={row.error}
                      onChange={(e) => updateError(idx, "error", e.target.value)}
                    />
                  </td>
                  <td className="px-1 py-1 align-top">
                    <textarea
                      className="input min-h-[52px] text-xs"
                      disabled={readOnly}
                      placeholder="Как надо делать"
                      value={row.correct}
                      onChange={(e) => updateError(idx, "correct", e.target.value)}
                    />
                  </td>
                  <td className="px-1 py-1 align-top">
                    <StringListEditor
                      values={row.visual_cues}
                      readOnly={readOnly}
                      onChange={(values) => updateError(idx, "visual_cues", values)}
                    />
                  </td>
                  {!readOnly && (
                    <td className="px-1 py-1 align-top">
                      <button
                        type="button"
                        className="btn-ghost px-1 py-0.5 text-xs"
                        onClick={() => removeError(idx)}
                      >
                        ×
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {commentThreads && commentThreads.length > 0 && (
        <div className="space-y-1 border-t border-neutral-200 pt-2 dark:border-neutral-700">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-neutral-400">Комментарии</p>
          {commentThreads.map((t) => (
            <div key={t.id} className="rounded-md bg-amber-50 px-2 py-1.5 text-xs dark:bg-amber-950/30">
              {t.messages.map((m) => (
                <p key={m.id} className="whitespace-pre-wrap">
                  {m.body}
                </p>
              ))}
              {t.status === "open" && onResolveComment && (
                <button
                  type="button"
                  className="btn-ghost mt-1 px-1 py-0 text-[10px]"
                  onClick={(e) => {
                    e.stopPropagation();
                    onResolveComment(t.id);
                  }}
                >
                  Закрыть
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </article>
  );
}
