"""Core device manager for board allocation and leasing."""

import uuid
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from enum import Enum

from .models import Board, Lease, LeaseRequest
from .config import (
    BoardsConfig,
    get_board_by_id,
    get_available_boards,
    update_board_health,
    quarantine_board
)
from .lock_manager import DistributedLockManager
from .redis_client import RedisClient

logger = logging.getLogger(__name__)


class LeaseStatus(Enum):
    """Lease status enumeration."""
    ACTIVE = "active"
    EXPIRED = "expired"
    RELEASED = "released"
    FAILED = "failed"


class AllocationStrategy(Enum):
    """Board allocation strategy."""
    FIRST_AVAILABLE = "first_available"
    LEAST_USED = "least_used"
    RANDOM = "random"
    LOCATION_AFFINITY = "location_affinity"


class DeviceManager:
    """
    Core device manager for board allocation and leasing.
    
    Handles:
    - Board allocation with various strategies
    - Lease lifecycle management
    - Health status tracking
    - Automatic quarantine on failures
    """
    
    def __init__(
        self,
        config: BoardsConfig,
        lock_manager: DistributedLockManager,
        redis_client: RedisClient,
        default_lease_timeout: int = 1800,  # 30 minutes
        max_retries: int = 3,
        quarantine_threshold: int = 3
    ):
        """
        Initialize the device manager.
        
        Args:
            config: Board configuration
            lock_manager: Distributed lock manager for atomic operations
            redis_client: Redis client for state management
            default_lease_timeout: Default lease timeout in seconds
            max_retries: Maximum retry attempts for board allocation
            quarantine_threshold: Failures before auto-quarantine
        """
        self.config = config
        self.lock_manager = lock_manager
        self.redis_client = redis_client
        self.default_lease_timeout = default_lease_timeout
        self.max_retries = max_retries
        self.quarantine_threshold = quarantine_threshold
        
        logger.info(
            f"DeviceManager initialized with {len(config.boards)} boards, "
            f"timeout={default_lease_timeout}s, retries={max_retries}"
        )
    
    async def acquire_board(
        self,
        request: LeaseRequest,
        strategy: AllocationStrategy = AllocationStrategy.FIRST_AVAILABLE
    ) -> Optional[Lease]:
        """
        Acquire a board lease based on the request.
        
        Args:
            request: Lease request parameters
            strategy: Allocation strategy to use
            
        Returns:
            Lease object if successful, None otherwise
        """
        # Get available boards for the requested family
        available_boards = self._get_candidate_boards(request.board_family, strategy)
        
        if not available_boards:
            logger.warning(f"No available boards for family {request.board_family}")
            return None
        
        # Try to acquire a board with retries
        for attempt in range(self.max_retries):
            for board in available_boards:
                lease = await self._try_acquire_board(board, request)
                if lease:
                    logger.info(
                        f"Successfully acquired board {board.board_id} "
                        f"for family {request.board_family} (attempt {attempt + 1})"
                    )
                    return lease
            
            # Brief delay before retry
            if attempt < self.max_retries - 1:
                import asyncio
                await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
        
        logger.error(
            f"Failed to acquire board for family {request.board_family} "
            f"after {self.max_retries} attempts"
        )
        return None
    
    async def _try_acquire_board(
        self,
        board: Board,
        request: LeaseRequest
    ) -> Optional[Lease]:
        """
        Try to acquire a specific board.
        
        Args:
            board: Board to acquire
            request: Lease request
            
        Returns:
            Lease if successful, None otherwise
        """
        # Skip unhealthy boards
        if board.health_status != "healthy":
            logger.debug(f"Skipping unhealthy board {board.board_id}")
            return None
        
        # Try to acquire lock
        timeout = request.timeout or self.default_lease_timeout
        lock_token = await self.lock_manager.acquire_lock(
            resource_id=board.board_id,
            timeout=timeout,
            blocking=False  # Don't block, try next board
        )
        
        if not lock_token:
            logger.debug(f"Board {board.board_id} is already locked")
            return None
        
        # Create lease object
        lease_id = str(uuid.uuid4())
        now = datetime.now()
        expires_at = now + timedelta(seconds=timeout)
        
        lease = Lease(
            lease_id=lease_id,
            board_id=board.board_id,
            board_ip=board.board_ip,
            telnet_port=board.telnet_port,
            acquired_at=now,
            expires_at=expires_at,
            lock_token=lock_token,
            priority=request.priority
        )
        
        # Store lease in Redis
        await self._store_lease(lease)
        
        # Update board last used time
        board.last_used = now
        
        return lease
    
    async def release_board(self, lease_id: str) -> bool:
        """
        Release a board lease.
        
        Args:
            lease_id: Lease ID to release
            
        Returns:
            True if successful, False otherwise
        """
        # Get lease from Redis
        lease = await self._get_lease(lease_id)
        if not lease:
            logger.warning(f"Lease {lease_id} not found")
            return False
        
        # Release the lock
        released = await self.lock_manager.release_lock(
            lease.board_id,
            lease.lock_token
        )
        
        if not released:
            logger.error(
                f"Failed to release lock for board {lease.board_id} "
                f"(lease {lease_id})"
            )
            # Continue to clean up lease anyway
        
        # Delete lease from Redis
        await self._delete_lease(lease_id)
        
        # Update lease status
        lease.status = LeaseStatus.RELEASED.value
        
        logger.info(f"Released board {lease.board_id} (lease {lease_id})")
        return True
    
    async def extend_lease(
        self,
        lease_id: str,
        additional_time: int = 1800
    ) -> bool:
        """
        Extend an existing lease.
        
        Args:
            lease_id: Lease to extend
            additional_time: Additional time in seconds
            
        Returns:
            True if successful, False otherwise
        """
        # Get lease from Redis
        lease = await self._get_lease(lease_id)
        if not lease:
            logger.warning(f"Lease {lease_id} not found")
            return False
        
        # Extend the lock
        extended = await self.lock_manager.extend_lock(
            lease.board_id,
            lease.lock_token,
            additional_time
        )
        
        if not extended:
            logger.error(f"Failed to extend lock for lease {lease_id}")
            return False
        
        # Update lease expiration
        lease.expires_at = datetime.now() + timedelta(seconds=additional_time)
        await self._store_lease(lease)
        
        logger.info(
            f"Extended lease {lease_id} for board {lease.board_id} "
            f"by {additional_time} seconds"
        )
        return True
    
    async def get_lease_info(self, lease_id: str) -> Optional[Lease]:
        """
        Get information about a lease.
        
        Args:
            lease_id: Lease ID
            
        Returns:
            Lease object if found, None otherwise
        """
        return await self._get_lease(lease_id)
    
    async def get_board_status(self, board_id: str) -> Dict[str, Any]:
        """
        Get current status of a board.
        
        Args:
            board_id: Board ID
            
        Returns:
            Status dictionary
        """
        board = get_board_by_id(self.config, board_id)
        if not board:
            return {"error": f"Board {board_id} not found"}
        
        # Check if board is locked
        lock_info = await self.lock_manager.get_lock_info(board_id)
        
        # Get active lease if any
        lease = None
        if lock_info and lock_info.get("is_locked"):
            # Find lease by lock token
            lease = await self._find_lease_by_board(board_id)
        
        return {
            "board_id": board_id,
            "soc_family": board.soc_family,
            "health_status": board.health_status,
            "failure_count": board.failure_count,
            "is_locked": bool(lock_info and lock_info.get("is_locked")),
            "lease_id": lease.lease_id if lease else None,
            "expires_at": lease.expires_at.isoformat() if lease else None,
            "last_used": board.last_used.isoformat() if board.last_used else None
        }
    
    async def report_failure(
        self,
        board_id: str,
        reason: str = "",
        quarantine: bool = True
    ) -> bool:
        """
        Report a board failure and potentially quarantine it.
        
        Args:
            board_id: Board that failed
            reason: Failure reason
            quarantine: Whether to auto-quarantine after threshold
            
        Returns:
            True if board was quarantined, False otherwise
        """
        board = get_board_by_id(self.config, board_id)
        if not board:
            logger.error(f"Board {board_id} not found")
            return False
        
        # Increment failure count
        board.failure_count += 1
        logger.warning(
            f"Board {board_id} failure #{board.failure_count}: {reason}"
        )
        
        # Check if we should quarantine
        if quarantine and board.failure_count >= self.quarantine_threshold:
            quarantine_board(self.config, board_id, reason)
            logger.error(
                f"Board {board_id} quarantined after {board.failure_count} failures"
            )
            return True
        
        return False
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """
        Get current queue and allocation status.
        
        Returns:
            Status dictionary with queue metrics
        """
        # Count boards by status
        total_boards = len(self.config.boards)
        healthy_boards = len(self.config.get_healthy_boards())
        
        # Count active leases
        active_leases = await self._count_active_leases()
        
        # Get boards by family
        families = {}
        for family in self.config.get_families():
            boards = self.config.get_boards_by_family(family)
            available = len([b for b in boards if b.health_status == "healthy"])
            families[family] = {
                "total": len(boards),
                "available": available
            }
        
        return {
            "total_boards": total_boards,
            "healthy_boards": healthy_boards,
            "active_leases": active_leases,
            "available_boards": healthy_boards - active_leases,
            "families": families,
            "quarantine_threshold": self.quarantine_threshold
        }
    
    def _get_candidate_boards(
        self,
        family: str,
        strategy: AllocationStrategy
    ) -> List[Board]:
        """
        Get candidate boards for allocation based on strategy.
        
        Args:
            family: Board family
            strategy: Allocation strategy
            
        Returns:
            Ordered list of candidate boards
        """
        boards = get_available_boards(self.config, family)
        
        if strategy == AllocationStrategy.LEAST_USED:
            # Sort by last used time (oldest first)
            boards.sort(key=lambda b: b.last_used or datetime.min)
        elif strategy == AllocationStrategy.RANDOM:
            import random
            random.shuffle(boards)
        # FIRST_AVAILABLE uses default order
        
        return boards
    
    async def _store_lease(self, lease: Lease) -> None:
        """Store lease in Redis."""
        import json
        client = await self.redis_client.get_client()
        lease_key = f"lease:{lease.lease_id}"
        lease_data = {
            "lease_id": lease.lease_id,
            "board_id": lease.board_id,
            "board_ip": lease.board_ip,
            "telnet_port": lease.telnet_port,
            "lock_token": lease.lock_token,
            "acquired_at": lease.acquired_at.isoformat(),
            "expires_at": lease.expires_at.isoformat(),
            "priority": lease.priority,
            "status": lease.status
        }
        
        # Calculate TTL based on expiration
        ttl = int((lease.expires_at - datetime.now()).total_seconds())
        if ttl > 0:
            await client.set(lease_key, json.dumps(lease_data), ex=ttl)
    
    async def _get_lease(self, lease_id: str) -> Optional[Lease]:
        """Get lease from Redis."""
        import json
        client = await self.redis_client.get_client()
        lease_key = f"lease:{lease_id}"
        lease_data = await client.get(lease_key)
        
        if not lease_data:
            return None
        
        data = json.loads(lease_data)
        return Lease(
            lease_id=data["lease_id"],
            board_id=data["board_id"],
            board_ip=data["board_ip"],
            telnet_port=data["telnet_port"],
            lock_token=data["lock_token"],
            acquired_at=datetime.fromisoformat(data["acquired_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            priority=data["priority"],
            status=data.get("status", LeaseStatus.ACTIVE.value)
        )
    
    async def _delete_lease(self, lease_id: str) -> None:
        """Delete lease from Redis."""
        client = await self.redis_client.get_client()
        lease_key = f"lease:{lease_id}"
        await client.delete(lease_key)
    
    async def _find_lease_by_board(self, board_id: str) -> Optional[Lease]:
        """Find active lease for a board."""
        client = await self.redis_client.get_client()
        
        # Scan for all lease keys
        cursor = 0
        while True:
            cursor, keys = await client.scan(
                cursor=cursor,
                match="lease:*",
                count=100
            )
            
            for key in keys:
                lease_data = await client.get(key)
                if lease_data:
                    import json
                    data = json.loads(lease_data)
                    if data["board_id"] == board_id:
                        lease_id = key.split(":")[-1]
                        return await self._get_lease(lease_id)
            
            if cursor == 0:
                break
        
        return None
    
    async def _count_active_leases(self) -> int:
        """Count active leases in Redis."""
        client = await self.redis_client.get_client()
        
        count = 0
        cursor = 0
        while True:
            cursor, keys = await client.scan(
                cursor=cursor,
                match="lease:*",
                count=100
            )
            count += len(keys)
            
            if cursor == 0:
                break
        
        return count