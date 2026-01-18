from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from ..models.control import ControlConfig, ModelAlias, ModelProfile, Provider, ProviderAuth
from ..services.model_registry import model_registry
from ..services.control_store import get_json, set_json
from ..services.provider_registry import registry
from ..services.provider_router import proxy_models_for_provider
from ..services import model_catalog as model_catalog_service
from ..services import matching_engine
from ..services.audit_log import list_logs as list_audit_logs
from ..services.self_heal import (
    daily_tick as self_heal_daily_tick,
    rollback_latest as self_heal_rollback_latest,
    run_full_check as self_heal_run_full_check,
)


router = APIRouter(prefix="/api/control")


def _check_api_key(authorization: str | None) -> None:
    from ..settings import settings

    if not settings.api_key:
        return
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")


def _mask_provider(p: Provider) -> dict:
    d = p.model_dump(mode="json")
    auth = dict(d.get("auth") or {})
    token = auth.get("token")
    auth["has_token"] = bool(token)
    auth["token"] = None
    d["auth"] = auth
    return d


@router.get("/providers")
async def list_providers(authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    cfg = registry.get()
    return {
        "schema_version": cfg.schema_version,
        "default_provider_id": cfg.default_provider_id,
        "providers": [_mask_provider(p) for p in cfg.providers],
        "runtime": {
            p.id: registry.runtime(p.id).model_dump(mode="json")
            for p in cfg.providers
        },
    }


@router.post("/providers")
async def upsert_provider(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    try:
        p = Provider.model_validate(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid provider: {type(e).__name__}")

    cfg = registry.get()
    existing = {x.id: x for x in cfg.providers}
    if p.id in existing:
        old = existing[p.id]
        auth_payload = payload.get("auth") if isinstance(payload, dict) else None
        token_field_present = isinstance(auth_payload, dict) and ("token" in auth_payload)
        if isinstance(p.auth, ProviderAuth) and not token_field_present:
            p.auth.token = old.auth.token
        new_list = [p if x.id == p.id else x for x in cfg.providers]
    else:
        new_list = [*cfg.providers, p]
    default_provider_id = cfg.default_provider_id or p.id
    registry.save(ControlConfig(schema_version=cfg.schema_version, providers=new_list, default_provider_id=default_provider_id))
    return {"ok": True}


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    cfg = registry.get()
    new_list = [p for p in cfg.providers if p.id != provider_id]
    default_provider_id = cfg.default_provider_id
    if default_provider_id == provider_id:
        default_provider_id = new_list[0].id if new_list else None
    registry.save(ControlConfig(schema_version=cfg.schema_version, providers=new_list, default_provider_id=default_provider_id))
    return {"ok": True}


@router.post("/defaults")
async def set_defaults(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    default_provider_id = payload.get("default_provider_id")
    if default_provider_id is not None and not isinstance(default_provider_id, str):
        raise HTTPException(status_code=400, detail="default_provider_id must be a string or null")
    cfg = registry.get()
    old_default_provider_id = cfg.default_provider_id
    if default_provider_id and default_provider_id not in {p.id for p in cfg.providers}:
        raise HTTPException(status_code=400, detail="unknown provider id")
    registry.save(ControlConfig(schema_version=cfg.schema_version, providers=cfg.providers, default_provider_id=default_provider_id))
    sync_result = await model_catalog_service.on_default_provider_changed(old_default_provider_id, default_provider_id, actor="control_api")
    presets = None
    try:
        if isinstance(default_provider_id, str):
            cached = model_catalog_service.list_cached(default_provider_id, status="online", limit=500)
            model_ids = [x.get("model_id") for x in cached if isinstance(x.get("model_id"), str)]
            presets = matching_engine.upsert_layer_presets(provider_id=default_provider_id, models=model_ids, actor="control_api")
    except Exception:
        presets = None
    return {"ok": True, "model_catalog": sync_result, "layer_presets": presets}


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    p = registry.get_provider(provider_id)
    if not p:
        raise HTTPException(status_code=404, detail="provider not found")
    try:
        models = await proxy_models_for_provider(p)
        return {"ok": True, "models_sample": (models.get("data") or [])[:5]}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"test failed: {type(e).__name__}")


@router.get("/providers/{provider_id}/models")
async def list_provider_models(provider_id: str, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    p = registry.get_provider(provider_id)
    if not p:
        raise HTTPException(status_code=404, detail="provider not found")
    models = await proxy_models_for_provider(p)
    r = await model_catalog_service.fetch_and_cache(p, actor="control_api")
    return {"ok": True, "models": models.get("data") or [], "cache": r}


@router.get("/model_catalog")
async def get_model_catalog(provider_id: str, status: str = "online", authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    return {"provider_id": provider_id, "status": status, "items": model_catalog_service.list_cached(provider_id, status=status)}


@router.post("/model_catalog/sync")
async def sync_model_catalog(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    provider_id = payload.get("provider_id")
    if provider_id is None:
        provider_id = registry.get().default_provider_id
    if not isinstance(provider_id, str) or not provider_id:
        raise HTTPException(status_code=400, detail="provider_id required")
    p = registry.get_provider(provider_id)
    if not p:
        raise HTTPException(status_code=404, detail="provider not found")
    r = await model_catalog_service.fetch_and_cache(p, actor="control_api")
    cached = model_catalog_service.list_cached(provider_id, status="online", limit=500)
    model_ids = [x.get("model_id") for x in cached if isinstance(x.get("model_id"), str)]
    presets = matching_engine.upsert_layer_presets(provider_id=provider_id, models=model_ids, actor="control_api")
    return {"ok": True, "cache": r, "layer_presets": presets}


@router.get("/layer_presets")
async def get_layer_presets(authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    return {"items": matching_engine.list_layer_presets()}


@router.get("/audit_logs")
async def get_audit_logs(
    authorization: str | None = Header(default=None),
    since_unix_ms: int | None = None,
    until_unix_ms: int | None = None,
    action: str | None = None,
    limit: int = 200,
) -> dict:
    _check_api_key(authorization)
    return {"items": list_audit_logs(since_unix_ms=since_unix_ms, until_unix_ms=until_unix_ms, action=action, limit=limit, decrypt=False)}


@router.post("/self_heal/daily_tick")
async def run_daily_tick(authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    return self_heal_daily_tick(actor="control_api")


@router.post("/self_heal/rollback_latest")
async def rollback_latest(authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    return self_heal_rollback_latest(actor="control_api")


@router.post("/self_heal/run_full_check")
async def run_full_check(authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    return self_heal_run_full_check(actor="control_api")


@router.get("/models")
async def list_model_aliases(authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    return {"models": [m.model_dump(mode="json") for m in model_registry.list_aliases()]}


@router.post("/models")
async def upsert_model_alias(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    try:
        m = ModelAlias.model_validate(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid model alias: {type(e).__name__}")
    existing = {x.id: x for x in model_registry.list_aliases()}
    models = [m if x.id == m.id else x for x in existing.values()] if m.id in existing else [*existing.values(), m]
    model_registry.save_aliases(models)
    return {"ok": True}


@router.delete("/models/{alias_id}")
async def delete_model_alias(alias_id: str, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    models = [m for m in model_registry.list_aliases() if m.id != alias_id]
    model_registry.save_aliases(models)
    return {"ok": True}


@router.get("/profiles")
async def list_profiles(authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    return {
        "default_profile_id": model_registry.default_profile_id(),
        "profiles": [p.model_dump(mode="json") for p in model_registry.list_profiles()],
    }


@router.post("/profiles")
async def upsert_profile(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    try:
        p = ModelProfile.model_validate(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid profile: {type(e).__name__}")
    existing = {x.id: x for x in model_registry.list_profiles()}
    profiles = [p if x.id == p.id else x for x in existing.values()] if p.id in existing else [*existing.values(), p]
    default_profile_id = model_registry.default_profile_id() or p.id
    model_registry.save_profiles(profiles, default_profile_id=default_profile_id)
    return {"ok": True}


@router.post("/profiles/default")
async def set_default_profile(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    default_profile_id = payload.get("default_profile_id")
    if default_profile_id is not None and not isinstance(default_profile_id, str):
        raise HTTPException(status_code=400, detail="default_profile_id must be a string or null")
    if default_profile_id and not model_registry.get_profile(default_profile_id):
        raise HTTPException(status_code=400, detail="unknown profile id")
    model_registry.save_profiles(model_registry.list_profiles(), default_profile_id=default_profile_id)
    return {"ok": True}


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    profiles = [p for p in model_registry.list_profiles() if p.id != profile_id]
    default_profile_id = model_registry.default_profile_id()
    if default_profile_id == profile_id:
        default_profile_id = profiles[0].id if profiles else None
    model_registry.save_profiles(profiles, default_profile_id=default_profile_id)
    return {"ok": True}


@router.get("/websearch")
async def get_websearch(authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    v = get_json("web.searxng_base_url")
    return {"searxng_base_url": v if isinstance(v, str) else None}


@router.post("/websearch")
async def set_websearch(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    v = payload.get("searxng_base_url")
    if v is not None and not isinstance(v, str):
        raise HTTPException(status_code=400, detail="searxng_base_url must be a string or null")
    set_json("web.searxng_base_url", v)
    return {"ok": True}
