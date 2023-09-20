import json
import os
import pytest
import subprocess
import tempfile

app_name = "trigger"
command_name = "record"
k8s_json_contents = {"boot": {"use_connectivity_service": True, "connectivity_service_host": "np04-srv-023", "connectivity_service_port": 30005, "start_connectivity_service": False},
                 "readout": {"use_fake_data_producers": True}}

custom_command1 = {"apps": {app_name: f"data/{app_name}_{command_name}"}}
custom_command2 = {"modules": [{"data": {}, "match": "*"}]}
conf_types = ["normal", "k8s"]
exe_names = ["nanorc", "nanotimingrc"]
commands = f"boot {command_name}".split()
conf_name = "test-conf"
cluster_address = "k8s://np04-srv-015:31000"

def insert_jsons():
    os.chdir(conf_name)
    with open(f'{command_name}.json', 'w') as json_file1:
        json.dump(custom_command1, json_file1)

    os.chdir("data")
    with open(f'{app_name}_{command_name}.json', 'w') as json_file2:
        json.dump(custom_command2, json_file2)

    os.chdir("../..")
    print(os.getcwd())
    print(os.listdir())

def perform_all_runs(exe_name, conf_type):
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

    match conf_type:
        case "normal":
            DMG_args = ["daqconf_multiru_gen", "-m", "my_dro_map.json", conf_name]
            subprocess.run(DMG_args)
            partition_name = f"test-partition-{conf_type}"
            insert_jsons()
            arglist = [exe_name, conf_name, partition_name] + commands

        case "k8s":
            with open('conf.json', 'w') as json_file:
                json.dump(k8s_json_contents, json_file)
            DMG_args_k8s = ["daqconf_multiru_gen", "--force", "-c", "conf.json", "-m", "my_dro_map.json", "--force-pm", "k8s", conf_name]
            subprocess.run(DMG_args_k8s)
            partition_name = f"test-partition-{conf_type}"
            insert_jsons()
            arglist = [exe_name, "--pm", cluster_address, conf_name, partition_name] + commands

    print(arglist)
    output = subprocess.run(arglist)
    os.chdir(start_dir)
    return output.returncode

@pytest.mark.parametrize("exe_name", exe_names)
@pytest.mark.parametrize("conf_type", conf_types)
def test_no_errors(exe_name, conf_type):
    code = perform_all_runs(exe_name, conf_type)
    assert code == 0
