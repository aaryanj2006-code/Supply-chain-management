"""Knowledge base documents for the RAG pipeline (markdown, split by '## ' sections)."""
POLICIES = {
    "Procurement Policy": """# Procurement Policy
## Approval thresholds
Purchase orders under 5,000 USD may be approved by the inventory planner. Orders between 5,000 and 25,000 USD require supply chain manager approval. Orders above 25,000 USD require director sign-off.
## Supplier selection
Prefer suppliers with on-time delivery above 90 percent. If the primary supplier is rated high risk, place the order with a lower-risk backup supplier in the same category or split the order 70/30 between two suppliers.
## Expedited orders
Expedited shipping is allowed only when projected stockout occurs before the standard lead time ends. Document the reason in the purchase order.""",
    "Reorder Rules": """# Reorder and Replenishment Rules
## Reorder point
Reorder point equals average daily demand times supplier lead time plus safety stock. Raise a purchase order when on-hand plus on-order inventory falls below the reorder point.
## Order quantity
Order the economic order quantity, or enough to cover 30 days of forecast demand beyond the reorder point, whichever is larger.
## Shortage response
If days of cover is lower than the supplier lead time, treat the item as a critical shortage: reorder immediately, request expedited delivery and notify the category manager.""",
    "Safety Stock Guidelines": """# Safety Stock Guidelines
## Calculation
Safety stock equals 1.65 times the standard deviation of daily demand times the square root of lead time, targeting a 95 percent service level.
## Demand spikes
When recent weekly demand exceeds the historical mean by more than three standard errors, treat it as a demand spike. Increase safety stock by 25 percent for four weeks and review whether the spike is a lasting trend or a one-off promotion.""",
    "Overstock and Markdown Policy": """# Excess Inventory Policy
## Overstock definition
An item is overstocked when on-hand inventory covers more than 90 days of forecast demand.
## Actions
Stop reordering overstocked items. Transfer surplus to locations with shortages, bundle slow movers, or apply a markdown of 10 to 25 percent. Items above 180 days of cover require a clearance plan reviewed monthly.""",
    "Supplier SLA and Escalation": """# Supplier SLA and Escalation
## Service levels
Suppliers must deliver on time at least 90 percent of the time with lead time variation under 15 percent.
## Escalation
Suppliers with on-time delivery below 70 percent are high risk. Escalate to the supplier manager, start a performance review and qualify a backup supplier. Two consecutive late deliveries trigger dual sourcing for that category.""",
}
