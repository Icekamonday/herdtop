#!/bin/sh
# Refuse a credential or an internal name in the tracked files, and an
# internal name in the commit messages that the upstream lacks. The
# repository leaves the office: neither may reach it. Run it before each
# push; the arguments go to name_scan.py (`--log <range>`).
set -eu
cd "$(dirname "$0")/.."
if git grep -nIE \
    '(password|passwd|secret|api[_-]?key|token)[[:space:]]*[:=][[:space:]]*["'"'"'][A-Za-z0-9+/_-]{8,}|BEGIN[[:space:]].*PRIVATE KEY|glpat-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}' \
    -- ':!scripts/no-secrets.sh'; then
    echo "no-secrets: the lines above look like hardcoded credentials" >&2
    exit 1
fi
python3 scripts/name_scan.py "$@"
echo "no-secrets: clean"
