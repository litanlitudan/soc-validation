"""Unit tests for configuration management."""

import pytest
import tempfile
import yaml
from pathlib import Path
from src.device_manager.config import load_boards_config, get_board_by_family, get_board_by_id
from src.device_manager.models import Board


class TestBoardsConfig:
    """Test boards configuration loading."""
    
    def test_load_empty_config(self):
        """Test loading when config file doesn't exist."""
        config = load_boards_config("/nonexistent/path.yaml")
        assert config.boards == []
    
    def test_load_valid_config(self):
        """Test loading valid boards configuration."""
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({
                'boards': [
                    {
                        'board_id': 'soc-a-001',
                        'soc_family': 'socA',
                        'board_ip': '10.1.1.101',
                        'telnet_port': 23,
                        'location': 'lab-site-a'
                    },
                    {
                        'board_id': 'soc-b-001',
                        'soc_family': 'socB',
                        'board_ip': '10.1.2.101',
                        'telnet_port': 23,
                        'location': 'lab-site-b'
                    }
                ]
            }, f)
            temp_path = f.name
        
        try:
            config = load_boards_config(temp_path)
            assert len(config.boards) == 2
            assert config.boards[0].board_id == 'soc-a-001'
            assert config.boards[1].board_id == 'soc-b-001'
        finally:
            Path(temp_path).unlink()
    
    def test_get_board_by_family(self):
        """Test getting board by family."""
        config = load_boards_config("/nonexistent/path.yaml")
        config.boards = [
            Board(
                board_id='soc-a-001',
                soc_family='socA',
                board_ip='10.1.1.101',
                health_status='healthy'
            ),
            Board(
                board_id='soc-a-002',
                soc_family='socA',
                board_ip='10.1.1.102',
                health_status='unhealthy'
            ),
            Board(
                board_id='soc-b-001',
                soc_family='socB',
                board_ip='10.1.2.101',
                health_status='healthy'
            )
        ]
        
        # Should get first healthy board from family
        board = get_board_by_family(config, 'socA')
        assert board is not None
        assert board.board_id == 'soc-a-001'
        
        # Should get socB board
        board = get_board_by_family(config, 'socB')
        assert board is not None
        assert board.board_id == 'soc-b-001'
        
        # Should return None for non-existent family
        board = get_board_by_family(config, 'socC')
        assert board is None
    
    def test_get_board_by_id(self):
        """Test getting board by ID."""
        config = load_boards_config("/nonexistent/path.yaml")
        config.boards = [
            Board(
                board_id='soc-a-001',
                soc_family='socA',
                board_ip='10.1.1.101'
            ),
            Board(
                board_id='soc-b-001',
                soc_family='socB',
                board_ip='10.1.2.101'
            )
        ]
        
        # Should find existing board
        board = get_board_by_id(config, 'soc-a-001')
        assert board is not None
        assert board.soc_family == 'socA'
        
        # Should return None for non-existent ID
        board = get_board_by_id(config, 'soc-c-001')
        assert board is None