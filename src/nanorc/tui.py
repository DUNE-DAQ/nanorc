import sys
import asyncio
import httpx
import requests
import os
import datetime
import time

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
from rich.spinner import Spinner

from textual import log, events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Content, Container, Vertical
from textual.widget import Widget
from textual.widgets import Button, Header, Footer, Static, Input, Label
from textual.reactive import reactive, Reactive
from textual.message import Message, MessageTarget
from textual.screen import Screen

import logging
from logging.handlers import QueueHandler, QueueListener
import queue
from anytree import RenderTree
from anytree.importer import DictImporter

logging.basicConfig(level=logging.DEBUG)
alwaysAsk = False
network_timeout = None   #This is immediately changed as soon as the app starts
auth = ("fooUsr", "barPass")

class TitleBox(Static):
    def __init__(self, title, **kwargs):
        super().__init__(Markdown(f'# {title}'))

class RunNumDisplay(Static): pass

class RunInfo(Static):
    runnum  = reactive('null')
    runtype = reactive('null')
    running = reactive(False)

    def __init__(self, hostname, **kwargs):
        super().__init__(**kwargs)
        self.runtext = Markdown('# Run info')
        self.hostname = hostname

    def change_text(self):
        run_num_display = self.query_one(RunNumDisplay)
        if self.runtype == "null":                      #Before any runs start
            self.runtext = Markdown('# Run info')
        else:
            if self.running:                            #During a run
                self.runtext = Markdown(f'# Run info\nNumber: {self.runnum}\n\nType: {self.runtype}')
            else:                                       #Between runs
                self.runtext = Markdown(f'# Run info\nLast Number: {self.runnum}\n\nLast Type: {self.runtype}')

        self.change_colour(run_num_display)
        run_num_display.update(self.runtext)

    def change_colour(self, obj) -> None:
        stoplist = ['STOPPED', "null"]      #STOPPED isn't used any more but we'll keep it just in case
        runlist = ['TEST', 'PROD']
        #If the colour is correct then return
        if self.runtype in stoplist:        #No runs have happened, so red
            rightclass = "redtextbox"
        elif self.runtype in runlist:       #A run has happened, but is it ongoing?
            if self.running:                #Ongoing run should be green
                rightclass = "greentextbox"
            else:                           #If we are between runs then go back to red
                rightclass = "redtextbox"
        else:
            raise RuntimeError("Could not assign a colour!")

        if obj.has_class(rightclass):       #If the class is correct already, then we are done
            return
        else:                               #Otherwise, swap to the other colour
            obj.toggle_class("redtextbox")
            obj.toggle_class("greentextbox")

    async def update_all(self) -> None:
        async with httpx.AsyncClient() as client:
            r = await client.get(f'{self.hostname}/nanorcrest/run_data', auth=auth)
        data = r.json()
        if data == "I'm busy!":
            return
        self.runnum = data['number']
        self.runtype = data['type']
        self.running = data['is_running']

    def watch_runtype(self) -> None:
        self.change_text()

    def watch_runnum(self) -> None:
        self.change_text()

    def watch_running(self) -> None:
        self.change_text()

    def on_mount(self) -> None:
        self.set_interval(0.1, self.update_all)

    def compose(self) -> ComposeResult:
        #yield RunNumDisplay(id="runbox", classes="redtextbox")
        yield RunNumDisplay(classes="redtextbox")

class LogDisplay(Static):
    logs = reactive('')

    class SearchAgain(Message):
        '''The message that tells the searchbar to update itself'''
        def __init__(self, sender: MessageTarget) -> None:
            super().__init__(sender)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.handler = RichHandler()
        self.search_mode = False
        self.searched_logs = ''

    def watch_logs(self, logs:str, searched_logs:str) -> None:
        if self.search_mode:
            self.emit_no_wait(self.SearchAgain(self)) #Send a message up to the parent
            self.update(searched_logs)
        else:
            self.update(Text(logs))

    def delete_logs(self) -> None:
        self.logs = ""
        self.update(Text(self.logs))

    def save_logs(self) -> None:
        data = self.logs
        t = datetime.datetime.now()
        t_str = t.strftime("%Y-%m-%d-%Hh%Mm%Ss")
        filename = f"logs_{t_str}.txt"
        try:
            with open(filename, "x") as f:
                f.write(data)
            f.close()
        except:
            pass

    async def receive_log(self, the_log):
        the_log_r = '\n'.join(the_log.split('\n')[::-1]) #Split the logs up at newlines, reverse the list, then recombine into a string
        self.logs = f'{the_log_r}\n' + self.logs
        self.update(Text(self.logs))                    #We render the logs as rich text

class Logs(Static):
    def __init__(self, hostname, **kwargs):
        super().__init__(**kwargs)
        self.hostname = hostname

    def compose(self) -> ComposeResult:
        yield TitleBox('Logs')

        yield Input(placeholder='Search logs')
        yield Horizontal(
            Button("Save logs", id="save_logs", variant='primary'),
            Button("Clear logs", id="delete_logs", variant='warning'),
            classes='horizontalbuttonscontainer'
            )
        yield Vertical(
            LogDisplay(),
            classes='verticallogs'
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
            logdisplay.update(Text(logdisplay.searched_logs))
        else:
            logdisplay.search_mode = False
            logdisplay.update(Text(logdisplay.logs))

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
    active = reactive(True)
    ask = reactive('none')

    def __init__(self, hostname, **kwargs):
        super().__init__(**kwargs)
        self.hostname = hostname

    async def update_rcstatus(self) -> None:
        async with httpx.AsyncClient() as client:
            r = await client.get(f'{self.hostname}/nanorcrest/status', auth=auth)
        info = r.json()                 #dictionary of information about the topnode
        if info == "I'm busy!":
            return

        self.rcstatus = info['state']

    def watch_rcstatus(self, rcstatus:str) -> None:
        self.change_status(rcstatus, self.active, self.ask)

    def receive_active_change(self, new_active:bool) -> None:
        self.active = new_active

    def watch_active(self, active:bool):
        self.change_status(self.rcstatus, active, self.ask)

    def update_ask(self):
        if alwaysAsk:
            self.ask = "Expert Mode"
        else:
            self.ask = "Non-Expert Mode"

    def watch_ask(self, ask:str):
        self.change_status(self.rcstatus, self.active, ask)

    def change_status(self, status, actBool, asktext):
        if actBool:
            actText = "Idle"
        else:
            actText = "Working"
        status_display = self.query_one(StatusDisplay)
        nice_status = status.replace('_', ' ').capitalize()
        status_display.update(Markdown(f'# Status\n{nice_status}\n{actText}\n\n{asktext}'))

    def on_mount(self) -> None:
        self.set_interval(0.1, self.update_rcstatus)
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
        yield TreeDisplay()

    async def update_rctree(self) -> None:
        async with httpx.AsyncClient() as client:
            r = await client.get(f'{self.hostname}/nanorcrest/tree', auth=auth)
        tree_data = r.json()
        if tree_data == "I'm busy!":
            return
        #Format is {'children': [...], 'name': 'foonode'} where the elements of children have the same structure
        importer = DictImporter()
        i_data = importer.import_(tree_data)
        the_text = Text("")
        for pre, _, node in RenderTree(i_data):
            the_line = Text("")
            working = True
            state_str = ''
            style = ''
            if node.errored:
                state_str += "ERROR - "
                style = 'bold red'
                working = False

            pathstring = ""
            for n in node.path:     #The path is provided as a tuple of nodes, with the parents first
                pathstring = pathstring + '.' + n.name

            async with httpx.AsyncClient() as client:       #Checks the state of each node
                fullpath = f'{self.hostname}/nanorcrest/node/' + pathstring
                r = await client.get(fullpath, auth=auth)
                node_data = r.json()

                if 'process_state' in node_data:    #Only app nodes have this one
                    if node_data['process_state'] != "alive":
                        state_str += f"{node_data['process_state']} - "
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
        '''The message that informs the log widget of a new entry'''
        def __init__(self, sender: MessageTarget, text:str) -> None:
            self.text = text
            super().__init__(sender)

    def __init__(self, hostname, **kwargs):
        super().__init__(**kwargs)
        self.hostname = hostname
        self.active = True

    def on_mount(self) -> None:
        self.set_interval(0.1, self.update_buttons)

    def compose(self) -> ComposeResult:
        yield TitleBox('Commands')
        yield Horizontal(id="box1", classes='horizontalbuttonscontainer')
        yield Horizontal(id="box2", classes='horizontalbuttonscontainer')

    async def update_buttons(self) -> None:
        async with httpx.AsyncClient() as client:
            r = await client.get(f'{self.hostname}/nanorcrest/command', auth=auth)
        data = r.json()
        if data == "I'm busy!":
            return
        self.commands = [key for key in data]   #Command is a dict of currently allowed commands and some associated data, this gets the keys

    def watch_commands(self, commands:list[str]) -> None:
        second_line = ["exclude", "include", "pin_threads"]
        box1 = self.query_one("#box1", Horizontal)  #Query using both id and class
        box2 = self.query_one("#box2", Horizontal)

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
            else:
                box1.mount(Button(c.replace('_', ' ').capitalize(), id=c, variant='primary'))
        #Generate 2nd line
        for c in self.commands:
            if c not in second_line:
                continue
            else:
                box2.mount(Button(c.replace('_', ' ').capitalize(), id=c, variant='primary'))
        box2.mount(Button('Quit', id='quit', variant='primary'))
        box2.mount(Button('Abort',variant='error', id='abort'))  #Abort button is red

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Event handler called when a button is pressed."""
        if self.active:
            button_id = event.button.id
            if button_id == 'abort':
                sys.exit(0)
            if button_id == 'quit':
                try:                                    #Try to shutdown
                    payload = {'command': button_id}
                    async with httpx.AsyncClient() as client:
                        r2 = await client.post(f'{self.hostname}/nanorcrest/command', auth=auth, data=payload, timeout=60)
                except:
                    sys.exit(0)                         #If it fails then close the TUI anyway
                sys.exit(0)                             #If it succeeds close the TUI

            #Get all allowed commands and their inputs
            async with httpx.AsyncClient() as client:
                r1 = await client.get(f'{self.hostname}/nanorcrest/command', auth=auth)

            data = r1.json()         #json has format {'boot': [{'timeout': {'default': None, 'required': False, 'type': 'INT'}}]}
            paramlist = data[button_id]
            mandatory = False
            for p in paramlist:
                for key in p:       #Should be just one of these
                    info = p[key]
                if info['required']:
                    mandatory = True
                    break
            self.active = False      #Deactivate until the command is completed
            for s in self.siblings:
                if isinstance(s, Status):
                    status_obj = s
                    break
            status_obj.receive_active_change(False)
            #The box must be shown if there are mandatory arguments. It also can be requested by pressing 'i' to switch modes.
            if mandatory or alwaysAsk:
                self.app.mount(InputWindow(hostname=self.hostname, command=button_id, id="pop_up"))
            else:
                payload = {'command': button_id}
                if 'timeout' in payload:    #Default timeout is 5s: not enough to boot!
                    #We add 5 to the timeout: if nanorc reaches the timeout, we want the request to have time to report back the error.
                    t = int(payload['timeout']) + 5
                else:
                    t = network_timeout     #We default to CLI timeout (+5)
                #Boot is being weird and taking longer than its timeout somehow, so we have cheated by disabling the read timeout
                if button_id == "boot":
                    async with httpx.AsyncClient() as client:
                        timeout = httpx.Timeout(t, read=None)
                        r2 = await client.post(f'{self.hostname}/nanorcrest/command', auth=auth, data=payload, timeout=timeout)
                else:
                    async with httpx.AsyncClient() as client:
                        r2 = await client.post(f'{self.hostname}/nanorcrest/command', auth=auth, data=payload, timeout=t)

                if "logs" in r2.json():
                    cmd_log = r2.json()['logs']                        #Other fields are "form" and "return_code"
                    self.post_message_no_wait(self.NewLog(self, cmd_log))   #Sends a message to the parent (the app)
                if "Exception" in r2.json():
                    raise ValueError(r2.json())
                self.active = True
                status_obj.receive_active_change(True)


    def receive_active_change(self, new_active:bool) -> None:
        self.active = new_active

class InputWindow(Widget):
    class NewLog(Message):
        '''The message that informs the log widget of a new entry'''
        def __init__(self, sender: MessageTarget, text:str) -> None:
            self.text = text
            super().__init__(sender)

    def __init__(self, hostname, command, **kwargs):
        super().__init__(**kwargs)
        self.command = command
        self.hostname = hostname

    def compose(self) -> ComposeResult:
        r = requests.get(f'{self.hostname}/nanorcrest/command', auth=auth)
        data = r.json()     #json has format {'boot': [{'timeout': {'default': None, 'required': False, 'type': 'INT'}}]}
        paramlist = data[self.command]
        self.params = {k:v for d in paramlist for k, v in d.items()}    #We turn the list of dicts into one dict for convenience

        button_list = []

        for k,v in self.params.items():
            if v['required']:
                b = Input(placeholder=k, id=k)
                b.styles.background = 'red'
                button_list.append(b)
            elif alwaysAsk:
                button_list.append(Input(placeholder=k, id=k))


        yield Vertical(
            *button_list,
            Horizontal(
                Button("Execute Command", id="go", variant='success'),
                Button('Cancel',variant='error', id='cancel'),
                classes = "horizontalbuttonscontainer"
            ),
            Static(id='errordisplay')
        )

    def validate_input(self, inputs):
        params_out = {}
        for i in inputs:
                if i.value == "":
                    if self.params[i.id]['required']:                           #We can't allow a required field to be empty!
                        return f"Required parameter \"{i.id}\" is missing!"     #The attempt at sending a command is over
                else:
                    #We enforce here that the string will be convertable to the appropriate type
                    match self.params[i.id]['type']:
                        case "STRING":
                            pass        #This is a valid input type, so it's included in case we need to do something later
                        case "INT":
                            if not i.value.isdigit():
                                return f"{i.value} is not a valid input for \"{i.id}\". Input should be an integer."
                        case "FLOAT":
                            try:
                                f = float(i.value)
                            except:
                                return f"{i.value} is not a valid input for \"{i.id}\". Input should be a float."
                        case "BOOL":
                            if (i.value.lower() != "true") and (i.value.lower() != "false"):
                                return f"{i.value} is not a valid input for \"{i.id}\". Input should be a boolean."
                        case _:
                            if "Choice" in self.params[i.id]['type']:
                                choices_as_str = self.params[i.id]['type'][7:-1]        #This gets the list part of "Choice([a,b,c,d])"
                                choices = eval(choices_as_str)                          #Turn the string into a real list
                                if i.value not in choices:
                                    return f"{i.value} is not a valid input for \"{i.id}\". Input should be one of the following: {choices_as_str}."
                    params_out[i.id] = i.value
        return params_out


    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        inputs = self.query(Input)
        #A list of all statics with the given id. There should only be one of these, so we get element 0
        errordisplay = [q for q in self.query(Static) if q.id == "errordisplay"][0]
        for s in self.app.query(Static):    #This gets all the children of the app, since they all inherit from static
                if isinstance(s, Status):
                    status_obj = s
                if isinstance(s, Command):
                    command_obj = s

        if button_id == "go":
            val_output = self.validate_input(inputs)
            if type(val_output) == str:                         #We got an error
                errordisplay.update(val_output)                 #Display it and stop
                return

            payload = {'command': self.command, **val_output}   #Otherwise, the function returned the parameters as a dict
            if self.command == "boot":
                boot_time = 55
            else:
                boot_time = 0
            if 'timeout' in payload:
                t = int(payload['timeout']) + 5 + boot_time
            else:
                t = network_timeout + boot_time

            async with httpx.AsyncClient() as client:
                r = await client.post(f'{self.hostname}/nanorcrest/command', auth=auth, data=payload, timeout=t)
            cmd_data = r.json()     #We put r.json() in a variable so we aren't converting from string to dict over and over

            if "logs" in cmd_data:
                cmd_log = cmd_data['logs']                      #Other fields are "form" and "return_code"
                self.emit_no_wait(self.NewLog(self, cmd_log))   #Sends a message to the parent (the app)
            if "Exception" in cmd_data:
                errordisplay.update(cmd_data['Exception'])
                return
            status_obj.receive_active_change(True)              #Turn commands back on, and tell status we are no longer working
            command_obj.receive_active_change(True)
            self.remove()

        if button_id == "cancel":
            status_obj.receive_active_change(True)
            command_obj.receive_active_change(True)
            self.remove()

from importlib import resources
import nanorc

class NanoRCTUI(App):
    CSS_PATH = resources.files(nanorc).joinpath('tui.css')
    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("i", "toggle_inputs", "Toggle expert mode")
    ]

    def __init__(self, host, rest_port, timeout, banner, **kwargs):
        super().__init__(**kwargs)

        self.mylog = logging.getLogger("NanoRCTUI")
        self.hostname = f'http://{host}:{rest_port}'
        global network_timeout
        network_timeout = timeout + 5

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
            RunInfo  (hostname = self.hostname, classes='container', id='runinfo'),
            Status   (hostname = self.hostname, classes='container', id='status'),
            Command  (hostname = self.hostname, classes='container', id='command'),
            TreeView (hostname = self.hostname, classes='container', id='tree'),
            Logs     (hostname = self.hostname, classes='container', id='log'),
            id = 'app-grid'
        )

        yield Header(show_clock=True)
        yield Footer()

if __name__ == "__main__":
    app = NanoRCTUI()
    app.run()
