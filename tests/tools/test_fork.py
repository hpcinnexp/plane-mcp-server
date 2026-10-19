"""The hpcinnexp/plane fork's resources: initiatives, companies, the schedule, project initiatives.

`test_dispatch.py` already runs every action against `SpyClient`; these pin what is
specific to the fork -- the payloads its endpoints expect, and that its refusals
reach the caller with their reason.
"""

from __future__ import annotations

import pytest
from plane.errors.errors import HttpError

from plane_mcp.fork import ForkCreateProject, PlaneForkClient


def _fork_calls(spy):
    return [call for call in spy.recorder.calls if call.method.startswith("fork.")]


# -- initiatives ---------------------------------------------------------------


def test_initiatives_skip_the_paid_edition_feature_probe(registered, spy):
    """The fork has no workspace feature endpoint; probing it is what 404'd."""
    registered["initiative"].fn(action="list")

    assert spy.recorder.methods == ["fork.initiatives.list"]


def test_initiative_create_sends_only_what_was_set(registered, spy):
    registered["initiative"].fn(
        action="create", name="Growth", status="in-progress", target_date="2026-12-31", company_ids="c-1,c-2"
    )

    call = spy.recorder.only()
    assert call.method == "fork.initiatives.create"
    assert call.kwargs["data"] == {
        "name": "Growth",
        "status": "in-progress",
        "target_date": "2026-12-31",
        "company_ids": ["c-1", "c-2"],
    }


def test_an_empty_id_list_clears_it(registered, spy):
    registered["initiative"].fn(action="update", initiative_id="i-1", client_ids="[]")

    assert spy.recorder.only().kwargs["data"] == {"client_ids": []}


def test_initiative_status_is_the_forks_vocabulary(registered, spy):
    result = registered["initiative"].fn(action="create", name="Growth", status="ACTIVE")

    assert result.startswith("Error:") and "in-progress" in result
    assert not spy.recorder.calls


def test_list_projects_drops_the_nested_levels(registered, spy):
    spy.returns["fork.initiatives.hierarchy"] = {
        "id": "i-1",
        "projects": [{"id": "p-1", "name": "Web", "is_member": True, "modules": [], "unassigned_cycles": []}],
    }

    result = registered["initiative"].fn(action="list_projects", initiative_id="i-1")

    assert result == [{"id": "p-1", "name": "Web", "is_member": True}]


@pytest.mark.parametrize(("role", "sent"), [("", 15), ("member", 15), ("admin", 20)])
def test_member_roles_map_to_the_forks_numbers(role, sent, registered, spy):
    registered["initiative"].fn(action="add_members", initiative_id="i-1", member_ids="u-1", role=role)

    assert spy.recorder.only().kwargs["role"] == sent


def test_a_refusal_carries_the_forks_reason(registered, spy):
    reason = {"error": "Only the initiative's admins can edit it"}
    spy.returns["fork.initiatives.update"] = HttpError("HTTP 403: Forbidden", 403, reason)

    result = registered["initiative"].fn(action="update", initiative_id="i-1", name="Taken over")

    assert result.startswith("Error: HTTP 403") and "initiative's admins" in result


def test_a_server_error_is_not_dressed_up_as_a_refusal(registered, spy):
    spy.returns["fork.initiatives.list"] = HttpError("HTTP 500", 500, "boom")

    with pytest.raises(HttpError):
        registered["initiative"].fn(action="list")


# -- companies -----------------------------------------------------------------


def test_company_members_take_ids_and_emails(registered, spy):
    registered["company"].fn(action="add_members", company_id="c-1", emails="ana@example.com")

    call = spy.recorder.only()
    assert call.kwargs["member_ids"] == [] and call.kwargs["emails"] == ["ana@example.com"]


def test_company_members_need_someone_to_add(registered, spy):
    result = registered["company"].fn(action="add_members", company_id="c-1")

    assert result == "Error: action 'add_members' requires: member_ids or emails."
    assert not spy.recorder.calls


# -- schedule ------------------------------------------------------------------


class _Me:
    id = "me-1"


def test_schedule_defaults_to_the_caller(registered, spy):
    spy.returns["users.get_me"] = _Me()

    registered["schedule"].fn(action="list", date_from="2026-10-19", date_to="2026-10-25")

    assert _fork_calls(spy)[-1].kwargs["user_id"] == "me-1"


def test_set_sends_the_forks_slot_shape(registered, spy):
    registered["schedule"].fn(
        action="set", user_id="u-1", workitem_id="w-1", date="2026-10-20", start_minute=0, end_minute=90
    )

    call = spy.recorder.only()
    assert call.method == "fork.schedule.set"
    assert call.kwargs["data"] == {"issue_id": "w-1", "date": "2026-10-20", "start_minute": 0, "end_minute": 90}


def test_midnight_is_a_start_not_a_missing_value(registered, spy):
    result = registered["schedule"].fn(
        action="set", user_id="u-1", workitem_id="w-1", date="2026-10-20", start_minute=0, end_minute=60
    )

    assert not (isinstance(result, str) and result.startswith("Error:")), result


@pytest.mark.parametrize(("start", "end"), [(600, 540), (600, 600), (0, 1441)])
def test_a_slot_must_end_after_it_starts(start, end, registered, spy):
    result = registered["schedule"].fn(
        action="set", user_id="u-1", workitem_id="w-1", date="2026-10-20", start_minute=start, end_minute=end
    )

    assert result.startswith("Error:")
    assert not spy.recorder.calls


def test_clear_without_a_workitem_clears_the_day(registered, spy):
    registered["schedule"].fn(action="clear", user_id="u-1", date="2026-10-20")

    call = spy.recorder.only()
    assert call.kwargs["issue_id"] is None and call.kwargs["date"] == "2026-10-20"


def test_after_due_date_reaches_the_caller(registered, spy):
    reason = {"error": "The work item is due on 2026-10-10", "code": "after_due_date"}
    spy.returns["fork.schedule.set"] = HttpError("HTTP 400: Bad Request", 400, reason)

    result = registered["schedule"].fn(
        action="set", user_id="u-1", workitem_id="w-1", date="2026-10-20", start_minute=540, end_minute=600
    )

    assert "after_due_date" in result


# -- projects ------------------------------------------------------------------


def test_project_create_requires_an_initiative(registered, spy):
    result = registered["project"].fn(action="create", name="Web", identifier="WEB")

    assert result == "Error: action 'create' requires: initiative_id."
    assert not spy.recorder.calls


def test_project_create_carries_initiative_and_clients(registered, spy):
    registered["project"].fn(action="create", name="Web", identifier="WEB", initiative_id="i-1", client_ids="u-1")

    data = spy.recorder.only().kwargs["data"]
    sent = data.model_dump(exclude_none=True)
    assert sent["initiative"] == "i-1" and sent["client_ids"] == ["u-1"]


def test_the_sdk_model_alone_would_drop_the_initiative():
    """Why ForkCreateProject exists: the SDK model ignores fields it does not declare."""
    from plane.models.projects import CreateProject

    assert "initiative" not in CreateProject(name="Web", identifier="WEB", initiative="i-1").model_dump()
    assert ForkCreateProject(name="Web", identifier="WEB", initiative="i-1").model_dump()["initiative"] == "i-1"


# -- wiring --------------------------------------------------------------------


def test_fork_resources_build_the_forks_urls():
    client = PlaneForkClient(api_key="k", base_url="https://plane.example.com")

    assert client.fork.initiatives._build_url("acme/initiatives") == (
        "https://plane.example.com/api/v1/workspaces/acme/initiatives/"
    )
    assert client.fork.schedule._build_url("acme/user-schedule/u-1").endswith(
        "/api/v1/workspaces/acme/user-schedule/u-1/"
    )
