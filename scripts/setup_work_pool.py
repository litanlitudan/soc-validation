#!/usr/bin/env python3
"""Setup default work pool for Prefect."""

import os
import asyncio
from prefect import get_client
from prefect.client.schemas.actions import WorkPoolCreate


async def create_default_work_pool():
    """Create a default work pool for running flows."""
    # Set the Prefect API URL
    os.environ["PREFECT_API_URL"] = "http://localhost:4200/api"
    
    async with get_client() as client:
        try:
            # Check if work pool already exists
            existing_pools = await client.read_work_pools()
            pool_names = [pool.name for pool in existing_pools]
            
            if "default-pool" in pool_names:
                print("✓ Work pool 'default-pool' already exists")
                return
            
            # Create the default work pool
            work_pool = await client.create_work_pool(
                work_pool=WorkPoolCreate(
                    name="default-pool",
                    type="process",
                    description="Default work pool for SoC validation tests",
                    base_job_template={
                        "job_configuration": {
                            "command": "{{ command }}",
                            "env": "{{ env }}",
                            "labels": "{{ labels }}",
                            "name": "{{ name }}",
                            "stream_output": True,
                            "working_dir": "{{ working_dir }}"
                        },
                        "variables": {
                            "type": "object",
                            "properties": {
                                "command": {
                                    "type": "string",
                                    "title": "Command",
                                    "default": "python",
                                    "description": "The command to run"
                                },
                                "env": {
                                    "type": "object",
                                    "title": "Environment Variables",
                                    "default": {},
                                    "additionalProperties": {
                                        "type": "string"
                                    }
                                },
                                "labels": {
                                    "type": "object",
                                    "title": "Labels",
                                    "default": {},
                                    "additionalProperties": {
                                        "type": "string"
                                    }
                                },
                                "name": {
                                    "type": "string",
                                    "title": "Name"
                                },
                                "working_dir": {
                                    "type": "string",
                                    "title": "Working Directory",
                                    "default": "/app"
                                }
                            }
                        }
                    }
                )
            )
            print(f"✓ Created work pool: {work_pool.name}")
            print(f"  Type: {work_pool.type}")
            print(f"  Status: {work_pool.status}")
            
        except Exception as e:
            print(f"✗ Error creating work pool: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(create_default_work_pool())