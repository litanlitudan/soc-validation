"""Unit tests for board configuration management."""

import pytest
import yaml
import tempfile
from pathlib import Path
from pydantic import ValidationError

from src.device_manager.config import (
    BoardsConfig,
    load_boards_config,
    save_boards_config,
    get_board_by_id,
    get_board_by_family,
    update_board_health,
    quarantine_board,
    get_available_boards
)
from src.device_manager.models import Board


@pytest.fixture
def sample_boards_data():
    """Sample boards data for testing."""
    return {
        "boards": [
            {
                "board_id": "soc-a-001",
                "soc_family": "socA",
                "board_ip": "10.1.1.101",
                "telnet_port": 23,
                "pdu_host": "pdu-a.lab.local",
                "pdu_outlet": 1,
                "location": "lab-site-a",
                "health_status": "healthy"
            },
            {
                "board_id": "soc-a-002",
                "soc_family": "socA",
                "board_ip": "10.1.1.102",
                "telnet_port": 23,
                "pdu_host": "pdu-a.lab.local",
                "pdu_outlet": 2,
                "location": "lab-site-a",
                "health_status": "healthy"
            },
            {
                "board_id": "soc-b-001",
                "soc_family": "socB",
                "board_ip": "10.1.2.101",
                "telnet_port": 23,
                "pdu_host": "pdu-b.lab.local",
                "pdu_outlet": 1,
                "location": "lab-site-b",
                "health_status": "degraded"
            },
            {
                "board_id": "soc-c-001",
                "soc_family": "socC",
                "board_ip": "10.1.3.101",
                "telnet_port": 23,
                "location": "lab-site-c",
                "health_status": "healthy"
            }
        ]
    }


@pytest.fixture
def sample_config(sample_boards_data):
    """Create a BoardsConfig instance from sample data."""
    boards = [Board(**board) for board in sample_boards_data["boards"]]
    return BoardsConfig(boards=boards)


@pytest.fixture
def temp_config_file(sample_boards_data):
    """Create a temporary YAML config file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(sample_boards_data, f)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


class TestBoardsConfig:
    """Test BoardsConfig model and methods."""
    
    def test_create_empty_config(self):
        """Test creating an empty configuration."""
        config = BoardsConfig()
        assert config.boards == []
        assert len(config.boards) == 0
    
    def test_create_config_with_boards(self, sample_config):
        """Test creating configuration with boards."""
        assert len(sample_config.boards) == 4
        assert sample_config.boards[0].board_id == "soc-a-001"
    
    def test_get_boards_by_family(self, sample_config):
        """Test getting boards by SoC family."""
        soc_a_boards = sample_config.get_boards_by_family("socA")
        assert len(soc_a_boards) == 2
        assert all(b.soc_family == "socA" for b in soc_a_boards)
        
        soc_b_boards = sample_config.get_boards_by_family("socB")
        assert len(soc_b_boards) == 1
        
        soc_d_boards = sample_config.get_boards_by_family("socD")
        assert len(soc_d_boards) == 0
    
    def test_get_healthy_boards(self, sample_config):
        """Test getting healthy boards."""
        healthy = sample_config.get_healthy_boards()
        assert len(healthy) == 3
        assert all(b.health_status == "healthy" for b in healthy)
    
    def test_get_boards_by_location(self, sample_config):
        """Test getting boards by location."""
        site_a = sample_config.get_boards_by_location("lab-site-a")
        assert len(site_a) == 2
        
        site_b = sample_config.get_boards_by_location("lab-site-b")
        assert len(site_b) == 1
    
    def test_get_families(self, sample_config):
        """Test getting unique SoC families."""
        families = sample_config.get_families()
        assert families == {"socA", "socB", "socC"}
    
    def test_get_locations(self, sample_config):
        """Test getting unique locations."""
        locations = sample_config.get_locations()
        assert locations == {"lab-site-a", "lab-site-b", "lab-site-c"}
    
    def test_summary(self, sample_config):
        """Test configuration summary."""
        summary = sample_config.summary()
        assert summary["total_boards"] == 4
        assert summary["healthy_boards"] == 3
        assert "socA" in summary["families"]
        assert summary["boards_by_family"]["socA"] == 2
        assert summary["boards_by_location"]["lab-site-a"] == 2
    
    def test_validate_config_no_issues(self, sample_config):
        """Test validation with no issues."""
        issues = sample_config.validate_config()
        # One board missing PDU config should generate warning
        assert len(issues["errors"]) == 0
        assert len(issues["warnings"]) == 1
        assert "soc-c-001" in issues["warnings"][0]
    
    def test_validate_config_duplicate_board_id(self):
        """Test validation with duplicate board IDs."""
        boards = [
            Board(board_id="soc-001", soc_family="socA", board_ip="10.1.1.1"),
            Board(board_id="soc-001", soc_family="socB", board_ip="10.1.1.2")
        ]
        config = BoardsConfig(boards=boards)
        issues = config.validate_config()
        
        assert len(issues["errors"]) == 1
        assert "Duplicate board IDs" in issues["errors"][0]
    
    def test_validate_config_duplicate_endpoint(self):
        """Test validation with duplicate IP:port combinations."""
        boards = [
            Board(board_id="soc-001", soc_family="socA", board_ip="10.1.1.1", telnet_port=23),
            Board(board_id="soc-002", soc_family="socB", board_ip="10.1.1.1", telnet_port=23)
        ]
        config = BoardsConfig(boards=boards)
        issues = config.validate_config()
        
        assert len(issues["warnings"]) > 0
        assert any("Duplicate endpoints" in w for w in issues["warnings"])
    
    def test_validate_config_pdu_conflict(self):
        """Test validation with PDU outlet conflicts."""
        boards = [
            Board(
                board_id="soc-001",
                soc_family="socA",
                board_ip="10.1.1.1",
                pdu_host="pdu-a",
                pdu_outlet=1
            ),
            Board(
                board_id="soc-002",
                soc_family="socB",
                board_ip="10.1.1.2",
                pdu_host="pdu-a",
                pdu_outlet=1
            )
        ]
        config = BoardsConfig(boards=boards)
        issues = config.validate_config()
        
        assert len(issues["errors"]) == 1
        assert "PDU conflict" in issues["errors"][0]


class TestLoadBoardsConfig:
    """Test configuration loading."""
    
    def test_load_from_file(self, temp_config_file):
        """Test loading configuration from YAML file."""
        config = load_boards_config(temp_config_file, validate=False)
        assert len(config.boards) == 4
        assert config.boards[0].board_id == "soc-a-001"
    
    def test_load_nonexistent_file(self):
        """Test loading from non-existent file."""
        config = load_boards_config("/nonexistent/path.yaml", validate=False)
        assert len(config.boards) == 0
    
    def test_load_empty_file(self):
        """Test loading from empty file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("")
            temp_path = f.name
        
        try:
            config = load_boards_config(temp_path, validate=False)
            assert len(config.boards) == 0
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def test_load_invalid_yaml(self):
        """Test loading invalid YAML."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content:")
            temp_path = f.name
        
        try:
            with pytest.raises(yaml.YAMLError):
                load_boards_config(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def test_load_with_validation_errors(self):
        """Test loading with validation errors."""
        data = {
            "boards": [
                {
                    "board_id": "soc-001",
                    "soc_family": "socA",
                    "board_ip": "10.1.1.1",
                    "pdu_host": "pdu-a",
                    "pdu_outlet": 1
                },
                {
                    "board_id": "soc-002",
                    "soc_family": "socB",
                    "board_ip": "10.1.1.2",
                    "pdu_host": "pdu-a",
                    "pdu_outlet": 1  # Conflict
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(data, f)
            temp_path = f.name
        
        try:
            with pytest.raises(ValueError):
                load_boards_config(temp_path, validate=True)
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def test_load_with_default_health_status(self):
        """Test that missing health_status gets default value."""
        data = {
            "boards": [
                {
                    "board_id": "soc-001",
                    "soc_family": "socA",
                    "board_ip": "10.1.1.1"
                    # No health_status specified
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(data, f)
            temp_path = f.name
        
        try:
            config = load_boards_config(temp_path, validate=False)
            assert config.boards[0].health_status == "healthy"
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestSaveBoardsConfig:
    """Test configuration saving."""
    
    def test_save_config(self, sample_config):
        """Test saving configuration to file."""
        with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False) as f:
            temp_path = f.name
        
        try:
            save_boards_config(sample_config, temp_path)
            
            # Load it back and verify
            loaded = load_boards_config(temp_path, validate=False)
            assert len(loaded.boards) == len(sample_config.boards)
            assert loaded.boards[0].board_id == sample_config.boards[0].board_id
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_get_board_by_id(self, sample_config):
        """Test getting board by ID."""
        board = get_board_by_id(sample_config, "soc-a-001")
        assert board is not None
        assert board.board_id == "soc-a-001"
        assert board.soc_family == "socA"
        
        board = get_board_by_id(sample_config, "nonexistent")
        assert board is None
    
    def test_get_board_by_family(self, sample_config):
        """Test getting board by family."""
        board = get_board_by_family(sample_config, "socA")
        assert board is not None
        assert board.soc_family == "socA"
        assert board.health_status == "healthy"
        
        # Should skip degraded board
        board = get_board_by_family(sample_config, "socB")
        assert board is None  # socB board is degraded
        
        board = get_board_by_family(sample_config, "nonexistent")
        assert board is None
    
    def test_update_board_health(self, sample_config):
        """Test updating board health status."""
        success = update_board_health(sample_config, "soc-a-001", "degraded")
        assert success is True
        
        board = get_board_by_id(sample_config, "soc-a-001")
        assert board.health_status == "degraded"
        
        # Invalid status
        success = update_board_health(sample_config, "soc-a-001", "invalid")
        assert success is False
        
        # Nonexistent board
        success = update_board_health(sample_config, "nonexistent", "healthy")
        assert success is False
    
    def test_quarantine_board(self, sample_config):
        """Test quarantining a board."""
        board = get_board_by_id(sample_config, "soc-a-001")
        initial_failures = board.failure_count
        
        success = quarantine_board(sample_config, "soc-a-001", "Test failure")
        assert success is True
        
        board = get_board_by_id(sample_config, "soc-a-001")
        assert board.health_status == "quarantined"
        assert board.failure_count == initial_failures + 1
        
        # Nonexistent board
        success = quarantine_board(sample_config, "nonexistent", "Test")
        assert success is False
    
    def test_get_available_boards(self, sample_config):
        """Test getting available boards."""
        # All healthy boards
        available = get_available_boards(sample_config)
        assert len(available) == 3
        
        # Filter by family
        available = get_available_boards(sample_config, "socA")
        assert len(available) == 2
        assert all(b.soc_family == "socA" for b in available)
        
        # Family with no healthy boards
        available = get_available_boards(sample_config, "socB")
        assert len(available) == 0  # socB board is degraded