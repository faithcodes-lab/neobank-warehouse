#!/usr/bin/env bash
# Enforces the prose conventions in CONTRIBUTING.md.
#
#   ./check-style.sh staged     check staged files and the commit message
#   ./check-style.sh tree       check every tracked file
#
# Exits non zero on any violation, which aborts the commit when run from the hook
# and fails the build when run in CI.

set -uo pipefail

MODE="${1:-tree}"
COMMIT_MSG_FILE="${2:-}"
status=0

# Em dash and en dash. Hyphens are fine, including in ISO dates.
DASHES=$'—|–'

# Files allowed to contain the patterns, because they define or document them.
# Extend per repo by listing paths in .style-ignore, one per line.
EXCLUDE='^(scripts/check-style\.sh|CONTRIBUTING\.md|\.githooks/|\.github/workflows/style\.yml)'

excluded() {
  echo "$1" | grep -qE "$EXCLUDE" && return 0
  [ -f .style-ignore ] && grep -qxF "$1" .style-ignore && return 0
  return 1
}

report() {
  echo "BLOCKED: $1"
  echo "$2"
  echo
  status=1
}

# Text files only, skipping binaries and anything excluded.
text_files() {
  while read -r f; do
    [ -f "$f" ] && grep -Iq . "$f" 2>/dev/null && ! excluded "$f" && echo "$f"
  done
}

check_dashes() {
  local label="$1" files="$2"
  [ -z "$files" ] && return 0
  local hits
  hits=$(echo "$files" | tr '\n' '\0' | xargs -0 grep -InE "$DASHES" 2>/dev/null || true)
  [ -n "$hits" ] && report "$label contains an em or en dash. Use a comma, colon, full stop or parentheses." "$hits"
  return 0
}

case "$MODE" in
  staged)
    files=$(git diff --cached --name-only --diff-filter=ACM | text_files)
    check_dashes "Staged content" "$files"

    if [ -n "$COMMIT_MSG_FILE" ] && [ -f "$COMMIT_MSG_FILE" ]; then
      msg=$(grep -v '^#' "$COMMIT_MSG_FILE")
      if echo "$msg" | grep -qE "$DASHES"; then
        report "Commit message contains an em or en dash." "$msg"
      fi
      subject=$(echo "$msg" | head -1)
      if [ ${#subject} -gt 60 ]; then
        report "Commit subject is ${#subject} chars, limit is 60." "$subject"
      fi
      if echo "$subject" | grep -qE '^[A-Z]'; then
        report "Commit subject should be lower case and imperative." "$subject"
      fi
    fi
    ;;

  tree)
    files=$(git ls-files | text_files)
    check_dashes "Tracked content" "$files"
    ;;

  *)
    echo "usage: $0 [staged|tree] [commit-msg-file]" >&2
    exit 2
    ;;
esac

if [ $status -ne 0 ]; then
  echo "See CONTRIBUTING.md. To override: git commit --no-verify"
fi

exit $status
