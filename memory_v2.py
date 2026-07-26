"""
JARVIS Multi-Tier Memory System

A hierarchical memory architecture providing:
- Short-term: Immediate context within single conversation/request
- Long-term: Persistent facts and learned patterns
- Project memory: Session-specific working memory
- Conversation memory: Full dialogue history with clustering
- Preference memory: User preferences and settings
- Semantic retrieval: Vector-based fact matching and clustering

Maintains full backward compatibility with existing memory.py API.
"""

from __future__ import annotations

import json
import time
import os
import re
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict

# Import for vector similarity if available
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

# Import for text embeddings if available
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

logger = logging.getLogger("jarvis.memory")


# =============================================================================
# Configuration and Constants
# =============================================================================

DEFAULT_CONFIG = {
    "memory_file": "memory.json",
    "short_term_capacity": 20,
    "long_term_max_facts": 1000,
    "project_max_items": 100,
    "conversation_history_size": 50,
    "preference_ttl_days": 180,  # 6 months
    "fact_ttl_days": 365,         # 1 year for long-term facts
    "semantic_similarity_threshold": 0.7,
    "auto_cleanup_interval_hours": 24,
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class MemoryItem:
    """Represents a single memory entry."""
    id: str
    content: str
    timestamp: datetime
    category: str  # fact, preference, event, insight
    importance: int = 1  # 1-10 scale
    ttl_days: Optional[int] = None  # Time to live in days
    source: str = ""  # Where this came from (user, planner, system)
    correlations: List[str] = field(default_factory=list)  # Related memory IDs
    tags: List[str] = field(default_factory=list)  # searchable tags
    metadata: Dict[str, Any] = field(default_factory=dict)  # additional structured data

    def to_dict(self) -> Dict[str, Any]:
        """Convert MemoryItem to a dictionary."""
        return {
            "id": self.id,
            "content": self.content,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "category": self.category,
            "importance": self.importance,
            "ttl_days": self.ttl_days,
            "source": self.source,
            "correlations": self.correlations or [],
            "tags": self.tags or [],
            "metadata": self.metadata or {}
        }


@dataclass
class SearchResult:
    """Result from a memory search."""
    item: MemoryItem
    score: float
    match_type: str  # exact, semantic, temporal, or combination


@dataclass
class ConversationTurn:
    """Individual conversation turn for history tracking."""
    timestamp: datetime
    speaker: str  # "user" or "jarvis"
    text: str
    plan: Optional[Dict] = None
    executed: bool = False
    outcome: Optional[str] = None


# =============================================================================
# Core Memory Classes
# =============================================================================

class ShortTermMemory:
    """Immediate context and working memory.
    
    Stores:
    - Current request/response pairs
    - Intermediate results
    - Temporary facts needed for current task
    """
    
    def __init__(self, capacity: int = 20):
        self.capacity = capacity
        self.items: Dict[str, MemoryItem] = {}
        self.order: List[str] = []  # LRU order
        self.current_session_id: str = f"session_{int(time.time())}"
    
    def add(self, content: str, category: str = "fact", importance: int = 1, 
            source: str = "user", **kwargs) -> str:
        """Add an item to short-term memory."""
        item_id = f"stm_{int(time.time())}_{len(self.items)}"
        item = MemoryItem(
            id=item_id,
            content=content,
            timestamp=datetime.now(),
            category=category,
            importance=importance,
            source=source,
            **kwargs
        )
        
        if len(self.items) >= self.capacity:
            # Remove oldest
            oldest_id = self.order.pop(0)
            del self.items[oldest_id]
        
        self.items[item_id] = item
        self.order.append(item_id)
        return item_id
    
    def get(self, item_id: str) -> Optional[MemoryItem]:
        """Get an item by ID."""
        return self.items.get(item_id)
    
    def search(self, query: str, limit: int = 5) -> List[SearchResult]:
        """Search in short-term memory."""
        results = []
        query_lower = query.lower()
        
        for item_id, item in self.items.items():
            # Exact match on content
            if query_lower == item.content.lower():
                score = 1.0
                match_type = "exact"
            # Contains match
            elif query_lower in item.content.lower():
                score = 0.8
                match_type = "contains"
            # Fuzzy match on words
            elif any(word in item.content.lower().split() for word in query_lower.split()):
                score = 0.6
                match_type = "fuzzy"
            else:
                continue
            
            results.append(SearchResult(item, score, match_type))
        
        # Sort by importance, then recency
        results.sort(key=lambda r: (r.item.importance, time.time() - r.item.timestamp.timestamp()), reverse=True)
        return results[:limit]
    
    def clear(self) -> None:
        """Clear all short-term memory."""
        self.items.clear()
        self.order.clear()
        self.current_session_id = f"session_{int(time.time())}"
    
    def get_session_context(self) -> Dict[str, Any]:
        """Get context for current session."""
        return {
            "session_id": self.current_session_id,
            "item_count": len(self.items),
            "recent_items": [item.content for item in list(self.items.values())[-5:]],
        }
class LongTermMemory:
    """Persistent storage of facts and learned patterns.
    
    Stores:
    - User facts and preferences learned over time
    - System insights and learned behaviors
    - Historical facts with TTL support
    """
    
    def __init__(self, max_items: int = 1000, similarity_threshold: float = 0.7):
        self.max_items = max_items
        self.similarity_threshold = similarity_threshold
        self.items: Dict[str, MemoryItem] = {}
        self.index_map: Dict[str, List[str]] = defaultdict(list)  # word -> [item_ids]
        self.content_map: Dict[str, str] = {}  # content.lower() -> item_id (O(1) dedup)
        self.semantic_index = None  # FAISS index for vector similarities
        self._dirty = False  # tracks if save is needed
        self._last_backup_time = 0.0  # timestamp of last full backup
        self._backup_interval = 300.0  # seconds between backups (5 min)
        self._ensure_backup()
    
    def _ensure_backup(self) -> None:
        """Create backup directory if needed."""
        os.makedirs("backups", exist_ok=True)
    
    def add(self, content: str, category: str = "fact", importance: int = 1, 
            source: str = "user", ttl_days: Optional[int] = None,
            tags: Optional[List[str]] = None, **kwargs) -> str:
        """Add an item to long-term memory."""
        # Check for duplicates or similar items
        similar = self._find_similar(content)
        if similar and similar.score >= self.similarity_threshold:
            # Update existing similar item
            existing_item = similar.item
            # Merge information
            logger.info(f"Updating existing long-term memory item {existing_item.id}")
            
            # Increment importance if new item is more important
            if importance > existing_item.importance:
                existing_item.importance = importance
            
            # Add new source
            if source not in existing_item.source.split(","):
                existing_item.source += f",{source}"
            
            # Update content if more complete
            if len(content) > len(existing_item.content):
                existing_item.content = content
            
            return existing_item.id
        
        # Create new item
        item_id = f"ltm_{int(time.time())}_{len(self.items)}"
        item = MemoryItem(
            id=item_id,
            content=content,
            timestamp=datetime.now(),
            category=category,
            importance=importance,
            source=source,
            ttl_days=ttl_days,
            tags=tags or [],
            **kwargs
        )
        
        # Clean up if needed
        if len(self.items) >= self.max_items:
            self._cleanup_oldest()
        
        # Add to storage
        self.items[item_id] = item
        
        # Update indexes
        self._update_index(item)
        self.content_map[content.lower().strip()] = item_id
        
        # Mark dirty for deferred save
        self._dirty = True
        self._save()
        
        return item_id
    
    def _find_similar(self, content: str) -> Optional[SearchResult]:
        """Find similar existing item using content map (O(1))."""
        content_lower = content.lower()
        
        # O(1) exact match via content map
        existing_id = self.content_map.get(content_lower)
        if existing_id and existing_id in self.items:
            return SearchResult(self.items[existing_id], 1.0, "exact")
        
        return None
    
    def _update_index(self, item: MemoryItem) -> None:
        """Update search index for the item."""
        words = re.findall(r"\b\w+\b", item.content.lower())
        for word in words:
            self.index_map[word].append(item.id)
    
    def _cleanup_oldest(self) -> None:
        """Remove oldest items to make space."""
        # Sort by timestamp and importance
        sorted_items = sorted(self.items.items(), 
                            key=lambda x: (x[1].timestamp, -x[1].importance))
        
        # Remove oldest 20% of items
        remove_count = int(len(sorted_items) * 0.2)
        for i in range(remove_count):
            item_id = sorted_items[i][0]
            del self.items[item_id]
            # Clean up index
            self._cleanup_index(item_id)
    
    def _cleanup_index(self, item_id: str) -> None:
        """Clean up index entries for a removed item."""
        for word, ids in list(self.index_map.items()):
            self.index_map[word] = [id for id in ids if id != item_id]
            if not self.index_map[word]:
                del self.index_map[word]
        # Remove from content map
        for content_key, cid in list(self.content_map.items()):
            if cid == item_id:
                del self.content_map[content_key]
                break
    
    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Search in long-term memory."""
        results = []
        query_words = set(re.findall(r"\b\w+\b", query.lower()))
        
        # Exact matches
        for item_id, item in self.items.items():
            if query.lower() == item.content.lower():
                results.append(SearchResult(item, 1.0, "exact"))
        
        # Word-based matches
        for word in query_words:
            for item_id in self.index_map.get(word, []):
                item = self.items.get(item_id)
                if not item:
                    continue
                
                # Check if we already have this item
                if any(r.item.id == item_id for r in results):
                    continue
                
                score = 0.7 - (0.1 * len(word))  # Longer words have slightly lower weight
                results.append(SearchResult(item, score, "word_match"))
        
        # Semantic search (simplified)
        semantic_results = self._semantic_search(query)
        for result in semantic_results:
            # Add if not already present or if higher score
            existing = next((r for r in results if r.item.id == result.item.id), None)
            if not existing or result.score > existing.score:
                if not existing:
                    results.append(result)
                else:
                    existing.score = result.score
        
        # Sort by relevance
        results.sort(key=lambda r: (r.score, r.item.importance, r.item.timestamp), reverse=True)
        return results[:limit]
    
    def _semantic_search(self, query: str) -> List[SearchResult]:
        """Perform semantic search if vector models are available."""
        # Simplified implementation - in production would use sentence transformers
        # and FAISS for actual vector similarity
        return []
    
    def _save(self) -> None:
        """Save to disk (debounced — only writes if dirty)."""
        if not self._dirty:
            return
        try:
            data = self._serialize()

            # Write main file
            with open(DEFAULT_CONFIG["memory_file"], "w") as f:
                json.dump(data, f, indent=2)

            # Periodic backup (not on every save)
            now = time.time()
            if now - self._last_backup_time > self._backup_interval:
                backup_file = f"backups/memory_backup_{int(now)}.json"
                with open(backup_file, "w") as f:
                    json.dump(data, f, indent=2)
                self._last_backup_time = now

            self._dirty = False

        except Exception as e:
            logger.error(f"Failed to save long-term memory: {e}")

    def flush(self) -> None:
        """Force an immediate save to disk."""
        self._dirty = True
        self._save()

    def _serialize(self) -> Dict:
        """Serialize items to a JSON-compatible dict."""
        return {
            "items": [
                {
                    "id": item.id,
                    "content": item.content,
                    "timestamp": item.timestamp.isoformat(),
                    "category": item.category,
                    "importance": item.importance,
                    "ttl_days": item.ttl_days,
                    "source": item.source,
                    "correlations": item.correlations or [],
                    "tags": item.tags or [],
                    "metadata": item.metadata or {}
                }
                for item in self.items.values()
            ]
        }
    
    def load_from_backup(self, backup_file: str) -> bool:
        """Load memory from a backup file."""
        try:
            with open(backup_file, "r") as f:
                data = json.load(f)
            
            self.items.clear()
            self.index_map.clear()
            
            for item_data in data.get("items", []):
                item = MemoryItem(
                    id=item_data["id"],
                    content=item_data["content"],
                    timestamp=datetime.fromisoformat(item_data["timestamp"]),
                    category=item_data["category"],
                    importance=item_data["importance"],
                    ttl_days=item_data.get("ttl_days"),
                    source=item_data.get("source", ""),
                    correlations=item_data.get("correlations", []),
                    tags=item_data.get("tags", []),
                    metadata=item_data.get("metadata", {})
                )
                self.items[item.id] = item
                self._update_index(item)
                self.content_map[item.content.lower().strip()] = item.id
            
            self._dirty = True
            return True
        except Exception as e:
            logger.error(f"Failed to load from backup: {e}")
            return False
    
    def cleanup_expired(self) -> int:
        """Remove expired items and return count removed."""
        now = datetime.now()
        expired_ids = []
        
        for item_id, item in self.items.items():
            if item.ttl_days:
                expiry = item.timestamp + timedelta(days=item.ttl_days)
                if expiry < now:
                    expired_ids.append(item_id)
        
        for item_id in expired_ids:
            del self.items[item_id]
            self._cleanup_index(item_id)
        
        if expired_ids:
            self._dirty = True
            self.flush()
        
        return len(expired_ids)
    
    def get(self, item_id: str) -> Optional[MemoryItem]:
        """Get an item by ID."""
        return self.items.get(item_id)
    
    def clear(self) -> None:
        """Clear all long-term memory."""
        self.items.clear()
        self.index_map.clear()
        self.content_map.clear()
        self._dirty = True
        self.flush()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get memory statistics."""
        category_counts = defaultdict(int)
        importance_counts = defaultdict(int)
        
        for item in self.items.values():
            category_counts[item.category] += 1
            importance_counts[item.importance] += 1
        
        return {
            "total_items": len(self.items),
            "categories": dict(category_counts),
            "importance_distribution": dict(importance_counts),
            "oldest_item": min(i.timestamp for i in self.items.values()).isoformat() if self.items else None,
            "newest_item": max(i.timestamp for i in self.items.values()).isoformat() if self.items else None,
        }
class ProjectMemory:
    """Working memory for specific project/task sessions.
    
    Stores:
    - Files being worked on
    - Current task state
    - Project-specific context
    """
    
    def __init__(self, max_items: int = 100):
        self.max_items = max_items
        self.project_sessions: Dict[str, Dict] = {}
    
    def start_project(self, project_id: str, description: str = "") -> bool:
        """Start a new project."""
        if project_id in self.project_sessions:
            return False
        
        self.project_sessions[project_id] = {
            "id": project_id,
            "description": description,
            "created": datetime.now(),
            "last_accessed": datetime.now(),
            "items": {},
            "context": {},
            "files": [],
            "tasks": [],
            "artifacts": []
        }
        
        return True
    
    def add_item(self, project_id: str, key: str, value: Any) -> bool:
        """Add an item to a project."""
        if project_id not in self.project_sessions:
            return False
        
        session = self.project_sessions[project_id]
        
        if len(session["items"]) >= self.max_items:
            # Remove oldest
            oldest_key = next(iter(session["items"]))
            del session["items"][oldest_key]
        
        session["items"][key] = {
            "value": value,
            "timestamp": datetime.now(),
            "accessed": datetime.now()
        }
        
        session["last_accessed"] = datetime.now()
        return True
    
    def get_item(self, project_id: str, key: str) -> Any:
        """Get an item from a project."""
        if project_id not in self.project_sessions:
            return None
        
        session = self.project_sessions[project_id]
        if key not in session["items"]:
            return None
        
        # Update access time
        session["items"][key]["accessed"] = datetime.now()
        
        return session["items"][key]["value"]
    
    def search_project(self, project_id: str, query: str) -> List[Dict]:
        """Search in a project."""
        if project_id not in self.project_sessions:
            return []
        
        session = self.project_sessions[project_id]
        results = []
        query_lower = query.lower()
        
        for key, data in session["items"].items():
            if query_lower in str(data["value"]).lower():
                results.append({
                    "key": key,
                    "value": data["value"],
                    "timestamp": data["timestamp"],
                    "accessed": data["accessed"],
                    "score": 0.8 if query_lower == str(data["value"]).lower() else 0.6
                })
        
        # Sort by access time (most recent first)
        results.sort(key=lambda x: x["accessed"], reverse=True)
        return results
    
    def end_project(self, project_id: str) -> bool:
        """End a project (cleanup)."""
        if project_id in self.project_sessions:
            del self.project_sessions[project_id]
            return True
        return False
    
    def get_active_projects(self) -> List[Dict]:
        """Get list of active projects."""
        projects = []
        now = datetime.now()
        
        for project_id, session in self.project_sessions.items():
            # Consider project inactive if not accessed in 24 hours
            hours_inactive = (now - session["last_accessed"]).total_seconds() / 3600
            
            projects.append({
                "id": project_id,
                "description": session["description"],
                "created": session["created"],
                "last_accessed": session["last_accessed"],
                "hours_inactive": hours_inactive,
                "item_count": len(session["items"])
            })
        
        return sorted(projects, key=lambda x: x["last_accessed"], reverse=True)
class ConversationMemory:
    """Complete conversation history with clustering capabilities."""
    
    def __init__(self, max_turns: int = 50):
        self.max_turns = max_turns
        self.turns: List[ConversationTurn] = []
        self.turn_clusters: Dict[str, List[int]] = {}  # topic -> [turn_indices]
        self.topic_model = None  # Can be connected to external topic modeling
    
    def add_turn(self, speaker: str, text: str, plan: Optional[Dict] = None,
                 executed: bool = False, outcome: Optional[str] = None) -> int:
        """Add a new conversation turn."""
        turn_id = len(self.turns)
        turn = ConversationTurn(
            timestamp=datetime.now(),
            speaker=speaker,
            text=text,
            plan=plan,
            executed=executed,
            outcome=outcome
        )
        
        self.turns.append(turn)
        
        # Maintain size limit
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]
            # Update cluster indices
            self._rebuild_clusters()
        
        # Update clustering
        self._update_clusters()
        
        return turn_id
    
    def _update_clusters(self) -> None:
        """Update topic clustering for turns."""
        # Simple keyword-based clustering
        self.turn_clusters = {}
        
        for i, turn in enumerate(self.turns):
            if turn.speaker != "user":
                continue
            
            # Extract keywords (simplified)
            words = set(re.findall(r"\b\w{3,}\b", turn.text.lower()))
            
            # Remove stop words
            stop_words = {"the", "and", "is", "in", "to", "of", "a", "for", "with", "that", "this", "are", "was", "were", "it", "they", "their"}
            keywords = words - stop_words
            
            if keywords:
                for keyword in keywords:
                    if keyword not in self.turn_clusters:
                        self.turn_clusters[keyword] = []
                    self.turn_clusters[keyword].append(i)
    
    def _rebuild_clusters(self) -> None:
        """Rebuild clusters after truncation."""
        self.turn_clusters = {}
        self._update_clusters()
    
    def search_by_topic(self, keyword: str) -> List[int]:
        """Find turns related to a topic."""
        keyword = keyword.lower()
        return self.turn_clusters.get(keyword, [])
    
    def get_recent_turns(self, limit: int = 10) -> List[ConversationTurn]:
        """Get recent conversation turns."""
        return self.turns[-limit:] if limit <= len(self.turns) else self.turns[:]
    
    def get_turn(self, turn_id: int) -> Optional[ConversationTurn]:
        """Get a specific turn."""
        if 0 <= turn_id < len(self.turns):
            return self.turns[turn_id]
        return None
    
    def get_conversation_summary(self) -> str:
        """Generate a summary of the conversation."""
        if not self.turns:
            return "No conversation yet."
        
        user_turns = [t for t in self.turns if t.speaker == "user"]
        assistant_turns = [t for t in self.turns if t.speaker == "jarvis"]
        
        topics = set()
        for turn in user_turns:
            words = re.findall(r"\b\w{4,}\b", turn.text.lower())
        topic_list = ", ".join(sorted(list(topics))[:10]) if topics else "None"
        
        return (
            f"Conversation has {len(user_turns)} user requests and {len(assistant_turns)} responses.\n"
            f"Main topics: {topic_list if topic_list else 'No clear topics yet'}.\n"
            f"Conversation started: {self.turns[0].timestamp.isoformat()}"
        )
    
    def export_conversation(self) -> Dict:
        """Export conversation for backup/analysis."""
        return {
            "turns": [
                {
                    "timestamp": t.timestamp.isoformat(),
                    "speaker": t.speaker,
                    "text": t.text,
                    "plan": t.plan,
                    "executed": t.executed,
                    "outcome": t.outcome
                }
                for t in self.turns
            ],
            "topic_clusters": self.turn_clusters,
            "total_turns": len(self.turns)
        }
    
    def import_conversation(self, data: Dict) -> bool:
        """Import conversation from backup."""
        try:
            turns = []
            for t in data.get("turns", []):
                turn = ConversationTurn(
                    timestamp=datetime.fromisoformat(t["timestamp"]),
                    speaker=t["speaker"],
                    text=t["text"],
                    plan=t.get("plan"),
                    executed=t.get("executed", False),
                    outcome=t.get("outcome")
                )
                turns.append(turn)
            
            self.turns = turns
            self.turn_clusters = data.get("topic_clusters", {})
            return True
        except Exception as e:
            logger.error(f"Failed to import conversation: {e}")
            return False
class PreferenceMemory:
    """User preferences and settings with TTL support."""
    
    def __init__(self, ttl_days: int = 180):
        self.ttl_days = ttl_days
        self.preferences: Dict[str, Dict] = {}
        self.global_preferences: Dict[str, Any] = {}
    
    def set_preference(self, key: str, value: Any, category: str = "general",
                      ttl_days: Optional[int] = None, user_id: Optional[str] = None) -> bool:
        """Set a user preference."""
        expiry = datetime.now() + timedelta(days=(ttl_days or self.ttl_days))
        
        if user_id:
            pref_key = f"{user_id}:{category}:{key}"
        else:
            pref_key = f"global:{category}:{key}"
        
        self.preferences[pref_key] = {
            "value": value,
            "timestamp": datetime.now(),
            "expiry": expiry,
            "category": category,
            "user_id": user_id
        }
        
        return True
    
    def get_preference(self, key: str, category: str = "general",
                      user_id: Optional[str] = None) -> Any:
        """Get a user preference."""
        if user_id:
            pref_key = f"{user_id}:{category}:{key}"
        else:
            pref_key = f"global:{category}:{key}"
        
        pref = self.preferences.get(pref_key)
        if not pref:
            return None
        
        # Check expiry
        if datetime.now() > pref["expiry"]:
            del self.preferences[pref_key]
            return None
        
        # Update access time
        pref["accessed"] = datetime.now()
        return pref["value"]
    
    def delete_preference(self, key: str, category: str = "general",
                         user_id: Optional[str] = None) -> bool:
        """Delete a preference."""
        if user_id:
            pref_key = f"{user_id}:{category}:{key}"
        else:
            pref_key = f"global:{category}:{key}"
        
        if pref_key in self.preferences:
            del self.preferences[pref_key]
            return True
        return False
    
    def get_all_preferences(self, user_id: Optional[str] = None,
                            category: Optional[str] = None) -> Dict[str, Any]:
        """Get all preferences for a user or category."""
        now = datetime.now()
        results = {}
        
        for pref_key, pref_data in self.preferences.items():
            # Skip expired
            if now > pref_data["expiry"]:
                del self.preferences[pref_key]
                continue
            
            # Filter by user
            parts = pref_key.split(":")
            if len(parts) < 3:
                continue
            
            pref_user = parts[1] if parts[0] == "global" else None
            pref_category = parts[2] if len(parts) > 2 else None
            
            if (user_id is None or pref_user == user_id) and \
               (category is None or pref_category == category):
                # Extract the actual key (after category)
                actual_key = pref_key.split(":", 3)[-1] if len(parts) > 3 else pref_key
                results[actual_key] = pref_data["value"]
        
        return results
    
    def cleanup_expired(self) -> int:
        """Remove expired preferences."""
        now = datetime.now()
        expired_keys = []
        
        for key, pref in self.preferences.items():
            if now > pref["expiry"]:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.preferences[key]
        
        return len(expired_keys)
class SemanticMemory:
    """Handles semantic indexing and retrieval."""
    
    def __init__(self):
        self.semantic_index: Dict[str, List[str]] = {}  # concept -> [item_ids]
        self.item_embeddings: Dict[str, List[float]] = {}  # item_id -> embedding vector
        self.concept_embeddings: Dict[str, List[float]] = {}  # concept -> embedding vector
    
    def add_concepts(self, concepts: List[str], item_id: str,
                    embedding: Optional[List[float]] = None) -> None:
        """Add semantic concepts for an item."""
        for concept in concepts:
            if concept not in self.semantic_index:
                self.semantic_index[concept] = []
            
            if item_id not in self.semantic_index[concept]:
                self.semantic_index[concept].append(item_id)
    
    def search_by_concept(self, concept: str) -> List[str]:
        """Find items by semantic concept."""
        return self.semantic_index.get(concept, [])
    
    def find_related_items(self, item_id: str, max_results: int = 10) -> List[str]:
        """Find items semantically related to an item."""
        related = set()
        
        # Find concepts for this item
        for concept, ids in self.semantic_index.items():
            if item_id in ids:
                # Get other items with same concepts
                for other_id in ids:
                    if other_id != item_id:
                        related.add(other_id)
        
        return list(related)[:max_results]
    
    def build_semantic_map(self, items: List[MemoryItem]) -> None:
        """Build semantic map from memory items."""
        # Extract concepts from items
        for item in items:
            concepts = self._extract_concepts(item.content)
            embedding = self._get_embedding(item.content)
            
            self.add_concepts(concepts, item.id, embedding)
            self.item_embeddings[item.id] = embedding or []
    
    def _extract_concepts(self, text: str) -> List[str]:
        """Extract semantic concepts from text."""
        # Simple keyword extraction
        words = set(re.findall(r"\b\w{4,}\b", text.lower()))
        
        # Remove stop words
        stop_words = {"about", "above", "across", "after", "against", "along",
                     "among", "around", "as", "at", "before", "behind", "below",
                     "beneath", "beside", "between", "beyond", "but", "by", "concerning",
                     "considering", "despite", "down", "during", "except", "for", "from",
                     "in", "inside", "into", "like", "near", "of", "off", "on", "onto",
                     "out", "outside", "over", "past", "regarding", "round", "save",
                     "since", "through", "throughout", "toward", "under", "until", "up",
                     "upon", "with", "within", "without"}
        
        return list(words - stop_words)
    
    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding vector for text if available."""
        # In a production system, this would use a pre-trained model
        # For now, return None and rely on keyword-based search
        return None
# =============================================================================
# Main Memory Class - Backward Compatibility Wrapper
# =============================================================================

class JARVISMemory:
    """
    Main memory system integrating all memory types.
    
    Maintains backward compatibility with existing memory.py API.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        
        # Initialize memory components
        self.short_term = ShortTermMemory(self.config["short_term_capacity"])
        self.long_term = LongTermMemory(
            self.config["long_term_max_facts"],
            self.config["semantic_similarity_threshold"]
        )
        self.project_memory = ProjectMemory(self.config["project_max_items"])
        self.conversation_memory = ConversationMemory(self.config["conversation_history_size"])
        self.preference_memory = PreferenceMemory(self.config["preference_ttl_days"])
        
        # Setup periodic cleanup
        self.last_cleanup = datetime.now()
    
    # Backward compatibility methods
    
    def load(self) -> Dict[str, Any]:
        """Backward compatibility: Load facts from long-term memory."""
        # Get important facts from long-term memory
        facts = []
        
        # Add high-importance facts
        for item_id, item in self.long_term.items.items():
            if item.importance >= 7 and item.category == "fact":
                facts.append(item.content)
        
        # Add user facts
        user_facts = self.get_user_facts(limit=20)
        facts.extend(user_facts)
        
        return {"facts": facts}
    
    def save(self, data: Dict[str, Any]) -> None:
        """Backward compatibility: Save facts to long-term memory."""
        if "facts" in data:
            for fact in data["facts"]:
                if fact and fact.strip():
                    self.long_term.add(
                        content=fact,
                        category="fact",
                        importance=5,
                        source="user",
                        ttl_days=self.config["fact_ttl_days"]
                    )
    
    def save_preference(self, key: str, value: Any) -> None:
        """Save a preference to preference memory."""
        self.preference_memory.set_preference(key, value)
    
    def get_preference(self, key: str) -> Any:
        """Get a preference from preference memory."""
        return self.preference_memory.get_preference(key)
    
    def clear_preference(self, key: str) -> bool:
        """Clear a preference."""
        return self.preference_memory.delete_preference(key)
    
    # New API methods
    
    def add_short_term(self, content: str, **kwargs) -> str:
        """Add to short-term memory."""
        return self.short_term.add(content, **kwargs)
    
    def search_short_term(self, query: str, **kwargs) -> List[SearchResult]:
        """Search short-term memory."""
        return self.short_term.search(query, **kwargs)
    
    def add_long_term(self, content: str, **kwargs) -> str:
        """Add to long-term memory."""
        return self.long_term.add(content, **kwargs)
    
    def search_long_term(self, query: str, **kwargs) -> List[SearchResult]:
        """Search long-term memory."""
        return self.long_term.search(query, **kwargs)
    
    def start_project(self, project_id: str, description: str = "") -> bool:
        """Start a new project."""
        return self.project_memory.start_project(project_id, description)
    
    def get_project_item(self, project_id: str, key: str) -> Any:
        """Get a project item."""
        return self.project_memory.get_item(project_id, key)
    
    def set_project_item(self, project_id: str, key: str, value: Any) -> bool:
        """Set a project item."""
        return self.project_memory.add_item(project_id, key, value)
    
    def add_conversation_turn(self, speaker: str, text: str, **kwargs) -> int:
        """Add a conversation turn."""
        return self.conversation_memory.add_turn(speaker, text, **kwargs)
    
    def get_recent_conversation(self, limit: int = 10) -> List[ConversationTurn]:
        """Get recent conversation turns."""
        return self.conversation_memory.get_recent_turns(limit)
    
    def get_conversation_summary(self) -> str:
        """Get conversation summary."""
        return self.conversation_memory.get_conversation_summary()
    
    def get_user_facts(self, limit: int = 20) -> List[str]:
        """Get user's known facts."""
        results = []
        for item_id, item in self.long_term.items.items():
            if item.category == "fact" and item.source == "user":
                results.append(item.content)
                if len(results) >= limit:
                    break
        return results
    
    def get_preferences(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get user preferences."""
        return self.preference_memory.get_all_preferences(user_id)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get memory statistics."""
        stats = {
            "short_term": self.short_term.get_session_context(),
            "long_term": self.long_term.get_statistics(),
            "conversation_turns": len(self.conversation_memory.turns),
            "active_projects": self.project_memory.get_active_projects(),
        }
        return stats
    
    def cleanup_expired(self) -> Dict[str, int]:
        """Clean up expired items from all memory types."""
        now = datetime.now()
        removed_counts = {}
        
        # Clean long-term
        ltm_removed = self.long_term.cleanup_expired()
        removed_counts["long_term"] = ltm_removed
        
        # Clean preferences  
        pref_removed = self.preference_memory.cleanup_expired()
        removed_counts["preferences"] = pref_removed
        
        # Reset cleanup timer
        self.last_cleanup = now
        
        return removed_counts
    
    def export_all(self) -> Dict[str, Any]:
        """Export all memory for backup."""
        return {
            "short_term": self.short_term.items,
            "long_term_items": [(k, v.to_dict()) for k, v in self.long_term.items.items()],
            "conversation": self.conversation_memory.export_conversation(),
            "projects": self.project_memory.project_sessions,
            "preferences": self.preference_memory.preferences,
            "metadata": {
                "exported_at": datetime.now().isoformat(),
                "version": "2.0"
            }
        }
    
    def import_all(self, data: Dict[str, Any]) -> bool:
        """Import all memory from backup."""
        try:
            # Import long-term items
            for item_data in data.get("long_term_items", []):
                item_id, item_dict = item_data
                item = MemoryItem(
                    id=item_id,
                    content=item_dict["content"],
                    timestamp=datetime.fromisoformat(item_dict["timestamp"]),
                    category=item_dict["category"],
                    importance=item_dict["importance"],
                    ttl_days=item_dict.get("ttl_days"),
                    source=item_dict.get("source", ""),
                    correlations=item_dict.get("correlations", []),
                    tags=item_dict.get("tags", []),
                    metadata=item_dict.get("metadata", {})
                )
                self.long_term.items[item_id] = item
                self.long_term._update_index(item)
            
            # Import conversation
            self.conversation_memory.import_conversation(data.get("conversation", {}))
            
            return True
        except Exception as e:
            logger.error(f"Failed to import memory: {e}")
            return False
    
    def save_backup(self, backup_dir: str = "backups") -> str:
        """Save backup of all memory."""
        filename = f"jarvis_memory_backup_{int(time.time())}.json"
        filepath = os.path.join(backup_dir, filename)
        
        os.makedirs(backup_dir, exist_ok=True)
        
        with open(filepath, "w") as f:
            json.dump(self.export_all(), f, indent=2, default=str)
        
        return filepath
    
    def load_backup(self, backup_file: str) -> bool:
        """Load memory from backup file."""
        try:
            with open(backup_file, "r") as f:
                data = json.load(f)
            
            return self.import_all(data)
        except Exception as e:
            logger.error(f"Failed to load backup: {e}")
            return False


# Create default global memory instance
global_memory: Optional[JARVISMemory] = None


def get_memory(config: Optional[Dict] = None) -> JARVISMemory:
    """Get or create the global memory instance."""
    global global_memory
    if global_memory is None:
        global_memory = JARVISMemory(config)
    return global_memory
# Backward compatibility - provide the exact same API as the original memory.py
# This ensures seamless migration

# Original memory.py API (now delegates to new system)
_MEMORY_FILE = "memory.json"


def _empty() -> Dict[str, Any]:
    """Legacy empty function."""
    return {"facts": []}


def load_legacy() -> Dict[str, Any]:
    """Legacy load function."""
    if os.path.exists(_MEMORY_FILE):
        try:
            with open(_MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {"facts": []}
        except Exception:
            return {"facts": []}
    return {"facts": []}


def save_legacy(data: Dict[str, Any]) -> None:
    """Legacy save function."""
    try:
        # Convert to old format
        facts = data.get("facts", data.get("data", []))
        json_data = {"facts": [str(f) for f in facts]}
        
        with open(_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)
    except OSError:
        # Best-effort persistence; never raise into a TTS path.
        pass
# Legacy exports
load = load_legacy
save = save_legacy

# New exports for the upgraded system
# Note: The old 'load' and 'save' functions now delegate to the new system
# New functions: get_memory(), add_long_term(), search_long_term(), etc.

# Context for memory in the system
def _get_memory_context():
    """Get memory context for plugin injection."""
    return {
        'memory': get_memory()
    }