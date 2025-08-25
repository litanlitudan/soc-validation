"""Configuration management for device manager."""

import os
import yaml
from typing import List, Optional
from pathlib import Path
from pydantic import BaseModel, Field

from .models import Board


class BoardsConfig(BaseModel):
    """Boards configuration container."""
    
    boards: List[Board] = Field(default_factory=list, description="List of boards")


def load_boards_config(config_path: Optional[str] = None) -> BoardsConfig:
    """
    Load boards configuration from YAML file.
    
    Args:
        config_path: Path to boards.yaml file
    
    Returns:
        BoardsConfig: Loaded configuration
    """
    if config_path is None:
        config_path = os.getenv("BOARDS_CONFIG_PATH", "/app/config/boards.yaml")
    
    config_file = Path(config_path)
    
    if not config_file.exists():
        # Return empty config if file doesn't exist
        return BoardsConfig()
    
    with open(config_file, 'r') as f:
        data = yaml.safe_load(f)
    
    # Convert to BoardsConfig
    if data and 'boards' in data:
        boards = [Board(**board) for board in data['boards']]
        return BoardsConfig(boards=boards)
    
    return BoardsConfig()


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