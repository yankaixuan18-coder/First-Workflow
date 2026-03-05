# AI 做饭助手（Cooking Copilot）- 可运行 MVP（继续版）

你说“那你继续”，我已经把后端从“只有调料计算”升级到“**可选菜 + 可开始做菜会话 + 可推进步骤**”。

## 这版新增了什么

- `GET /recipes`：获取可做菜列表。
- `GET /recipes/{recipe_id}`：获取某道菜详情和步骤。
- `POST /sessions/start`：开始一次做菜会话。
- `POST /sessions/{session_id}/next`：推进到下一步。
- `GET /sessions/{session_id}`：查看当前会话状态。
- 保留 `POST /seasoning/calculate`：调料动态换算。

## 快速启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

打开：`http://127.0.0.1:8000/docs`

## 先这样体验一遍（3 分钟）

### 1) 看菜谱

```bash
curl http://127.0.0.1:8000/recipes
```

### 2) 开始会话（以番茄炒蛋为例）

```bash
curl -X POST 'http://127.0.0.1:8000/sessions/start' \
  -H 'Content-Type: application/json' \
  -d '{"recipe_id":"tomato_egg","servings":2,"flavor_level":"normal"}'
```

记下返回中的 `session_id`。

### 3) 推进下一步

```bash
curl -X POST 'http://127.0.0.1:8000/sessions/<session_id>/next'
```

连续调用几次，会变成 `status=completed`。

### 4) 调料换算

```bash
curl -X POST 'http://127.0.0.1:8000/seasoning/calculate' \
  -H 'Content-Type: application/json' \
  -d '{
    "base_amount": 3,
    "base_main_weight": 300,
    "actual_main_weight": 450,
    "base_servings": 2,
    "actual_servings": 2,
    "flavor_level": "light",
    "cooking_method": "stir_fry",
    "alpha": 0.9,
    "min_amount": 0,
    "max_amount": 10
  }'
```

## 你现在只要做这 1 件事

把你想优先支持的 **10 道菜名** 发给我。  
我下一步直接给你：
1. 10 道菜的标准化步骤（可直接入库）
2. 每道菜调料基准参数（可直接喂给 `/seasoning/calculate`）
3. 批量导入脚本（初始化数据）
