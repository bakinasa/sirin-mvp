import { FormEvent, useEffect, useState } from "react";
import { api } from "../lib/api";

type Provider = {
  id: string;
  name: string;
  type: string;
  base_url: string;
  capabilities_json: Record<string, unknown>;
  is_active: boolean;
};

type Model = {
  id: string;
  provider_id: string;
  model_id: string;
  label: string;
  is_free: boolean;
  provider_name?: string;
  provider_type?: string;
  base_url?: string;
  capabilities_json?: Record<string, unknown>;
  is_enabled?: boolean;
  input_price: number | null;
  output_price: number | null;
  context_window: number | null;
  tags: string[];
};

const PROVIDER_HELP: Record<string, string> = {
  openrouter: "Шлюз к разным моделям (в т.ч. бесплатным). Нужен API-ключ OpenRouter.",
  hubris: "Шлюз с пометкой free/paid. Нужен API-ключ Hubris.",
  tsarrouter: "Российский OpenAI-совместимый роутер. Нужен ключ TsarRouter.",
  openai_compatible: "Прямое подключение к OpenAI или любому совместимому /v1 API.",
  yandex: "YandexGPT. Без вашего ключа проверка будет FAIL — это нормально.",
  gigachat: "GigaChat. Без вашего ключа проверка будет FAIL — это нормально.",
};

export function ModelsPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [cred, setCred] = useState({ provider_id: "", api_key: "", label: "Мой ключ" });
  const [testResult, setTestResult] = useState<{
    provider: string;
    ok: boolean;
    hint: string;
  } | null>(null);
  const [syncMsg, setSyncMsg] = useState("");
  const [busyId, setBusyId] = useState("");
  const [providerChoice, setProviderChoice] = useState<string>(""); // provider.id or "custom"
  const [testByModelId, setTestByModelId] = useState<
    Record<string, { ok: boolean; hint: string; provider: string }>
  >({});

  const [form, setForm] = useState({
    provider_type: "openai_compatible",
    provider_name: "",
    base_url: "",
    structured_output: true,
    vision: false,
    russian_friendly: false,
    model_id: "",
    label: "",
    api_key: "",
    is_free: false,
  });

  type ManualModelForm = {
    model_id: string;
    label: string;
    is_free: boolean;
    input_price: string;
    output_price: string;
    context_window: string;
    tags_csv: string;
  };

  const emptyManualForm: ManualModelForm = {
    model_id: "",
    label: "",
    is_free: false,
    input_price: "",
    output_price: "",
    context_window: "",
    tags_csv: "",
  };

  const [manualByProvider, setManualByProvider] = useState<Record<string, ManualModelForm>>(
    {}
  );

  function getManual(providerId: string) {
    return manualByProvider[providerId] || emptyManualForm;
  }

  async function load() {
    const [p, m] = await Promise.all([
      api<Provider[]>("/providers"),
      api<Model[]>("/user-models"),
    ]);
    setProviders(p);
    setModels(m);
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  async function saveKey(e: FormEvent) {
    e.preventDefault();
    setSyncMsg("");
    try {
      await api("/providers/credentials", {
        method: "POST",
        body: JSON.stringify(cred),
      });
      const providerName =
        providers.find((p) => p.id === cred.provider_id)?.name || "провайдер";
      setCred({ ...cred, api_key: "" });
      await load();
      setSyncMsg(
        `Ключ для «${providerName}» сохранён, каталог моделей обновлён. Теперь они появятся в Model Selector на шагах проекта.`
      );
    } catch (err) {
      setSyncMsg(`Не удалось сохранить ключ: ${err}`);
    }
  }

  async function sync(providerId: string, name: string) {
    setBusyId(providerId);
    setSyncMsg("");
    try {
      const items = await api<Model[]>(`/providers/${providerId}/models/sync`);
      await load();
      setSyncMsg(
        items.length
          ? `«${name}»: загружено рабочих моделей: ${items.length}.`
          : `«${name}»: моделей нет. Проверьте API-ключ (кнопка «Проверить ключ»).`
      );
    } catch (e) {
      setSyncMsg(`Не удалось обновить каталог: ${e}`);
    } finally {
      setBusyId("");
    }
  }

  async function test(providerId: string, name: string) {
    setBusyId(providerId);
    setTestResult(null);
    try {
      const res = await api<{
        ok: boolean;
        provider: string;
        synced_models?: number;
        hint?: string;
      }>("/providers/test", {
        method: "POST",
        body: JSON.stringify({ provider_id: providerId }),
      });
      setTestResult({
        provider: res.provider || name,
        ok: res.ok,
        hint:
          res.hint ||
          (res.ok
            ? "Ключ принят."
            : "FAIL — ключ не найден или неверный."),
      });
      await load();
    } catch (e) {
      setTestResult({
        provider: name,
        ok: false,
        hint: `Ошибка проверки: ${e}`,
      });
    } finally {
      setBusyId("");
    }
  }

  async function addModelManual(providerId: string) {
    const form = getManual(providerId);
    setBusyId(providerId);
    setSyncMsg("");

    if (!form.model_id.trim() || !form.label.trim()) {
      setSyncMsg("Заполните обязательные поля: model_id и label.");
      setBusyId("");
      return;
    }

    const payload = {
      model_id: form.model_id.trim(),
      label: form.label.trim(),
      is_free: form.is_free,
      input_price: form.input_price.trim() ? Number(form.input_price) : null,
      output_price: form.output_price.trim() ? Number(form.output_price) : null,
      context_window: form.context_window.trim()
        ? Number(form.context_window)
        : null,
      capabilities_json: {},
      tags: form.tags_csv
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
    };

    try {
      await api(`/providers/${providerId}/models`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await load();
      setManualByProvider((prev) => ({ ...prev, [providerId]: emptyManualForm }));
      setSyncMsg("Модель добавлена. Она появится в Model Selector на шагах проекта.");
    } catch (err) {
      setSyncMsg(`Не удалось добавить модель: ${String(err)}`);
    } finally {
      setBusyId("");
    }
  }

  function applyPresetToForm(p: Provider) {
    const caps = p.capabilities_json || {};
    setForm((prev) => ({
      ...prev,
      provider_type: p.type,
      provider_name: p.name,
      base_url: p.base_url,
      structured_output: Boolean((caps as any)["structured_output"] ?? true),
      vision: Boolean((caps as any)["vision"] ?? false),
      russian_friendly: Boolean((caps as any)["russian_friendly"] ?? false),
      api_key: "",
    }));
  }

  async function addUserModel(e: FormEvent) {
    e.preventDefault();
    setSyncMsg("");
    setTestByModelId((prev) => prev); // keep shape

    if (!form.provider_name.trim() || !form.base_url.trim() || !form.provider_type.trim()) {
      setSyncMsg("Заполните поля провайдера: provider_name, provider_type, base_url.");
      return;
    }
    if (!form.label.trim() || !form.model_id.trim()) {
      setSyncMsg("Заполните поля модели: label и model_id.");
      return;
    }
    if (!form.api_key.trim()) {
      setSyncMsg("Введите API-ключ (BYOK) для этой модели.");
      return;
    }

    setBusyId("add");
    try {
      await api("/user-models", {
        method: "POST",
        body: JSON.stringify({
          label: form.label.trim(),
          provider_type: form.provider_type.trim(),
          provider_name: form.provider_name.trim(),
          base_url: form.base_url.trim(),
          capabilities_json: {
            structured_output: form.structured_output,
            vision: form.vision,
            russian_friendly: form.russian_friendly,
          },
          model_id: form.model_id.trim(),
          api_key: form.api_key,
          is_free: form.is_free,
          tags: [],
        }),
      });

      await load();
      setSyncMsg("Модель добавлена. Теперь она доступна для выбора на шагах проекта.");
      setForm((prev) => ({
        ...prev,
        api_key: "",
        model_id: "",
        label: "",
        is_free: false,
      }));
      setProviderChoice((prev) => prev);
    } catch (err) {
      setSyncMsg(`Не удалось добавить модель: ${String(err)}`);
    } finally {
      setBusyId("");
    }
  }

  async function testUserModel(userModelId: string) {
    setBusyId(userModelId);
    try {
      const res = await api<{
        ok: boolean;
        provider: string;
        hint: string;
      }>(`/user-models/${userModelId}/test`, { method: "POST" });

      setTestByModelId((prev) => ({
        ...prev,
        [userModelId]: { ok: res.ok, hint: res.hint, provider: res.provider },
      }));
    } catch (err) {
      setTestByModelId((prev) => ({
        ...prev,
        [userModelId]: { ok: false, hint: String(err), provider: "" },
      }));
    } finally {
      setBusyId("");
    }
  }

  // New UX: user-owned models list + add form (BYOK per model connection).
  // The legacy UI below remains in the file but is unreachable.
  if (true) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Модели</h1>
          <p className="mt-2 max-w-3xl text-sm text-neutral-600 dark:text-neutral-300">
            Добавьте модель с вашим BYOK. Сервер хранит поля подключения и позволяет
            проверить работоспособность кнопкой Test.
          </p>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="panel space-y-3">
            <h2 className="text-lg font-semibold">Ваши добавленные модели</h2>
            {models.length === 0 ? (
              <p className="text-sm text-neutral-500">Пока нет моделей. Добавьте справа.</p>
            ) : (
              <ul className="space-y-2">
                {models.map((m) => {
                  const tr = testByModelId[m.id];
                  return (
                    <li
                      key={m.id}
                      className="rounded-lg border border-neutral-200 p-3 dark:border-neutral-700"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <div className="font-medium">
                            {(m.provider_name ? `${m.provider_name}: ` : "") + m.label}
                          </div>
                          <div className="font-mono text-xs text-neutral-500">{m.model_id}</div>
                          {m.is_free ? (
                            <div className="mt-1 inline-flex rounded bg-emerald-50 px-2 py-0.5 text-xs text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200">
                              free
                            </div>
                          ) : null}
                        </div>
                        <div className="flex flex-col items-end gap-1">
                          <button
                            className="btn-ghost"
                            disabled={busyId === m.id}
                            onClick={() => testUserModel(m.id)}
                          >
                            {busyId === m.id ? "Testing…" : "Test"}
                          </button>
                        </div>
                      </div>
                      {tr ? (
                        <p
                          className={`mt-2 text-sm ${
                            tr.ok
                              ? "text-emerald-700 dark:text-emerald-200"
                              : "text-amber-700 dark:text-amber-200"
                          }`}
                        >
                          <strong>{tr.ok ? "OK" : "FAIL"}:</strong> {tr.hint}
                        </p>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}

            {syncMsg ? (
              <p className="rounded-lg bg-neutral-50 px-3 py-2 text-sm dark:bg-neutral-800">
                {syncMsg}
              </p>
            ) : null}
          </div>

          <form onSubmit={addUserModel} className="panel space-y-3">
            <h2 className="text-lg font-semibold">Добавить модель</h2>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-1">
                <label className="label">Провайдер</label>
                <select
                  className="input"
                  value={providerChoice}
                  onChange={(e) => {
                    const id = e.target.value;
                    setProviderChoice(id);
                    if (id === "custom") {
                      setForm((prev) => ({
                        ...prev,
                        provider_type: "openai_compatible",
                        provider_name: "",
                        base_url: "",
                        structured_output: true,
                        vision: false,
                        russian_friendly: false,
                        api_key: "",
                      }));
                    } else {
                      const p = providers.find((pp) => pp.id === id);
                      if (p) applyPresetToForm(p);
                    }
                  }}
                >
                  <option value="">Выберите готовый провайдер</option>
                  {providers.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                  <option value="custom">Custom (заполню вручную)</option>
                </select>
              </div>

              <div className="space-y-1">
                <label className="label">is_free</label>
                <select
                  className="input"
                  value={form.is_free ? "yes" : "no"}
                  onChange={(e) => setForm((prev) => ({ ...prev, is_free: e.target.value === "yes" }))}
                >
                  <option value="no">paid/не знаю</option>
                  <option value="yes">free</option>
                </select>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <label className="label">provider_name</label>
                <input
                  className="input"
                  value={form.provider_name}
                  onChange={(e) => setForm((prev) => ({ ...prev, provider_name: e.target.value }))}
                />
              </div>
              <div>
                <label className="label">provider_type</label>
                <input
                  className="input"
                  value={form.provider_type}
                  onChange={(e) => setForm((prev) => ({ ...prev, provider_type: e.target.value }))}
                />
              </div>
            </div>

            <div>
              <label className="label">base_url</label>
              <input
                className="input"
                value={form.base_url}
                onChange={(e) => setForm((prev) => ({ ...prev, base_url: e.target.value }))}
                placeholder="https://.../v1"
              />
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={form.structured_output}
                  onChange={(e) => setForm((prev) => ({ ...prev, structured_output: e.target.checked }))}
                />
                <span className="text-sm">structured_output</span>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={form.vision}
                  onChange={(e) => setForm((prev) => ({ ...prev, vision: e.target.checked }))}
                />
                <span className="text-sm">vision</span>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={form.russian_friendly}
                  onChange={(e) =>
                    setForm((prev) => ({ ...prev, russian_friendly: e.target.checked }))
                  }
                />
                <span className="text-sm">russian_friendly</span>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <label className="label">label</label>
                <input
                  className="input"
                  required
                  value={form.label}
                  onChange={(e) => setForm((prev) => ({ ...prev, label: e.target.value }))}
                />
              </div>
              <div>
                <label className="label">model_id</label>
                <input
                  className="input"
                  required
                  value={form.model_id}
                  onChange={(e) => setForm((prev) => ({ ...prev, model_id: e.target.value }))}
                />
              </div>
            </div>

            <div>
              <label className="label">API key (BYOK)</label>
              <input
                className="input"
                type="password"
                required
                value={form.api_key}
                onChange={(e) => setForm((prev) => ({ ...prev, api_key: e.target.value }))}
                placeholder="API key"
              />
            </div>

            <button className="btn-primary" type="submit" disabled={busyId === "add"}>
              {busyId === "add" ? "Saving…" : "Добавить модель"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Модели и провайдеры</h1>
        <p className="mt-2 max-w-3xl text-sm text-neutral-600 dark:text-neutral-300">
          Здесь подключаются внешние ИИ-сервисы. Вы добавляете свой API-ключ (BYOK), обновляете
          список моделей и выбираете их на шагах пайплайна. Пока ключей нет — генерация идёт в
          демо-режиме (mock), это ожидаемо.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="panel space-y-3">
          <h2 className="text-lg font-semibold">Провайдеры</h2>
          <p className="text-xs text-neutral-500">
            <strong>Обновить модели</strong> — запросить актуальный каталог у провайдера.{" "}
            <strong>Проверить ключ</strong> — убедиться, что сохранённый/env ключ работает.
          </p>
          {providers.map((p) => (
            <div
              key={p.id}
              className="space-y-2 rounded-lg border border-neutral-200 p-3 dark:border-neutral-700"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-medium">{p.name}</p>
                  <p className="text-xs text-neutral-500">
                    {PROVIDER_HELP[p.type] || "OpenAI-совместимый шлюз."}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-neutral-400">{p.base_url}</p>
                </div>
                <div className="flex gap-2">
                  <button
                    className="btn-ghost"
                    disabled={busyId === p.id}
                    onClick={() => sync(p.id, p.name)}
                    title="Скачать/обновить список моделей этого провайдера"
                  >
                    Обновить модели
                  </button>
                  <button
                    className="btn-ghost"
                    disabled={busyId === p.id}
                    onClick={() => test(p.id, p.name)}
                    title="Проверить, что API-ключ работает"
                  >
                    Проверить ключ
                  </button>
                </div>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-semibold">Ваши модели</p>
                {models.filter((m) => m.provider_id === p.id).length ? (
                  <ul className="space-y-1 text-sm">
                    {models
                      .filter((m) => m.provider_id === p.id)
                      .map((m) => (
                        <li
                          key={m.id}
                          className="rounded-md border border-neutral-200 px-2 py-1 dark:border-neutral-700"
                        >
                          <div className="font-medium">{m.label}</div>
                          <div className="font-mono text-xs text-neutral-500">{m.model_id}</div>
                          {m.is_free ? (
                            <div className="mt-1 inline-flex rounded bg-emerald-50 px-2 py-0.5 text-xs text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200">
                              free
                            </div>
                          ) : null}
                        </li>
                      ))}
                  </ul>
                ) : (
                  <p className="text-sm text-neutral-500">Пока нет добавленных моделей.</p>
                )}
              </div>

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  addModelManual(p.id);
                }}
                className="space-y-2 rounded-lg bg-neutral-50 p-3 dark:bg-neutral-800"
              >
                <p className="text-sm font-semibold">Add model manually</p>

                <div className="grid gap-3 md:grid-cols-2">
                  <div>
                    <label className="label">model_id</label>
                    <input
                      className="input"
                      required
                      value={getManual(p.id).model_id}
                      onChange={(e) =>
                        setManualByProvider((prev) => ({
                          ...prev,
                          [p.id]: { ...getManual(p.id), model_id: e.target.value },
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="label">label</label>
                    <input
                      className="input"
                      required
                      value={getManual(p.id).label}
                      onChange={(e) =>
                        setManualByProvider((prev) => ({
                          ...prev,
                          [p.id]: { ...getManual(p.id), label: e.target.value },
                        }))
                      }
                    />
                  </div>
                </div>

                <div className="grid gap-3 md:grid-cols-2">
                  <div>
                    <label className="label">is_free</label>
                    <select
                      className="input"
                      value={getManual(p.id).is_free ? "yes" : "no"}
                      onChange={(e) =>
                        setManualByProvider((prev) => ({
                          ...prev,
                          [p.id]: {
                            ...getManual(p.id),
                            is_free: e.target.value === "yes",
                          },
                        }))
                      }
                    >
                      <option value="no">paid/не знаю</option>
                      <option value="yes">free</option>
                    </select>
                  </div>
                  <div>
                    <label className="label">tags (через запятую)</label>
                    <input
                      className="input"
                      value={getManual(p.id).tags_csv}
                      onChange={(e) =>
                        setManualByProvider((prev) => ({
                          ...prev,
                          [p.id]: { ...getManual(p.id), tags_csv: e.target.value },
                        }))
                      }
                      placeholder="structured-output, russian-friendly"
                    />
                  </div>
                </div>

                <div className="grid gap-3 md:grid-cols-3">
                  <div>
                    <label className="label">input_price</label>
                    <input
                      className="input"
                      value={getManual(p.id).input_price}
                      onChange={(e) =>
                        setManualByProvider((prev) => ({
                          ...prev,
                          [p.id]: { ...getManual(p.id), input_price: e.target.value },
                        }))
                      }
                      placeholder="0"
                    />
                  </div>
                  <div>
                    <label className="label">output_price</label>
                    <input
                      className="input"
                      value={getManual(p.id).output_price}
                      onChange={(e) =>
                        setManualByProvider((prev) => ({
                          ...prev,
                          [p.id]: { ...getManual(p.id), output_price: e.target.value },
                        }))
                      }
                      placeholder="0"
                    />
                  </div>
                  <div>
                    <label className="label">context_window</label>
                    <input
                      className="input"
                      value={getManual(p.id).context_window}
                      onChange={(e) =>
                        setManualByProvider((prev) => ({
                          ...prev,
                          [p.id]: {
                            ...getManual(p.id),
                            context_window: e.target.value,
                          },
                        }))
                      }
                      placeholder="128000"
                    />
                  </div>
                </div>

                <button className="btn-primary" type="submit" disabled={busyId === p.id}>
                  Добавить модель
                </button>
              </form>
            </div>
          ))}
          {syncMsg && (
            <p className="rounded-lg bg-neutral-50 px-3 py-2 text-sm dark:bg-neutral-800">
              {syncMsg}
            </p>
          )}
          {testResult && (
            <p
              className={`rounded-lg px-3 py-2 text-sm ${
                testResult!.ok
                  ? "bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100"
                  : "bg-amber-50 text-amber-950 dark:bg-amber-950 dark:text-amber-100"
              }`}
            >
              <strong>
                {testResult!.provider}: {testResult!.ok ? "OK" : "FAIL"}
              </strong>
              <br />
              {testResult!.hint}
            </p>
          )}
        </div>

        <form onSubmit={saveKey} className="panel space-y-3">
          <h2 className="text-lg font-semibold">Добавить свой API-ключ (BYOK)</h2>
          <p className="text-xs text-neutral-500">
            Ключ хранится зашифрованным. Списание идёт на стороне вашего провайдера.
          </p>
          <select
            className="input"
            required
            value={cred.provider_id}
            onChange={(e) => setCred({ ...cred, provider_id: e.target.value })}
          >
            <option value="">Выберите провайдера</option>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <input
            className="input"
            type="password"
            required
            placeholder="API key"
            value={cred.api_key}
            onChange={(e) => setCred({ ...cred, api_key: e.target.value })}
          />
          <input
            className="input"
            placeholder="Подпись ключа (например: рабочий OpenRouter)"
            value={cred.label}
            onChange={(e) => setCred({ ...cred, label: e.target.value })}
          />
          <button className="btn-primary" type="submit">
            Сохранить ключ
          </button>
        </form>
      </div>
    </div>
  );
}
