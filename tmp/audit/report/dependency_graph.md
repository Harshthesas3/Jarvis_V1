# Dependency Graph

```mermaid
graph TD
    %% Core Processing Pipeline
    WD[Wake Word Detector] -->|Audio Input| STT[Speech-to-Text]
    STT -->|Text| IR[Intent Router]
    IR -->|Intent| SR[Skill Router]
    SR -->|Query| SRG[Skill Registry]
    SR -->|Skill to Execute| EE[Execution Engine]
    
    %% Memory and Event Services
    EE -->|Store/Recall| MM[Memory Manager]
    EE -->|Publish Events| EB[Event Bus]
    MM -->|Publish Updates| EB
    EB -->|Subscribe| Tel[Telemetry]
    EB -->|Subscribe| WS[Workspace Manager]
    EB -->|Subscribe| Notif[Notification System]
    
    %% Workflow Processing
    WS -->|Persist State| MM
    WS -->|Publish Events| EB
    WS -->|Execute Task| EE
    
    %% Notification and Feedback
    Notif -->|Send Alert| UI[User Interface]
    Tel -->|Metrics| EB
    
    %% Styling
    classDef core fill:#e core fill:#E3F2FD,stroke:#1565C0,stroke-width:2px;
    classDef service fill:#FFF3E0,stroke:#EF6C00,stroke-width:2px;
    classDef workflow layer:#FFF8E1,stroke:#F57C00,stroke-width:2px;
    class WD,STT,IR,SR,EE core;
    class MM,EB service;
    class WS,Telemetry,Notif workflow;
```

## Dependency Summary

### Core Processing Pipeline (Synchronous)
1. **Wake Word Detector** → Speech-to-Text
2. **Speech-to-Text** → Intent Router  
3. **Intent Router** → Skill Router
4. **Skill Router** → Skill Registry
5. **Skill Router** → Execution Engine
6. **Execution Engine** → Memory Manager
7. **Execution Engine** → Event Bus
8. **Memory Manager** → Event Bus

### Workflow Processing (Mixed Sync/Async)
9. **Workspace Manager** → Memory Manager
10. **Workspace Manager** → Event Bus
11. **Workspace Manager** → Execution Engine
12. **Telemetry** → Event Bus (Subscription)
13. **Notification System** → Event Bus (Subscription)
14. **Notification System** → User Interface

### Key Properties
- **Acyclic**: No circular dependencies in direct call graph
- **Layered Architecture**: 
  - Core Pipeline (synchronous request/response)
  - Services (asynchronous event-driven)
  - Workflow Orchestration (business logic)
- **Single Responsibility**: Each node has clearly defined ownership
- **Event Bus as Central Mediator**: Enables loose coupling between components
- **Data Flow**: 
  - Synchronous: User Request → ... → Execution Engine → Memory/Event Bus
  - Asynchronous: Event Bus → Subscribers (Telemetry, Workspace, Notifications)

This dependency graph ensures:
1. No circular dependencies in direct method calls
2. Each subsystem has exactly one owner/responsibility
3. Communication follows the specified event-driven model where appropriate
4. Data persistence flows exclusively through Memory Manager
5. Cross-component communication happens via well-defined interfaces