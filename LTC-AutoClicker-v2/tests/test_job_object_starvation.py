"""
Windows Job Object Resource Starvation Harness for LTC AutoClicker.
Applies hard Windows Job Object memory and process limits to ensure the application
survives and operates cleanly under constrained operating system conditions.
"""

import os
import sys
import time
import ctypes
from ctypes import wintypes
import subprocess
import unittest

# Win32 Job Object Constants
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
JobObjectExtendedLimitInformation = 9


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class TestJobObjectStarvation(unittest.TestCase):
    def test_run_under_job_object_memory_cap(self):
        """Run application inside a restricted Windows Job Object with a 150MB commit memory cap."""
        kernel32 = ctypes.windll.kernel32

        # 1. Create native Job Object
        h_job = kernel32.CreateJobObjectW(None, None)
        self.assertNotEqual(h_job, 0, "Failed to create Windows Job Object")

        try:
            # 2. Configure 150MB Job Memory Cap
            limit_info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            limit_info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_JOB_MEMORY | JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
            limit_info.JobMemoryLimit = 150 * 1024 * 1024  # 150 MB

            success = kernel32.SetInformationJobObject(
                h_job,
                JobObjectExtendedLimitInformation,
                ctypes.byref(limit_info),
                ctypes.sizeof(limit_info)
            )
            self.assertTrue(success, "Failed to configure Job Object limits")

            # 3. Spawn child process (main.py in test mode)
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            main_py = os.path.join(base_dir, "main.py")

            cmd = [sys.executable, "-c", "import sys, time; sys.path.append(r'" + base_dir + "'); from src.gui import AutoclickerApp; app = AutoclickerApp(); app.withdraw(); app.update(); time.sleep(0.3); app.destroy()"]
            proc = subprocess.Popen(cmd)

            # 4. Assign process to Job Object
            assigned = kernel32.AssignProcessToJobObject(h_job, int(proc._handle))
            self.assertTrue(assigned, "Failed to assign process to Job Object")

            # 5. Wait for clean completion under memory constraints
            exit_code = proc.wait(timeout=10)
            self.assertEqual(exit_code, 0, f"Process failed under Job Object constraints with exit code {exit_code}")

        finally:
            kernel32.CloseHandle(h_job)


if __name__ == "__main__":
    unittest.main()
