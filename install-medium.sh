#!/bin/bash
apt-get update
apt-get install python3 -y
apt-get install python3-pip -y
apt-get install python3-dev -y
apt-get install build-essential -y

python3 -m pip install setproctitle

