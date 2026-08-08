"""
JARVIS Agent Orchestration System

A sophisticated agent-based architecture that decomposes JARVIS's complex
functionality into specialized, independently testable agents.

Core Principles:
- Each agent has ONE clear responsibility
- Agents communicate via events/queues (no direct dependencies)
- All agents are independently testable
- No circular dependencies between agents
- Backward compatibility maintained through orchestrator
- Hot-reloadable agents without system restart
"""

import logging
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from queue import Queue, Empty
from typing import Any, Dict, List, Optional, Callable
from threading import Lock

logger = logging.getLogger("jarvis.agents")

# =============================================================================
# Event System
# =============================================================================

class EventType(Enum):
    """Agent event types."""
    AGENT_STARTED = "agent_started"
    AGENT_STOPPED = "agent_stopped"
    AGENT_ERROR = "agent_error"
    TASK_ASSIGNED = "task_assigned"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    STATE_UPDATED = "state_updated"
    MESSAGE = "message"
    SYSTEM_STATUS = "system_status"

@dataclass
class AgentEvent:
    """Event published by agents."""
    id: str
    source: str
    type: EventType
    target: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    priority: int = 0

class EventBus:
    """Event bus for agent communication without direct dependencies."""
    
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}
        self.lock = Lock()
    
    def subscribe(self, event_type: EventType, callback: Callable):
        """Subscribe to events."""
        with self.lock:
            if event_type not in self.subscribers:
                self.subscribers[event_type] = []
            self.subscribers[event_type].append(callback)
    
    def publish(self, event: AgentEvent):
        """Publish an event to all subscribers."""
        with self.lock:
            callbacks = self.subscribers.get(event.type, [])
            for callback in callbacks[:]:  # Copy list to avoid modification during iteration
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"Error in event handler: {e}")
    
    def unsubscribe(self, event_type: EventType, callback: Callable):
        """Unsubscribe a callback."""
        with self.lock:
            if event_type in self.subscribers:
                try:
                    self.subscribers[event_type].remove(callback)
                except ValueError:
                    pass
class MessageQueue:
    """Thread-safe message queue for asynchronous communication."""
    
    def __init__(self):
        self.queue = Queue()
        self.lock = Lock()
        self.pending = set()
    
    def send(self, message: AgentEvent):
        """Send a message to the queue."""
        with self.lock:
            self.queue.put(message)
            self.pending.add(message.id)
    
    def receive(self, timeout: Optional[float] = None) -> Optional[AgentEvent]:
        """Receive a message from the queue."""
        try:
            if timeout:
                message = self.queue.get(timeout=timeout)
            else:
                message = self.queue.get_nowait()
            
            with self.lock:
                self.pending.discard(message.id)
            
            return message
        except Empty:
            return None
    
    def ack(self, message_id: str):
        """Acknowledge a message."""
        with self.lock:
            self.pending.discard(message_id)
    
    def get_pending_count(self) -> int:
        """Get number of pending messages."""
        with self.lock:
            return len(self.pending)

# =============================================================================
# Agent Base Classes
# =============================================================================

class AgentState(Enum):
    """Agent state."""
    IDLE = "idle"
    RUNNING = "running"
    BUSY = "busy"
    ERROR = "error"
    STOPPING = "stopping"
    STOPPED = "stopped"

@dataclass
class AgentConfig:
    """Agent configuration."""
    name: str
    agent_type: str
    enabled: bool = True
    max_tasks: int = 5
    priority: int = 0
    concurrency: int = 1
    timeout: float = 30.0
    max_retries: int = 3
    backoff_factor: float = 1.0
    tags: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)

class Agent(ABC):
    """Base class for all JARVIS agents."""
    
    def __init__(self, config: AgentConfig, event_bus: EventBus):
        self.config = config
        self.event_bus = event_bus
        self.state = AgentState.IDLE
        self.id = f"{config.agent_type}_{uuid.uuid4().hex[:8]}"
        self.task_queue = MessageQueue()
        self.pending_tasks = []
        self.completed_tasks = []
        self.failed_tasks = []
        self._thread = None
        self._shutdown_event = threading.Event()
        
        # Subscribe to relevant events
        self._setup_subscriptions()
        
        # Log agent initialization
        logger.info(f"Agent {self.config.name} ({self.id}) initialized")
    
    def _setup_subscriptions(self):
        """Setup event subscriptions for this agent."""
        # Default subscriptions - subclasses should override
        self.event_bus.subscribe(EventType.MESSAGE, self._handle_message)
        self.event_bus.subscribe(EventType.AGENT_STARTED, self._handle_agent_started)
        self.event_bus.subscribe(EventType.AGENT_STOPPED, self._handle_agent_stopped)
        self.event_bus.subscribe(EventType.AGENT_ERROR, self._handle_agent_error)
    
    @abstractmethod
    def _main_loop(self):
        """Main agent loop. Must be implemented by subclasses."""
        pass
    
    def start(self):
        """Start the agent."""
        if self.state in [AgentState.RUNNING, AgentState.BUSY]:
            logger.warning(f"Agent {self.config.name} is already running")
            return False

        try:
            self.state = AgentState.RUNNING
            self.event_bus.publish(AgentEvent(
                id=str(uuid.uuid4()),
                source=self.id,
                type=EventType.AGENT_STARTED,
                data={"agent_name": self.config.name, "agent_type": self.config.agent_type}
            ))

            # Start the agent's main loop in a separate thread
            self._thread = threading.Thread(target=self._main_loop, daemon=True)
            self._thread.start()

            logger.info(f"Agent {self.config.name} started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start agent {self.config.name}: {e}")
            self.state = AgentState.ERROR
            self.event_bus.publish(AgentEvent(
                id=str(uuid.uuid4()),
                source=self.id,
                type=EventType.AGENT_ERROR,
                data={"error": str(e), "agent_name": self.config.name}
            ))
            return False

    def stop(self):
        """Stop the agent."""
        if self.state not in [AgentState.RUNNING, AgentState.BUSY]:
            return True

        try:
            self.state = AgentState.STOPPING
            logger.info(f"Stopping agent {self.config.name}")

            # Signal shutdown
            self._shutdown_event.set()

            # Wait for thread to finish
            if self._thread:
                self._thread.join(timeout=5.0)

            self.state = AgentState.STOPPED

            self.event_bus.publish(AgentEvent(
                id=str(uuid.uuid4()),
                source=self.id,
                type=EventType.AGENT_STOPPED,
                data={"agent_name": self.config.name}
            ))

            logger.info(f"Agent {self.config.name} stopped successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to stop agent {self.config.name}: {e}")
            self.state = AgentState.ERROR
            return False

    def assign_task(self, task: Dict[str, Any], target_agent: Optional[str] = None):
        """Assign a task to this agent."""
        if self.state not in [AgentState.RUNNING, AgentState.BUSY]:
            logger.warning(f"Cannot assign task to agent {self.config.name} - not running")
            return False

        # Create task event
        task_event = AgentEvent(
            id=str(uuid.uuid4()),
            source="orchestrator",
            type=EventType.TASK_ASSIGNED,
            target=target_agent,
            data={
                "task_id": task.get("id", str(uuid.uuid4())),
                "task_type": task.get("type"),
                "payload": task,
                "priority": task.get("priority", 0),
                "deadline": task.get("deadline"),
                "assigner": "orchestrator"
            }
        )

        self.task_queue.send(task_event)
        logger.debug(f"Task assigned to agent {self.config.name}: {task.get('type')}")
        return True
    
    def _handle_message(self, event: AgentEvent):
        """Handle incoming messages."""
        pass
    
    def _handle_agent_started(self, event: AgentEvent):
        """Handle agent started event."""
        pass
    
    def _handle_agent_stopped(self, event: AgentEvent):
        """Handle agent stopped event."""
        pass
    
    def _handle_agent_error(self, event: AgentEvent):
        """Handle agent error event."""
        pass
    
    def get_status(self) -> Dict[str, Any]:
        """Get agent status."""
        return {
            "id": self.id,
            "name": self.config.name,
            "state": self.state.value,
            "task_queue_size": self.task_queue.get_pending_count(),
            "pending_tasks": len(self.pending_tasks),
            "completed_tasks": len(self.completed_tasks),
            "failed_tasks": len(self.failed_tasks),
            "config": {
                "agent_type": self.config.agent_type,
                "enabled": self.config.enabled,
                "max_tasks": self.config.max_tasks,
                "concurrency": self.config.concurrency,
                "tags": self.config.tags,
                "capabilities": self.config.capabilities,
            }
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert agent to dictionary."""
        return {
            "id": self.id,
            "name": self.config.name,
            "agent_type": self.config.agent_type,
            "state": self.state.value,
            "enabled": self.config.enabled,
            "max_tasks": self.config.max_tasks,
            "priority": self.config.priority,
            "concurrency": self.config.concurrency,
            "tags": self.config.tags,
            "capabilities": self.config.capabilities,
            "status": self.get_status()
        }

# =============================================================================
# Specialized Agents
# =============================================================================

class PlannerAgent(Agent):
    """Agent responsible for planning and decision-making."""
    
    def __init__(self, config: AgentConfig, event_bus: EventBus, context: Dict[str, Any]):
        super().__init__(config, event_bus)
        self.context = context
        self.planner_active = True  # Simulate if planner.is_ready()
    
    def _setup_subscriptions(self):
        """Setup subscriptions specific to planner."""
        super()._setup_subscriptions()
        self.event_bus.subscribe(EventType.SYSTEM_STATUS, self._handle_system_status)
    
    def _main_loop(self):
        """Planner agent main loop."""
        while not self._shutdown_event.is_set():
            try:
                # Check for tasks
                task_event = self.task_queue.receive(timeout=1.0)
                if task_event:
                    self._handle_task_event(task_event)
                
                # Health check
                if not self.planner_active:
                    self.state = AgentState.ERROR
                    self.event_bus.publish(AgentEvent(
                        id=str(uuid.uuid4()),
                        source=self.id,
                        type=EventType.AGENT_ERROR,
                        data={"message": "Planner module not available"}
                    ))
                    break
                
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Planner agent error: {e}")
                time.sleep(1.0)
    
    def _handle_task_event(self, event: AgentEvent):
        """Handle task events."""
        if event.type == EventType.TASK_ASSIGNED:
            task = event.data
            self.state = AgentState.BUSY
            
            try:
                # Process the task using the original planner logic
                from jarvis.planner import plan_action
                payload = task.get("payload", {})
                user_text = payload.get("text", "") if isinstance(payload, dict) else str(payload)
                result = plan_action(user_text, use_llm=True)
                
                # Publish completion event
                self.event_bus.publish(AgentEvent(
                    id=str(uuid.uuid4()),
                    source=self.id,
                    type=EventType.TASK_COMPLETED,
                    target=event.source,
                    data={
                        "task_id": task["task_id"],
                        "result": result,
                        "agent_id": self.id
                    }
                ))
                
                self.completed_tasks.append(task["task_id"])
                logger.info(f"Planner agent completed task {task['task_id']}")
                
            except Exception as e:
                logger.error(f"Planner agent failed task {task.get('task_id', 'unknown')}: {e}")
                self.failed_tasks.append(task.get("task_id", "unknown"))
                
                # Publish failure event
                self.event_bus.publish(AgentEvent(
                    id=str(uuid.uuid4()),
                    source=self.id,
                    type=EventType.TASK_FAILED,
                    target=event.source,
                    data={
                        "task_id": task["task_id"],
                        "error": str(e),
                        "agent_id": self.id
                    }
                ))
            
            finally:
                self.state = AgentState.RUNNING
    
    def _handle_system_status(self, event: AgentEvent):
        """Handle system status updates."""
        status = event.data.get("status", {})
        if status.get("planner_module") == "unavailable":
            self.planner_active = False
            logger.warning("Planner module is unavailable")
class ExecutorAgent(Agent):
    """Agent responsible for executing tasks."""
    
    def __init__(self, config: AgentConfig, event_bus: EventBus, context: Dict[str, Any]):
        super().__init__(config, event_bus)
        self.context = context
        self.executor_active = True  # Simulate if executor.is_ready()
    
    def _setup_subscriptions(self):
        """Setup subscriptions specific to executor."""
        super()._setup_subscriptions()
        self.event_bus.subscribe(EventType.SYSTEM_STATUS, self._handle_system_status)
    
    def _main_loop(self):
        """Executor agent main loop."""
        while not self._shutdown_event.is_set():
            try:
                # Check for tasks
                task_event = self.task_queue.receive(timeout=1.0)
                if task_event:
                    self._handle_task_event(task_event)
                
                # Health check
                if not self.executor_active:
                    self.state = AgentState.ERROR
                    self.event_bus.publish(AgentEvent(
                        id=str(uuid.uuid4()),
                        source=self.id,
                        type=EventType.AGENT_ERROR,
                        data={"message": "Executor module not available"}
                    ))
                    break
                
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Executor agent error: {e}")
                time.sleep(1.0)
    
    def _handle_task_event(self, event: AgentEvent):
        """Handle task events."""
        if event.type == EventType.TASK_ASSIGNED:
            task = event.data
            self.state = AgentState.BUSY
            
            try:
                # Process the task using the original executor logic
                from task_executor import execute_plan
                result = execute_plan(task.get("payload", {}))
                
                # Publish completion event
                self.event_bus.publish(AgentEvent(
                    id=str(uuid.uuid4()),
                    source=self.id,
                    type=EventType.TASK_COMPLETED,
                    target=event.source,
                    data={
                        "task_id": task["task_id"],
                        "result": result,
                        "agent_id": self.id
                    }
                ))
                
                self.completed_tasks.append(task["task_id"])
                logger.info(f"Executor agent completed task {task['task_id']}")
                
            except Exception as e:
                logger.error(f"Executor agent failed task {task.get('task_id', 'unknown')}: {e}")
                self.failed_tasks.append(task.get("task_id", "unknown"))
                
                # Publish failure event
                self.event_bus.publish(AgentEvent(
                    id=str(uuid.uuid4()),
                    source=self.id,
                    type=EventType.TASK_FAILED,
                    target=event.source,
                    data={
                        "task_id": task["task_id"],
                        "error": str(e),
                        "agent_id": self.id
                    }
                ))
            
            finally:
                self.state = AgentState.RUNNING
    
    def _handle_system_status(self, event: AgentEvent):
        """Handle system status updates."""
        status = event.data.get("status", {})
        if status.get("executor_module") == "unavailable":
            self.executor_active = False
            logger.warning("Executor module is unavailable")
# =============================================================================
# Main Agent Orchestrator
# =============================================================================

class AgentOrchestrator:
    """Main orchestrator for all JARVIS agents."""
    
    def __init__(self, context: Dict[str, Any]):
        self.context = context
        self.event_bus = EventBus()
        self.agents: Dict[str, Agent] = {}
        self.lock = Lock()
        
        # Setup default agents
        self._setup_default_agents()
        
        logger.info("Agent orchestrator initialized")
    
    def _setup_default_agents(self):
        """Setup default agents for JARVIS."""
        # Planner Agent
        planner_config = AgentConfig(
            name="Planner",
            agent_type="planner",
            enabled=True,
            max_tasks=5,
            priority=10,
            concurrency=1,
            timeout=60.0,
            max_retries=3,
            backoff_factor=1.0,
            tags=["planning", "intelligence", "decision"],
            capabilities=["intent_analysis", "plan_generation", "multi_step"],
        )
        self.add_agent(planner_config)

        # Executor Agent
        executor_config = AgentConfig(
            name="Executor",
            agent_type="executor",
            enabled=True,
            max_tasks=10,
            priority=5,
            concurrency=2,
            timeout=30.0,
            max_retries=2,
            backoff_factor=1.0,
            tags=["execution", "automation", "action"],
            capabilities=["tool_dispatch", "task_execution", "error_recovery"],
        )
        self.add_agent(executor_config)
    
    def add_agent(self, config: AgentConfig) -> Agent:
        """Add a new agent to the orchestrator."""
        with self.lock:
            if config.name in self.agents:
                logger.warning(f"Agent {config.name} already exists")
                return self.agents[config.name]
            
            # Create agent based on type
            if config.agent_type == "planner":
                agent = PlannerAgent(config, self.event_bus, self.context)
            elif config.agent_type == "executor":
                agent = ExecutorAgent(config, self.event_bus, self.context)
            else:
                raise ValueError(f"Unknown agent type: {config.agent_type}")
            
            self.agents[config.name] = agent
            
            # Start agent if enabled
            if config.enabled:
                agent.start()
            
            logger.info(f"Added agent {config.name} ({config.agent_type})")
            return agent
    
    def remove_agent(self, agent_name: str) -> bool:
        """Remove an agent from the orchestrator."""
        with self.lock:
            if agent_name not in self.agents:
                return False
            
            agent = self.agents[agent_name]
            agent.stop()
            
            del self.agents[agent_name]
            
            logger.info(f"Removed agent {agent_name}")
            return True
    
    def get_agent(self, agent_name: str) -> Optional[Agent]:
        """Get an agent by name."""
        return self.agents.get(agent_name)
    
    def list_agents(self) -> List[Dict[str, Any]]:
        """List all agents."""
        with self.lock:
            return [agent.to_dict() for agent in self.agents.values()]
    
    def get_agent_status(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """Get status of an agent."""
        agent = self.get_agent(agent_name)
        return agent.get_status() if agent else None
    
    def assign_task(self, task: Dict[str, Any], target_agent: Optional[str] = None):
        """Assign a task to an agent."""
        with self.lock:
            # Find an available agent with matching capabilities
            candidate_agents = []
            
            for agent_name, agent in self.agents.items():
                if not agent.config.enabled or agent.state in [AgentState.STOPPING, AgentState.STOPPED]:
                    continue
                
                if target_agent and agent_name != target_agent:
                    continue
                
                # Check if agent has the required capabilities from task
                required_capabilities = task.get("capabilities", [])
                has_capabilities = all(cap in agent.config.capabilities for cap in required_capabilities)
                
                if has_capabilities and agent.state == AgentState.RUNNING:
                    candidate_agents.append((agent.config.priority, agent_name, agent))
            
            # Sort by priority (higher first)
            candidate_agents.sort(key=lambda x: x[0], reverse=True)
            
            if not candidate_agents:
                logger.warning("No available agent for task")
                return False
            
            # Assign task to the highest priority agent
            _, agent_name, agent = candidate_agents[0]
            
            logger.info(f"Assigning task {task.get('id', 'unknown')} to agent {agent_name}")
            return agent.assign_task(task, target_agent)
    
    def start_all_agents(self):
        """Start all enabled agents."""
        with self.lock:
            for agent_name, agent in self.agents.items():
                if agent.config.enabled and agent.state == AgentState.IDLE:
                    agent.start()
    
    def stop_all_agents(self):
        """Stop all agents."""
        with self.lock:
            for agent_name, agent in self.agents.items():
                agent.stop()
    
    def publish_event(self, event: AgentEvent):
        """Publish an event to all agents."""
        self.event_bus.publish(event)
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status."""
        with self.lock:
            total_tasks = sum(len(agent.pending_tasks) for agent in self.agents.values())
            completed_tasks = sum(len(agent.completed_tasks) for agent in self.agents.values())
            failed_tasks = sum(len(agent.failed_tasks) for agent in self.agents.values())
            
            return {
                "orchestrator_active": True,
                "agent_count": len(self.agents),
                "running_agents": sum(1 for agent in self.agents.values() if agent.state == AgentState.RUNNING),
                "busy_agents": sum(1 for agent in self.agents.values() if agent.state == AgentState.BUSY),
                "total_tasks_processed": completed_tasks + failed_tasks,
                "successful_tasks": completed_tasks,
                "failed_tasks": failed_tasks,
                "pending_tasks": total_tasks,
                "queue_depth": sum(agent.task_queue.get_pending_count() for agent in self.agents.values()),
                "agents": [agent.get_status() for agent in self.agents.values()]
            }

# Global orchestrator instance
_orchestrator: Optional[AgentOrchestrator] = None

def get_orchestrator(context: Optional[Dict[str, Any]] = None) -> AgentOrchestrator:
    """Get or create the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        if context is None:
            # Default minimal context
            context = {}
        _orchestrator = AgentOrchestrator(context)
    return _orchestrator

def shutdown_orchestrator():
    """Shutdown the orchestrator and all agents."""
    global _orchestrator
    if _orchestrator:
        _orchestrator.stop_all_agents()
        _orchestrator = None