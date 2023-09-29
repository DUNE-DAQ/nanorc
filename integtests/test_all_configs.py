import json
import os
import pytest
import subprocess
import tempfile
from nanorc.integ_utils import get_default_config_dict, write_config, generate_dromap_contents, log_has_no_errors, logs_are_error_free, get_a_port_with_500_consecutive_ports_open

conf_types = ["normal", "top-json"]
exe_names = ["nanorc", "nanotimingrc"]
#exe_names = ["nanotimingrc"]
cmd_dict = {
    "nanorc": "boot conf conf start_run 111 wait 5 stop_run scrap terminate".split(),
    "nano04rc": "boot conf start_run TEST wait 5 stop_run scrap terminate".split(),
    "nanotimingrc": "boot conf start_run wait 5 stop_run scrap terminate".split()
}

def perform_all_runs(exe_name, conf_type):
    '''
    We generate a config using daqconf_multiru_gen, then run nanorc with it in two different ways.
    The error code of the process is used to determine whether everything worked.
    All processes are run in a temporary directory, so as not to fill up the CWD with logs.
    '''
    commands = cmd_dict[exe_name]
    start_dir = os.getcwd()

    temp_dir_object = tempfile.TemporaryDirectory()
    temp_dir_name = temp_dir_object.name                                            # Make a temp directory.

    dro_file_name = f'{temp_dir_name}/dro.json'
    config_file_name_1 = f'{temp_dir_name}/conf1.json'
    config_file_name_2 = f'{temp_dir_name}/conf2.json'

    with open(dro_file_name, 'w') as f:
        f.write(generate_dromap_contents(n_streams=2))


    port1 = get_a_port_with_500_consecutive_ports_open()
    config_data_1 = get_default_config_dict()
    config_data_1["boot"]["base_command_port"] = port1+1
    config_data_1["boot"]["connectivity_service_port"] = port1
    if exe_name in ['nanorc', 'nano04rc']:
        config_data_1["detector"]["op_env"] = "nanorc-integtest"
        config_data_1["daq_common"]["data_rate_slowdown_factor"] = 1
        config_data_1["detector"]["clock_speed_hz"] = 62500000 # DuneWIB/WIBEth
        config_data_1["readout"]["use_fake_cards"] = True
    else:
        boot = config_data_1['boot']
        config_data_1 = {}
        config_data_1['boot'] = boot

    write_config(config_file_name_1, config_data_1)

    from copy import deepcopy as dc
    config_data_2 = dc(config_data_1)
    config_data_2["boot"]["base_command_port"] = port1+1
    config_data_2["boot"]["connectivity_service_port"] = port1

    write_config(config_file_name_2, config_data_2)

    conf_name_1 = f'{temp_dir_name}/test-conf-1'
    conf_name_2 = f'{temp_dir_name}/test-conf-2'
    top_level = f'{temp_dir_name}/top-level.json'

    DMG_args_1 = []
    DMG_args_2 = []
    if exe_name in ['nanorc', 'nano04rc']:
        DMG_args_1 = ["fddaqconf_gen","-c", config_file_name_1, "-m", dro_file_name, conf_name_1]
        DMG_args_2 = ["fddaqconf_gen","-c", config_file_name_2, "-m", dro_file_name, conf_name_2]
    else:
        DMG_args_1 = ["listrev_gen","-c", config_file_name_1, conf_name_1]
        DMG_args_2 = ["listrev_gen","-c", config_file_name_2, conf_name_2]

    try:
        subprocess.run(DMG_args_1)
    except Exception as e:
        pytest.fail(reason=str(e))


    partition_name = f"test-partition-{conf_type}"

    match conf_type:
        case "normal":
            arglist = [exe_name, conf_name_1, partition_name] + commands

        case "top-json":        #Two duplicates of the regular config is enough to test that a top level json is functional
            subprocess.run(DMG_args_2)

            TJ_content = {
                "apparatus_id": "test",
                "sub1": conf_name_1,
                "sub2": conf_name_2
            }

            with open(top_level, "w") as outfile:
                json.dump(TJ_content, outfile)

            arglist = [exe_name, top_level, partition_name] + commands

    os.chdir(temp_dir_name)
    output = subprocess.run(arglist)
    os.chdir(start_dir)
    return output.returncode

@pytest.mark.parametrize("exe_name", exe_names)
@pytest.mark.parametrize("conf_type", conf_types)
def test_no_errors(exe_name, conf_type):
    code = perform_all_runs(exe_name, conf_type)
    assert code == 0
