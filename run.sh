#!/usr/bin/env bash
# Launch the Automated Printing System
# Uses XCB/X11 backend which works reliably on both Wayland (via XWayland) and X11.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export QT_QPA_PLATFORM=xcb
export QT_LOGGING_RULES="qt.qpa.wayland=false"

exec .venv/bin/python -m app.main "$@"
