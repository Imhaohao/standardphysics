#!/usr/bin/env bash
# Build SPCore.xcframework (device + simulator, arm64) and the Swift bindings for sp-ffi.
# Run on macOS with Xcode and rustup:  core/scripts/build-xcframework.sh [--debug]
# Output: core/build/SPCore.xcframework and core/build/swift/sp_ffi.swift (add both to the Xcode project).
set -euo pipefail

CORE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$CORE_DIR/build"
PROFILE="release"
CARGO_PROFILE_FLAG="--release"
if [[ "${1:-}" == "--debug" ]]; then
  PROFILE="debug"
  CARGO_PROFILE_FLAG=""
fi

DEVICE_TARGET="aarch64-apple-ios"
SIM_TARGET="aarch64-apple-ios-sim"
LIB_NAME="libsp_ffi.a"
MODULE_NAME="sp_ffiFFI"
FRAMEWORK_NAME="SPCore"

export IPHONEOS_DEPLOYMENT_TARGET="${IPHONEOS_DEPLOYMENT_TARGET:-17.0}"

cd "$CORE_DIR"
rustup target add "$DEVICE_TARGET" "$SIM_TARGET" >/dev/null

echo "Building sp-ffi for $DEVICE_TARGET and $SIM_TARGET ($PROFILE)"
cargo build -p sp-ffi --lib $CARGO_PROFILE_FLAG --target "$DEVICE_TARGET"
cargo build -p sp-ffi --lib $CARGO_PROFILE_FLAG --target "$SIM_TARGET"

echo "Generating Swift bindings"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/swift" "$BUILD_DIR/headers"
cargo run -p sp-ffi --features bindgen --bin uniffi-bindgen -- generate \
  --library "target/$DEVICE_TARGET/$PROFILE/$LIB_NAME" \
  --language swift \
  --out-dir "$BUILD_DIR/swift"

# XCFramework headers: the C header plus a module map named module.modulemap.
cp "$BUILD_DIR/swift/${MODULE_NAME}.h" "$BUILD_DIR/headers/"
cp "$BUILD_DIR/swift/${MODULE_NAME}.modulemap" "$BUILD_DIR/headers/module.modulemap"

echo "Creating $FRAMEWORK_NAME.xcframework"
xcodebuild -create-xcframework \
  -library "target/$DEVICE_TARGET/$PROFILE/$LIB_NAME" -headers "$BUILD_DIR/headers" \
  -library "target/$SIM_TARGET/$PROFILE/$LIB_NAME" -headers "$BUILD_DIR/headers" \
  -output "$BUILD_DIR/$FRAMEWORK_NAME.xcframework"

echo "Done:"
echo "  $BUILD_DIR/$FRAMEWORK_NAME.xcframework"
echo "  $BUILD_DIR/swift/sp_ffi.swift"
