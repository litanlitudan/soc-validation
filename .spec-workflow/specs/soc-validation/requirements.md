# Requirements Document

## Introduction

This feature implements a minimum viable Prefect-based test infrastructure for software stack validation on SoC hardware, targeting a 3-month development timeline. The system enables compiler and runtime engineering teams to automate test execution on real hardware, reducing manual coordination overhead by 50% through basic automation and real-time notifications. Following the product steering vision, this MVP focuses on delivering a functional system for 1-2 pilot teams with 10-20 boards.

## Alignment with Product Vision

Per the product steering document, this infrastructure addresses critical needs for software stack engineering teams:
- Reduces manual coordination from 60% to 30% of engineer time (50% reduction)
- Provides basic automated test execution on actual SoC hardware
- Enables compiler and runtime validation with faster feedback loops
- Delivers real-time visibility through Prefect UI and Slack/Feishu notifications
- Establishes foundation for future scaling post-project

## Requirements

### Requirement 1: Prefect Control Plane (Simplified for MVP)

**User Story:** As a compiler engineer, I want a simple control plane to submit and monitor test jobs, so that I can validate compiler builds without manual hardware coordination.

#### Acceptance Criteria

1. WHEN deploying the system THEN it SHALL use Prefect Server 3.x in a Docker container as specified in tech.md
2. IF a work pool is created THEN it SHALL support 1-2 SoC families with fixed concurrency (10-20 boards total)
3. WHEN tests are submitted THEN they SHALL enter a simple FIFO queue with 3 priority levels (high/normal/low)
4. IF monitoring test status THEN the Prefect UI SHALL show queue position and running tests
5. WHEN accessing the system THEN it SHALL support up to 10 concurrent users per performance standards

### Requirement 2: Basic Host Runner Infrastructure

**User Story:** As a DevOps engineer, I want a simple worker setup that executes tests on boards, so that I can manage our small hardware lab efficiently.

#### Acceptance Criteria

1. WHEN deploying workers THEN they SHALL run as Prefect Workers in Python 3.12+ containers
2. IF managing boards THEN the system SHALL control 10-20 boards via basic serial and power scripts
3. WHEN accessing boards THEN workers SHALL use simple serial console connections for output capture
4. IF multiple workers exist THEN they SHALL coordinate through Redis 7.4+ for basic locking
5. WHEN storing configuration THEN boards.yaml SHALL define static board inventory per structure.md

### Requirement 3: Simple Device Management

**User Story:** As a runtime engineer, I want guaranteed exclusive access to boards during test execution, so that my runtime tests don't interfere with other teams' compiler tests.

#### Acceptance Criteria

1. WHEN requesting a board THEN the system SHALL allocate the first available board matching the SoC family
2. IF a board is leased THEN Redis SHALL hold an exclusive lock preventing other access
3. WHEN a test completes THEN the system SHALL release the board within 30 seconds
4. IF a board fails 3 times in a day THEN it SHALL be marked as unhealthy in the database
5. WHEN leasing fails THEN the system SHALL retry up to 3 times before failing the test

### Requirement 4: Basic Queue Management

**User Story:** As a compiler engineer, I want to see my position in the queue and submit high-priority builds, so that critical fixes can be validated quickly.

#### Acceptance Criteria

1. WHEN submitting tests THEN users SHALL specify priority as high (1), normal (2), or low (3)
2. IF multiple tests are queued THEN higher priority tests SHALL execute first (simple sorting)
3. WHEN viewing the queue THEN users SHALL see their position and approximately how many tests are ahead
4. IF the queue exceeds 50 tests THEN new submissions SHALL be rejected with a clear message
5. WHEN average wait time exceeds 30 minutes THEN the system SHALL send an alert notification

### Requirement 5: Minimal Notifications

**User Story:** As a software stack team lead, I want to receive notifications when tests complete or fail, so that my team can respond quickly to issues.

#### Acceptance Criteria

1. WHEN configuring notifications THEN the system SHALL support either Slack OR Feishu (not both)
2. IF a test completes successfully THEN a simple success message SHALL be sent with test ID and duration
3. WHEN a test fails THEN the notification SHALL include error message and link to logs
4. IF notification delivery fails THEN the system SHALL log the error but not block test execution
5. WHEN setting up notifications THEN only one channel SHALL be configured per deployment

### Requirement 6: Basic Test Execution

**User Story:** As a runtime engineer, I want to submit test binaries and get results back, so that I can validate runtime performance on real hardware.

#### Acceptance Criteria

1. WHEN submitting a test THEN users SHALL provide a test binary and target board family via REST API
2. IF executing tests THEN the system SHALL copy binaries to the board and execute via serial commands
3. WHEN tests run THEN serial output SHALL be captured and stored as a local file
4. IF a test times out (30 minutes default) THEN it SHALL be terminated and marked as failed
5. WHEN results are ready THEN they SHALL be stored locally for 7 days per data retention policy

### Requirement 7: Simple Storage

**User Story:** As a compiler engineer, I want to download test logs and artifacts, so that I can debug compilation issues.

#### Acceptance Criteria

1. WHEN storing artifacts THEN the system SHALL use local filesystem under /data/artifacts
2. IF disk usage exceeds 100GB THEN oldest artifacts SHALL be deleted automatically
3. WHEN accessing artifacts THEN users SHALL get a direct file path or simple HTTP link
4. IF artifacts are requested after 7 days THEN the system SHALL return a "not found" error
5. WHEN listing artifacts THEN the API SHALL return the most recent 100 results

### Requirement 8: Basic CI Integration (Stretch Goal)

**User Story:** As a DevOps engineer, I want Jenkins to trigger tests automatically, so that our CI pipeline includes hardware validation.

#### Acceptance Criteria

1. IF CI integration is implemented THEN the system SHALL accept webhooks from Jenkins
2. WHEN receiving a webhook THEN the system SHALL validate a simple shared secret
3. IF the webhook is valid THEN a test SHALL be submitted with parameters from the payload
4. WHEN CI tests complete THEN results SHALL be posted back via a simple callback URL
5. IF this feature is not completed THEN manual API submission SHALL be the only method

## Non-Functional Requirements

### Code Architecture and Modularity

Following tech.md and structure.md guidelines:
- **Single Responsibility**: Separate modules for flows/, tasks/, device_manager/, and notifications/
- **FastAPI Structure**: Device manager API using FastAPI with Pydantic v2 models
- **Import Patterns**: Use absolute imports for cross-module, relative within modules
- **Python Standards**: Python 3.12+ with strict typing, async/await for I/O operations

### Performance (MVP Targets)

Per product.md performance standards:
- API response time < 500ms average
- Board lease operations < 10 seconds
- Queue reordering < 5 seconds
- Page load time < 5 seconds
- Support 10 concurrent users
- Status update latency < 5 seconds acceptable

### Scalability (3-Month Scope)

Limited scope for MVP:
- Support 10-20 boards maximum
- Handle 200+ tests/day
- Single server deployment (no distributed system)
- Local file storage only
- One notification channel

### Security (Basic Requirements)

Per tech.md security guidelines:
- Credentials in .env files (not hardcoded)
- Basic webhook secret validation
- No user authentication for MVP
- Network isolation via Docker networks
- No TLS required for internal services

### Reliability (MVP Acceptable)

Per product.md success metrics:
- 85% infrastructure success rate acceptable
- Manual intervention acceptable for some failures
- Basic retry logic (3 attempts)
- No high availability or failover
- Simple health checks via HTTP endpoints

### Usability

Per product.md UX principles:
- Prefect UI shows basic queue and test status
- English-only interface
- Desktop-first design
- Basic error messages with suggested actions
- Simple REST API with basic documentation