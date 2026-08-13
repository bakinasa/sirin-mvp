# Architecture overview

## Services

- `web` — React SPA (Vite)
- `api` — FastAPI REST API
- `worker` — polls queued AI runs
- `db` — PostgreSQL
- `redis` — reserved for queue/cache
- `minio` — object storage for attachments (future wiring)
- `proxy` — nginx on port 8080

## Human-in-the-loop

Each `PipelineStep` has status. AI run for step N requires step N-1 to be `approved` or `locked`.

## Prompt layers

1. System template (versioned)
2. Auto context bundle (approved artifacts + DATA boundary)
3. Operator prompt (editable)
4. Output JSON schema
