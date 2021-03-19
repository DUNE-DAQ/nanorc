#!/usr/bin/env bash
# we can't use safe mode, shitty scripts being called
# set -o errexit -o nounset -o pipefail
# IFS=$'\n\t\v'
shopt -s expand_aliases # script uses aliases, does't work in non-interactive shells unless explicitly enabled

# Constructed from
# https://github.com/DUNE-DAQ/minidaqapp/wiki/Instructions-for-setting-up-a-v2.4.0-development-environment

echo "starting setup"

# tmp_dir=$(mktemp -d -t ci-XXXXXXXXXX)
# default is not $PWD, very likely to be AFS share (very slow)
tmp_dir=${1:-"/tmp/$USER/nanorc-buildenv"}

echo "setting up daq application in $tmp_dir"
mkdir -p $tmp_dir
cd $tmp_dir

echo "sourcing daq built tools"
git clone https://github.com/DUNE-DAQ/daq-buildtools.git -b v2.3.0
source daq-buildtools/dbt-setup-env.sh

echo "setting up project"
dbt-create.sh dunedaq-v2.4.0 daq-app
cd daq-app

echo "setting up build env"
dbt-setup-build-environment
echo "running dbt-build"
dbt-build.sh

# Download data file for minidaqapp fake data source
curl -Lo frames.bin https://cernbox.cern.ch/index.php/s/VAqNtn7bwuQtff3/download
