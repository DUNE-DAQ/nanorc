import json
import os
import pytest
import subprocess
import tempfile

conf_types = ["normal", "top-json"]
exe_names = ["nanorc", "nanotimingrc"]
cmd_dict = {"nanorc": "boot conf start_run 111 wait 60 stop_run scrap terminate".split(),
            "nano04rc": "boot conf start_run TEST wait 60 stop_run scrap terminate".split(),
            "nanotimingrc": "boot conf start_run wait 60 stop_run scrap terminate".split()
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
    temp_dir_name = temp_dir_object.name                                        #Make a temp directory.
    os.popen(f'cp {start_dir}/my_dro_map.json {temp_dir_name}/my_dro_map.json') #Copy the DRO map inside.
    os.chdir(temp_dir_name)                                                     #Move into the temp dir.

    conf_name_1 = "test-conf"
    conf_name_2 = "extra-test-conf"
    DMG_args_1 = ["daqconf_multiru_gen", "-m", "my_dro_map.json", conf_name_1]
    DMG_args_2 = ["daqconf_multiru_gen", "-m", "my_dro_map.json", conf_name_2]
    subprocess.run(DMG_args_1)                                                  #Generate a config
    partition_name = f"test-partition-{conf_type}"

    match conf_type:
        case "normal":
            arglist = [exe_name, conf_name_1, partition_name] + commands

        case "top-json":        #Two duplicates of the regular config is enough to test that a top level json is functional
            subprocess.run(DMG_args_2)
            TJ_content = {"apparatus_id": "test", "sub1": conf_name_1, "sub2": conf_name_2}
            with open("top-level.json", "w") as outfile:
                json.dump(TJ_content, outfile)
            arglist = [exe_name, "top-level.json", partition_name] + commands

    output = subprocess.run(arglist)
    os.chdir(start_dir)
    return output.returncode

@pytest.mark.parametrize("exe_name", exe_names)
@pytest.mark.parametrize("conf_type", conf_types)
def test_no_errors(exe_name, conf_type):
    code = perform_all_runs(exe_name, conf_type)
    assert code == 0
