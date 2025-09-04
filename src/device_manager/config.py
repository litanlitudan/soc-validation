"""Configuration management for device manager."""

import os
import yaml
import logging
from typing import List, Optional, Dict, Set
from pathlib import Path
from pydantic import BaseModel, Field, ValidationError
from collections import defaultdict

from .models import Board

logger = logging.getLogger(__name__)


class BoardsConfig(BaseModel):
    """Boards configuration container."""
    
    boards: List[Board] = Field(default_factory=list, description="List of boards")
    
    def validate_config(self) -> Dict[str, List[str]]:
        """
        Validate the configuration for consistency and completeness.
        
        Returns:
            Dict with validation warnings and errors
        """
        issues = {"errors": [], "warnings": []}
        
        # Check for duplicate board IDs
        board_ids = [board.board_id for board in self.boards]
        duplicates = [id for id in board_ids if board_ids.count(id) > 1]
        if duplicates:
            issues["errors"].append(f"Duplicate board IDs found: {set(duplicates)}")
        
        # Check for duplicate IP:port combinations
        endpoints = [(b.board_ip, b.telnet_port) for b in self.boards]
        duplicate_endpoints = [ep for ep in endpoints if endpoints.count(ep) > 1]
        if duplicate_endpoints:
            issues["warnings"].append(f"Duplicate endpoints (IP:port) found: {set(duplicate_endpoints)}")
        
        # Validate each board
        for board in self.boards:
            # Check for missing critical fields
            if not board.board_ip:
                issues["errors"].append(f"Board {board.board_id} missing IP address")
        
        return issues
    
    def get_boards_by_family(self, family: str) -> List[Board]:
        """Get all boards for a specific SoC family."""
        return [b for b in self.boards if b.soc_family == family]
    
    def get_healthy_boards(self) -> List[Board]:
        """Get all healthy boards."""
        return [b for b in self.boards if b.health_status == "healthy"]
    
    def get_boards_by_location(self, location: str) -> List[Board]:
        """Get all boards at a specific location."""
        return [b for b in self.boards if b.location == location]
    
    def get_families(self) -> Set[str]:
        """Get set of all available SoC families."""
        return set(b.soc_family for b in self.boards)
    
    def get_locations(self) -> Set[str]:
        """Get set of all locations."""
        return set(b.location for b in self.boards)
    
    def summary(self) -> Dict:
        """Get configuration summary statistics."""
        return {
            "total_boards": len(self.boards),
            "healthy_boards": len(self.get_healthy_boards()),
            "families": list(self.get_families()),
            "locations": list(self.get_locations()),
            "boards_by_family": {
                family: len(self.get_boards_by_family(family))
                for family in self.get_families()
            },
            "boards_by_location": {
                location: len(self.get_boards_by_location(location))
                for location in self.get_locations()
            }
        }


def load_boards_config(config_path: Optional[str] = None, validate: bool = True) -> BoardsConfig:
    """
    Load boards configuration from YAML file.
    
    Args:
        config_path: Path to boards.yaml file
        validate: Whether to validate the configuration
    
    Returns:
        BoardsConfig: Loaded configuration
        
    Raises:
        FileNotFoundError: If config file doesn't exist and not optional
        ValidationError: If configuration is invalid
        yaml.YAMLError: If YAML parsing fails
    """
    if config_path is None:
        config_path = os.getenv("BOARDS_CONFIG_PATH", "/app/config/boards.yaml")
    
    config_file = Path(config_path)
    
    if not config_file.exists():
        logger.warning(f"Configuration file not found: {config_path}")
        # Try fallback to example config
        example_path = config_file.parent / "boards.example.yaml"
        if example_path.exists():
            logger.info(f"Using example configuration: {example_path}")
            config_file = example_path
        else:
            logger.warning("No configuration file found, using empty config")
            return BoardsConfig()
    
    try:
        with open(config_file, 'r') as f:
            data = yaml.safe_load(f)
            
        if not data:
            logger.warning("Configuration file is empty")
            return BoardsConfig()
        
        if 'boards' not in data:
            logger.error("Configuration missing 'boards' key")
            return BoardsConfig()
        
        # Parse boards with validation
        boards = []
        errors = []
        for idx, board_data in enumerate(data['boards']):
            try:
                # Add default health_status if missing
                if 'health_status' not in board_data:
                    board_data['health_status'] = 'healthy'
                    
                board = Board(**board_data)
                boards.append(board)
            except ValidationError as e:
                errors.append(f"Board {idx} ({board_data.get('board_id', 'unknown')}): {e}")
                logger.error(f"Failed to parse board {idx}: {e}")
        
        if errors and validate:
            raise ValueError(f"Configuration validation failed:\n" + "\n".join(errors))
        
        config = BoardsConfig(boards=boards)
        
        # Validate configuration if requested
        if validate:
            issues = config.validate_config()
            
            # Log warnings
            for warning in issues["warnings"]:
                logger.warning(f"Config validation warning: {warning}")
            
            # Raise on errors
            if issues["errors"]:
                error_msg = "Configuration errors found:\n" + "\n".join(issues["errors"])
                logger.error(error_msg)
                raise ValueError(error_msg)
        
        logger.info(f"Loaded {len(boards)} boards from {config_file}")
        logger.info(f"Configuration summary: {config.summary()}")
        
        return config
        
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse YAML configuration: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise


def get_board_by_family(config: BoardsConfig, family: str) -> Optional[Board]:
    """
    Get first available board from a specific family.
    
    Args:
        config: Boards configuration
        family: SoC family to search for
    
    Returns:
        Board or None if not found
    """
    for board in config.boards:
        if board.soc_family == family and board.health_status == "healthy":
            return board
    return None


def get_board_by_id(config: BoardsConfig, board_id: str) -> Optional[Board]:
    """
    Get board by its ID.
    
    Args:
        config: Boards configuration
        board_id: Board ID to search for
    
    Returns:
        Board or None if not found
    """
    for board in config.boards:
        if board.board_id == board_id:
            return board
    return None


def save_boards_config(config: BoardsConfig, config_path: Optional[str] = None) -> None:
    """
    Save boards configuration to YAML file.
    
    Args:
        config: BoardsConfig to save
        config_path: Path to save the configuration
    """
    if config_path is None:
        config_path = os.getenv("BOARDS_CONFIG_PATH", "/app/config/boards.yaml")
    
    config_file = Path(config_path)
    
    # Create directory if it doesn't exist
    config_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert to dict for YAML serialization
    data = {
        "boards": [board.model_dump(exclude_none=True) for board in config.boards]
    }
    
    # Write YAML file
    with open(config_file, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    logger.info(f"Saved configuration with {len(config.boards)} boards to {config_file}")


def update_board_health(config: BoardsConfig, board_id: str, health_status: str) -> bool:
    """
    Update the health status of a board.
    
    Args:
        config: BoardsConfig instance
        board_id: Board ID to update
        health_status: New health status (healthy, degraded, unhealthy, quarantined)
    
    Returns:
        True if updated, False if board not found
    """
    valid_statuses = ["healthy", "degraded", "unhealthy", "quarantined"]
    if health_status not in valid_statuses:
        logger.error(f"Invalid health status: {health_status}. Must be one of {valid_statuses}")
        return False
    
    board = get_board_by_id(config, board_id)
    if board:
        board.health_status = health_status
        logger.info(f"Updated board {board_id} health status to {health_status}")
        return True
    
    logger.warning(f"Board {board_id} not found in configuration")
    return False


def quarantine_board(config: BoardsConfig, board_id: str, reason: str = "") -> bool:
    """
    Quarantine a board (set health to quarantined and increment failure count).
    
    Args:
        config: BoardsConfig instance
        board_id: Board ID to quarantine
        reason: Optional reason for quarantine
    
    Returns:
        True if quarantined, False if board not found
    """
    board = get_board_by_id(config, board_id)
    if board:
        board.health_status = "quarantined"
        board.failure_count += 1
        logger.warning(f"Quarantined board {board_id}. Failure count: {board.failure_count}. Reason: {reason}")
        return True
    
    logger.error(f"Cannot quarantine: Board {board_id} not found")
    return False


def get_available_boards(config: BoardsConfig, family: Optional[str] = None) -> List[Board]:
    """
    Get all available (healthy) boards, optionally filtered by family.
    
    Args:
        config: BoardsConfig instance
        family: Optional SoC family filter
    
    Returns:
        List of available boards
    """
    boards = config.get_healthy_boards()
    
    if family:
        boards = [b for b in boards if b.soc_family == family]
    
    return boards