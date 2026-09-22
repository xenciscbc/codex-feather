"""Structured baselines preserve human Markdown and reject ambiguous evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/feather-handoff/scripts"))
from feather_handoff import baseline


def sample():
    return {"schema_version": 1, "captured_at": "2026-09-12T12:00:00+08:00",
            "git": {"state": "not-repository"},
            "files": [{"path": "src/a.py", "state": "present", "sha256": "a" * 64}]}


class BaselineFormatTest(unittest.TestCase):
    def test_roundtrip_preserves_siblings_and_examples(self):
        text = '# work\r\n\r\n## 詳細紀錄\r\n```text\r\n## 檔案基準\r\n```\r\n## Notes\r\nmanual\r\n'
        saved = baseline.put(text, sample())
        self.assertTrue(saved.startswith(text))
        self.assertEqual(baseline.parse(saved), sample())
        self.assertNotIn('\n', saved.replace('\r\n', ''))
        self.assertEqual(baseline.put(saved, sample()), saved)
        self.assertIsNone(baseline.parse(text))

    def test_invalid_schema_is_not_absent(self):
        for change in [{'schema_version': 2}, {'schema_version': True}, {'captured_at': 'yesterday'},
                       {'files': []}, {'git': {'state': 'available', 'head': 'bad', 'branch': None}}]:
            value = {**sample(), **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                baseline.validate(value)

    def test_invalid_backtick_opener_cannot_hide_baseline(self):
        block = baseline.put('# work\n', sample())
        text = '```bad`\n' + block
        self.assertEqual(baseline.parse(text), sample())
        self.assertEqual(baseline.put(text, sample()), text)
        with self.assertRaises(ValueError):
            baseline.parse(text + block)

    def test_similar_manual_heading_is_preserved(self):
        manual = '# work\n## 檔案基準   \nkeep this manual section\n'
        self.assertIsNone(baseline.parse(manual))
        saved = baseline.put(manual, sample())
        self.assertTrue(saved.startswith(manual))
        self.assertEqual(baseline.parse(saved), sample())

    def test_ambiguous_section_and_duplicate_json_keys(self):
        block = baseline.put('# work\n', sample())
        for text in [block + block, block.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'),
                     block.replace('```json', '```text'), block[:-5]]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                baseline.parse(text)

    def test_unsafe_paths_and_invalid_observations(self):
        for path in ['', '/a', '../a', 'a/../b', 'a\\b', '.git/config', '.feather/handoffs/a.md',
                     'NUL', 'a:b', 'a//b', 'a/*']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                baseline.paths_input([path])
        for observation in [{'state': 'present', 'sha256': 'x'}, {'state': 'unknown'}, {'state': 'missing', 'sha256': 'a' * 64}]:
            value = sample()
            value['files'] = [{'path': 'a', **observation}]
            with self.subTest(observation=observation), self.assertRaises(ValueError):
                baseline.validate(value)


if __name__ == '__main__':
    unittest.main()
