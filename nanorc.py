#!/usr/bin/env python

import os
import sh
import sys
import socket
import time
import json

from sshpm import SSHProcessManager

boot_json='''
{
    "env" : {
        "DBT_ROOT": "env",
        "DBT_AREA_ROOT": "env"
    },
    "apps" : {
        "stoca" : {
            "exec": "daq_application",
            "host": "localhost",
            "port": 12345
        },
        "suka": {
            "exec": "daq_application",
            "host": "localhost",
            "port": 12346
        }
    }
}
'''

boot = json.loads(boot_json)

print(boot)


pm = SSHProcessManager()
pm.spawn(boot)

time.sleep(25)
pm.terminate()
raise SystemExit(0)


p.terminate()

