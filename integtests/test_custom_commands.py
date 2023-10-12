import json
import os
import pytest
import subprocess
import tempfile
from nanorc.integ_utils import get_default_config_dict, write_config, generate_dromap_contents

custom_commands_json = {
    "random":
        {
            "modules": [
                {
                    "data": {
                        "some_number": 123,
                        "pi": 3.14,
                        "lore-ipsum": "Nanorc fluctuat nec mergitur"
                    },
                    "match": "*"
                }
            ]
        },
    "record":
        {
            "modules": [
                {
                    "data": {
                        "duration": 2,
                    },
                    "match": "datahandler_100"
                }
            ]
        }
}


conf_types = ["normal"]#, "k8s"]
exe_names = ["nanorc", "nanotimingrc"]

use_args = [False, True]
cluster_address = "k8s://np04-srv-016:31000"

def insert_json(config_name, app_names, command_name, command_data):
    for app_name in app_names:
        with open(f'{config_name}/data/{app_name}_{command_name}.json', 'w') as json_file:
            json.dump(command_data, json_file)

def perform_all_runs(exe_name, conf_type, custom_command, with_args):
    '''
    We generate a config using fddaqconf_gen, then run nanorc with it in two different ways.
    The error code of the process is used to determine whether everything worked.
    All processes are run in a temporary directory, so as not to fill up the CWD with logs.
    '''
    start_dir = os.getcwd()

    temp_dir_object = tempfile.TemporaryDirectory()
    temp_dir_name = temp_dir_object.name                                        #Make a temp directory.

    dro_file_name = f'{temp_dir_name}/dro.json'
    config_file_name_1 = f'{temp_dir_name}/conf1.json'

    with open(dro_file_name, 'w') as f:
        f.write(generate_dromap_contents(n_streams=2))

    config_data_1 = get_default_config_dict()
    config_data_1["boot"]["use_connectivity_service"] =  True
    config_data_1["boot"]["connectivity_service_host"] = "np04-srv-023"
    config_data_1["boot"]["connectivity_service_port"] = 30005
    config_data_1["boot"]["start_connectivity_service"] = False

    if exe_name in ['nanorc', 'nano04rc']:
        config_data_1["detector"]["op_env"] = "nanorc-integtest"
        config_data_1["daq_common"]["data_rate_slowdown_factor"] = 1
        config_data_1["detector"]["clock_speed_hz"] = 62500000 # DuneWIB/WIBEth
        config_data_1["readout"]["use_fake_cards"] = True

    elif exe_name == 'nanotimingrc':
        boot = config_data_1['boot']
        config_data_1 = {}
        config_data_1['boot'] = boot

    if conf_type == 'k8s':
        config_data_1["boot"]["process_manager"] = 'k8s'

    write_config(config_file_name_1, config_data_1)

    conf_name_1 = f'{temp_dir_name}/test-conf-1'

    DMG_args_1 = []
    app_names = []

    if exe_name in ['nanorc', 'nano04rc']:
        DMG_args_1 = ["fddaqconf_gen","-c", config_file_name_1, "-m", dro_file_name, conf_name_1]
        app_names = ['rulocalhosteth0'] if custom_command == "record" else ['dfo', 'trigger']

    elif exe_name == 'nanotimingrc':
        DMG_args_1 = ["listrev_gen","-c", config_file_name_1, conf_name_1]
        app_names = ['listrev-app-s']

    try:
        subprocess.run(DMG_args_1)
    except Exception as e:
        pytest.fail(msg=str(e))

    partition_name = f"test-partition-{conf_type}"
    insert_json(
        config_name = conf_name_1,
        app_names = app_names,
        command_name = custom_command,
        command_data = custom_commands_json[custom_command],
    )
    #insert_json(config_name, app_name, command_name, command_data):
    commands = f"boot conf {custom_command}".split()
    if with_args:
        commands += ['--duration', '3'] if custom_command == 'record' else ['--some-number', '3', '--pi', '6.2', '--lore-ipsum', 'alea jacta est']

    arglist = []
    if conf_type == "normal":
        arglist = [exe_name, conf_name_1, partition_name] + commands

    elif conf_type == "k8s":
        arglist = [exe_name, "--pm", cluster_address, conf_name_1, partition_name] + commands

    os.chdir(temp_dir_name)
    output = subprocess.run(arglist)
    os.chdir(start_dir)
    return output.returncode

@pytest.mark.parametrize("exe_name", exe_names)
@pytest.mark.parametrize("conf_type", conf_types)
@pytest.mark.parametrize("custom_command", custom_commands_json.keys())
@pytest.mark.parametrize("with_args", use_args)
def test_no_errors(exe_name, conf_type, custom_command, with_args):
    code = perform_all_runs(exe_name, conf_type, custom_command, with_args)
    assert code == 0
