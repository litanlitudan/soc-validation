#!/usr/bin/env python3
"""Validate OpenAPI specification and check consistency with models."""

import sys
import yaml
from pathlib import Path
from typing import Dict, Any, List, Set
import json


def load_openapi_spec(spec_path: Path) -> Dict[str, Any]:
    """Load and parse the OpenAPI specification."""
    with open(spec_path, 'r') as f:
        return yaml.safe_load(f)


def validate_spec_structure(spec: Dict[str, Any]) -> List[str]:
    """Validate the basic structure of the OpenAPI spec."""
    errors = []
    
    # Check required top-level fields
    required_fields = ['openapi', 'info', 'paths']
    for field in required_fields:
        if field not in spec:
            errors.append(f"Missing required field: {field}")
    
    # Check info structure
    if 'info' in spec:
        info_required = ['title', 'version']
        for field in info_required:
            if field not in spec['info']:
                errors.append(f"Missing required field in info: {field}")
    
    # Check that paths exist
    if 'paths' in spec and not spec['paths']:
        errors.append("No paths defined in the specification")
    
    return errors


def validate_endpoints(spec: Dict[str, Any]) -> List[str]:
    """Validate endpoint definitions."""
    errors = []
    
    if 'paths' not in spec:
        return errors
    
    for path, path_obj in spec['paths'].items():
        if not path.startswith('/'):
            errors.append(f"Path {path} must start with /")
        
        # Check for valid HTTP methods
        valid_methods = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
        for method, operation in path_obj.items():
            if method not in valid_methods:
                continue
                
            # Check operation structure
            if 'responses' not in operation:
                errors.append(f"{method.upper()} {path}: Missing responses")
            
            if 'operationId' not in operation:
                errors.append(f"{method.upper()} {path}: Missing operationId")
            
            # Check for tags
            if 'tags' not in operation:
                errors.append(f"{method.upper()} {path}: Missing tags")
    
    return errors


def validate_schemas(spec: Dict[str, Any]) -> List[str]:
    """Validate schema definitions."""
    errors = []
    
    if 'components' not in spec or 'schemas' not in spec['components']:
        return errors
    
    schemas = spec['components']['schemas']
    
    # Check each schema
    for schema_name, schema_def in schemas.items():
        if 'type' not in schema_def:
            errors.append(f"Schema {schema_name}: Missing type")
        
        if schema_def.get('type') == 'object':
            if 'properties' not in schema_def:
                errors.append(f"Schema {schema_name}: Object schema missing properties")
            
            # Check required fields are defined in properties
            if 'required' in schema_def:
                for required_field in schema_def['required']:
                    if 'properties' not in schema_def or required_field not in schema_def['properties']:
                        errors.append(f"Schema {schema_name}: Required field '{required_field}' not in properties")
    
    return errors


def check_model_consistency(spec: Dict[str, Any]) -> List[str]:
    """Check consistency between OpenAPI schemas and Python models."""
    warnings = []
    
    # Expected model schemas based on models.py
    expected_schemas = {
        'Board': {
            'required': ['board_id', 'soc_family', 'board_ip'],
            'properties': ['board_id', 'soc_family', 'board_ip', 'telnet_port', 
                         'pdu_host', 'pdu_outlet', 'location', 'health_status',
                         'failure_count', 'last_used']
        },
        'LeaseRequest': {
            'required': ['board_family'],
            'properties': ['board_family', 'timeout', 'priority']
        },
        'Lease': {
            'required': ['lease_id', 'board_id', 'acquired_at', 'expires_at'],
            'properties': ['lease_id', 'board_id', 'flow_run_id', 'acquired_at',
                         'expires_at', 'status']
        },
        'TestSubmission': {
            'required': ['test_binary', 'board_family'],
            'properties': ['test_binary', 'board_family', 'priority', 'timeout']
        },
        'TestResult': {
            'required': ['result_id', 'flow_run_id', 'board_id', 'test_binary',
                        'started_at', 'status'],
            'properties': ['result_id', 'flow_run_id', 'board_id', 'test_binary',
                         'started_at', 'completed_at', 'status', 'output_file',
                         'error_message']
        }
    }
    
    if 'components' in spec and 'schemas' in spec['components']:
        schemas = spec['components']['schemas']
        
        # Check each expected schema
        for schema_name, expected in expected_schemas.items():
            if schema_name not in schemas:
                warnings.append(f"Expected schema {schema_name} not found")
                continue
            
            schema = schemas[schema_name]
            
            # Check required fields
            if 'required' in schema:
                schema_required = set(schema['required'])
                expected_required = set(expected['required'])
                
                missing = expected_required - schema_required
                if missing:
                    warnings.append(f"Schema {schema_name}: Missing required fields {missing}")
                
                extra = schema_required - expected_required
                if extra:
                    warnings.append(f"Schema {schema_name}: Extra required fields {extra}")
            
            # Check properties
            if 'properties' in schema:
                schema_props = set(schema['properties'].keys())
                expected_props = set(expected['properties'])
                
                missing = expected_props - schema_props
                if missing:
                    warnings.append(f"Schema {schema_name}: Missing properties {missing}")
    
    return warnings


def validate_references(spec: Dict[str, Any]) -> List[str]:
    """Validate that all $ref references point to existing definitions."""
    errors = []
    
    def extract_refs(obj: Any, refs: Set[str]) -> None:
        """Recursively extract all $ref values."""
        if isinstance(obj, dict):
            if '$ref' in obj:
                refs.add(obj['$ref'])
            for value in obj.values():
                extract_refs(value, refs)
        elif isinstance(obj, list):
            for item in obj:
                extract_refs(item, refs)
    
    # Collect all references
    all_refs = set()
    extract_refs(spec, all_refs)
    
    # Check each reference
    for ref in all_refs:
        if ref.startswith('#/'):
            # Internal reference
            path_parts = ref[2:].split('/')
            current = spec
            for part in path_parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    errors.append(f"Invalid reference: {ref}")
                    break
    
    return errors


def main():
    """Main validation function."""
    project_root = Path(__file__).parent.parent
    spec_path = project_root / 'docs' / 'openapi.yaml'
    
    if not spec_path.exists():
        print(f"❌ OpenAPI spec not found at {spec_path}")
        sys.exit(1)
    
    print(f"Validating OpenAPI specification at {spec_path}")
    print("-" * 50)
    
    try:
        spec = load_openapi_spec(spec_path)
    except Exception as e:
        print(f"❌ Failed to parse OpenAPI spec: {e}")
        sys.exit(1)
    
    # Run validations
    all_errors = []
    all_warnings = []
    
    # Structural validation
    errors = validate_spec_structure(spec)
    if errors:
        all_errors.extend(errors)
    else:
        print("✅ Spec structure is valid")
    
    # Endpoint validation
    errors = validate_endpoints(spec)
    if errors:
        all_errors.extend(errors)
    else:
        print("✅ Endpoints are valid")
    
    # Schema validation
    errors = validate_schemas(spec)
    if errors:
        all_errors.extend(errors)
    else:
        print("✅ Schemas are valid")
    
    # Reference validation
    errors = validate_references(spec)
    if errors:
        all_errors.extend(errors)
    else:
        print("✅ All references are valid")
    
    # Model consistency check
    warnings = check_model_consistency(spec)
    if warnings:
        all_warnings.extend(warnings)
    else:
        print("✅ Schemas are consistent with models")
    
    # Summary
    print("-" * 50)
    
    if all_errors:
        print(f"\n❌ Found {len(all_errors)} errors:")
        for error in all_errors:
            print(f"  - {error}")
    
    if all_warnings:
        print(f"\n⚠️  Found {len(all_warnings)} warnings:")
        for warning in all_warnings:
            print(f"  - {warning}")
    
    if not all_errors and not all_warnings:
        print("\n✅ OpenAPI specification is valid and consistent!")
        
        # Print statistics
        if 'paths' in spec:
            endpoint_count = sum(
                len([m for m in p.keys() if m in ['get', 'post', 'put', 'patch', 'delete']])
                for p in spec['paths'].values()
            )
            print(f"\n📊 Statistics:")
            print(f"  - Endpoints: {endpoint_count}")
            print(f"  - Paths: {len(spec['paths'])}")
            if 'components' in spec and 'schemas' in spec['components']:
                print(f"  - Schemas: {len(spec['components']['schemas'])}")
            if 'tags' in spec:
                print(f"  - Tags: {len(spec['tags'])}")
    
    sys.exit(1 if all_errors else 0)


if __name__ == "__main__":
    main()