"""Bounded handling of brief Windows reader/scanner sharing conflicts."""
import time


def retry_windows_lock(operation, *arguments):
    for attempt in range(5):
        try:
            return operation(*arguments)
        except PermissionError as error:
            if getattr(error, 'winerror', None) not in (5, 32, 33) or attempt == 4:
                raise
            time.sleep(.025 * 2 ** attempt)
