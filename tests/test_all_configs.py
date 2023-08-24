import json
import os
import pytest
import subprocess
import tempfile

conf_types = ["normal", "top-json"]
commands = "boot conf start_run 111 wait 60 stop_run scrap terminate".split()

@pytest.fixture(params = conf_types)
def perform_all_runs(request):
    '''
    We generate a config using daqconf_multiru_gen, then run nanorc with it in two different ways.
    The error code of the process is used to determine whether everything worked.
    All processes are run in a temporary directory, so as not to fill up the CWD with logs.
    '''
    start_dir = os.getcwd()
    temp_dir_object = tempfile.TemporaryDirectory()
    temp_dir_name = temp_dir_object.name                                        #Make a temp directory.
    os.popen(f'cp {start_dir}/my_dro_map.json {temp_dir_name}/my_dro_map.json') #Copy the DRO map inside.
    os.chdir(temp_dir_name)                                                     #Move into the temp dir.

    conf_name = "test-conf"
    DMG_args = ["daqconf_multiru_gen", "-m", "my_dro_map.json", conf_name]
    subprocess.run(DMG_args)                                                    #Generate a config
    partition_name = f"test-partition-{request.param}"

    match request.param:
        case "normal":
            arglist = ["nanorc", conf_name, partition_name] + commands

        case "top-json":        #Two duplicates of the regular config is enough to test that a top level json is functional
            TJ_content = {"apparatus_id": "test", "sub1": conf_name, "sub2": conf_name}
            with open("top-level.json", "w") as outfile:
                json.dump(TJ_content, outfile)
            arglist = ["nanorc", "top-level.json", partition_name] + commands

    output = subprocess.run(arglist)
    os.chdir(start_dir)
    return output.returncode

def test_no_errors(perform_all_runs):
    assert perform_all_runs == 0
