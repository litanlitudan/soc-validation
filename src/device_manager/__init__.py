"""Device Manager module for board allocation and control."""

from .api import app
from .models import Board, Lease, LeaseRequest, TestSubmission, TestResult
from .config import load_boards_config, get_board_by_family, get_board_by_id, BoardsConfig

__all__ = [
    "app",
    "Board",
    "Lease",
    "LeaseRequest",
    "TestSubmission",
    "TestResult",
    "BoardsConfig",
    "load_boards_config",
    "get_board_by_family",
    "get_board_by_id"
]