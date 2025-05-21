#!/bin/bash
LOG_FILE="./debugSH.log"
ICCID="8944538532057627725"

sms_api_auth(){
    echo $(date '+%Y-%m-%d %H:%M:%S') "user authentication lunched $PWD" >> $LOG_FILE
    username=$(grep "user=" auth.conf | cut -d'=' -f2)
    password=$(grep "mdp=" auth.conf | cut -d'=' -f2)
    auth_response=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
            -H 'content-type: application/*+json' \
            -d '{"username":"'$username'","password":"'$password'"}'\
            https://api.worldov.net/v1/auth/login
      )
      echo $(date '+%Y-%m-%d %H:%M:%S') "user authentication status code! $auth_response " >> $LOG_FILE
    if [ -n "$auth_response" ]; then
        #token=$(grep "response={" auth.conf | awk -F':"' '{print $2}' | awk -F'",' '{print $1}')
        #echo $token >> auth_token.conf
        echo $(date '+%Y-%m-%d %H:%M:%S') "user authenticated successfully!" >> $LOG_FILE
    else
        echo $(date '+%Y-%m-%d %H:%M:%S') "user authentication failed!" >> $LOG_FILE
    fi
}

sms_to_send=" 0224 setparam"
DATA='{"text":"'$sms_to_send'"}'
TOKEN=$(cat auth_token.conf)
authr="Authorization: Bearer $TOKEN"
echo "$DATA"
sms_api_auth


