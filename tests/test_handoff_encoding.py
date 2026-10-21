"""The public JSON protocol stays UTF-8 under a legacy Windows-style process encoding."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TOOL = Path(__file__).resolve().parents[1] / "skills/handoff/scripts/handoff.py"


class HandoffEncodingTest(unittest.TestCase):
    def test_read_emits_utf8_with_legacy_stdout_encoding(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            record = project / ".feather/handoffs/work.md"
            record.parent.mkdir(parents=True)
            content = ("# 服務核對\n更新：2026-10-21T10:00:00+08:00\n狀態：進行中\n"
                       "目標：核對設定\n進度：等待驗收。\n下一步：保留待決項目。\n")
            record.write_bytes(content.encode("utf-8"))
            for encoding in ("cp950", "cp1252"):
                with self.subTest(encoding=encoding):
                    environment = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": encoding}
                    result = subprocess.run(
                        [sys.executable, "-B", str(TOOL), "--project", str(project), "--exact-root",
                         "read", "--work", "work.md"],
                        capture_output=True, env=environment, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    output = json.loads(result.stdout.decode("utf-8"))
                    self.assertEqual(output["content"], content)
                    self.assertEqual(output["work_status"], "進行中")
