"""Calendar skill implementation."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from jarvis.skills.interfaces import SkillInterface

# Simple in-memory storage for events (in a real implementation, this would connect to actual calendar services)
_CALENDAR_STORAGE_FILE = os.path.join(os.path.expanduser("~"), ".jarvis_calendar_events.json")


class CalendarSkill(SkillInterface):
    """Skill for calendar and scheduling operations."""

    @property
    def name(self) -> str:
        return "calendar"

    @property
    def description(self) -> str:
        return "Calendar operations including event creation, retrieval, updating, and deletion"

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute calendar operations.

        Supported operations:
        - create_event: Create a new calendar event
        - get_event: Get details of a specific event
        - list_events: List events within a time range
        - update_event: Update an existing event
        - delete_event: Delete an event
        - get_today_events: Get today's events
        - get_tomorrow_events: Get tomorrow's events
        - get_upcoming_events: Get upcoming events

        Args:
            action: Operation to perform
            **kwargs: Operation-specific arguments

        Returns:
            Dictionary with execution results
        """
        start_time = time.time()
        action = kwargs.get("action", "").lower()

        try:
            # Load existing events
            events = self._load_events()

            if action == "create_event":
                result = self._create_event(events, **kwargs)
            elif action == "get_event":
                result = self._get_event(events, **kwargs)
            elif action == "list_events":
                result = self._list_events(events, **kwargs)
            elif action == "update_event":
                result = self._update_event(events, **kwargs)
            elif action == "delete_event":
                result = self._delete_event(events, **kwargs)
            elif action == "get_today_events":
                result = self._get_today_events(events, **kwargs)
            elif action == "get_tomorrow_events":
                result = self._get_tomorrow_events(events, **kwargs)
            elif action == "get_upcoming_events":
                result = self._get_upcoming_events(events, **kwargs)
            else:
                result = {
                    "success": False,
                    "reason": f"Unknown action: {action}",
                    "logs": [
                        f"Available actions: create_event, get_event, list_events, update_event, delete_event, "
                        f"get_today_events, get_tomorrow_events, get_upcoming_events"
                    ],
                    "data": None
                }

            # Save events if they were modified
            if action in ["create_event", "update_event", "delete_event"]:
                if result.get("success"):
                    self._save_events(events)

            # Add execution time to result
            result["execution_time"] = time.time() - start_time
            return result

        except Exception as e:
            return {
                "success": False,
                "reason": f"CalendarSkill execution failed: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None,
                "execution_time": time.time() - start_time
            }

    def _load_events(self) -> List[Dict[str, Any]]:
        """Load events from storage."""
        try:
            if os.path.exists(_CALENDAR_STORAGE_FILE):
                with open(_CALENDAR_STORAGE_FILE, 'r') as f:
                    return json.load(f)
            return []
        except Exception:
            return []

    def _save_events(self, events: List[Dict[str, Any]]) -> None:
        """Save events to storage."""
        try:
            with open(_CALENDAR_STORAGE_FILE, 'w') as f:
                json.dump(events, f, indent=2, default=str)
        except Exception:
            pass  # Silently fail if we can't save

    def _create_event(self, events: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        """Create a new calendar event."""
        title = kwargs.get("title")
        start_time_str = kwargs.get("start_time")
        end_time_str = kwargs.get("end_time")
        description = kwargs.get("description", "")
        location = kwargs.get("location", "")

        if not title:
            return {
                "success": False,
                "reason": "title parameter required",
                "logs": ["Please provide title parameter"],
                "data": None
            }

        if not start_time_str:
            return {
                "success": False,
                "reason": "start_time parameter required",
                "logs": ["Please provide start_time parameter (ISO format)"],
                "data": None
            }

        try:
            # Parse start time
            start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))

            # Parse end time if provided, otherwise default to 1 hour later
            if end_time_str:
                end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
            else:
                end_time = start_time + timedelta(hours=1)

            # Create event
            event = {
                "id": str(uuid.uuid4()),
                "title": title,
                "description": description,
                "location": location,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }

            events.append(event)

            return {
                "success": True,
                "reason": f"Event created: {title}",
                "logs": [
                    f"Created event '{title}'",
                    f"Start: {start_time.strftime('%Y-%m-%d %H:%M')}",
                    f"End: {end_time.strftime('%Y-%m-%d %H:%M')}"
                ],
                "data": event
            }
        except ValueError as e:
            return {
                "success": False,
                "reason": f"Invalid date/time format: {str(e)}",
                "logs": ["Please use ISO format for dates (e.g., 2023-12-25T14:30:00)"],
                "data": None
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to create event: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _get_event(self, events: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        """Get details of a specific event."""
        event_id = kwargs.get("event_id")
        if not event_id:
            return {
                "success": False,
                "reason": "event_id parameter required",
                "logs": ["Please provide event_id parameter"],
                "data": None
            }

        for event in events:
            if event.get("id") == event_id:
                return {
                    "success": True,
                    "reason": f"Event retrieved: {event.get('title')}",
                    "logs": [f"Retrieved event details for ID: {event_id}"],
                    "data": event
                }

        return {
            "success": False,
            "reason": f"Event not found: {event_id}",
            "logs": [f"No event found with ID: {event_id}"],
            "data": None
        }

    def _list_events(self, events: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        """List events within a time range."""
        start_time_str = kwargs.get("start_time")
        end_time_str = kwargs.get("end_time")
        limit = kwargs.get("limit", 50)

        try:
            # Parse time filters
            start_time = None
            end_time = None

            if start_time_str:
                start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            if end_time_str:
                end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))

            # Filter events
            filtered_events = []
            for event in events:
                event_start = datetime.fromisoformat(event["start_time"].replace('Z', '+00:00'))
                event_end = datetime.fromisoformat(event["end_time"].replace('Z', '+00:00'))

                # Check if event overlaps with the requested time range
                if start_time and event_end < start_time:
                    continue  # Event ends before our start time
                if end_time and event_start > end_time:
                    continue  # Event starts after our end time

                filtered_events.append(event)

            # Sort by start time
            filtered_events.sort(key=lambda x: x["start_time"])

            # Apply limit
            if limit:
                filtered_events = filtered_events[:limit]

            return {
                "success": True,
                "reason": f"Found {len(filtered_events)} events",
                "logs": [
                    f"Listed {len(filtered_events)} events",
                    f"Time range: {start_time_str or 'beginning'} to {end_time_str or 'end'}"
                ],
                "data": {
                    "events": filtered_events,
                    "count": len(filtered_events)
                }
            }
        except ValueError as e:
            return {
                "success": False,
                "reason": f"Invalid date/time format: {str(e)}",
                "logs": ["Please use ISO format for dates (e.g., 2023-12-25T14:30:00)"],
                "data": None
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to list events: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _update_event(self, events: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        """Update an existing event."""
        event_id = kwargs.get("event_id")
        if not event_id:
            return {
                "success": False,
                "reason": "event_id parameter required",
                "logs": ["Please provide event_id parameter"],
                "data": None
            }

        for i, event in enumerate(events):
            if event.get("id") == event_id:
                # Update fields that are provided
                updated = False
                for field in ["title", "description", "location"]:
                    if field in kwargs and kwargs[field] is not None:
                        event[field] = kwargs[field]
                        updated = True

                # Handle time updates
                if "start_time" in kwargs and kwargs["start_time"] is not None:
                    try:
                        event["start_time"] = datetime.fromisoformat(kwargs["start_time"].replace('Z', '+00:00')).isoformat()
                        updated = True
                    except ValueError:
                        return {
                            "success": False,
                            "reason": "Invalid start_time format",
                            "logs": ["Please use ISO format for start_time"],
                            "data": None
                        }

                if "end_time" in kwargs and kwargs["end_time"] is not None:
                    try:
                        event["end_time"] = datetime.fromisoformat(kwargs["end_time"].replace("Z", "+00:00")).isoformat()
                        updated = True
                    except ValueError:
                        return {
                            "success": False,
                            "reason": "Invalid end_time format",
                            "logs": ["Please use ISO format for end_time"],
                            "data": None
                        }

                if updated:
                    event["updated_at"] = datetime.now().isoformat()
                    return {
                        "success": True,
                        "reason": f"Event updated: {event.get('title')}",
                        "logs": [f"Updated event ID: {event_id}"],
                        "data": event
                    }
                else:
                    return {
                        "success": True,
                        "reason": f"No changes made to event: {event.get('title')}",
                        "logs": [f"No modifications provided for event ID: {event_id}"],
                        "data": event
                    }

        return {
            "success": False,
            "reason": f"Event not found: {event_id}",
            "logs": [f"No event found with ID: {event_id}"],
            "data": None
        }

    def _delete_event(self, events: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        """Delete an event."""
        event_id = kwargs.get("event_id")
        if not event_id:
            return {
                "success": False,
                "reason": "event_id parameter required",
                "logs": ["Please provide event_id parameter"],
                "data": None
            }

        for i, event in enumerate(events):
            if event.get("id") == event_id:
                deleted_event = events.pop(i)
                return {
                    "success": True,
                    "reason": f"Event deleted: {deleted_event.get('title')}",
                    "logs": [f"Deleted event ID: {event_id}"],
                    "data": {"deleted_event_id": event_id}
                }

        return {
            "success": False,
            "reason": f"Event not found: {event_id}",
            "logs": [f"No event found with ID: {event_id}"],
            "data": None
        }

    def _get_today_events(self, events: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        """Get today's events."""
        today = datetime.now().date()
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.combine(today, datetime.max.time())

        return self._list_events(
            events,
            start_time=start_of_day.isoformat(),
            end_time=end_of_day.isoformat(),
            **kwargs
        )

    def _get_tomorrow_events(self, events: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        """Get tomorrow's events."""
        tomorrow = datetime.now().date() + timedelta(days=1)
        start_of_day = datetime.combine(tomorrow, datetime.min.time())
        end_of_day = datetime.combine(tomorrow, datetime.max.time())

        return self._list_events(
            events,
            start_time=start_of_day.isoformat(),
            end_time=end_of_day.isoformat(),
            **kwargs
        )

    def _get_upcoming_events(self, events: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        """Get upcoming events (from now onwards)."""
        now = datetime.now()
        return self._list_events(
            events,
            start_time=now.isoformat(),
            **kwargs
        )
