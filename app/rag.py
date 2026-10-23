"""RAG: chunk policy docs, embed (hashing TF-IDF-style vectors), store in the DB vector table, cosine search.
Swap `embed()` for OpenAI/Gemini embeddings and the table for pgvector in production."""
import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from .models import PolicyChunk
from .policies import POLICIES

_vec = HashingVectorizer(n_features=1024, alternate_sign=False, norm="l2", ngram_range=(1, 2),
                         stop_words="english")
_index = {"ids": None, "mat": None, "rows": None}


def embed(texts):
    return _vec.transform(texts).toarray()


def ingest(db):
    if db.query(PolicyChunk).count():
        return
    for source, doc in POLICIES.items():
        for sec in doc.split("\n## ")[1:]:
            title, _, body = sec.partition("\n")
            text = f"{source} - {title}: {body.strip()}"
            db.add(PolicyChunk(source=source, title=title.strip(), text=text, vec=embed([text])[0].tolist()))
    db.commit()
    _index["mat"] = None


def retrieve(db, query, k=3):
    if _index["mat"] is None:
        rows = db.query(PolicyChunk).all()
        _index["rows"] = [dict(source=r.source, title=r.title, text=r.text) for r in rows]
        _index["mat"] = np.array([r.vec for r in rows]) if rows else np.zeros((0, 1024))
    if not len(_index["mat"]):
        return []
    sims = _index["mat"] @ embed([query])[0]
    top = np.argsort(-sims)[:k]
    return [dict(_index["rows"][i], score=round(float(sims[i]), 3)) for i in top]
