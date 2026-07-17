"""
Regression tests for UnifiedTickTickAPI pin / unpin.

Pinning is a full-task update under the hood (TickTick has no pin endpoint):
we stamp pinnedTime on the task and re-save it. Because the V2 /batch/task
endpoint REPLACES the task with whatever we send, pin/unpin MUST round-trip
every existing field or they get wiped.

The historic bug: pin sent only {id, projectId, pinnedTime}, so TickTick
cleared startDate, dueDate, isAllDay and timeZone (silent data loss), and the
tool's reply still echoed the old dates because it never re-read the task.

These tests drive the REAL UnifiedTickTickAPI against a mocked V2 client and
inspect the payload actually sent to batch_tasks. That is the exact layer the
old pin tests skipped by mocking the whole unified API, which is why they never
caught the bug.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ticktick_sdk.models import Task
from ticktick_sdk.unified.api import UnifiedTickTickAPI


pytestmark = [pytest.mark.pinning, pytest.mark.unit]


def _make_api(existing_task: Task) -> tuple[UnifiedTickTickAPI, AsyncMock]:
    """Build a UnifiedTickTickAPI with a mocked V2 client and get_task."""
    api = UnifiedTickTickAPI.__new__(UnifiedTickTickAPI)
    api._initialized = True
    api._router = MagicMock()
    api._router.has_v2 = True
    api._v2_client = MagicMock()
    api._v2_client.batch_tasks = AsyncMock(
        return_value={"id2etag": {existing_task.id: "etag1"}, "id2error": {}}
    )
    # Patch the unified get_task so the pre-fetch/merge step has something to read.
    api.get_task = AsyncMock(return_value=existing_task)  # type: ignore[assignment]
    return api, api._v2_client.batch_tasks


def _sent_update(batch_mock: AsyncMock) -> dict:
    """Extract the single update payload sent to v2_client.batch_tasks."""
    sent = batch_mock.call_args.kwargs["update"]
    assert len(sent) == 1
    return sent[0]


def _dated_task() -> Task:
    """A task with both dates set, matching the issue's repro (due 2026-07-20)."""
    return Task(
        id="aaaaaaaaaaaaaaaaaaaaaaaa",
        project_id="bbbbbbbbbbbbbbbbbbbbbbbb",
        title="Task with a due date",
        is_all_day=False,
        time_zone="Europe/Brussels",
        start_date=datetime(2026, 7, 20, 13, 0, tzinfo=timezone.utc),
        due_date=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc),
        tags=["work"],
    )


class TestPinPreservesDates:
    """The headline regression: pin/unpin must not wipe the task's dates."""

    async def test_pin_keeps_start_and_due_dates(self):
        task = _dated_task()
        api, batch_mock = _make_api(task)

        result = await api.pin_task(task.id, task.project_id)

        update = _sent_update(batch_mock)
        # These four used to be dropped from the payload, so TickTick cleared them.
        assert update["startDate"] == "2026-07-20T13:00:00.000+0000"
        assert update["dueDate"] == "2026-07-20T15:00:00.000+0000"
        assert update["isAllDay"] is False
        assert update["timeZone"] == "Europe/Brussels"
        assert update["tags"] == ["work"]
        # And it must actually pin.
        assert update["pinnedTime"] is not None
        assert result.is_pinned is True

    async def test_unpin_keeps_dates_and_clears_pin(self):
        task = _dated_task()
        task.pinned_time = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
        api, batch_mock = _make_api(task)

        result = await api.unpin_task(task.id, task.project_id)

        update = _sent_update(batch_mock)
        assert update["startDate"] == "2026-07-20T13:00:00.000+0000"
        assert update["dueDate"] == "2026-07-20T15:00:00.000+0000"
        assert update["isAllDay"] is False
        assert update["timeZone"] == "Europe/Brussels"
        # Unpin sends pinnedTime: null explicitly, inside a full valid task, so
        # the cleared flag actually sticks server-side.
        assert update["pinnedTime"] is None
        assert result.is_pinned is False

    async def test_pin_returned_task_matches_what_was_saved(self):
        """The tool's reply must not lie: the returned task keeps its real dates."""
        task = _dated_task()
        api, _ = _make_api(task)

        result = await api.pin_task(task.id, task.project_id)

        # The returned object still carries the real dates (they were never lost).
        assert result.start_date == datetime(2026, 7, 20, 13, 0, tzinfo=timezone.utc)
        assert result.due_date == datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)

    async def test_pin_preserves_kanban_column(self):
        task = _dated_task()
        task.column_id = "dddddddddddddddddddddddd"
        api, batch_mock = _make_api(task)

        await api.pin_task(task.id, task.project_id)

        update = _sent_update(batch_mock)
        # columnId is not serialized by to_v2_dict, so pin passes it through
        # to avoid knocking the task out of its board column.
        assert update["columnId"] == "dddddddddddddddddddddddd"

    async def test_pin_preserves_recurrence_anchors(self):
        """A pinned recurring task must keep its RRULE chain anchor."""
        task = Task(
            id="aaaaaaaaaaaaaaaaaaaaaaaa",
            project_id="bbbbbbbbbbbbbbbbbbbbbbbb",
            title="Weekly review",
            repeat_flag="RRULE:FREQ=WEEKLY;BYDAY=MO",
            repeat_from=2,
            repeat_first_date=datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc),
            repeat_task_id="cccccccccccccccccccccccc",
            ex_date=["20260202T000000Z"],
            due_date=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc),
        )
        api, batch_mock = _make_api(task)

        await api.pin_task(task.id, task.project_id)

        update = _sent_update(batch_mock)
        assert update["repeatFlag"] == "RRULE:FREQ=WEEKLY;BYDAY=MO"
        assert update["repeatFrom"] == 2
        assert "repeatFirstDate" in update
        assert update["repeatTaskId"] == "cccccccccccccccccccccccc"
        assert update["exDate"] == ["20260202T000000Z"]


class TestBatchPinSingleWrite:
    """batch_pin_tasks writes the whole set in one /batch/task call."""

    def _make_multi_api(self, by_id: dict[str, Task]) -> UnifiedTickTickAPI:
        api = UnifiedTickTickAPI.__new__(UnifiedTickTickAPI)
        api._initialized = True
        api._router = MagicMock()
        api._router.has_v2 = True
        api._v2_client = MagicMock()
        api._v2_client.batch_tasks = AsyncMock(
            return_value={
                "id2etag": {tid: "e" for tid in by_id},
                "id2error": {},
            }
        )
        api.get_task = AsyncMock(  # type: ignore[assignment]
            side_effect=lambda tid, pid: by_id[tid]
        )
        return api

    async def test_mixed_pin_and_unpin_in_one_write(self):
        t1 = Task(
            id="a" * 24,
            project_id="p" * 24,
            title="One",
            due_date=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc),
        )
        t2 = Task(
            id="c" * 24,
            project_id="p" * 24,
            title="Two",
            due_date=datetime(2026, 7, 21, 15, 0, tzinfo=timezone.utc),
        )
        api = self._make_multi_api({t1.id: t1, t2.id: t2})

        results = await api.batch_pin_tasks([
            {"task_id": t1.id, "project_id": t1.project_id, "pin": True},
            {"task_id": t2.id, "project_id": t2.project_id, "pin": False},
        ])

        # One combined write for both tasks, not one call per task.
        assert api._v2_client.batch_tasks.await_count == 1
        updates = api._v2_client.batch_tasks.call_args.kwargs["update"]
        assert len(updates) == 2
        # First pinned, second unpinned; both keep their due dates.
        assert updates[0]["pinnedTime"] is not None
        assert updates[0]["dueDate"] == "2026-07-20T15:00:00.000+0000"
        assert updates[1]["pinnedTime"] is None
        assert updates[1]["dueDate"] == "2026-07-21T15:00:00.000+0000"
        # Results come back in input order.
        assert [r.id for r in results] == [t1.id, t2.id]
