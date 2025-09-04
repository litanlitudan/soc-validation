# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SoC Validation Test Infrastructure - A Prefect-based test orchestration platform for software stack validation on System-on-Chip (SoC) hardware. This MVP enables compiler and runtime engineering teams to automate test execution on real hardware.

## Common Development Commands

### Building and Running

```bash
# Development environment setup
make setup              # Initial project setup (copies .env, builds images)
make up                 # Start all services (Prefect, Device Manager, Redis)
make down               # Stop all services
make restart            # Restart all services
make logs               # View all service logs

# Docker-specific
docker-compose up -d    # Start services in background
docker-compose ps       # Check service status
docker-compose logs -f  # View logs with follow
```

### Testing

```bash
# Run tests
make test               # Run all tests
make test-unit          # Run unit tests only (pytest tests/unit/ -v)
make test-integration   # Run integration tests
make test-e2e           # Run end-to-end tests
make test-coverage      # Generate coverage report

# Run tests in Docker
docker-compose exec worker pytest tests/
docker-compose exec worker pytest tests/unit/test_device_manager_api.py -v  # Single test file
```

### Code Quality

```bash
# Linting and formatting
make lint               # Run ruff and black checks
make format             # Auto-format code with black and ruff
make type-check         # Run mypy type checking

# Manual commands
ruff check src/         # Linting
black src/              # Formatting
mypy src/               # Type checking
```

### Utilities

```bash
make shell              # Open shell in Prefect container
make redis-cli          # Open Redis CLI
make health-check       # Check all service health
make clean              # Clean Python artifacts
make clean-data         # Clean runtime data (preserves databases)
```

## Architecture

### Distributed System Design

The system follows a distributed architecture with clear separation of concerns:

1. **Central Orchestrator** (runs in Docker):
   - Prefect Server (port 4200): Workflow orchestration
   - Device Manager API (port 8000): Board allocation and management
   - Notification Service (port 9000): Slack/Feishu webhooks
   - Redis (port 6379): Distributed locking and queue management
   - SQLite: Prefect database (at /data/prefect.db)

2. **Distributed Workers** (Python processes on remote nodes):
   - Deploy near lab infrastructure for low-latency hardware access
   - Direct telnet connections to SoC boards (port 23)
   - Communicate with orchestrator via REST APIs

### Key Service Interactions

- **Test Submission Flow**: Client → Device Manager API → Redis Queue → Prefect Flow → Worker → Board
- **Board Management**: Device Manager uses Redis for atomic board allocation/release
- **Notifications**: Test completion triggers webhooks via Notification Service
- **Queue Management**: Priority-based FIFO queue in Redis with real-time visibility

### Data Models (src/device_manager/models.py)

- `Board`: Hardware representation with connectivity details
- `Lease`: Board allocation tracking with timeout
- `TestSubmission`: Test job with priority and target board family
- `LeaseRequest`: Board allocation request parameters

### Configuration

- **Board Inventory**: `config/boards.yaml` - defines available hardware
- **Environment**: `.env` files for service configuration
- **Python Config**: `pyproject.toml` - project metadata and tool settings

## Development Patterns

### API Development

Device Manager API uses FastAPI with:
- Lifespan context manager for startup/shutdown (`@asynccontextmanager`)
- Pydantic models for request/response validation
- Redis for distributed state management
- Structured logging with Python's logging module

### Prefect Flows

Test execution flows (src/flows/test_execution.py):
- Use `@flow` decorator for orchestration
- Accept typed parameters with defaults
- Return structured results as dictionaries
- Use `get_run_logger()` for flow-specific logging

### Testing Strategy

- Unit tests: Individual component testing (src/device_manager/, src/notifications/)
- Integration tests: Service interaction testing
- E2E tests: Full workflow validation
- Test markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.e2e`

### Error Handling

- Use HTTPException for API errors
- Implement health checks for all services
- Graceful Redis connection handling with retry logic
- Structured logging for debugging

## Important Notes

### Docker Compose Version
**CRITICAL**: Requires Docker Compose v1.29.2 for compatibility. Install with:
```bash
make install-docker-compose
```

### Worker Deployment
Workers are NOT containerized on the central server. They run as separate Python processes on distributed nodes near test hardware for direct board access.

### Database
Using SQLite for Prefect database (simpler for MVP). Data persists in Docker volume at `/data/prefect.db`.

### Spec Workflow
The project uses a spec-driven development approach with documents in `.spec-workflow/specs/soc-validation/`:
- `requirements.md`: Feature requirements
- `design.md`: Technical design
- `tasks.md`: Implementation tasks

### Current Development State
The project is in active development with:
- Device Manager API being implemented with OpenAPI specification
- Queue management transitioning from src/queue/ to src/queue_manager/
- Test execution flows being built out
- Unit tests being added for API endpoints