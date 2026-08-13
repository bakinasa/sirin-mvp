# AI Studio 360

Human-in-the-loop веб-студия для ускорения пайплайна 360°-тренажёрных модулей.

## Быстрый старт

```bash
cp .env.example .env
docker compose up --build
```

Откройте [http://localhost:8080](http://localhost:8080)

Логин по умолчанию (из seed):

- email: `admin@aistudio.local`
- password: `admin123`

## Что внутри

| Сервис | Назначение |
|--------|------------|
| `web` | React + Vite + Tailwind UI |
| `api` | FastAPI + SQLAlchemy + Alembic |
| `worker` | Фоновый опрос queued AI runs |
| `db` | PostgreSQL |
| `redis` | Кэш / очередь (зарезервирован) |
| `minio` | Файловое хранилище |
| `proxy` | Nginx `:8080` → web + `/api` |

## Пайплайн

1. Project → Brief (approve)
2. Draft TZ (AI → edit → approve)
3. Expert feedback (human → approve)
4. Expert synthesis (AI → approve)
5. Final TZ (AI → approve)
6. Scene breakdown (AI → approve)
7. Production planning (AI → approve)
8. Storyboard (AI → approve)
9. Export (markdown / json / text bundle)

Следующий AI-шаг **нельзя** запустить, пока предыдущий не в статусе `approved`.

## Промты (3 слоя)

1. **System template** — версионируется на backend (`/prompt-templates`)
2. **Context bundle** — только approved-артефакты + DATA boundary
3. **Operator prompt** — редактируемый на каждом шаге

Сборка: `System + Context + Operator + Output Schema`.

## Модели и BYOK

Раздел **Models & Providers**:

- пресеты OpenRouter / Hubris / TsarRouter / OpenAI-compatible / Yandex / GigaChat
- sync каталога моделей
- encrypted BYOK keys
- primary + fallback на шаге
- без ключа работает **mock generator** (удобно для демо)

## Структура

```text
apps/web          — frontend
apps/api          — backend
apps/worker       — worker
packages/shared-types
docs/prompts
docs/architecture
infra/nginx
docker-compose.yml
```

## Как добавить pipeline step

1. Добавьте `StepType` в `apps/api/app/domain/enums.py` и `PIPELINE_ORDER`
2. Добавьте system template + operator preset в `apps/api/app/seed.py`
3. Добавьте output schema в `prompt_assembler.OUTPUT_SCHEMAS`
4. Добавьте маршрут на фронте (или используйте `PipelineStudioPage`)

## Как добавить провайдер

1. Пресет в `apps/api/app/llm/registry.py`
2. Адаптер через `OpenAICompatibleProvider` (или новый класс по протоколу `LLMProvider`)
3. Sync через `POST/GET /providers/{id}/models/sync`

## Make

```bash
make up      # docker compose up --build
make down
make logs
make reset  # down -v && up --build
```
