import { useState } from "react";
import { CommentThread, DocItem } from "../lib/api";
import { StatusBadge } from "./StatusBadge";

type Frame = Record<string, unknown>;

type Props = {
  item: DocItem;
  variant: "training" | "diagnostic";
  selected: boolean;
  readOnly: boolean;
  commentThreads?: CommentThread[];
  onResolveComment?: (id: string) => void;
  onSelect: () => void;
  onChange: (item: DocItem) => void;
};

function asFrames(value: unknown): Frame[] {
  if (!Array.isArray(value)) return [];
  return value.map((row) => (row && typeof row === "object" ? { ...(row as Frame) } : {}));
}

function asStringList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((x) => String(x ?? ""));
  if (typeof value === "string" && value.trim()) return [value];
  return [];
}

function asCategoryGroups(value: unknown): { title: string; violation: string; description: string }[] {
  if (!Array.isArray(value)) return [];
  return value.map((row) => {
    if (typeof row === "string") return { title: row, violation: "", description: "" };
    if (row && typeof row === "object") {
      const o = row as Record<string, unknown>;
      return {
        title: String(o.title ?? o.name ?? ""),
        violation: String(o.violation ?? ""),
        description: String(o.description ?? ""),
      };
    }
    return { title: "", violation: "", description: "" };
  });
}

export function SceneCard({
  item,
  variant,
  selected,
  readOnly,
  commentThreads,
  onResolveComment,
  onSelect,
  onChange,
}: Props) {
  const frames = asFrames(item.frames);
  const isTraining = variant === "training";

  function patch(next: Partial<DocItem>) {
    onChange({ ...item, ...next });
  }

  function updateFrame(index: number, field: string, value: unknown) {
    const next = asFrames(item.frames);
    next[index] = { ...next[index], [field]: value };
    patch({ frames: next });
  }

  function addFrame() {
    const next = asFrames(item.frames);
    next.push(
      isTraining
        ? { shot_no: next.length + 1, action: "", accent: "" }
        : { shot_no: next.length + 1, action: "", violation: "", accent: "" }
    );
    patch({ frames: next });
  }

  const categories = asCategoryGroups(item.violation_categories);
  const [showCategories, setShowCategories] = useState(categories.length > 0);

  function removeFrame(index: number) {
    patch({ frames: asFrames(item.frames).filter((_, i) => i !== index) });
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
            placeholder="Например: Выход из подъезда"
          />
          {selected && (
            <p className="mt-0.5 text-xs text-neutral-500">
              Выбрано: точечная правка и комментарий справа относятся к этой сцене.
            </p>
          )}
        </div>
        {item.status && <StatusBadge status={String(item.status)} />}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="label text-xs">Актёры</label>
          <input
            className="input"
            disabled={readOnly}
            value={String(item.actors ?? "")}
            onChange={(e) => patch({ actors: e.target.value })}
            onClick={(e) => e.stopPropagation()}
          />
        </div>
        <div>
          <label className="label text-xs">Локация</label>
          <input
            className="input"
            disabled={readOnly}
            value={String(item.location ?? "")}
            onChange={(e) => patch({ location: e.target.value })}
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      </div>

      <div onClick={(e) => e.stopPropagation()}>
        <div className="mb-1 flex items-center justify-between">
          <label className="label text-xs">Кадры</label>
          {!readOnly && (
            <button type="button" className="btn-ghost px-2 py-0.5 text-xs" onClick={addFrame}>
              + кадр
            </button>
          )}
        </div>
        <div className="overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-700">
          <table className="min-w-full text-left text-xs">
            <thead className="bg-neutral-50 dark:bg-neutral-900">
              <tr>
                <th className="px-2 py-1.5 font-medium">№</th>
                <th className="px-2 py-1.5 font-medium">Действие в кадре</th>
                {!isTraining && <th className="px-2 py-1.5 font-medium">Нарушение (пусто = норма)</th>}
                <th className="px-2 py-1.5 font-medium">Акцент</th>
                {!readOnly && <th className="w-8 px-1 py-1.5" />}
              </tr>
            </thead>
            <tbody>
              {frames.length === 0 && (
                <tr>
                  <td className="px-2 py-2 text-neutral-400" colSpan={isTraining ? 4 : 5}>
                    Нет кадров. Добавьте строку.
                  </td>
                </tr>
              )}
              {frames.map((frame, idx) => (
                <tr key={String(frame.id ?? idx)} className="border-t border-neutral-200 dark:border-neutral-800">
                  <td className="px-1 py-1 align-top">
                    <input
                      className="input w-14 px-1 py-1 text-xs"
                      disabled={readOnly}
                      value={String(frame.shot_no ?? idx + 1)}
                      onChange={(e) => updateFrame(idx, "shot_no", e.target.value)}
                    />
                  </td>
                  <td className="px-1 py-1 align-top">
                    <textarea
                      className="input min-h-[52px] text-xs"
                      disabled={readOnly}
                      value={String(frame.action ?? "")}
                      onChange={(e) => updateFrame(idx, "action", e.target.value)}
                    />
                  </td>
                  {!isTraining && (
                    <td className="px-1 py-1 align-top">
                      <textarea
                        className="input min-h-[52px] text-xs"
                        disabled={readOnly}
                        placeholder="Оставьте пустым если норма"
                        value={String(frame.violation ?? "")}
                        onChange={(e) => updateFrame(idx, "violation", e.target.value)}
                      />
                    </td>
                  )}
                  <td className="px-1 py-1 align-top">
                    <textarea
                      className="input min-h-[52px] text-xs"
                      disabled={readOnly}
                      value={String(frame.accent ?? "")}
                      onChange={(e) => updateFrame(idx, "accent", e.target.value)}
                    />
                  </td>
                  {!readOnly && (
                    <td className="px-1 py-1 align-top">
                      <button type="button" className="btn-ghost px-1 py-0.5 text-xs" onClick={() => removeFrame(idx)}>
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

      {isTraining && (
        <div>
          <label className="label text-xs">Аудиотекст</label>
          <textarea
            className="input min-h-[72px]"
            disabled={readOnly}
            value={String(item.audio_text ?? "")}
            onChange={(e) => patch({ audio_text: e.target.value })}
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}

      {!isTraining && (
        <div onClick={(e) => e.stopPropagation()}>
          <div className="mb-1 flex items-center justify-between">
            <button
              type="button"
              className="label flex items-center gap-1 text-xs"
              onClick={() => setShowCategories((v) => !v)}
            >
              Категории нарушений {showCategories ? "▴" : "▾"}
            </button>
            {!readOnly && (
              <button
                type="button"
                className="btn-ghost px-2 py-0.5 text-xs"
                onClick={() =>
                  patch({
                    violation_categories: [...categories, { title: `Категория ${categories.length + 1}`, violation: "", description: "" }],
                  })
                }
              >
                + категория
              </button>
            )}
          </div>
          {showCategories && (
            <div className="space-y-2">
              {categories.length === 0 && (
                <p className="text-xs text-neutral-400">Нет категорий. Добавьте через кнопку выше.</p>
              )}
              {categories.map((cat, idx) => (
                <div key={idx} className="space-y-1 rounded-md border border-neutral-200 p-2 dark:border-neutral-700">
                  <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                    <input
                      className="input text-sm"
                      disabled={readOnly}
                      placeholder="Название категории"
                      value={cat.title}
                      onChange={(e) => {
                        const next = categories.map((c, i) => (i === idx ? { ...c, title: e.target.value } : c));
                        patch({ violation_categories: next });
                      }}
                    />
                    <input
                      className="input text-sm"
                      disabled={readOnly}
                      placeholder="Нарушение из таблицы кадров"
                      value={cat.violation}
                      onChange={(e) => {
                        const next = categories.map((c, i) => (i === idx ? { ...c, violation: e.target.value } : c));
                        patch({ violation_categories: next });
                      }}
                    />
                    {!readOnly && (
                      <button
                        type="button"
                        className="btn-ghost self-start px-2 py-1 text-xs"
                        onClick={() => patch({ violation_categories: categories.filter((_, i) => i !== idx) })}
                      >
                        ×
                      </button>
                    )}
                  </div>
                  <textarea
                    className="input min-h-[60px] text-sm"
                    disabled={readOnly}
                    placeholder="Подробное описание: почему это нарушение, какое правило нарушено, к чему приводит"
                    value={cat.description}
                    onChange={(e) => {
                      const next = categories.map((c, i) => (i === idx ? { ...c, description: e.target.value } : c));
                      patch({ violation_categories: next });
                    }}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div onClick={(e) => e.stopPropagation()}>
        <label className="label text-xs">Правила / регламенты</label>
        <DocumentListEditor
          values={asStringList(item.regulations)}
          readOnly={readOnly}
          onChange={(values) => patch({ regulations: values })}
        />
      </div>
      <div>
        <label className="label text-xs">Реквизит</label>
        {Array.isArray(item.props) ? (
          <StringListEditor
            values={asStringList(item.props)}
            readOnly={readOnly}
            onChange={(values) => patch({ props: values })}
          />
        ) : (
          <textarea
            className="input min-h-[56px]"
            disabled={readOnly}
            value={String(item.props ?? "")}
            onChange={(e) => patch({ props: e.target.value })}
            onClick={(e) => e.stopPropagation()}
          />
        )}
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

export function StringListEditor({
  values,
  readOnly,
  onChange,
}: {
  values: string[];
  readOnly: boolean;
  onChange: (values: string[]) => void;
}) {
  return (
    <div className="space-y-1" onClick={(e) => e.stopPropagation()}>
      {values.map((line, idx) => (
        <div key={idx} className="flex gap-1">
          <input
            className="input text-sm"
            disabled={readOnly}
            value={line}
            onChange={(e) => onChange(values.map((v, i) => (i === idx ? e.target.value : v)))}
          />
          {!readOnly && (
            <button
              type="button"
              className="btn-ghost px-2 py-1 text-xs"
              onClick={() => onChange(values.filter((_, i) => i !== idx))}
            >
              ×
            </button>
          )}
        </div>
      ))}
      {!readOnly && (
        <button type="button" className="btn-ghost px-2 py-0.5 text-xs" onClick={() => onChange([...values, ""])}>
          + строка
        </button>
      )}
    </div>
  );
}

function DocumentListEditor({
  values,
  readOnly,
  onChange,
}: {
  values: string[];
  readOnly: boolean;
  onChange: (values: string[]) => void;
}) {
  return (
    <div className="space-y-1">
      {values.map((line, idx) => (
        <div key={idx} className="flex gap-1">
          <input
            className="input text-sm"
            disabled={readOnly}
            placeholder="Название СОП / регламента"
            value={line}
            onChange={(e) => onChange(values.map((v, i) => (i === idx ? e.target.value : v)))}
          />
          {!readOnly && (
            <button
              type="button"
              className="btn-ghost px-2 py-1 text-xs"
              onClick={() => onChange(values.filter((_, i) => i !== idx))}
            >
              ×
            </button>
          )}
        </div>
      ))}
      {!readOnly && (
        <button type="button" className="btn-ghost px-2 py-0.5 text-xs" onClick={() => onChange([...values, ""])}>
          + документ
        </button>
      )}
    </div>
  );
}
