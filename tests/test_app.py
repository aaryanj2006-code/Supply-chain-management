import os, time, tempfile
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/t.db"
from fastapi.testclient import TestClient
from app.main import app


def test_flow():
    with TestClient(app) as c:
        assert c.get("/health").json()["status"] == "ok"
        assert len(c.get("/products").json()) == 40
        assert len(c.get("/analytics/shortage-risk").json()) > 0
        assert len(c.get("/analytics/overstock").json()) > 0
        assert c.get("/analytics/supplier-risk").json()[0]["risk_level"] == "high"
        assert "sources" in c.post("/rag/query", json={"question": "approval threshold"}).json()
        rid = c.post("/agents/run").json()["run_id"]
        for _ in range(30):
            st = c.get(f"/agents/runs/{rid}").json()
            if st["status"] in ("completed", "failed"):
                break
            time.sleep(0.5)
        assert st["status"] == "completed", st
        recs = c.get("/recommendations").json()
        assert recs and c.post(f"/recommendations/{recs[0]['id']}/approve").json()["status"] == "approved"
