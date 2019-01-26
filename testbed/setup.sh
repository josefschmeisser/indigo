#!/bin/bash

if test "$#" -ne 1; then
	echo "Usage: setup.sh host"
	exit
fi

HOST=$1

# in the best case, the hosts are already free
echo "free host (-force!)"
pos allocations free --force "$HOST"

# allocate all hosts for ONE experiment
echo "allocate host"
pos allocations allocate "$HOST"

echo "load experiment variables"
pos allocations variables "$HOST" host-variables.yaml
#pos allocations variables "$HOST" --as-default default-variables.yaml

echo "set images to debian stretch"
pos nodes image "$HOST" debian-stretch

echo "reboot experiment host..."
# run reset blocking in background and wait for processes to end before continuing
{ pos nodes reset "$HOST"; echo "$HOST booted successfully"; } &
wait

# copy deploy key (enables read-only access to the git repository)
{ pos nodes copy "$HOST" $HOME/deploy_key/id_rsa --dest /root/.ssh/id_rsa;
  pos nodes copy "$HOST" $HOME/deploy_key/id_rsa.pub --dest /root/.ssh/id_rsa.pub; } &
wait
pos commands launch "$HOST" chmod 600 /root/.ssh/id_rsa

echo "deploy & run experiment scripts..."
{ pos commands launch --infile single-host.sh "$HOST"; echo "$HOST userscript executed"; } &
wait

# after the experiment is done, make hosts available for other students
#echo "free host"
#pos allocations free "$HOST"
