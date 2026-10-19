"""Command entry points shared by the portable launcher and Python package."""
import sys


def main():
    command = sys.argv.pop(1) if len(sys.argv) > 1 and sys.argv[1] in ('serve', 'setup') else 'serve'
    if command == 'setup':
        from .setup_studio import main as run
    else:
        from .server import main as run
    run()


if __name__ == '__main__':
    main()
