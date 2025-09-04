"""Unit tests for the distributed lock manager."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from datetime import datetime, timedelta

from src.device_manager.lock_manager import DistributedLockManager, MultiResourceLockManager


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    mock = AsyncMock()
    mock.set = AsyncMock()
    mock.get = AsyncMock()
    mock.delete = AsyncMock()
    mock.exists = AsyncMock()
    mock.eval = AsyncMock()
    mock.ttl = AsyncMock()
    mock.expire = AsyncMock()
    mock.scan = AsyncMock()
    return mock


@pytest.fixture
def lock_manager(mock_redis):
    """Create a lock manager instance with mock Redis."""
    return DistributedLockManager(
        redis_client=mock_redis,
        default_timeout=30,
        blocking_timeout=5,
        retry_interval=0.1
    )


@pytest.fixture
def multi_lock_manager(mock_redis):
    """Create a multi-resource lock manager instance."""
    return MultiResourceLockManager(
        redis_client=mock_redis,
        default_timeout=30,
        blocking_timeout=5,
        retry_interval=0.1
    )


class TestDistributedLockManager:
    """Test cases for DistributedLockManager."""

    @pytest.mark.asyncio
    async def test_acquire_lock_success(self, lock_manager, mock_redis):
        """Test successful lock acquisition."""
        mock_redis.set.return_value = True
        
        token = await lock_manager.acquire_lock("board-001", timeout=60)
        
        assert token is not None
        assert isinstance(token, str)
        mock_redis.set.assert_called_once()
        args = mock_redis.set.call_args
        assert args[0][0] == "lock:board:board-001"
        assert args[1]["nx"] is True
        assert args[1]["ex"] == 60

    @pytest.mark.asyncio
    async def test_acquire_lock_already_locked(self, lock_manager, mock_redis):
        """Test acquiring lock when resource is already locked."""
        mock_redis.set.return_value = False
        
        token = await lock_manager.acquire_lock("board-001", blocking=False)
        
        assert token is None
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_acquire_lock_with_blocking(self, lock_manager, mock_redis):
        """Test acquiring lock with blocking enabled."""
        # First attempt fails, second succeeds
        mock_redis.set.side_effect = [False, False, True]
        
        token = await lock_manager.acquire_lock("board-001", blocking=True)
        
        assert token is not None
        assert mock_redis.set.call_count >= 2

    @pytest.mark.asyncio
    async def test_acquire_lock_blocking_timeout(self, lock_manager, mock_redis):
        """Test blocking acquisition timing out."""
        mock_redis.set.return_value = False
        lock_manager.blocking_timeout = 0.3  # Short timeout for test
        
        start_time = asyncio.get_event_loop().time()
        token = await lock_manager.acquire_lock("board-001", blocking=True)
        elapsed = asyncio.get_event_loop().time() - start_time
        
        assert token is None
        assert elapsed >= 0.3
        assert elapsed < 0.5  # Should not take too long

    @pytest.mark.asyncio
    async def test_release_lock_success(self, lock_manager, mock_redis):
        """Test successful lock release."""
        mock_redis.eval.return_value = 1
        
        result = await lock_manager.release_lock("board-001", "test-token")
        
        assert result is True
        mock_redis.eval.assert_called_once()
        args = mock_redis.eval.call_args
        # Check that Lua script is used for atomic release
        assert "get" in args[0][0]
        assert "del" in args[0][0]

    @pytest.mark.asyncio
    async def test_release_lock_not_owner(self, lock_manager, mock_redis):
        """Test releasing lock when not the owner."""
        mock_redis.eval.return_value = 0
        
        result = await lock_manager.release_lock("board-001", "wrong-token")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_extend_lock_success(self, lock_manager, mock_redis):
        """Test successful lock extension."""
        mock_redis.eval.return_value = 1
        
        result = await lock_manager.extend_lock("board-001", "test-token", 60)
        
        assert result is True
        mock_redis.eval.assert_called_once()

    @pytest.mark.asyncio
    async def test_extend_lock_not_owner(self, lock_manager, mock_redis):
        """Test extending lock when not the owner."""
        mock_redis.eval.return_value = 0
        
        result = await lock_manager.extend_lock("board-001", "wrong-token", 60)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_is_locked(self, lock_manager, mock_redis):
        """Test checking if resource is locked."""
        mock_redis.exists.return_value = 1
        
        result = await lock_manager.is_locked("board-001")
        
        assert result is True
        mock_redis.exists.assert_called_once_with("lock:board:board-001")

    @pytest.mark.asyncio
    async def test_is_not_locked(self, lock_manager, mock_redis):
        """Test checking if resource is not locked."""
        mock_redis.exists.return_value = 0
        
        result = await lock_manager.is_locked("board-001")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_get_lock_info_exists(self, lock_manager, mock_redis):
        """Test getting lock information when lock exists."""
        mock_redis.get.return_value = b"test-token"
        mock_redis.ttl.return_value = 120
        lock_manager._local_locks["board-001"] = "test-token"
        
        info = await lock_manager.get_lock_info("board-001")
        
        assert info is not None
        assert info["resource_id"] == "board-001"
        assert info["token"] == "test-token"
        assert info["ttl"] == 120
        assert info["is_owner"] is True

    @pytest.mark.asyncio
    async def test_get_lock_info_not_exists(self, lock_manager, mock_redis):
        """Test getting lock information when lock doesn't exist."""
        mock_redis.get.return_value = None
        
        info = await lock_manager.get_lock_info("board-001")
        
        assert info is None

    @pytest.mark.asyncio
    async def test_lock_context_manager_success(self, lock_manager, mock_redis):
        """Test using lock as context manager successfully."""
        mock_redis.set.return_value = True
        mock_redis.eval.return_value = 1
        
        async with lock_manager.lock("board-001") as token:
            assert token is not None
            # Lock should be acquired
            mock_redis.set.assert_called_once()
        
        # Lock should be released after context
        mock_redis.eval.assert_called_once()

    @pytest.mark.asyncio
    async def test_lock_context_manager_failure(self, lock_manager, mock_redis):
        """Test context manager when lock acquisition fails."""
        mock_redis.set.return_value = False
        
        async with lock_manager.lock("board-001", blocking=False) as token:
            assert token is None
            # No work should be done if lock not acquired
        
        # Release should not be called if lock was not acquired
        mock_redis.eval.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_expired_locks(self, lock_manager, mock_redis):
        """Test clearing expired locks."""
        mock_redis.scan.return_value = (0, [b"lock:board:test1", b"lock:board:test2"])
        mock_redis.ttl.side_effect = [-1, 30]  # First has no TTL, second is fine
        mock_redis.expire.return_value = True
        
        cleared = await lock_manager.clear_expired_locks()
        
        assert cleared == 1
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_force_unlock(self, lock_manager, mock_redis):
        """Test force unlocking a resource."""
        mock_redis.delete.return_value = 1
        
        result = await lock_manager.force_unlock("board-001")
        
        assert result is True
        mock_redis.delete.assert_called_once_with("lock:board:board-001")


class TestMultiResourceLockManager:
    """Test cases for MultiResourceLockManager."""

    @pytest.mark.asyncio
    async def test_acquire_multiple_locks_success(self, multi_lock_manager, mock_redis):
        """Test acquiring multiple locks successfully."""
        mock_redis.set.return_value = True
        
        locks = await multi_lock_manager.acquire_multiple_locks(
            ["board-001", "board-002", "board-003"]
        )
        
        assert locks is not None
        assert len(locks) == 3
        assert "board-001" in locks
        assert "board-002" in locks
        assert "board-003" in locks
        assert mock_redis.set.call_count == 3

    @pytest.mark.asyncio
    async def test_acquire_multiple_locks_partial_failure(self, multi_lock_manager, mock_redis):
        """Test acquiring multiple locks with partial failure."""
        # First two succeed, third fails
        mock_redis.set.side_effect = [True, True, False]
        mock_redis.eval.return_value = 1
        
        locks = await multi_lock_manager.acquire_multiple_locks(
            ["board-001", "board-002", "board-003"]
        )
        
        assert locks is None
        # The successfully acquired locks should be released
        assert mock_redis.eval.call_count == 2  # Two releases

    @pytest.mark.asyncio
    async def test_release_multiple_locks(self, multi_lock_manager, mock_redis):
        """Test releasing multiple locks."""
        mock_redis.eval.side_effect = [1, 1, 0]  # Two succeed, one fails
        
        locks = {
            "board-001": "token-001",
            "board-002": "token-002",
            "board-003": "token-003"
        }
        
        results = await multi_lock_manager.release_multiple_locks(locks)
        
        assert results["board-001"] is True
        assert results["board-002"] is True
        assert results["board-003"] is False
        assert mock_redis.eval.call_count == 3


@pytest.mark.asyncio
async def test_concurrent_lock_acquisition():
    """Test that locks properly handle concurrent acquisition attempts."""
    mock_redis = AsyncMock()
    acquired_count = 0
    
    async def try_acquire(manager, resource_id):
        nonlocal acquired_count
        # Only first attempt should succeed
        if acquired_count == 0:
            mock_redis.set.return_value = True
            acquired_count += 1
        else:
            mock_redis.set.return_value = False
        
        token = await manager.acquire_lock(resource_id, blocking=False)
        return token is not None
    
    manager = DistributedLockManager(mock_redis)
    
    # Try to acquire same lock concurrently
    results = await asyncio.gather(
        try_acquire(manager, "board-001"),
        try_acquire(manager, "board-001"),
        try_acquire(manager, "board-001"),
    )
    
    # Only one should succeed
    assert sum(results) == 1