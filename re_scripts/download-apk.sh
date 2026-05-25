#!/usr/bin/env bash
###############################################################################
# download-apk.sh
# ===============
#
# Description:           Searches for an APK and downloads to current directory
# Author:                Michael De Pasquale
# Creation Date:         2024-11-29
# Modification Date:     2024-11-29
#
###############################################################################

export PATH=$PATH:$HOME/Android/Sdk/platform-tools
export PATH=$PATH:$HOME/Android/Sdk/emulator

_usage() {
    echo "Usage: download-apk.sh keyword"
    echo ""
    echo ""
}

# Check args
if [[ "$#" != "1" ]]; then
    echo "Error: Expected 1 argument."

    _usage
    exit 1
fi

# Search for packages matching keyword
echo "Searching for '$1'"
PACKAGE_MATCHES="$(adb shell pm list packages | grep "$1")"
PACKAGE_MATCH_COUNT=$(echo "$PACKAGE_MATCHES" | wc -l)

# >1 Match - abort
if [[ "$PACKAGE_MATCH_COUNT" != "1" ]]; then
    echo "Error: Found $PACKAGE_MATCH_COUNT matches"
    echo "Check matches below and refine keyword."
    echo "$PACKAGE_MATCHES"

    exit 2
fi

PACKAGE_NAME=$(echo "$PACKAGE_MATCHES" | grep -oP "(?<=package:).*")
echo "Found package '$PACKAGE_NAME'"

# Get full path to package file(s)
PACKAGE_PATH=$(adb shell pm path $PACKAGE_NAME)
RESULT=$?

# Check we actually got a path
if [[ "$PACKAGE_PATH" == "" ]]; then
    echo "Error: Failed to get path(s)"

    exit 3
fi

# Download
echo "Found path(s) for '$PACKAGE_NAME', retrieving"
mkdir "$PACKAGE_NAME"

IFS=$'\n'

for CUR_PATH in $PACKAGE_PATH; do
    CUR_PATH=$(echo "$CUR_PATH" | grep -oP "(?<=package:).*")
    echo "Retrieving $CUR_PATH"
    adb pull "$CUR_PATH" "$PACKAGE_NAME/"
done

