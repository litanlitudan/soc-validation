"""
Distributed lock manager using Redis for board allocation.

This module provides a distributed locking mechanism to ensure
atomic board allocation across multiple workers and API instances.
"""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Optional, AsyncIterator

import redis.asyncio as redis
from redis.exceptions import RedisError, LockError, LockNotOwnedError

logger = logging.getLogger(__name__)


class DistributedLockManager:
    """
    Manages distributed locks using Redis for thread-safe board allocation.
    
    Implements a distributed locking mechanism with automatic expiration
    and owner tracking to prevent deadlocks and ensure fair resource access.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        default_timeout: int = 30,
        blocking_timeout: int = 10,
        retry_interval: float = 0.1
    ):
        """
        Initialize the distributed lock manager.
        
        Args:
            redis_client: Async Redis client instance
            default_timeout: Default lock timeout in seconds (prevents deadlocks)
            blocking_timeout: Maximum time to wait for lock acquisition
            retry_interval: Time between lock acquisition attempts
        """
        self.redis = redis_client
        self.default_timeout = default_timeout
        self.blocking_timeout = blocking_timeout
        self.retry_interval = retry_interval
        self._local_locks = {}  # Track locks owned by this instance

    async def acquire_lock(
        self,
        resource_id: str,
        timeout: Optional[int] = None,
        blocking: bool = True,
        token: Optional[str] = None
    ) -> Optional[str]:
        """
        Acquire a distributed lock for a resource.
        
        Args:
            resource_id: Unique identifier for the resource (e.g., board ID)
            timeout: Lock expiration time in seconds (defaults to self.default_timeout)
            blocking: Whether to wait for lock if not immediately available
            token: Optional token to use as lock value (generated if not provided)
            
        Returns:
            Lock token if acquired, None if failed
        """
        lock_key = f"lock:board:{resource_id}"
        lock_token = token or str(uuid.uuid4())
        timeout = timeout or self.default_timeout
        
        try:
            # Try to acquire lock with SET NX (set if not exists) and expiration
            acquired = await self.redis.set(
                lock_key,
                lock_token,
                nx=True,  # Only set if doesn't exist
                ex=timeout  # Expiration in seconds
            )
            
            if acquired:
                self._local_locks[resource_id] = lock_token
                logger.debug(f"Lock acquired for {resource_id} with token {lock_token}")
                return lock_token
            
            # If blocking, retry until timeout
            if blocking:
                elapsed = 0
                while elapsed < self.blocking_timeout:
                    await asyncio.sleep(self.retry_interval)
                    elapsed += self.retry_interval
                    
                    acquired = await self.redis.set(
                        lock_key,
                        lock_token,
                        nx=True,
                        ex=timeout
                    )
                    
                    if acquired:
                        self._local_locks[resource_id] = lock_token
                        logger.debug(f"Lock acquired for {resource_id} after {elapsed:.1f}s")
                        return lock_token
                
                logger.warning(f"Failed to acquire lock for {resource_id} after {self.blocking_timeout}s")
            
            return None
            
        except RedisError as e:
            logger.error(f"Redis error acquiring lock for {resource_id}: {e}")
            return None

    async def release_lock(
        self,
        resource_id: str,
        token: str
    ) -> bool:
        """
        Release a distributed lock.
        
        Args:
            resource_id: Unique identifier for the resource
            token: Lock token to verify ownership
            
        Returns:
            True if lock was released, False otherwise
        """
        lock_key = f"lock:board:{resource_id}"
        
        # Lua script for atomic check-and-delete
        # This ensures we only delete the lock if we own it
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        
        try:
            result = await self.redis.eval(lua_script, 1, lock_key, token)
            
            if result:
                # Remove from local tracking
                self._local_locks.pop(resource_id, None)
                logger.debug(f"Lock released for {resource_id}")
                return True
            else:
                logger.warning(f"Failed to release lock for {resource_id}: not owner or doesn't exist")
                return False
                
        except RedisError as e:
            logger.error(f"Redis error releasing lock for {resource_id}: {e}")
            return False

    async def extend_lock(
        self,
        resource_id: str,
        token: str,
        additional_time: int = 30
    ) -> bool:
        """
        Extend the expiration time of an existing lock.
        
        Args:
            resource_id: Unique identifier for the resource
            token: Lock token to verify ownership
            additional_time: Additional seconds to extend the lock
            
        Returns:
            True if lock was extended, False otherwise
        """
        lock_key = f"lock:board:{resource_id}"
        
        # Lua script for atomic check-and-extend
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        
        try:
            result = await self.redis.eval(
                lua_script,
                1,
                lock_key,
                token,
                additional_time
            )
            
            if result:
                logger.debug(f"Lock extended for {resource_id} by {additional_time}s")
                return True
            else:
                logger.warning(f"Failed to extend lock for {resource_id}: not owner or doesn't exist")
                return False
                
        except RedisError as e:
            logger.error(f"Redis error extending lock for {resource_id}: {e}")
            return False

    async def is_locked(self, resource_id: str) -> bool:
        """
        Check if a resource is currently locked.
        
        Args:
            resource_id: Unique identifier for the resource
            
        Returns:
            True if resource is locked, False otherwise
        """
        lock_key = f"lock:board:{resource_id}"
        
        try:
            exists = await self.redis.exists(lock_key)
            return bool(exists)
        except RedisError as e:
            logger.error(f"Redis error checking lock for {resource_id}: {e}")
            return False

    async def get_lock_info(self, resource_id: str) -> Optional[dict]:
        """
        Get information about a lock.
        
        Args:
            resource_id: Unique identifier for the resource
            
        Returns:
            Dictionary with lock info (token, ttl) or None if not locked
        """
        lock_key = f"lock:board:{resource_id}"
        
        try:
            # Get lock token and TTL
            token = await self.redis.get(lock_key)
            if not token:
                return None
                
            ttl = await self.redis.ttl(lock_key)
            
            return {
                "resource_id": resource_id,
                "token": token.decode() if isinstance(token, bytes) else token,
                "ttl": ttl,
                "is_owner": resource_id in self._local_locks and 
                           self._local_locks[resource_id] == (token.decode() if isinstance(token, bytes) else token)
            }
            
        except RedisError as e:
            logger.error(f"Redis error getting lock info for {resource_id}: {e}")
            return None

    @asynccontextmanager
    async def lock(
        self,
        resource_id: str,
        timeout: Optional[int] = None,
        blocking: bool = True
    ) -> AsyncIterator[Optional[str]]:
        """
        Context manager for acquiring and releasing locks.
        
        Usage:
            async with lock_manager.lock("board-001") as token:
                if token:
                    # Do work with the locked resource
                    pass
                else:
                    # Failed to acquire lock
                    pass
        
        Args:
            resource_id: Unique identifier for the resource
            timeout: Lock expiration time in seconds
            blocking: Whether to wait for lock if not immediately available
            
        Yields:
            Lock token if acquired, None otherwise
        """
        token = None
        try:
            token = await self.acquire_lock(resource_id, timeout, blocking)
            yield token
        finally:
            if token:
                await self.release_lock(resource_id, token)

    async def clear_expired_locks(self) -> int:
        """
        Clear expired locks (Redis handles this automatically, but this can be used for cleanup).
        
        Returns:
            Number of locks cleared
        """
        pattern = "lock:board:*"
        cleared = 0
        
        try:
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(
                    cursor,
                    match=pattern,
                    count=100
                )
                
                for key in keys:
                    # Check if key has no TTL (shouldn't happen, but safety check)
                    ttl = await self.redis.ttl(key)
                    if ttl == -1:  # No expiration set
                        await self.redis.expire(key, self.default_timeout)
                        cleared += 1
                        logger.warning(f"Set expiration for lock without TTL: {key}")
                
                if cursor == 0:
                    break
                    
            return cleared
            
        except RedisError as e:
            logger.error(f"Redis error clearing expired locks: {e}")
            return cleared

    async def force_unlock(self, resource_id: str) -> bool:
        """
        Force unlock a resource (admin operation, use with caution).
        
        Args:
            resource_id: Unique identifier for the resource
            
        Returns:
            True if lock was removed, False otherwise
        """
        lock_key = f"lock:board:{resource_id}"
        
        try:
            deleted = await self.redis.delete(lock_key)
            if deleted:
                self._local_locks.pop(resource_id, None)
                logger.warning(f"Force unlocked resource {resource_id}")
                return True
            return False
            
        except RedisError as e:
            logger.error(f"Redis error force unlocking {resource_id}: {e}")
            return False


class MultiResourceLockManager(DistributedLockManager):
    """
    Extended lock manager that can handle multiple resources atomically.
    Useful for operations that require locking multiple boards at once.
    """

    async def acquire_multiple_locks(
        self,
        resource_ids: list[str],
        timeout: Optional[int] = None,
        blocking: bool = True
    ) -> Optional[dict[str, str]]:
        """
        Acquire locks for multiple resources atomically.
        
        Args:
            resource_ids: List of resource identifiers
            timeout: Lock expiration time in seconds
            blocking: Whether to wait for locks if not immediately available
            
        Returns:
            Dictionary of resource_id -> token if all acquired, None if any failed
        """
        acquired_locks = {}
        
        try:
            # Try to acquire all locks
            for resource_id in resource_ids:
                token = await self.acquire_lock(resource_id, timeout, blocking)
                if token:
                    acquired_locks[resource_id] = token
                else:
                    # Failed to acquire one lock, release all acquired
                    for rid, tok in acquired_locks.items():
                        await self.release_lock(rid, tok)
                    return None
            
            return acquired_locks
            
        except Exception as e:
            # On any error, release all acquired locks
            logger.error(f"Error acquiring multiple locks: {e}")
            for rid, tok in acquired_locks.items():
                await self.release_lock(rid, tok)
            return None

    async def release_multiple_locks(
        self,
        locks: dict[str, str]
    ) -> dict[str, bool]:
        """
        Release multiple locks.
        
        Args:
            locks: Dictionary of resource_id -> token
            
        Returns:
            Dictionary of resource_id -> success status
        """
        results = {}
        
        for resource_id, token in locks.items():
            results[resource_id] = await self.release_lock(resource_id, token)
        
        return results