from pathlib import Path

attempts_file = Path("attempts.txt")
attempts = int(attempts_file.read_text(encoding="utf-8")) if attempts_file.exists() else 0
attempts += 1
attempts_file.write_text(str(attempts) + "\n", encoding="utf-8")

if attempts <= 2:
    raise SystemExit("temporary failure: target release-check dependency unavailable")

print("unexpected success: retry bound exceeded")
