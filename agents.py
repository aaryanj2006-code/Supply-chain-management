"""LangGraph workflow: Monitor -> Demand -> Supplier -> Policy RAG -> Recommender.
Conditional edge ends the run early when no risk is detected. Run state lives in Redis."""
import json, math
from datetime import datetime
from typing import TypedDict
from langgraph.graph import StateGraph, END
from .db import SessionLocal
from .cache import cache
from .analytics import product_metrics, supplier_scores
from .models import Recommendation
from .rag import retrieve
from .llm import get_llm, parse_json

SEV = {"critical": 0, "shortage": 1, "overstock": 2, "spike": 3}
QUERIES = {
    "shortage": "reorder point safety stock shortage replenishment order quantity",
    "overstock": "excess inventory overstock markdown stop reordering",
    "supplier": "high risk supplier backup dual sourcing escalation on-time delivery",
    "spike": "demand spike safety stock increase",
}


class State(TypedDict, total=False):
    run_id: str
    products_at_risk: list
    supplier_scores: dict
    policy_context: dict
    recommendations: list
    llm_used: bool


def _set(rid, **kw):
    st = cache.get(f"run:{rid}") or {"id": rid}
    st.update(kw)
    cache.set(f"run:{rid}", st, 86400)


def monitor(s):
    _set(s["run_id"], status="running", step="monitor")
    with SessionLocal() as db:
        sc = supplier_scores(db)
        metrics = product_metrics(db, sc)
    risk = [m for m in metrics if m["status"] != "ok" or m["spike"]]
    _set(s["run_id"], products_scanned=len(metrics), risks_found=len(risk))
    return {"products_at_risk": risk, "supplier_scores": sc}


def demand(s):
    _set(s["run_id"], step="demand")
    for m in s["products_at_risk"]:
        t = m["trend_pct"]
        m["trend"] = "rising" if t > 10 else "falling" if t < -10 else "stable"
    return {"products_at_risk": s["products_at_risk"]}


def supplier(s):
    _set(s["run_id"], step="supplier")
    sc = s["supplier_scores"]
    for m in s["products_at_risk"]:
        alts = [x for x in sc.values() if x["category"] == m["category"] and x["id"] != m["supplier_id"]]
        alt = min(alts, key=lambda x: x["risk_score"]) if alts else None
        m["alt_supplier"] = alt["name"] if alt else None
        m["alt_risk"] = alt["risk_level"] if alt else None
    return {"products_at_risk": s["products_at_risk"]}


def policy(s):
    _set(s["run_id"], step="policy_rag")
    with SessionLocal() as db:
        ctx = {k: retrieve(db, q, 2) for k, q in QUERIES.items()}
    return {"policy_context": ctx}


def _build(m, ctx):
    spike_only = m["status"] == "ok" and m["spike"]
    key = "shortage" if m["status"] in ("critical", "shortage") else m["status"] if m["status"] == "overstock" else "spike"
    cite = ctx[key][0] if ctx.get(key) else None
    sup, notes, conf = m["supplier"], [], {"critical": 0.92, "shortage": 0.8, "overstock": 0.75}.get(m["status"], 0.65)
    if key == "shortage":
        qty = max(m["eoq"], math.ceil(m["reorder_point"] + m["forecast_30d"] - m["on_hand"] - m["on_order"]))
        action = "EXPEDITED_REORDER" if m["status"] == "critical" else "REORDER"
        if m["supplier_risk"] == "high" and m["alt_supplier"]:
            sup, conf = m["alt_supplier"], conf - 0.05
            notes.append(f"primary supplier {m['supplier']} is high risk, switching to {sup}")
            ccite = ctx["supplier"][0]
            cite = ccite
        reason = (f"{m['days_cover']} days of cover vs {m['lead_time']}-day lead time; reorder point {m['reorder_point']}, "
                  f"on hand {m['on_hand']}. Demand {m['trend']} ({m['trend_pct']}%). " + "; ".join(notes))
    elif key == "overstock":
        keep = int(m["daily_forecast"] * 60)
        qty, action = max(m["on_hand"] - keep, 0), "STOP_ORDERS_AND_MARKDOWN"
        reason = f"{m['days_cover']} days of cover (threshold 90). About {qty} surplus units tie up ${qty * m['unit_cost']:,.0f}."
    else:
        qty, action = int(m["safety_stock"] * 0.25), "RAISE_SAFETY_STOCK"
        reason = f"Demand spike detected (z={m['demand_z']}, {m['trend_pct']}% above baseline). Stock still covers {m['days_cover']} days."
    return dict(sku=m["sku"], product_name=m["name"], severity="spike" if spike_only else m["status"],
                action=action, quantity=int(qty), supplier=sup, reason=reason, confidence=round(conf, 2),
                policy=f"{cite['source']}: {cite['title']}" if cite else "n/a")


def recommend(s):
    _set(s["run_id"], step="recommender")
    recs = [_build(m, s["policy_context"]) for m in s["products_at_risk"]]
    recs.sort(key=lambda r: SEV.get(r["severity"], 9))
    llm, used = get_llm(), False
    if llm and recs:
        try:
            facts = [{k: r[k] for k in ("sku", "severity", "action", "quantity", "supplier", "reason", "policy")} for r in recs[:12]]
            prompt = ("You are a supply chain analyst. For each item, write a 1-2 sentence justification for a planner, "
                      "using only the given facts and citing the policy. Reply ONLY with JSON: {\"SKU\": \"justification\"}.\n"
                      + json.dumps(facts))
            out = parse_json(llm.invoke(prompt).content)
            for r in recs:
                if r["sku"] in out:
                    r["reason"], used = str(out[r["sku"]]), True
        except Exception:
            pass
    with SessionLocal() as db:
        db.query(Recommendation).filter(Recommendation.status == "pending").delete()
        db.add_all([Recommendation(run_id=s["run_id"], **r) for r in recs])
        db.commit()
    return {"recommendations": recs, "llm_used": used}


g = StateGraph(State)
for name, fn in [("monitor", monitor), ("demand", demand), ("supplier", supplier), ("policy", policy), ("recommend", recommend)]:
    g.add_node(name, fn)
g.set_entry_point("monitor")
g.add_conditional_edges("monitor", lambda s: "demand" if s["products_at_risk"] else END, {"demand": "demand", END: END})
g.add_edge("demand", "supplier")
g.add_edge("supplier", "policy")
g.add_edge("policy", "recommend")
g.add_edge("recommend", END)
graph = g.compile()


def run_agent(rid):
    try:
        out = graph.invoke({"run_id": rid})
        _set(rid, status="completed", step="done", recommendations=len(out.get("recommendations", [])),
             llm_used=out.get("llm_used", False), finished=datetime.utcnow().isoformat())
    except Exception as e:
        _set(rid, status="failed", error=str(e))
    cache.delete("dashboard:summary")
