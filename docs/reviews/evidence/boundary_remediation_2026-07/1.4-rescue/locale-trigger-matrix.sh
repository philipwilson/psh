#!/bin/sh
# Slot 1.4 ruling #1: the FULL locale-warning trigger matrix.
#
# Integrator's discriminator to test: a shell warns when the resolved name that
# failed setlocale originates from the TRIGGER VARIABLE'S OWN NON-EMPTY VALUE —
# not "assignment warns, unset is silent". Case F (`LC_ALL=` empty) is textually
# an assignment yet bash is silent, because the failing name comes from LC_CTYPE.
#
# Usage: locale-trigger-matrix.sh <shell invocation...>
BOGUS=xx_BOGUS.UTF-8

run() {
    label=$1; shift
    envspec=$1; shift
    script=$1; shift
    err=$(env -i PATH="$PATH" HOME="$HOME" $envspec "$@" -c "$script" 2>&1 >/dev/null)
    [ -z "$err" ] && err="<silent>"
    printf '%-42s %s\n' "$label" "$err"
}

echo "### $* ###"

# --- assign a bogus value to each of the four variables ---------------------
run "assign-bogus LC_ALL"      ""  "LC_ALL=$BOGUS; :" "$@"
run "assign-bogus LC_CTYPE"    ""  "LC_CTYPE=$BOGUS; :" "$@"
run "assign-bogus LC_COLLATE"  ""  "LC_COLLATE=$BOGUS; :" "$@"
run "assign-bogus LANG"        ""  "LANG=$BOGUS; :" "$@"

# --- assign EMPTY, exposing a bogus lower-precedence value ------------------
run "empty LC_ALL exposes bogus CTYPE"   "LC_ALL=C LC_CTYPE=$BOGUS" "LC_ALL=; :" "$@"
run "empty LC_CTYPE exposes bogus LANG"  "LC_CTYPE=C LANG=$BOGUS"   "LC_CTYPE=; :" "$@"

# --- unset, exposing a bogus lower-precedence value -------------------------
run "unset LC_ALL exposes bogus CTYPE"   "LC_ALL=C LC_CTYPE=$BOGUS" "unset LC_ALL; :" "$@"
run "unset LC_ALL exposes bogus LANG"    "LC_ALL=C LANG=$BOGUS"     "unset LC_ALL; :" "$@"
run "unset LC_CTYPE exposes bogus LANG"  "LC_CTYPE=C LANG=$BOGUS"   "unset LC_CTYPE; :" "$@"
run "unset LC_COLLATE exposes bogus LANG" "LC_COLLATE=C LANG=$BOGUS" "unset LC_COLLATE; :" "$@"

# --- unset a variable whose OWN value was bogus (nothing new becomes live) --
run "unset bogus LC_CTYPE itself"        "LC_CTYPE=$BOGUS"          "unset LC_CTYPE; :" "$@"

# --- LANG assigned while the categories are unset ---------------------------
run "assign-bogus LANG, categories unset" "" "unset LC_ALL LC_CTYPE LC_COLLATE; LANG=$BOGUS; :" "$@"

# --- startup (value present in the inherited environment) -------------------
run "startup bogus LC_ALL"     "LC_ALL=$BOGUS"     ':' "$@"
run "startup bogus LC_CTYPE"   "LC_CTYPE=$BOGUS"   ':' "$@"
run "startup bogus LC_COLLATE" "LC_COLLATE=$BOGUS" ':' "$@"
run "startup bogus LANG"       "LANG=$BOGUS"       ':' "$@"

# --- temp-env prefix --------------------------------------------------------
run "tempenv prefix bogus LC_CTYPE" "" "LC_CTYPE=$BOGUS true" "$@"
run "tempenv prefix bogus LANG"     "" "LANG=$BOGUS true" "$@"
