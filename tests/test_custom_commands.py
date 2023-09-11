import json
import os
import pytest
import subprocess
import tempfile

app_name = "trigger"

custom_command1 = {"apps": {app_name: f"data/{app_name}_custom_command"}}
custom_command2 = {"modules": [{"data": {}, "match": "*"}]}
conf_types = ["normal", "k8s"]
commands = "boot custom_command".split()
conf_name = "test-conf"
cluster_address = "k8s://np04-srv-015:31000"

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

    DMG_args = ["daqconf_multiru_gen", "-m", "my_dro_map.json", conf_name]
    subprocess.run(DMG_args)                                                    #Generate a config
    print(os.listdir())
    partition_name = f"test-partition-{request.param}"
    os.chdir(conf_name)
    with open('custom_command.json', 'w') as json_file1:
        json.dump(custom_command1, json_file1)
    print(os.listdir())
    os.chdir("data")
    with open(f'{app_name}_custom_command.json', 'w') as json_file2:
        json.dump(custom_command2, json_file2)
    print(os.listdir())
    os.chdir("../..")

    match request.param:
        case "normal":
            arglist = ["nanorc", conf_name, partition_name] + commands

        case "k8s":
            arglist = ["nanorc", "--pm", cluster_address, conf_name, partition_name] + commands

    output = subprocess.run(arglist)
    os.chdir(start_dir)
    return output.returncode

def test_no_errors(perform_all_runs):
    assert perform_all_runs == 0

