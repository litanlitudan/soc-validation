"""
Redis client configuration and connection management.

Provides Redis connection pooling and client initialization
for the device manager service.
"""

import logging
import os
from typing import Optional

import redis.asyncio as redis
from redis.exceptions import RedisError, ConnectionError

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Manages Redis connection and provides client instance.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        max_connections: int = 50,
        socket_keepalive: bool = True,
        socket_keepalive_options: Optional[dict] = None,
        health_check_interval: int = 30,
        retry_on_error: bool = True,
        max_retries: int = 3,
    ):
        """
        Initialize Redis client with connection pool.
        
        Args:
            url: Redis connection URL (defaults to env REDIS_URL)
            max_connections: Maximum number of connections in pool
            socket_keepalive: Enable TCP keepalive
            socket_keepalive_options: TCP keepalive options
            health_check_interval: Interval for connection health checks
            retry_on_error: Whether to retry on connection errors
            max_retries: Maximum number of connection retries
        """
        self.url = url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.max_connections = max_connections
        self.socket_keepalive = socket_keepalive
        self.socket_keepalive_options = socket_keepalive_options or {}
        self.health_check_interval = health_check_interval
        self.retry_on_error = retry_on_error
        self.max_retries = max_retries
        self._client: Optional[redis.Redis] = None
        self._pool: Optional[redis.ConnectionPool] = None

    async def connect(self) -> redis.Redis:
        """
        Create and return Redis client with connection pooling.
        
        Returns:
            Async Redis client instance
            
        Raises:
            ConnectionError: If unable to connect to Redis
        """
        if self._client is not None:
            try:
                # Test existing connection
                await self._client.ping()
                return self._client
            except (RedisError, ConnectionError):
                logger.warning("Existing Redis connection lost, reconnecting...")
                await self.disconnect()

        try:
            # Create connection pool
            self._pool = redis.ConnectionPool.from_url(
                self.url,
                max_connections=self.max_connections,
                socket_keepalive=self.socket_keepalive,
                socket_keepalive_options=self.socket_keepalive_options,
                health_check_interval=self.health_check_interval,
                decode_responses=False,  # Return bytes for flexibility
            )
            
            # Create client from pool
            self._client = redis.Redis(connection_pool=self._pool)
            
            # Test connection
            await self._client.ping()
            logger.info(f"Connected to Redis at {self.url}")
            
            return self._client
            
        except ConnectionError as e:
            logger.error(f"Failed to connect to Redis at {self.url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to Redis: {e}")
            raise ConnectionError(f"Could not connect to Redis: {e}")

    async def disconnect(self):
        """
        Close Redis connection and cleanup resources.
        """
        if self._client:
            await self._client.aclose()
            self._client = None
            
        if self._pool:
            await self._pool.disconnect()
            self._pool = None
            
        logger.info("Disconnected from Redis")

    async def get_client(self) -> redis.Redis:
        """
        Get Redis client, creating connection if needed.
        
        Returns:
            Async Redis client instance
        """
        if self._client is None:
            return await self.connect()
        
        try:
            # Verify connection is still alive
            await self._client.ping()
            return self._client
        except (RedisError, ConnectionError):
            logger.warning("Redis connection lost, attempting reconnect...")
            return await self.connect()

    async def health_check(self) -> dict:
        """
        Perform health check on Redis connection.
        
        Returns:
            Dictionary with health status and details
        """
        try:
            client = await self.get_client()
            
            # Get Redis info
            info = await client.info()
            
            # Extract key metrics
            return {
                "status": "healthy",
                "connected": True,
                "redis_version": info.get("redis_version", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "uptime_in_seconds": info.get("uptime_in_seconds", 0),
                "pool_size": self._pool.max_connections if self._pool else 0,
            }
            
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e)
            }

    async def execute_with_retry(self, operation, *args, max_retries: Optional[int] = None, **kwargs):
        """
        Execute Redis operation with automatic retry on failure.
        
        Args:
            operation: Redis operation to execute (e.g., client.get)
            *args: Positional arguments for operation
            max_retries: Maximum retry attempts (uses self.max_retries if None)
            **kwargs: Keyword arguments for operation
            
        Returns:
            Result of the operation
            
        Raises:
            RedisError: If all retries are exhausted
        """
        max_retries = max_retries or self.max_retries
        last_error = None
        
        for attempt in range(max_retries):
            try:
                client = await self.get_client()
                return await operation(*args, **kwargs)
                
            except ConnectionError as e:
                last_error = e
                if attempt < max_retries - 1:
                    logger.warning(f"Redis operation failed (attempt {attempt + 1}/{max_retries}): {e}")
                    await self.disconnect()  # Force reconnection
                else:
                    logger.error(f"Redis operation failed after {max_retries} attempts: {e}")
                    
            except RedisError as e:
                # Non-connection errors should not be retried
                logger.error(f"Redis operation error: {e}")
                raise
                
        # If we get here, all retries exhausted
        raise last_error or RedisError("Redis operation failed")


# Global Redis client instance (singleton pattern)
_redis_client: Optional[RedisClient] = None


def get_redis_client() -> RedisClient:
    """
    Get the global Redis client instance.
    
    Returns:
        RedisClient instance
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client


async def initialize_redis(url: Optional[str] = None) -> redis.Redis:
    """
    Initialize and connect the global Redis client.
    
    Args:
        url: Optional Redis URL override
        
    Returns:
        Connected Redis client
    """
    client = get_redis_client()
    if url:
        client.url = url
    return await client.connect()


async def cleanup_redis():
    """
    Cleanup and disconnect the global Redis client.
    """
    client = get_redis_client()
    await client.disconnect()