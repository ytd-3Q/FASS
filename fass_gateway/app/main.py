from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routers.openai_compat import router as openai_compat_router
from .routers.chat_api import router as chat_api_router
from .routers.memory_api import router as memory_api_router
from .routers.plugins_api import router as plugins_api_router
from .routers.settings_api import router as settings_api_router
from .routers.tasks_api import router as tasks_api_router
from .routers.timeline_api import router as timeline_api_router
from .routers.control_api import router as control_api_router
from .routers.mcp_api import router as mcp_api_router
from .routers.automations_api import router as automations_api_router
from .routers.trace_api import router as trace_api_router
from .routers.config_api import router as config_api_router
from .routers.models_api import router as models_api_router
from .routers.legacy_ollama_api import router as legacy_ollama_api_router
from .services.task_runner import runner
from .services.provider_registry import registry
from .services.model_registry import model_registry
from .services.mcp_loader import load_builtin_tools
from .services.self_heal import backup as self_heal_backup
from .services.self_heal import integrity_check as self_heal_integrity_check
from .services.self_heal import rollback_latest as self_heal_rollback_latest


app = FastAPI(title="FASS Gateway", version="0.1.0")
app.include_router(openai_compat_router)
app.include_router(chat_api_router)
app.include_router(memory_api_router)
app.include_router(plugins_api_router)
app.include_router(settings_api_router)
app.include_router(tasks_api_router)
app.include_router(timeline_api_router)
app.include_router(control_api_router)
app.include_router(mcp_api_router)
app.include_router(automations_api_router)
app.include_router(trace_api_router)
app.include_router(config_api_router)
app.include_router(models_api_router)
app.include_router(legacy_ollama_api_router)


@app.on_event("startup")
async def _startup() -> None:
    try:
        self_heal_backup(actor="startup", reason="startup")
        check = self_heal_integrity_check()
        if not check.get("ok"):
            self_heal_rollback_latest(actor="startup")
    except Exception:
        pass
    registry.load()
    model_registry.load()
    load_builtin_tools()
    runner.start()


@app.on_event("shutdown")
async def _shutdown() -> None:
    await runner.stop()

webui_dir = Path(__file__).resolve().parents[2] / "webui"
webui_dist_dir = webui_dir / "dist"
app.mount("/", StaticFiles(directory=str(webui_dist_dir if webui_dist_dir.exists() else webui_dir), html=True), name="webui")

