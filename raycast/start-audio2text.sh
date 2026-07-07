#!/bin/bash

# @raycast.schemaVersion 1
# @raycast.title Start Audio2Text
# @raycast.mode silent
# @raycast.icon 🎙️
# @raycast.packageName Audio2Text

osascript <<'EOF'
tell application "iTerm"
  create window with default profile command "/Users/marksnd/myPythonCode/Audio2Text/web/start.sh"
  activate
end tell
EOF
