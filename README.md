# claude-reply-review

A [Claude Code](https://code.claude.com) hook that checks each reply Claude writes for clarity, asks Claude to rewrite
replies you couldn't follow, and gives long replies a short summary that is shown under the reply and read aloud.

Claude often understands its own reply because it knows its reasoning and the output of the commands it ran. You see
only the text. This hook has a second Claude model read each reply with only what you see. If part of the reply can't
be followed from that, Claude is asked to write a clearer one.

## What it does

After Claude finishes a reply:

1. A second Claude model, the reviewer, reads the conversation as you see it: your messages and Claude's text, without
   Claude's reasoning, tool calls or tool output.
2. The reviewer lists the questions a careful reader would have and marks each as one of two kinds:
   - **meaning**: you can't tell what part of the reply says or refers to, or what you are asked to do. Examples: a
     name that is never explained, a reference to output you never saw, an unclear "it", a question of yours that is
     not answered.
   - **more_info**: you understand the reply but might want more evidence or detail.
3. If there is at least one "meaning" question, Claude gets those questions and writes a new, complete reply that
   answers them. The new reply is not checked again, so a reply is sent back at most once. "more_info" questions are
   not sent: in testing, a reviewer that could only answer "clear" or "unclear" also sent back clear replies just to
   ask for more evidence.
4. An accepted reply of 100 words or more gets a summary of two or three sentences written by the reviewer. It appears
   as a note under the reply (`Summary: ...`) and is read aloud. Shorter replies are read aloud in full.

| Reply | Note under it | Read aloud |
| :- | :- | :- |
| Sent back | none | nothing |
| Accepted, 100 words or more | summary | the summary |
| Accepted, shorter | none | the whole reply |
| Rewritten after a send-back, 100 words or more | summary, from one extra reviewer call | the summary |
| Rewritten after a send-back, shorter | none | the whole reply |

The reviewer judges only whether you can follow a reply, not whether it is correct.

## Requirements

- Claude Code, logged in. The reviewer runs as `claude -p` and uses your Claude account.
- Python 3.
- macOS for reading aloud, which uses `say`. On other systems the check and the summary note work, and nothing is
  read aloud.

## Install

```bash
git clone https://github.com/dmalhotra/claude-reply-review.git
mkdir -p ~/.claude/hooks
cp claude-reply-review/review-reply.py claude-reply-review/speak-reply.py ~/.claude/hooks/
```

Then add the hook to `~/.claude/settings.json`, merged with any `hooks` you already have:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$HOME/.claude/hooks/review-reply.py\"",
            "timeout": 180,
            "statusMessage": "Checking that the reply is clear"
          }
        ]
      }
    ]
  }
}
```

If Claude Code can't find `python3`, give its full path, for example `/opt/homebrew/bin/python3`.

Sessions you start afterwards use the hook. Sessions that are already running normally load it by themselves; if one
doesn't, type `/hooks` in it and press Esc.

## Use

Work as usual. After each reply, "Checking that the reply is clear" is shown while the reviewer runs.

- When a reply is sent back, a "Stop hook feedback" message lists the questions, and Claude's new reply appears below
  the first one. The first reply stays on screen; read the new one in its place.
- To stop the reading aloud, run `pkill -x say` (inside Claude Code: `! pkill -x say`).
- To turn the hook off, remove its entry from `~/.claude/settings.json`.

## Settings

At the top of `review-reply.py`:

| Name | Default | What it sets |
| :- | :- | :- |
| `MODEL` | `"fable"` | the reviewer model; any name `claude --model` accepts, such as `sonnet`, `haiku` or `opus` |
| `CONTEXT_CHARS` | `8000` | how much of the earlier conversation the reviewer reads, in characters, counted back from your latest message |
| `SHORT_WORDS` | `100` | replies shorter than this get no summary and are read aloud in full |
| `REVIEW` | | the instructions for the check; keep the two question kinds `meaning` and `more_info`, which the script reads |
| `SUMMARY` | | the instructions for the summary |

`REVIEW` describes the user as "a researcher in scientific computing"; change that to describe you. The message Claude
gets when a reply is sent back is in `main()`. Changes take effect from the next reply; nothing needs reloading.

## Time and cost

Measured on 2026-11-02, each check added 4–6 seconds per reply with `sonnet` and 6–13 seconds with `fable`. The extra
summary call for a rewritten reply took about 4 seconds. Each call uses some of your Claude usage.

## Limits

- A reply that is already on screen can't be hidden, so a sent-back reply stays above the rewritten one.
- The reviewer reads the earlier conversation only up to `CONTEXT_CHARS`; older parts are cut off.
- Replies of scripts that run `claude -p` are checked too, and can be sent back.
- If the reviewer fails, for example by timing out, the reply is accepted without a summary, a long reply is not read
  aloud, and the error is appended to `review-reply.log` next to the script.

## Files

- `review-reply.py`: the Stop hook. It reads the conversation from the session's transcript file, runs the reviewer
  with `claude -p` (no tools, no CLAUDE.md or memory, not saved as a session), and then sends the reply back, adds the
  summary note, or accepts the reply.
- `speak-reply.py`: reads the text it is given aloud with `say`, leaving out code blocks, tables, links and markdown
  symbols. New text stops the text still being read.

## License

Apache License 2.0; see [LICENSE](LICENSE).
