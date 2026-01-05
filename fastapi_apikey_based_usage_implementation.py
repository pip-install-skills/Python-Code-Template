from __future__ import annotations

import os
import hmac
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict

from fastapi import FastAPI, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId


# ----------------------------
# Settings
# ----------------------------

class Settings(BaseSettings):
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "app"
    API_KEY_HMAC_SECRET: str = "change-me-in-env"  # put in env in real life

    class Config:
        env_file = ".env"


settings = Settings()


# ----------------------------
# Mongo setup
# ----------------------------

client = AsyncIOMotorClient(settings.MONGODB_URI)
db = client[settings.MONGODB_DB]
api_keys_col = db["api_keys"]


# ----------------------------
# Helpers
# ----------------------------

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def current_month_utc(dt: Optional[datetime] = None) -> str:
    d = dt or utc_now()
    return d.strftime("%Y-%m")  # e.g. "2026-01"

def hash_api_key(raw_key: str) -> str:
    """
    HMAC-hash the API key so DB compromise doesn't leak live keys.
    """
    secret = settings.API_KEY_HMAC_SECRET.encode("utf-8")
    msg = raw_key.encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()

def generate_api_key() -> str:
    """
    Return a random API key. Store only its HMAC hash.
    """
    # token_urlsafe gives URL-safe base64-ish string
    return secrets.token_urlsafe(32)

def key_prefix(raw_key: str, n: int = 8) -> str:
    return raw_key[:n]


# ----------------------------
# Pydantic models
# ----------------------------

class CreateKeyRequest(BaseModel):
    user_id: str = Field(..., description="Owner identifier (string is fine, can be ObjectId etc.)")
    name: str = Field(default="default", description="Human label for the key")
    monthly_limit: int = Field(default=1000, ge=1, description="Monthly request quota")
    scopes: List[str] = Field(default_factory=list, description="Optional permissions/scopes")
    active: bool = True

class CreateKeyResponse(BaseModel):
    api_key: str
    key_id: str
    prefix: str
    monthly_limit: int
    scopes: List[str]

class KeyPublic(BaseModel):
    key_id: str
    user_id: str
    name: str
    prefix: str
    monthly_limit: int
    scopes: List[str]
    active: bool
    usage_month: str
    usage_count: int
    created_at: datetime
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


class ApiKeyContext(BaseModel):
    key_id: str
    user_id: str
    scopes: List[str]
    monthly_limit: int
    usage_month: str
    usage_count: int


# ----------------------------
# FastAPI app
# ----------------------------

app = FastAPI(title="API Key Auth with Monthly Quota (MongoDB)")


@app.on_event("startup")
async def ensure_indexes() -> None:
    # Unique on hash so you can't insert duplicates
    await api_keys_col.create_index([("key_hash", 1)], unique=True)
    # Helpful for lookups / admin listing
    await api_keys_col.create_index([("user_id", 1), ("active", 1)])
    await api_keys_col.create_index([("prefix", 1)])


# ----------------------------
# Admin endpoints (example)
# In real systems, protect these with admin auth.
# ----------------------------

@app.post("/admin/keys", response_model=CreateKeyResponse)
async def admin_create_key(req: CreateKeyRequest) -> CreateKeyResponse:
    raw = generate_api_key()
    doc = {
        "user_id": req.user_id,
        "name": req.name,
        "key_hash": hash_api_key(raw),
        "prefix": key_prefix(raw),
        "monthly_limit": req.monthly_limit,
        "scopes": req.scopes,
        "active": req.active,
        "usage_month": current_month_utc(),
        "usage_count": 0,
        "created_at": utc_now(),
        "last_used_at": None,
        "revoked_at": None,
    }

    try:
        result = await api_keys_col.insert_one(doc)
    except Exception as e:
        # Extremely unlikely unless collision; still handle gracefully
        raise HTTPException(status_code=500, detail="Failed to create key") from e

    return CreateKeyResponse(
        api_key=raw,  # show once; client must store it
        key_id=str(result.inserted_id),
        prefix=doc["prefix"],
        monthly_limit=req.monthly_limit,
        scopes=req.scopes,
    )


@app.get("/admin/keys/{user_id}", response_model=List[KeyPublic])
async def admin_list_keys(user_id: str) -> List[KeyPublic]:
    out: List[KeyPublic] = []
    async for d in api_keys_col.find({"user_id": user_id}).sort("created_at", -1):
        out.append(
            KeyPublic(
                key_id=str(d["_id"]),
                user_id=d["user_id"],
                name=d.get("name", "default"),
                prefix=d.get("prefix", ""),
                monthly_limit=d.get("monthly_limit", 0),
                scopes=d.get("scopes", []),
                active=bool(d.get("active", False)),
                usage_month=d.get("usage_month", ""),
                usage_count=int(d.get("usage_count", 0)),
                created_at=d.get("created_at"),
                last_used_at=d.get("last_used_at"),
                revoked_at=d.get("revoked_at"),
            )
        )
    return out


@app.post("/admin/keys/{key_id}/revoke")
async def admin_revoke_key(key_id: str) -> Dict[str, Any]:
    try:
        oid = ObjectId(key_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid key_id")

    res = await api_keys_col.update_one(
        {"_id": oid, "active": True},
        {"$set": {"active": False, "revoked_at": utc_now()}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Key not found or already inactive")
    return {"ok": True}


# ----------------------------
# Auth dependency (the important bit)
# ----------------------------

async def require_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> ApiKeyContext:
    """
    Validate key, enforce monthly quota, and increment usage atomically.
    """
    if not x_api_key or len(x_api_key) < 10:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing/invalid API key")

    h = hash_api_key(x_api_key)
    month = current_month_utc()

    # Atomic quota enforcement using an update pipeline on the key document.
    #
    # Stage 1: reset usage if month changed
    # Stage 2: compute 'allowed' (usage_count < monthly_limit) and increment only if allowed
    # Stage 3: set last_used_at only if allowed
    #
    # We keep "allowed" as a transient field and $unset it at the end.
    pipeline = [
        {
            "$set": {
                "usage_count": {
                    "$cond": [
                        {"$ne": ["$usage_month", month]},
                        0,
                        "$usage_count",
                    ]
                },
                "usage_month": month,
            }
        },
        {
            "$set": {
                "allowed": {"$lt": ["$usage_count", "$monthly_limit"]},
                "usage_count": {
                    "$cond": [
                        {"$lt": ["$usage_count", "$monthly_limit"]},
                        {"$add": ["$usage_count", 1]},
                        "$usage_count",
                    ]
                },
                "last_used_at": {
                    "$cond": [
                        {"$lt": ["$usage_count", "$monthly_limit"]},
                        "$$NOW",
                        "$last_used_at",
                    ]
                },
            }
        },
        {"$unset": "allowed"},
    ]

    # We need to know if allowed or not; easiest is to re-check after update:
    # - If usage_count changed or (usage_count <= limit) etc.
    #
    # But we removed 'allowed'. So we do a small trick:
    # return the doc AFTER update, then decide allowed by verifying:
    # if usage_count <= monthly_limit AND last_used_at == now-ish? Not perfect.
    #
    # Better: don't unset allowed until after we read it. So we run two-step:
    pipeline_with_allowed = pipeline[:-1]  # omit unset for the response

    updated = await api_keys_col.find_one_and_update(
        {"key_hash": h, "active": True},
        pipeline_with_allowed,
        return_document=True,  # After
    )

    if not updated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive API key")

    allowed = bool(updated.get("allowed", False))
    if not allowed:
        # cleanup: remove transient field
        await api_keys_col.update_one({"_id": updated["_id"]}, {"$unset": {"allowed": ""}})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Monthly quota exceeded ({updated.get('monthly_limit')} requests/month).",
        )

    # cleanup: remove transient field
    await api_keys_col.update_one({"_id": updated["_id"]}, {"$unset": {"allowed": ""}})

    return ApiKeyContext(
        key_id=str(updated["_id"]),
        user_id=updated["user_id"],
        scopes=updated.get("scopes", []),
        monthly_limit=int(updated.get("monthly_limit", 0)),
        usage_month=updated.get("usage_month", month),
        usage_count=int(updated.get("usage_count", 0)),
    )


def require_scopes(required: List[str]):
    async def _dep(ctx: ApiKeyContext = Depends(require_api_key)) -> ApiKeyContext:
        have = set(ctx.scopes or [])
        need = set(required)
        if not need.issubset(have):
            raise HTTPException(status_code=403, detail="Insufficient scope")
        return ctx
    return _dep


# ----------------------------
# Example protected resources
# ----------------------------

@app.get("/me")
async def me(ctx: ApiKeyContext = Depends(require_api_key)) -> Dict[str, Any]:
    return {
        "key_id": ctx.key_id,
        "user_id": ctx.user_id,
        "usage": {"month": ctx.usage_month, "count": ctx.usage_count, "limit": ctx.monthly_limit},
        "scopes": ctx.scopes,
    }


@app.get("/premium-data")
async def premium_data(ctx: ApiKeyContext = Depends(require_scopes(["premium:read"]))) -> Dict[str, Any]:
    # Your expensive stuff goes here
    return {"data": ["✨", "sparkly", "premium", "bytes"]}


# ----------------------------
# Run:
# uvicorn main:app --reload
# ----------------------------
