import sys
import asyncio
import requests
from datetime import datetime
#from rc import RC

from rich import print
from rich.align import Align
from rich.box import DOUBLE
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text
from rich.json import JSON
from rich.console import RenderableType
from rich.markdown import Markdown
from rich.style import Style

from textual import log, events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Content, Container, Vertical
from textual.widget import Widget
from textual.widgets import Button, Header, Footer, Static, Input
from textual.reactive import reactive, Reactive
from textual.message import Message, MessageTarget
from textual.screen import Screen

import logging
from logging.handlers import QueueHandler, QueueListener
import queue
from anytree import RenderTree

logging.basicConfig(level=logging.DEBUG)


class TitleBox(Static):
    def __init__(self, title, **kwargs):
        super().__init__(Markdown(f'# {title}'))

class RunNumDisplay(Static): pass

# class RunTypeDisplay(Static): pass

class RunInfo(Static):
    runnum  = reactive('none')
    runtype = reactive('none')

    def __init__(self, hostname, **kwargs):
        super().__init__(**kwargs)
        self.runtext = Markdown('# Run info')
        self.hostname = hostname
    
    def update_text(self):
        run_num_display = self.query_one(RunNumDisplay)
        
        if self.runtype != "none":
            self.runtext = Markdown(f'# Run info\n\nNumber: {self.runnum}\n\nType: {self.runtype}')
        else:
            self.runtext = Markdown('# Run info')

        self.change_colour(run_num_display)
        run_num_display.update(self.runtext)

    def change_colour(self, obj) -> None:
        #If the colour is correct then return
        if ('STOPPED' in self.runtype and obj.has_class("redtextbox")) or ('STOPPED' not in self.runtype and obj.has_class("greentextbox")):
            return 
        #Otherwise, swap to the other colour
        if obj.has_class("redtextbox"):
            obj.remove_class("redtextbox")
            obj.add_class("greentextbox")
        else:
            obj.remove_class("greentextbox")
            obj.add_class("redtextbox")

    def update_runnum(self) -> None:
        r = requests.get((f'{self.hostname}/nanorcrest/run_number'), auth=("fooUsr", "barPass"))
        if r.text:
            self.runnum = r.text

    def update_runtype(self) -> None:
        r = requests.get((f'{self.hostname}/nanorcrest/run_type'), auth=("fooUsr", "barPass"))
        self.runnum = r.text

    def watch_runtype(self, run:str) -> None:
        self.update_text()

    def watch_runnum(self, run:str) -> None:
        self.update_text()

    def on_mount(self) -> None:
        self.set_interval(0.1, self.update_runnum)
        self.set_interval(0.1, self.update_runtype)

    def compose(self) -> ComposeResult:
        yield RunNumDisplay(classes="redtextbox")
        
class LogDisplay(Static):
    logs = reactive('')

    class SearchAgain(Message):    
        '''The message that tells the searchbar to update itself'''
        def __init__(self, sender: MessageTarget) -> None:
            super().__init__(sender)

    def __init__(self, log_queue, **kwargs):
        super().__init__(**kwargs)
        self.log_queue = log_queue
        self.handler = RichHandler()
        self.search_mode = False
        self.searched_logs = ''
    
    def on_mount(self) -> None:
        self.set_interval(0.1, self.update_logs) # execute update_logs every second
    
    def update_logs(self) -> None:
        while True: # drain the queue of logs
            try:
                record = self.log_queue.get(block=False)
                text = self.handler.render_message(record, record.msg)
                self.logs = f'{text}\n' + self.logs
            except:
                break

    def watch_logs(self, logs:str, searched_logs:str) -> None:
        if self.search_mode:
            self.emit_no_wait(self.SearchAgain(self)) #Send a message up to the parent
            self.update(searched_logs)
        else:
            self.update(logs)
    
    def delete_logs(self) -> None:
        self.logs = ""

    def save_logs(self) -> None:
        data = self.logs
        # self.delete_logs() # dont want to delete_logs here
        
        time = str(datetime.now())
        
        time = time[:-7]               # Times to the nearest second instead of microsecond
        time = "-".join(time.split())  # Joins date and time with a hyphen instead of a space
        time = time.replace(":","")    # chuck the weird ":"
        filename = f"logs_{time}"
        try: 
            with open(filename, "x") as f:
                f.write(data)
        except:
            pass
    
class Logs(Static):
    def __init__(self, log_queue, hostname, **kwargs):
        super().__init__(**kwargs)
        self.log_queue = log_queue
        self.hostname = hostname
    
    def compose(self) -> ComposeResult:
        yield TitleBox('Logs')
        yield Input(placeholder='Search logs')
        yield Horizontal(
            Button("Save logs", id="save_logs"),
            Button("Clear logs", id="delete_logs"),
            classes='horizontalbuttonscontainer'
        )
        yield Vertical(
            LogDisplay(self.log_queue),
            id='verticallogs'
        )

    async def on_button_pressed (self, event: Button.Pressed) -> None:
        button_id = event.button.id
        logdisplay = self.query_one(LogDisplay)
        method = getattr(logdisplay, button_id)
        method()

    async def on_input_changed(self, message: Input.Changed) -> None:
        """A coroutine to handle a text changed message."""
        await self.begin_search(message.value)

    async def on_log_display_search_again(self, message:LogDisplay.SearchAgain) -> None:
        '''To get the right name, we convert from CamelCase to snake_case'''
        textbox = self.query_one(Input)
        await self.begin_search(textbox.value)
        
    async def begin_search(self, message:str) -> None:
        '''This function is called when the logs update, and when the user types in the box'''
        logdisplay = self.query_one(LogDisplay)
        if message:
            logdisplay.search_mode = True
            task = asyncio.create_task(self.filter_logs(logdisplay, message))
            logdisplay.searched_logs = await(task)
            logdisplay.update(logdisplay.searched_logs)
        else:
            logdisplay.search_mode = False
            logdisplay.update(logdisplay.logs)

    async def filter_logs(self, logdisplay, term: str):
        loglist = logdisplay.logs.split("\n")                                       #Splits the log string into a list of logs
        #Gets a list of all logs that contain term as a substring (case insensitive)
        searchedlist = [log for log in loglist if term.lower() in log.lower()]   
        return "\n".join(searchedlist)                                              #Reformats the list as a string with newlines



class StatusDisplay(Static): pass

class Status(Static):
    rcstatus = reactive('none')

    def __init__(self, hostname, **kwargs):
        super().__init__(**kwargs)
        self.hostname = hostname

    def update_rcstatus(self) -> None:
        r = requests.get((f'{self.hostname}/nanorcrest/status'), auth=("fooUsr", "barPass"))
        info = r.json()                 #dictionary of information about the topnode
        self.rcstatus = info['state']

    def watch_rcstatus(self, status:str) -> None:
        status_display = self.query_one(StatusDisplay)
        nice_status = status.replace('_', ' ').capitalize()
        status_display.update(Markdown(f'# Status\n\n{nice_status}'))

    def on_mount(self) -> None:
        self.set_interval(0.1, self.update_rcstatus)

    def compose(self) -> ComposeResult:
        # yield TitleBox("Status {}")
        yield StatusDisplay()

class TreeDisplay(Static): pass

class TreeView(Static):
    rctree = reactive('')
    
    def __init__(self, hostname, **kwargs):
        super().__init__(**kwargs)
        self.hostname = hostname
        
    def compose(self) -> ComposeResult:
        yield TitleBox("Apps")
        yield Vertical(TreeDisplay(), id='verticaltree')
    
    def update_rctree(self) -> None:
        r = requests.get((f'{self.hostname}/nanorcrest/tree'), auth=("fooUsr", "barPass"))
        self.rctree = r.json()      #Format is {'children': [...], 'name': 'foonode'} where the elements of children have the same structure

    def watch_rctree(self, tree:dict) -> None:
        tree_display = self.query_one(TreeDisplay)

        nicetree = self.render_json(tree, 0, "")
        tree_display.update(nicetree)

    def on_mount(self) -> None:
        self.set_interval(0.1, self.update_rctree)

    def render_json(self, elements, level:int, prefix:str):
        branch_extend = '│  '
        branch_mid    = '├─ '
        branch_last   = '└─ '
        spacing       = '   '
        rows = []
        last_cat = False
        last_app = False
        clist = self.make_colour_list("bold magenta", "royal_blue1", "green")        #Colours may be altered here
        '''
        for tl_key in tree:                                                                 #Loop over top level nodes
            tlvalue = tree[tl_key]
            typelist = tlvalue['children']
            text = f"{col1}{tl_key}: {tlvalue['state']}\n{col1end}"    
            rows.append(text)
            for i, typedict in enumerate(typelist):                                         #Loop over the dictionaries that correspond to a category
                last_cat = (i == len(typelist)-1)
                typename = list(typedict.keys())[0]    
                typedata = typedict[typename]                                               #Gets the subdictionary with state and children
                applist = typedata['children']
                if last_cat:                                                    #If we are at the end, use the right shape
                    c1 = branch_last
                else:
                    c1 = branch_mid               
                text = f"{col1}{c1}{col1end}{col2}{typename}: {typedata['state']}\n{col2end}"
                rows.append(text)
                for j, appdict in enumerate(applist):                                                     #Loop over the apps themselves
                    last_app = (j == len(applist)-1)
                    appname = list(appdict.keys())[0]
                    appdata = appdict[appname]                                              #Gets the subdictionary that contains the state
                    if last_cat:
                        a1 = spacing
                    else:
                        a1 = branch_extend
                    if last_app:
                        a2 = branch_last
                    else:
                        a2 = branch_mid
                    text = f"{col1}{a1}{col1end}{col2}{a2}{col2end}{col3}{appname}: {appdata['state']}\n{col3end}"
                    rows.append(text)
        '''
        
        '''
        if type(elements) == dict:      #The top level might be a dict instead of a list of them
            text = elements['name']
            if 'children' in tree:
                new_level  = level + 1
                for child in children:
                    new_prefix = branch
                    rows += render_json(child, new_level, )
            return "".join(rows)
        else:
            for node in elements:       #A list of dictionaries
                text = tree['name']
                if 'children' in tree:
                    new_level  = level + 1
                    for child in children:
                        new_prefix = branch
                        rows += render_json(child, new_level, )
                return "".join(rows)
        '''
        return f"[red]WORK IN PROGRESS![/red]"
    
    def make_colour_list(*colours):
        clist = []
        for c in colours:
            col = f'[{c}]'              #Adds square brackets
            c_end = f"[/{col[1:]}"      #Inserts a slash at the start
            c_tuple = (col, c_end)
            clist.append(c_tuple)

        return clist

class Command(Static):
    commands = reactive([])
    
    def __init__(self, hostname, **kwargs):
        super().__init__(**kwargs)
        self.hostname = hostname
        self.all_commands = []
        
    def on_mount(self) -> None:
        self.set_interval(0.1, self.update_buttons)

    def update_buttons(self) -> None:
        r = requests.get((f'{self.hostname}/nanorcrest/command'), auth=("fooUsr", "barPass"))
        self.commands = [key for key in r.json()]   #Command is a dict of currently allowed commands and some associated data, this gets the keys

    def watch_commands(self, commands:list[str]) -> None:
        #always_displayed = ['quit', 'abort']
        for button in self.query(Button):
            if button.id in self.commands:
                button.display=True
            else:
                button.display=False

            if button.id == 'abort':
                button.color = 'red'
        
    def compose(self) -> ComposeResult:
        yield TitleBox('Commands')
        r = requests.get((f'{self.hostname}/nanorcrest/fsm'), auth=("fooUsr", "barPass"))
        fsm = r.json()
        for data in fsm['transitions']:         #List of transitions, format is {'dest': 'ready', 'source': 'configured', 'trigger': 'start'}
            self.all_commands.append(data['trigger']) #Gets every transition trigger (i.e every command)

        yield Vertical(
            Horizontal(
                *[Button(b.replace('_', ' ').capitalize(), id=b) for b in self.all_commands], #Generates a button for each command
                classes='horizontalbuttonscontainer',
            ),
            Horizontal(
                Button('Quit', id='quit'),
                Button('Abort',variant='error', id='abort'),
                classes='horizontalbuttonscontainer',
            ),
            id = 'verticalbuttoncontainer'
        )
        
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Event handler called when a button is pressed."""
        button_id = event.button.id
        if button_id == 'abort':
            sys.exit(0)
        else:
            self.app.mount(InputWindow(hostname=self.hostname, command=button_id, id="pop_up"))
            #Since this code runs as a module, we need to ask the command widget what its app is
            for b in self.query(Button):
                b.disable = True
            
class InputWindow(Widget):
    def __init__(self, hostname, command, **kwargs):
        super().__init__(**kwargs)
        self.command = command
        self.hostname = hostname

    def compose(self) -> ComposeResult:
        r = requests.get((f'{self.hostname}/nanorcrest/command'), auth=("fooUsr", "barPass"))
        data = r.json()     #json has format {'boot': [{'timeout': {'default': None, 'required': False, 'type': 'INT'}}]}
        paramlist = data[self.command]
        params = {k: v for d in paramlist for k, v in d.items()}    #We turn the list of dicts into one dict for convenience 
        yield Vertical(
            *[Input(placeholder=key, id=key) for key in params],
            Horizontal(
                Button("Execute Command", id="go"),
                Button('Cancel',variant='error', id='cancel'),
                classes = "horizontalbuttonscontainer"
            )
        )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        params = {}
        inputs = self.query(Input)

        if button_id == "go":
            for i in inputs:
                params[i.id] = i.value
            payload = {'command': self.command, **params}
            r = requests.post((f'{self.hostname}/nanorcrest/command'), auth=("fooUsr", "barPass"), data=payload)
            
        self.remove()

class NanoRCTUI(App):
    CSS_PATH = "/afs/cern.ch/user/j/jhancock/nanorc-dev-area/sourcecode/nanorc/src/nanorc/tui.css"
    BINDINGS = [("d", "toggle_dark", "Toggle dark mode")]

    def __init__(self, host, rest_port, banner, **kwargs):
        super().__init__(**kwargs)
        self.log_queue = queue.Queue(-1)
        self.queue_handler = QueueHandler(self.log_queue)
        #self.rc.log.propagate = False
        #self.rc.log.addHandler(self.queue_handler)
        self.hostname = f'http://{host}:{rest_port}'

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Container(
            RunInfo  (hostname = self.hostname, classes='container'),
            Status   (hostname = self.hostname, classes='container'),
            Command  (hostname = self.hostname, classes='container', id='command'),
            TreeView (hostname = self.hostname, classes='container', id='tree'),
            Logs     (log_queue=self.log_queue, hostname = self.hostname, classes='container', id='log'),
            id = 'app-grid'
        )
        
        yield Header(show_clock=True)
        yield Footer()  
        
if __name__ == "__main__":
    app = NanoRCTUI()
    app.run()

#TODO get rid of the foouser stuff since it's insecure (get auth from dotnanorc like with the logbook)
#TODO get rid of anything that accesses the rc object (API only!)
#TODO the popup should only appear when there are mandatory arguments, or the user uses a keybind (ctrl?)
#TODO Command buttons should be deactivated when there is a popup