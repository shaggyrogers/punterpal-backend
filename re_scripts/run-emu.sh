#!/usr/bin/env bash
export PATH=$PATH:$HOME/Android/Sdk/platform-tools
export PATH=$PATH:$HOME/Android/Sdk/emulator

# Forward port 8080 to PC
# Probably not necessary unless using httptoolkit scripts with connect hook
adb reverse tcp:8080 tcp:8080

emulator \
    -no-sim \
    -no-skin \
    -no-passive-gps \
    -avd Pixel_9_API_32 \
    -http-proxy 127.0.0.1:8080
