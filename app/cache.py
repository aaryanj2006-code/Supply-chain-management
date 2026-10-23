"""Redis wrapper. Falls back to an in-memory dict if REDIS_URL is unset/unreachable."""
import os, json, time
try:
    import redis
except ImportError:
    redis = None


class Cache:
    def __init__(self):
        self.mem, self.r = {}, None
        url = os.getenv("REDIS_URL")
        if url and redis:
            try:
                self.r = redis.from_url(url, decode_responses=True)
                self.r.ping()
            except Exception:
                self.r = None

    @property
    def backend(self):
        return "redis" if self.r else "memory"

    def get(self, key):
        if self.r:
            v = self.r.get(key)
            return json.loads(v) if v else None
        v = self.mem.get(key)
        return v[1] if v and v[0] > time.time() else None

    def set(self, key, value, ttl=60):
        if self.r:
            self.r.setex(key, ttl, json.dumps(value, default=str))
        else:
            self.mem[key] = (time.time() + ttl, json.loads(json.dumps(value, default=str)))

    def delete(self, key):
        if self.r:
            self.r.delete(key)
        else:
            self.mem.pop(key, None)


cache = Cache()
