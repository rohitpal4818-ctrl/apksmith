#!/usr/bin/env bash
# Fetch the sample APK used by the integration tests.
#
# The integration tests skip cleanly when this file is absent, so running them
# without it is fine. This exists so a contributor can opt into the tests that
# need a real APK.
#
# F-Droid is open source (Apache-2.0) and is used as a known-good baseline:
# a legitimate app that should not produce a wall of false positives.

set -euo pipefail

APK_URL="https://f-droid.org/F-Droid.apk"
DEST="$(dirname "$0")/../samples/F-Droid.apk"

mkdir -p "$(dirname "$DEST")"

echo "downloading $(basename "$DEST") (~12 MB) ..."
curl -L --fail --progress-bar "$APK_URL" -o "$DEST"

echo "done: $DEST"
echo
echo "Now run:  pytest"