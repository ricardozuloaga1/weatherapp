#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
OUTPUT="${TMPDIR:-/tmp}/weatheravatar-simulator/WeatherAvatar.app"
mkdir -p "$OUTPUT"
SDK="$(xcrun --sdk iphonesimulator --show-sdk-path)"
xcrun swiftc -sdk "$SDK" -target arm64-apple-ios18.0-simulator -module-cache-path "${TMPDIR:-/tmp}/weatheravatar-swift-cache" ios-simulator/App.swift -o "$OUTPUT/WeatherAvatar" -framework UIKit -framework WebKit
cp ios-simulator/Info.plist "$OUTPUT/Info.plist"
codesign --force --sign - "$OUTPUT"
printf '%s\n' "$OUTPUT"
