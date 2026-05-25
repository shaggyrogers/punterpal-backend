#!/usr/bin/env bash
export PATH=$PATH:$HOME/Android/Sdk/platform-tools
export PATH=$PATH:$HOME/Android/Sdk/emulator

adb push ./frida-server-16.5.7-android-x86_64 /data/local/tmp/frida-server

# This doesn't work. Need to run manually with su to avoid this.
# adb root

adb shell "chmod 655 /data/local/tmp/frida-server"

echo "Need to manually start frida-server as root in adb shell via the commands below:"
echo "adb shell: >su; /data/local/tmp/frida-server &"

# This won't work either. Need to run adb shell and manually execute the commands below.
# adb shell "su; chmod 655 /data/local/tmp/frida-server; /data/local/tmp/frida-server &"
