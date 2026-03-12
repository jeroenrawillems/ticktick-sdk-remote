# TickTick Remote MCP Server

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A remote [MCP](https://modelcontextprotocol.io/) (Model Context Protocol) server for [TickTick](https://ticktick.com), designed to run on [Railway](https://railway.app) so you can use it from **Claude.ai**, **Claude Mobile** (iOS/Android), and any MCP-compatible client — no local setup needed.

Forked from [dev-mirzabicer/ticktick-sdk](https://github.com/dev-mirzabicer/ticktick-sdk). Includes full support for [Dida365 (滴答清单)](https://dida365.com).

## Table of Contents

- [Quick Start (Deploy to Railway)](#quick-start-deploy-to-railway)
- [Connect to Claude](#connect-to-claude)
- [Features](#features)
- [Available MCP Tools (43 Total)](#available-mcp-tools-43-total)
- [Example Conversations](#example-conversations)
- [Getting Your Credentials](#getting-your-credentials)
- [Environment Variables](#environment-variables)
- [Health Check & Monitoring](#health-check--monitoring)
- [Architecture](#architecture)
- [TickTick API Quirks](#important-ticktick-api-quirks)
- [Python Library Reference](#python-library-reference)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Quick Start (Deploy to Railway)

### 1. Get Your TickTick Credentials

You need 5 things from TickTick (see [Getting Your Credentials](#getting-your-credentials) for details):

| Credential | Where to get it |
|-----------|----------------|
| `TICKTICK_CLIENT_ID` | [TickTick Developer Portal](https://developer.ticktick.com/manage) → Create App |
| `TICKTICK_CLIENT_SECRET` | Same as above |
| `TICKTICK_ACCESS_TOKEN` | Run the OAuth2 flow (see below) |
| `TICKTICK_USERNAME` | Your TickTick email |
| `TICKTICK_PASSWORD` | Your TickTick password |

### 2. Deploy to Railway

1. **Fork this repo** on GitHub
2. **Create a Railway account** at [railway.app](https://railway.app)
3. **Create a new project** → **Deploy from GitHub repo** → select your fork
4. **Add environment variables** in Railway's dashboard (the 5 credentials above)
5. **Generate a public domain** in Settings → Networking → Public Networking → "Generate Domain"
6. **Set the healthcheck path** in Settings → Deploy → Healthcheck Path → `/health`
7. **Wait for deployment** to finish (green status)
8. **Note your URL** — something like `https://your-app-production.up.railway.app`

### 3. Connect to Claude

See [Connect to Claude](#connect-to-claude) below.

---

## Connect to Claude

### Claude.ai (Web)

1. Go to **claude.ai** → **Settings** → **Connectors**
2. Click **"Add custom connector"**
3. Enter a name (e.g., "ticktick")
4. Enter URL: `https://your-app-production.up.railway.app/mcp`
5. Click **"Add"**

### Claude Mobile (iOS/Android)

Once added via claude.ai, the connector automatically appears in the Claude mobile app. You cannot add new connectors from mobile — only use ones already configured on the web.

### Claude Desktop / Claude Code (Local Alternative)

If you want to run the server locally instead, see the [original repo](https://github.com/dev-mirzabicer/ticktick-sdk) which supports stdio transport for local MCP usage.

---

## Features

- **43 MCP Tools**: Tasks, projects, folders, kanban columns, tags, habits, focus, user analytics
- **Batch Operations**: All mutations accept lists (1-100 items) for bulk operations
- **Remote Access**: Runs as an HTTP server with streamable-http transport
- **Health Check**: `/health` endpoint for deployment platform monitoring
- **Dual Output**: Markdown for humans, JSON for machines
- **Dida365 Support**: Works with both ticktick.com and dida365.com

---

## Available MCP Tools (43 Total)

All mutation tools accept lists for batch operations (1-100 items).

### Task Tools (Batch-Capable)
| Tool | Description |
|------|-------------|
| `ticktick_create_tasks` | Create 1-50 tasks with titles, dates, tags, etc. |
| `ticktick_get_task` | Get task details by ID |
| `ticktick_list_tasks` | List tasks (active/completed/abandoned/deleted via status filter) |
| `ticktick_update_tasks` | Update 1-100 tasks (includes column assignment) |
| `ticktick_complete_tasks` | Complete 1-100 tasks |
| `ticktick_delete_tasks` | Delete 1-100 tasks (moves to trash) |
| `ticktick_move_tasks` | Move 1-50 tasks between projects |
| `ticktick_set_task_parents` | Set parent-child relationships for 1-50 tasks |
| `ticktick_unparent_tasks` | Remove parent relationships from 1-50 tasks |
| `ticktick_search_tasks` | Search tasks by text |
| `ticktick_pin_tasks` | Pin or unpin 1-100 tasks |

### Project Tools
| Tool | Description |
|------|-------------|
| `ticktick_list_projects` | List all projects |
| `ticktick_get_project` | Get project details with tasks |
| `ticktick_create_project` | Create a new project |
| `ticktick_update_project` | Update project properties |
| `ticktick_delete_project` | Delete a project |

### Folder Tools
| Tool | Description |
|------|-------------|
| `ticktick_list_folders` | List all folders |
| `ticktick_create_folder` | Create a folder |
| `ticktick_rename_folder` | Rename a folder |
| `ticktick_delete_folder` | Delete a folder |

### Kanban Column Tools
| Tool | Description |
|------|-------------|
| `ticktick_list_columns` | List columns for a kanban project |
| `ticktick_create_column` | Create a kanban column |
| `ticktick_update_column` | Update column name or order |
| `ticktick_delete_column` | Delete a kanban column |

### Tag Tools
| Tool | Description |
|------|-------------|
| `ticktick_list_tags` | List all tags |
| `ticktick_create_tag` | Create a tag with color |
| `ticktick_update_tag` | Update tag properties (includes rename via label) |
| `ticktick_delete_tag` | Delete a tag |
| `ticktick_merge_tags` | Merge two tags |

### Habit Tools (Batch-Capable)
| Tool | Description |
|------|-------------|
| `ticktick_habits` | List all habits |
| `ticktick_habit` | Get habit details |
| `ticktick_habit_sections` | List sections (morning/afternoon/night) |
| `ticktick_create_habit` | Create a new habit |
| `ticktick_update_habit` | Update habit properties (includes archive/unarchive) |
| `ticktick_delete_habit` | Delete a habit |
| `ticktick_checkin_habits` | Check in 1-50 habits (supports backdating) |
| `ticktick_habit_checkins` | Get check-in history |

### User & Analytics Tools
| Tool | Description |
|------|-------------|
| `ticktick_get_profile` | Get user profile |
| `ticktick_get_status` | Get account status |
| `ticktick_get_statistics` | Get productivity stats |
| `ticktick_get_preferences` | Get user preferences |
| `ticktick_focus_heatmap` | Get focus heatmap data |
| `ticktick_focus_by_tag` | Get focus time by tag |

---

## Example Conversations

Once connected, you can ask Claude things like:

- "What tasks do I have due today?"
- "Create a task to call John tomorrow at 2pm"
- "Show me my high priority tasks"
- "Mark the grocery shopping task as complete"
- "What's my current streak for the Exercise habit?"
- "Check in my meditation habit for today"
- "Create a new habit to drink 8 glasses of water daily"

---

## Getting Your Credentials

### Step 1: Register Your App at TickTick

1. Go to the [TickTick Developer Portal](https://developer.ticktick.com/manage)
2. Click **"Create App"**
3. Fill in:
   - **App Name**: e.g., "My TickTick MCP"
   - **Redirect URI**: `http://127.0.0.1:8080/callback`
4. Save your **Client ID** and **Client Secret**

### Step 2: Get OAuth2 Access Token

You need a computer (just once) to run this:

```bash
pip install ticktick-sdk
TICKTICK_CLIENT_ID=your_client_id \
TICKTICK_CLIENT_SECRET=your_client_secret \
ticktick-sdk auth
```

This opens your browser, you log into TickTick and authorize the app, and it prints your access token. Copy it — you'll paste it into Railway.

> **No computer available?** You can use [Google Colab](https://colab.research.google.com/) (free, runs in browser) or [Replit](https://replit.com/) to run the auth command.

> **SSH/Headless?** Add `--manual` flag for a text-based flow.

---

## Environment Variables

| Variable | Required | Description |
|----------|:--------:|-------------|
| `TICKTICK_CLIENT_ID` | Yes | OAuth2 client ID from developer portal |
| `TICKTICK_CLIENT_SECRET` | Yes | OAuth2 client secret |
| `TICKTICK_ACCESS_TOKEN` | Yes | OAuth2 access token (from auth command) |
| `TICKTICK_USERNAME` | Yes | Your TickTick email |
| `TICKTICK_PASSWORD` | Yes | Your TickTick password |
| `TICKTICK_HOST` | No | API host: `ticktick.com` (default) or `dida365.com` (Chinese) |
| `TICKTICK_TIMEOUT` | No | Request timeout in seconds (default: `30`) |
| `TICKTICK_DEVICE_ID` | No | Device ID for V2 API (auto-generated) |
| `MCP_BEARER_TOKEN` | No | Bearer token for server authentication (see note) |
| `PORT` | No | Server port (default: `8000`, Railway sets this automatically) |

> **Note on MCP_BEARER_TOKEN**: Claude.ai's custom connector UI does not currently support bearer token auth. If you set this variable, requests without the correct `Authorization: Bearer <token>` header will be rejected. Leave it unset for Claude.ai compatibility.

---

## Health Check & Monitoring

The server exposes a `/health` endpoint:

```bash
curl https://your-app-production.up.railway.app/health
# {"status": "ok"}
```

Set this as the **Healthcheck Path** in Railway settings to ensure deployments are verified before going live.

### Test with MCP Inspector

```bash
npx @anthropic-ai/inspector https://your-app-production.up.railway.app/mcp
```

---

## Architecture

This server combines TickTick's two different APIs:

| API | Type | What It Handles |
|-----|------|----------------|
| **V1 (OAuth2)** | Official, documented | Project with all tasks, basic operations |
| **V2 (Session)** | Unofficial, reverse-engineered | Tags, folders, habits, focus, subtasks, and more |

```
┌─────────────────────────────────────────────────────────────┐
│              Claude.ai / Claude Mobile / MCP Client          │
└─────────────────────────┬───────────────────────────────────┘
                          │ streamable-http
┌─────────────────────────▼───────────────────────────────────┐
│              FastMCP Server (Railway)                         │
│              43 tools, /health endpoint                      │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    TickTickClient                             │
│            Unified async API layer                           │
└─────────────────────────┬───────────────────────────────────┘
                          │
           ┌──────────────┴──────────────┐
           ▼                             ▼
┌──────────────────────┐      ┌──────────────────────┐
│      V1 API          │      │      V2 API          │
│     (OAuth2)         │      │     (Session)        │
│ • Project with tasks │      │ • Tags, folders      │
│ • Limited features   │      │ • Habits, focus      │
│                      │      │ • Full subtasks      │
└──────────────────────┘      └──────────────────────┘
```

---

## Important: TickTick API Quirks

### 1. Recurrence Requires start_date
If you create a recurring task without a start_date, TickTick **silently ignores** the recurrence rule.

### 2. Subtasks Require Separate Call
Setting `parent_id` during task creation is **ignored** by the API. Use the `ticktick_set_task_parents` tool after creating the task.

### 3. Soft Delete
Deleting tasks moves them to trash rather than permanently removing them.

### 4. Date Clearing
To clear a task's `due_date`, you must also clear `start_date` (TickTick restores due_date from start_date otherwise).

### 5. Tag Order Not Preserved
The API does not preserve tag order — tags may be returned in any order.

### 6. Inbox is Special
The inbox is a special project that cannot be deleted.

---

## Python Library Reference

This repo also includes a full async Python SDK. For library usage examples (tasks, projects, tags, habits, focus, etc.), see the [original repo's documentation](https://github.com/dev-mirzabicer/ticktick-sdk#python-library-setup--usage).

---

## Troubleshooting

### "Token exchange failed"
- Verify your Client ID and Client Secret are correct
- Ensure the Redirect URI matches exactly (including trailing slashes)
- Check that you're using the correct TickTick developer portal

### "Authentication failed"
- Check your TickTick username (email) and password
- Try logging into ticktick.com to verify credentials

### "V2 initialization failed"
- Your password may contain special characters — try changing it
- Check for 2FA/MFA (not currently supported)

### "Configuration incomplete"
- Make sure all 5 required environment variables are set in Railway
- Check for typos in variable names

### Railway deployment fails
- Check the build logs in Railway dashboard
- Make sure the repo has the `Dockerfile` in the root

---

## License

MIT License — see [LICENSE](LICENSE) for details.

Based on [ticktick-sdk](https://github.com/dev-mirzabicer/ticktick-sdk) by dev-mirzabicer.
