from kanban_tui.modal.modal_jira_url_screen import ModalBaseUrlScreen
from typing import Iterable, TYPE_CHECKING

from kanban_tui.config import Backends
from kanban_tui.modal.modal_auth_screen import ModalAuthScreen

if TYPE_CHECKING:
    from kanban_tui.app import KanbanTui

from rich.text import Text
from textual import on, work
from textual.reactive import reactive
from textual.widget import Widget
from textual.events import ScreenResume
from textual.widgets import Header
from textual.screen import Screen
from textual.worker import get_current_worker

from kanban_tui.classes.board import Board
from kanban_tui.widgets.board_widgets import KanbanBoard, TaskSearchBar
from kanban_tui.widgets.custom_widgets import KanbanTuiFooter
from kanban_tui.widgets.task_card import TaskCard


class BoardScreen(Screen):
    app: "KanbanTui"
    active_board: reactive[Board | None] = reactive(None, init=False)

    def compose(self) -> Iterable[Widget]:
        yield KanbanBoard()
        yield Header()
        yield TaskSearchBar()
        yield KanbanTuiFooter()

    @on(TaskSearchBar.SearchChanged)
    def handle_search_changed(self, event: TaskSearchBar.SearchChanged) -> None:
        self.query_one(KanbanBoard).apply_search(event.query)

    @on(TaskSearchBar.Submitted)
    def handle_search_submitted(self, event: TaskSearchBar.Submitted) -> None:
        if not event.query.strip():
            return
        board = self.query_one(KanbanBoard)
        if not board.focus_next_search_match():
            self.app.notify("No matching tasks", severity="warning", timeout=2)

    @on(TaskSearchBar.Dismissed)
    def handle_search_dismissed(self, event: TaskSearchBar.Dismissed) -> None:
        board = self.query_one(KanbanBoard)
        board.clear_search()
        self.query_one(TaskSearchBar).close()
        if board.selected_task:
            card = board.query_one_optional(
                f"#taskcard_{board.selected_task.task_id}", TaskCard
            )
            if card:
                card.focus()

    def watch_active_board(self):
        if self.active_board:
            border_title = Text.from_markup(
                f" [red]Active Board:[/] {self.active_board.full_name}"
            )
            self.query_one(KanbanBoard).border_title = border_title

    async def ensure_active_board(self):
        if not self.active_board:
            await self.query_one(KanbanBoard).action_show_boards()

    async def ensure_api_key(self):
        if not self.app.backend.api_key:
            await self.app.push_screen_wait(ModalAuthScreen())

    async def ensure_base_url(self):
        if not self.app.backend.settings.base_url:
            await self.app.push_screen_wait(ModalBaseUrlScreen())

    @work(group="board-refresh", exclusive=True)
    @on(ScreenResume)
    async def load_kanban_board(self, event: ScreenResume | None = None):
        self.set_reactive(BoardScreen.active_board, self.app.active_board)

        match self.app.config.backend.mode:
            case Backends.JIRA:
                await self.ensure_api_key()
                if not self.app.backend.api_key:
                    worker = get_current_worker()
                    worker.cancel()
                    self.app.config.set_backend(Backends("sqlite"))
                    self.app.exit(return_code=1, message="Please enter a valid api key")

                await self.ensure_base_url()
                if not self.app.backend.settings.base_url:
                    worker = get_current_worker()
                    worker.cancel()
                    self.app.config.set_backend(Backends("sqlite"))
                    self.app.exit(
                        return_code=1, message="Please enter a valid jira base url"
                    )

        await self.ensure_active_board()

        if self.app.needs_refresh:
            self.app.update_task_list()
            await self.query_one(KanbanBoard).refresh_columns()
            self.app.needs_refresh = False
