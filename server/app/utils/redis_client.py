"""
Redis client utilities with in-memory fallback for local development.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

import redis.asyncio as redis

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Global Redis connection pool (or in-memory fallback)
_redis_pool: Optional[redis.Redis] = None
_using_memory_fallback: bool = False


class InMemoryRedis:
    """In-memory Redis-like storage for local development without Redis."""

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._expiry: Dict[str, datetime] = {}

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        self._data.clear()
        self._expiry.clear()

    async def get(self, key: str) -> Optional[bytes]:
        self._cleanup_expired()
        value = self._data.get(key)
        if value is not None:
            return value if isinstance(value, bytes) else str(value).encode()
        return None

    async def set(self, key: str, value: Any, ex: int = None) -> bool:
        self._data[key] = value
        if ex:
            self._expiry[key] = datetime.now() + timedelta(seconds=ex)
        return True

    async def setex(self, key: str, ttl: int, value: Any) -> bool:
        return await self.set(key, value, ex=ttl)

    async def delete(self, *keys: str) -> int:
        count = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                self._expiry.pop(key, None)
                count += 1
        return count

    async def exists(self, key: str) -> int:
        self._cleanup_expired()
        return 1 if key in self._data else 0

    async def expire(self, key: str, seconds: int) -> bool:
        if key in self._data:
            self._expiry[key] = datetime.now() + timedelta(seconds=seconds)
            return True
        return False

    async def ttl(self, key: str) -> int:
        if key not in self._data:
            return -2
        if key not in self._expiry:
            return -1
        remaining = (self._expiry[key] - datetime.now()).total_seconds()
        return max(0, int(remaining))

    async def incr(self, key: str) -> int:
        self._cleanup_expired()
        current = self._data.get(key, 0)
        if isinstance(current, bytes):
            current = int(current)
        self._data[key] = current + 1
        return self._data[key]

    def pipeline(self) -> "InMemoryPipeline":
        return InMemoryPipeline(self)

    def _cleanup_expired(self) -> None:
        now = datetime.now()
        expired = [k for k, exp in self._expiry.items() if exp <= now]
        for key in expired:
            self._data.pop(key, None)
            self._expiry.pop(key, None)


class InMemoryPipeline:
    """Pipeline for InMemoryRedis."""

    def __init__(self, redis_instance: InMemoryRedis):
        self._redis = redis_instance
        self._commands: list = []

    def incr(self, key: str) -> "InMemoryPipeline":
        self._commands.append(("incr", key, None))
        return self

    def ttl(self, key: str) -> "InMemoryPipeline":
        self._commands.append(("ttl", key, None))
        return self

    def expire(self, key: str, seconds: int) -> "InMemoryPipeline":
        self._commands.append(("expire", key, seconds))
        return self

    def get(self, key: str) -> "InMemoryPipeline":
        self._commands.append(("get", key, None))
        return self

    def set(self, key: str, value: Any, ex: int = None) -> "InMemoryPipeline":
        self._commands.append(("set", key, (value, ex)))
        return self

    def setex(self, key: str, seconds: int, value: Any) -> "InMemoryPipeline":
        self._commands.append(("set", key, (value, seconds)))
        return self

    def delete(self, key: str) -> "InMemoryPipeline":
        self._commands.append(("delete", key, None))
        return self

    async def execute(self) -> list:
        results = []
        for cmd, key, arg in self._commands:
            if cmd == "incr":
                results.append(await self._redis.incr(key))
            elif cmd == "ttl":
                results.append(await self._redis.ttl(key))
            elif cmd == "expire":
                results.append(await self._redis.expire(key, arg))
            elif cmd == "get":
                results.append(await self._redis.get(key))
            elif cmd == "set":
                value, ex = arg
                results.append(await self._redis.set(key, value, ex=ex))
            elif cmd == "delete":
                results.append(await self._redis.delete(key))
        return results


async def init_redis() -> None:
    """Initialize Redis connection pool, with in-memory fallback."""
    global _redis_pool, _using_memory_fallback

    try:
        pool = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=False,
        )
        await pool.ping()
        _redis_pool = pool
        _using_memory_fallback = False
        logger.info("Redis connection established")
    except Exception as e:
        logger.warning(f"Redis unavailable ({e}), using in-memory fallback")
        _redis_pool = InMemoryRedis()
        _using_memory_fallback = True
        logger.info("In-memory session store initialized (dev mode)")


async def close_redis() -> None:
    """Close Redis connection pool."""
    global _redis_pool, _using_memory_fallback

    if _redis_pool:
        await _redis_pool.close()
        _redis_pool = None
        _using_memory_fallback = False
        logger.info("Redis connection closed")


async def get_redis():
    """Get Redis connection for dependency injection."""
    if _redis_pool is None:
        await init_redis()

    return _redis_pool


class RedisSessionStore:
    """Session storage using Redis."""

    def __init__(self, redis_client: redis.Redis, prefix: str = "session"):
        self.redis = redis_client
        self.prefix = prefix

    def _key(self, session_id: str) -> str:
        return f"{self.prefix}:{session_id}"

    async def set(
        self, session_id: str, data: dict, ttl_seconds: int = 300
    ) -> None:
        """Store session data."""
        import json

        key = self._key(session_id)
        await self.redis.setex(key, ttl_seconds, json.dumps(data))

    async def get(self, session_id: str) -> Optional[dict]:
        """Retrieve session data."""
        import json

        key = self._key(session_id)
        data = await self.redis.get(key)

        if data:
            return json.loads(data)
        return None

    async def delete(self, session_id: str) -> None:
        """Delete session data."""
        key = self._key(session_id)
        await self.redis.delete(key)

    async def exists(self, session_id: str) -> bool:
        """Check if session exists."""
        key = self._key(session_id)
        return await self.redis.exists(key) > 0

    async def extend(self, session_id: str, ttl_seconds: int) -> bool:
        """Extend session TTL."""
        key = self._key(session_id)
        return await self.redis.expire(key, ttl_seconds)


class RedisRateLimiter:
    """Rate limiting using Redis."""

    def __init__(
        self,
        redis_client: redis.Redis,
        prefix: str = "ratelimit",
        max_requests: int = 60,
        window_seconds: int = 60,
    ):
        self.redis = redis_client
        self.prefix = prefix
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def _key(self, identifier: str) -> str:
        return f"{self.prefix}:{identifier}"

    async def is_allowed(self, identifier: str) -> tuple:
        """
        Check if request is allowed.

        Returns:
            Tuple of (is_allowed, remaining_requests, reset_time)
        """
        key = self._key(identifier)

        # Use pipeline for atomic operations
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        results = await pipe.execute()

        current_count = results[0]
        ttl = results[1]

        # Set expiry if this is the first request
        if ttl == -1:
            await self.redis.expire(key, self.window_seconds)
            ttl = self.window_seconds

        remaining = max(0, self.max_requests - current_count)
        is_allowed = current_count <= self.max_requests

        return is_allowed, remaining, ttl

    async def reset(self, identifier: str) -> None:
        """Reset rate limit for an identifier."""
        key = self._key(identifier)
        await self.redis.delete(key)
