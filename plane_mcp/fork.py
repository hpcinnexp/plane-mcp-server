"""Endpoints of the hpcinnexp/plane fork that `plane-sdk` does not know.

The fork's `/api/v1/` adds companies and the per-user schedule, and its initiatives
are not the paid edition's: one initiative per project, `status` and `target_date`
rather than `state` and `end_date`, a plain list rather than a paginated envelope,
and no workspace feature flag. The SDK's `initiatives` namespace would 404 on the
feature probe and fail to parse the responses, so these resources call the fork's
endpoints directly and hand back its JSON as is.

They hang off `PlaneForkClient.fork`, so tools reach them through the same client
as everything else, and `SpyClient` binds calls against these signatures exactly as
it does against the SDK's.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping
from typing import Any

from plane import PlaneClient
from plane.api.base_resource import BaseResource
from plane.errors.errors import HttpError
from plane.models.projects import CreateProject, UpdateProject


class ForkInitiatives(BaseResource):
    """Initiative -> Project -> Module -> Cycle -> Work item."""

    def __init__(self, config: Any) -> None:
        super().__init__(config, "/workspaces/")

    def list(self, workspace_slug: str, include_archived: bool = False) -> list[dict[str, Any]]:
        params = {"archived": "true"} if include_archived else None
        return self._get(f"{workspace_slug}/initiatives", params=params)

    def retrieve(self, workspace_slug: str, initiative_id: str) -> dict[str, Any]:
        return self._get(f"{workspace_slug}/initiatives/{initiative_id}")

    def create(self, workspace_slug: str, data: Mapping[str, Any]) -> dict[str, Any]:
        return self._post(f"{workspace_slug}/initiatives", data)

    def update(self, workspace_slug: str, initiative_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        return self._patch(f"{workspace_slug}/initiatives/{initiative_id}", data)

    def delete(self, workspace_slug: str, initiative_id: str) -> None:
        self._delete(f"{workspace_slug}/initiatives/{initiative_id}")

    def hierarchy(self, workspace_slug: str, initiative_id: str) -> dict[str, Any]:
        return self._get(f"{workspace_slug}/initiatives/{initiative_id}/hierarchy")

    def list_members(self, workspace_slug: str, initiative_id: str) -> list[dict[str, Any]]:
        return self._get(f"{workspace_slug}/initiatives/{initiative_id}/members")

    def add_members(
        self, workspace_slug: str, initiative_id: str, member_ids: list[str], role: int = 15
    ) -> list[dict[str, Any]]:
        return self._post(
            f"{workspace_slug}/initiatives/{initiative_id}/members", {"member_ids": member_ids, "role": role}
        )

    def update_member(self, workspace_slug: str, initiative_id: str, member_id: str, role: int) -> list[dict[str, Any]]:
        return self._patch(f"{workspace_slug}/initiatives/{initiative_id}/members/{member_id}", {"role": role})

    def remove_member(self, workspace_slug: str, initiative_id: str, member_id: str) -> None:
        self._delete(f"{workspace_slug}/initiatives/{initiative_id}/members/{member_id}")


class ForkCompanies(BaseResource):
    """Companies of the group sharing the workspace; initiatives belong to one or several."""

    def __init__(self, config: Any) -> None:
        super().__init__(config, "/workspaces/")

    def list(self, workspace_slug: str) -> list[dict[str, Any]]:
        return self._get(f"{workspace_slug}/companies")

    def create(self, workspace_slug: str, data: Mapping[str, Any]) -> dict[str, Any]:
        return self._post(f"{workspace_slug}/companies", data)

    def update(self, workspace_slug: str, company_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        return self._patch(f"{workspace_slug}/companies/{company_id}", data)

    def delete(self, workspace_slug: str, company_id: str) -> None:
        self._delete(f"{workspace_slug}/companies/{company_id}")

    def list_members(self, workspace_slug: str, company_id: str) -> dict[str, Any]:
        return self._get(f"{workspace_slug}/companies/{company_id}/members")

    def add_members(
        self, workspace_slug: str, company_id: str, member_ids: list[str], emails: list[str]
    ) -> dict[str, Any]:
        return self._post(
            f"{workspace_slug}/companies/{company_id}/members", {"member_ids": member_ids, "emails": emails}
        )

    def remove_member(self, workspace_slug: str, company_id: str, member_id: str) -> None:
        self._delete(f"{workspace_slug}/companies/{company_id}/members/{member_id}")

    def cancel_invitation(self, workspace_slug: str, company_id: str, invitation_id: str) -> None:
        self._delete(f"{workspace_slug}/companies/{company_id}/invitations/{invitation_id}")


class ForkSchedule(BaseResource):
    """Time slots a user plans for their assigned work items, one per work item and day."""

    def __init__(self, config: Any) -> None:
        super().__init__(config, "/workspaces/")

    def list(self, workspace_slug: str, user_id: str, date_from: str, date_to: str) -> list[dict[str, Any]]:
        return self._get(
            f"{workspace_slug}/user-schedule/{user_id}", params={"date_from": date_from, "date_to": date_to}
        )

    def set(self, workspace_slug: str, user_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        return self._post(f"{workspace_slug}/user-schedule/{user_id}", data)

    def clear(
        self, workspace_slug: str, user_id: str, date: str, issue_id: str | None = None, today: str | None = None
    ) -> None:
        params = {"date": date, "issue_id": issue_id, "today": today}
        self._delete(
            f"{workspace_slug}/user-schedule/{user_id}", params={k: v for k, v in params.items() if v is not None}
        )


class Fork:
    """The fork's own resources, grouped so `client.fork.<resource>` reads as what it is."""

    def __init__(self, config: Any) -> None:
        self.initiatives = ForkInitiatives(config)
        self.companies = ForkCompanies(config)
        self.schedule = ForkSchedule(config)


class PlaneForkClient(PlaneClient):
    """`PlaneClient` plus the fork's resources under `fork`."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fork = Fork(self.config)


class ForkCreateProject(CreateProject):
    """The SDK model drops unknown fields; the fork requires an initiative and takes clients."""

    initiative: str | None = None
    client_ids: list[str] | None = None


class ForkUpdateProject(UpdateProject):
    initiative: str | None = None
    client_ids: list[str] | None = None


def answers_refusals(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Hand a 4xx back as text carrying the fork's own reason, rather than a bare status.

    The fork explains its refusals in the body -- "after_due_date", "Only the
    initiative's admins can edit it", "Move this initiative's projects..." -- and
    that body is what tells the caller what to do next.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except HttpError as exc:
            status = getattr(exc, "status_code", None)
            if status is None or not 400 <= status < 500:
                raise
            return f"Error: HTTP {status}: {getattr(exc, 'response', None) or exc}"

    return wrapper
