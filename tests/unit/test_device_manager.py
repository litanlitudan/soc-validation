"""Unit tests for device manager core functionality."""

import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import json

from src.device_manager.manager import (
    DeviceManager,
    LeaseStatus,
    AllocationStrategy
)
from src.device_manager.models import Board, Lease, LeaseRequest
from src.device_manager.config import BoardsConfig


@pytest.fixture
def sample_boards():
    """Create sample boards for testing."""
    return [
        Board(
            board_id="soc-a-001",
            soc_family="socA",
            board_ip="10.1.1.101",
            telnet_port=23,
            location="lab-site-a",
            health_status="healthy"
        ),
        Board(
            board_id="soc-a-002",
            soc_family="socA",
            board_ip="10.1.1.102",
            telnet_port=23,
            location="lab-site-a",
            health_status="healthy"
        ),
        Board(
            board_id="soc-b-001",
            soc_family="socB",
            board_ip="10.1.2.101",
            telnet_port=23,
            location="lab-site-b",
            health_status="healthy"
        ),
        Board(
            board_id="soc-b-002",
            soc_family="socB",
            board_ip="10.1.2.102",
            telnet_port=23,
            location="lab-site-b",
            health_status="quarantined"
        )
    ]


@pytest.fixture
def board_config(sample_boards):
    """Create board configuration."""
    return BoardsConfig(boards=sample_boards)


@pytest.fixture
def mock_lock_manager():
    """Create mock lock manager."""
    mock = AsyncMock()
    mock.acquire_lock = AsyncMock()
    mock.release_lock = AsyncMock()
    mock.extend_lock = AsyncMock()
    mock.get_lock_info = AsyncMock()
    return mock


@pytest.fixture
def mock_redis_client():
    """Create mock Redis client."""
    mock = AsyncMock()
    mock.get_client = AsyncMock()
    return mock


@pytest.fixture
async def device_manager(board_config, mock_lock_manager, mock_redis_client):
    """Create device manager instance."""
    return DeviceManager(
        config=board_config,
        lock_manager=mock_lock_manager,
        redis_client=mock_redis_client,
        default_lease_timeout=1800,
        max_retries=3,
        quarantine_threshold=3
    )


class TestDeviceManagerInit:
    """Test device manager initialization."""
    
    def test_init_with_defaults(self, board_config, mock_lock_manager, mock_redis_client):
        """Test initialization with default parameters."""
        dm = DeviceManager(
            config=board_config,
            lock_manager=mock_lock_manager,
            redis_client=mock_redis_client
        )
        
        assert dm.config == board_config
        assert dm.lock_manager == mock_lock_manager
        assert dm.redis_client == mock_redis_client
        assert dm.default_lease_timeout == 1800
        assert dm.max_retries == 3
        assert dm.quarantine_threshold == 3
    
    def test_init_with_custom_values(self, board_config, mock_lock_manager, mock_redis_client):
        """Test initialization with custom parameters."""
        dm = DeviceManager(
            config=board_config,
            lock_manager=mock_lock_manager,
            redis_client=mock_redis_client,
            default_lease_timeout=3600,
            max_retries=5,
            quarantine_threshold=10
        )
        
        assert dm.default_lease_timeout == 3600
        assert dm.max_retries == 5
        assert dm.quarantine_threshold == 10


class TestBoardAcquisition:
    """Test board acquisition functionality."""
    
    @pytest.mark.asyncio
    async def test_acquire_board_success(self, device_manager, mock_lock_manager, mock_redis_client):
        """Test successful board acquisition."""
        # Setup mocks
        lock_token = "token-123"
        mock_lock_manager.acquire_lock.return_value = lock_token
        
        redis_mock = AsyncMock()
        redis_mock.set = AsyncMock()
        mock_redis_client.get_client.return_value = redis_mock
        
        # Create request
        request = LeaseRequest(
            board_family="socA",
            timeout=1800,
            priority=2
        )
        
        # Acquire board
        lease = await device_manager.acquire_board(request)
        
        # Verify
        assert lease is not None
        assert lease.board_id in ["soc-a-001", "soc-a-002"]
        assert lease.board_ip in ["10.1.1.101", "10.1.1.102"]
        assert lease.lock_token == lock_token
        assert lease.priority == 2
        
        # Check lock was acquired
        mock_lock_manager.acquire_lock.assert_called_once()
        
        # Check lease was stored in Redis
        redis_mock.set.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_acquire_board_no_available(self, device_manager):
        """Test acquisition when no boards available."""
        request = LeaseRequest(
            board_family="socC",  # Non-existent family
            timeout=1800,
            priority=2
        )
        
        lease = await device_manager.acquire_board(request)
        assert lease is None
    
    @pytest.mark.asyncio
    async def test_acquire_board_all_locked(self, device_manager, mock_lock_manager):
        """Test acquisition when all boards are locked."""
        # Mock all lock attempts to fail
        mock_lock_manager.acquire_lock.return_value = None
        
        request = LeaseRequest(
            board_family="socA",
            timeout=1800,
            priority=1
        )
        
        lease = await device_manager.acquire_board(request)
        assert lease is None
        
        # Should have tried multiple times due to retries
        assert mock_lock_manager.acquire_lock.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_acquire_board_skip_unhealthy(self, device_manager, mock_lock_manager, mock_redis_client):
        """Test that unhealthy boards are skipped."""
        # Setup successful lock for healthy board
        mock_lock_manager.acquire_lock.return_value = "token-123"
        
        redis_mock = AsyncMock()
        redis_mock.set = AsyncMock()
        mock_redis_client.get_client.return_value = redis_mock
        
        request = LeaseRequest(
            board_family="socB",
            timeout=1800,
            priority=2
        )
        
        lease = await device_manager.acquire_board(request)
        
        # Should get the healthy board, not the quarantined one
        assert lease is not None
        assert lease.board_id == "soc-b-001"
        assert lease.board_ip == "10.1.2.101"
    
    @pytest.mark.asyncio
    async def test_acquire_board_with_strategy(self, device_manager, mock_lock_manager, mock_redis_client):
        """Test different allocation strategies."""
        mock_lock_manager.acquire_lock.return_value = "token-123"
        
        redis_mock = AsyncMock()
        redis_mock.set = AsyncMock()
        mock_redis_client.get_client.return_value = redis_mock
        
        request = LeaseRequest(board_family="socA")
        
        # Test FIRST_AVAILABLE strategy (default)
        lease = await device_manager.acquire_board(
            request,
            strategy=AllocationStrategy.FIRST_AVAILABLE
        )
        assert lease is not None
        
        # Test LEAST_USED strategy
        lease = await device_manager.acquire_board(
            request,
            strategy=AllocationStrategy.LEAST_USED
        )
        assert lease is not None
        
        # Test RANDOM strategy
        lease = await device_manager.acquire_board(
            request,
            strategy=AllocationStrategy.RANDOM
        )
        assert lease is not None


class TestBoardRelease:
    """Test board release functionality."""
    
    @pytest.mark.asyncio
    async def test_release_board_success(self, device_manager, mock_lock_manager, mock_redis_client):
        """Test successful board release."""
        lease_id = "lease-123"
        board_id = "soc-a-001"
        lock_token = "token-123"
        
        # Mock Redis to return lease data
        lease_data = {
            "lease_id": lease_id,
            "board_id": board_id,
            "board_ip": "10.1.1.101",
            "telnet_port": 23,
            "lock_token": lock_token,
            "acquired_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(minutes=30)).isoformat(),
            "priority": 2,
            "status": "active"
        }
        
        redis_mock = AsyncMock()
        redis_mock.get.return_value = json.dumps(lease_data)
        redis_mock.delete = AsyncMock()
        mock_redis_client.get_client.return_value = redis_mock
        
        # Mock successful lock release
        mock_lock_manager.release_lock.return_value = True
        
        # Release board
        result = await device_manager.release_board(lease_id)
        
        assert result is True
        mock_lock_manager.release_lock.assert_called_once_with(board_id, lock_token)
        redis_mock.delete.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_release_board_not_found(self, device_manager, mock_redis_client):
        """Test releasing non-existent lease."""
        redis_mock = AsyncMock()
        redis_mock.get.return_value = None
        mock_redis_client.get_client.return_value = redis_mock
        
        result = await device_manager.release_board("non-existent-lease")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_release_board_lock_failure(self, device_manager, mock_lock_manager, mock_redis_client):
        """Test release when lock release fails."""
        lease_id = "lease-123"
        
        lease_data = {
            "lease_id": lease_id,
            "board_id": "soc-a-001",
            "board_ip": "10.1.1.101",
            "telnet_port": 23,
            "lock_token": "token-123",
            "acquired_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(minutes=30)).isoformat(),
            "priority": 2,
            "status": "active"
        }
        
        redis_mock = AsyncMock()
        redis_mock.get.return_value = json.dumps(lease_data)
        redis_mock.delete = AsyncMock()
        mock_redis_client.get_client.return_value = redis_mock
        
        # Mock lock release failure
        mock_lock_manager.release_lock.return_value = False
        
        # Should still clean up lease
        result = await device_manager.release_board(lease_id)
        assert result is True
        redis_mock.delete.assert_called_once()


class TestLeaseExtension:
    """Test lease extension functionality."""
    
    @pytest.mark.asyncio
    async def test_extend_lease_success(self, device_manager, mock_lock_manager, mock_redis_client):
        """Test successful lease extension."""
        lease_id = "lease-123"
        additional_time = 1800
        
        lease_data = {
            "lease_id": lease_id,
            "board_id": "soc-a-001",
            "board_ip": "10.1.1.101",
            "telnet_port": 23,
            "lock_token": "token-123",
            "acquired_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(minutes=30)).isoformat(),
            "priority": 2,
            "status": "active"
        }
        
        redis_mock = AsyncMock()
        redis_mock.get.return_value = json.dumps(lease_data)
        redis_mock.set = AsyncMock()
        mock_redis_client.get_client.return_value = redis_mock
        
        mock_lock_manager.extend_lock.return_value = True
        
        result = await device_manager.extend_lease(lease_id, additional_time)
        
        assert result is True
        mock_lock_manager.extend_lock.assert_called_once()
        redis_mock.set.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_extend_lease_not_found(self, device_manager, mock_redis_client):
        """Test extending non-existent lease."""
        redis_mock = AsyncMock()
        redis_mock.get.return_value = None
        mock_redis_client.get_client.return_value = redis_mock
        
        result = await device_manager.extend_lease("non-existent")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_extend_lease_lock_failure(self, device_manager, mock_lock_manager, mock_redis_client):
        """Test extension when lock extend fails."""
        lease_id = "lease-123"
        
        lease_data = {
            "lease_id": lease_id,
            "board_id": "soc-a-001",
            "board_ip": "10.1.1.101",
            "telnet_port": 23,
            "lock_token": "token-123",
            "acquired_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(minutes=30)).isoformat(),
            "priority": 2,
            "status": "active"
        }
        
        redis_mock = AsyncMock()
        redis_mock.get.return_value = json.dumps(lease_data)
        mock_redis_client.get_client.return_value = redis_mock
        
        mock_lock_manager.extend_lock.return_value = False
        
        result = await device_manager.extend_lease(lease_id)
        assert result is False


class TestBoardStatus:
    """Test board status functionality."""
    
    @pytest.mark.asyncio
    async def test_get_board_status_unlocked(self, device_manager, mock_lock_manager):
        """Test getting status of unlocked board."""
        board_id = "soc-a-001"
        
        mock_lock_manager.get_lock_info.return_value = None
        
        status = await device_manager.get_board_status(board_id)
        
        assert status["board_id"] == board_id
        assert status["soc_family"] == "socA"
        assert status["health_status"] == "healthy"
        assert status["is_locked"] is False
        assert status["lease_id"] is None
    
    @pytest.mark.asyncio
    async def test_get_board_status_locked(self, device_manager, mock_lock_manager, mock_redis_client):
        """Test getting status of locked board."""
        board_id = "soc-a-001"
        lease_id = "lease-123"
        
        mock_lock_manager.get_lock_info.return_value = {
            "is_locked": True,
            "token": "token-123"
        }
        
        # Mock finding lease
        lease_data = {
            "lease_id": lease_id,
            "board_id": board_id,
            "board_ip": "10.1.1.101",
            "telnet_port": 23,
            "lock_token": "token-123",
            "acquired_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(minutes=30)).isoformat(),
            "priority": 2,
            "status": "active"
        }
        
        redis_mock = AsyncMock()
        redis_mock.scan = AsyncMock(return_value=(0, [f"lease:{lease_id}"]))
        redis_mock.get.return_value = json.dumps(lease_data)
        mock_redis_client.get_client.return_value = redis_mock
        
        status = await device_manager.get_board_status(board_id)
        
        assert status["is_locked"] is True
        assert status["lease_id"] == lease_id
        assert status["expires_at"] is not None
    
    @pytest.mark.asyncio
    async def test_get_board_status_not_found(self, device_manager):
        """Test getting status of non-existent board."""
        status = await device_manager.get_board_status("non-existent")
        assert "error" in status


class TestFailureReporting:
    """Test failure reporting functionality."""
    
    @pytest.mark.asyncio
    async def test_report_failure_increment(self, device_manager):
        """Test failure count increment."""
        board_id = "soc-a-001"
        
        # Get initial failure count
        board = next(b for b in device_manager.config.boards if b.board_id == board_id)
        initial_count = board.failure_count
        
        # Report failure (not enough to quarantine)
        quarantined = await device_manager.report_failure(board_id, "Test failure")
        
        assert not quarantined
        assert board.failure_count == initial_count + 1
    
    @pytest.mark.asyncio
    async def test_report_failure_quarantine(self, device_manager):
        """Test automatic quarantine after threshold."""
        board_id = "soc-a-001"
        
        # Get board and set failure count near threshold
        board = next(b for b in device_manager.config.boards if b.board_id == board_id)
        board.failure_count = device_manager.quarantine_threshold - 1
        
        # Report failure should trigger quarantine
        quarantined = await device_manager.report_failure(
            board_id,
            "Critical failure",
            quarantine=True
        )
        
        assert quarantined
        assert board.health_status == "quarantined"
    
    @pytest.mark.asyncio
    async def test_report_failure_no_quarantine(self, device_manager):
        """Test failure reporting without quarantine."""
        board_id = "soc-a-001"
        
        board = next(b for b in device_manager.config.boards if b.board_id == board_id)
        board.failure_count = device_manager.quarantine_threshold - 1
        
        # Report failure with quarantine disabled
        quarantined = await device_manager.report_failure(
            board_id,
            "Test failure",
            quarantine=False
        )
        
        assert not quarantined
        assert board.health_status == "healthy"
        assert board.failure_count == device_manager.quarantine_threshold
    
    @pytest.mark.asyncio
    async def test_report_failure_invalid_board(self, device_manager):
        """Test reporting failure for non-existent board."""
        result = await device_manager.report_failure("non-existent", "Test")
        assert result is False


class TestQueueStatus:
    """Test queue status functionality."""
    
    @pytest.mark.asyncio
    async def test_get_queue_status(self, device_manager, mock_redis_client):
        """Test getting queue status."""
        # Mock active lease count
        redis_mock = AsyncMock()
        redis_mock.scan = AsyncMock(side_effect=[
            (100, ["lease:1", "lease:2"]),
            (0, ["lease:3"])
        ])
        mock_redis_client.get_client.return_value = redis_mock
        
        status = await device_manager.get_queue_status()
        
        assert status["total_boards"] == 4
        assert status["healthy_boards"] == 3  # One is quarantined
        assert status["active_leases"] == 3
        assert status["available_boards"] == 0
        assert "families" in status
        assert status["quarantine_threshold"] == 3
    
    @pytest.mark.asyncio
    async def test_get_queue_status_no_leases(self, device_manager, mock_redis_client):
        """Test queue status with no active leases."""
        redis_mock = AsyncMock()
        redis_mock.scan = AsyncMock(return_value=(0, []))
        mock_redis_client.get_client.return_value = redis_mock
        
        status = await device_manager.get_queue_status()
        
        assert status["active_leases"] == 0
        assert status["available_boards"] == 3


class TestLeaseInfo:
    """Test lease information retrieval."""
    
    @pytest.mark.asyncio
    async def test_get_lease_info_exists(self, device_manager, mock_redis_client):
        """Test getting existing lease info."""
        lease_id = "lease-123"
        
        lease_data = {
            "lease_id": lease_id,
            "board_id": "soc-a-001",
            "board_ip": "10.1.1.101",
            "telnet_port": 23,
            "lock_token": "token-123",
            "acquired_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(minutes=30)).isoformat(),
            "priority": 2,
            "status": "active"
        }
        
        redis_mock = AsyncMock()
        redis_mock.get.return_value = json.dumps(lease_data)
        mock_redis_client.get_client.return_value = redis_mock
        
        lease = await device_manager.get_lease_info(lease_id)
        
        assert lease is not None
        assert lease.lease_id == lease_id
        assert lease.board_id == "soc-a-001"
    
    @pytest.mark.asyncio
    async def test_get_lease_info_not_found(self, device_manager, mock_redis_client):
        """Test getting non-existent lease info."""
        redis_mock = AsyncMock()
        redis_mock.get.return_value = None
        mock_redis_client.get_client.return_value = redis_mock
        
        lease = await device_manager.get_lease_info("non-existent")
        assert lease is None