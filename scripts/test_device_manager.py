#!/usr/bin/env python
"""Manual testing script for Device Manager API."""

import sys
sys.path.insert(0, '/home/tanl/soc-validation')

import asyncio
import os
from pathlib import Path

# Set up test environment
os.environ['BOARDS_CONFIG_PATH'] = str(Path(__file__).parent.parent / "config" / "boards.example.yaml")
os.environ['REDIS_URL'] = 'redis://localhost:6379'

from src.device_manager.api import app


def main():
    """Run the Device Manager API server."""
    print("Starting Device Manager API server...")
    print(f"Board config: {os.environ['BOARDS_CONFIG_PATH']}")
    print(f"Redis URL: {os.environ['REDIS_URL']}")
    print("\nAPI endpoints available at:")
    print("  - http://localhost:8000/docs (Swagger UI)")
    print("  - http://localhost:8000/api/health (Health check)")
    print("  - http://localhost:8000/api/v1/boards (List boards)")
    print("\nPress Ctrl+C to stop the server.\n")
    
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()