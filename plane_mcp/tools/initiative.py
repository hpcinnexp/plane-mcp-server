"""Workspace initiatives, as the hpcinnexp/plane fork models them.

Hierarchy: Initiative -> Project -> Module -> Cycle -> Work item. Every project
belongs to exactly one initiative, set on the project itself (`project create`
with initiative_id). Initiatives are always on; there is no feature flag to probe.
See `plane_mcp/fork.py` for why this does not go through the SDK's namespace.
"""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP

from plane_mcp.client import get_plane_client_context
from plane_mcp.fork import answers_refusals
from plane_mcp.toolkit import Action, build_annotations, build_description, coerce_list, one_of, opt, require

NAME = "initiative"
TITLE = "Initiatives"

STATUSES = ("planned", "in-progress", "paused", "completed", "cancelled")
ROLES = {"admin": 20, "member": 15}

_FIELDS = (
    "identifier",
    "description",
    "status",
    "start_date",
    "target_date",
    "lead",
    "client_ids",
    "company_ids",
)

ACTIONS = (
    Action("list", (), ("include_archived",), note="every initiative, each with the project_ids you see", read=True),
    Action("retrieve", ("initiative_id",), read=True),
    Action("create", ("name",), _FIELDS, note="you become its admin"),
    Action(
        "update",
        ("initiative_id",),
        ("name", *_FIELDS),
        note="initiative admins only; only the fields you pass are changed",
    ),
    Action("delete", ("initiative_id",), note="initiative admins only; it must have no projects", destructive=True),
    Action("list_projects", ("initiative_id",), note="the projects you see, with is_member", read=True),
    Action(
        "hierarchy",
        ("initiative_id",),
        note="projects -> modules -> cycles with work item counts and estimated hours",
        read=True,
    ),
    Action("list_members", ("initiative_id",), read=True),
    Action("add_members", ("initiative_id", "member_ids"), ("role",), note="initiative admins only"),
    Action("update_member", ("initiative_id", "member_id", "role"), note="initiative admins only"),
    Action("remove_member", ("initiative_id", "member_id"), note="initiative admins only", destructive=True),
)

FOOTER = (
    f"status: {', '.join(STATUSES)}. role: admin or member (default). Dates are YYYY-MM-DD. "
    "lead and member ids come from `member list_workspace`, company_ids from `company list`; id lists "
    "replace the whole list. identifier defaults from the name. A project joins an initiative through "
    "`project update` initiative_id."
)

LEGACY = {
    "list_initiatives": "list",
    "retrieve_initiative": "retrieve",
    "create_initiative": "create",
    "update_initiative": "update",
    "delete_initiative": "delete",
    "list_initiative_projects": "list_projects",
}

LEGACY_UNMAPPED = {
    "manage_initiative_projects": "a project's initiative is set on the project: use `project update` with "
    "initiative_id",
}


def _payload(**fields: Any) -> dict[str, Any]:
    """The fields the caller set. An id list is sent even when empty, since [] clears it."""
    payload = {key: opt(value) for key, value in fields.items() if key not in ("client_ids", "company_ids")}
    payload = {key: value for key, value in payload.items() if value is not None}
    for key in ("client_ids", "company_ids"):
        ids = coerce_list(fields[key])
        if ids is not None:
            payload[key] = ids
    return payload


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name=NAME,
        description=build_description("Workspace initiatives; each groups projects.", ACTIONS, FOOTER),
        annotations=build_annotations(TITLE, ACTIONS),
    )
    @answers_refusals
    def initiative(
        action: Literal[
            "list",
            "retrieve",
            "create",
            "update",
            "delete",
            "list_projects",
            "hierarchy",
            "list_members",
            "add_members",
            "update_member",
            "remove_member",
        ],
        initiative_id: str = "",
        name: str = "",
        identifier: str = "",
        description: str = "",
        status: str = "",
        start_date: str = "",
        target_date: str = "",
        lead: str = "",
        client_ids: str = "",
        company_ids: str = "",
        include_archived: bool = False,
        member_id: str = "",
        member_ids: str = "",
        role: str = "",
    ) -> dict[str, Any] | list[dict[str, Any]] | str | None:
        client, workspace_slug = get_plane_client_context()

        if error := one_of("status", status, STATUSES) or one_of("role", role, tuple(ROLES)):
            return error
        if absent := require(
            ACTIONS,
            action,
            initiative_id=initiative_id,
            name=name,
            member_id=member_id,
            member_ids=member_ids,
            role=role,
        ):
            return absent

        initiatives = client.fork.initiatives
        fields = dict(
            identifier=identifier,
            description=description,
            status=status,
            start_date=start_date,
            target_date=target_date,
            lead=lead,
            client_ids=client_ids,
            company_ids=company_ids,
        )

        if action == "list":
            return initiatives.list(workspace_slug=workspace_slug, include_archived=include_archived)

        if action == "create":
            return initiatives.create(workspace_slug=workspace_slug, data=_payload(name=name, **fields))

        if action == "retrieve":
            return initiatives.retrieve(workspace_slug=workspace_slug, initiative_id=initiative_id)

        if action == "update":
            return initiatives.update(
                workspace_slug=workspace_slug, initiative_id=initiative_id, data=_payload(name=name, **fields)
            )

        if action == "delete":
            initiatives.delete(workspace_slug=workspace_slug, initiative_id=initiative_id)
            return None

        if action in ("list_projects", "hierarchy"):
            tree = initiatives.hierarchy(workspace_slug=workspace_slug, initiative_id=initiative_id)
            if action == "hierarchy":
                return tree
            return [
                {key: value for key, value in project.items() if key not in ("modules", "unassigned_cycles")}
                for project in (tree or {}).get("projects", [])
            ]

        if action == "list_members":
            return initiatives.list_members(workspace_slug=workspace_slug, initiative_id=initiative_id)

        if action == "add_members":
            return initiatives.add_members(
                workspace_slug=workspace_slug,
                initiative_id=initiative_id,
                member_ids=coerce_list(member_ids) or [],
                role=ROLES[role or "member"],
            )

        if action == "update_member":
            return initiatives.update_member(
                workspace_slug=workspace_slug, initiative_id=initiative_id, member_id=member_id, role=ROLES[role]
            )

        initiatives.remove_member(workspace_slug=workspace_slug, initiative_id=initiative_id, member_id=member_id)
        return None
