import json

from redis import Redis
from redis.exceptions import RedisError


class Cache:
    """Cache failure is observable but must not turn into an authorization bypass."""

    def __init__(self, url):
        self.client = Redis.from_url(url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2)

    def get(self, key):
        try:
            value = self.client.get(key)
            return json.loads(value) if value else None
        except (RedisError, ValueError):
            return None

    def set(self, key, value, ttl=300):
        try:
            self.client.setex(key, ttl, json.dumps(value, ensure_ascii=False))
        except RedisError:
            pass

    def close(self):
        self.client.close()
