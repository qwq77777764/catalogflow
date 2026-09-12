"""PyInstaller entry point; no user configuration is read during bundle analysis."""

if __name__ == "__main__":
    from multiprocessing import freeze_support

    freeze_support()

    from catalogflow.desktop import main

    raise SystemExit(main())
