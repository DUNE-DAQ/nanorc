#!/usr/bin/env python

import os
import sh
import sys
import socket
import time
import json
import cmd
from rich.console import Console
from rich.pretty import Pretty


from sshpm import SSHProcessManager
from daqctrl import DAQAppController

boot_json='''
{
    "env" : {
        "DBT_ROOT": "env",
        "DBT_AREA_ROOT": "env"
    },
    "hosts": {
        "my_pc": "localhost"
    },
    "apps" : {
        "stoca" : {
            "exec": "daq_application",
            "host": "my_pc",
            "port": 12345
        },
        "suka": {
            "exec": "daq_application",
            "host": "my_pc",
            "port": 12346
        }
    }
}
'''


init_json = '''{
    'stoca': 'listrev_init',
    'suka': 'listrev_init'
}'''

conf_json = '''
    'stoca': 'listrev_conf',
    'suka': 'listrev_conf'
'''

boot = json.loads(boot_json)


class NanoRC:
    """docstring for NanoRC"""
    def __init__(self, console: Console):
        super(NanoRC, self).__init__()     
        self.console = console

        self.pm = SSHProcessManager(console)


class NanoRCShell(cmd.Cmd):
    """A Poor's man RC"""
    prompt = 'rc> '
    def __init__(self, console: Console, rc: NanoRC):
        super(NanoRCShell, self).__init__()
        self.rc = rc
        self.console = console

    def do_create(self, arg: str):
        self.console.print(Pretty(boot))

        self.rc.pm.spawn(boot)

    def do_destroy(self, arg: str):
        self.rc.pm.terminate()

    def do_exit(self, arg: str):
        self.rc.pm.terminate()
        return True
        

def main():



    pm = SSHProcessManager()


    pm.spawn(boot)



    dac = DAQAppController(pm.apps, 'examples/')

    for i in range(30):
        time.sleep(1)
        print(f'Elapsed {i}s')
    pm.terminate()
    raise SystemExit(0)

    p.terminate()

if __name__ == '__main__':
    # try:
    #     main()
    # except KeyboardInterrupt:
    #     # pass
    #     SSHProcessManager.kill_all_instances()
    # finally:
        # exit_gracefully()_name__ == '__main__':

    console = Console()
    rc = NanoRC(console)
    NanoRCShell(console, rc).cmdloop()





