#!/opt/homebrew/bin/bash
# Does the bare-exit saved-status rule apply to NON-EXIT traps too?
B=/opt/homebrew/bin/bash
P="python -m psh --norc"
cells=(
  'trap "false; exit" USR1; kill -USR1 $$; sleep 0.2; exit 3'
  'trap "true; exit" USR1; false; kill -USR1 $$; sleep 0.2; exit 3'
  'trap "echo entry=\$?; false; exit" USR1; kill -USR1 $$; sleep 0.2; exit 3'
  'trap "false; exit" USR1; kill -USR1 $$; sleep 0.2'
)
for c in "${cells[@]}"; do
  bo=$($B --norc --noprofile -c "$c" 2>&1); br=$?
  po=$(cd "$PSH_ROOT" && PYTHONPATH="$PSH_ROOT" python -m psh --norc -c "$c" 2>&1); pr=$?
  if [ "$bo|$br" = "$po|$pr" ]; then m="OK  "; else m="DIFF"; fi
  printf '%s %-62s bash=(%s,%s) psh=(%s,%s)\n' "$m" "$c" "$bo" "$br" "$po" "$pr"
done
