#!/usr/bin/env python
"""Test script to validate OpenAPI schema generation."""

import sys
sys.path.insert(0, '/home/tanl/soc-validation')

import json
import os
from pathlib import Path

# Set up test environment
os.environ['BOARDS_CONFIG_PATH'] = str(Path(__file__).parent.parent / "config" / "boards.example.yaml")

from src.device_manager.api import app


def main():
    """Extract and validate OpenAPI schema."""
    schema = app.openapi()
    
    print("OpenAPI Schema Summary:")
    print(f"  Title: {schema['info']['title']}")
    print(f"  Version: {schema['info']['version']}")
    print(f"  Description: {schema['info']['description']}")
    
    print("\nEndpoints:")
    for path, methods in schema['paths'].items():
        for method, details in methods.items():
            print(f"  {method.upper()} {path}")
            if 'summary' in details:
                print(f"    - {details['summary']}")
    
    print("\nModels:")
    if 'components' in schema and 'schemas' in schema['components']:
        for model_name in schema['components']['schemas'].keys():
            print(f"  - {model_name}")
    
    # Save the schema to a file
    output_file = Path(__file__).parent.parent / "docs" / "openapi.json"
    output_file.parent.mkdir(exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(schema, f, indent=2)
    
    print(f"\nOpenAPI schema saved to: {output_file}")


if __name__ == "__main__":
    main()