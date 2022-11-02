from textual import log
from textual.app import App, ComposeResult
from textual.containers import Container, Content
from textual.widgets import Button, Header, Footer, Static

class StatusDisplay(Static):
    pass
#     def __init__(self, rc):
#         super().__init__()
#         self.rc = rc

#     def compose(self) -> ComposeResult:
#         from .node_render import status_data
#         yield


class NanoRCStatus(Static):
    def __init__(self, rc, **kwargs):
        super().__init__(**kwargs)
        self.rc = rc

    def update_status(self) -> None:
        from .node_render import get_status
        status_display = self.query_one(StatusDisplay)
        status_display.update(get_status(self.rc.topnode))

    def on_mount(self) -> None:
        self.update_status()

    def compose(self) -> ComposeResult:
        yield StatusDisplay()
        yield Button('Update status', id='update_status', variant='primary')

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Event handler called when a button is pressed."""
        if event.button.id == "update_status":
            self.update_status()

class RunInfo(Static):
    def __init__(self, rc, **kwargs):
        super().__init__(**kwargs)
        self.rc = rc

    def update_run(self) -> None:
        from .runinfo import get_run_info
        self.update(get_run_info(run_info = None))

    def on_mount(self) -> None:
        self.update_run()

class TreeView(Static):
    def __init__(self, rc, **kwargs):
        super().__init__(**kwargs)
        self.rc = rc

    def update_tree(self) -> None:
        from .node_render import get_node
        self.update(get_node(self.rc.topnode))

    def on_mount(self) -> None:
        self.update_tree()

class StateBox(Static):
    def __init__(self, rc, **kwargs):
        super().__init__(**kwargs)
        self.rc = rc
    
    def compose(self) -> ComposeResult:
        #Creates the initial set of buttons

        for c in self.rc.topnode.fsm.get_available_commands(self.rc.topnode.state):
            yield Button(c, id=c, variant="primary")
        
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Event handler called when a button is pressed."""
        button_id = event.button.id
        method = getattr(self.rc, button_id)    #We use the name of the button to find the right method of the Nanorc class
        params = 120                            #Placeholder!
        method(params)

        #Then it must change the set of buttons to represent the allowed FSM transitions.

class NanoRCTUI(App):
    CSS_PATH = "nanorc.css"
    BINDINGS = [("d", "toggle_dark", "Toggle dark mode")]

    def __init__(self, rc, banner, **kwargs):
        super().__init__(**kwargs)
        self.rc = rc
        self.banner = banner

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield TreeView(rc=self.rc)
        yield NanoRCStatus(rc=self.rc)
        yield RunInfo(rc=self.rc)
        yield StateBox(rc=self.rc)
        yield Header()
        yield Footer()
        
