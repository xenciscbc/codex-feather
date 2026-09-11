"""Selected history mutations through the public CLI."""
import unittest
import os
from tests import test_handoff_tool as fixtures

RECORD = fixtures.RECORD


class HistoryMutationsTest(unittest.TestCase):
    setUp = fixtures.HandoffToolTest.setUp
    run_tool = fixtures.HandoffToolTest.run_tool
    write_work = fixtures.HandoffToolTest.write_work
    snapshot = fixtures.HandoffToolTest.snapshot
    def prepare_history(self):
        self.write_work()
        first = "## first · 完成：2026-09-11T10:00:00+08:00\n" + RECORD
        second = "## second · 完成：2026-09-11T11:00:00+08:00\n" + RECORD
        path = self.write_work("history.md", "# 交接歷史\n\n" + first + second)
        return path, first, second, self.run_tool("history")["entries"]

    def test_clear_exact_selection_preserves_remainder_and_refuses_stale_retry(self):
        path, first, second, entries = self.prepare_history()
        selection = {"version": entries[0]["document_version"], "ids": [entries[0]["id"]]}
        result = self.run_tool("clear", payload=selection)
        self.assertTrue(result["complete"])
        self.assertEqual(path.read_bytes(), ("# 交接歷史\n\n" + second).encode())
        before = self.snapshot()
        self.run_tool("clear", payload=selection, expected=2)
        self.assertEqual(before, self.snapshot())
        self.assertEqual((self.directory / "config-audit.md").read_bytes(), RECORD.encode())

    def test_clear_requires_explicit_sealed_source_and_preserves_ambiguous_history(self):
        path, first, second, entries = self.prepare_history()
        archive = self.directory / "archive"
        archive.mkdir()
        sealed = archive / "batch.md"
        sealed.write_bytes(path.read_bytes())
        self.run_tool("clear", payload={"version": entries[0]["document_version"],
                      "ids": [e["id"] for e in entries]})
        self.assertEqual(path.read_text(encoding="utf-8"), "# 交接歷史\n\n")
        self.assertIn(first.encode(), sealed.read_bytes())
        self.run_tool("clear", payload={"source": "archive/batch.md", "version": entries[0]["document_version"],
                      "ids": [entries[0]["id"]]})
        self.assertEqual(sealed.read_bytes(), ("# 交接歷史\n\n" + second).encode())
        path.write_text("# 交接歷史\n\nunknown content\n" + first, encoding="utf-8")
        ambiguous = self.run_tool("history", expected=2)["entries"][0]
        before = self.snapshot()
        self.run_tool("clear", payload={"version": ambiguous["document_version"],
                      "ids": [ambiguous["id"]]}, expected=2)
        self.assertEqual(before, self.snapshot())

    def test_seal_preserves_order_and_refuses_destination_conflicts(self):
        path, first, second, entries = self.prepare_history()
        payload = {"version": entries[0]["document_version"], "ids": [entries[0]["id"]],
                   "destination": "batch.md"}
        result = self.run_tool("seal", payload=payload)
        self.assertTrue(result["complete"])
        destination = self.directory / "archive/batch.md"
        self.assertEqual(destination.read_bytes(), ("# 交接歷史\n\n" + first).encode())
        self.assertEqual(path.read_bytes(), ("# 交接歷史\n\n" + second).encode())
        current = self.run_tool("history")["entries"][0]
        before = self.snapshot()
        self.run_tool("seal", payload={**payload, "version": current["document_version"],
                      "ids": [current["id"]]}, expected=2)
        self.assertEqual(before, self.snapshot())

    def test_seal_defers_for_completed_source_on_first_attempt_and_retry(self):
        work = self.write_work(content=RECORD.replace("狀態：進行中", "狀態：完成"))
        body = work.read_bytes().split(b"\n", 1)[1]
        entry = "## config-audit · 完成：2026-09-11T10:00:00+08:00\n".encode() + body
        history = self.write_work("history.md", "# 交接歷史\n\n")
        history.write_bytes(history.read_bytes() + entry)
        selected = self.run_tool("history")["entries"][0]
        payload = {"version": selected["document_version"], "ids": [selected["id"]],
                   "destination": "batch.md"}
        before = self.snapshot()
        result = self.run_tool("seal", payload=payload, expected=2)
        self.assertEqual(result["code"], "pending-archive")
        self.assertEqual(before, self.snapshot())
        destination = self.directory / "archive/batch.md"
        destination.parent.mkdir()
        destination.write_bytes(history.read_bytes())
        before = self.snapshot()
        self.run_tool("seal", payload=payload, expected=2)
        self.assertEqual(before, self.snapshot())
        self.run_tool("archive", "--work", work.name,
                      payload={"version": self.run_tool("read", "--work", work.name)["version"]})
        result = self.run_tool("seal", payload=payload)
        self.assertTrue(result["complete"])
        self.assertEqual(history.read_bytes(), "# 交接歷史\n\n".encode())

    def test_seal_reports_different_trailing_body_bytes_as_conflict(self):
        work = self.write_work(content=RECORD.replace("狀態：進行中", "狀態：完成"))
        body = work.read_bytes().split(b"\n", 1)[1]
        history = self.write_work("history.md", "# 交接歷史\n\n")
        history.write_bytes(history.read_bytes() +
                           "## config-audit · 完成：2026-09-11T10:00:00+08:00\n".encode() + body + b"\n")
        entry = self.run_tool("history")["entries"][0]
        before = self.snapshot()
        result = self.run_tool("seal", payload={"version": entry["document_version"],
                               "ids": [entry["id"]], "destination": "batch.md"}, expected=2)
        self.assertEqual(result["code"], "conflict")
        self.assertEqual(before, self.snapshot())

    @unittest.skipUnless(os.name == "nt", "Windows sharing denial is platform-specific")
    def test_failed_clear_and_seal_retain_sources_then_retry_exact_selection(self):
        path, first, second, entries = self.prepare_history()
        selected = {"version": entries[0]["document_version"], "ids": [entries[0]["id"]]}
        original = path.read_bytes()
        with path.open("rb"):
            failed = self.run_tool("clear", payload=selected, expected=2)
            self.assertEqual(failed["source_version"], selected["version"])
            self.assertEqual(failed["state"], "unchanged")
            self.assertIn("recovery", failed)
            result = self.run_tool("seal", payload={**selected, "destination": "retry.md"}, expected=2)
        self.assertEqual(path.read_bytes(), original)
        destination = self.directory / "archive/retry.md"
        saved = destination.read_bytes()
        self.assertEqual(saved, ("# 交接歷史\n\n" + first).encode())
        retry = {**selected, "destination": "retry.md", "destination_version": result["destination_version"]}
        result = self.run_tool("seal", payload=retry)
        self.assertEqual(destination.read_bytes(), saved)
        self.assertEqual(path.read_bytes(), ("# 交接歷史\n\n" + second).encode())
        # Recovery after source was removed but final acknowledgement was lost.
        self.run_tool("seal", payload={**retry, "version": result["version"]})
        self.assertEqual(destination.read_bytes(), saved)
        self.assertEqual(path.read_bytes(), ("# 交接歷史\n\n" + second).encode())
