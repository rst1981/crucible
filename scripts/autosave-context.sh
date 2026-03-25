#!/usr/bin/env bash
# Autosave CONTEXT.md to git every 15 minutes
# Scheduled via Windows Task Scheduler — see scripts/README.md

cd "$(dirname "$0")/.." || exit 1

git add CONTEXT.md
if ! git diff --cached --quiet; then
  git commit -m "Auto-save CONTEXT.md [$(date '+%Y-%m-%d %H:%M')]"
  git push
fi
