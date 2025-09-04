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
from .manager import DeviceManager, AllocationStrategy

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Global instances
device_manager: Optional[DeviceManager] = None
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

    # Initialize Redis connection and device manager
    try:
        redis_client = await initialize_redis()
        lock_manager = DistributedLockManager(
            redis_client=redis_client,
            default_timeout=1800,  # 30 minutes default timeout
            blocking_timeout=30,    # Wait up to 30 seconds for lock
            retry_interval=0.5      # Check every 500ms when blocking
        )

        global device_manager
        device_manager = DeviceManager(
            config=boards_config,
            lock_manager=lock_manager,
            redis_client=redis_client,
            default_lease_timeout=1800,
            max_retries=3,
            quarantine_threshold=3
        )
        logger.info("Redis connection and device manager initialized")
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
    if not device_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Device manager not initialized"
        )

    # Use device manager to acquire board
    lease = await device_manager.acquire_board(request)

    if not lease:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No available boards for family {request.board_family}"
        )

    logger.info(f"Lease {lease.lease_id} acquired for board {lease.board_id}")

    return LeaseResponse(
        lease_id=lease.lease_id,
        board_id=lease.board_id,
        board_ip=lease.board_ip,
        telnet_port=lease.telnet_port,
        expires_at=lease.expires_at
    )


@app.delete("/api/v1/lease/{lease_id}")
async def release_lease(lease_id: str):
    """Release a board lease."""
    if not device_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Device manager not initialized"
        )

    # Use device manager to release board
    released = await device_manager.release_board(lease_id)

    if not released:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lease {lease_id} not found"
        )

    logger.info(f"Lease {lease_id} released")

    return {"status": "released", "lease_id": lease_id}


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
    if not device_manager:
        raise HTTPException(
            status_code=503,
            detail="Device manager not initialized"
        )

    # Get queue status from device manager
    status = await device_manager.get_queue_status()

    # TODO: Integrate with Prefect for actual test queue metrics
    status["queue_size"] = 0
    status["estimated_wait_time"] = 0

    return status


@app.get("/api/v1/boards/{board_id}/status")
async def get_board_status(board_id: str):
    """Get complete status for a specific board."""
    if not device_manager:
        raise HTTPException(
            status_code=503,
            detail="Device manager not initialized"
        )

    # Use device manager to get board status
    status = await device_manager.get_board_status(board_id)

    if "error" in status:
        raise HTTPException(
            status_code=404,
            detail=status["error"]
        )

    return status


@app.post("/api/v1/lease/{lease_id}/extend")
async def extend_lease(lease_id: str, additional_time: int = 1800):
    """Extend an existing board lease."""
    if not device_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Device manager not initialized"
        )

    # Use device manager to extend lease
    extended = await device_manager.extend_lease(lease_id, additional_time)

    if not extended:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Failed to extend lease {lease_id}"
        )

    # Get updated lease info
    lease = await device_manager.get_lease_info(lease_id)

    logger.info(f"Lease {lease_id} extended by {additional_time} seconds")

    return {
        "status": "extended",
        "lease_id": lease_id,
        "board_id": lease.board_id,
        "new_expires_at": lease.expires_at,
        "additional_seconds": additional_time
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)