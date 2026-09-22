"""Task service module containing all business logic for task CRUD operations in Supabase."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from database import get_supabase_client
from utils.security import verify_task_ownership

logger = logging.getLogger(__name__)


def create_task(
    telegram_user_id: int,
    title: str,
    category: str,
    priority: str,
    due_at: Optional[datetime] = None,
    repeat_rule: str = "none",
    description: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Save a confirmed task to Supabase."""
    client = get_supabase_client()
    try:
        # 1. Resolve user ID UUID
        user_res = client.table("users").select("id").eq("telegram_user_id", telegram_user_id).limit(1).execute()
        if not user_res.data:
            logger.error("Cannot create task. User telegram_id=%s not registered.", telegram_user_id)
            return None
        
        user_uuid = user_res.data[0]["id"]

        new_task = {
            "user_id": user_uuid,
            "title": title,
            "description": description,
            "category": category.lower(),
            "priority": priority.lower(),
            "due_at": due_at.isoformat() if due_at else None,
            "status": "pending",
            "repeat_rule": repeat_rule.lower()
        }

        res = client.table("tasks").insert(new_task).execute()
        if res.data:
            logger.info("Task created successfully in database: %s", title)
            return res.data[0]
        return None

    except Exception as exc:
        logger.error("Error creating task: %s", exc)
        return None


def get_task_by_id(task_id: str, telegram_user_id: int) -> Optional[Dict[str, Any]]:
    """Fetch task and verify user ownership in a single operation."""
    client = get_supabase_client()
    return verify_task_ownership(client, task_id, telegram_user_id)


def get_pending_tasks(
    telegram_user_id: int,
    category: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Retrieve all pending tasks of an authorized user, optionally filtered by category.

    Sorted chronologically by priority (high -> medium -> low) and due date.
    """
    client = get_supabase_client()
    try:
        # Resolve user_id
        user_res = client.table("users").select("id").eq("telegram_user_id", telegram_user_id).limit(1).execute()
        if not user_res.data:
            return []
        user_uuid = user_res.data[0]["id"]

        query = client.table("tasks").select("*").eq("user_id", user_uuid).eq("status", "pending")
        
        if category and category.lower() != "all":
            query = query.eq("category", category.lower())

        res = query.execute()
        
        # Sort key helper: priority high -> medium -> low, then due date
        priority_weights = {"high": 0, "medium": 1, "low": 2}
        
        sorted_tasks = sorted(
            res.data or [],
            key=lambda x: (
                priority_weights.get(x.get("priority", "medium").lower(), 1),
                x.get("due_at") or "9999-12-31T23:59:59"
            )
        )
        return sorted_tasks

    except Exception as exc:
        logger.error("Error fetching pending tasks for %s: %s", telegram_user_id, exc)
        return []


def get_completed_tasks(telegram_user_id: int) -> List[Dict[str, Any]]:
    """Retrieve completed tasks of an authorized user, ordered by completed_at descending."""
    client = get_supabase_client()
    try:
        user_res = client.table("users").select("id").eq("telegram_user_id", telegram_user_id).limit(1).execute()
        if not user_res.data:
            return []
        user_uuid = user_res.data[0]["id"]

        res = (
            client.table("tasks")
            .select("*")
            .eq("user_id", user_uuid)
            .eq("status", "completed")
            .order("completed_at", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        logger.error("Error fetching completed tasks: %s", exc)
        return []


def get_overdue_tasks(telegram_user_id: int) -> List[Dict[str, Any]]:
    """Retrieve overdue tasks of an authorized user.

    A task is overdue if status is pending AND due_at is older than current UTC timestamp.
    """
    client = get_supabase_client()
    try:
        user_res = client.table("users").select("id").eq("telegram_user_id", telegram_user_id).limit(1).execute()
        if not user_res.data:
            return []
        user_uuid = user_res.data[0]["id"]

        now_utc = datetime.utcnow().isoformat()

        res = (
            client.table("tasks")
            .select("*")
            .eq("user_id", user_uuid)
            .eq("status", "pending")
            .lt("due_at", now_utc)
            .order("due_at", desc=False)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        logger.error("Error fetching overdue tasks: %s", exc)
        return []


def count_dashboard_stats(telegram_user_id: int) -> Dict[str, int]:
    """Retrieve counts for pending, completed, and overdue tasks to populate the main dashboard."""
    client = get_supabase_client()
    stats = {"pending": 0, "overdue": 0, "completed": 0}
    try:
        user_res = client.table("users").select("id").eq("telegram_user_id", telegram_user_id).limit(1).execute()
        if not user_res.data:
            return stats
        user_uuid = user_res.data[0]["id"]

        # Fetch all tasks for user to compute aggregates in a single network pass
        res = client.table("tasks").select("status, due_at").eq("user_id", user_uuid).execute()
        
        now_utc = datetime.utcnow()

        for t in (res.data or []):
            status = t.get("status")
            due_at_str = t.get("due_at")

            if status == "completed":
                stats["completed"] += 1
            elif status == "pending":
                stats["pending"] += 1
                if due_at_str:
                    try:
                        clean_str = due_at_str.replace("Z", "+00:00")
                        due_dt = datetime.fromisoformat(clean_str).replace(tzinfo=None)
                        if due_dt < now_utc:
                            stats["overdue"] += 1
                    except ValueError:
                        pass

        return stats
    except Exception as exc:
        logger.error("Error computing dashboard stats: %s", exc)
        return stats


def complete_task_by_id(task_id: str, telegram_user_id: int) -> Optional[Dict[str, Any]]:
    """Mark a task as completed in Supabase. Sets completed_at timestamp to UTC now."""
    client = get_supabase_client()
    try:
        # Security: verify ownership first
        task = verify_task_ownership(client, task_id, telegram_user_id)
        if not task:
            return None

        now_utc = datetime.utcnow().isoformat()

        res = (
            client.table("tasks")
            .update({"status": "completed", "completed_at": now_utc})
            .eq("id", task_id)
            .execute()
        )
        
        # Deactivate associated pending reminders for this completed task
        client.table("reminders").update({"status": "cancelled"}).eq("task_id", task_id).eq("status", "pending").execute()

        if res.data:
            logger.info("Marked task %s as completed.", task_id)
            return res.data[0]
        return None
    except Exception as exc:
        logger.error("Error completing task %s: %s", task_id, exc)
        return None


def delete_task_by_id(task_id: str, telegram_user_id: int) -> bool:
    """Permanently delete task from Supabase. Relies on cascade triggers to purge reminders."""
    client = get_supabase_client()
    try:
        # Security: verify ownership first
        task = verify_task_ownership(client, task_id, telegram_user_id)
        if not task:
            return False

        res = client.table("tasks").delete().eq("id", task_id).execute()
        if res.data:
            logger.info("Deleted task %s.", task_id)
            return True
        return False
    except Exception as exc:
        logger.error("Error deleting task %s: %s", task_id, exc)
        return False


def update_task(
    task_id: str,
    telegram_user_id: int,
    updates: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Update a task's fields in Supabase after verifying ownership."""
    client = get_supabase_client()
    try:
        # Security: verify ownership first
        task = verify_task_ownership(client, task_id, telegram_user_id)
        if not task:
            return None

        res = (
            client.table("tasks")
            .update(updates)
            .eq("id", task_id)
            .execute()
        )
        if res.data:
            logger.info("Updated task %s with: %s", task_id, updates)
            return res.data[0]
        return None
    except Exception as exc:
        logger.error("Error updating task %s: %s", task_id, exc)
        return None
