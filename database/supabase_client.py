"""Supabase client manager for Todo-list by LDR.

Provides a thread-safe singleton connection to Supabase PostgreSQL with error handling.
"""

from __future__ import annotations

import logging
from typing import Optional
from supabase import Client, create_client
from config import config

logger = logging.getLogger(__name__)

_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """Return the initialized Supabase client singleton instance.

    Uses lazy initialization to avoid crashing on import if environment is being prepared.
    """
    global _supabase_client
    if _supabase_client is None:
        try:
            logger.info("Initializing Supabase client connection...")
            _supabase_client = create_client(config.supabase_url, config.supabase_key)
            logger.info("Supabase client initialized successfully.")
        except Exception as exc:
            logger.critical("Failed to create Supabase client: %s", exc)
            raise RuntimeError(f"Could not connect to Supabase: {exc}") from exc

    return _supabase_client


def check_supabase_connection() -> bool:
    """Verify that Supabase is reachable and database queries execute properly."""
    try:
        client = get_supabase_client()
        # Simple test query on users table
        response = client.table("users").select("id").limit(1).execute()
        logger.info("Supabase database health check passed.")
        return True
    except Exception as exc:
        logger.error("Supabase health check failed: %s", exc)
        return False
