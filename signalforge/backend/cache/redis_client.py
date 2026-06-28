import json
import asyncio
import hashlib
import logging
from typing import Any, Optional, Union
import redis.asyncio as redis
from backend.config import settings

logger = logging.getLogger(__name__)

# LLM cache TTL and prefix
LLM_CACHE_TTL = 3600  # 60 minutes - matches data cache TTL
LLM_KEY_PREFIX = "llm"


def _make_llm_cache_key(agent: str, input_dict: dict) -> str:
    """
    Build a deterministic Redis key from the LLM input data.

    Uses SHA-256 of canonical JSON (sorted keys, no whitespace).
    Truncated to 16 hex chars — collision probability negligible
    for the small number of tickers in use.

    Args:
        agent:      "market" | "sector"
        input_dict: the exact dict of values passed to the LLM prompt

    Returns:
        e.g. "llm:market:a3f8c2e1d9b74f20"
             "llm:sector:AAPL:7c4d1e9f2a836b51"
    """
    canonical = json.dumps(input_dict, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:16]

    ticker_segment = input_dict.get("ticker", "")
    if ticker_segment:
        return f"{LLM_KEY_PREFIX}:{agent}:{ticker_segment}:{digest}"
    return f"{LLM_KEY_PREFIX}:{agent}:{digest}"


class RedisClient:
    def __init__(self):
        self.redis: Optional[redis.Redis] = None

    async def connect(self):
        """Initialize Redis connection with retry logic and fallback."""
        # List of hosts to try, in order
        hosts_to_try = [
            ("localhost", settings.REDIS_PORT, f"localhost:{settings.REDIS_PORT}"),
            (settings.REDIS_HOST, settings.REDIS_PORT, f"{settings.REDIS_HOST}:{settings.REDIS_PORT}")      
        ]

        last_error = None

        # Try each host with retry logic
        for host, port, host_description in hosts_to_try:
            for attempt in range(3):
                try:
                    self.redis = redis.Redis(
                        host=host,
                        port=port,
                        password=settings.REDIS_PASSWORD,
                        decode_responses=True,
                        socket_connect_timeout=5.0,
                        socket_timeout=5.0,
                    )
                    # Test connection
                    await self.redis.ping()
                    logger.info(f"Connected to Redis at {host_description} (attempt {attempt + 1})")
                    return
                except Exception as e:
                    last_error = e
                    if attempt < 2:  # Don't log on the last attempt
                        logger.warning(f"Failed to connect to Redis at {host_description} (attempt {attempt + 1}/3): {e}")
                        # Wait before retrying
                        await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff: 1s, 2s
                    else:
                        logger.warning(f"Failed to connect to Redis at {host_description} after 3 attempts: {e}")

        # If we got here, all attempts failed
        logger.warning(f"Failed to connect to Redis after attempting all hosts. Last error: {last_error}")
        logger.warning("Redis functionality will be disabled - application will continue without caching")
        self.redis = None
        # Don't raise ConnectionError - allow app to start without Redis

    async def disconnect(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
            logger.info("Disconnected from Redis")

    async def get(self, key: str) -> Optional[Any]:
        """Get value from Redis and deserialize JSON."""
        if not self.redis:
            logger.debug("Redis not connected, returning None for get operation")
            return None

        try:
            value = await self.redis.get(key)
            if value is None:
                return None

            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        except Exception as e:
            logger.warning(f"Error getting key {key} from Redis: {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None
    ) -> bool:
        """Set value in Redis with optional expiration and JSON serialization."""
        if not self.redis:
            logger.debug("Redis not connected, skipping set operation for key: %s", key)
            return False

        try:
            serialized_value = json.dumps(value) if not isinstance(value, (str, int, float)) else value
            result = await self.redis.set(key, serialized_value, ex=expire)
            return result
        except Exception as e:
            logger.warning(f"Error setting key {key} in Redis: {e}")
            return False

    async def delete(self, key: str) -> int:
        """Delete key from Redis."""
        if not self.redis:
            logger.debug("Redis not connected, skipping delete operation for key: %s", key)
            return 0
        try:
            return await self.redis.delete(key)
        except Exception as e:
            logger.warning(f"Error deleting key {key} from Redis: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        if not self.redis:
            logger.debug("Redis not connected, returning False for exists operation on key: %s", key)
            return False
        try:
            return await self.redis.exists(key)
        except Exception as e:
            logger.warning(f"Error checking existence of key {key} in Redis: {e}")
            return False

    async def get_llm_narrative(
        self,
        agent: str,
        input_dict: dict,
    ) -> Optional[str]:
        """
        Retrieve a cached LLM narrative string.

        Returns the cached string if found, None if cache miss.
        Logs a clear HIT/MISS at DEBUG level for observability.
        Never raises — Redis errors return None (LLM will be called).

        Args:
            agent:      "market" | "sector"
            input_dict: same dict that will be / was passed to the LLM
        """
        key = _make_llm_cache_key(agent, input_dict)
        if not self.redis:
            logger.debug("Redis not connected, returning None for LLM cache get operation key=%s", key)
            return None
        try:
            value = await self.redis.get(key)
            if value is not None:
                logger.debug("LLM cache HIT  key=%s", key)
                return value
            logger.debug("LLM cache MISS key=%s", key)
            return None
        except Exception as exc:
            logger.warning("LLM cache get error (key=%s): %s", key, exc)
            return None

    async def set_llm_narrative(
        self,
        agent: str,
        input_dict: dict,
        narrative: str,
        ttl: int = LLM_CACHE_TTL,
    ) -> None:
        """
        Store an LLM narrative string in Redis.

        TTL defaults to LLM_CACHE_TTL (3600s = 60 min).
        Never raises — Redis errors are logged and silently ignored.

        Args:
            agent:      "market" | "sector"
            input_dict: same dict used to generate the narrative
            narrative:  the LLM response string to cache
            ttl:        expiry in seconds (default 3600)
        """
        key = _make_llm_cache_key(agent, input_dict)
        if not self.redis:
            logger.debug("Redis not connected, skipping LLM cache set operation key=%s", key)
            return
        try:
            await self.redis.set(key, narrative, ex=ttl)
            logger.debug("LLM cache SET  key=%s ttl=%ds", key, ttl)
        except Exception as exc:
            logger.warning("LLM cache set error (key=%s): %s", key, exc)


# --- LLM Cache Redis CLI reference ---
#
# List all LLM cache keys:
#   redis-cli KEYS "llm:*"
#
# Inspect a market narrative:
#   redis-cli GET "llm:market:a3f8c2e1d9b74f20"
#
# Check TTL remaining on a key:
#   redis-cli TTL "llm:market:a3f8c2e1d9b74f20"
#
# Manually bust market LLM cache (all market narratives):
#   redis-cli KEYS "llm:market:*" | xargs redis-cli DEL
#
# Manually bust sector LLM cache for one ticker:
#   redis-cli KEYS "llm:sector:AAPL:*" | xargs redis-cli DEL
#
# Manually bust ALL LLM cache (forces re-call on next analysis):
#   redis-cli KEYS "llm:*" | xargs redis-cli DEL
#
# Bump prompt_version in llm_input dict instead of manual flush
# when changing prompt wording — old keys expire naturally.

# Global Redis client instance
redis_client = RedisClient()