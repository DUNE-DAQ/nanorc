import json
import os
import pytest
import subprocess
import tempfile

app_name = "trigger"
k8s_json_contents = {"boot": {"use_connectivity_service": True, "connectivity_service_host": "np04-srv-023", "connectivity_service_port": 30005, "start_connectivity_service": False},
                 "readout": {"use_fake_data_producers": True}}
expert_json = {"id": "record", "entry_state": "ANY", "exit_state": "ANY", "data": {}}
conf_types = ["normal", "k8s"]
conf_name = "test-conf"
commands = f"boot expert_command {conf_name}/{conf_name}/dfo expert.json".split()
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

    match request.param:
        case "normal":
            DMG_args = ["daqconf_multiru_gen", "-m", "my_dro_map.json", conf_name]
            subprocess.run(DMG_args)
            partition_name = f"test-partition-{request.param}"
            with open('expert.json', 'w') as json_file1:
                json.dump(expert_json, json_file1)
            arglist = ["nanorc", conf_name, partition_name] + commands

        case "k8s":
            with open('conf.json', 'w') as json_file:
                json.dump(k8s_json_contents, json_file)
            DMG_args_k8s = ["daqconf_multiru_gen", "--force", "-c", "conf.json", "-m", "my_dro_map.json", "--force-pm", "k8s", conf_name]
            subprocess.run(DMG_args_k8s)
            partition_name = f"test-partition-{request.param}"
            with open('expert.json', 'w') as json_file1:
                json.dump(expert_json, json_file1)
            arglist = ["nanorc", "--pm", cluster_address, conf_name, partition_name] + commands

    output = subprocess.run(arglist)
    os.chdir(start_dir)
    return output.returncode

def test_no_errors(perform_all_runs):
    assert perform_all_runs == 0

