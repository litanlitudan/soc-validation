# Technical Steering

## Architecture Overview

### System Architecture

A **lightweight, containerized microservices system** that runs well on a single server or small VM, with minimal external dependencies:

```
┌────────────────────────────────────────────┐
│ Control Plane (Orchestration)              │
│  • Prefect Server 3.x (self-hosted, Docker)│
│  • Work Pools & Work Queues                │
│  • Redis Streams (queue + locks)           │
│  • Traefik / NGINX (simple gateway)        │
└────────────────────────────────────────────┘
                      │
┌────────────────────────────────────────────┐
│ Execution Layer (Agents & Workers)         │
│  • Prefect Workers (Python 3.12+)          │
│  • Device Manager API (FastAPI + Pydantic) │
│  • Notification Service (async, Redis pub) │
└────────────────────────────────────────────┘
                      │
┌────────────────────────────────────────────┐
│ Hardware Abstraction Layer                 │
│  • Simple pluggable drivers (gRPC APIs)    │
│  • Serial/JTAG/PDU control                 │
│  • Board registry in Postgres JSONB        │
└────────────────────────────────────────────┘
                      │
┌────────────────────────────────────────────┐
│ Storage & Monitoring                       │
│  • MinIO (local S3) or AWS S3 if available │
│  • PostgreSQL 16+ (single instance)        │
│  • Redis 7.4+ / Dragonfly (cache, queue)   │
│  • Prometheus + Grafana (basic metrics)    │
│  • OpenTelemetry (logs/traces if needed)   │
└────────────────────────────────────────────┘
```

---

## Core Stack

* **Workflow Orchestration:** Prefect Server 3.x (self-hosted, Docker)
* **Execution Model:** Work Pools + Work Queues → Prefect Workers
* **Programming Language:** Python 3.12+ (strict typing)
* **Runtime:** Docker Compose (simple, no Kubernetes until scale requires)
* **API Framework:** FastAPI (with Pydantic v2)
* **Database:** PostgreSQL 16+ (single instance) or SQLite
* **Cache / Message Queue:** Redis 7.4+ or Dragonfly (one system for caching, queues, and locks)
* **Object Storage:** MinIO for local / S3 (AWS or R2) for cloud

---

## Development Tools

* **Dependencies:** uv
* **Testing:** pytest 8.x + pytest-asyncio
* **Lint / Format:** ruff (all-in-one)
* **Type Checking:** pyright (fast)
* **Docs:** mkdocs-material + mkdocstrings
* **CI/CD:** Jenkins or GitHub Actions (simple workflows)

---

## Monitoring & Observability

* **Metrics:** Prometheus + Grafana (basic dashboards)
* **Logging:** structlog (local) → Loki if centralized logs needed
* **Tracing:** OpenTelemetry (optional; enable when debugging perf issues)

---

## Security

* **Secrets:** .env files in dev → Vault/KMS (AWS/GCP) when scaling
* **Transport Security:** TLS 1.3 on all external APIs
* **Code Security:** Dependabot / Renovate for updates + Sigstore for image signing (later)