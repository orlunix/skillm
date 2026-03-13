#!/usr/bin/env bash
#
# Package skillm into a standalone binary.
#
# Usage:
#   ./package.sh                     # build only
#   ./package.sh --install           # build + install to /usr/local/bin
#   ./package.sh --install-to /path  # build + install to custom path
#
# Requirements: Python 3.10+ (only for building, not for running the binary)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

NAME="skillm"
ENTRY="skillm_entry.py"
DIST="dist/$NAME"

# ── Helpers ──────────────────────────────────────────────

info()  { echo -e "\033[32m[+]\033[0m $*"; }
warn()  { echo -e "\033[33m[!]\033[0m $*"; }
error() { echo -e "\033[31m[-]\033[0m $*"; exit 1; }

# ── Check prerequisites ─────────────────────────────────

command -v python3 >/dev/null 2>&1 || error "python3 not found"

PYTHON=python3
PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    error "Python 3.10+ required (found $PY_VERSION)"
fi

info "Using Python $PY_VERSION"

# ── Set up build venv ────────────────────────────────────

BUILD_VENV="$SCRIPT_DIR/.build-venv"

if [ ! -d "$BUILD_VENV" ]; then
    info "Creating build virtualenv..."
    $PYTHON -m venv "$BUILD_VENV"
fi

# shellcheck disable=SC1091
source "$BUILD_VENV/bin/activate"

info "Installing dependencies..."
pip install -q -e . pyinstaller

# ── Build ────────────────────────────────────────────────

info "Building standalone binary..."
pyinstaller \
    --onefile \
    --name "$NAME" \
    --collect-submodules=skillm \
    --distpath dist \
    --workpath build/pyinstaller \
    --specpath build \
    --clean \
    --noconfirm \
    "$ENTRY" 2>&1 | grep -E "(INFO: Building|completed|Build complete)" || true

if [ ! -f "$DIST" ]; then
    error "Build failed — $DIST not found"
fi

SIZE=$(du -h "$DIST" | cut -f1)
info "Built: $DIST ($SIZE)"

# ── Verify ───────────────────────────────────────────────

info "Verifying..."
VERSION=$("$DIST" --version 2>&1) || error "Binary failed to run"
info "Version: $VERSION"

# ── Install (optional) ──────────────────────────────────

INSTALL_PATH=""

while [ $# -gt 0 ]; do
    case "$1" in
        --install)
            INSTALL_PATH="/usr/local/bin"
            shift
            ;;
        --install-to)
            INSTALL_PATH="$2"
            shift 2
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

if [ -n "$INSTALL_PATH" ]; then
    TARGET="$INSTALL_PATH/$NAME"

    if [ "$INSTALL_PATH" = "/usr/local/bin" ] && [ "$(id -u)" -ne 0 ]; then
        info "Installing to $TARGET (requires sudo)..."
        sudo cp "$DIST" "$TARGET"
        sudo chmod 755 "$TARGET"
    else
        mkdir -p "$INSTALL_PATH"
        info "Installing to $TARGET..."
        cp "$DIST" "$TARGET"
        chmod 755 "$TARGET"
    fi

    info "Installed: $TARGET"
    "$TARGET" --version
fi

# ── Done ─────────────────────────────────────────────────

deactivate 2>/dev/null || true

echo ""
info "Done! Binary at: $DIST"
echo ""
echo "  To install globally:    sudo cp $DIST /usr/local/bin/$NAME"
echo "  To install to shared:   cp $DIST /home/prgn_share/bin/$NAME"
echo ""
