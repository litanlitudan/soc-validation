"""Data models for device management."""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime


class Board(BaseModel):
    """Board configuration model."""
    
    board_id: str = Field(..., description="Unique board identifier")
    soc_family: str = Field(..., description="SoC family (e.g., socA, socB)")
    board_ip: str = Field(..., description="Board IP address")
    telnet_port: int = Field(default=23, description="Telnet port")
    pdu_host: Optional[str] = Field(None, description="PDU hostname")
    pdu_outlet: Optional[int] = Field(None, description="PDU outlet number")
    location: str = Field(default="unknown", description="Physical location")
    health_status: str = Field(default="healthy", description="Board health status")
    failure_count: int = Field(default=0, description="Failure count")
    last_used: Optional[datetime] = Field(None, description="Last usage timestamp")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "board_id": "soc-a-001",
                "soc_family": "socA",
                "board_ip": "10.1.1.101",
                "telnet_port": 23,
                "pdu_host": "pdu-a.lab.local",
                "pdu_outlet": 1,
                "location": "lab-site-a"
            }
        }
    )


class LeaseRequest(BaseModel):
    """Board lease request model."""
    
    board_family: str = Field(..., description="Target SoC family")
    timeout: int = Field(default=1800, description="Lease timeout in seconds")
    priority: int = Field(default=2, ge=1, le=3, description="Priority (1=high, 2=normal, 3=low)")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "board_family": "socA",
                "timeout": 1800,
                "priority": 2
            }
        }
    )


class Lease(BaseModel):
    """Board lease model."""
    
    lease_id: str = Field(..., description="Unique lease identifier")
    board_id: str = Field(..., description="Leased board ID")
    flow_run_id: Optional[str] = Field(None, description="Prefect flow run ID")
    acquired_at: datetime = Field(..., description="Lease acquisition time")
    expires_at: datetime = Field(..., description="Lease expiration time")
    status: str = Field(default="active", description="Lease status")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "lease_id": "lease-123e4567-e89b-12d3-a456-426614174000",
                "board_id": "soc-a-001",
                "flow_run_id": "flow-run-123",
                "acquired_at": "2024-01-01T00:00:00Z",
                "expires_at": "2024-01-01T00:30:00Z",
                "status": "active"
            }
        }
    )


class TestSubmission(BaseModel):
    """Test submission request model."""
    
    test_binary: str = Field(..., description="Path to test binary")
    board_family: str = Field(..., description="Target board family")
    priority: int = Field(default=2, ge=1, le=3, description="Test priority")
    timeout: int = Field(default=1800, description="Test timeout in seconds")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "test_binary": "/path/to/test",
                "board_family": "socA",
                "priority": 2,
                "timeout": 1800
            }
        }
    )


class TestResult(BaseModel):
    """Test execution result model."""
    
    result_id: str = Field(..., description="Unique result identifier")
    flow_run_id: str = Field(..., description="Prefect flow run ID")
    board_id: str = Field(..., description="Board used for test")
    test_binary: str = Field(..., description="Test binary path")
    started_at: datetime = Field(..., description="Test start time")
    completed_at: Optional[datetime] = Field(None, description="Test completion time")
    status: str = Field(..., description="Test status (running/passed/failed/timeout)")
    output_file: Optional[str] = Field(None, description="Path to output file")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "result_id": "result-123e4567-e89b-12d3-a456-426614174000",
                "flow_run_id": "flow-run-123",
                "board_id": "soc-a-001",
                "test_binary": "/path/to/test",
                "started_at": "2024-01-01T00:00:00Z",
                "completed_at": "2024-01-01T00:05:00Z",
                "status": "passed",
                "output_file": "/data/artifacts/result-123/output.log"
            }
        }
    )