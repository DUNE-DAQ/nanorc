import json
import os
import pytest
import subprocess
import tempfile

json_contents = {"boot": {"use_connectivity_service": True, "connectivity_service_host": "np04-srv-023", "connectivity_service_port": 30005, "start_connectivity_service": False},
                 "readout": {"use_fake_data_producers": True}}
conf_types = ["no-db", "db"]
exe_names = ["nanorc", "nanotimingrc"]
cmd_dict = {"nanorc": "boot conf start_run 111 wait 60 stop_run scrap terminate".split(),
            "nano04rc": "boot conf start_run TEST wait 60 stop_run scrap terminate".split(),
            "nanotimingrc": "boot conf start_run wait 60 stop_run scrap terminate".split()}
conf_name = "test-conf"
db_name = "integ-test-conf"
cluster_address = "k8s://np04-srv-015:31000"

def perform_all_runs(exe_name, conf_type):
    '''
    We generate a config using daqconf_multiru_gen, then run nanorc (on k8s) with and without uploading to the mongoDB.
    The error code of the process is used to determine whether everything worked.
    All processes are run in a temporary directory, so as not to fill up the CWD with logs.
    '''
    commands = cmd_dict[exe_name]
    start_dir = os.getcwd()
    temp_dir_object = tempfile.TemporaryDirectory()
    temp_dir_name = temp_dir_object.name                                        #Make a temp directory.
    os.popen(f'cp {start_dir}/my_dro_map.json {temp_dir_name}/my_dro_map.json') #Copy the DRO map inside.
    os.chdir(temp_dir_name)                                                     #Move into the temp dir.
    with open('conf.json', 'w') as json_file:
        json.dump(json_contents, json_file)


    DMG_args = ["daqconf_multiru_gen", "--force", "-c", "conf.json", "-m", "my_dro_map.json", "--force-pm", "k8s", conf_name]
    subprocess.run(DMG_args)                                                    #Generate a config
    partition_name = f"test-partition-{conf_type}"

    match conf_type:
        case "no-db":
            arglist = [exe_name, "--pm", cluster_address, conf_name, partition_name] + commands

        case "db":      #We upload the config to the database first
            upload_args = ["upload-conf", conf_name, db_name]
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
