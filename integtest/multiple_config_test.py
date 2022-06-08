import pytest

# The next three variable declarations *must* be present as globals in the test
# file. They're read by the "fixtures" in conftest.py to determine how
# to run the config generation and nanorc

# The name of the python module for the config generation.
# Use "multi" if multiple configs per test are being used
confgen_name="multi"

# The arguments to pass to the config generator, excluding the json
# output directory (the test framework handles that).
#When multiple configs are used per test, then start each one with the module used for config generation, and end each with "END".
confgen_arguments=[ "daqconf_multiru_gen", "-o", ".", "-s", "10", "-n", "2", "END", "daqconf_multiru_gen", "-o", ".", "-s", "15", "-n", "2", "END"]

# The commands to run in nanorc, as a list
nanorc_command_list="boot init conf start 1 resume wait 10 stop scrap terminate".split()

# The tests themselves
def test_nanorc_success(run_nanorc):
    # Basic test to check that nanorc ran successfully
    assert run_nanorc.completed_process.returncode==0
