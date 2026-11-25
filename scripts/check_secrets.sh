#!/usr/bin/env bash
# Fail if tracked or new files hold Azure subscription or tenant IDs, storage keys or API keys.
# Built-in Azure Policy definition IDs are public and allowed.
set -u
cd "$(dirname "$0")/.."

GUID='[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
POLICY="/providers/Microsoft.Authorization/policy(Set)?Definitions/$GUID"
SELF='scripts/check_secrets.sh'

# Tracked files plus new files Git does not ignore, so it also works before a commit.
files=()
while IFS= read -r f; do
  [ -f "$f" ] && [ "$f" != "$SELF" ] && files+=("$f")
done < <(git ls-files -co --exclude-standard)

failed=0
report() {  # $1 = label, grep output on stdin. Returns 1 on hits (it runs in a pipe subshell).
  local hits
  hits="$(cat)"
  if [ -n "$hits" ]; then
    echo "FAIL: $1"
    echo "$hits" | sed 's/^/  /'
    return 1
  fi
}

# GUIDs (subscription and tenant IDs look like this). Remove policy definition IDs first.
for f in "${files[@]}"; do
  grep -IEn "$GUID" "$f" 2>/dev/null | sed -E "s#$POLICY##g" | grep -E "$GUID" | sed "s#^#$f:#"
done | report "GUID found. Put subscription and tenant IDs in an .example file or an environment variable." || failed=1

grep -IEn 'AccountKey=[A-Za-z0-9+/=]{20,}|[A-Za-z0-9+/]{86}==' "${files[@]}" \
  | report "Storage account key found." || failed=1

grep -IEn 'sk-ant-[A-Za-z0-9_-]{20,}' "${files[@]}" \
  | report "Anthropic API key found." || failed=1

[ "$failed" -eq 0 ] && echo "OK: no secrets found in ${#files[@]} files."
exit "$failed"
