#!/usr/bin/env python3
# Reads the markdown text on stdin aloud with macOS `say`, leaving out code blocks, tables, links and markdown symbols;
# run by review-reply.py. New text stops the text still being read; `pkill -x say` stops it by hand.
import re
import subprocess
import sys


def speech_text(md):
    lines = []
    for line in re.sub(r"```.*?```", " ", md, flags=re.S).splitlines():
        s = line.strip()
        if s.startswith("|"):
            continue
        s = re.sub(r"^#+\s*", "", s)
        s = re.sub(r"^([-*+]|\d+\.)\s+", "", s)
        lines.append(s)
    text = "\n".join(lines)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = text.replace("**", "").replace("`", "").replace("_", " ").replace("→", " to ")
    return text.strip()


def main():
    text = speech_text(sys.stdin.read())
    subprocess.run(["pkill", "-x", "say"])
    if not text:
        return
    say = subprocess.Popen(["say"], stdin=subprocess.PIPE, start_new_session=True)
    say.stdin.write(text.encode())
    say.stdin.close()


main()
