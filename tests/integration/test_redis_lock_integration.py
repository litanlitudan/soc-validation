"""Integration tests for Redis and lock manager."""

import asyncio
import pytest
import os
from datetime import datetime, timedelta

from src.device_manager.redis_client import RedisClient, initialize_redis, cleanup_redis
from src.device_manager.lock_manager import DistributedLockManager


@pytest.fixture
async def redis_client():
    """Create a Redis client for testing."""
    client = RedisClient(url=os.getenv("REDIS_URL", "redis://localhost:6379"))
    redis = await client.connect()
    yield client
    await client.disconnect()


@pytest.fixture
async def lock_manager(redis_client):
    """Create a lock manager with real Redis connection."""
    redis = await redis_client.get_client()
    manager = DistributedLockManager(
        redis_client=redis,
        default_timeout=10,
        blocking_timeout=2,
        retry_interval=0.1
    )
    yield manager
    # Clean up any test locks
    await redis.flushdb()


@pytest.mark.integration
class TestRedisLockIntegration:
    """Integration tests for Redis-based locking."""

    @pytest.mark.asyncio
    async def test_redis_connection(self, redis_client):
        """Test basic Redis connection."""
        client = await redis_client.get_client()
        result = await client.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_acquire_and_release_lock(self, lock_manager):
        """Test acquiring and releasing a lock with real Redis."""
        # Acquire lock
        token = await lock_manager.acquire_lock("test-board-001", timeout=5)
        assert token is not None
        
        # Verify lock is held
        is_locked = await lock_manager.is_locked("test-board-001")
        assert is_locked is True
        
        # Release lock
        released = await lock_manager.release_lock("test-board-001", token)
        assert released is True
        
        # Verify lock is released
        is_locked = await lock_manager.is_locked("test-board-001")
        assert is_locked is False

    @pytest.mark.asyncio
    async def test_lock_prevents_concurrent_access(self, lock_manager):
        """Test that lock prevents concurrent access."""
        # First acquisition should succeed
        token1 = await lock_manager.acquire_lock("test-board-002", timeout=5)
        assert token1 is not None
        
        # Second acquisition should fail (non-blocking)
        token2 = await lock_manager.acquire_lock("test-board-002", timeout=5, blocking=False)
        assert token2 is None
        
        # Release first lock
        await lock_manager.release_lock("test-board-002", token1)
        
        # Now acquisition should succeed
        token3 = await lock_manager.acquire_lock("test-board-002", timeout=5, blocking=False)
        assert token3 is not None
        
        # Clean up
        await lock_manager.release_lock("test-board-002", token3)

    @pytest.mark.asyncio
    async def test_lock_expiration(self, lock_manager):
        """Test that locks expire after timeout."""
        # Acquire lock with very short timeout
        token = await lock_manager.acquire_lock("test-board-003", timeout=1)
        assert token is not None
        
        # Verify lock exists
        is_locked = await lock_manager.is_locked("test-board-003")
        assert is_locked is True
        
        # Wait for expiration
        await asyncio.sleep(1.5)
        
        # Lock should have expired
        is_locked = await lock_manager.is_locked("test-board-003")
        assert is_locked is False
        
        # Should be able to acquire again
        token2 = await lock_manager.acquire_lock("test-board-003", timeout=5)
        assert token2 is not None
        
        # Clean up
        await lock_manager.release_lock("test-board-003", token2)

    @pytest.mark.asyncio
    async def test_extend_lock(self, lock_manager):
        """Test extending a lock's expiration."""
        # Acquire lock with short timeout
        token = await lock_manager.acquire_lock("test-board-004", timeout=2)
        assert token is not None
        
        # Get initial TTL
        info = await lock_manager.get_lock_info("test-board-004")
        initial_ttl = info["ttl"]
        
        # Extend lock
        extended = await lock_manager.extend_lock("test-board-004", token, additional_time=10)
        assert extended is True
        
        # Check new TTL is longer
        info = await lock_manager.get_lock_info("test-board-004")
        new_ttl = info["ttl"]
        assert new_ttl > initial_ttl
        
        # Clean up
        await lock_manager.release_lock("test-board-004", token)

    @pytest.mark.asyncio
    async def test_concurrent_lock_attempts(self, lock_manager):
        """Test multiple concurrent attempts to acquire the same lock."""
        results = []
        
        async def try_acquire(board_id, delay=0):
            await asyncio.sleep(delay)
            token = await lock_manager.acquire_lock(board_id, timeout=5, blocking=False)
            if token:
                results.append(token)
                await asyncio.sleep(0.5)  # Hold lock briefly
                await lock_manager.release_lock(board_id, token)
            return token is not None
        
        # Launch multiple concurrent attempts
        tasks = [
            try_acquire("test-board-005", 0),
            try_acquire("test-board-005", 0.01),
            try_acquire("test-board-005", 0.02),
            try_acquire("test-board-005", 0.03),
        ]
        
        successes = await asyncio.gather(*tasks)
        
        # Only one should succeed
        assert sum(successes) == 1
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_lock_context_manager(self, lock_manager):
        """Test using lock as context manager."""
        async with lock_manager.lock("test-board-006", timeout=5) as token:
            assert token is not None
            
            # Lock should be held
            is_locked = await lock_manager.is_locked("test-board-006")
            assert is_locked is True
            
            # Another attempt should fail
            token2 = await lock_manager.acquire_lock("test-board-006", blocking=False)
            assert token2 is None
        
        # Lock should be released after context
        is_locked = await lock_manager.is_locked("test-board-006")
        assert is_locked is False

    @pytest.mark.asyncio
    async def test_force_unlock(self, lock_manager):
        """Test force unlocking a resource."""
        # Acquire lock
        token = await lock_manager.acquire_lock("test-board-007", timeout=10)
        assert token is not None
        
        # Force unlock (admin operation)
        unlocked = await lock_manager.force_unlock("test-board-007")
        assert unlocked is True
        
        # Lock should be gone
        is_locked = await lock_manager.is_locked("test-board-007")
        assert is_locked is False
        
        # Original token should not work for release
        released = await lock_manager.release_lock("test-board-007", token)
        assert released is False


@pytest.mark.integration
class TestRedisClient:
    """Integration tests for Redis client."""

    @pytest.mark.asyncio
    async def test_health_check(self, redis_client):
        """Test Redis health check functionality."""
        health = await redis_client.health_check()
        
        assert health["status"] == "healthy"
        assert health["connected"] is True
        assert "redis_version" in health
        assert health["redis_version"] != "unknown"

    @pytest.mark.asyncio
    async def test_connection_recovery(self, redis_client):
        """Test that client can recover from connection loss."""
        # Get initial client
        client1 = await redis_client.get_client()
        await client1.ping()
        
        # Simulate connection loss by closing
        await redis_client.disconnect()
        
        # Should reconnect automatically
        client2 = await redis_client.get_client()
        result = await client2.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_execute_with_retry(self, redis_client):
        """Test executing operations with retry logic."""
        client = await redis_client.get_client()
        
        # Simple operation that should succeed
        result = await redis_client.execute_with_retry(
            client.set,
            "test-key",
            "test-value",
            ex=10
        )
        assert result is True
        
        # Verify value was set
        value = await client.get("test-key")
        assert value == b"test-value"
        
        # Clean up
        await client.delete("test-key")