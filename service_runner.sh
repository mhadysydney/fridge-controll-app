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
SMS_STATE=0

sendSMS(){
    #local send_status="$1"
    CURL_RESPONSE=""
    if [ $SMS_STATE -eq 0 ]; then
        echo $(date '+%Y-%m-%d %H:%M:%S') "Sending sms $sms_to_send" >> $LOG_FILE
        TOKEN=$(cat auth_token.conf)
        DATA='{"text":"'$sms_to_send'"}'
        echo $(date '+%Y-%m-%d %H:%M:%S') "Extracted Token: $TOKEN" >> $LOG_FILE
        CURL_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
                            --header "Authorization: Bearer $TOKEN" \
                            --header 'accept: application/json' \
                            --header 'content-type: application/*+json' \
                            --data "$DATA" \
                        https://api.worldov.net/v1/sms/system/sim/$ICCID)
        echo $(date '+%Y-%m-%d %H:%M:%S') "SMS ($sms_to_send) Response: $CURL_RESPONSE, sms_state: $SMS_STATE)" >> $LOG_FILE
        if [ $CURL_RESPONSE -eq 200 ]; then
                echo $(date '+%Y-%m-%d %H:%M:%S') "SMS ($sms_to_send) sent Successfully to device (ICCID: $ICCID, Response: $CURL_RESPONSE, sms_state: $SMS_STATE)" >> $LOG_FILE
                sleep 8
                #sms_to_send=" 0224 cpureset"
                #RESTART_FMB=$(sendSMS)
                #sleep 10
                RESTART_FMB=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
                            --header "Authorization: Bearer $TOKEN" \
                            --header 'accept: application/json' \
                            --header 'content-type: application/*+json' \
                           --data '{"text":" 0224 cpureset"}' \
                        https://api.worldov.net/v1/sms/system/sim/$ICCID 2>> $LOG_FILE)
                if [ $RESTART_FMB -eq 200 ]; then
                    SMS_STATE=1
                    apiRetry=0
                    echo $(date '+%Y-%m-%d %H:%M:%S') "Device restarted successfully!" >> $LOG_FILE
                else
                   echo $(date '+%Y-%m-%d %H:%M:%S') "failed to send restart command with HTTP code $RESTART_FMB" >> $LOG_FILE
                fi
                #STATUS=$(echo $CURL_BODY | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
                #if [ "$STATUS" = "success" ]; then
                #    echo "Successfully sent ngrok URL to FMB920 (ICCID: $ICCID, Response: $CURL_BODY)" >> $LOG_FILE
                #else
                 #   echo "Failed to send ngrok URL to FMB920 (ICCID: $ICCID, Response: $CURL_BODY)" >> $LOG_FILE
                #fi
    
        elif [[ $CURL_RESPONSE -eq 401 ]]; then
            sms_api_auth
            ((apiRetry++))
            sleep 10
            echo $(date '+%Y-%m-%d %H:%M:%S') "sendSMS attempt :"$apiRetry >> $LOG_FILE
            if [[ $apiRetry -le 5 ]];then
                sendSMS
            else
                echo $(date '+%Y-%m-%d %H:%M:%S') "sendSMS attempt limit reached exiting script service_runner, apiRetry:"$apiRetry >> $LOG_FILE
                exit
            fi
        else
                echo $(date '+%Y-%m-%d %H:%M:%S') "curl request failed with HTTP code $CURL_RESPONSE (SMS: $sms_to_send, sms_state: $SMS_STATE)" >> $LOG_FILE
        fi
    fi
    return $CURL_RESPONSE
}

sms_api_auth(){
    echo $(date '+%Y-%m-%d %H:%M:%S') "user authentication lunched" >> $LOG_FILE
    username=$(grep "user=" auth.conf | cut -d'=' -f2)
    password=$(grep "mdp=" auth.conf | cut -d'=' -f2)
    auth_response=$(curl -s -X POST \
            -H 'content-type: application/*+json' \
            -d '{"username":"'$username'","password":"'$password'"}'\
            https://api.worldov.net/v1/auth/login
      )
    if [ -n "$auth_response" ]; then
        token=$(grep "response={" auth.conf | awk -F':"' '{print $2}' | awk -F'",' '{print $1}')
        echo $token > auth_token.conf
        echo $(date '+%Y-%m-%d %H:%M:%S') "user authenticated successfully!" >> $LOG_FILE
    else
        echo $(date '+%Y-%m-%d %H:%M:%S') "user authentication failed!" >> $LOG_FILE
    fi
}

$PYTHON $FMB_DIR/tcp_server_v8.py >> $LOG_FILE 2>&1 &
TCP_PID=$!

echo $(date '+%Y-%m-%d %H:%M:%S') "Started tcp_server_v8.py (PID: $TCP_PID)" >> $LOG_FILE

$NGROK tcp 50122 --log $NGROK_LOG &
NGROK_PID=$!
echo $(date '+%Y-%m-%d %H:%M:%S') "Enter sleeping mode" >> $LOG_FILE
sleep 12
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
            sms_to_send=" 0224 setparam 2004:$HOSTNAME;2005:$PORT"
            sendSMS
            #sleep 10
            #sms_to_send=" 0224 cpureset"
            #RESTART_FMB=$(sendSMS)
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
            
    fi
    
    sleep 60
done