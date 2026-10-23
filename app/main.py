import os, uuid
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from .db import Base, engine, get_db, SessionLocal
from .cache import cache
from .models import Product, Inventory, Supplier, PurchaseOrder, Recommendation
from .seed import seed
from .rag import ingest, retrieve
from .analytics import product_metrics, supplier_scores
from .agents import run_agent
from .llm import get_llm

DASH = os.path.join(os.path.dirname(__file__), "..", "dashboard", "index.html")


@asynccontextmanager
async def lifespan(_):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
        ingest(db)
    yield


app = FastAPI(title="AI Supply Chain & Inventory Optimization", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class POIn(BaseModel):
    product_id: int
    supplier_id: int
    qty: int = Field(gt=0)
    unit_price: Optional[float] = None


class Question(BaseModel):
    question: str


def row(o):
    return {c.name: getattr(o, c.name) for c in o.__table__.columns if c.name != "vec"}


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(DASH)


@app.get("/health", tags=["system"])
def health(db: Session = Depends(get_db)):
    db.query(Product).first()
    return {"status": "ok", "cache": cache.backend, "llm": bool(get_llm())}


# ---------- core CRUD ----------
@app.get("/products", tags=["inventory"])
def products(db: Session = Depends(get_db)):
    return [row(p) for p in db.query(Product).all()]


@app.get("/inventory", tags=["inventory"])
def inventory(db: Session = Depends(get_db)):
    return product_metrics(db)


@app.put("/inventory/{product_id}", tags=["inventory"])
def update_inventory(product_id: int, on_hand: int, db: Session = Depends(get_db)):
    inv = db.get(Inventory, product_id)
    if not inv:
        raise HTTPException(404, "Product not found")
    inv.on_hand = on_hand
    db.commit()
    cache.delete("dashboard:summary")
    return row(inv)


@app.get("/suppliers", tags=["suppliers"])
def suppliers(db: Session = Depends(get_db)):
    return [row(s) for s in db.query(Supplier).all()]


@app.get("/purchase-orders", tags=["procurement"])
def purchase_orders(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(PurchaseOrder).order_by(PurchaseOrder.id.desc())
    if status:
        q = q.filter(PurchaseOrder.status == status)
    return [row(o) for o in q.limit(200)]


@app.post("/purchase-orders", status_code=201, tags=["procurement"])
def create_po(body: POIn, db: Session = Depends(get_db)):
    p, s = db.get(Product, body.product_id), db.get(Supplier, body.supplier_id)
    if not p or not s:
        raise HTTPException(404, "Unknown product or supplier")
    po = PurchaseOrder(product_id=p.id, supplier_id=s.id, qty=body.qty, unit_price=body.unit_price or p.unit_cost,
                       order_date=date.today(), promised_date=date.today() + timedelta(days=s.lead_time_days),
                       status="ordered", source="manual")
    db.add(po)
    db.get(Inventory, p.id).on_order += body.qty
    db.commit()
    cache.delete("dashboard:summary")
    return row(po)


# ---------- analytics ----------
@app.get("/analytics/shortage-risk", tags=["analytics"])
def shortage(db: Session = Depends(get_db)):
    r = [m for m in product_metrics(db) if m["status"] in ("critical", "shortage")]
    return sorted(r, key=lambda m: m["days_cover"] - m["lead_time"])


@app.get("/analytics/overstock", tags=["analytics"])
def overstock(db: Session = Depends(get_db)):
    return sorted([m for m in product_metrics(db) if m["status"] == "overstock"], key=lambda m: -m["days_cover"])


@app.get("/analytics/demand-anomalies", tags=["analytics"])
def anomalies(db: Session = Depends(get_db)):
    return [m for m in product_metrics(db) if m["spike"]]


@app.get("/analytics/supplier-risk", tags=["analytics"])
def supplier_risk(db: Session = Depends(get_db)):
    return sorted(supplier_scores(db).values(), key=lambda s: -s["risk_score"])


@app.get("/dashboard/summary", tags=["analytics"])
def summary(db: Session = Depends(get_db)):
    hit = cache.get("dashboard:summary")
    if hit:
        return hit
    m, sc = product_metrics(db), supplier_scores(db)
    out = dict(
        products=len(m), stock_value=round(sum(x["stock_value"] for x in m)),
        critical=sum(x["status"] == "critical" for x in m), shortage=sum(x["status"] == "shortage" for x in m),
        overstock=sum(x["status"] == "overstock" for x in m), spikes=sum(x["spike"] for x in m),
        overstock_value=round(sum(x["stock_value"] for x in m if x["status"] == "overstock")),
        high_risk_suppliers=sum(s["risk_level"] == "high" for s in sc.values()),
        pending_recommendations=db.query(Recommendation).filter(Recommendation.status == "pending").count(),
        cover_chart=[dict(name=x["name"], days_cover=x["days_cover"], lead_time=x["lead_time"], status=x["status"])
                     for x in sorted(m, key=lambda x: x["days_cover"] - x["lead_time"])[:12]])
    cache.set("dashboard:summary", out, 30)
    return out


# ---------- RAG ----------
@app.post("/rag/query", tags=["rag"])
def rag_query(body: Question, db: Session = Depends(get_db)):
    chunks = retrieve(db, body.question, 3)
    answer, llm = None, get_llm()
    if llm and chunks:
        try:
            ctx = "\n".join(c["text"] for c in chunks)
            answer = llm.invoke(f"Answer using only this policy context. Cite the policy name.\n\n{ctx}\n\nQuestion: {body.question}").content
        except Exception:
            pass
    return {"answer": answer or chunks[0]["text"] if chunks else "No policy found.", "sources": chunks}


# ---------- agents ----------
@app.post("/agents/run", status_code=202, tags=["agents"])
def start_run(bg: BackgroundTasks):
    rid = uuid.uuid4().hex[:8]
    cache.set(f"run:{rid}", {"id": rid, "status": "queued"}, 86400)
    bg.add_task(run_agent, rid)
    return {"run_id": rid, "status": "queued"}


@app.get("/agents/runs/{run_id}", tags=["agents"])
def get_run(run_id: str):
    st = cache.get(f"run:{run_id}")
    if not st:
        raise HTTPException(404, "Run not found")
    return st


@app.get("/recommendations", tags=["agents"])
def recommendations(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Recommendation).order_by(Recommendation.id)
    if status:
        q = q.filter(Recommendation.status == status)
    return [row(r) for r in q.all()]


@app.post("/recommendations/{rid}/{decision}", tags=["agents"])
def decide(rid: int, decision: str, db: Session = Depends(get_db)):
    if decision not in ("approve", "reject"):
        raise HTTPException(400, "decision must be approve or reject")
    r = db.get(Recommendation, rid)
    if not r:
        raise HTTPException(404, "Recommendation not found")
    r.status = "approved" if decision == "approve" else "rejected"
    if decision == "approve" and "REORDER" in r.action:
        p = db.query(Product).filter(Product.sku == r.sku).first()
        s = db.query(Supplier).filter(Supplier.name == r.supplier).first()
        if p and s:
            db.add(PurchaseOrder(product_id=p.id, supplier_id=s.id, qty=r.quantity, unit_price=p.unit_cost,
                                 order_date=date.today(), promised_date=date.today() + timedelta(days=s.lead_time_days),
                                 status="ordered", source="agent"))
            db.get(Inventory, p.id).on_order += r.quantity
    db.commit()
    cache.delete("dashboard:summary")
    return row(r)
