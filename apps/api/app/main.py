"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, experts, exports, pipeline, projects, prompts, providers, sources, studio


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="AI Studio 360",
    description="Human-in-the-loop studio for 360° training module pipelines",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(experts.router)
app.include_router(pipeline.router)
app.include_router(providers.router)
app.include_router(prompts.router)
app.include_router(exports.router)
app.include_router(sources.router)
app.include_router(studio.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-studio-360-api"}
