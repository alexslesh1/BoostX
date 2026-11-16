#!/bin/sh
# Builds both binaries. Needs only Go; works from macOS, Linux or Windows (Git Bash).
#
#   ./build.sh
#
# Output:
#   ../src/boostx/resources/engine/   nexora-engine.exe + WinDivert (what the desktop app starts)
#   dist/linux/                       nexora-relay for x86-64 and arm64 servers
set -eu
cd "$(dirname "$0")"

flags='-trimpath -buildvcs=false'
engine_dir=../src/boostx/resources/engine
mkdir -p "$engine_dir" dist/linux

CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build $flags -ldflags '-s -w' -o "$engine_dir/nexora-engine.exe" ./cmd/nexora-engine
cp third_party/windivert/WinDivert64.dll third_party/windivert/WinDivert64.sys "$engine_dir/"
cp third_party/windivert/NOTICE.txt "$engine_dir/WinDivert-NOTICE.txt"

CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build $flags -ldflags '-s -w' -o dist/linux/nexora-relay ./cmd/nexora-relay
CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build $flags -ldflags '-s -w' -o dist/linux/nexora-relay-arm64 ./cmd/nexora-relay

echo "engine: $engine_dir"
echo "relay:  dist/linux"
