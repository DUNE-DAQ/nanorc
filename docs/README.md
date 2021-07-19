# Nano RC (Not ANOther Run Control)

Poor man's Run Control for DUNE DAQ applications

## How to run me

This tutorial will guide you through the one-host minidaq example.

This tutorial assumes you run on a linux host with /cvmfs mounted, such as lxplus at CERN.

### Setup

First, set up a working area according to [the daq-buildtools instructions](https://dune-daq-sw.readthedocs.io/en/latest/packages/daq-buildtools/).

Next, install nanorc:

```bash
pip install https://github.com/DUNE-DAQ/nanorc/archive/refs/tags/<tag/branch>.tar.gz
```
Get the example data file:

```bash
curl https://cernbox.cern.ch/index.php/s/VAqNtn7bwuQtff3/download -o frames.bin
```

Generate a configuration:

```bash 
python -m minidaqapp.nanorc.mdapp_multiru_gen mdapp_fake
```

Now you're ready to run.

### Running the NanoRC

In the `nanorc-demo` directory:

```
./nanorc/nanorc.py mdapp_fake

                            Shonky NanoRC                             
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ This is an admittedly shonky tiny RC to run DUNE-DAQ applications. ┃
│   Give it a command and it will do your biddings,                  │
│   but trust it and it will betray you!                             │
│ Handle wiht care!                                                  │
└────────────────────────────────────────────────────────────────────┘
shonky rc> 
```
To see the commands available use `help`.

```
shonky rc> help

Documented commands (type help <topic>):
========================================
boot  conf  init  pause  resume  scrap  start  status  stop  terminate  wait

Undocumented commands:
======================
exit  help  quit
```

`boot` will start your applications. In the case of the example, a trigger emulator application to supply triggers and a readout and dataflow application which receives the triggers.
```
shonky rc> boot
          {                                                                                                                                                 
               'apps': {                                                                                                                                               
                   'ruemu_df': {'exec': 'daq_application', 'host': 'host_rudf', 'port': 3334},                                                                      
                   'trgemu': {'exec': 'daq_application', 'host': 'host_trg', 'port': 3333}                                                                         
               },                                                                                                                                                 
               'env': {'DBT_AREA_ROOT': 'env', 'DBT_ROOT': 'env'},                                                                                                    
               'hosts': {'host_rudf': 'lxplus7102.cern.ch', 'host_trg': 'lxplus7102.cern.ch'}                                                              
           }                                                                                                                                                           
⠹ # apps started ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   0% -:--:-- 0:00:16
⠹ ruemu_df       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   0% -:--:-- 0:00:16
⠹ trgemu         ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   0% -:--:-- 0:00:16
                                    Apps                                     
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ name     ┃ host               ┃ alive ┃ pings ┃ last cmd ┃ last succ. cmd ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ ruemu_df │ lxplus7102.cern.ch │ True  │ True  │ None     │ None           │
│ trgemu   │ lxplus7102.cern.ch │ True  │ True  │ None     │ None           │
└──────────┴────────────────────┴───────┴───────┴──────────┴────────────────┘
```

You can then send the `init`, `conf`, `start`, and `resume` commands to get things going. Note that `start` requires a run number as argument. The commands produce quite verbose output so that you can see what was sent directly to the applications without digging in the logfiles.

Triggers will not be generated until after a resume command is issued, and then trigger records with 2 links each at 1 Hz will be generated.

Use 'status' to see what's going on:

```
shonky rc> status
                                    Apps                                     
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ name     ┃ host               ┃ alive ┃ pings ┃ last cmd ┃ last succ. cmd ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ ruemu_df │ lxplus7102.cern.ch │ True  │ True  │ start    │ start          │
│ trgemu   │ lxplus7102.cern.ch │ True  │ True  │ resume   │ resume         │
└──────────┴────────────────────┴───────┴───────┴──────────┴────────────────┘
```

When you've seen enough use `stop`, `scrap` and `terminate` commands. In case you experience timeout problems booting applications or sending commands, consider changing the `hosts` values from `localhost` to the hostname of your machine. This has to do with SSH authentication.

### Viewing logs and output

Logs are kept in the working directory at the time you started nanorc, named `log_<name>_<port>.txt`.

You can peak in the output hdf5 file using:

```bash
h5dump -H swtest_run000666_0000_tapper_20210513T133527.hdf5
```
(your file will be named something else of course).

For TriggerRecordHeaders:

```bash
python3 $DFMODULES_FQ_DIR/dfmodules/bin/hdf5dump/hdf5_dump.py -TRH -f swtest_run000666_0000_tapper_20210513T133527.hdf5
```
For FragmentHeaders:
```bash
python3 $DFMODULES_FQ_DIR/dfmodules/bin/hdf5dump/hdf5_dump.py -H -f swtest_run000666_0000_tapper_20210513T133527.hdf5
```

## More on boot

It can be instructive to take a closer look at how we can tell nanorc to `boot` the DAQ's applications. Let's take a look at a relatively simple example file, `examples/mdapp_fake/boot.json`:
```
{
    "apps": {
        "ruemu_df": {
            "exec": "daq_application",
            "host": "host_rudf",
            "port": 3334
        },
        "trgemu": {
            "exec": "daq_application",
            "host": "host_trg",
            "port": 3333
        }
    },
    "response_listener": {
        "port": 56789
    },
    "env": {
        "DUNEDAQ_ERS_VERBOSITY_LEVEL": 1
    },
    "hosts": {
        "host_rudf": "localhost",
        "host_trg": "localhost"
    },
    "exec": {
        "daq_application_ups" : {
            "comment": "Application profile using dbt-setup to setup environment",
            "env": {
               "DBT_AREA_ROOT": "getenv"
            },
            "cmd": [
                "CMD_FAC=rest://localhost:${APP_PORT}",
                "INFO_SVC=file://info_${APP_ID}_${APP_PORT}.json",
                "cd ${DBT_AREA_ROOT}",
                "source dbt-setup-env.sh",
                "dbt-setup-runtime-environment",
                "cd ${APP_WD}",
                "daq_application --name ${APP_ID} -c ${CMD_FAC} -i ${INFO_SVC}"
            ]
        },
        "daq_application" : {
            "comment": "Application profile using basic PATH variables (more efficient)",
            "env":{
                "CET_PLUGIN_PATH": "getenv",
                "DUNEDAQ_SHARE_PATH": "getenv",
                "LD_LIBRARY_PATH": "getenv",
                "PATH": "getenv",
                "TRACE_FILE": "getenv:/tmp/trace_buffer_${HOSTNAME}_${USER}"
            },
            "cmd": [
                "CMD_FAC=rest://localhost:${APP_PORT}",
                "INFO_SVC=file://info_${APP_NAME}_${APP_PORT}.json",
                "cd ${APP_WD}",
                "daq_application --name ${APP_NAME} -c ${CMD_FAC} -i ${INFO_SVC}"
            ]
        }
    }
}
```
...you'll notice a few features about it which are common to boot files. Looking at the highest-level keys:

* `apps` contains the definition of what applications will run, and what sockets they'll be controlled on
* `env` contains a list of environment variables which can control the applications
* `hosts` is the cheatsheet whereby `apps` maps the labels of hosts to their actual names
* `exec` defines the exact procedure by which an application will be launched

It should be pointed out that some substitutions are made when nanorc uses a file such as this to boot the processes. Specifically:

* `"getenv"` is replaced with the actual value of the environment variable, throwing a Python exception if it is unset
* `"getenv:<default value>"` is replaced with the actual value of the environment variable if it is set, with `<default value>` used if it is unset
* If a host is provided as `localhost` or `127.0.0.1`, the result of the Python call `socket.gethostname` is used in its place
