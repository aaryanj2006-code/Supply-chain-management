"""Synthetic data with planted shortages, overstock, demand spikes and unreliable suppliers."""
import math, random
from datetime import date, timedelta
from .models import Supplier, Product, Inventory, Sale, PurchaseOrder

CATS = {
    "Electronics": ["Wireless Mouse", "USB-C Hub", "Keyboard", "Webcam", "Headset"],
    "Grocery": ["Olive Oil", "Basmati Rice", "Green Tea", "Almond Pack", "Pasta"],
    "Apparel": ["Cotton Tee", "Denim Jeans", "Hoodie", "Running Socks", "Rain Jacket"],
    "Home": ["LED Bulb Pack", "Bath Towel", "Water Bottle", "Desk Lamp", "Storage Box"],
}
# name, category, lead time, on-time reliability
SUPPLIERS = [
    ("VoltEdge Components", "Electronics", 10, 0.95), ("QuickShip Traders", "Electronics", 14, 0.55),
    ("FreshRoute Foods", "Grocery", 5, 0.93), ("GreenHarvest Co", "Grocery", 8, 0.60),
    ("UrbanThread Mills", "Apparel", 18, 0.90), ("StitchWorks Ltd", "Apparel", 20, 0.62),
    ("HomeNest Supply", "Home", 9, 0.94), ("BrightLiving Imports", "Home", 15, 0.70),
]


def seed(db):
    if db.query(Supplier).count():
        return
    rnd, today = random.Random(42), date.today()
    sups = []
    for n, c, lead, rel in SUPPLIERS:
        s = Supplier(name=n, category=c, lead_time_days=lead)
        db.add(s)
        sups.append((s, rel))
    db.flush()
    by_cat = {}
    for s, rel in sups:
        by_cat.setdefault(s.category, []).append((s, rel))

    idx, sales = 0, []
    for cat, names in CATS.items():
        for variant in ("Standard", "Pro"):
            for nm in names:
                sup, rel = by_cat[cat][idx % 2 if idx % 3 else 0]
                cost = round(rnd.uniform(4, 120), 2)
                p = Product(sku=f"SKU-{1000 + idx}", name=f"{nm} {variant}", category=cat,
                            unit_cost=cost, supplier_id=sup.id)
                db.add(p)
                db.flush()
                base = rnd.uniform(5, 60)
                for d in range(120, 0, -1):
                    day = today - timedelta(days=d)
                    wk = 1 + 0.2 * math.sin(2 * math.pi * day.weekday() / 7)
                    q = max(0, int(rnd.gauss(base * wk, base * 0.15)))
                    if idx % 8 == 4 and d <= 7:  # planted demand spike
                        q = int(q * 2.4)
                    sales.append(dict(product_id=p.id, day=day, qty=q))
                lead = sup.lead_time_days
                m = idx % 8
                if m == 0:   cover = rnd.uniform(2, 5)               # imminent stockout
                elif m == 1: cover = lead + rnd.uniform(1, 4)        # below reorder point
                elif m in (2, 3): cover = rnd.uniform(150, 260)      # overstock
                else:        cover = lead + rnd.uniform(25, 60)      # healthy
                db.add(Inventory(product_id=p.id, on_hand=int(base * cover), on_order=0))
                for _ in range(3):  # purchase history with delays
                    od = today - timedelta(days=rnd.randint(35, 170))
                    promised = od + timedelta(days=lead)
                    late = 0 if rnd.random() < rel else rnd.randint(2, 9)
                    jitter = 0.12 if rel < 0.7 else 0.03
                    db.add(PurchaseOrder(product_id=p.id, supplier_id=sup.id, qty=int(base * 30),
                                         unit_price=round(cost * (1 + rnd.gauss(0, jitter)), 2),
                                         order_date=od, promised_date=promised,
                                         delivered_date=promised + timedelta(days=late), status="delivered"))
                idx += 1
    db.bulk_insert_mappings(Sale, sales)
    db.commit()
