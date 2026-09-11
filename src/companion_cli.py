"""PyInstaller entry wrapper for the established Companion CLI package."""

from companion.cli import main


raise SystemExit(main())
