#!/usr/bin/env python

import os
import sh
import sys
import socket
import time
import json
import atexit
import signal

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

print(boot)


pm = SSHProcessManager()

# Cleanup before exiting
def __goodbye():
    print("Killing all processes before exiting")
    pm.terminate()

atexit.register(__goodbye)
signal.signal(signal.SIGTERM, __goodbye)
signal.signal(signal.SIGINT, __goodbye)
# ---

pm.spawn(boot)



dac = DAQAppController(pm.apps, 'examples/')

for i in range(15):
    time.sleep(1)
    print(f'Elapsed {i}s')
pm.terminate()
raise SystemExit(0)


p.terminate()



