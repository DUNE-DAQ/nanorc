# Nano RC (Not ANOther Run Control)

Poor man's Run Control for DUNE DAQ applications

## How to run me

This tutorial will guide you through the one-host minidaq example.

This tutorial assumes you run on a linux host with /cvmfs mounted, such as lxplus at CERN.

### Setup

First, set up a working area according to [the daq-buildtools instructions](https://dune-daq-sw.readthedocs.io/en/latest/packages/daq-buildtools/).

Get the example data file:

```bash
curl -o frames.bin -O https://cernbox.cern.ch/index.php/s/0XzhExSIMQJUsp0/download
```

Generate a configuration:

```bash 
daqconf_multiru_gen fake_daq
```

Next (if you want to), you can create a file called `top_level.json` which contains:

```json
{
  "apparatus_id": "fake_daq",
  "minidaq": "fake_daq"
}
```

Now you're ready to run.

### Running the NanoRC

To see a list of options you can pass nanorc in order to control things such as the amount of information it prints and the timeouts for transitions, run `nanorc -h`. We'll skip those for now in the following demo:
```
nanorc top_level.json partition-name# or "nanorc fake_daq partition-name" if you didn't create the top_level.json

╭──────────────────────────────────────────────────────────────────────────╮
│                              Shonky NanoRC                               │
│  This is an admittedly shonky nanp RC to control DUNE-DAQ applications.  │
│    Give it a command and it will do your biddings,                       │
│    but trust it and it will betray you!                                  │
│  Use it with care!                                                       │
╰──────────────────────────────────────────────────────────────────────────╯

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

`boot` will start your applications. In the case of the example, a trigger application to supply triggers, a hardware signal interface (HSI) application, and a readout and dataflow application which receives the triggers.
```
shonky rc> boot

  # apps started ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00 0:00:02
  dataflow       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00 0:00:02
  hsi            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00 0:00:02
  ruemu0         ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00 0:00:01
  trigger        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00 0:00:02
                                Apps                                
┏━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ name     ┃ host      ┃ alive ┃ pings ┃ last cmd ┃ last succ. cmd ┃
┡━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ dataflow │ mu2edaq13 │ True  │ True  │ None     │ None           │
│ hsi      │ mu2edaq13 │ True  │ True  │ None     │ None           │
│ ruemu0   │ mu2edaq13 │ True  │ True  │ None     │ None           │
│ trigger  │ mu2edaq13 │ True  │ True  │ None     │ None           │
└──────────┴───────────┴───────┴───────┴──────────┴────────────────┘

```

You can then send the `init`, `conf`, `start`, and `resume` commands to get things going. `start` requires a run number as argument. It also optionally takes booleans to toggle data storage (`--disable-data-storage` and `--enable-data-storage`) and an integer to control trigger separation in ticks (`--trigger-interval-ticks <num ticks>`).

The commands produce quite verbose output so that you can see what was sent directly to the applications without digging in the logfiles.

Triggers will not be generated until after a resume command is issued, and then trigger records with 2 links each at a default of 1 Hz will be generated.

Use 'status' to see what's going on:

```
shonky rc> status
                                    Apps                                     
┏━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ name     ┃ host      ┃ alive ┃ pings ┃ last cmd ┃ last succ. cmd ┃
┡━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ dataflow │ mu2edaq13 │ True  │ True  │ None     │ None           │
│ hsi      │ mu2edaq13 │ True  │ True  │ None     │ None           │
│ ruemu0   │ mu2edaq13 │ True  │ True  │ None     │ None           │
│ trigger  │ mu2edaq13 │ True  │ True  │ None     │ None           │
└──────────┴───────────┴───────┴───────┴──────────┴────────────────┘
```

When you've seen enough use `stop`, `scrap` and `terminate` commands. In case you experience timeout problems booting applications or sending commands, consider changing the `hosts` values from `localhost` to the hostname of your machine. This has to do with SSH authentication.

nanorc commands can be autocompleted with TAB, for example, TAB will autocomplete `r` to `resume`. Options like `--disable-data-storage` will be completed with TAB after typing `start --d`.

You can also control nanorc in "batch mode", e.g.:
```
run_number=999
nanorc mdapp_fake partition-name boot init conf start --disable-data-storage $run_number wait 2 resume wait 60 pause wait 2 stop scrap terminate
```
Notice the ability to control the time via transitions from the command line via the `wait` argument. 

### Viewing logs and output

Logs are kept in the working directory at the time you started nanorc, named `log_<application name>_<port>.txt`.

You can peek at the output hdf5 file using:

```bash
h5dump -H swtest_run000666_0000_tapper_20210513T133527.hdf5
```
(your file will be named something else, of course).

For TriggerRecordHeaders:

```bash
python3 $DFMODULES_FQ_DIR/dfmodules/bin/hdf5dump/hdf5_dump.py -p trigger -f swtest_run000666_0000_tapper_20210513T133527.hdf5
```
For FragmentHeaders:
```bash
python3 $DFMODULES_FQ_DIR/dfmodules/bin/hdf5dump/hdf5_dump.py -p fragment swtest_run000666_0000_tapper_20210513T133527.hdf5
```

## More on boot

It can be instructive to take a closer look at how we can tell nanorc to `boot` the DAQ's applications. Let's take a look at a relatively simple example file in the nanorc repo, `examples/mdapp_fake/boot.json`:
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

## How to run WebUI

To access the WebUI, add the --web option when running nanorc. When nanorc starts up, it will display a box which shows what lxplus node to connect to.
[node image](https://jonathanhancock0.github.io/img/node.png)
Before you can connect, a SOCKS proxy must be set up to that node in another termainal window, using `ssh -N -D 8080 username@lxplusXXXX.cern.ch` and substituting XXXX with whatever number is shown.
Once you have set up your browser to use a SOCKS proxy, connect to the address in the browser, and you should see something like this.
[GUI image](https://jonathanhancock0.github.io/img/GUI.png)
From here, using nanorc is just about the same: transitions between FSM states can be done using the State Control Buttons, and the information that nanorc outputs can be viewed by clicking the triangle under "Last response from nanorc".
Note that this information will still be output to the terminal.  
