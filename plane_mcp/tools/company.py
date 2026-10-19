"""Companies of the group sharing the workspace (hpcinnexp/plane fork).

An initiative is shared by one or several companies (`initiative update` with
company_ids). Company members are workspace members; belonging to a company adds
nobody to its projects. Workspace admins manage companies and their members.
"""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP

from plane_mcp.client import get_plane_client_context
from plane_mcp.fork import answers_refusals
from plane_mcp.toolkit import Action, build_annotations, build_description, coerce_list, missing, require

NAME = "company"
TITLE = "Companies"

ACTIONS = (
    Action("list", (), note="all companies, with member_count", read=True),
    Action("create", ("name",)),
    Action("update", ("company_id", "name")),
    Action(
        "delete",
        ("company_id",),
        note="its initiatives stay; one company must remain",
        destructive=True,
    ),
    Action("list_members", ("company_id",), note="members and pending invitations", read=True),
    Action(
        "add_members",
        ("company_id",),
        ("member_ids", "emails"),
        note="at least one; outside emails get a workspace invite",
    ),
    Action("remove_member", ("company_id", "member_id"), destructive=True),
    Action("cancel_invitation", ("company_id", "invitation_id"), destructive=True),
)

FOOTER = (
    "Workspace admins only, except list. Member ids come from `member list_workspace`, invitation_id from list_members."
)

LEGACY: dict[str, str] = {}


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name=NAME,
        description=build_description("Companies of the group sharing the workspace.", ACTIONS, FOOTER),
        annotations=build_annotations(TITLE, ACTIONS),
    )
    @answers_refusals
    def company(
        action: Literal[
            "list", "create", "update", "delete", "list_members", "add_members", "remove_member", "cancel_invitation"
        ],
        company_id: str = "",
        name: str = "",
        member_id: str = "",
        member_ids: str = "",
        emails: str = "",
        invitation_id: str = "",
    ) -> dict[str, Any] | list[dict[str, Any]] | str | None:
        client, workspace_slug = get_plane_client_context()

        if absent := require(
            ACTIONS, action, company_id=company_id, name=name, member_id=member_id, invitation_id=invitation_id
        ):
            return absent

        companies = client.fork.companies

        if action == "list":
            return companies.list(workspace_slug=workspace_slug)

        if action == "create":
            return companies.create(workspace_slug=workspace_slug, data={"name": name})

        if action == "update":
            return companies.update(workspace_slug=workspace_slug, company_id=company_id, data={"name": name})

        if action == "delete":
            companies.delete(workspace_slug=workspace_slug, company_id=company_id)
            return None

        if action == "list_members":
            return companies.list_members(workspace_slug=workspace_slug, company_id=company_id)

        if action == "add_members":
            ids = coerce_list(member_ids) or []
            addresses = coerce_list(emails) or []
            if not ids and not addresses:
                return missing(action, "member_ids or emails")
            return companies.add_members(
                workspace_slug=workspace_slug, company_id=company_id, member_ids=ids, emails=addresses
            )

        if action == "remove_member":
            companies.remove_member(workspace_slug=workspace_slug, company_id=company_id, member_id=member_id)
            return None

        companies.cancel_invitation(workspace_slug=workspace_slug, company_id=company_id, invitation_id=invitation_id)
        return None
