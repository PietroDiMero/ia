#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR%/scripts}"
cd "$ROOT_DIR"

LABEL="com.selfimprover.assistant"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"

cat >"$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>cd "$ROOT_DIR" && ./scripts/run_server.sh</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${ROOT_DIR}/logs/launchd.out</string>
  <key>StandardErrorPath</key>
  <string>${ROOT_DIR}/logs/launchd.err</string>
  <key>WorkingDirectory</key>
  <string>${ROOT_DIR}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <!-- Optionally define OPENAI_API_KEY here or via ${ROOT_DIR}/.env -->
  </dict>
</dict>
</plist>
PLIST

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "LaunchAgent installed and loaded: $PLIST"
echo "It will auto-start at login and restart on crash."
