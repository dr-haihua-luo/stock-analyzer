import json
import asyncio
from typing import Any, Optional, Union
import redis.asyncio as redis
from backend.config import settings
import logging

logger = logging.getLogger(__name__)


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


# Global Redis client instance
redis_client = RedisClient()