from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Cooking Copilot MVP API", version="0.2.0")


class SeasoningRequest(BaseModel):
    base_amount: float = Field(..., gt=0, description="基准调料量 B")
    base_main_weight: float = Field(..., gt=0, description="基准主食材量 W0(g)")
    actual_main_weight: float = Field(..., gt=0, description="实际主食材量 W(g)")
    base_servings: int = Field(..., gt=0, description="基准份数")
    actual_servings: int = Field(..., gt=0, description="实际份数")
    flavor_level: str = Field("normal", description="light/normal/heavy")
    cooking_method: str = Field("stir_fry", description="stir_fry/fry/stew")
    alpha: float = Field(0.9, ge=0.85, le=1.0, description="缩放指数 α")
    min_amount: float = Field(0.0, ge=0)
    max_amount: float = Field(9999.0, gt=0)


class SeasoningResponse(BaseModel):
    recommended_amount: float
    applied_flavor_factor: float
    applied_cooking_factor: float
    note: str


class StartSessionRequest(BaseModel):
    recipe_id: str
    servings: int = Field(..., gt=0)
    flavor_level: Literal["light", "normal", "heavy"] = "normal"


FLAVOR_FACTOR = {
    "light": 0.9,
    "normal": 1.0,
    "heavy": 1.1,
}

COOKING_FACTOR = {
    "fry": 1.05,
    "stir_fry": 1.0,
    "stew": 0.95,
}

RECIPES = {
    "kung_pao_chicken": {
        "id": "kung_pao_chicken",
        "name": "宫保鸡丁",
        "difficulty": 2,
        "default_servings": 2,
        "steps": [
            "鸡胸肉切丁，加少许盐和淀粉抓匀腌制10分钟",
            "调碗汁：生抽、醋、糖、淀粉和水混合",
            "热锅冷油，下鸡丁滑炒至变色后盛出",
            "下干辣椒和花椒爆香，回锅鸡丁翻炒",
            "倒入碗汁收汁，最后下花生米翻匀出锅",
        ],
    },
    "tomato_egg": {
        "id": "tomato_egg",
        "name": "番茄炒蛋",
        "difficulty": 1,
        "default_servings": 2,
        "steps": [
            "鸡蛋打散，加少许盐",
            "番茄切块，热锅炒蛋后盛出",
            "番茄下锅炒出汁，回锅鸡蛋翻炒",
            "加盐和少许糖调味，收汁出锅",
        ],
    },
}

SESSIONS: dict[str, dict] = {}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/recipes")
def list_recipes() -> list[dict]:
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "difficulty": r["difficulty"],
            "default_servings": r["default_servings"],
            "step_count": len(r["steps"]),
        }
        for r in RECIPES.values()
    ]


@app.get("/recipes/{recipe_id}")
def get_recipe(recipe_id: str) -> dict:
    recipe = RECIPES.get(recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="recipe not found")
    return recipe


@app.post("/sessions/start")
def start_session(payload: StartSessionRequest) -> dict:
    recipe = RECIPES.get(payload.recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="recipe not found")

    session_id = str(uuid4())
    SESSIONS[session_id] = {
        "session_id": session_id,
        "recipe_id": recipe["id"],
        "recipe_name": recipe["name"],
        "servings": payload.servings,
        "flavor_level": payload.flavor_level,
        "current_step_index": 0,
        "total_steps": len(recipe["steps"]),
        "status": "running",
    }

    return {
        **SESSIONS[session_id],
        "current_step_text": recipe["steps"][0],
    }


@app.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    recipe = RECIPES[session["recipe_id"]]
    step_idx = session["current_step_index"]
    step_text = recipe["steps"][step_idx] if session["status"] == "running" else "已完成全部步骤"
    return {**session, "current_step_text": step_text}


@app.post("/sessions/{session_id}/next")
def next_step(session_id: str) -> dict:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    if session["status"] == "completed":
        return {**session, "current_step_text": "已完成全部步骤"}

    recipe = RECIPES[session["recipe_id"]]
    session["current_step_index"] += 1

    if session["current_step_index"] >= session["total_steps"]:
        session["current_step_index"] = session["total_steps"] - 1
        session["status"] = "completed"
        return {**session, "current_step_text": "已完成全部步骤"}

    return {
        **session,
        "current_step_text": recipe["steps"][session["current_step_index"]],
    }


@app.post("/seasoning/calculate", response_model=SeasoningResponse)
def calculate_seasoning(payload: SeasoningRequest) -> SeasoningResponse:
    if payload.flavor_level not in FLAVOR_FACTOR:
        raise HTTPException(status_code=400, detail="flavor_level must be one of: light/normal/heavy")
    if payload.cooking_method not in COOKING_FACTOR:
        raise HTTPException(status_code=400, detail="cooking_method must be one of: fry/stir_fry/stew")
    if payload.min_amount > payload.max_amount:
        raise HTTPException(status_code=400, detail="min_amount cannot be greater than max_amount")

    sf = payload.actual_servings / payload.base_servings
    tf = FLAVOR_FACTOR[payload.flavor_level]
    cf = COOKING_FACTOR[payload.cooking_method]

    raw = payload.base_amount * (payload.actual_main_weight / payload.base_main_weight) ** payload.alpha * sf * tf * cf
    clamped = max(payload.min_amount, min(raw, payload.max_amount))

    note = "normal"
    if clamped == payload.min_amount and raw < payload.min_amount:
        note = "clamped_to_min"
    elif clamped == payload.max_amount and raw > payload.max_amount:
        note = "clamped_to_max"

    return SeasoningResponse(
        recommended_amount=round(clamped, 2),
        applied_flavor_factor=tf,
        applied_cooking_factor=cf,
        note=note,
    )
