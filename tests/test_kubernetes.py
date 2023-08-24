import json
import os
import pytest
import subprocess
import tempfile

json_contents = {"boot": {"use_connectivity_service": True, "connectivity_service_host": "np04-srv-023", "connectivity_service_port": 30005, "start_connectivity_service": False},
                 "readout": {"use_fake_data_producers": True}}
conf_types = ["no-db", "db"]
commands = "boot conf start_run 111 wait 60 stop_run scrap terminate".split()
conf_name = "test-conf"
db_name = "integ-test-conf"
cluster_address = "k8s://np04-srv-015:31000"


@pytest.fixture(params = conf_types)
def perform_all_runs(request):
    '''
    We generate a config using daqconf_multiru_gen, then run nanorc (on k8s) with and without uploading to the mongoDB.
    The error code of the process is used to determine whether everything worked.
    All processes are run in a temporary directory, so as not to fill up the CWD with logs.
    '''
    start_dir = os.getcwd()
    temp_dir_object = tempfile.TemporaryDirectory()
    temp_dir_name = temp_dir_object.name                                        #Make a temp directory.
    os.popen(f'cp {start_dir}/my_dro_map.json {temp_dir_name}/my_dro_map.json') #Copy the DRO map inside.
    os.chdir(temp_dir_name)                                                     #Move into the temp dir.
    with open('conf.json', 'w') as json_file:
        json.dump(json_contents, json_file)


    DMG_args = ["daqconf_multiru_gen", "--force", "-c", "conf.json", "-m", "my_dro_map.json", "--force-pm", "k8s", conf_name]
    subprocess.run(DMG_args)                                                    #Generate a config
    partition_name = f"test-partition-{request.param}"

    match request.param:
        case "no-db":
            arglist = ["nanorc", "--pm", cluster_address, conf_name, partition_name] + commands

        case "db":      #We upload the config to the database first
            upload_args = ["upload-conf", conf_name, db_name]
            subprocess.run(upload_args)
            arglist = ["nanorc", "--pm", cluster_address, f"db://{db_name}", partition_name] + commands

    output = subprocess.run(arglist)
    os.chdir(start_dir)
    return output.returncode

def test_no_errors(perform_all_runs):
    assert perform_all_runs == 0
