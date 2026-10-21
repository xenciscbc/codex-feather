"""C6: the work header ends at the managed sections' fence-aware ATX heading rule, in reads and updates alike."""
import unittest

from test_handoff_local_fixes import COMPLETED, LocalFixesBase, sha

TITLE = "交接 Foo ✓"
UPDATED = "2026-09-10T09:00:00+08:00"
# Field-like lines in the user's own notes: never header fields, duplicates or update targets.
NOTES = "狀態：完成\n下一步：x\n注意：使用者筆記\n更新：not-a-time\n"


def headings() -> list[str]:
    """ATX headings of every level: zero to three spaces of indent, a space, a tab or nothing after the hashes."""
    result = []
    for level in range(1, 7):
        hashes = "#" * level
        result += [f"{hashes} Notes", f"  {hashes} 筆記", f"   {hashes}\tNotes", f"{hashes}", f" {hashes}\t"]
    return result


# Not headings: four spaces of indent, hashes without a separator, a heading inside a fenced example.
CONTROLS = {"four-space": "    ## Notes", "no-separator": "##Notes", "fenced": "```text\n## Notes"}


def work(heading: str, status="進行中", notes=NOTES, eol="\n", bom=False, close_fence=False) -> bytes:
    text = (f"# {TITLE}\n更新：{UPDATED}\n狀態：{status}\n目標：g\n進度：p\n下一步：n\n\n{heading}\n{notes}"
            + ("```\n" if close_fence else "") + "\n## 詳細紀錄\n證據 ✓\n")
    return (b"\xef\xbb\xbf" if bom else b"") + text.replace("\n", eol).encode("utf-8")


SAMPLE = (1, 7, 13, 19, 20, 26)
VARIANTS = {"lf": {}, "crlf": {"eol": "\r\n"}, "bom": {"bom": True}, "bom-crlf": {"eol": "\r\n", "bom": True}}


class HeaderBoundaryTest(LocalFixesBase):
    def each(self):
        """Every heading with LF; with CRLF and BOM, one heading per level covering each indent and separator."""
        return [(f"{variant}-{index}.md", heading, options)
                for variant, options in VARIANTS.items() for index, heading in enumerate(headings())
                if variant == "lf" or index in SAMPLE]

    def test_list_and_read_end_the_header_at_every_atx_heading(self):
        for name, heading, options in self.each():
            with self.subTest(work=name, heading=heading):
                data = self.put(name, work(heading, **options)).read_bytes()
                read = self.run_tool("read", "--work", name)
                self.assertEqual((read["status"], read["problems"], read["record_status"]), ("ok", [], "進行中"))
                self.assertEqual((read["title"], read["updated"], read["next"], read["notes"]), (TITLE, UPDATED, "n", ""))
                self.assertEqual(read["version"], sha(data))
                self.assertEqual((self.directory / name).read_bytes(), data)
        listed = self.run_tool("list")
        self.assertTrue(listed["complete"], listed["issues"])
        self.assertEqual({item["status"] for item in listed["items"]}, {"進行中"})
        self.assertEqual({item["next"] for item in listed["items"]}, {"n"})

    def test_partial_update_replaces_and_inserts_header_fields_and_keeps_the_body(self):
        for name, heading, options in self.each():
            with self.subTest(work=name, heading=heading):
                data = self.put(name, work(heading, **options)).read_bytes()
                eol = options.get("eol", "\n")
                updated = self.run_tool("update", "--work", name, payload={
                    "version": sha(data), "fields": {"status": "受阻", "next": "m", "notes": "z", "updated": COMPLETED}})
                self.assertEqual((updated["status"], updated["work_status"], updated["next"], updated["notes"]),
                                 ("ok", "受阻", "m", "z"))
                expected = data.replace(f"更新：{UPDATED}{eol}狀態：進行中{eol}".encode(), f"更新：{COMPLETED}{eol}狀態：受阻{eol}".encode())
                expected = expected.replace(f"下一步：n{eol}{eol}".encode(), f"下一步：m{eol}注意：z{eol}{eol}".encode(), 1)
                self.assertEqual((self.directory / name).read_bytes(), expected)
                body = data[data.index(f"{eol}{heading}{eol}".encode("utf-8")):]
                self.assertTrue(expected.endswith(body))

    def test_completion_archives_the_body_with_its_notes(self):
        for name, heading, options in self.each():
            with self.subTest(work=name, heading=heading):
                data = self.put(name, work(heading, **options)).read_bytes()
                eol = options.get("eol", "\n")
                if self.history.exists():
                    self.history.unlink()
                completed = self.run_tool("update", "--work", name, payload={
                    "version": sha(data), "fields": {"status": "完成", "updated": COMPLETED}})
                self.assertEqual((completed["status"], completed["archived"]), ("ok", True))
                self.assertEqual((completed["title"], completed["completed"]), (TITLE, COMPLETED))
                self.assertFalse((self.directory / name).exists())
                saved = data.replace(f"更新：{UPDATED}{eol}狀態：進行中".encode(), f"更新：{COMPLETED}{eol}狀態：完成".encode())
                body = saved.split(b"\n", 1)[1]
                self.assertTrue(self.history.read_bytes().endswith(
                    f"## {TITLE} · 完成：{COMPLETED}\n".encode("utf-8") + body))

    def test_archive_round_trip_keeps_a_completed_body_byte_for_byte(self):
        for name, heading, options in self.each():
            with self.subTest(work=name, heading=heading):
                if self.history.exists():
                    self.history.unlink()
                data = self.put(name, work(heading, status="完成", notes="狀態：進行中\n下一步：x\n", **options)).read_bytes()
                listed = self.run_tool("list")
                self.assertEqual([item["record_status"] for item in listed["items"] if item["work"] == name], ["完成待歸檔"])
                archived = self.run_tool("archive", "--work", name, payload={"version": sha(data)})
                self.assertEqual((archived["status"], archived["title"], archived["completed"]), ("ok", TITLE, UPDATED))
                self.assertEqual(self.history.read_bytes().split(f"## {TITLE} · 完成：{UPDATED}\n".encode("utf-8"), 1)[1],
                                 data.split(b"\n", 1)[1])
                entries = self.run_tool("history")["entries"]
                self.assertEqual([(entry["title"], entry["completed"]) for entry in entries], [(TITLE, UPDATED)])

    def test_details_update_after_an_indented_heading_keeps_the_notes(self):
        data = self.put("a.md", work("  ## Notes")).read_bytes()
        updated = self.run_tool("update", "--work", "a.md", payload={
            "version": sha(data), "details": "新證據", "fields": {"updated": UPDATED}})
        self.assertEqual(updated["preserved_sections"], [])
        self.assertEqual((self.directory / "a.md").read_bytes(),
                         data.replace("證據 ✓".encode(), "新證據".encode()))


class HeaderBoundaryControlTest(LocalFixesBase):
    def test_non_headings_keep_field_like_lines_in_the_header(self):
        for label, line in CONTROLS.items():
            with self.subTest(label):
                name = f"{label}.md"
                data = self.put(name, work(line, close_fence=label == "fenced")).read_bytes()
                read = self.run_tool("read", "--work", name, expected=2)
                self.assertEqual((read["status"], read["record_status"]), ("partial", "格式待確認"))
                self.assertIn("Expected one nonempty 狀態 field", read["problems"])
                self.assertIn("Expected one nonempty 下一步 field", read["problems"])
                refused = self.run_tool("update", "--work", name, expected=2,
                                        payload={"version": sha(data), "fields": {"next": "m"}})
                self.assertEqual(refused["code"], "format")
                self.assertIn("Duplicate 下一步", refused["message"])
                self.assertEqual((self.directory / name).read_bytes(), data)

    def test_genuine_header_duplicates_are_still_reported(self):
        data = self.put("a.md", work("  ## Notes").replace("目標：g\n".encode(), "目標：g\n狀態：受阻\n".encode())).read_bytes()
        read = self.run_tool("read", "--work", "a.md", expected=2)
        self.assertIn("Expected one nonempty 狀態 field", read["problems"])
        refused = self.run_tool("update", "--work", "a.md", expected=2,
                                payload={"version": sha(data), "fields": {"status": "受阻"}})
        self.assertIn("Duplicate 狀態", refused["message"])
        self.assertEqual((self.directory / "a.md").read_bytes(), data)

    def test_blank_and_displaced_titles_are_still_reported(self):
        for label, data, problem in (
                ("blank", work("  ## Notes").replace(f"# {TITLE}\n".encode(), b"#  \t\n"), "Work title must not be blank"),
                ("displaced", b"intro\n" + work("  ## Notes"),
                 "Work title must be the first line; preceding content needs review")):
            with self.subTest(label):
                self.put("a.md", data)
                read = self.run_tool("read", "--work", "a.md", expected=2)
                self.assertIn(problem, read["problems"])
                self.assertNotIn("Expected one nonempty 狀態 field", read["problems"])
                listed = self.run_tool("list", expected=2)
                self.assertIn(problem, listed["issues"][0]["message"])
                self.assertEqual((self.directory / "a.md").read_bytes(), data)


class HeaderLineEndingTest(LocalFixesBase):
    """Header lines end only at LF (or CRLF): characters str.splitlines breaks on stay inside a field value."""

    VALUES = ("see # 1", "see\x0b# 1", "see\x0c# 1", "see\x1c# 1", "see\x1d# 1", "see\x1e# 1", "see\x85# 1",
              "see # 1", "see # 1", "x ```", "x\x0c```", "x\x85~~~", "x ```")

    def test_field_values_with_unicode_line_separators_read_and_update_intact(self):
        for index, value in enumerate(self.VALUES):
            with self.subTest(value=value):
                name = f"v{index}.md"
                created = self.run_tool("create", "--work", name,
                                        payload={"title": TITLE, "details": "證據",
                                                 "fields": {"goal": value, "progress": "p", "next": "n"}})
                self.assertEqual(created["status"], "ok")
                before = (self.directory / name).read_bytes()
                read = self.run_tool("read", "--work", name)
                self.assertEqual((read["status"], read["problems"]), ("ok", []))
                self.assertEqual((read["goal"], read["progress"], read["next"]), (value, "p", "n"))
                updated = self.run_tool("update", "--work", name, payload={
                    "version": read["version"], "fields": {"notes": "z", "updated": read["updated"]}})
                self.assertEqual((updated["status"], updated["goal"], updated["notes"]), ("ok", value, "z"))
                self.assertEqual((self.directory / name).read_bytes(),
                                 before.replace("下一步：n\n".encode(), "下一步：n\n注意：z\n".encode(), 1))


class HeaderFenceTest(LocalFixesBase):
    """A fence in the header hides headings: closed, the header ends at the next real heading; open, at the end."""

    def data(self, closed: bool) -> bytes:
        return (f"# {TITLE}\n更新：{UPDATED}\n狀態：進行中\n目標：g\n進度：p\n下一步：n\n\n```text\n## not a heading\n"
                + ("```\n" if closed else "") + "  ## Notes\n注意：after the heading\n\n## 詳細紀錄\n決策：late\n").encode()

    def test_closed_fence_in_the_header_ends_it_at_the_following_heading(self):
        data = self.put("a.md", self.data(closed=True)).read_bytes()
        read = self.run_tool("read", "--work", "a.md")
        self.assertEqual((read["status"], read["problems"], read["notes"], read["decision"]), ("ok", [], "", ""))
        updated = self.run_tool("update", "--work", "a.md",
                                payload={"version": sha(data), "fields": {"status": "受阻", "updated": UPDATED}})
        self.assertEqual(updated["work_status"], "受阻")
        self.assertEqual((self.directory / "a.md").read_bytes(), data.replace("狀態：進行中".encode(), "狀態：受阻".encode()))

    def test_unclosed_fence_in_the_header_runs_it_to_the_end_of_the_file(self):
        data = self.put("a.md", self.data(closed=False)).read_bytes()
        read = self.run_tool("read", "--work", "a.md")
        self.assertEqual((read["status"], read["problems"]), ("ok", []))
        self.assertEqual((read["notes"], read["decision"]), ("after the heading", "late"))
        updated = self.run_tool("update", "--work", "a.md",
                                payload={"version": sha(data), "fields": {"decision": "now", "updated": UPDATED}})
        self.assertEqual(updated["decision"], "now")
        self.assertEqual((self.directory / "a.md").read_bytes(), data.replace("決策：late".encode(), "決策：now".encode()))


if __name__ == "__main__":
    unittest.main()
