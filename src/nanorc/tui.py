import sys
import asyncio
import requests
import os
from datetime import datetime

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
from anytree.importer import DictImporter

logging.basicConfig(level=logging.DEBUG)
allowInput = True
alwaysAsk = False

class TitleBox(Static):
    def __init__(self, title, **kwargs):
        super().__init__(Markdown(f'# {title}'))

class RunNumDisplay(Static): pass

class RunInfo(Static):
    runnum  = reactive('none')
    runtype = reactive('none')

    def __init__(self, hostname, **kwargs):
        super().__init__(**kwargs)
        self.runtext = Markdown('# Run info')
        self.hostname = hostname

    def change_text(self):
        run_num_display = self.query_one(RunNumDisplay)
        if self.runtype == "none":
            self.runtext = Markdown('# Run info')
        else:
            self.runtext = Markdown(f'# Run info\n\nNumber: {self.runnum}\n\nType: {self.runtype}')
            
        self.change_colour(run_num_display)
        run_num_display.update(self.runtext)

    def change_colour(self, obj) -> None:
        redlist = ['STOPPED', 'none']
        greenlist = ['TEST', 'PROD']
        #If the colour is correct then return
        if (self.runtype in redlist and obj.has_class("redtextbox")) or ('STOPPED' not in self.runtype and obj.has_class("greentextbox")):
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
        if r.text == "null":
            self.runnum = ""
        else:
            self.runnum = r.text

    def update_runtype(self) -> None:
        r = requests.get((f'{self.hostname}/nanorcrest/run_type'), auth=("fooUsr", "barPass"))
        self.runnum = r.text

    def watch_runtype(self, run:str) -> None:
        self.change_text()

    def watch_runnum(self, run:str) -> None:
        self.change_text()

    def on_mount(self) -> None:
        self.set_interval(0.1, self.update_runnum)
        self.set_interval(0.1, self.update_runtype)

    def compose(self) -> ComposeResult:
        yield RunNumDisplay(id="runbox", classes="redtextbox")
        
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

    async def receive_log(self, the_log):
        md = Text(the_log)              #Renders the message into rich text
        self.logs = f'{md}\n' + self.logs
        self.update(self.logs)
    
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
        '''
        yield Vertical(
            LogDisplay(self.log_queue),
            id='verticallogs'
        )
        '''
        yield LogDisplay(self.log_queue)

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

    async def deliver_message(self, text):
        logdisplay = self.query_one(LogDisplay)
        await logdisplay.receive_log(text)

class StatusDisplay(Static): pass

class Status(Static):
    rcstatus = reactive('none')
    active = reactive('none')
    ask = reactive('none')

    def __init__(self, hostname, **kwargs):
        super().__init__(**kwargs)
        self.hostname = hostname

    def update_rcstatus(self) -> None:
        r = requests.get((f'{self.hostname}/nanorcrest/status'), auth=("fooUsr", "barPass"))
        info = r.json()                 #dictionary of information about the topnode
        self.rcstatus = info['state']

    def watch_rcstatus(self, rcstatus:str) -> None:
        self.change_status(rcstatus, self.active, self.ask)

    def update_active(self):
        if allowInput:
            self.active = "Idle"
        else:
            self.active = "Working..."
    
    def watch_active(self, active:str) -> None:
        self.change_status(self.rcstatus, active, self.ask)

    def update_ask(self):
        if alwaysAsk:
            self.ask = "All inputs required"
        else:
            self.ask = "Default Inputs used"

    def watch_ask(self, ask:str):
        self.change_status(self.rcstatus, self.active, ask)

    def change_status(self, status, act, asktext):
        status_display = self.query_one(StatusDisplay)
        nice_status = status.replace('_', ' ').capitalize()
        status_display.update(Markdown(f'# Status\n{nice_status}\n{act}\n\n{asktext}'))

    def on_mount(self) -> None:
        self.set_interval(0.1, self.update_rcstatus)
        self.set_interval(0.1, self.update_active)
        self.set_interval(0.1, self.update_ask)

    def compose(self) -> ComposeResult:
        # yield TitleBox("Status {}")
        yield StatusDisplay()

class TreeDisplay(Static): pass

class TreeView(Static):
    rctree = reactive('none')
    
    def __init__(self, hostname, **kwargs):
        super().__init__(**kwargs)
        self.hostname = hostname
        
    def compose(self) -> ComposeResult:
        yield TitleBox("Apps")
        #yield Vertical(TreeDisplay(), id='verticaltree')
        yield TreeDisplay()
    
    def update_rctree(self) -> None:
        r = requests.get((f'{self.hostname}/nanorcrest/tree'), auth=("fooUsr", "barPass"))
        #Format is {'children': [...], 'name': 'foonode'} where the elements of children have the same structure
        importer = DictImporter()
        data = importer.import_(r.json())
        the_text = Text("")
        for pre, _, node in RenderTree(data):
            the_line = Text("")
            working = True
            state_str = ''
            style = ''
            if node.errored:
                state_str += "ERROR - "
                style = 'bold red'
                working = False
            state_str += f"{node.state}"
            if not node.included:
                state_str += " - excluded"
                style = 'bright_black'
                working = False
            if node.state != "none" and working:        #A none state will have the default colour (white)
                style = "green"
            state_str += '\n'
            the_text.append(f"{pre}{node.name}: ", style=(style))
            the_text.append(state_str, style=(style))

        self.rctree = the_text     #This is a string representation of the tree

    def watch_rctree(self, rctree:str) -> None:
        tree_display = self.query_one(TreeDisplay)
        tree_display.update(rctree)

    def on_mount(self) -> None:
        self.set_interval(0.1, self.update_rctree)

class Command(Static):
    commands = reactive([])

    class NewLog(Message):    
        '''The message that informs the log queue of a new entry'''
        def __init__(self, sender: MessageTarget, text:str) -> None:
            self.text = text
            super().__init__(sender)
    
    def __init__(self, hostname, **kwargs):
        super().__init__(**kwargs)
        self.hostname = hostname
        
    def on_mount(self) -> None:
        self.set_interval(0.1, self.update_buttons)

    def update_buttons(self) -> None:
        r = requests.get((f'{self.hostname}/nanorcrest/command'), auth=("fooUsr", "barPass"))
        self.commands = [key for key in r.json()]   #Command is a dict of currently allowed commands and some associated data, this gets the keys

    def watch_commands(self, commands:list[str]) -> None:
        second_line = ["exclude", "include"]
        global allowInput
        box1 = self.query(Horizontal)[0]
        box2 = self.query(Horizontal)[1]

        #Delete old buttons
        all_buttons1 = box1.query(Button)
        all_buttons2 = box2.query(Button)
        for b in all_buttons1:
            b.remove()
        for b in all_buttons2:
            b.remove()

        #Generate 1st line
        for c in self.commands:
            if c in second_line:
                continue
            if c == "abort":
                box1.mount(Button('Abort',variant='error', id='abort'))  #Abort button is red
            else:
                box1.mount(Button(c.replace('_', ' ').capitalize(), id=c))
        #Generate 2nd line
        for c in self.commands:
            if c not in second_line:
                continue
            if c == "abort":
                box2.mount(Button('Abort',variant='error', id='abort'))  #Abort button is red
            else:
                box2.mount(Button(c.replace('_', ' ').capitalize(), id=c))
        

        '''
        for button in self.query(Button):
            if button.id in self.commands:
                button.display=True
            else:
                button.display=False

            if button.id == 'abort':
                button.color = 'red'
        '''


        allowInput = True        #A change in FSM state means our command is done so we can accept a new one
        
    def compose(self) -> ComposeResult:
        yield TitleBox('Commands')
        yield Horizontal(id="box1", classes='horizontalbuttonscontainer')
        yield Horizontal(id="box2", classes='horizontalbuttonscontainer')
        '''
        r = requests.get((f'{self.hostname}/nanorcrest/fsm'), auth=("fooUsr", "barPass"))   #Change this (to /command)!
        fsm = r.json()
        for data in fsm['transitions']:         #List of transitions, format is {'dest': 'ready', 'source': 'configured', 'trigger': 'start'}
            if data['trigger'] not in self.all_commands:    #There can be duplicates: avoid them
                self.all_commands.append(data['trigger'])   #Gets every transition trigger (i.e every command)

        yield Horizontal(
                *[Button(b.replace('_', ' ').capitalize(), id=b) for b in self.all_commands], #Generates a button for each command
                classes='horizontalbuttonscontainer',
            )
        yield Horizontal(
                Button('Quit', id='quit'),
                Button('Abort',variant='error', id='abort'),
                classes='horizontalbuttonscontainer',
            )
        '''

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Event handler called when a button is pressed."""
        global allowInput
        if allowInput:
            button_id = event.button.id
            if button_id == 'abort':
                sys.exit(0)
            #Get all allowed commands and their inputs
            r = requests.get((f'{self.hostname}/nanorcrest/command'), auth=("fooUsr", "barPass"))
            data = r.json()         #json has format {'boot': [{'timeout': {'default': None, 'required': False, 'type': 'INT'}}]}
            paramlist = data[button_id]
            mandatory = False 
            for p in paramlist:
                for key in p:       #Should be just one of these
                    info = p[key]
                if info['required']:
                    mandatory = True
                    break
            allowInput = False      #Deactivate until the command is completed
            #The box must be shown if there are mandatory arguments. It also can be requested by pressing 'i' to switch modes.
            if mandatory or alwaysAsk:               
                self.app.mount(InputWindow(hostname=self.hostname, command=button_id, id="pop_up"))
            else:
                payload = {'command': button_id}
                #Sends the command to nanorc 
                r = requests.post((f'{self.hostname}/nanorcrest/command'), auth=("fooUsr", "barPass"), data=payload)
                if button_id == "start":
                    raise ValueError(r.json())
                if "logs" in r.json():
                    cmd_log = r.json()['logs']                      #Other fields are form and "return_code"
                    self.emit_no_wait(self.NewLog(self, cmd_log))   #Sends a message to the parent (the app)
                if "Exception" in r.json():
                    raise ValueError(r.json())
                   
class InputWindow(Widget):
    class NewLog(Message):    
        '''The message that informs the log queue of a new entry'''
        def __init__(self, sender: MessageTarget, text:str) -> None:
            super().__init__(sender)

    def __init__(self, hostname, command, **kwargs):
        super().__init__(**kwargs)
        self.command = command
        self.hostname = hostname

    def compose(self) -> ComposeResult:
        r = requests.get((f'{self.hostname}/nanorcrest/command'), auth=("fooUsr", "barPass"))
        data = r.json()     #json has format {'boot': [{'timeout': {'default': None, 'required': False, 'type': 'INT'}}]}
        paramlist = data[self.command]
        self.params = {k:v for d in paramlist for k, v in d.items()}    #We turn the list of dicts into one dict for convenience 
        yield Vertical(
            *[Input(placeholder=key, id=key) for key in self.params],
            Horizontal(
                Button("Execute Command", id="go"),
                Button('Cancel',variant='error', id='cancel'),
                classes = "horizontalbuttonscontainer"
            ), 
            Static(id='errordisplay')
        )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        params_out = {}
        inputs = self.query(Input)
        #A list of all statics with the given id. There should only be one of these, so we get element 0
        errordisplay = [q for q in self.query(Static) if q.id == "errordisplay"][0]
        global allowInput

        if button_id == "go":
            for i in inputs:
                if i.value == "":     
                    if self.params[i.id]['required']:       #We can't allow a required field to be empty!
                        errordisplay.update(f"Required parameter \"{i.id}\" is missing!")
                        return                              #An attempt at sending a command is over
                else:
                    #We enforce here that the string will be convertable to the appropriate type
                    match self.params[i.id]['type']:
                        case "INT":
                            if not i.value.isdigit():
                                errordisplay.update(f"{i.value} is not a valid input for \"{i.id}\". Input should be an integer.")
                                return
                        case "FLOAT":
                            for char in i.value:
                                if (not char.isdigit()) and (char != '.'):
                                    errordisplay.update(f"{i.value} is not a valid input for \"{i.id}\". Input should be a float.")
                                    return
                        case "BOOL":
                            if (i.value.lower() != "true") and (i.value.lower() != "false"):
                                errordisplay.update(f"{i.value} is not a valid input for \"{i.id}\". Input should be a boolean.")
                                return
                    params_out[i.id] = i.value

            payload = {'command': self.command, **params_out}
            r = requests.post((f'{self.hostname}/nanorcrest/command'), auth=("fooUsr", "barPass"), data=payload)
            if "logs" in r.json():
                cmd_log = r.json()['logs']                      #Other fields are "form" and "return_code"
                self.emit_no_wait(self.NewLog(self, cmd_log))   #Sends a message to the parent (the app)
            if "Exception" in r.json():
                raise ValueError(r.json())
            allowInput = True
            self.remove()

        if button_id == "cancel":
            allowInput = True
            self.remove()
        

class NanoRCTUI(App):
    CSS_PATH = __file__[:-2] + "css"      #Gets the full path for a file called tui.css in the same folder as tui.py
    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("i", "toggle_inputs", "Toggle whether optional inputs are taken")
        ]

    def __init__(self, host, rest_port, banner, **kwargs):
        super().__init__(**kwargs)
        self.mylog = logging.getLogger("NanoRCTUI")
        self.log_queue = queue.Queue(-1)
        self.queue_handler = QueueHandler(self.log_queue)
        self.mylog.addHandler(self.queue_handler)
        self.hostname = f'http://{host}:{rest_port}'

    async def on_command_new_log(self, message:Command.NewLog) -> None:
        '''To get the right name, we convert from CamelCase to snake_case'''
        log_obj = self.query_one(Logs)
        await log_obj.deliver_message(message.text)

    async def on_input_window_new_log(self, message:InputWindow.NewLog) -> None:
        '''The input window can provide logs too'''
        log_obj = self.query_one(Logs)
        await log_obj.deliver_message(message.text)

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark
    
    def action_toggle_inputs(self) -> None:
        global alwaysAsk
        alwaysAsk = not alwaysAsk

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
#TODO Time freezes when requests are sent: figure out why
#TODO Make the logs scroll again
#TODO Make the command box not be narrow
#TODO Get rid of logqueue maybe

#TODO The run number box doesn't work for some reason
#TODO Fix idle/working thing
#TODO commands that go back are freezing for some reason