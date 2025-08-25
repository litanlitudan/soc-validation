# Product Steering

## Vision & Mission

### Vision Statement
To deliver a functional test orchestration platform for software stack validation on SoC hardware within 3 months, enabling compiler and runtime teams to automate their test workflows and reduce manual overhead by 50% through basic automation and real-time notifications.

### Mission
Within 3 months, we will deliver a minimum viable test infrastructure that:
- Automates basic test execution and hardware allocation
- Improves hardware utilization through simple queue management
- Provides visibility into test progress and board status
- Enables faster validation cycles for compilers and runtimes
- Delivers test notifications through Slack and Feishu

### Problem Statement
Software stack engineering teams face significant challenges:
- **Manual Overhead**: 60% of engineer time spent on test setup, monitoring, and hardware management
- **Resource Conflicts**: Compiler and runtime teams competing for limited hardware access
- **Limited Visibility**: No real-time insight into test queue, hardware availability, or performance regressions
- **Slow Feedback Loops**: Days to get compiler validation and runtime performance results
- **Scaling Bottlenecks**: Unable to efficiently test across multiple SoC architectures and revisions
- **Knowledge Silos**: Performance regressions and compatibility issues not effectively communicated

### Target Users

#### Primary Users
1. **Compiler Engineers**
   - Need: Reliable hardware access for compiler validation and optimization testing
   - Goal: Validate compiler correctness and performance across multiple SoC architectures
   - Pain Point: Waiting for hardware access, inconsistent test environments, manual result collection

2. **Runtime Engineers**
   - Need: Automated testing of runtime libraries and system software on real hardware
   - Goal: Ensure runtime performance and correctness across different silicon revisions
   - Pain Point: Complex setup for different board configurations, lack of performance regression tracking

3. **Software Stack Teams**
   - Need: Continuous integration testing on actual hardware targets
   - Goal: Validate entire software stack from kernel to applications
   - Pain Point: Manual coordination for hardware access, slow feedback loops on stack changes

4. **DevOps/Lab Engineers**
   - Need: Centralized management of heterogeneous hardware resources
   - Goal: Maximize lab efficiency and hardware utilization
   - Pain Point: Manual coordination of hardware access and maintenance

#### Secondary Users
1. **Engineering Managers**
   - Need: Visibility into test progress and resource utilization
   - Goal: Optimize team productivity and resource allocation
   - Pain Point: Lack of metrics and insights for decision making

2. **Quality Assurance Teams**
   - Need: Comprehensive test coverage and reproducible results
   - Goal: Ensure silicon quality and reliability
   - Pain Point: Inconsistent test environments and missing coverage

## User Experience Principles

### Core UX Guidelines

#### 1. Zero-Touch Automation
- **Principle**: Once configured, tests should run without human intervention
- **Implementation**:
  - Automatic hardware allocation and setup
  - Self-healing from common failures
  - Intelligent retry mechanisms
- **Success Metric**: <5% of test runs require manual intervention

#### 2. Real-Time Transparency
- **Principle**: Users should always know what's happening and why
- **Implementation**:
  - Live test status in Prefect UI
  - Real-time notifications via Slack/Feishu
  - Detailed logs and artifacts readily accessible
- **Success Metric**: <30 seconds from event to notification

#### 3. Intelligent Resource Management
- **Principle**: The system should make optimal decisions about resource allocation
- **Implementation**:
  - Historical data-based wait time estimations
  - Automatic load balancing across boards
  - Priority-based preemption when needed
- **Success Metric**: >80% hardware utilization during business hours

#### 4. Fail-Fast, Recover-Quickly
- **Principle**: Problems should be detected early and recovered automatically
- **Implementation**:
  - Aggressive timeouts with clear error messages
  - Automatic board quarantine for repeated failures
  - Graceful degradation when resources limited
- **Success Metric**: <10 minutes mean time to recovery

### Design System Principles

#### Visual Hierarchy
- **Dashboard First**: Primary dashboard shows queue status, running tests, and hardware health
- **Progressive Disclosure**: Summary views with drill-down to detailed information
- **Status Indicators**: Clear visual indicators for test status (queued, running, passed, failed)
- **Color Coding**: Consistent use of colors (green=healthy, yellow=warning, red=critical)

#### Information Architecture
```
Home Dashboard
├── Queue Overview (position, wait times)
├── Active Tests (what's running where)
├── Hardware Status (availability, health)
└── Recent Results (last 24 hours)

Test Management
├── Submit New Test
├── View Test History
├── Manage Priorities
└── Download Artifacts

Hardware Management
├── Board Inventory
├── Health Monitoring
├── Maintenance Schedule
└── Utilization Reports

Analytics
├── Test Metrics
├── Hardware Efficiency
├── Failure Analysis
└── Trend Reports
```

### Accessibility Requirements (MVP)
- **Basic Accessibility**: Keyboard navigation for main functions
- **Clear UI**: High contrast colors, readable fonts
- **Language Support**: English only for MVP
- **Responsive Design**: Desktop-first, basic mobile view

### Performance Standards (MVP)
- **Page Load Time**: <5 seconds for dashboard
- **API Response Time**: <500ms average
- **Status Updates**: <5 second latency acceptable
- **Concurrent Users**: Support 10 simultaneous users
- **Data Retention**: 7 days of test history

## Feature Priorities (3-Month Project)

### Must-Have Features (Delivered by Month 3)

#### Core Functionality
1. **Basic Test Execution**
   - Submit tests via REST API
   - Simple board allocation (first-available)
   - Test execution with basic result collection
   - Local file storage for artifacts

2. **Minimal Hardware Management**
   - Static board inventory (10-20 boards)
   - Basic lease/release mechanism
   - Manual power control via scripts
   - Simple up/down health status

3. **Simple Queue Management**
   - FIFO queue with 3 priority levels (high/normal/low)
   - Basic queue visibility in Prefect UI
   - No wait time estimation
   - Round-robin board allocation

4. **Basic Notifications**
   - Test complete notifications only
   - Failure alerts with basic info
   - Slack OR Feishu integration (one channel)

### Stretch Goals (If Time Permits)

1. **Enhanced Queue**
   - Simple wait time calculation based on queue length
   - Basic priority preemption

2. **Better Monitoring**
   - Simple dashboard showing queue and active tests
   - Basic utilization metrics

3. **CI Integration**
   - Jenkins webhook support for triggering tests

### Out of Scope (Post-Project)

- Multi-SoC family support (focus on 1-2 families only)
- Advanced load balancing
- Performance analytics
- Historical data analysis
- Complex scheduling
- Multi-channel notifications
- User authentication/authorization
- Cost tracking

## Success Metrics (3-Month Goals)

### Key Performance Indicators (KPIs)

#### Month 1 Goals
- **System Setup**: Prefect server deployed and accessible
- **Basic Integration**: 5 boards connected and controllable
- **Proof of Concept**: Successfully run 10 tests end-to-end

#### Month 2 Goals
- **Test Throughput**: 50+ tests/day automated
- **Hardware Connected**: 10-15 boards integrated
- **Queue Working**: Basic priority queue operational
- **Notifications**: Slack or Feishu alerts functioning

#### Month 3 Goals (Project Completion)
- **Test Throughput**: 200+ tests/day automated
  - Current baseline: ~20 tests/day manual
- **Hardware Utilization**: >50% during business hours
  - Current baseline: ~30% with manual coordination
- **Queue Efficiency**: <30 minutes average wait time
  - Current baseline: 2-4 hours manual process
- **Infrastructure Reliability**: >85% success rate
  - Acceptable for MVP
- **User Adoption**: 3-5 active users
  - Compiler or runtime team pilot
- **Time Saved**: 20 hours/week across pilot team
  - Measured by reduced manual coordination

### Business Metrics (3-Month Project)

#### Efficiency Gains
- **Operational Efficiency**: Reduce manual coordination by 50%
  - Measurement: Hours saved in pilot team
  - Target: 20 hours/week saved
- **Hardware ROI**: Better utilization of existing boards
  - Measurement: Tests per board per day
  - Target: 2x increase from baseline

#### Proof of Value
- **Pilot Success**: Demonstrate viability for larger rollout
  - One team fully using the system
  - Positive feedback from users
  - Clear path to scale post-project

#### Deliverables
- **Working System**: Deployed and operational infrastructure
- **Documentation**: Setup and usage guides
- **Runbooks**: Basic operational procedures
- **Handoff**: Knowledge transfer to ops team

## User Journey Maps

### Journey 1: Test Submission
```
Engineer → Submit Test → System Allocates Board → Test Executes → Results Delivered
   |           |              |                      |              |
   2 min    Immediate      <5 min wait          30-60 min      Slack/Email

Pain Points Addressed:
- No manual board coordination needed
- Automatic queue management
- Real-time progress visibility
- Proactive notifications
```

### Journey 2: Failure Investigation
```
Alert Received → View Logs → Download Artifacts → Analyze Results → Share Findings
      |             |              |                    |                |
   <30 sec      1 click       Direct S3 link      Integrated UI     Team Channel

Pain Points Addressed:
- Immediate failure notification
- Centralized log access
- Easy artifact retrieval
- Collaborative debugging
```

### Journey 3: Hardware Maintenance
```
Schedule Window → System Drains Board → Perform Maintenance → Mark Healthy → Auto-Resume
       |                |                      |                    |              |
   1 week ahead    Automatic           Physical work          UI Update      Immediate

Pain Points Addressed:
- Planned maintenance windows
- Graceful test migration
- Clear hardware status
- Automatic recovery
```

## Competitive Landscape

### Current Alternatives
1. **Manual Coordination**
   - Pros: Full control, flexible
   - Cons: Time-consuming, error-prone, doesn't scale

2. **Commercial Solutions** (e.g., Cadence vManager)
   - Pros: Feature-rich, vendor support
   - Cons: Expensive ($100K+), vendor lock-in, complex

3. **Home-grown Scripts**
   - Pros: Customized, low cost
   - Cons: Maintenance burden, limited features, poor documentation

### Our Differentiation
- **Open Source Foundation**: Built on Prefect, avoiding vendor lock-in
- **Cloud-Native Architecture**: Scales elastically with demand
- **Intelligent Automation**: Data-driven optimization and smart scheduling
- **Modern Developer Experience**: REST APIs, real-time notifications, web UI
- **Cost-Effective**: 10x lower TCO than commercial solutions

## Risk Mitigation

### Technical Risks
- **Hardware Diversity**: Support varied hardware through plugin architecture
- **Scale Limitations**: Design for horizontal scaling from day one
- **Integration Complexity**: Provide clear APIs and documentation

### Adoption Risks
- **Change Resistance**: Gradual rollout with parallel manual option
- **Learning Curve**: Comprehensive documentation and training
- **Trust Building**: Start with non-critical tests, build confidence

### Operational Risks
- **Single Point of Failure**: High availability design with failover
- **Data Loss**: Regular backups and disaster recovery plan
- **Security Breaches**: Defense in depth, regular security audits

## Success Criteria (End of 3-Month Project)

### Minimum Success Criteria
- ✅ 10+ boards under management
- ✅ 100+ tests/day throughput
- ✅ <1 hour average queue time
- ✅ 1 team actively using system
- ✅ 80% infrastructure success rate
- ✅ Basic documentation complete

### Target Success Criteria
- ✅ 15-20 boards under management
- ✅ 200+ tests/day throughput
- ✅ <30 minute average queue time
- ✅ 2-3 teams piloting system
- ✅ 85% infrastructure success rate
- ✅ Operational handoff complete

### Project Completion Checklist
- ✅ System deployed and accessible
- ✅ Core features functional (queue, execution, notifications)
- ✅ Documentation and runbooks created
- ✅ Pilot team trained and using system
- ✅ Handoff to operations team complete
- ✅ Post-project roadmap defined