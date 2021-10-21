from anytree import NodeMixin
import time
from datetime import datetime

import logging
from .sshpm import SSHProcessManager
from .appctrl import AppSupervisor, ResponseListener, ResponseTimeout, NoResponse
from typing import Union, NoReturn

# This one is just to give a nicer name
class GroupNode(NodeMixin):
    def __init__(self, name:str, parent=None, children=None):
        self.name = name
        self.parent = parent
        self.log = logging.getLogger(self.__class__.__name__+"_"+self.name)
        if children:
            self.children = children

    def send_command(self, cmd:str,
                     state_entry:str, state_exit:str,
                     cfg_method:str=None, overwrite_data:dict={},
                     timeout:int=None) -> tuple:
        self.log.debug(f"Sending {cmd} to {self.name}")

        if not self.children:
            return

        ok, failed = {},{}

        for child in self.children:
            o, f = child.send_command(cmd=cmd,
                                      state_entry = state_entry, state_exit = state_exit,
                                      cfg_method = cfg_method, overwrite_data = overwrite_data,
                                      timeout = timeout)
            ok.update(o)
            failed.update(f)

        return (ok, failed)

    def terminate(self)-> NoReturn:
        self.log.debug(f"Sending terminate to {self.name}")
        if not self.children:
            return

        for child in self.children:
            child.terminate()

    def boot(self) -> NoReturn:
        self.log.debug(f"Sending boot to {self.name}")

        if not self.children:
            return

        for child in self.children:
            child.boot()

# Now on to useful stuff
class ApplicationNode(NodeMixin):
    def __init__(self, name, sup, parent=None):
        self.name = name
        self.sup = sup
        self.parent = parent
        # Absolutely no children for applicationnode



class SubsystemNode(NodeMixin):
    def __init__(self, name:str, cfgmgr, console, parent=None, children=None):
        self.name = name
        self.cfgmgr = cfgmgr
        self.pm = None
        self.listener = None
        self.parent = parent
        self.console = console
        self.log = logging.getLogger(self.__class__.__name__+"_"+self.name)
        if children:
            self.children = children

    def boot(self) -> NoReturn:
        self.log.debug(f"Sending boot to {self.name}")
        try:
            self.pm = SSHProcessManager(self.console)
            self.pm.boot(self.cfgmgr.boot)
        except Exception as e:
            self.console.print_exception()
            self.return_code = 11
            return

        self.listener = ResponseListener(self.cfgmgr.boot["response_listener"]["port"])
        children = [ ApplicationNode(name=n,
                                     sup=AppSupervisor(self.console, d, self.listener),
                                     parent=self)
                     for n,d in self.pm.apps.items() ]
        self.children = children

    def terminate(self) -> NoReturn:
        if self.children:
            for child in self.children:
                child.sup.terminate()
                if child.parent.listener:
                    child.parent.listener.unregister(child.name)
                child.parent = None

        if self.listener:
            self.listener.terminate()
        if self.pm:
            self.pm.terminate()


    def send_command(self, cmd:str,
                     state_entry:str, state_exit:str,
                     cfg_method:str=None, overwrite_data:dict={},
                     timeout:int=None) -> tuple:
        self.log.debug(f"Sending {cmd} to {self.name}")

        sequence = getattr(self.cfgmgr, cmd+'_order', None)

        appset = list(self.children)
        ok, failed = {}, {}

        if not sequence:
            # Loop over data keys if no sequence is specified or all apps, if data is empty

            for n in appset:
                # BERK I don't know how to sort this.
                # This is essntially calling cfgmgr.runtime_start(runtime_start_data)
                if cfg_method:
                    f=getattr(self.cfgmgr,cfg_method)
                    data = f(overwrite_data)
                else:
                    data = getattr(self.cfgmgr, cmd)

                n.sup.send_command(cmd, data[n.name] if data else {}, state_entry, state_exit)

            start = datetime.now()

            while(appset):
                done = []
                for n in appset:
                    try:
                        r = n.sup.check_response()
                    except NoResponse:
                        continue

                    done += [n]

                    (ok if r['success'] else failed)[n.name] = r

                for d in done:
                    appset.remove(d)

                now = datetime.now()
                elapsed = (now - start).total_seconds()

                if elapsed > timeout:
                    raise RuntimeError("Send multicommand failed")

                time.sleep(0.1)
                self.log.debug("tic toc")

        else:
            # There probably is a way to do that in a much nicer, pythonesque, way
            for n in sequence:
                for child_node in appset:
                    if n == child_node.name:
                        if cfg_method:
                            f=getattr(self.cfgmgr,cfg_method)
                            data = f(overwrite_data)
                        else:
                            data = getattr(self.cfgmgr, cmd)
                        r = child_node.sup.send_command_and_wait(cmd, data[n] if data else {},
                                                                 state_entry, state_exit, timeout)
                        (ok if r['success'] else failed)[n] = r


        return (ok, failed)

