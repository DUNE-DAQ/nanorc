import pytest

# The next three variable declarations *must* be present as globals in the test
# file. They're read by the "fixtures" in conftest.py to determine how
# to run the config generation and nanorc

# The name of the python module for the config generation
confgen_name="daqconf_multiru_gen"
# The arguments to pass to the config generator, excluding the json
# output directory (the test framework handles that)
confgen_arguments=[ "-o", ".", "-s", "10", "-n", "2"]
# The commands to run in nanorc, as a dictionary
nanorc_keys = [("Partition No. " + str(i)) for i in range(10)]
nanorc_script = "boot init conf start 1 resume wait 10 stop scrap terminate".split()
nanorc_values = [["--partition-number", str(i)] + nanorc_script for i in range(10)]
nanorc_command_list = {nanorc_keys[i]: nanorc_values[i] for i in range(10)}            #This variable is the one that gets sent to pytest

# The tests themselves
def test_nanorc_success(run_nanorc):
    # Basic test to check that nanorc ran successfully
    assert run_nanorc.completed_process.returncode==0
