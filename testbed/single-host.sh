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
#pip2 install -U pip
pip install -U pip
#pip2 install -U tensorflow
pip install -U tensorflow
# mininet
apt-get --yes install mininet
# protobuf
apt-get --yes install python-protobuf
# TODO python ipc

# install indigo
GIT_REPO=$(pos_get_variable git/repo)

INDIGO=indigo

echo "Cloning $GIT_REPO into $INDIGO"
git clone --recursive $GIT_REPO $INDIGO
cd $INDIGO
# checkout a particular branch or commit
git checkout $(pos_get_variable git/commit)

# write back the hash of the exact git commit used for reference later
pos_set_variable git/commit-hash $(git rev-parse --verify HEAD)

echo 'all done'
