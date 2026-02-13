from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Static

from ..config import InsightConfig
from ..db.codex_db import CodexDb
from ..db.codex_sessions import CodexSessionsFs


class DashboardScreen(Screen[None]):
    BINDINGS = [("l", "goto_list", "Sessions")]

    def __init__(self, cfg: InsightConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self._db = CodexDb(cfg.codex_db_path)
        self._fs = CodexSessionsFs(cfg.codex_sessions_dir)

    def compose(self):
        with Vertical():
            yield Static("Level 0: 全局 Dashboard", id="title")
            with Horizontal():
                yield Static("", id="stats")
                yield Static("", id="bycwd")
            yield Static("最近 Sessions（Enter 下钻）", id="recent_title")
            table = DataTable(id="recent_table")
            table.cursor_type = "row"
            yield table

    def on_mount(self) -> None:
        self._refresh_dashboard()

    def _refresh_dashboard(self) -> None:
        backend = self._db if self._db.exists() else self._fs
        stats = backend.stats()
        stats_w = self.query_one("#stats", Static)
        if not (self._db.exists() or self._fs.exists()):
            stats_w.update("未发现 Codex 数据：既没有 SQLite，也没有 ~/.codex/sessions。")
        else:
            tok = "未知" if stats.token_sum is None else str(stats.token_sum)
            stats_w.update(f"Session 数：{stats.session_count}\nToken 总消耗：{tok}")

        bycwd = backend.sessions_by_cwd(limit=10)
        bycwd_w = self.query_one("#bycwd", Static)
        if not bycwd:
            bycwd_w.update("按项目（cwd）分组：无数据")
        else:
            lines = ["按项目（cwd）分组 Top10："]
            for cwd, c in bycwd:
                lines.append(f"- {c}  {cwd}")
            bycwd_w.update("\n".join(lines))

        table = self.query_one("#recent_table", DataTable)
        table.clear(columns=True)
        table.add_columns("id", "title", "tokens", "cwd")
        for s in backend.recent_sessions(limit=30):
            table.add_row(
                s.session_id,
                (s.title or "")[:80],
                "" if s.token_count is None else str(s.token_count),
                (s.cwd or "")[:80],
                key=s.session_id,
            )

    def action_goto_list(self) -> None:
        self.app.action_goto_list()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:  # noqa: N802
        self.app.open_session(str(event.row_key.value))
