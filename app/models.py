from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, JSON, Text
from .db import Base


class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    category = Column(String)
    lead_time_days = Column(Integer, default=7)


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    sku = Column(String, unique=True, index=True)
    name = Column(String)
    category = Column(String)
    unit_cost = Column(Float)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))


class Inventory(Base):
    __tablename__ = "inventory"
    product_id = Column(Integer, ForeignKey("products.id"), primary_key=True)
    on_hand = Column(Integer, default=0)
    on_order = Column(Integer, default=0)


class Sale(Base):
    __tablename__ = "sales_history"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)
    day = Column(Date, index=True)
    qty = Column(Integer)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    qty = Column(Integer)
    unit_price = Column(Float)
    order_date = Column(Date)
    promised_date = Column(Date)
    delivered_date = Column(Date, nullable=True)
    status = Column(String, default="delivered")  # ordered | delivered
    source = Column(String, default="history")    # history | manual | agent


class Recommendation(Base):
    __tablename__ = "recommendations"
    id = Column(Integer, primary_key=True)
    run_id = Column(String, index=True)
    sku = Column(String)
    product_name = Column(String)
    severity = Column(String)
    action = Column(String)
    quantity = Column(Integer)
    supplier = Column(String)
    reason = Column(Text)
    confidence = Column(Float)
    policy = Column(String)
    status = Column(String, default="pending")  # pending | approved | rejected
    created_at = Column(DateTime, default=datetime.utcnow)


class PolicyChunk(Base):
    __tablename__ = "policy_chunks"
    id = Column(Integer, primary_key=True)
    source = Column(String)
    title = Column(String)
    text = Column(Text)
    vec = Column(JSON)
