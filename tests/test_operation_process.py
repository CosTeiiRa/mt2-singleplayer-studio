import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from metin2_studio.operation_process import process_identity, previous_build_running


class ProcessIdentityTests(unittest.TestCase):
    def test_current_process_has_stable_creation_identity(self):
        identity = process_identity(os.getpid())
        self.assertTrue(identity)
        self.assertEqual(process_identity(os.getpid()), identity)
        self.assertTrue(previous_build_running({'pid': os.getpid(), 'identity': identity}))
        self.assertFalse(previous_build_running({'pid': os.getpid(), 'identity': identity + '-different'}))

    def test_finished_child_is_not_treated_as_a_running_build(self):
        process = subprocess.Popen([sys.executable, '-c', 'pass'])
        process.wait(timeout=10)
        self.assertIsNone(process_identity(process.pid))
        self.assertFalse(previous_build_running({'pid': process.pid, 'identity': 'old'}))

    def test_unknown_previous_identity_stays_blocked_while_that_pid_is_running(self):
        self.assertTrue(previous_build_running({'pid': os.getpid(), 'identity': None}))
        self.assertFalse(previous_build_running(None))
