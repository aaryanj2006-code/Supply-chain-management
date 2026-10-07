# AI Supply Chain & Inventory Optimization System

Agentic platform that monitors inventory, forecasts demand, scores supplier risk, retrieves procurement policy (RAG) and recommends actions (reorder, expedite, switch supplier, markdown) with human approval.

**Live demo:** _add your Render URL_ · **API docs:** `/docs`

## Architecture
```
Dashboard (HTML + Chart.js) -> FastAPI REST -> Redis (cache + agent run state)
                                   |
        LangGraph: Monitor -> Demand -> Supplier -> Policy RAG -> Recommender
                                   |
              PostgreSQL (data + policy vector table)
```
The LLM (Groq / OpenAI / Gemini via LangChain) writes the justification for each recommendation. Numbers (forecast, reorder point, EOQ, risk score) are computed deterministically in `app/analytics.py`, so the system still works without an API key.

## Run locally
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # optional: add GROQ_API_KEY etc.
uvicorn app.main:app --reload
```
Open http://localhost:8000 (dashboard) and http://localhost:8000/docs. With no `DATABASE_URL` it uses SQLite; with no `REDIS_URL` it uses an in-memory cache. The database is seeded automatically on first start.

## Tests
`pytest -q`

## Key endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | /health | status, cache backend, LLM enabled |
| GET | /products, /suppliers, /inventory | data + computed metrics |
| GET/POST | /purchase-orders | list / create |
| GET | /analytics/shortage-risk, /overstock, /demand-anomalies, /supplier-risk | analytics |
| GET | /dashboard/summary | cached KPIs |
| POST | /rag/query | policy Q&A |
| POST | /agents/run | start agent workflow (returns run_id) |
| GET | /agents/runs/{id} | run status from Redis |
| GET | /recommendations | agent output |
| POST | /recommendations/{id}/approve or reject | human-in-the-loop; approve creates a PO |

Postman collection: `postman/supply-chain-ai.postman_collection.json`.

## Deploy on Render
1. Push to GitHub. 2. Render > New > Blueprint > select repo (`render.yaml` creates web service, Postgres, Redis). 3. Add `GROQ_API_KEY` (or OPENAI/GOOGLE key) in the web service env. 4. Open the public URL.
