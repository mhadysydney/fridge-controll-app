#!/bin/bash
FMB_DIR="."
LOG_FILE="$FMB_DIR/tcp_server_v8.log"
NGROK_LOG="$FMB_DIR/ngrok.log"
PYTHON="./venv/bin/python3"
NGROK="/snap/bin/ngrok"
ICCID="8944538532057627725"
TOKEN=""
sms_to_send=""
apiRetry=0

sendSMS(){
   # local sms_to_send="$1"
    echo $(date '+%Y-%m-%d %H:%M:%S') "Sending sms $sms_to_send" >> $LOG_FILE
    TOKEN=$(cat auth_token.conf)
    CURL_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
                            --header 'Authorization: Bearer '$TOKEN \
                            --header 'accept: application/json' \
                            --header 'content-type: application/*+json' \
                            --data '{"text":"'$sms_to_send'"}' \
                        https://api.worldov.net/v1/sms/system/sim/$ICCID )
    
    if [ "$CURL_RESPONSE" -eq 401 ]; then
        sms_api_auth
        apiRetry=$apiRetry+1
        sleep 10
        if [ $apiRetry<=5 ];then
            sendSMS $sms_to_send

    return $CURL_RESPONSE
}

sms_api_auth(){
    echo $(date '+%Y-%m-%d %H:%M:%S') "user authentication lunched" >> $LOG_FILE
    username=$(grep "user=" fmb-control-app/auth.conf | cut -d'=' -f2)
    password=$(grep "mdp=" fmb-control-app/auth.conf | cut -d'=' -f2)
    auth_response=$(curl -s -X POST \
            -H 'content-type: application/*+json' \
            -d '{"username":"","password":""}'\
            https://api.worldov.net/v1/auth/login
      )
    if [$auth_response -neq ""];then
        token=$(grep "response={" auth.conf | awk -F':"' '{print $2}' | awk -F'",' '{print $1}')
        echo $token >> auth_token.conf
        echo $(date '+%Y-%m-%d %H:%M:%S') "user authenticated successfully!" >> $LOG_FILE
    else
        echo $(date '+%Y-%m-%d %H:%M:%S') "user authentication failed!" >> $LOG_FILE
    fi
}

$PYTHON $FMB_DIR/tcp_server_v8.py >> $LOG_FILE 2>&1 &
TCP_PID=$!
SMS_STATE=0
echo $(date '+%Y-%m-%d %H:%M:%S') "Started tcp_server_v8.py (PID: $TCP_PID)" >> $LOG_FILE

$NGROK tcp 50122 --log $NGROK_LOG &
NGROK_PID=$!
echo $(date '+%Y-%m-%d %H:%M:%S') "Enter sleeping mode" >> $LOG_FILE
sleep 7
echo $(date '+%Y-%m-%d %H:%M:%S') "Exit sleeping mode" >> $LOG_FILE
echo $(date '+%Y-%m-%d %H:%M:%S') "Started ngrok (PID: $NGROK_PID), sms_state: $SMS_STATE" >> $LOG_FILE
NGROK_URL=$(grep "started tunnel" $NGROK_LOG | tail -1 | grep -o "tcp://[^ ]*")
echo $(date '+%Y-%m-%d %H:%M:%S') "New ngrok URL: $NGROK_URL" >> $LOG_FILE

while true; do
    if ! ps -p $TCP_PID > /dev/null; then
        echo $(date '+%Y-%m-%d %H:%M:%S') "tcp_server_v8.py crashed, restarting" >> $LOG_FILE
        $PYTHON $FMB_DIR/tcp_server_v8.py >> $LOG_FILE 2>&1 &
        TCP_PID=$!
    fi
    if ! ps -p $NGROK_PID > /dev/null; then
        echo $(date '+%Y-%m-%d %H:%M:%S') "ngrok crashed, restarting" >> $LOG_FILE
        $NGROK tcp 50122 --log $NGROK_LOG &
        NGROK_PID=$!
        sleep 7
        NGROK_URL=$(grep "started tunnel" $NGROK_LOG | tail -1 | grep -o "tcp://[^ ]*")
        SMS_STATE=0
        echo $(date '+%Y-%m-%d %H:%M:%S') "New ngrok URL: $NGROK_URL, sms_state: $SMS_STATE" >> $LOG_FILE
        
        # TODO Update FMB device config
    fi

    if [ -z "$NGROK_URL" ]; then
            echo $(date '+%Y-%m-%d %H:%M:%S') "Failed to extract ngrok URL from $NGROK_LOG" >> $LOG_FILE
    elif [[ $SMS_STATE -eq 0 ]]; then
            # Extract hostname and port
            HOSTNAME=$(echo $NGROK_URL | cut -d'/' -f3 | cut -d':' -f1)
            PORT=$(echo $NGROK_URL | cut -d':' -f3)
            echo $(date '+%Y-%m-%d %H:%M:%S') "Extracted ngrok URL: $NGROK_URL (Hostname: $HOSTNAME, Port: $PORT)" >> $LOG_FILE
            sms_to_send='" 0224 setparam 2004:'$HOSTNAME';2005:'$PORT'"'
            CURL_RESPONSE=$(sendSMS $sms_to_send)
            
            # Send curl request to configure FMB920
            #CURL_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
            #                --header 'Authorization: Bearer '$TOKEN \
            #                --header 'accept: application/json' \
            #                --header 'content-type: application/*+json' \
            #                --data '{"text":" 0224 setparam 2004:'$HOSTNAME';2005:'$PORT'"}' \
            #            https://api.worldov.net/v1/sms/system/sim/$ICCID 2>> $LOG_FILE)
            #CURL_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
             #   -d "ICCID=$ICCID&hostname=$HOSTNAME&port=$PORT" \
              #  $API_URL 2>> $LOG_FILE)
            #CURL_BODY=$(curl -s -X POST \
             #   -d "ICCID=$ICCID&hostname=$HOSTNAME&port=$PORT" \
              #  $API_URL 2>> $LOG_FILE)

            # Log curl response status
            if [ "$CURL_RESPONSE" -eq 200 ]; then
                SMS_STATE=1
                echo $(date '+%Y-%m-%d %H:%M:%S') "Successfully sent ngrok URL to FMB920 (ICCID: $ICCID, Response: $CURL_RESPONSE, sms_state: $SMS_STATE)" >> $LOG_FILE
                sleep 8
                sms_to_send=" 0224 cpureset"
                RESTART_FMB=$(sendSMS $sms_to_send)
                sleep 10
                #$(sendSMS $sms_to_send)$(curl -s -o /dev/null -w "%{http_code}" -X POST \
                #            --header 'Authorization: Bearer '$TOKEN \
                #            --header 'accept: application/json' \
                #            --header 'content-type: application/*+json' \
                #            --data '{"text":" 0224 cpureset"}' \
                #        https://api.worldov.net/v1/sms/system/sim/$ICCID 2>> $LOG_FILE)
                if [ "$RESTART_FMB" -eq 200 ]; then
                    echo $(date '+%Y-%m-%d %H:%M:%S') "Device restarted successfully!" >> $LOG_FILE
                else
                    echo $(date '+%Y-%m-%d %H:%M:%S') "failed to send restart command" >> $LOG_FILE
                fi
                #STATUS=$(echo $CURL_BODY | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
                #if [ "$STATUS" = "success" ]; then
                #    echo "Successfully sent ngrok URL to FMB920 (ICCID: $ICCID, Response: $CURL_BODY)" >> $LOG_FILE
                #else
                 #   echo "Failed to send ngrok URL to FMB920 (ICCID: $ICCID, Response: $CURL_BODY)" >> $LOG_FILE
                #fi
            else
                echo $(date '+%Y-%m-%d %H:%M:%S') "curl request failed with HTTP code $CURL_RESPONSE (Response: $CURL_RESPONSE, sms_state: $SMS_STATE)" >> $LOG_FILE
            fi
    fi
    
    sleep 60
done