"""Each person's daily schedule of work items (hpcinnexp/plane fork).

A slot plans one work item on one day, from start_minute to end_minute. Anyone in
the workspace reads a schedule (on the projects they are in); only its owner
changes it, and only for work items assigned to them.
"""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP

from plane_mcp.client import get_plane_client_context
from plane_mcp.fork import answers_refusals
from plane_mcp.toolkit import Action, build_annotations, build_description, require

NAME = "schedule"
TITLE = "Schedule"

MINUTES_IN_DAY = 24 * 60

ACTIONS = (
    Action("list", ("date_from", "date_to"), ("user_id",), note="slots in the range, both days included", read=True),
    Action(
        "set",
        ("workitem_id", "date", "start_minute", "end_minute"),
        ("estimate_hours",),
        note="plans the work item that day or moves its slot; repeat for other days",
    ),
    Action(
        "clear",
        ("date",),
        ("workitem_id", "today"),
        note="the work item's slot that day, or the whole day",
        destructive=True,
    ),
)

FOOTER = (
    "user_id defaults to you; only your own schedule can change. Dates are YYYY-MM-DD; minutes count from "
    "midnight (9:30 is 570, end exclusive, max 1440). Only work items assigned to you, never after their due "
    "date (after_due_date). Scheduling moves a backlog item to unstarted; one left with no slot from today "
    "goes back to backlog. estimate_hours also sets its estimate."
)

LEGACY: dict[str, str] = {}


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name=NAME,
        description=build_description("Daily schedule of work items per person.", ACTIONS, FOOTER),
        annotations=build_annotations(TITLE, ACTIONS),
    )
    @answers_refusals
    def schedule(
        action: Literal["list", "set", "clear"],
        user_id: str = "",
        date_from: str = "",
        date_to: str = "",
        workitem_id: str = "",
        date: str = "",
        # None is unset: 0 (midnight) is a real start
        start_minute: int | None = None,
        end_minute: int | None = None,
        # None leaves the estimate alone; 0 is a real value
        estimate_hours: float | None = None,
        today: str = "",
    ) -> dict[str, Any] | list[dict[str, Any]] | str | None:
        client, workspace_slug = get_plane_client_context()

        if absent := require(
            ACTIONS,
            action,
            date_from=date_from,
            date_to=date_to,
            workitem_id=workitem_id,
            date=date,
            start_minute=start_minute is not None,
            end_minute=end_minute is not None,
        ):
            return absent
        if action == "set" and not 0 <= start_minute < end_minute <= MINUTES_IN_DAY:
            return f"Error: set needs 0 <= start_minute < end_minute <= {MINUTES_IN_DAY}."

        owner = user_id or str(client.users.get_me().id)
        slots = client.fork.schedule

        if action == "list":
            return slots.list(workspace_slug=workspace_slug, user_id=owner, date_from=date_from, date_to=date_to)

        if action == "set":
            data: dict[str, Any] = {
                "issue_id": workitem_id,
                "date": date,
                "start_minute": start_minute,
                "end_minute": end_minute,
            }
            if estimate_hours is not None:
                data["estimate_hours"] = estimate_hours
            return slots.set(workspace_slug=workspace_slug, user_id=owner, data=data)

        slots.clear(
            workspace_slug=workspace_slug,
            user_id=owner,
            date=date,
            issue_id=workitem_id or None,
            today=today or None,
        )
        return None
