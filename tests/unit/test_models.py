"""Unit tests for device manager models."""

import pytest
from datetime import datetime, timedelta
from src.device_manager.models import Board, LeaseRequest, Lease, TestSubmission, TestResult


class TestBoardModel:
    """Test Board model."""
    
    def test_board_creation(self):
        """Test creating a Board instance."""
        board = Board(
            board_id="soc-a-001",
            soc_family="socA",
            board_ip="10.1.1.101",
            telnet_port=23,
            location="lab-site-a"
        )
        
        assert board.board_id == "soc-a-001"
        assert board.soc_family == "socA"
        assert board.board_ip == "10.1.1.101"
        assert board.telnet_port == 23
        assert board.health_status == "healthy"
        assert board.failure_count == 0
    
    def test_board_with_pdu(self):
        """Test Board with PDU configuration."""
        board = Board(
            board_id="soc-b-001",
            soc_family="socB",
            board_ip="10.1.2.101",
            pdu_host="pdu-b.lab.local",
            pdu_outlet=1
        )
        
        assert board.pdu_host == "pdu-b.lab.local"
        assert board.pdu_outlet == 1


class TestLeaseRequest:
    """Test LeaseRequest model."""
    
    def test_lease_request_defaults(self):
        """Test LeaseRequest with default values."""
        request = LeaseRequest(board_family="socA")
        
        assert request.board_family == "socA"
        assert request.timeout == 1800  # 30 minutes default
        assert request.priority == 2  # normal priority
    
    def test_lease_request_custom(self):
        """Test LeaseRequest with custom values."""
        request = LeaseRequest(
            board_family="socB",
            timeout=3600,
            priority=1
        )
        
        assert request.timeout == 3600
        assert request.priority == 1
    
    def test_lease_request_priority_validation(self):
        """Test priority validation."""
        with pytest.raises(ValueError):
            LeaseRequest(board_family="socA", priority=0)
        
        with pytest.raises(ValueError):
            LeaseRequest(board_family="socA", priority=4)


class TestLease:
    """Test Lease model."""
    
    def test_lease_creation(self):
        """Test creating a Lease instance."""
        now = datetime.now()
        expires = now + timedelta(minutes=30)
        
        lease = Lease(
            lease_id="lease-123",
            board_id="soc-a-001",
            acquired_at=now,
            expires_at=expires,
            status="active"
        )
        
        assert lease.lease_id == "lease-123"
        assert lease.board_id == "soc-a-001"
        assert lease.status == "active"
        assert lease.flow_run_id is None


class TestTestSubmission:
    """Test TestSubmission model."""
    
    def test_test_submission_defaults(self):
        """Test TestSubmission with defaults."""
        submission = TestSubmission(
            test_binary="/path/to/test",
            board_family="socA"
        )
        
        assert submission.test_binary == "/path/to/test"
        assert submission.board_family == "socA"
        assert submission.priority == 2
        assert submission.timeout == 1800
    
    def test_test_submission_priority_validation(self):
        """Test priority validation."""
        # Valid priorities
        for priority in [1, 2, 3]:
            submission = TestSubmission(
                test_binary="/test",
                board_family="socA",
                priority=priority
            )
            assert submission.priority == priority
        
        # Invalid priorities
        with pytest.raises(ValueError):
            TestSubmission(
                test_binary="/test",
                board_family="socA",
                priority=0
            )


class TestTestResult:
    """Test TestResult model."""
    
    def test_test_result_creation(self):
        """Test creating a TestResult instance."""
        started = datetime.now()
        completed = started + timedelta(minutes=5)
        
        result = TestResult(
            result_id="result-123",
            flow_run_id="flow-456",
            board_id="soc-a-001",
            test_binary="/path/to/test",
            started_at=started,
            completed_at=completed,
            status="passed",
            output_file="/data/artifacts/result-123/output.log"
        )
        
        assert result.result_id == "result-123"
        assert result.status == "passed"
        assert result.error_message is None
    
    def test_test_result_failed(self):
        """Test TestResult for failed test."""
        result = TestResult(
            result_id="result-789",
            flow_run_id="flow-999",
            board_id="soc-b-001",
            test_binary="/path/to/test",
            started_at=datetime.now(),
            status="failed",
            error_message="Test assertion failed"
        )
        
        assert result.status == "failed"
        assert result.error_message == "Test assertion failed"
        assert result.completed_at is None