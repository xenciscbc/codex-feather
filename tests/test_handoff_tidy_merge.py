"""Handoff tidy ticket 01: the bundled handoff tool, unchanged, carries both merge shapes through its public command.

A partial move writes the target (create for a new record, update for an existing one) and reads it back before the
moved items leave the source; a full merge then completes the source, which the tool archives into history; a gate
note restricting moved and remaining items is copied word for word and stays in the active source (spec Acceptance
item 9, Testing Decisions). Two merges into one target are carried by sequential updates, the second made with the
version the first returned and built from the content it saved (handoff tidy write edges spec, Acceptance item 5)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/handoff/scripts/handoff.py"

ITEM_A = "- 項目A：核對 readiness 端點的 timeout。"
ITEM_B = "- 項目B：補上 port 設定的說明。"
ITEM_C = "- 項目C：清理舊的 log 設定。"
ITEM_D = "- 項目D：統一 log 的輪替週期。"
EVIDENCE = "### 證據\nport=7319 已於 2026-09-11 核對。"
GATE_NOTE = "pending acceptance: claim X（項目A 與 項目B 尚待驗收，未經 code review）"
SIBLING = "## 詳細紀錄補充\n人工補充保留。\n"


def source_record(items: list[str], gate_note: str | None = None) -> str:
    details = "### 待辦項目\n" + "\n".join(items) + "\n\n" + EVIDENCE + "\n"
    if gate_note:
        details += "\n" + gate_note + "\n"
    return ("# config-audit\n更新：2026-09-11T10:00:00+08:00\n狀態：進行中\n\n"
            "目標：核對設定\n進度：port=7319；readiness 待確認。\n下一步：核對 readiness\n"
            "注意：timeout 等待使用者決定。\n\n## 詳細紀錄\n" + details + "\n" + SIBLING)


def details_of(content: str) -> str:
    """The text of a record's details section, as a write built from that content starts from."""
    return content.split("\n## 詳細紀錄\n", 1)[1].split("\n## ", 1)[0]


def remaining_details(items: list[str], gate_note: str | None = None) -> str:
    details = "### 待辦項目\n" + "\n".join(items) + "\n\n" + EVIDENCE + "\n"
    if gate_note:
        details += "\n" + gate_note + "\n"
    return details


class HandoffTidyMergeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(os.path.realpath(self.temporary.name))
        self.directory = self.project / ".feather/handoffs"
        self.directory.mkdir(parents=True)
        self.source = self.directory / "config-audit.md"

    def run_tool(self, *args, payload=None, expected=0) -> dict:
        # --exact-root keeps every operation inside the temporary project, never the repository's own .feather/.
        result = subprocess.run(
            [sys.executable, "-B", str(TOOL), "--project", str(self.project), "--exact-root", *args],
            input=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def read(self, work: str) -> dict:
        return self.run_tool("read", "--work", work)

    def write_source(self, content: str) -> bytes:
        data = content.encode("utf-8")
        self.source.write_bytes(data)
        return data

    def create_existing_target(self) -> None:
        self.run_tool("create", "--work", "readiness.md", payload={
            "title": "readiness", "fields": {"goal": "整理 readiness 檢查", "progress": "已列出既有檢查。",
                                             "next": "補齊 timeout 檢查"},
            "details": "### 待辦項目\n- 既有項目：列出 readiness 檢查。\n"})

    def remove_moved_items_from_source(self, remaining: list[str], gate_note: str | None = None) -> dict:
        current = self.read(self.source.name)
        return self.run_tool("update", "--work", self.source.name, payload={
            "version": current["version"], "details": remaining_details(remaining, gate_note)})

    def assert_source_keeps_only(self, remaining: list[str], moved: list[str]) -> dict:
        read = self.read(self.source.name)
        content = read["content"]
        for item in remaining:
            self.assertIn(item, content)
        for item in moved:
            self.assertNotIn(item, content)
        # The source's other fields and sections are intact.
        self.assertEqual(read["goal"], "核對設定")
        self.assertEqual(read["progress"], "port=7319；readiness 待確認。")
        self.assertEqual(read["next"], "核對 readiness")
        self.assertEqual(read["notes"], "timeout 等待使用者決定。")
        self.assertIn(EVIDENCE, content)
        self.assertTrue(content.endswith(SIBLING), content)
        self.assertEqual(read["record_status"], "進行中")
        return read

    def test_partial_move_into_a_new_target_writes_and_reads_it_back_before_the_source(self):
        original = self.write_source(source_record([ITEM_A, ITEM_B, ITEM_C]))
        created = self.run_tool("create", "--work", "readiness.md", payload={
            "title": "readiness", "fields": {"goal": "整理 readiness 檢查", "progress": "自 config-audit 移入。",
                                             "next": "核對 timeout"},
            "details": "### 待辦項目\n" + ITEM_A + "\n"})
        self.assertEqual(created["status"], "ok")
        target = self.read("readiness.md")
        self.assertIn(ITEM_A, target["content"])
        self.assertEqual(target["version"], created["version"])
        self.assertEqual(self.source.read_bytes(), original, "the source changes only after the target is read back")

        updated = self.remove_moved_items_from_source([ITEM_B, ITEM_C])
        self.assertEqual(updated["status"], "ok")
        self.assert_source_keeps_only([ITEM_B, ITEM_C], [ITEM_A])
        self.assertIn(ITEM_A, self.read("readiness.md")["content"])

    def test_partial_move_into_an_existing_target_updates_and_reads_it_back_before_the_source(self):
        self.create_existing_target()
        original = self.write_source(source_record([ITEM_A, ITEM_B, ITEM_C]))
        before = self.read("readiness.md")
        moved = self.run_tool("update", "--work", "readiness.md", payload={
            "version": before["version"],
            "details": "### 待辦項目\n- 既有項目：列出 readiness 檢查。\n" + ITEM_A + "\n"})
        self.assertEqual(moved["status"], "ok")
        target = self.read("readiness.md")
        self.assertIn(ITEM_A, target["content"])
        self.assertIn("- 既有項目：列出 readiness 檢查。", target["content"])
        self.assertEqual(target["goal"], "整理 readiness 檢查")
        self.assertEqual(self.source.read_bytes(), original, "the source changes only after the target is read back")

        self.remove_moved_items_from_source([ITEM_B, ITEM_C])
        self.assert_source_keeps_only([ITEM_B, ITEM_C], [ITEM_A])

    def test_full_merge_completes_and_archives_the_source_into_history(self):
        self.create_existing_target()
        original = self.write_source(source_record([ITEM_A, ITEM_B, ITEM_C]))
        before = self.read("readiness.md")
        self.run_tool("update", "--work", "readiness.md", payload={
            "version": before["version"],
            "details": "### 待辦項目\n- 既有項目：列出 readiness 檢查。\n" + "\n".join([ITEM_A, ITEM_B, ITEM_C]) + "\n"})
        target = self.read("readiness.md")
        for item in (ITEM_A, ITEM_B, ITEM_C):
            self.assertIn(item, target["content"])
        self.assertEqual(self.source.read_bytes(), original, "the source changes only after the target is read back")

        progress = "已全部併入 readiness.md，本紀錄無剩餘工作。"
        current = self.read(self.source.name)
        completed = self.run_tool("update", "--work", self.source.name, payload={
            "version": current["version"],
            "fields": {"status": "完成", "progress": progress, "next": "無"},
            "details": "### 已移出項目\n項目A、項目B、項目C 已移至 readiness.md。\n\n" + EVIDENCE + "\n"})
        self.assertEqual(completed["status"], "ok", completed)
        self.assertTrue(completed["archived"])
        self.assertTrue(completed["history_appended"])
        self.assertFalse(self.source.exists())

        listed = self.run_tool("list")
        self.assertTrue(listed["complete"])
        self.assertEqual([item["work"] for item in listed["items"]], ["readiness.md"])

        history = self.run_tool("history", "--work", "config-audit")
        self.assertTrue(history["complete"])
        self.assertEqual(len(history["entries"]), 1)
        entry = history["entries"][0]
        self.assertEqual(entry["title"], "config-audit")
        self.assertIn("狀態：完成", entry["body"])
        self.assertIn("進度：" + progress, entry["body"])
        self.assertIn("readiness.md", entry["body"])

    def test_gate_note_is_copied_word_for_word_and_the_source_stays_active(self):
        self.write_source(source_record([ITEM_A, ITEM_B, ITEM_C], GATE_NOTE))
        original = self.source.read_bytes()
        self.run_tool("create", "--work", "readiness.md", payload={
            "title": "readiness", "fields": {"goal": "整理 readiness 檢查", "progress": "自 config-audit 移入。",
                                             "next": "核對 timeout"},
            "details": "### 待辦項目\n" + ITEM_A + "\n\n" + GATE_NOTE + "\n"})
        target = self.read("readiness.md")
        self.assertIn(ITEM_A, target["content"])
        self.assertIn("\n" + GATE_NOTE + "\n", target["content"])
        self.assertEqual(self.source.read_bytes(), original, "the source changes only after the target is read back")

        # Item B, which the note restricts, remains, so the note stays in the source.
        self.remove_moved_items_from_source([ITEM_B, ITEM_C], GATE_NOTE)
        source = self.assert_source_keeps_only([ITEM_B, ITEM_C], [ITEM_A])
        self.assertIn("\n" + GATE_NOTE + "\n", source["content"])
        self.assertIn("\n狀態：進行中\n", source["content"])

        listed = self.run_tool("list")
        self.assertEqual({item["work"]: item["record_status"] for item in listed["items"]},
                         {"config-audit.md": "進行中", "readiness.md": "進行中"})
        self.assertEqual(self.run_tool("history")["status"], "missing")
        self.assertFalse((self.directory / "history.md").exists())

    def test_two_merges_into_one_target_keep_the_first_when_the_second_is_built_from_its_saved_content(self):
        # Handoff tidy write edges (0.27.1), Acceptance item 5: the second write compares with the version the tool
        # reported for the first and is built from the content the first saved, so the first merge is kept; the
        # version noted when proposing no longer matches.
        self.create_existing_target()
        self.write_source(source_record([ITEM_A, ITEM_B, ITEM_C], GATE_NOTE))
        second_source = self.directory / "log-cleanup.md"
        second_source.write_bytes(
            ("# log-cleanup\n更新：2026-09-12T09:00:00+08:00\n狀態：進行中\n\n目標：清理 log\n進度：已列出。\n"
             "下一步：移入 readiness\n\n## 詳細紀錄\n### 待辦項目\n" + ITEM_D + "\n").encode("utf-8"))
        noted = self.read("readiness.md")

        # The first merge moves item A, with the gate note restricting it, built from the content read when noted.
        first = self.run_tool("update", "--work", "readiness.md", payload={
            "version": noted["version"],
            "details": details_of(noted["content"]) + ITEM_A + "\n\n" + GATE_NOTE + "\n"})
        self.assertEqual(first["status"], "ok", first)
        self.assertNotEqual(first["version"], noted["version"])

        # An update with the version noted before the first write is refused and changes nothing.
        stale = self.run_tool("update", "--work", "readiness.md", expected=2, payload={
            "version": noted["version"],
            "details": details_of(noted["content"]) + "\n### 自 log-cleanup 移入\n" + ITEM_D + "\n"})
        self.assertEqual((stale["status"], stale["code"]), ("error", "conflict"), stale)
        current = self.read("readiness.md")
        self.assertEqual(current["version"], first["version"])
        self.assertEqual(current["content"], first["content"])

        # The second merge compares with the version the first reported and is built from the content it saved.
        second = self.run_tool("update", "--work", "readiness.md", payload={
            "version": first["version"],
            "details": details_of(first["content"]) + "\n### 自 log-cleanup 移入\n" + ITEM_D + "\n"})
        self.assertEqual(second["status"], "ok", second)
        target = self.read("readiness.md")
        self.assertEqual(target["version"], second["version"])
        content = target["content"]
        for line in ("- 既有項目：列出 readiness 檢查。", ITEM_A, ITEM_D):
            self.assertEqual(content.count(line), 1, line)
        self.assertEqual(content.count("\n" + GATE_NOTE + "\n"), 1)
        self.assertNotIn(ITEM_B, content)
        self.assertEqual(target["goal"], "整理 readiness 檢查")
        self.assertEqual(target["record_status"], "進行中")


if __name__ == "__main__":
    unittest.main()
