#!/usr/bin/env python3
"""Initialize Prefect Server with proper database setup."""

import asyncio
import os
import sys
from pathlib import Path

# Ensure aiosqlite is available
try:
    import aiosqlite
    print("✓ aiosqlite is installed")
except ImportError:
    print("✗ aiosqlite is not installed")
    sys.exit(1)

# Set the database URL for SQLite with aiosqlite
os.environ["PREFECT_API_DATABASE_CONNECTION_URL"] = "sqlite+aiosqlite:////data/prefect.db"

# Create data directory if it doesn't exist
data_dir = Path("/data")
data_dir.mkdir(exist_ok=True)

print(f"Database URL: {os.environ['PREFECT_API_DATABASE_CONNECTION_URL']}")
print("Starting Prefect Server...")

# Start the Prefect server
os.system("prefect server start")