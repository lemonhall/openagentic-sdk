from __future__ import annotations

from textual.app import App
from textual.binding import Binding
from textual.widgets import Footer, Header

from .config import InsightConfig, load_config
from .screens.dashboard import DashboardScreen
from .screens.session_detail import SessionDetailScreen
from .screens.session_list import SessionListScreen


class CodexInsightApp(App[None]):
    TITLE = "Codex Insight"

    BINDINGS = [
        Binding("d", "goto_dashboard", "Dashboard"),
        Binding("l", "goto_list", "Sessions"),
        Binding("q", "quit", "Quit"),
        Binding("escape", "back", "Back", show=False),
        Binding("?", "help", "Help"),
    ]

    def __init__(
        self,
        *,
        db_path_override: str | None = None,
        sessions_dir_override: str | None = None,
        timezone_override: str | None = None,
    ) -> None:
        super().__init__()
        self._db_path_override = db_path_override
        self._sessions_dir_override = sessions_dir_override
        self._timezone_override = timezone_override
        self.cfg: InsightConfig = load_config()
        if self._db_path_override:
            self.cfg = self.cfg.with_overrides(db_path=self._db_path_override)
        if self._sessions_dir_override:
            self.cfg = self.cfg.with_overrides(sessions_dir=self._sessions_dir_override)
        if self._timezone_override:
            self.cfg = self.cfg.with_overrides(timezone=self._timezone_override)

    def compose(self):
        yield Header(show_clock=True)
        yield Footer()

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen(self.cfg))

    def action_goto_dashboard(self) -> None:
        self.switch_screen(DashboardScreen(self.cfg))

    def action_goto_list(self) -> None:
        self.switch_screen(SessionListScreen(self.cfg))

    def action_back(self) -> None:
        if len(self.screen_stack) > 1:
            self.pop_screen()

    def action_help(self) -> None:
        self.notify(
            "快捷键：d Dashboard；l Sessions；Enter 下钻；Esc 返回；q 退出",
            title="帮助",
        )

    def open_session(self, session_id: str) -> None:
        self.push_screen(SessionDetailScreen(self.cfg, session_id=session_id))
