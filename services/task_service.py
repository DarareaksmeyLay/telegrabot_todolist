"""Task service module containing all business logic for task CRUD operations in Supabase."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
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

        query = client.table("tasks").select("*").eq("user_id", user_uuid).in_("status", ["pending", "overdue"])
        
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

    A task is overdue if status is 'overdue' OR status is pending AND due_at is older than current UTC timestamp.
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
            .in_("status", ["pending", "overdue"])
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
            elif status == "overdue":
                stats["pending"] += 1
                stats["overdue"] += 1
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


import calendar
from datetime import datetime, timezone, timedelta


def compute_next_recurrence(due_at_str: Optional[str], repeat_rule: str) -> datetime:
    """Calculate the next upcoming UTC datetime for a repeating task."""
    now_utc = datetime.now(timezone.utc)
    
    if due_at_str:
        try:
            clean_str = due_at_str.replace("Z", "+00:00")
            base_dt = datetime.fromisoformat(clean_str)
            if base_dt.tzinfo is None:
                base_dt = base_dt.replace(tzinfo=timezone.utc)
        except Exception:
            base_dt = now_utc
    else:
        base_dt = now_utc

    next_dt = base_dt
    # Loop until the recurrence target is in the future
    for _ in range(100):
        if repeat_rule == "daily":
            next_dt = next_dt + timedelta(days=1)
        elif repeat_rule == "weekdays":
            next_dt = next_dt + timedelta(days=1)
            while next_dt.weekday() >= 5:  # 5=Saturday, 6=Sunday
                next_dt = next_dt + timedelta(days=1)
        elif repeat_rule == "weekly":
            next_dt = next_dt + timedelta(weeks=1)
        elif repeat_rule == "monthly":
            year = next_dt.year + (next_dt.month // 12)
            month = 1 if next_dt.month == 12 else next_dt.month + 1
            max_days = calendar.monthrange(year, month)[1]
            day = min(next_dt.day, max_days)
            next_dt = next_dt.replace(year=year, month=month, day=day)
        else:
            break

        if next_dt > now_utc:
            break

    return next_dt


def complete_task_by_id(task_id: str, telegram_user_id: int) -> Optional[Dict[str, Any]]:
    """Mark a task as completed in Supabase. Sets completed_at timestamp to UTC now.
    
    If the task has a repeat_rule (daily, weekdays, weekly, monthly), automatically creates
    the next scheduled task occurrence and carries forward any active reminders.
    """
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

        if not res.data:
            return None

        completed_data = res.data[0]

        # Check if this task repeats
        repeat_rule = (task.get("repeat_rule") or "none").lower()
        if repeat_rule in ["daily", "weekdays", "weekly", "monthly"]:
            try:
                next_due_utc = compute_next_recurrence(task.get("due_at"), repeat_rule)
                new_task = {
                    "user_id": task["user_id"],
                    "title": task["title"],
                    "description": task.get("description"),
                    "category": task.get("category", "personal"),
                    "priority": task.get("priority", "medium"),
                    "due_at": next_due_utc.isoformat(),
                    "status": "pending",
                    "repeat_rule": repeat_rule
                }
                new_task_res = client.table("tasks").insert(new_task).execute()
                if new_task_res.data:
                    next_task_obj = new_task_res.data[0]
                    completed_data["next_task"] = next_task_obj
                    logger.info("Auto-spawned recurring task %s (due %s) from %s", next_task_obj["id"], next_due_utc, task_id)
                    
                    # Re-create active reminders with matching time offsets
                    if task.get("due_at"):
                        try:
                            clean_old = task.get("due_at").replace("Z", "+00:00")
                            old_due_dt = datetime.fromisoformat(clean_old)
                            if old_due_dt.tzinfo is None:
                                old_due_dt = old_due_dt.replace(tzinfo=timezone.utc)
                            
                            # Get reminders that existed before cancellation
                            old_rems_res = client.table("reminders").select("*").eq("task_id", task_id).execute()
                            for r in (old_rems_res.data or []):
                                r_clean = r.get("remind_at", "").replace("Z", "+00:00")
                                r_dt = datetime.fromisoformat(r_clean)
                                if r_dt.tzinfo is None:
                                    r_dt = r_dt.replace(tzinfo=timezone.utc)
                                
                                offset = old_due_dt - r_dt
                                new_remind_at = next_due_utc - offset
                                if new_remind_at > datetime.now(timezone.utc):
                                    client.table("reminders").insert({
                                        "task_id": next_task_obj["id"],
                                        "user_id": task["user_id"],
                                        "remind_at": new_remind_at.isoformat(),
                                        "status": "pending"
                                    }).execute()
                                    logger.info("Cloned reminder for recurring task %s at %s", next_task_obj["id"], new_remind_at)
                        except Exception as rem_exc:
                            logger.error("Error cloning reminders for recurring task: %s", rem_exc)
            except Exception as rec_exc:
                logger.error("Error creating next recurrence for task %s: %s", task_id, rec_exc)

        logger.info("Marked task %s as completed.", task_id)
        return completed_data
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


def get_upcoming_tasks(telegram_user_id: int) -> List[Dict[str, Any]]:
    """Retrieve all pending tasks with a valid due_at scheduled in the future, sorted chronologically."""
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
            .gt("due_at", now_utc)
            .order("due_at", desc=False)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        logger.error("Error fetching upcoming tasks for %s: %s", telegram_user_id, exc)
        return []
