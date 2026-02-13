from __future__ import annotations

from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Static

from ..config import InsightConfig
from ..db.codex_db import CodexDb
from ..db.codex_sessions import CodexSessionsFs


class SessionListScreen(Screen[None]):
    BINDINGS = [("d", "goto_dashboard", "Dashboard")]

    def __init__(self, cfg: InsightConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self._db = CodexDb(cfg.codex_db_path)
        self._fs = CodexSessionsFs(cfg.codex_sessions_dir)

    def compose(self):
        with Vertical():
            yield Static("Level 1: Session 列表（Enter 下钻）", id="title")
            table = DataTable(id="table")
            table.cursor_type = "row"
            yield table

    def on_mount(self) -> None:
        table = self.query_one("#table", DataTable)
        table.add_columns("id", "title", "tokens", "cwd", "rollout")
        backend = self._db if self._db.exists() else self._fs
        if not (self._db.exists() or self._fs.exists()):
            return
        for s in backend.recent_sessions(limit=500):
            table.add_row(
                s.session_id,
                (s.title or "")[:80],
                "" if s.token_count is None else str(s.token_count),
                (s.cwd or "")[:60],
                "Y" if s.rollout_path else "",
                key=s.session_id,
            )

    def action_goto_dashboard(self) -> None:
        self.app.action_goto_dashboard()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:  # noqa: N802
        self.app.open_session(str(event.row_key.value))
