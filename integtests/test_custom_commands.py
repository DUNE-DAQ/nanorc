import json
import os
import pytest
import subprocess
import tempfile
from nanorc.integ_utils import get_default_config_dict, write_config, generate_dromap_contents

app_name = "trigger"
command_name = "record"

custom_command1 = {
    "apps": {
        app_name: f"data/{app_name}_{command_name}"
    }
}
custom_command2 = {
    "modules": [{"data": {}, "match": "*"}]
}

conf_types = ["normal", "k8s"]
exe_names = ["nanorc", "nanotimingrc"]

commands = f"boot conf {command_name}".split()

cluster_address = "k8s://np04-srv-015:31000"

def insert_json(conf_name_1):
    with open(f'{conf_name_1}/{command_name}.json', 'w') as f:
        json.dump({
            "apps": {
                app_name: f"data/{app_name}_{command_name}"
            }
        },
        f)
    with open(f'{conf_name_1}/data/{app_name}_{command_name}.json', 'w') as json_file2:
        json.dump(custom_command2, json_file2)


def perform_all_runs(exe_name, conf_type):
    '''
    We generate a config using fddaqconf_gen, then run nanorc with it in two different ways.
    The error code of the process is used to determine whether everything worked.
    All processes are run in a temporary directory, so as not to fill up the CWD with logs.
    '''
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

    if exe_name in ['nanorc', 'nano04rc']:
        DMG_args_1 = ["fddaqconf_gen","-c", config_file_name_1, "-m", dro_file_name, conf_name_1]

    elif exe_name == 'nanotimingrc':
        DMG_args_1 = ["listrev_gen","-c", config_file_name_1, conf_name_1]

    subprocess.run(DMG_args_1)

    partition_name = f"test-partition-{conf_type}"
    insert_json(conf_name_1)

    arglist = []
    if conf_type == "normal":
        arglist = [exe_name, conf_name_1, partition_name] + commands

    elif conf_type == "k8s":
        arglist = [exe_name, "--pm", cluster_address, conf_name_1, partition_name] + commands

    output = subprocess.run(arglist)
    return output.returncode

@pytest.mark.parametrize("exe_name", exe_names)
@pytest.mark.parametrize("conf_type", conf_types)
def test_no_errors(exe_name, conf_type):
    code = perform_all_runs(exe_name, conf_type)
    assert code == 0
