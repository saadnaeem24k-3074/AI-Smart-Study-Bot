import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from bot import AttendanceBot
from core.session_manager import SessionManager
from utils.state_store import StateStore


class SessionManagerNotesTests(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_state_tracks_join_leave_and_notes_generation(self):
        manager = object.__new__(SessionManager)
        with (
            patch.object(StateStore, "_state", {
                "current_class": None,
                "status": "idle",
                "attendance_marked": False,
                "session_start": None,
                "last_caption": "",
                "alerts": [],
                "slide_count": 0,
            }),
            patch.object(StateStore, "_save"),
        ):
            state = StateStore()
            manager.state = state
            state.set_current_class({"subject": "Software"})
            self.assertEqual(state.get("status"), "joining")

            state.mark_joined()
            self.assertEqual(state.get("status"), "in_class")

            state.set_status("generating_notes")
            self.assertEqual(state.get("status"), "generating_notes")
            state.set_idle()
            self.assertEqual(state.get("status"), "idle")
            self.assertIsNone(state.get("current_class"))

    async def test_notes_start_as_soon_as_finalization_is_requested(self):
        manager = object.__new__(SessionManager)
        recorder = Mock(subject="Software")
        finalize_started = asyncio.Event()

        async def finalize():
            finalize_started.set()
            return Path("notes/Software/session")

        recorder.finalize = AsyncMock(side_effect=finalize)
        manager.current_recorder = recorder
        manager._notes_task = None
        manager.state = Mock()

        task = manager.start_notes_finalization()
        await asyncio.wait_for(finalize_started.wait(), timeout=1)

        manager.state.set_status.assert_called_once_with("generating_notes")
        recorder.finalize.assert_awaited_once()
        await task
        manager.state.set_idle.assert_called_once_with()

    async def test_bot_shutdown_finalizes_notes_after_leaving(self):
        handler = Mock()
        handler.leave = AsyncMock()
        session = Mock(current_handler=handler)
        session.finalize_notes = AsyncMock()
        bot = object.__new__(AttendanceBot)
        bot.scheduler = Mock(session=session)

        await bot._leave_active_meeting()

        handler.leave.assert_awaited_once()
        session.finalize_notes.assert_awaited_once()

    async def test_concurrent_shutdown_and_session_cleanup_finalize_notes_once(self):
        manager = object.__new__(SessionManager)
        recorder = Mock(subject="Software")
        recorder.finalize = AsyncMock(return_value=Path("notes/Software/session"))
        manager.current_recorder = recorder
        manager._notes_task = None
        manager.state = Mock()

        await asyncio.gather(manager.finalize_notes(), manager.finalize_notes())

        recorder.finalize.assert_awaited_once()
        manager.state.update.assert_called_once_with("last_notes", str(Path("notes/Software/session")))


if __name__ == "__main__":
    unittest.main()
