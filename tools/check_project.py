"""Dependency-free syntax checks for local development and CI."""
from pathlib import Path
import ast
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
paths = list(root.glob('*.py')) + list((root / 'tests').glob('*.py')) + list((root / 'tools').glob('*.py'))
for path in paths:
    ast.parse(path.read_text('utf-8-sig'), filename=str(path))
for path in (root / 'web').glob('*.js'):
    subprocess.run(['node', '--check', str(path)], check=True)
print(f'Python syntax: {len(paths)} files; JavaScript syntax: all web scripts passed.')
