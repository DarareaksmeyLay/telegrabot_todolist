-- ====================================================================
-- Todo-list by LDR - Supabase PostgreSQL Database Schema
-- Version: 1.0.0
-- Compatible with: Supabase / PostgreSQL 15+
-- ====================================================================

-- 1. Enable pgcrypto extension for UUID generation if not already active
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. Clean trigger function for updating updated_at timestamp automatically
CREATE OR REPLACE FUNCTION set_updated_at_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = timezone('utc'::text, now());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ====================================================================
-- 3. USERS TABLE
-- Stores authorized Telegram users, preferences, and individual timezones
-- ====================================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id BIGINT UNIQUE NOT NULL,
    telegram_username TEXT,
    first_name TEXT,
    timezone TEXT NOT NULL DEFAULT 'Asia/Phnom_Penh',
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Index for instant lookup during message authentication
CREATE INDEX IF NOT EXISTS idx_users_telegram_user_id 
    ON users(telegram_user_id);

-- Trigger to keep users.updated_at current
DROP TRIGGER IF EXISTS trigger_users_updated_at ON users;
CREATE TRIGGER trigger_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at_timestamp();


-- ====================================================================
-- 4. TASKS TABLE
-- Stores tasks with categories, priorities, due dates, and recurrence
-- ====================================================================
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL CHECK (category IN ('personal', 'work', 'school')),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high')),
    due_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'overdue')),
    repeat_rule TEXT NOT NULL DEFAULT 'none' CHECK (repeat_rule IN ('none', 'daily', 'weekdays', 'weekly', 'monthly')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    completed_at TIMESTAMPTZ
);

-- Composite indexes for high-speed filtered queries
CREATE INDEX IF NOT EXISTS idx_tasks_user_status 
    ON tasks(user_id, status);

CREATE INDEX IF NOT EXISTS idx_tasks_user_category_status 
    ON tasks(user_id, category, status);

CREATE INDEX IF NOT EXISTS idx_tasks_due_pending 
    ON tasks(user_id, due_at) 
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_tasks_completed_at 
    ON tasks(user_id, completed_at DESC) 
    WHERE status = 'completed';

-- Trigger to keep tasks.updated_at current
DROP TRIGGER IF EXISTS trigger_tasks_updated_at ON tasks;
CREATE TRIGGER trigger_tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at_timestamp();


-- ====================================================================
-- 5. REMINDERS TABLE
-- Durable storage for scheduled notifications, snooze states, and history
-- Survives bot restarts; acts as single source of truth for APScheduler / PTB
-- ====================================================================
CREATE TABLE IF NOT EXISTS reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    remind_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'cancelled')),
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Indexes for the startup reminder recovery and poll queries
CREATE INDEX IF NOT EXISTS idx_reminders_pending_time 
    ON reminders(remind_at) 
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_reminders_task_id 
    ON reminders(task_id);

CREATE INDEX IF NOT EXISTS idx_reminders_user_id 
    ON reminders(user_id);


-- ====================================================================
-- 6. ROW LEVEL SECURITY (RLS) POLICIES (Optional / Defense-in-depth)
-- ====================================================================
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE reminders ENABLE ROW LEVEL SECURITY;

-- Note: The backend bot connects via the Supabase Service Role Key (or authenticated user key).
-- When using the service role key, RLS is automatically bypassed by PostgreSQL.
-- The following policies grant full operational access to service role contexts while locking
-- out anonymous unauthorized public access.
CREATE POLICY service_role_all_users ON users 
    FOR ALL USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

CREATE POLICY service_role_all_tasks ON tasks 
    FOR ALL USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

CREATE POLICY service_role_all_reminders ON reminders 
    FOR ALL USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');
