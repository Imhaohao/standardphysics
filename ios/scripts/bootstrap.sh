#!/usr/bin/env bash
# Builds the Rust engine for iOS and generates the Xcode project. Run before opening Xcode.
set -euo pipefail
IOS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -d /opt/homebrew/opt/rustup/bin ]]; then
  export PATH="/opt/homebrew/opt/rustup/bin:$PATH"
fi
command -v rustup >/dev/null || { echo "rustup is required: brew install rustup && rustup toolchain install stable"; exit 1; }
IPHONEOS_DEPLOYMENT_TARGET=26.0 "$IOS_DIR/../core/scripts/build-xcframework.sh" "$@"
cd "$IOS_DIR" && xcodegen generate
