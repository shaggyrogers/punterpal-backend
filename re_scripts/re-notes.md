# Notes

## Setup

* Install android SDK
* Download android w/ google play (used API 32)
* Set up AVD (used pixel 9)
* Root AVD using https://gitlab.com/newbit/rootAVD (will install required magisk)
* Install mitmproxy
* Run mitmweb
* Start AVD with proxy (see script)
* In AVD browse to http://mitm.it/cert/magisk to download magisk module with root certificate, then open magisk and install
* Maybe need to also copy ~/.mitmproxy/mitmproxy-ca-cert.cer to phone and install in settings?

### Device

Rooting S21 needed specific odin version (3.13.1)
Same as above but use proxy in wifi settings

# Viewing logs

    adb logcat main

# Patching APK

Add android SDK tools to path

    export PATH=$PATH:$HOME/Android/Sdk/platform-tools
    export PATH=$PATH:$HOME/Android/Sdk/emulator
    export PATH=$PATH:$HOME/Android/Sdk/build-tools/34.0.0

## Modification Process

* Find stuff to modify (use jadx-gui)
* Decompile with apktool d
* Find corresponding smali representation, make changes
  - Useful cheatsheet here: https://sallam.gitbook.io/sec-88/android-appsec/smali/smali-cheat-sheet
* Recompile with apktool b
* Sign
* Install

## Signing

Just need to run once, password for this one is 'password'

    keytool -genkey -v -keystore my-release-key.keystore -alias alias_name -keyalg RSA -keysize 2048 -validity 10000

Then sign

    apksigner sign -verbose -ks my-release-key.keystore apk-name.apk

## Installing

If split use install-multiple:

    adb install-multiple -r ladbrokes_recomp.apk split_config.xxhdpi.apk split_config.x86_64.apk

# RE Notes

## Location

* Need to spoof location using emulator settings
  - Confirm worked by checking in maps

## Mitmproxy

* Apps can just ignore proxy settings...
  - Using "Super Proxy" or other app that uses VPN to force adherence to proxy settings works
  - Issues with cert pinning? Some requests fail likely due to client not trusting proxy ca cert
  - Frida script exists to bypass cert pinning, not guaranteed to work, some apps may need manual patching

## Ladbrokes/Neds

Requests use persistedQuery scheme where the "query" part of the request is hashed.
Might be possible to patch APK to prevent app from using persistedQuery scheme.
Replaying requests might be an option but will be annoying to implement and require updates if anything new is added.

- Patched smali/zb/c.smali to disable persistedQuery - no effect
- Other options
  + Patch Other candidates, maybe add logging?
  + Intercept cfg request or patch cfg code and change persistedQuery to false
    - Try intercept feature in mitmproxy

        https://www.ladbrokes.com.au/cfg/android.json
        change api.graphql.persistedQueries to false

  + Hash is the same for same kind of request, only variables change!

Neds seems to just be a clone of Ladbrokes

## Bluebet, Palmerbet

These don't connect, maybe cert pinning?

android-api.bluebet.com.au
fixture.palmerbet.online

Both flutter apps

### Flutter Cert Pinning Patch

Try this, seems to mostly work for bluebet, but sports A-Z won't load

    https://github.com/NVISOsecurity/disable-flutter-tls-verification

* Add APK tools to PATH (see above)
* Copy and run Frida server
  - See `start-frida-server.sh`
* Find APK name e.g. palmerbet:

    > adb shell
    > ps -A | grep palm
     [ ... ] com.palmerbet.mobile.android

* Inject bypass

    frida -U --codeshare TheDauntless/disable-flutter-tls-v1 -f com.palmerbet.mobile.android


### Bluebet

* Sports AZ doesn't load
  - Try get sport IDs from finding response data in memory dump, or trial and error?

### Palmerbet - Bot Detection

* ~~Check for *any* differences in request (maybe cookie header case, or HTTP version?)~~
* ~~Maybe context matters? e.g. cookie must be associated with specific initial request(s)~~

* Works if using mitmproxy! Also confirmed that HTTP requests are identical... issue is in SSL/TLS layer
* Maybe TLS version, or TLS cipher? Want TLSv1.3 / `TLS_AES_256_GCM_SHA384`
  - See examples here:
    + https://urllib3.readthedocs.io/en/stable/advanced-usage.html#custom-ssl-contexts
    + https://master-spring-ter.medium.com/understanding-tls-versions-a-comprehensive-guide-791e599e181c

#### Decrypting TLS Scraper Traffic w/ Wireshark

Start wireshark

    export SSLKEYLOGFILE=/home/michael/ssl-keylog-file.txt
    pipenv run

Wireshark: Under Edit > Preferences > Protocols > TLS > (Pre)-Master-Secret log filename, browse to SSLKEYLOGFILE
