"""Unit tests for Device Manager API."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
import json
from datetime import datetime, timedelta

from src.device_manager.api import app
from src.device_manager.models import Board, LeaseRequest, TestSubmission


client = TestClient(app)


def test_health_check():
    """Test health check endpoint."""
    with patch('src.device_manager.api.get_redis_client') as mock_redis:
        # Mock successful Redis connection
        mock_redis_instance = Mock()
        mock_redis_instance.ping.return_value = True
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
        mock_redis_instance.ping.side_effect = Exception("Connection failed")
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
            pdu_host="pdu-a.lab.local",
            pdu_outlet=1,
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
    with patch('src.device_manager.api.get_redis_client') as mock_redis, \
         patch('src.device_manager.api.get_board_by_family') as mock_get_board:
        
        # Mock Redis client
        mock_redis_instance = Mock()
        mock_redis_instance.exists.return_value = False
        mock_redis_instance.set.return_value = True
        mock_redis.return_value = mock_redis_instance
        
        # Mock board
        mock_board = Board(
            board_id="soc-a-001",
            soc_family="socA",
            board_ip="10.1.1.101",
            telnet_port=23
        )
        mock_get_board.return_value = mock_board
        
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
    """Test acquiring lease when board is already in use."""
    with patch('src.device_manager.api.get_redis_client') as mock_redis, \
         patch('src.device_manager.api.get_board_by_family') as mock_get_board:
        
        # Mock Redis client - board already locked
        mock_redis_instance = Mock()
        mock_redis_instance.exists.return_value = True
        mock_redis.return_value = mock_redis_instance
        
        # Mock board
        mock_board = Board(
            board_id="soc-a-001",
            soc_family="socA",
            board_ip="10.1.1.101",
            telnet_port=23
        )
        mock_get_board.return_value = mock_board
        
        request_data = {
            "board_family": "socA",
            "timeout": 1800
        }
        
        response = client.post("/api/v1/lease", json=request_data)
        assert response.status_code == 409
        assert "already in use" in response.json()["detail"]


def test_release_lease():
    """Test releasing a board lease."""
    with patch('src.device_manager.api.get_redis_client') as mock_redis:
        # Mock Redis client
        mock_redis_instance = Mock()
        lease_data = {
            "lease_id": "test-lease-123",
            "board_id": "soc-a-001",
            "acquired_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(seconds=1800)).isoformat()
        }
        mock_redis_instance.get.return_value = json.dumps(lease_data)
        mock_redis.return_value = mock_redis_instance
        
        response = client.delete("/api/v1/lease/test-lease-123")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "released"
        assert data["lease_id"] == "test-lease-123"
        assert data["board_id"] == "soc-a-001"


def test_release_lease_not_found():
    """Test releasing non-existent lease."""
    with patch('src.device_manager.api.get_redis_client') as mock_redis:
        # Mock Redis client - lease not found
        mock_redis_instance = Mock()
        mock_redis_instance.get.return_value = None
        mock_redis.return_value = mock_redis_instance
        
        response = client.delete("/api/v1/lease/invalid-lease")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


def test_control_power():
    """Test board power control."""
    with patch('src.device_manager.api.get_board_by_id') as mock_get_board:
        # Mock board with PDU configuration
        mock_board = Board(
            board_id="soc-a-001",
            soc_family="socA",
            board_ip="10.1.1.101",
            telnet_port=23,
            pdu_host="pdu-a.lab.local",
            pdu_outlet=1
        )
        mock_get_board.return_value = mock_board
        
        request_data = {"action": "cycle"}
        
        response = client.post("/api/v1/power/soc-a-001", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["action"] == "cycle"


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
    response = client.get("/api/v1/tests/queue")
    assert response.status_code == 200
    data = response.json()
    assert "queue_size" in data
    assert "estimated_wait_time" in data
    assert "active_tests" in data