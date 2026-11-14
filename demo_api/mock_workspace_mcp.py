"""MOCK Google Workspace MCP server for the public demo.

The real project talks to the external ``workspace-mcp`` server, which needs a Google OAuth login. A public
demo cannot use someone's real mailbox, so this module exposes the same *kind* of tools (calendar, Gmail,
Drive; Streamable HTTP at ``/mcp``) over clearly fictional sample data. The ADK agent in
``mcp_server/agent.py`` is unchanged - only ``MCP_SERVER_URL`` points here instead of at workspace-mcp.

* Nothing is ever sent or written to a real account: ``send_gmail_message`` / ``create_event`` only
  change the visitor's in-memory demo session.
* State is isolated per visitor via the ``X-Demo-Session`` header (set by the demo API).
* All names, addresses (``*.example``) and documents are invented.
"""
from __future__ import annotations

import copy
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from mcp.server.mcpserver import Context, MCPServer

HOST = "127.0.0.1"
PORT = int(os.environ.get("MOCK_MCP_PORT", "8081"))
MAX_SESSIONS = 300
SESSION_TTL_S = 3600

mcp = MCPServer("mock-google-workspace")


def _today() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def seed() -> dict[str, Any]:
    d = _today()

    def at(days: int, hour: int, minutes: int = 0) -> str:
        return (d + timedelta(days=days, hours=hour, minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "calendars": [{"id": "primary", "summary": "Demo User (primary)"}, {"id": "team", "summary": "Platform Team"}],
        "events": [
            {"id": "ev1", "calendar": "primary", "summary": "Weekly planning", "start": at(0, 9), "end": at(0, 9, 45), "attendees": ["maya@acme.example"], "location": "Room Orion"},
            {"id": "ev2", "calendar": "primary", "summary": "1:1 with Maya Chen", "start": at(1, 14), "end": at(1, 14, 30), "attendees": ["maya@acme.example"], "location": "Video call"},
            {"id": "ev3", "calendar": "team", "summary": "Q3 roadmap review", "start": at(2, 11), "end": at(2, 12), "attendees": ["team@acme.example", "ravi@acme.example"], "location": "Room Vega"},
            {"id": "ev4", "calendar": "primary", "summary": "Dentist", "start": at(3, 8), "end": at(3, 9), "attendees": [], "location": "Smile Clinic"},
            {"id": "ev5", "calendar": "primary", "summary": "Demo day rehearsal", "start": at(4, 15), "end": at(4, 16), "attendees": ["ravi@acme.example"], "location": "Room Orion"},
        ],
        "emails": [
            {"id": "m1", "from": "Maya Chen <maya@acme.example>", "subject": "Roadmap doc feedback", "date": at(-1, 16), "snippet": "I left comments on the Q3 roadmap draft...",
             "body": "Hi, I left comments on the Q3 roadmap draft. Main concern: the launch date for the billing migration looks tight. Can we talk Tuesday? - Maya"},
            {"id": "m2", "from": "Ravi Patel <ravi@acme.example>", "subject": "Demo day: slides needed by Friday", "date": at(-2, 10), "snippet": "Please send your slides by Friday noon...",
             "body": "Please send your slides for demo day by Friday noon so I can merge the deck. Keep it to 5 minutes. Thanks! - Ravi"},
            {"id": "m3", "from": "Billing Bot <noreply@billing.example>", "subject": "Invoice 4821 is ready", "date": at(-3, 8), "snippet": "Your invoice for October is ready...",
             "body": "Your invoice 4821 for October (USD 1,240.00) is ready. This is an automated message."},
            {"id": "m4", "from": "Sam Ortiz <sam@partner.example>", "subject": "Intro: partnership call", "date": at(-4, 13), "snippet": "Would love to find 30 minutes next week...",
             "body": "Hi! Would love to find 30 minutes next week to talk about a partnership. Any day except Wednesday works. - Sam"},
        ],
        "files": [
            {"id": "f1", "name": "Q3 Roadmap (draft)", "mime": "application/vnd.google-apps.document", "modified": at(-1, 15),
             "content": "Q3 Roadmap (draft)\n1. Billing migration - target Sept 15 (risk: tight)\n2. Self-serve onboarding - target Aug 30\n3. Reporting v2 - stretch goal"},
            {"id": "f2", "name": "Demo day slides", "mime": "application/vnd.google-apps.presentation", "modified": at(-2, 12),
             "content": "Slide 1: Problem. Slide 2: Solution. Slide 3: Live demo. Slide 4: Roadmap. Slide 5: Ask."},
            {"id": "f3", "name": "Team budget 2026", "mime": "application/vnd.google-apps.spreadsheet", "modified": at(-6, 9),
             "content": "Category,Amount\nCloud,48000\nTooling,12000\nTravel,9000\nTraining,6000"},
        ],
        "outbox": [],
    }


_sessions: dict[str, dict[str, Any]] = {}
_touched: dict[str, float] = {}
_lock = threading.Lock()


def _state(ctx: Context) -> dict[str, Any]:
    sid = "anonymous"
    try:
        sid = (ctx.headers or {}).get("x-demo-session", "anonymous")[:64]
    except Exception:  # noqa: BLE001 - direct (non-HTTP) calls
        pass
    with _lock:
        now = time.time()
        for k in [k for k, t in _touched.items() if now - t > SESSION_TTL_S]:
            _sessions.pop(k, None)
            _touched.pop(k, None)
        if sid not in _sessions and len(_sessions) >= MAX_SESSIONS:
            oldest = min(_touched, key=_touched.get)
            _sessions.pop(oldest, None)
            _touched.pop(oldest, None)
        _touched[sid] = now
        return _sessions.setdefault(sid, seed())


def _fmt_event(e: dict[str, Any]) -> str:
    who = ", ".join(e["attendees"]) or "no attendees"
    return f'- {e["summary"]} | {e["start"]} -> {e["end"]} | {e["location"]} | {who} | calendar={e["calendar"]} | id={e["id"]}'


@mcp.tool()
def list_calendars(ctx: Context) -> str:
    """List the calendars available to the user (demo data)."""
    return "\n".join(f'- {c["summary"]} (id={c["id"]})' for c in _state(ctx)["calendars"])


@mcp.tool()
def get_events(ctx: Context, calendar_id: str = "primary", time_min: str = "", time_max: str = "", query: str = "") -> str:
    """Get calendar events between time_min and time_max (ISO 8601, e.g. 2025-01-31T00:00:00Z). Defaults to the next 7 days."""
    st = _state(ctx)
    lo = time_min or _today().strftime("%Y-%m-%dT%H:%M:%SZ")
    hi = time_max or (_today() + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [
        e for e in st["events"]
        if (calendar_id in ("", "all", e["calendar"])) and lo <= e["end"] and e["start"] <= hi
        and (not query or query.lower() in (e["summary"] + " " + " ".join(e["attendees"])).lower())
    ]
    rows.sort(key=lambda e: e["start"])
    return "\n".join(_fmt_event(e) for e in rows) or "No events found in that range."


@mcp.tool()
def create_event(ctx: Context, summary: str, start_time: str, end_time: str, calendar_id: str = "primary",
                 attendees: list[str] | None = None, location: str = "") -> str:
    """Create a calendar event (DEMO: only affects this visitor's sample calendar). Times are ISO 8601 UTC."""
    st = _state(ctx)
    if len(st["events"]) >= 60:
        return "Demo limit reached: too many events in this session."
    if not (summary and start_time and end_time):
        return "summary, start_time and end_time are required."
    ev = {"id": f"ev{len(st['events']) + 1}", "calendar": calendar_id or "primary", "summary": summary[:120],
          "start": start_time, "end": end_time, "attendees": list(attendees or [])[:10], "location": location[:120]}
    st["events"].append(ev)
    return "Event created (demo):\n" + _fmt_event(ev)


@mcp.tool()
def search_gmail_messages(ctx: Context, query: str = "", max_results: int = 10) -> str:
    """Search the user's Gmail messages. `query` matches sender, subject and snippet."""
    st = _state(ctx)
    q = query.lower().replace("from:", "").replace("subject:", "").strip()
    rows = [m for m in st["emails"] if not q or q in (m["from"] + " " + m["subject"] + " " + m["snippet"]).lower()]
    rows.sort(key=lambda m: m["date"], reverse=True)
    return "\n".join(f'- id={m["id"]} | {m["date"]} | {m["from"]} | {m["subject"]} | {m["snippet"]}' for m in rows[: max(1, min(max_results, 25))]) or "No messages found."


@mcp.tool()
def get_gmail_message_content(ctx: Context, message_id: str) -> str:
    """Get the full content of one Gmail message by id."""
    for m in _state(ctx)["emails"]:
        if m["id"] == message_id:
            return f'From: {m["from"]}\nDate: {m["date"]}\nSubject: {m["subject"]}\n\n{m["body"]}'
    return f"No message with id {message_id}."


@mcp.tool()
def send_gmail_message(ctx: Context, to: str, subject: str, body: str) -> str:
    """Send an email (DEMO: nothing leaves this server; the message is only recorded in the visitor's demo outbox)."""
    st = _state(ctx)
    if len(st["outbox"]) >= 20:
        return "Demo limit reached: too many sent messages in this session."
    st["outbox"].append({"to": to[:200], "subject": subject[:200], "body": body[:4000]})
    return f'Email to {to[:200]} recorded in the demo outbox (not actually sent). Subject: "{subject[:200]}"'


@mcp.tool()
def search_drive_files(ctx: Context, query: str = "", page_size: int = 10) -> str:
    """Search Google Drive files by name."""
    rows = [f for f in _state(ctx)["files"] if not query or query.lower() in f["name"].lower()]
    return "\n".join(f'- {f["name"]} | {f["mime"]} | modified {f["modified"]} | id={f["id"]}' for f in rows[: max(1, min(page_size, 25))]) or "No files found."


@mcp.tool()
def get_drive_file_content(ctx: Context, file_id: str) -> str:
    """Get the text content of a Drive file by id."""
    for f in _state(ctx)["files"]:
        if f["id"] == file_id:
            return f'{f["name"]}\n\n{f["content"]}'
    return f"No file with id {file_id}."


def snapshot_outbox(session_id: str) -> list[dict[str, Any]]:
    with _lock:
        return copy.deepcopy(_sessions.get(session_id, {}).get("outbox", []))


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host=HOST, port=PORT, stateless_http=True)
