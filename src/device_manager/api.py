"""Device Manager API Service."""

import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel
import logging
import json

from .models import Board, Lease, LeaseRequest, TestSubmission
from .config import load_boards_config, get_board_by_family, get_board_by_id
from .redis_client import get_redis_client, initialize_redis, cleanup_redis
from .lock_manager import DistributedLockManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Global instances
lock_manager: Optional[DistributedLockManager] = None
boards_config = None

# Lifespan context manager for startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info("Device Manager starting up...")
    
    # Load board configuration
    global boards_config
    boards_config = load_boards_config(os.getenv("BOARDS_CONFIG_PATH", "/app/config/boards.yaml"))
    logger.info(f"Loaded {len(boards_config.boards)} boards from configuration")
    
    # Initialize Redis connection and lock manager
    try:
        redis_client = await initialize_redis()
        global lock_manager
        lock_manager = DistributedLockManager(
            redis_client=redis_client,
            default_timeout=1800,  # 30 minutes default timeout
            blocking_timeout=30,    # Wait up to 30 seconds for lock
            retry_interval=0.5      # Check every 500ms when blocking
        )
        logger.info("Redis connection and lock manager initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Redis: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Device Manager shutting down...")
    
    # Clean up Redis connection
    await cleanup_redis()


# Create FastAPI app
app = FastAPI(
    title="SoC Validation Device Manager",
    version="0.1.0",
    description="Device management and board allocation service",
    lifespan=lifespan
)


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    version: str
    redis_connected: bool


class LeaseResponse(BaseModel):
    """Lease allocation response."""
    lease_id: str
    board_id: str
    board_ip: str
    telnet_port: int
    expires_at: datetime
    

class PowerAction(BaseModel):
    """Power control action."""
    action: str  # on, off, cycle


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    # Check Redis connection
    redis_connected = False
    try:
        redis_client = get_redis_client()
        client = await redis_client.get_client()
        await client.ping()
        redis_connected = True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
    
    return HealthResponse(
        status="healthy" if redis_connected else "degraded",
        service="device-manager",
        version="0.1.0",
        redis_connected=redis_connected
    )


@app.get("/api/v1/boards", response_model=List[Board])
async def list_boards():
    """List all configured boards."""
    if boards_config is None:
        return []
    return boards_config.boards


@app.get("/api/v1/boards/{board_id}", response_model=Board)
async def get_board(board_id: str):
    """Get specific board information."""
    board = get_board_by_id(boards_config, board_id)
    if not board:
        raise HTTPException(status_code=404, detail=f"Board {board_id} not found")
    return board


@app.post("/api/v1/lease", response_model=LeaseResponse)
async def acquire_lease(request: LeaseRequest):
    """Acquire a board lease."""
    if not lock_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lock manager not initialized"
        )
    
    # Find available board of the requested family
    available_boards = [b for b in boards_config.boards if b.board_family == request.board_family]
    if not available_boards:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No boards found for family {request.board_family}"
        )
    
    # Try to acquire a lock on any available board
    lease_id = str(uuid.uuid4())
    board_acquired = None
    lock_token = None
    
    for board in available_boards:
        # Check if board is healthy
        if board.health_status != "healthy":
            logger.debug(f"Skipping unhealthy board {board.board_id}")
            continue
        
        # Try to acquire lock on this board
        lock_token = await lock_manager.acquire_lock(
            resource_id=board.board_id,
            timeout=request.timeout,
            blocking=False  # Don't block, try next board
        )
        
        if lock_token:
            board_acquired = board
            break
    
    if not board_acquired or not lock_token:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No available boards for family {request.board_family}"
        )
    
    # Store lease information in Redis
    expires_at = datetime.now() + timedelta(seconds=request.timeout)
    lease_data = {
        "lease_id": lease_id,
        "board_id": board_acquired.board_id,
        "lock_token": lock_token,
        "acquired_at": datetime.now().isoformat(),
        "expires_at": expires_at.isoformat(),
        "priority": request.priority
    }
    
    # Store lease data
    redis_client = get_redis_client()
    client = await redis_client.get_client()
    lease_key = f"lease:{lease_id}"
    await client.set(lease_key, json.dumps(lease_data), ex=request.timeout)
    
    # Update board last used time
    board_acquired.last_used = datetime.now()
    
    logger.info(f"Lease {lease_id} acquired for board {board_acquired.board_id}")
    
    return LeaseResponse(
        lease_id=lease_id,
        board_id=board_acquired.board_id,
        board_ip=board_acquired.board_ip,
        telnet_port=board_acquired.telnet_port,
        expires_at=expires_at
    )


@app.delete("/api/v1/lease/{lease_id}")
async def release_lease(lease_id: str):
    """Release a board lease."""
    if not lock_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lock manager not initialized"
        )
    
    # Get lease information
    redis_client = get_redis_client()
    client = await redis_client.get_client()
    lease_key = f"lease:{lease_id}"
    lease_data = await client.get(lease_key)
    
    if not lease_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lease {lease_id} not found"
        )
    
    lease = json.loads(lease_data)
    board_id = lease["board_id"]
    lock_token = lease.get("lock_token")
    
    # Release the lock using the lock manager
    if lock_token:
        released = await lock_manager.release_lock(board_id, lock_token)
        if not released:
            logger.warning(f"Failed to release lock for board {board_id} with token {lock_token}")
    
    # Delete the lease information
    await client.delete(lease_key)
    
    logger.info(f"Lease {lease_id} released for board {board_id}")
    
    return {"status": "released", "lease_id": lease_id, "board_id": board_id}


@app.post("/api/v1/power/{board_id}")
async def control_power(board_id: str, action: PowerAction):
    """Control board power via PDU."""
    board = get_board_by_id(boards_config, board_id)
    if not board:
        raise HTTPException(status_code=404, detail=f"Board {board_id} not found")
    
    if not board.pdu_host or not board.pdu_outlet:
        raise HTTPException(
            status_code=400,
            detail=f"Board {board_id} does not have PDU configuration"
        )
    
    # TODO: Implement actual PDU control
    # For now, just log the action
    logger.info(f"Power {action.action} requested for board {board_id} "
                f"(PDU: {board.pdu_host}, Outlet: {board.pdu_outlet})")
    
    return {
        "status": "success",
        "board_id": board_id,
        "action": action.action,
        "message": f"Power {action.action} command sent"
    }


@app.post("/api/v1/tests/submit")
async def submit_test(submission: TestSubmission):
    """Submit a test to the queue."""
    # TODO: Integrate with Prefect to create a deployment run
    test_id = str(uuid.uuid4())
    
    logger.info(f"Test {test_id} submitted: {submission.test_binary} on {submission.board_family}")
    
    return {
        "test_id": test_id,
        "status": "queued",
        "test_binary": submission.test_binary,
        "board_family": submission.board_family,
        "priority": submission.priority
    }


@app.get("/api/v1/tests/queue")
async def get_queue_status():
    """Get current queue status."""
    # TODO: Query Prefect for actual queue status
    return {
        "queue_size": 0,
        "estimated_wait_time": 0,
        "active_tests": 0
    }


@app.get("/api/v1/boards/{board_id}/lock-status")
async def get_board_lock_status(board_id: str):
    """Get lock status for a specific board."""
    if not lock_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lock manager not initialized"
        )
    
    # Check if board exists
    board = get_board_by_id(boards_config, board_id)
    if not board:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board {board_id} not found"
        )
    
    # Get lock information
    lock_info = await lock_manager.get_lock_info(board_id)
    
    if lock_info:
        return {
            "board_id": board_id,
            "is_locked": True,
            "lock_token": lock_info["token"],
            "ttl_seconds": lock_info["ttl"],
            "is_owner": lock_info["is_owner"]
        }
    else:
        return {
            "board_id": board_id,
            "is_locked": False,
            "lock_token": None,
            "ttl_seconds": 0,
            "is_owner": False
        }


@app.post("/api/v1/lease/{lease_id}/extend")
async def extend_lease(lease_id: str, additional_time: int = 1800):
    """Extend an existing board lease."""
    if not lock_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lock manager not initialized"
        )
    
    # Get lease information
    redis_client = get_redis_client()
    client = await redis_client.get_client()
    lease_key = f"lease:{lease_id}"
    lease_data = await client.get(lease_key)
    
    if not lease_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lease {lease_id} not found"
        )
    
    lease = json.loads(lease_data)
    board_id = lease["board_id"]
    lock_token = lease.get("lock_token")
    
    # Extend the lock
    if lock_token:
        extended = await lock_manager.extend_lock(board_id, lock_token, additional_time)
        if not extended:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Failed to extend lock for board {board_id}"
            )
    
    # Update lease expiration
    new_expires = datetime.now() + timedelta(seconds=additional_time)
    lease["expires_at"] = new_expires.isoformat()
    await client.set(lease_key, json.dumps(lease), ex=additional_time)
    
    logger.info(f"Lease {lease_id} extended for board {board_id} by {additional_time} seconds")
    
    return {
        "status": "extended",
        "lease_id": lease_id,
        "board_id": board_id,
        "new_expires_at": new_expires,
        "additional_seconds": additional_time
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)