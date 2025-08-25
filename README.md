# SoC Validation Test Infrastructure

## Project Overview

The **soc-validation** project is a Prefect-based test orchestration platform for software stack validation on System-on-Chip (SoC) hardware. This MVP implementation enables compiler and runtime engineering teams to automate test execution on real hardware, reducing manual coordination overhead by 50% through basic automation and real-time notifications.

## Key Features

- **Automated Test Execution**: Submit and run tests on real SoC hardware via REST API
- **Hardware Management**: Manage 10-20 boards with automatic allocation and release
- **Queue Management**: Priority-based FIFO queue with real-time visibility
- **Notifications**: Slack/Feishu integration for test completion alerts
- **Distributed Architecture**: Central orchestrator with distributed workers near lab infrastructure

## Quick Start

### Prerequisites

- Docker and Docker Compose (v3.9+)
- Python 3.12+
- Git
- 4GB RAM minimum
- 10GB disk space

### Development Setup

1. Clone the repository:

```bash
git clone <repository-url>
cd soc_validation
```

2. Copy environment template:

```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Build and start the development environment:

```bash
# Build the images
docker-compose build

# Start all services
docker-compose up -d

# Check service status
docker-compose ps

# View logs (optional)
docker-compose logs -f
```

4. Verify services are running:

```bash
# Check health status
make health-check

# Access service UIs
open http://localhost:4200  # Prefect UI
open http://localhost:8000/docs  # Device Manager API docs
open http://localhost:9000/docs  # Notification Service API docs
```

5. Initialize Prefect work pool (first time only):

```bash
docker-compose exec prefect prefect work-pool create --type process default
```

### Running Tests

```bash
# Run tests inside Docker container
docker-compose exec worker pytest tests/

# Or use Make commands
make test           # Run all tests
make test-unit      # Run unit tests only
make test-integration  # Run integration tests
make test-e2e       # Run end-to-end tests
make test-coverage  # Generate coverage report
```

## Project Structure

```text
soc_validation/
├── src/                      # Source code
│   ├── device_manager/       # Device management API
│   │   ├── drivers/         # Hardware communication drivers
│   │   └── models/          # Pydantic data models
│   ├── flows/               # Prefect flows
│   ├── tasks/               # Prefect tasks
│   ├── queue/               # Queue management
│   ├── notifications/       # Notification services
│   ├── storage/             # Artifact storage
│   └── utils/               # Utility functions
├── config/                   # Configuration files
│   └── boards.yaml          # Board inventory
├── tests/                    # Test suites
│   ├── unit/                # Unit tests
│   ├── integration/         # Integration tests
│   └── e2e/                 # End-to-end tests
├── scripts/                  # Utility scripts
├── docs/                     # Documentation
├── data/                     # Runtime data (gitignored)
│   ├── prefect/            # Prefect database
│   ├── postgres/           # PostgreSQL data
│   ├── redis/              # Redis persistence
│   ├── artifacts/          # Test artifacts
│   └── logs/               # Application logs
├── docker-compose.yml        # Main Docker configuration
├── worker-compose.yml        # Distributed worker deployment
├── Dockerfile               # Multi-stage application image
├── Dockerfile.worker        # Worker-specific image
├── .dockerignore            # Docker build exclusions
├── requirements.txt         # Python dependencies
├── pyproject.toml          # Python project configuration
├── pytest.ini              # Pytest configuration
├── Makefile                # Development commands
├── .env.example            # Environment template
├── .env.worker.example     # Worker environment template
├── .gitignore              # Git exclusions
└── README.md               # This file
```

## Architecture

The soc-validation system follows a distributed architecture:

- **Central Orchestrator**: Prefect Server, Device Manager API, Redis, SQLite, Notification Service
- **Distributed Workers**: Python processes deployed near lab infrastructure for low-latency board access
- **Direct Board Access**: Workers connect directly to boards via telnet (port 23)
- **Communication**: Workers communicate with central orchestrator via REST APIs
- **Notification Service**: Bidirectional Slack/Feishu integration

### Key Design Decisions

1. **Workers are NOT containerized on the central server** - They run as separate Python processes on distributed nodes near test hardware
2. **Direct hardware access** - Workers have network connectivity to SoC boards via telnet
3. **Centralized orchestration** - All scheduling and coordination happens on the central server
4. **Distributed execution** - Test execution happens on worker nodes close to hardware

## Configuration

### Environment Variables

Key environment variables (see `.env.example` for full list):

```bash
# Prefect Configuration
PREFECT_API_PORT=4200
PREFECT_DATABASE_URL=sqlite:////data/prefect.db  # Using SQLite for simplicity

# Redis Configuration
REDIS_PORT=6379

# Notification Services
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/XXX
```

### Board Configuration

Edit `config/boards.yaml` to define your hardware inventory:

```yaml
boards:
  - board_id: soc-a-001
    soc_family: socA
    board_ip: 10.1.1.101
    telnet_port: 23
    pdu_host: pdu-a.lab.local
    pdu_outlet: 1
```

## API Documentation

### Submit Test

```bash
POST /api/v1/tests
{
  "test_binary": "/path/to/test",
  "board_family": "socA",
  "priority": 2
}
```

### Lease Board

```bash
POST /api/v1/lease
{
  "board_family": "socA",
  "timeout": 1800
}
```

### View Queue

```bash
GET /api/v1/queue
```

## Development

### Local Development Setup

1. Create Python virtual environment:

```bash
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

3. Install pre-commit hooks:

```bash
pre-commit install
```

4. Run linting and type checking:

```bash
make lint         # Run all linters
make format       # Auto-format code
make type-check   # Type checking with mypy
```

### Docker Commands

```bash
# Central Orchestrator Management
make up           # Start central services (Prefect, Device Manager, etc.)
make down         # Stop central services
make restart      # Restart central services
make logs         # View all logs
make logs-prefect # View Prefect logs only

# Utilities
make shell        # Open shell in Prefect container
make redis-cli    # Open Redis CLI
make build        # Rebuild Docker images
make clean        # Clean up generated files

# Testing
make test         # Run all tests
make test-coverage # Generate coverage report

# Worker Deployment (on worker nodes)
# Note: Workers are deployed separately on distributed nodes
cd /opt/soc-validation
docker-compose -f worker-compose.yml up -d
```

### Contributing

1. Create a feature branch
2. Make your changes
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## Deployment

### Central Orchestrator Deployment

1. Prepare environment:

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your values

# Create required directories
mkdir -p data/{prefect,redis,artifacts,logs,postgres}
```

2. Deploy services:

```bash
# Build images
docker-compose build

# Start services
docker-compose up -d

# Initialize database (first time only)
docker-compose exec prefect prefect server database upgrade

# Create default work pool
docker-compose exec prefect prefect work-pool create --type process default
```

### Distributed Worker Deployment

To deploy workers on remote machines near lab infrastructure:

1. Copy worker files to worker node:

```bash
scp worker-compose.yml Dockerfile.worker .env.worker.example \
  user@worker-node:/opt/soc-validation/
```

2. Configure worker:

```bash
# On worker node
cd /opt/soc-validation
cp .env.worker.example .env.worker
# Edit .env.worker with orchestrator IP and worker identity
```

3. Start worker:

```bash
docker-compose -f worker-compose.yml up -d
```

## Docker Services

### Central Orchestrator Services

| Service | Port | Description | Health Check |
|---------|------|-------------|-------------|
| Prefect Server | 4200 | Orchestration control plane | `/api/health` |
| Device Manager | 8000 | Board allocation API | `/api/health` |
| Notification | 9000 | Slack/Feishu webhooks | `/health` |
| Redis | 6379 | Distributed locking | `redis-cli ping` |

### Distributed Worker Services

| Service | Port | Description | Deployment |
|---------|------|-------------|------------|
| Worker | - | Test executor (Python process) | Near lab infrastructure |
| Node Exporter | 9100 | Worker node monitoring (optional) | On worker nodes |

### Container Images

- **Central Orchestrator Images**:
  - **Base Image**: `python:3.12-slim` with system dependencies
  - **Device Manager**: Multi-stage build target `device-manager` in main Dockerfile
  - **Notification**: Multi-stage build target `notification` in main Dockerfile
  - **Prefect Server**: Official `prefecthq/prefect:3-python3.12` image with SQLite
  - **Redis**: Official `redis:7.4-alpine` image

- **Distributed Worker Image**:
  - **Worker**: Separate `Dockerfile.worker` with hardware communication tools
  - **Deployment**: Built and deployed on worker nodes near lab infrastructure
  - **Network Mode**: Uses host network for direct board access

## Monitoring

### Service Health

```bash
# Check all service health
make health-check

# Individual service health
curl http://localhost:4200/api/health  # Prefect
curl http://localhost:8000/api/health  # Device Manager
curl http://localhost:9000/health      # Notifications

# Redis health
docker-compose exec redis redis-cli ping
```

### Dashboards

- **Prefect UI**: http://localhost:4200 - Flow runs, queue status, workers
- **Device Manager API**: http://localhost:8000/docs - Interactive API docs
- **Notification API**: http://localhost:9000/docs - Webhook endpoints

### Logs

```bash
# View all logs
docker-compose logs -f

# Service-specific logs
docker-compose logs -f prefect
docker-compose logs -f device-manager
docker-compose logs -f worker
docker-compose logs -f redis

# Log files (persisted in volumes)
ls -la data/logs/
```

### Metrics

- Container stats: `docker stats`
- Redis monitoring: `docker-compose exec redis redis-cli monitor`
- Worker status: Check Prefect UI > Work Pools

## Docker Volumes and Data Persistence

### Volume Mapping

| Volume | Container Path | Host Path | Purpose |
|--------|---------------|-----------|---------|
| prefect-data | /data | (volume) | Prefect database (SQLite) and storage |
| redis-data | /data | ./data/redis | Redis persistence |
| artifact-data | /data/artifacts | ./data/artifacts | Test artifacts |
| log-data | /app/logs | ./data/logs | Application logs |
| config | /app/config | ./config | Board configuration |
| source | /app/src | ./src | Application code (read-only) |

### Data Management

```bash
# Backup all data
tar -czf backup-$(date +%Y%m%d-%H%M%S).tar.gz data/

# Clean artifacts older than 7 days
find data/artifacts -type f -mtime +7 -delete

# Clear Redis cache
docker-compose exec redis redis-cli FLUSHALL

# Reset Prefect database (development only!)
rm -rf data/prefect/prefect.db
docker-compose restart prefect
```

## Troubleshooting

### Docker-Specific Issues

1. **Services Won't Start**
   ```bash
   # Check for port conflicts
   netstat -tulpn | grep -E '4200|8000|9000|6379'
   
   # Check Docker daemon
   docker info
   
   # Clean and rebuild
   docker-compose down -v
   docker-compose build --no-cache
   docker-compose up -d
   ```

2. **Container Health Check Failures**
   ```bash
   # Check container logs
   docker-compose logs <service-name>
   
   # Inspect health status
   docker inspect <container-name> --format='{{json .State.Health}}'
   
   # Restart unhealthy service
   docker-compose restart <service-name>
   ```

3. **Permission Issues**
   ```bash
   # Fix data directory permissions
   sudo chown -R $USER:$USER data/
   chmod -R 755 data/
   ```

4. **Out of Disk Space**
   ```bash
   # Check Docker disk usage
   docker system df
   
   # Clean up unused resources
   docker system prune -a --volumes
   
   # Clean old artifacts
   make clean-data
   ```

### Application Issues

1. **Board Connection Failed**
   - Check network connectivity: `docker-compose exec worker ping <board-ip>`
   - Verify telnet: `docker-compose exec worker telnet <board-ip> 23`
   - Check credentials in `.env` file
   - Ensure worker can reach boards (check firewall rules)

2. **Queue Stuck**
   - Check Redis: `docker-compose exec redis redis-cli ping`
   - View Redis keys: `docker-compose exec redis redis-cli keys '*'`
   - Check worker status in Prefect UI
   - Restart worker: `docker-compose restart worker`

3. **Notifications Not Working**
   - Check service health: `curl http://localhost:9000/health`
   - Verify webhook URLs in `.env`
   - Check logs: `docker-compose logs notification`
   - Test webhook manually: `curl -X POST http://localhost:9000/webhooks/test`

4. **Prefect API Connection Issues**
   ```bash
   # Check Prefect API health
   curl http://localhost:4200/api/health
   
   # Verify environment variable
   docker-compose exec worker env | grep PREFECT_API_URL
   
   # Test from worker container
   docker-compose exec worker curl http://prefect:4200/api/health
   ```

## License

[License Information]

## Support

For issues and questions:
- Create an issue in the repository
- Contact the development team
- Check documentation in `/docs`

## Roadmap

### Current (MVP - 3 Months)

- ✅ Basic test execution
- ✅ Simple queue management
- ✅ 10-20 board support
- ✅ Slack/Feishu notifications

### Future Enhancements

- Multi-SoC family support
- Advanced scheduling algorithms
- Performance analytics dashboard
- User authentication and RBAC
- Cloud deployment options
