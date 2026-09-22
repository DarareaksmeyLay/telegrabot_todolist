import React, { useState } from 'react';
import { 
  CheckCircle2, 
  Database, 
  Terminal, 
  ShieldCheck, 
  Clock, 
  Copy, 
  Check, 
  FolderTree, 
  Key, 
  Bot, 
  ListTodo, 
  ExternalLink,
  Calendar,
  Layers,
  Sparkles
} from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState<'architecture' | 'schema' | 'config' | 'files'>('architecture');
  const [copiedSQL, setCopiedSQL] = useState(false);
  const [copiedEnv, setCopiedEnv] = useState(false);

  const sampleSQL = `-- ====================================================================
-- Todo-list by LDR - Supabase PostgreSQL Database Schema
-- ====================================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id BIGINT UNIQUE NOT NULL,
    telegram_username TEXT,
    first_name TEXT,
    timezone TEXT NOT NULL DEFAULT 'Asia/Phnom_Penh',
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL CHECK (category IN ('personal', 'work', 'school')),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high')),
    due_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed')),
    repeat_rule TEXT NOT NULL DEFAULT 'none' CHECK (repeat_rule IN ('none', 'daily', 'weekdays', 'weekly', 'monthly')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    remind_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'cancelled')),
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);`;

  const sampleEnv = `TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
ALLOWED_TELEGRAM_USER_IDS="123456789,987654321"
SUPABASE_URL="https://your_project.supabase.co"
SUPABASE_KEY="your_supabase_service_role_key"
DEFAULT_TIMEZONE="Asia/Phnom_Penh"
BOT_NAME="Todo-list by LDR"`;

  const copyToClipboard = (text: string, type: 'sql' | 'env') => {
    navigator.clipboard.writeText(text);
    if (type === 'sql') {
      setCopiedSQL(true);
      setTimeout(() => setCopiedSQL(false), 2000);
    } else {
      setCopiedEnv(true);
      setTimeout(() => setCopiedEnv(false), 2000);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col font-sans">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur px-6 py-4 flex items-center justify-between sticky top-0 z-30">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center text-white shadow-lg shadow-cyan-500/20">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold tracking-tight text-white">Todo-list by LDR</h1>
              <span className="px-2 py-0.5 text-xs font-semibold uppercase tracking-wider bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-full">
                Phase 1 Ready
              </span>
            </div>
            <p className="text-xs text-slate-400">Personal Telegram Bot • Supabase PostgreSQL • JobQueue/APScheduler</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs px-2.5 py-1 rounded-md bg-slate-800 border border-slate-700 text-slate-300 flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-cyan-400" />
            Asia/Phnom_Penh (UTC+7)
          </span>
        </div>
      </header>

      {/* Main Container */}
      <div className="flex-1 max-w-7xl w-full mx-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Navigation & Core Overview */}
        <div className="lg:col-span-4 space-y-6">
          {/* Status Card */}
          <div className="bg-slate-800/60 border border-slate-700/80 rounded-2xl p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2">
              <Layers className="w-4 h-4 text-cyan-400" /> System Architecture
            </h2>
            <div className="space-y-3 text-xs text-slate-300">
              <div className="p-3 bg-slate-900/60 rounded-xl border border-slate-700/50 flex items-center justify-between">
                <span className="font-medium text-slate-400">Telegram Engine:</span>
                <span className="text-cyan-300 font-mono">python-telegram-bot v21+</span>
              </div>
              <div className="p-3 bg-slate-900/60 rounded-xl border border-slate-700/50 flex items-center justify-between">
                <span className="font-medium text-slate-400">Database Backend:</span>
                <span className="text-emerald-300 font-mono">Supabase PostgreSQL 15</span>
              </div>
              <div className="p-3 bg-slate-900/60 rounded-xl border border-slate-700/50 flex items-center justify-between">
                <span className="font-medium text-slate-400">Reminder Scheduler:</span>
                <span className="text-amber-300 font-mono">PTB JobQueue / APScheduler</span>
              </div>
              <div className="p-3 bg-slate-900/60 rounded-xl border border-slate-700/50 flex items-center justify-between">
                <span className="font-medium text-slate-400">Security Model:</span>
                <span className="text-purple-300 font-mono">Allowlist & Ownership Auth</span>
              </div>
            </div>
          </div>

          {/* Quick Tab Selector */}
          <div className="bg-slate-800/40 border border-slate-700/60 rounded-2xl p-2 flex flex-col gap-1">
            <button
              onClick={() => setActiveTab('architecture')}
              className={`flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-colors text-left ${
                activeTab === 'architecture'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              <Sparkles className="w-4 h-4" />
              <span>Phase 1 Architecture & Specs</span>
            </button>
            <button
              onClick={() => setActiveTab('schema')}
              className={`flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-colors text-left ${
                activeTab === 'schema'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              <Database className="w-4 h-4" />
              <span>Database Schema (schema.sql)</span>
            </button>
            <button
              onClick={() => setActiveTab('config')}
              className={`flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-colors text-left ${
                activeTab === 'config'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              <Key className="w-4 h-4" />
              <span>Configuration & Security</span>
            </button>
            <button
              onClick={() => setActiveTab('files')}
              className={`flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-colors text-left ${
                activeTab === 'files'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              <FolderTree className="w-4 h-4" />
              <span>Complete Project Structure</span>
            </button>
          </div>

          {/* Interactive Bot Preview Simulation */}
          <div className="bg-slate-800/60 border border-slate-700/80 rounded-2xl p-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
              <Bot className="w-3.5 h-3.5 text-cyan-400" /> Bot Interface Preview (/start)
            </h3>
            <div className="bg-slate-950 rounded-xl p-3 border border-slate-800 space-y-2 text-xs">
              <p className="text-slate-200">👋 Welcome, User!</p>
              <p className="text-slate-300">📝 <b>Personal To-Do Assistant</b></p>
              <p className="text-slate-400">📅 Today: 22 September 2026</p>
              <div className="pt-1 text-slate-300 space-y-0.5">
                <p>⏳ Pending: <span className="text-amber-400 font-semibold">4</span></p>
                <p>🔴 Overdue: <span className="text-rose-400 font-semibold">1</span></p>
                <p>✅ Completed: <span className="text-emerald-400 font-semibold">12</span></p>
              </div>
              <div className="pt-2 grid grid-cols-2 gap-1.5">
                <div className="bg-slate-800 text-center py-1.5 rounded-lg border border-slate-700 text-[11px] text-slate-200">➕ Create Task</div>
                <div className="bg-slate-800 text-center py-1.5 rounded-lg border border-slate-700 text-[11px] text-slate-200">📋 Show Tasks</div>
                <div className="bg-slate-800 text-center py-1.5 rounded-lg border border-slate-700 text-[11px] text-slate-200">🔔 Upcoming</div>
                <div className="bg-slate-800 text-center py-1.5 rounded-lg border border-slate-700 text-[11px] text-slate-200">✅ Completed</div>
                <div className="col-span-2 bg-slate-800 text-center py-1.5 rounded-lg border border-slate-700 text-[11px] text-slate-200">⚙️ Settings</div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Tab Content */}
        <div className="lg:col-span-8">
          {activeTab === 'architecture' && (
            <div className="bg-slate-800/40 border border-slate-700/80 rounded-2xl p-6 space-y-6">
              <div>
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-cyan-400" />
                  Todo-list by LDR — Phase 1 Architecture
                </h2>
                <p className="text-xs text-slate-400 mt-1">
                  Engineered with strict separation of concerns, durable database-backed reminders, and zero-trust Telegram user authorization.
                </p>
              </div>

              {/* Pillars */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-slate-900/60 border border-slate-700/60 rounded-xl p-4 space-y-2">
                  <div className="w-8 h-8 rounded-lg bg-cyan-500/20 text-cyan-400 flex items-center justify-center font-bold">1</div>
                  <h3 className="text-sm font-semibold text-white">Durable Reminders</h3>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    Reminders reside in Supabase PostgreSQL, not just Python RAM. On startup, pending jobs are safely restored and checked against offline missed alerts.
                  </p>
                </div>
                <div className="bg-slate-900/60 border border-slate-700/60 rounded-xl p-4 space-y-2">
                  <div className="w-8 h-8 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold">2</div>
                  <h3 className="text-sm font-semibold text-white">Zero-Trust Security</h3>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    Telegram callback data is never trusted blindly. All database operations strictly filter by internal user ID to prevent ID spoofing.
                  </p>
                </div>
                <div className="bg-slate-900/60 border border-slate-700/60 rounded-xl p-4 space-y-2">
                  <div className="w-8 h-8 rounded-lg bg-purple-500/20 text-purple-400 flex items-center justify-center font-bold">3</div>
                  <h3 className="text-sm font-semibold text-white">Clean State Machine</h3>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    ConversationHandler manages multistep task creation. Temporary state is never prematurely committed to database until explicit user confirmation.
                  </p>
                </div>
              </div>

              {/* Categories & Priorities */}
              <div className="p-4 bg-slate-900/80 rounded-xl border border-slate-800 space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">Default Category & Priority Mapping</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <div className="space-y-1.5">
                    <p className="text-slate-400 font-medium">Categories (Stored as lowercase):</p>
                    <div className="flex gap-2">
                      <span className="px-2.5 py-1 bg-slate-800 border border-slate-700 rounded-lg text-slate-200">👤 personal</span>
                      <span className="px-2.5 py-1 bg-slate-800 border border-slate-700 rounded-lg text-slate-200">💼 work</span>
                      <span className="px-2.5 py-1 bg-slate-800 border border-slate-700 rounded-lg text-slate-200">🎓 school</span>
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <p className="text-slate-400 font-medium">Priorities:</p>
                    <div className="flex gap-2">
                      <span className="px-2.5 py-1 bg-rose-500/20 text-rose-300 border border-rose-500/30 rounded-lg">🔴 high</span>
                      <span className="px-2.5 py-1 bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded-lg">🟡 medium</span>
                      <span className="px-2.5 py-1 bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 rounded-lg">🟢 low</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'schema' && (
            <div className="bg-slate-800/40 border border-slate-700/80 rounded-2xl p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-base font-bold text-white flex items-center gap-2">
                    <Database className="w-4 h-4 text-emerald-400" />
                    Supabase PostgreSQL Schema (schema.sql)
                  </h2>
                  <p className="text-xs text-slate-400">Copy and run this in your Supabase SQL Editor.</p>
                </div>
                <button
                  onClick={() => copyToClipboard(sampleSQL, 'sql')}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium transition-colors shadow-sm"
                >
                  {copiedSQL ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                  {copiedSQL ? 'Copied to Clipboard' : 'Copy SQL'}
                </button>
              </div>

              <div className="bg-slate-950 rounded-xl p-4 border border-slate-800 overflow-x-auto text-[11px] font-mono text-slate-300 max-h-[460px] overflow-y-auto leading-relaxed">
                <pre>{sampleSQL}</pre>
              </div>
            </div>
          )}

          {activeTab === 'config' && (
            <div className="bg-slate-800/40 border border-slate-700/80 rounded-2xl p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-base font-bold text-white flex items-center gap-2">
                    <Key className="w-4 h-4 text-amber-400" />
                    Environment Variables (.env.example)
                  </h2>
                  <p className="text-xs text-slate-400">Configure these securely in your local .env file.</p>
                </div>
                <button
                  onClick={() => copyToClipboard(sampleEnv, 'env')}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-medium transition-colors shadow-sm"
                >
                  {copiedEnv ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                  {copiedEnv ? 'Copied .env' : 'Copy .env'}
                </button>
              </div>

              <div className="bg-slate-950 rounded-xl p-4 border border-slate-800 text-[11px] font-mono text-slate-300 space-y-2">
                <pre className="overflow-x-auto">{sampleEnv}</pre>
              </div>

              <div className="p-4 bg-slate-900/60 rounded-xl border border-slate-700/60 text-xs space-y-2">
                <h4 className="font-semibold text-slate-200 flex items-center gap-1.5">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" /> Security Guarantee
                </h4>
                <p className="text-slate-400 leading-relaxed">
                  The bot uses <code className="text-cyan-300">ALLOWED_TELEGRAM_USER_IDS</code> to prevent unauthorized users from interacting with the bot. The custom <code className="text-cyan-300">@authorized_only</code> decorator rejects all unauthorized commands and callbacks before database queries execute.
                </p>
              </div>
            </div>
          )}

          {activeTab === 'files' && (
            <div className="bg-slate-800/40 border border-slate-700/80 rounded-2xl p-6 space-y-4">
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <FolderTree className="w-4 h-4 text-cyan-400" />
                Target Project Structure
              </h2>
              <div className="bg-slate-950 rounded-xl p-4 border border-slate-800 text-xs font-mono text-slate-300 leading-relaxed">
                <pre>{`todo_telegram_bot/
├── bot.py                     # Main application entry point & dispatcher
├── config.py                  # Validated settings & safe secret masking
├── requirements.txt           # Verified python dependencies
├── .env.example               # Environment variables template
├── .gitignore                 # Git ignore for venv, .env, and caches
│
├── database/
│   ├── __init__.py            # Database client exports
│   ├── supabase_client.py     # Supabase client singleton & health check
│   └── schema.sql             # Complete PostgreSQL DDL, triggers & RLS
│
├── handlers/
│   ├── __init__.py            # Handler router exports
│   ├── start.py               # /start command & dashboard
│   ├── menu.py                # Main menu callback handler
│   ├── create_task.py         # ConversationHandler for task wizard
│   ├── tasks.py               # Show tasks, category views & pagination
│   ├── edit_task.py           # In-place task editing
│   ├── reminders.py           # Reminder notifications & snooze callbacks
│   ├── completed.py           # Completed task history
│   └── settings.py            # User timezone settings
│
├── services/
│   ├── __init__.py
│   ├── task_service.py        # Business logic for tasks
│   ├── reminder_service.py    # Scheduler sync & restoration
│   └── user_service.py        # User profile & registration
│
├── keyboards/
│   ├── __init__.py
│   ├── main.py                # Main menu inline buttons
│   ├── categories.py          # Category filters
│   ├── tasks.py               # Task navigation & pagination
│   └── reminders.py           # Snooze & alert keyboards
│
└── utils/
    ├── __init__.py
    ├── dates.py               # Datetime & zoneinfo converters
    ├── security.py            # User whitelist & ownership checks
    ├── validators.py          # Input parser & date format checkers
    └── formatters.py          # Clean Telegram visual formatting`}</pre>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
