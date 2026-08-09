#!/opt/homebrew/bin/bash
# Command-generated instrument manifest, SELF-EXCLUDING (this script and the
# manifest it writes are not listed as instruments).
cd "$(dirname "$0")" || exit 2
{
  echo "# Slot 5C.1 instrument manifest"
  echo "# generated: $(date -u +%Y-%m-%dT%H:%M:%SZ) by MANIFEST.sh (self-excluding)"
  echo "# tree: $(cd ../.. && git rev-parse HEAD)"
  echo
  printf '%-40s %-34s %s\n' "FILE" "MD5" "KIND"
  for f in $(ls | grep -vE '^(MANIFEST\.sh|MANIFEST\.md5)$' | sort); do
    case "$f" in
      *_COPY.py) kind="READ-ONLY copy of a committed instrument" ;;
      *.out|*.txt) kind="transcript" ;;
      *.py|*.sh)   kind="instrument" ;;
      *)           kind="other" ;;
    esac
    printf '%-40s %-34s %s\n' "$f" "$(md5 -q "$f")" "$kind"
  done
  echo
  echo "instruments: $(ls | grep -E '\.(py|sh)$' | grep -vE '^MANIFEST\.sh$' | wc -l | tr -d ' ')"
  echo "transcripts: $(ls | grep -E '\.out$' | wc -l | tr -d ' ')"
} > MANIFEST.md5
cat MANIFEST.md5
