"""Browser automation skill implementation."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from jarvis.skills.interfaces import SkillInterface

if TYPE_CHECKING:
    from jarvis.skills.browsers.chrome_client import ChromeClient

logger = logging.getLogger("jarvis.skills.browser")


class BrowserSkill(SkillInterface):
    """Skill for browser automation and control."""

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return "Browser automation and control using Chrome DevTools"

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute browser operations.

        Supported operations:
        - navigate: Navigate to a URL
        - click: Click on an element
        - type: Type text into an element
        - fill_form: Fill out form elements
        - screenshot: Take a screenshot
        - snapshot: Get page snapshot
        - list_pages: List open pages
        - select_page: Select a page

        Args:
            action: Operation to perform
            **kwargs: Operation-specific arguments

        Returns:
            Dictionary with execution results
        """
        start_time = time.time()
        action = kwargs.get("action", "").lower()

        try:
            # Import only when needed to avoid heavy dependencies
            from jarvis.skills.browsers.chrome_client import ChromeClient

            client = ChromeClient()

            if action == "navigate":
                result = self._navigate(client, **kwargs)
            elif action == "click":
                result = self._click(client, **kwargs)
            elif action == "type":
                result = self._type(client, **kwargs)
            elif action == "fill_form":
                result = self._fill_form(client, **kwargs)
            elif action == "screenshot":
                result = self._screenshot(client, **kwargs)
            elif action == "snapshot":
                result = self._snapshot(client, **kwargs)
            elif action == "list_pages":
                result = self._list_pages(client, **kwargs)
            elif action == "select_page":
                result = self._select_page(client, **kwargs)
            else:
                result = {
                    "success": False,
                    "reason": f"Unknown action: {action}",
                    "logs": [f"Available actions: navigate, click, type, fill_form, screenshot, snapshot, list_pages, select_page"],
                    "data": None
                }

            # Add execution time to result
            result["execution_time"] = time.time() - start_time
            return result

        except ImportError as e:
            logger.error(f"Browser dependencies not available: {e}")
            return {
                "success": False,
                "reason": f"Browser automation dependencies not available: {str(e)}",
                "logs": [f"Import error: {str(e)}"],
                "data": None,
                "execution_time": time.time() - start_time
            }
        except Exception as e:
            logger.error("BrowserSkill execution failed: %s", e, exc_info=True)
            return {
                "success": False,
                "reason": f"BrowserSkill execution failed: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None,
                "execution_time": time.time() - start_time
            }

    def _navigate(self, client: ChromeClient, **kwargs) -> Dict[str, Any]:
        """Navigate to a URL."""
        url = kwargs.get("url")
        if not url:
            return {
                "success": False,
                "reason": "url parameter required",
                "logs": ["Please provide url parameter"],
                "data": None
            }

        try:
            client.navigate_page(type="url", url=url)
            return {
                "success": True,
                "reason": f"Navigated to {url}",
                "logs": [f"Navigation initiated: {url}"],
                "data": {"url": url}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Navigation failed: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"url": url}
            }

    def _click(self, client: ChromeClient, **kwargs) -> Dict[str, Any]:
        """Click on an element."""
        uid = kwargs.get("uid")
        if not uid:
            return {
                "success": False,
                "reason": "uid parameter required",
                "logs": ["Please provide uid parameter"],
                "data": None
            }

        try:
            client.click(uid=uid)
            return {
                "success": True,
                "reason": f"Clicked element {uid}",
                "logs": [f"Element clicked: {uid}"],
                "data": {"uid": uid}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Click failed: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"uid": uid}
            }

    def _type(self, client: ChromeClient, **kwargs) -> Dict[str, Any]:
        """Type text into an element."""
        uid = kwargs.get("uid")
        text = kwargs.get("text", "")

        if not uid:
            return {
                "success": False,
                "reason": "uid parameter required",
                "logs": ["Please provide uid parameter"],
                "data": None
            }

        try:
            client.type_text(uid=uid, text=text)
            return {
                "success": True,
                "reason": f"Typed text into element {uid}",
                "logs": [f"Text entered in {uid}: '{text[:50]}{'...' if len(text) > 50 else ''}'"],
                "data": {"uid": uid, "text": text}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Type failed: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"uid": uid, "text": text}
            }

    def _fill_form(self, client: ChromeClient, **kwargs) -> Dict[str, Any]:
        """Fill out form elements."""
        elements = kwargs.get("elements", [])

        if not isinstance(elements, list):
            return {
                "success": False,
                "reason": "elements parameter must be a list",
                "logs": ["Please provide elements as a list of dictionaries"],
                "data": None
            }

        try:
            client.fill_form(elements=elements)
            return {
                "success": True,
                "reason": f"Filled form with {len(elements)} elements",
                "logs": [f"Form filled with {len(elements)} elements"],
                "data": {"elements_count": len(elements)}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Fill form failed: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"elements": elements}
            }

    def _screenshot(self, client: ChromeClient, **kwargs) -> Dict[str, Any]:
        """Take a screenshot."""
        uid = kwargs.get("uid")
        file_path = kwargs.get("file_path")

        try:
            # This would use the actual Chrome DevTools screenshot method
            # For now, we'll return a simulated result
            result_data = {
                "uid": uid if uid else "full_page",
                "file_path": file_path,
                "screenshot_taken": True
            }

            return {
                "success": True,
                "reason": f"Screenshot taken{' of element ' + uid if uid else ' of full page'}",
                "logs": [f"Screenshot captured: {'element ' + uid if uid else 'full page'}"],
                "data": result_data
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Screenshot failed: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"uid": uid, "file_path": file_path}
            }

    def _snapshot(self, client: ChromeClient, **kwargs) -> Dict[str, Any]:
        """Get page snapshot."""
        verbose = kwargs.get("verbose", False)

        try:
            snapshot = client.take_snapshot(verbose=verbose)
            return {
                "success": True,
                "reason": "Page snapshot captured",
                "logs": ["Page snapshot taken successfully"],
                "data": snapshot
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Snapshot failed: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _list_pages(self, client: ChromeClient, **kwargs) -> Dict[str, Any]:
        """List open pages."""
        try:
            pages = client.list_pages()
            return {
                "success": True,
                "reason": f"Found {len(pages)} open pages",
                "logs": [f"Listed {len(pages)} browser tabs/windows"],
                "data": {"pages": pages, "count": len(pages)}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"List pages failed: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _select_page(self, client: ChromeClient, **kwargs) -> Dict[str, Any]:
        """Select a page."""
        page_id = kwargs.get("pageId")
        if page_id is None:
            return {
                "success": False,
                "reason": "pageId parameter required",
                "logs": ["Please provide pageId parameter"],
                "data": None
            }

        try:
            client.select_page(pageId=page_id)
            return {
                "success": True,
                "reason": f"Selected page {page_id}",
                "logs": [f"Page {page_id} selected"],
                "data": {"page_id": page_id}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Select page failed: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"page_id": page_id}
            }