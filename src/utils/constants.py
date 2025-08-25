"""Constants for soc-validation system."""

# Priority levels
PRIORITY_HIGH = 1
PRIORITY_NORMAL = 2
PRIORITY_LOW = 3

# Test status
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"
STATUS_CANCELLED = "cancelled"

# Board health status
HEALTH_HEALTHY = "healthy"
HEALTH_UNHEALTHY = "unhealthy"
HEALTH_QUARANTINED = "quarantined"

# Lease status
LEASE_ACTIVE = "active"
LEASE_EXPIRED = "expired"
LEASE_RELEASED = "released"

# Default timeouts (in seconds)
DEFAULT_TEST_TIMEOUT = 1800  # 30 minutes
DEFAULT_LEASE_TIMEOUT = 3600  # 1 hour
DEFAULT_BOARD_HEALTH_CHECK_TIMEOUT = 30

# Queue limits
MAX_QUEUE_SIZE = 50
QUEUE_WAIT_WARNING_MINUTES = 30

# Storage settings
ARTIFACT_RETENTION_DAYS = 7
MAX_DISK_USAGE_GB = 100
LOG_RETENTION_DAYS = 30

# Board failure thresholds
BOARD_FAILURE_THRESHOLD = 3
BOARD_QUARANTINE_HOURS = 24

# API settings
API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"

# Health check intervals (in seconds)
HEALTH_CHECK_INTERVAL = 60
WORKER_HEARTBEAT_INTERVAL = 30

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 30