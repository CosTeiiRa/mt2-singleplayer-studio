"""Run the portable Studio application without installing a Python package."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

from metin2_studio.__main__ import main


if __name__ == '__main__':
    main()
