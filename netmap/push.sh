#!/usr/bin/env bash
# Push netmap to GitHub. Run from inside the netmap/ folder:
#   ./push.sh                         # uses defaults below
#   ./push.sh "<repo-url>" <branch> "<commit message>"
set -euo pipefail

REPO="${1:-https://github.com/nont-naraphat/netmap.git}"
BRANCH="${2:-main}"
MSG="${3:-update netmap}"

# first-time init
if [ ! -d .git ]; then
  git init
  git branch -M "$BRANCH"
fi

# point origin at the repo (add or update)
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REPO"
else
  git remote add origin "$REPO"
fi

git add -A
if git diff --cached --quiet; then
  echo "nothing to commit"
else
  git commit -m "$MSG"
fi

# push (sets upstream on first run)
git push -u origin "$BRANCH"
echo "done -> $REPO ($BRANCH)"
