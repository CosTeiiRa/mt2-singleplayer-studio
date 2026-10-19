from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from metin2_studio.database import query


class DatabaseTests(unittest.TestCase):
    def test_read_only_transaction_and_no_credentials_in_sql(self):
        good = SimpleNamespace(returncode=0, stdout='{"set":"test","row":[1]}\n')
        with patch('metin2_studio.database.subprocess.run', return_value=good) as run:
            self.assertEqual(query(Path('.'), ['SELECT 1;']), {'test': [[1]]})
        sql = run.call_args.kwargs['input']
        self.assertIn('SET TRANSACTION READ ONLY', sql)
        self.assertIn('WITH CONSISTENT SNAPSHOT', sql)
        self.assertTrue(sql.endswith('ROLLBACK;'))
        self.assertNotIn('password', sql.lower())

    def test_stopped_docker_has_actionable_sanitized_error(self):
        failed = SimpleNamespace(returncode=1, stdout='', stderr='private-secret failed to connect to the docker API')
        with patch('metin2_studio.database.subprocess.run', return_value=failed), self.assertRaisesRegex(ValueError, 'Open Docker Desktop') as error:
            query(Path('.'), ['SELECT 1;'])
        self.assertNotIn('private-secret', str(error.exception))

    def test_query_errors_are_sanitized(self):
        failed = SimpleNamespace(returncode=1, stdout='', stderr='private-secret')
        with patch('metin2_studio.database.subprocess.run', return_value=failed), self.assertRaisesRegex(ValueError, 'read-only database') as error:
            query(Path('.'), ['SELECT 1;'])
        self.assertNotIn('private-secret', str(error.exception))
