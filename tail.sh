#!/usr/bin/env bash
# Colorized tail of the llm-tap log: IN=cyan, THINK=magenta, OUT=green,
# meta dim, non-200 red. Log picked from UPSTREAM's port in the sibling .env.
# Usage: ./tail.sh [logfile]
# (remote: ssh box tail -F /tmp/llm-tap/<port>.jsonl | ./tail.sh /dev/stdin)
DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$DIR/.env" ] && . "$DIR/.env"
PORT="${UPSTREAM##*:}"; PORT="${PORT%%/*}"
LOG="${1:-/tmp/llm-tap/${PORT:-tap}.jsonl}"
tail -n 5 -F "$LOG" | jq -r --unbuffered '
  def delta:
    if .dt == null then "" else
      " +" + (if .dt >= 60
             then "\((.dt/60)|floor)m\(if (.dt % 60 | floor) < 10 then "0" else "" end)\((.dt % 60 | floor))s"
             else "\(.dt | floor)s" end)
    end;
  "\u001b[2m\((.req_ts // .ts)[11:19]) → \(.ts[11:19])\(delta) \(.client) \(.model)\u001b[0m" +
  (if .status != 200 then " \u001b[31mSTATUS \(.status)\u001b[0m" else "" end) +
  "\n  \u001b[36mIN    \(.prompt | gsub("\n"; " ") | .[0:140])\u001b[0m" +
  (if (.reasoning // "") != "" then "\n  \u001b[35mTHINK \(.reasoning | gsub("\n"; " ") | .[0:160])\u001b[0m" else "" end) +
  "\n  \u001b[32mOUT   \(.result | gsub("\n"; " ") | .[0:160])\u001b[0m"'
