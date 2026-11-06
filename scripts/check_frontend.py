from html.parser import HTMLParser
from pathlib import Path
import subprocess


class ScriptParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag != "script":
            return

        attributes = dict(attrs)
        self.current = [] if "src" not in attributes else None

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.current is not None:
            self.scripts.append("".join(self.current))
            self.current = None


root = Path(__file__).resolve().parents[1]
checked = 0

for folder in ("frontend", "tools"):
    for html_file in sorted((root / folder).rglob("*.html")):
        parser = ScriptParser()
        parser.feed(html_file.read_text(encoding="utf-8"))

        for index, script in enumerate(parser.scripts, start=1):
            if not script.strip():
                continue

            result = subprocess.run(
                ["node", "--check"],
                input=script,
                text=True,
                encoding="utf-8",
                capture_output=True,
            )

            if result.returncode != 0:
                raise SystemExit(
                    f"{html_file.relative_to(root)}, script {index}:\n"
                    f"{result.stderr}"
                )

            checked += 1

if checked == 0:
    raise SystemExit("No inline JavaScript found to check.")

print(f"JavaScript syntax checks passed: {checked}")