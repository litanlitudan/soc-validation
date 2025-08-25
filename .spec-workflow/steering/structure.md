# Structure Steering

## Project Organization

### Directory Structure

```
soc_validation/
├── .env.example                    # Environment variable template
├── .gitignore                      # Git ignore patterns
├── docker-compose.yml              # Main orchestration file
├── Dockerfile                      # Prefect server container
├── Makefile                        # Common operations
├── README.md                       # Project documentation
│
├── data/                           # Persistent data (git-ignored)
│   ├── prefect.db                  # SQLite database
│   └── artifacts/                  # Test artifacts storage
│
├── src/                            # Source code
│   ├── __init__.py
│   ├── flows/                      # Prefect flows
│   ├── tasks/                      # Prefect tasks
│   ├── device_manager/             # Hardware abstraction
│   ├── notifications/              # Notification service
│   ├── config/                     # Configuration
│   └── utils/                      # Utilities
│
├── tests/                          # Test suite
│   ├── unit/                       # Unit tests
│   └── integration/                # Integration tests
│
├── scripts/                        # Operational scripts
├── docs/                           # Documentation
└── .spec-workflow/                 # Spec workflow (auto-generated)
```

---

## File Naming Conventions

* **Python modules**: `snake_case` (e.g., `board_tasks.py`)
* **Classes**: PascalCase in code; `snake_case` filenames
* **Constants**: In `config/settings.py` or `constants.py`
* **Tests**: Prefix with `test_` (e.g., `test_leasing.py`)
* **Config**: Use `.yaml` for YAML files, `.env` for local environments
* **Docs**: Markdown `.md`, lowercase with hyphens
* **Directory index docs**: `README.md`

---

## Module Organization

* **flows/**: Prefect flow definitions (1 per file, import tasks from `tasks/`)
* **tasks/**: Reusable Prefect tasks, grouped by functionality
* **device\_manager/**: Hardware abstraction, FastAPI app, pluggable drivers
* **notifications/**: Notification adapters, one per platform
* **config/**: Environment & board configuration
* **utils/**: Logging, metrics, common helpers

**Import structure**:

```python
# Cross-module
from src.device_manager.models import Board
from src.tasks.board_tasks import acquire_lease

# Within module
from .models import Lease
from ..utils.logging import get_logger
```

---

## Configuration Management

### Environment Variables (`.env`)

```bash
PREFECT_API_URL=http://localhost:4200/api
PREFECT_HOME=/usr/src/server
DEVICE_MANAGER_URL=http://localhost:8000
REDIS_URL=redis://localhost:6379
SLACK_WEBHOOK_URL=...
ARTIFACT_PATH=/data/artifacts
DATABASE_URL=sqlite:///data/prefect.db
```

### Board Configuration (`boards.yaml`)

```yaml
boards:
  - board_id: soc-a-001
    soc_family: socA
    soc_revision: rev2
    serial_port: /dev/ttyUSB0
    pdu_outlet: 1
    host_runner: runner-1
```

---

## Testing Workflow

```
tests/
├── unit/           # Fast, isolated tests
├── integration/    # Component interaction tests
└── e2e/            # End-to-end workflows (optional)
```

Run tests:

```bash
pytest tests/
pytest --cov=src tests/
```

---

## Documentation Structure

* **setup.md**: Installation & configuration
* **usage.md**: System usage
* **api.md**: API reference
* **runbooks/**: Operational docs (troubleshooting, maintenance)
* **README.md**: Project overview

Standards:

* Headers for structure
* Code fenced examples
* Mermaid/ASCII diagrams optional
* Line length ≤ 100 chars
* Inline docstrings for functions & classes

---

## Development Environment

**Required Tools**

```bash
Python 3.11+
Docker 24.0+
Docker Compose v2
Make
pytest, ruff, mypy
```

**Quick Setup**

```bash
cp .env.example .env
make up
```

---

## Monitoring & Logging

* **Metrics**: Queue depth, board utilization, throughput, API response times
* **Logging**: Structured logs via `structlog`
* **Health Checks**:

  * Prefect: `/api/health`
  * Device Manager: `/health`
  * Redis connection test
  * Custom board health script
