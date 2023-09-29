import json
import os
import pytest
import subprocess
import tempfile
from nanorc.integ_utils import get_default_config_dict, write_config, generate_dromap_contents

conf_types = ["no-db", "db"]
exe_names = ["nanorc", "nanotimingrc"]
cmd_dict = {
    "nanorc": "boot conf start_run 111 wait 5 stop_run scrap terminate".split(),
    "nano04rc": "boot conf start_run TEST wait 5 stop_run scrap terminate".split(),
    "nanotimingrc": "boot conf start_run wait 5 stop_run scrap terminate".split()
}
db_name = "integ-test-conf"
cluster_address = "k8s://np04-srv-015:31000"

def perform_all_runs(exe_name, conf_type):
    '''
    We generate a config using daqconf_multiru_gen, then run nanorc (on k8s) with and without uploading to the mongoDB.
    The error code of the process is used to determine whether everything worked.
    All processes are run in a temporary directory, so as not to fill up the CWD with logs.
    '''
    start_dir = os.getcwd()

    temp_dir_object = tempfile.TemporaryDirectory()
    temp_dir_name = temp_dir_object.name

    dro_file_name = f'{temp_dir_name}/dro.json'
    config_file_name_1 = f'{temp_dir_name}/conf1.json'

    with open(dro_file_name, 'w') as f:
        f.write(generate_dromap_contents(n_streams=2))

    config_data_1 = get_default_config_dict()
    config_data_1["boot"]["use_connectivity_service"] =  True
    config_data_1["boot"]["connectivity_service_host"] = "np04-srv-023"
    config_data_1["boot"]["connectivity_service_port"] = 30005
    config_data_1["boot"]["start_connectivity_service"] = False
    config_data_1["boot"]["process_manager"] = 'k8s'

    if exe_name in ['nanorc', 'nano04rc']:
        config_data_1["detector"]["op_env"] = "nanorc-integtest"
        config_data_1["daq_common"]["data_rate_slowdown_factor"] = 1
        config_data_1["detector"]["clock_speed_hz"] = 62500000 # DuneWIB/WIBEth
        config_data_1["readout"]["use_fake_cards"] = True

    elif exe_name == 'nanotimingrc':
        boot = config_data_1['boot']
        config_data_1 = {}
        config_data_1['boot'] = boot

    write_config(config_file_name_1, config_data_1)

    conf_basename = 'test-conf-1'
    conf_name_1 = f'{temp_dir_name}/{conf_basename}'
    DMG_args_1 = []

    if exe_name in ['nanorc', 'nano04rc']:
        DMG_args_1 = ["fddaqconf_gen", "-c", config_file_name_1, "-m", dro_file_name, conf_name_1]

    elif exe_name == 'nanotimingrc':
        DMG_args_1 = ["listrev_gen", "-c", config_file_name_1, conf_name_1]

    try:
        subprocess.run(DMG_args_1)
    except Exception as e:
        pytest.fail(reason=str(e))

    partition_name = f"test-partition-{conf_type}"
    commands = cmd_dict[exe_name]
    arglist = []
    match conf_type:
        case "no-db":
            arglist = [exe_name, "--pm", cluster_address, conf_name_1, partition_name] + commands

        case "db":      #We upload the config to the database first
            upload_args = ["upload-conf", conf_name_1, db_name]
            subprocess.run(upload_args)
            arglist = [exe_name, "--pm", cluster_address, f"db://{db_name}", partition_name] + commands

    output = subprocess.run(arglist)
    os.chdir(start_dir)
    return output.returncode

@pytest.mark.parametrize("exe_name", exe_names)
@pytest.mark.parametrize("conf_type", conf_types)
def test_no_errors(exe_name, conf_type):
    code = perform_all_runs(exe_name, conf_type)
    assert code == 0
