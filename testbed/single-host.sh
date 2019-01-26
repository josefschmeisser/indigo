#!/bin/bash

# exit on error
set -e
# log every command
set -x

echo $(pos_get_variable hostname)

# install dependencies
apt-get update
# python and tensorflow
apt-get --yes install python-pip python-dev python-virtualenv
# openvswitch
apt-get --yes install openvswitch-testcontroller
ln /usr/bin/ovs-testcontroller /usr/bin/controller
# python packages
#pip install -U pip
pip install -U tensorflow
pip install -U pyyaml
pip install -U posix_ipc
# mininet
apt-get --yes install mininet
# protobuf
apt-get --yes install python-protobuf

# install indigo
GIT_REPO=$(pos_get_variable git/repo)
INDIGO=indigo

# disable strict host checking for gitlab.lrz.de
echo -e "Host gitlab.lrz.de\n\tStrictHostKeyChecking no\n" >> ~/.ssh/config

echo "Cloning $GIT_REPO into $INDIGO"
git clone --recursive $GIT_REPO $INDIGO
cd $INDIGO
# checkout a particular branch or commit
git checkout $(pos_get_variable git/commit)

# write back the hash of the exact git commit used for reference later
pos_set_variable git/commit-hash $(git rev-parse --verify HEAD)

echo 'all done'
