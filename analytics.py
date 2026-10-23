"""Non-LLM analytics: demand forecast, reorder metrics, anomaly detection, supplier risk."""
import math
from collections import defaultdict
from datetime import date, timedelta
import numpy as np
from .models import Product, Inventory, Sale, Supplier, PurchaseOrder

ORDER_COST, HOLDING_RATE, Z95, WINDOW = 50.0, 0.2, 1.65, 60


def supplier_scores(db):
    cost = {p.id: p.unit_cost for p in db.query(Product).all()}
    pos = defaultdict(list)
    for po in db.query(PurchaseOrder).filter(PurchaseOrder.delivered_date.isnot(None)).all():
        pos[po.supplier_id].append(po)
    out = {}
    for s in db.query(Supplier).all():
        rows = pos.get(s.id, [])
        if rows:
            on_time = float(np.mean([r.delivered_date <= r.promised_date for r in rows]))
            leads = np.array([(r.delivered_date - r.order_date).days for r in rows], float)
            avg_lead, lead_cv = float(leads.mean()), float(leads.std() / max(leads.mean(), 1))
            ratios = np.array([r.unit_price / cost[r.product_id] for r in rows if cost.get(r.product_id)])
            price_cv = float(ratios.std()) if len(ratios) else 0.0
        else:
            on_time, avg_lead, lead_cv, price_cv = 1.0, float(s.lead_time_days), 0.0, 0.0
        risk = 100 * (0.5 * (1 - on_time) + 0.3 * min(lead_cv * 2, 1) + 0.2 * min(price_cv * 5, 1))
        out[s.id] = dict(id=s.id, name=s.name, category=s.category, on_time_rate=round(on_time, 2),
                         avg_lead_time=round(avg_lead, 1), lead_time_cv=round(lead_cv, 2),
                         price_volatility=round(price_cv, 3), risk_score=round(risk, 1),
                         risk_level="high" if risk >= 30 else "medium" if risk >= 15 else "low")
    return out


def product_metrics(db, scores=None):
    scores = scores or supplier_scores(db)
    start = date.today() - timedelta(days=WINDOW)
    series = defaultdict(lambda: np.zeros(WINDOW))
    for pid, day, qty in db.query(Sale.product_id, Sale.day, Sale.qty).filter(Sale.day >= start):
        i = (day - start).days
        if 0 <= i < WINDOW:
            series[pid][i] += qty
    inv = {i.product_id: i for i in db.query(Inventory).all()}
    res = []
    for p in db.query(Product).all():
        s, i = series[p.id], inv.get(p.id)
        if i is None:
            continue
        recent7, base28 = s[-7:].mean(), s[-28:].mean()
        forecast = max(0.6 * recent7 + 0.4 * base28, 0.01)            # blended daily forecast
        hist = s[:-7]
        z = (recent7 - hist.mean()) / (hist.std() / math.sqrt(7) + 1e-9)  # demand-spike z-score
        sup = scores.get(p.supplier_id, {})
        lead = sup.get("avg_lead_time") or 7
        safety = Z95 * s[-28:].std() * math.sqrt(lead)
        rop = forecast * lead + safety
        eoq = math.sqrt(2 * forecast * 365 * ORDER_COST / (HOLDING_RATE * p.unit_cost))
        cover = i.on_hand / forecast
        position = i.on_hand + i.on_order
        status = "ok"
        if cover < lead:
            status = "critical"
        elif position < rop:
            status = "shortage"
        elif cover > 90:
            status = "overstock"
        res.append(dict(
            product_id=p.id, sku=p.sku, name=p.name, category=p.category, unit_cost=p.unit_cost,
            supplier_id=p.supplier_id, supplier=sup.get("name"), supplier_risk=sup.get("risk_level"),
            on_hand=i.on_hand, on_order=i.on_order, daily_forecast=round(forecast, 1),
            forecast_30d=int(forecast * 30), trend_pct=round((recent7 / max(base28, 0.01) - 1) * 100, 1),
            demand_z=round(float(z), 2), spike=bool(z > 3), lead_time=round(lead, 1),
            safety_stock=int(safety), reorder_point=int(rop), eoq=int(eoq),
            days_cover=round(cover, 1), status=status, stock_value=round(i.on_hand * p.unit_cost, 2)))
    return res
