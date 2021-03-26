# Nano RC

Poor's man Run Control for DUNE DAQ applications

## How to run me

This tutorial will guide you through the one-host minidaq example.

This tutorial assumes you run on a linux host with /cvmfs mounted, such as lxplus.

### Setup
First, pick a folder you really like and set up a build environment there as per instructions at
https://github.com/DUNE-DAQ/minidaqapp/wiki/Instructions-for-setting-up-a-v2.4.0-development-environment

The location of said folder should be set in the `DBT_AREA_ROOT` variable.  
```bash
$ export DBT_AREA_ROOT=??
```

Checkout the develop branch of daq-buildtools after finishing the build.

In case of trouble, you can use `build-daq.sh` as reference.

Now setup requirements for nanorc:
```bash
$ cd $DBT_AREA_ROOT
$ dbt-setup-runtime-environment
$ pip install -r <nanorc dir>/requirements.txt
```

### Running the NanoRC

Assuming you're running in the virtualenv created by the Setup section:
```bash
$ <nanorc dir>/nanorc.py examples/minidaqapp
                            Shonky RC                            
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ This is an admittedly shonky RC to run DUNE-DAQ applications. ┃
│ Use it wisely!                                                │
└───────────────────────────────────────────────────────────────┘
```

You have entered an interactive CLI. You can exit using CTRL-C.
```
shonky rc> help

Documented commands (type help <topic>):
========================================
boot  conf  init  pause  resume  scrap  start  status  stop  terminate  wait

Undocumented commands:
======================
exit  help  quit

shonky rc>
```

`boot` will start your applications
```
shonky rc> boot
{
    'env': {'DBT_ROOT': 'env', 'DBT_AREA_ROOT': 'env'},
    'hosts': {'ru_pc': 'lxplus7107', 'trg_pc': 'lxplus7107'},
    'apps': {'ruemu': {'exec': 'daq_application', 'host': 'ru_pc', 'port': 3333}, 'trgemu': {'exec': 'daq_application', 'host': 'trg_pc', 'port': 3334}}
}
⠇ # apps started ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   0% -:--:-- 0:00:05
⠇ ruemu          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   0% -:--:-- 0:00:05
⠇ trgemu         ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   0% -:--:-- 0:00:05
                             Apps                              
┏━━━━━━━━┳━━━━━━┳━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ name   ┃ host ┃ alive ┃ pings      ┃ last cmd ┃ last cmd ok ┃
┡━━━━━━━━╇━━━━━━╇━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ ruemu  │ True │ True  │ lxplus7107 │          │             │
│ trgemu │ True │ True  │ lxplus7107 │          │             │
└────────┴──────┴───────┴────────────┴──────────┴─────────────┘
```

You can then send the `init`, `conf`, `start`, and `resume` command.
Note that `start` requires a run number as argument.
```
shonky rc> resume
Sending resume to ruemu
{'id': 'resume', 'data': {}, 'entry_state': 'RUNNING', 'exit_state': 'RUNNING'}
Received reply from ruemu to resume
{'data': {'ans-host': '188.185.91.197', 'ans-port': '13333', 'cmdid': 'resume'}, 'result': 'OK', 'success': True}
Sending resume to trgemu
{'id': 'resume', 'data': {}, 'entry_state': 'RUNNING', 'exit_state': 'RUNNING'}
Received reply from trgemu to resume
{'data': {'ans-host': '188.185.91.197', 'ans-port': '13334', 'cmdid': 'resume'}, 'result': 'OK', 'success': True}
                             Apps                              
┏━━━━━━━━┳━━━━━━┳━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ name   ┃ host ┃ alive ┃ pings      ┃ last cmd ┃ last cmd ok ┃
┡━━━━━━━━╇━━━━━━╇━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ ruemu  │ True │ True  │ lxplus7107 │ resume   │ resume      │
│ trgemu │ True │ True  │ lxplus7107 │ resume   │ resume      │
└────────┴──────┴───────┴────────────┴──────────┴─────────────┘
shonky rc>
```

In case you experience timeout problems booting applications or sending commands, consider changing the `hosts` values
from `localhost` to the hostname of your machine. This has to do with SSH authentication.

### Viewing logs

Logs are kept in the working directory at the time you started the NanoRC cli.  
They are named `log_<name>_<port>.txt`.