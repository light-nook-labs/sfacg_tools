#!/bin/bash
# Build SFACG Spider for different platforms
# Usage: ./build.sh [desktop|web|apk]

set -e
cd "$(dirname "$0")"

MODE=${1:-desktop}

case "$MODE" in
    desktop)
        echo "Building desktop app..."
        uv run flet pack app.py \
            --name "SFACG Spider" \
            --product-name "SFACG Spider" \
            --product-version "1.0.0" \
            --company-name "SFACG" \
            --add-data "sfacglib:sfacglib" \
            --add-data ".env:." \
            --icon app_icon.png \
            2>/dev/null || \
        uv run flet pack app.py \
            --name "SFACG Spider" \
            --add-data "sfacglib:sfacglib" \
            --add-data ".env:."
        echo "Done: dist/SFACG Spider"
        ;;

    web)
        echo "Building web app..."
        uv run flet publish app.py --app-name "SFACG Spider"
        echo "Done: dist/web"
        ;;

    apk)
        echo "Building Android APK..."
        echo "Requirements: Android SDK, NDK, Java JDK"
        echo ""
        uv run flet build apk \
            --app-name "SFACG Spider" \
            --org-name "com.sfacg.spider" \
            --build-number 1
        echo "Done: build/apk"
        ;;

    ios)
        echo "Building iOS app..."
        echo "Requirements: macOS, Xcode"
        uv run flet build ios \
            --app-name "SFACG Spider" \
            --org-name "com.sfacg.spider" \
            --build-number 1
        echo "Done: build/ios"
        ;;

    *)
        echo "Usage: ./build.sh [desktop|web|apk|ios]"
        exit 1
        ;;
esac
