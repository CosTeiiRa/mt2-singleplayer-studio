"""Run with python -m unittest discover -s tests -t . from the project root."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
