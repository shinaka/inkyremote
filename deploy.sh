#!/bin/bash
cd /home/jweinhart/inkyremote
git pull
sudo cp inkyremote.service /etc/systemd/system/
sudo systemctl daemon-reload