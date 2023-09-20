# NanoRC Integration Tests

These tests run using vanilla pytest, rather than the test framework in the "integrationtest" repository. This is because the framework is more suited to testing configurations, rather than NanoRC itself.
Before running these tests it is required to run `pip uninstall integrationtest`, as otherwise the pytest command will default to using the test framework.
After this, the tests can be run with `pytest <name_of_test>`. The -s flag can be useful to see the full output of NanoRC to the terminal.
