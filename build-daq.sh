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
git clone https://github.com/DUNE-DAQ/daq-buildtools.git -b v2.2.1
source daq-buildtools/dbt-setup-env.sh

echo "setting up project"
mkdir daq-app
cd daq-app
dbt-create.sh dunedaq-v2.3.0

echo "checking out newer code"
# https://github.com/DUNE-DAQ/minidaqapp/issues/11#issuecomment-776873658
cd sourcecode
git clone https://github.com/DUNE-DAQ/dataformats.git -b v2.0.0
git clone https://github.com/DUNE-DAQ/dfmessages.git -b v2.0.0
git clone https://github.com/DUNE-DAQ/dfmodules.git -b v2.0.1
git clone https://github.com/DUNE-DAQ/flxlibs.git -b develop
cd flxlibs && git checkout dd6483b && cd ..
git clone https://github.com/DUNE-DAQ/ipm.git -b v2.0.1
git clone https://github.com/DUNE-DAQ/nwqueueadapters.git -b v1.1.1
git clone https://github.com/DUNE-DAQ/readout.git -b develop
cd readout && git checkout c277d56 && cd ..
git clone https://github.com/DUNE-DAQ/restcmd.git -b develop
cd restcmd && git checkout 9e46044 && cd ..
git clone https://github.com/DUNE-DAQ/serialization.git -b v1.1.0
git clone https://github.com/DUNE-DAQ/trigemu.git -b v2.0.0
git clone https://github.com/DUNE-DAQ/minidaqapp.git -b develop
cd minidaqapp && git checkout 1a858fb && cd ..
echo 'set(build_order "daq-cmake" "ers" "logging" "cmdlib" "rcif" "restcmd" "opmonlib" "appfwk" "listrev" "daqdemos" "ipm" "serialization" "nwqueueadapters" "dataformats" "dfmessages" "dfmodules" "readout" "flxlibs" "trigemu" "minidaqapp")' > dbt-build-order.cmake
cd ..

sed -i 's,#"/cvmfs/dune.opensciencegrid.org/dunedaq/DUNE/products","/cvmfs/dune.opensciencegrid.org/dunedaq/DUNE/products",' dbt-settings
sed -i 's,#"/cvmfs/dune.opensciencegrid.org/dunedaq/DUNE/products_dev","/cvmfs/dune.opensciencegrid.org/dunedaq/DUNE/products_dev",' dbt-settings
sed -i 's/"msgpack_c v3_3_0 e19:prof"/"msgpack_c v3_3_0 e19:prof"\n    "felix v1_1_0 e19:prof"/' dbt-settings

echo "setting up build env"
dbt-setup-build-environment
echo "running dbt-build"
dbt-build.sh --install

curl -Lo frames.bin https://cernbox.cern.ch/index.php/s/VAqNtn7bwuQtff3/download

# fix alias issue
cd $tmp_dir/daq-buildtools
git checkout 7a01c1d