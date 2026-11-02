#!/usr/bin/env python3
# Stop hook: a second Claude model reads Claude's last reply as the user sees it: the conversation text, without
# Claude's reasoning or tool output. If the reply would leave the user with questions, the hook blocks the stop and
# sends the questions back, and Claude writes a clearer reply; that reply is not reviewed again. A reply of at least
# SHORT_WORDS words that is not sent back gets a summary written by the same model, shown as a note under the reply
# and read aloud by speak-reply.py; a shorter reply is read aloud in full. If the reviewer fails, the reply is accepted
# without a summary and the error is appended to review-reply.log.
import json
import os
import re
import shutil
import subprocess
import sys
import time

HOOKS = os.path.dirname(os.path.abspath(__file__))
MODEL = "fable"
CONTEXT_CHARS = 8000  # earlier conversation passed to the reviewer, counted from the end
SHORT_WORDS = 100

CONTEXT = """\
You read a reply written by an AI coding assistant before the user reads it. The user sees only the conversation \
text given to you: their own messages and the assistant's text. They do not see the assistant's reasoning, and tool \
calls and tool output are hidden."""

REVIEW = """\
Decide whether the user can fully understand the latest reply from what they see. List the questions a careful \
reader would have after reading the latest reply, most important first, at most 5, one sentence each, and give each \
one a kind:
- "meaning": the user cannot tell what part of the reply says or refers to, or what they are asked to do. For \
example: a term, abbreviation, name, file or setting used without explanation that the user cannot be expected to \
know (the user is a researcher in scientific computing); a reference to something the user has not seen, such as tool \
output or a decision made in reasoning; an "it", "this" or "that" whose meaning is unclear; an explanation with a \
missing step; a question from the user that is not answered; an instruction or question to the user that can be read \
in more than one way.
- "more_info": the user understands the reply but might want more evidence, measurements, detail or alternatives, or \
might doubt whether it is correct.
Use "meaning" only when the user cannot follow the reply without the answer; when in doubt, use "more_info". A name \
the user used in their own messages is known to them.
Do not list questions about style, length, tone or formatting, or about things the conversation shows the user \
already knows. Return an empty list when the reader would have no real question; a short reply can be clear."""

SUMMARY = """\
Write a summary of the latest reply to be read aloud to the user: two or three short sentences in plain spoken \
words, with no code, commands, file paths, symbols or markdown. Say what was found or done and what, if anything, \
the user is asked to decide or do, and keep every caveat that changes what the user should do. Use only what the \
reply says."""

QUESTIONS = {"type": "array", "items": {
    "type": "object",
    "properties": {"question": {"type": "string"}, "kind": {"enum": ["meaning", "more_info"]}},
    "required": ["question", "kind"]}}


def visible_messages(transcript_path):
    # (role, text) of what the user sees: their prompts and Claude's text, not tool calls or tool output
    msgs = []
    with open(transcript_path) as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("type") not in ("user", "assistant") or r.get("isSidechain") or r.get("isMeta"):
                continue
            c = (r.get("message") or {}).get("content")
            if isinstance(c, list):
                c = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
            text = re.sub(r"<system-reminder>.*?</system-reminder>", "", c or "", flags=re.S).strip()
            if text:
                msgs.append((r["type"], text))
    return msgs


def review_prompt(msgs, reply):
    last_user = max((i for i, (role, _) in enumerate(msgs) if role == "user"), default=None)
    if last_user is None:
        return "Latest reply:\n" + reply
    fmt = lambda ms: "\n\n".join(("User: " if role == "user" else "Assistant: ") + text for role, text in ms)
    this_turn = [m for m in msgs[last_user + 1:] if m[1] != reply.strip()]
    earlier = fmt(msgs[:last_user])[-CONTEXT_CHARS:]
    return (f"Earlier conversation (the user has read it):\n{earlier or '(none)'}\n\n"
            f"User's latest message:\n{msgs[last_user][1]}\n\n"
            f"Assistant's text earlier in this turn (the user has read it):\n{fmt(this_turn) or '(none)'}\n\n"
            f"Latest reply:\n{reply}")


def ask_reviewer(hook_input, reply, review, summarize):
    # the "meaning" questions about the reply (if review) and its spoken summary (if summarize)
    parts = [CONTEXT]
    props = {}
    if review:
        parts.append(REVIEW)
        props["questions"] = QUESTIONS
    if summarize:
        parts.append(SUMMARY)
        props["summary"] = {"type": "string"}
    schema = {"type": "object", "properties": props, "required": list(props)}
    claude = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
    out = subprocess.run(
        [claude, "-p", "--model", MODEL, "--tools", "", "--no-session-persistence", "--output-format", "json",
         "--json-schema", json.dumps(schema), "--system-prompt", "\n\n".join(parts)],
        input=review_prompt(visible_messages(hook_input["transcript_path"]), reply), capture_output=True, text=True,
        timeout=150, env={**os.environ, "CLAUDE_REPLY_REVIEW": "1", "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
                          "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"})
    res = json.loads(out.stdout)["structured_output"]
    return [q["question"] for q in res.get("questions", []) if q["kind"] == "meaning"], res.get("summary", "")


def speak(text):
    subprocess.run([sys.executable, os.path.join(HOOKS, "speak-reply.py")], input=text.encode())


def main():
    if os.environ.get("CLAUDE_REPLY_REVIEW"):  # the reviewer's own session
        return
    hook_input = json.load(sys.stdin)
    reply = hook_input.get("last_assistant_message") or ""
    review = not hook_input.get("stop_hook_active")  # a reply written after a send-back is only summarized
    short = len(reply.split()) < SHORT_WORDS
    if not reply.strip() or (short and not review):
        speak(reply)
        return
    try:
        qs, summary = ask_reviewer(hook_input, reply, review, not short)
    except Exception as e:
        with open(os.path.join(HOOKS, "review-reply.log"), "a") as log:
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {type(e).__name__}: {e}\n")
        qs, summary = [], ""
    if qs:
        print(json.dumps({"decision": "block", "reason": (
            "A reviewer read your reply as the user sees it, without your reasoning or tool output. These points "
            "would be unclear to the user:\n" + "\n".join(f"{i + 1}. {q}" for i, q in enumerate(qs)) +
            "\nWrite a new, complete reply that answers them and can be read on its own in place of the previous one. "
            "Run tools only if you need them to answer. Do not mention this review.")}))
        return
    if short:
        speak(reply)
        return
    if summary:
        print(json.dumps({"systemMessage": "Summary: " + summary}))
    speak(summary)


main()
