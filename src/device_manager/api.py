"""Device Manager API Service."""

import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import redis
import logging
import json

from .models import Board, Lease, LeaseRequest, TestSubmission
from .config import load_boards_config, get_board_by_family, get_board_by_id

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="SoC Validation Device Manager",
    version="0.1.0",
    description="Device management and board allocation service"
)

# Redis client
redis_client = None

def get_redis_client():
    """Get Redis client instance."""
    global redis_client
    if redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        redis_client = redis.from_url(redis_url, decode_responses=True)
    return redis_client


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


# Load board configuration
boards_config = load_boards_config(os.getenv("BOARDS_CONFIG_PATH", "/app/config/boards.yaml"))


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    # Check Redis connection
    redis_connected = False
    try:
        r = get_redis_client()
        r.ping()
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
    r = get_redis_client()
    
    # Find available board of the requested family
    board = get_board_by_family(boards_config, request.board_family)
    if not board:
        raise HTTPException(
            status_code=404, 
            detail=f"No available boards for family {request.board_family}"
        )
    
    # Try to acquire lock using Redis SET NX
    lease_id = str(uuid.uuid4())
    lock_key = f"board_lock:{board.board_id}"
    lease_key = f"lease:{lease_id}"
    
    # Check if board is already locked
    if r.exists(lock_key):
        # Board is already in use
        raise HTTPException(
            status_code=409,
            detail=f"Board {board.board_id} is already in use"
        )
    
    # Try to acquire the lock
    expires_at = datetime.now() + timedelta(seconds=request.timeout)
    lease_data = {
        "lease_id": lease_id,
        "board_id": board.board_id,
        "acquired_at": datetime.now().isoformat(),
        "expires_at": expires_at.isoformat(),
        "priority": request.priority
    }
    
    # Set lock with expiration
    lock_acquired = r.set(lock_key, lease_id, nx=True, ex=request.timeout)
    
    if not lock_acquired:
        raise HTTPException(
            status_code=409,
            detail=f"Failed to acquire lock for board {board.board_id}"
        )
    
    # Store lease information
    r.set(lease_key, json.dumps(lease_data), ex=request.timeout)
    
    # Update board last used time
    board.last_used = datetime.now()
    
    logger.info(f"Lease {lease_id} acquired for board {board.board_id}")
    
    return LeaseResponse(
        lease_id=lease_id,
        board_id=board.board_id,
        board_ip=board.board_ip,
        telnet_port=board.telnet_port,
        expires_at=expires_at
    )


@app.delete("/api/v1/lease/{lease_id}")
async def release_lease(lease_id: str):
    """Release a board lease."""
    r = get_redis_client()
    
    lease_key = f"lease:{lease_id}"
    lease_data = r.get(lease_key)
    
    if not lease_data:
        raise HTTPException(status_code=404, detail=f"Lease {lease_id} not found")
    
    lease = json.loads(lease_data)
    board_id = lease["board_id"]
    lock_key = f"board_lock:{board_id}"
    
    # Delete the lock and lease
    r.delete(lock_key)
    r.delete(lease_key)
    
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


@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    logger.info("Device Manager starting up...")
    logger.info(f"Loaded {len(boards_config.boards)} boards from configuration")
    
    # Test Redis connection
    try:
        r = get_redis_client()
        r.ping()
        logger.info("Redis connection established")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    logger.info("Device Manager shutting down...")
    
    # Clean up Redis connection
    global redis_client
    if redis_client:
        redis_client.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)