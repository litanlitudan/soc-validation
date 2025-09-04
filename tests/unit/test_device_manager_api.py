"""Unit tests for Device Manager API."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock
import json
from datetime import datetime, timedelta

from src.device_manager.api import app
from src.device_manager.models import Board, LeaseRequest, TestSubmission, Lease


client = TestClient(app)


def test_health_check():
    """Test health check endpoint."""
    with patch('src.device_manager.api.get_redis_client') as mock_redis:
        # Mock successful Redis connection
        mock_redis_instance = Mock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_redis_instance.get_client = AsyncMock(return_value=mock_client)
        mock_redis.return_value = mock_redis_instance
        
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "device-manager"
        assert data["version"] == "0.1.0"
        assert data["redis_connected"] is True


def test_health_check_redis_down():
    """Test health check when Redis is down."""
    with patch('src.device_manager.api.get_redis_client') as mock_redis:
        # Mock Redis connection failure
        mock_redis_instance = Mock()
        mock_redis_instance.get_client = AsyncMock(side_effect=Exception("Connection failed"))
        mock_redis.return_value = mock_redis_instance
        
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["redis_connected"] is False


def test_list_boards():
    """Test listing all boards."""
    with patch('src.device_manager.api.boards_config') as mock_config:
        # Mock board configuration
        mock_board = Board(
            board_id="soc-a-001",
            soc_family="socA",
            board_ip="10.1.1.101",
            telnet_port=23,
            location="lab-site-a"
        )
        mock_config.boards = [mock_board]
        
        response = client.get("/api/v1/boards")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["board_id"] == "soc-a-001"
        assert data[0]["soc_family"] == "socA"


def test_get_board():
    """Test getting specific board information."""
    with patch('src.device_manager.api.get_board_by_id') as mock_get_board:
        # Mock board retrieval
        mock_board = Board(
            board_id="soc-a-001",
            soc_family="socA",
            board_ip="10.1.1.101",
            telnet_port=23
        )
        mock_get_board.return_value = mock_board
        
        response = client.get("/api/v1/boards/soc-a-001")
        assert response.status_code == 200
        data = response.json()
        assert data["board_id"] == "soc-a-001"
        assert data["board_ip"] == "10.1.1.101"


def test_get_board_not_found():
    """Test getting non-existent board."""
    with patch('src.device_manager.api.get_board_by_id') as mock_get_board:
        mock_get_board.return_value = None
        
        response = client.get("/api/v1/boards/invalid-board")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


def test_acquire_lease():
    """Test acquiring a board lease."""
    with patch('src.device_manager.api.device_manager') as mock_device_manager:
        # Mock lease response
        mock_lease = Lease(
            lease_id="test-lease-123",
            board_id="soc-a-001",
            board_ip="10.1.1.101",
            telnet_port=23,
            lock_token="token-abc123",
            acquired_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=1800),
            priority=2,
            status="active"
        )
        mock_device_manager.acquire_board = AsyncMock(return_value=mock_lease)
        
        request_data = {
            "board_family": "socA",
            "timeout": 1800,
            "priority": 2
        }
        
        response = client.post("/api/v1/lease", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert "lease_id" in data
        assert data["board_id"] == "soc-a-001"
        assert data["board_ip"] == "10.1.1.101"
        assert data["telnet_port"] == 23


def test_acquire_lease_board_busy():
    """Test acquiring lease when no boards available."""
    with patch('src.device_manager.api.device_manager') as mock_device_manager:
        # Mock no board available
        mock_device_manager.acquire_board = AsyncMock(return_value=None)
        
        request_data = {
            "board_family": "socA",
            "timeout": 1800,
            "priority": 2
        }
        
        response = client.post("/api/v1/lease", json=request_data)
        assert response.status_code == 409
        assert "No available boards" in response.json()["detail"]


def test_release_lease():
    """Test releasing a board lease."""
    with patch('src.device_manager.api.device_manager') as mock_device_manager:
        # Mock successful release
        mock_device_manager.release_board = AsyncMock(return_value=True)
        
        response = client.delete("/api/v1/lease/test-lease-123")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "released"
        assert data["lease_id"] == "test-lease-123"


def test_release_lease_not_found():
    """Test releasing non-existent lease."""
    with patch('src.device_manager.api.device_manager') as mock_device_manager:
        # Mock lease not found
        mock_device_manager.release_board = AsyncMock(return_value=False)
        
        response = client.delete("/api/v1/lease/invalid-lease")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


def test_submit_test():
    """Test submitting a test to the queue."""
    request_data = {
        "test_binary": "/path/to/test",
        "board_family": "socA",
        "priority": 2,
        "timeout": 1800
    }
    
    response = client.post("/api/v1/tests/submit", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert "test_id" in data
    assert data["status"] == "queued"
    assert data["test_binary"] == "/path/to/test"
    assert data["board_family"] == "socA"


def test_get_queue_status():
    """Test getting queue status."""
    with patch('src.device_manager.api.device_manager') as mock_device_manager:
        # Mock queue status
        mock_device_manager.get_queue_status = AsyncMock(return_value={
            "active_tests": 2,
            "available_boards": 3,
            "quarantined_boards": 1
        })
        
        response = client.get("/api/v1/tests/queue")
        assert response.status_code == 200
        data = response.json()
        assert "queue_size" in data
        assert "estimated_wait_time" in data
        assert "active_tests" in data


def test_get_board_status():
    """Test getting board status."""
    with patch('src.device_manager.api.device_manager') as mock_device_manager:
        # Mock board status
        mock_device_manager.get_board_status = AsyncMock(return_value={
            "board_id": "soc-a-001",
            "health_status": "healthy",
            "is_allocated": False,
            "current_lease": None
        })
        
        response = client.get("/api/v1/boards/soc-a-001/status")
        assert response.status_code == 200
        data = response.json()
        assert data["board_id"] == "soc-a-001"
        assert data["health_status"] == "healthy"


def test_get_board_status_not_found():
    """Test getting status for non-existent board."""
    with patch('src.device_manager.api.device_manager') as mock_device_manager:
        # Mock board not found
        mock_device_manager.get_board_status = AsyncMock(return_value={
            "error": "Board not found"
        })
        
        response = client.get("/api/v1/boards/invalid-board/status")
        assert response.status_code == 404
        assert "Board not found" in response.json()["detail"]


def test_extend_lease():
    """Test extending a lease."""
    with patch('src.device_manager.api.device_manager') as mock_device_manager:
        # Mock successful extension
        mock_device_manager.extend_lease = AsyncMock(return_value=True)
        mock_lease = Lease(
            lease_id="test-lease-123",
            board_id="soc-a-001",
            board_ip="10.1.1.101",
            telnet_port=23,
            lock_token="token-abc123",
            acquired_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=3600),
            priority=2,
            status="active"
        )
        mock_device_manager.get_lease_info = AsyncMock(return_value=mock_lease)
        
        response = client.post("/api/v1/lease/test-lease-123/extend?additional_time=1800")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "extended"
        assert data["lease_id"] == "test-lease-123"
        assert data["board_id"] == "soc-a-001"


def test_extend_lease_failed():
    """Test failing to extend a lease."""
    with patch('src.device_manager.api.device_manager') as mock_device_manager:
        # Mock extension failure
        mock_device_manager.extend_lease = AsyncMock(return_value=False)
        
        response = client.post("/api/v1/lease/invalid-lease/extend?additional_time=1800")
        assert response.status_code == 409
        assert "Failed to extend lease" in response.json()["detail"]