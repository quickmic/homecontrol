#!/bin/bash
apt-get update
apt-get install python3 -y

mkdir /opt/homecontrol/
mkdir /opt/homecontrol/plugins/
cp /opt/homecontrol-git/homecontrol.py /opt/homecontrol/
cp -n /opt/homecontrol-git/config.txt /opt/homecontrol/config.txt
cp /opt/homecontrol-git/plugins/* /opt/homecontrol/plugins/

cp /opt/homecontrol-git/systemd/homecontrol.service /etc/systemd/system/homecontrol.service
chmod 644 /etc/systemd/system/homecontrol.service

systemctl daemon-reload
systemctl enable homecontrol
