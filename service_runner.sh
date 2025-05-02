#!/bin/bash
FMB_DIR="."
LOG_FILE="$FMB_DIR/tcp_server.log"
NGROK_LOG="$FMB_DIR/ngrok.log"
PYTHON="/usr/bin/python3"
NGROK="/snap/bin/ngrok"

$PYTHON $FMB_DIR/grok_fmb_server_v6.py >> $LOG_FILE 2>&1 &
TCP_PID=$!
echo "Started tcp_server.py (PID: $TCP_PID)" >> $LOG_FILE

$NGROK tcp 12345 --log $NGROK_LOG &
NGROK_PID=$!
echo "Started ngrok (PID: $NGROK_PID)" >> $LOG_FILE

while true; do
    if ! ps -p $TCP_PID > /dev/null; then
        echo "tcp_server.py crashed, restarting" >> $LOG_FILE
        $PYTHON $FMB_DIR/tcp_server.py >> $LOG_FILE 2>&1 &
        TCP_PID=$!
    fi
    if ! ps -p $NGROK_PID > /dev/null; then
        echo "ngrok crashed, restarting" >> $LOG_FILE
        $NGROK tcp 12345 --log $NGROK_LOG &
        NGROK_PID=$!
        sleep 5
        NGROK_URL=$(grep "started tunnel" $NGROK_LOG | tail -1 | grep -o "tcp://[^ ]*")
        echo "New ngrok URL: $NGROK_URL" >> $LOG_FILE
        # TODO: Update FMB device config
    fi
    sleep 60
done