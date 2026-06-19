#!/usr/bin/env psh
#
# text_stats.sh — a small but realistic command-line utility.
#
# Reports line / word / character counts for one or more files, with a
# running total, and demonstrates how the pieces of a "real" shell script
# fit together: option parsing with getopts, functions, arrays, arithmetic,
# and formatted output.
#
#   psh examples/text_stats.sh examples/*.sh
#   psh examples/text_stats.sh -w examples/fibonacci.sh   # words only
#   psh examples/text_stats.sh -h
#
# Analyze it:
#   psh --metrics examples/text_stats.sh
#   psh --lint    examples/text_stats.sh

set -u  # treat use of an unset variable as an error (a good default)

# ---------------------------------------------------------------------------
# usage: print help and exit. $0 is the script name; the heredoc keeps the
# message readable.
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: ${0##*/} [-l | -w | -c] [-h] FILE...

  -l   report line counts only
  -w   report word counts only
  -c   report character counts only
  -h   show this help

With no mode flag, all three counts are shown.
EOF
}

# Count fields for one file and print "lines words chars" on stdout — the
# Unix idiom of returning data through standard output rather than mutating
# globals. The caller reads the three numbers back with `read`.
count_file() {
    local file="$1"
    local lines=0 words=0 chars=0 line
    while IFS= read -r line; do
        lines=$((lines + 1))
        # set -- splits the line on IFS; $# is then the word count.
        set -- $line
        words=$((words + $#))
        chars=$((chars + ${#line} + 1))  # +1 for the stripped newline
    done < "$file"
    printf '%d %d %d\n' "$lines" "$words" "$chars"
}

mode="all"
while getopts "lwch" opt; do
    case "$opt" in
        l) mode="lines" ;;
        w) mode="words" ;;
        c) mode="chars" ;;
        h) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done
shift $((OPTIND - 1))

if [ "$#" -eq 0 ]; then
    echo "${0##*/}: no files given" >&2
    usage >&2
    exit 2
fi

# Column header depends on the selected mode.
case "$mode" in
    lines) printf '%8s  %s\n' "lines" "file" ;;
    words) printf '%8s  %s\n' "words" "file" ;;
    chars) printf '%8s  %s\n' "chars" "file" ;;
    all)   printf '%8s %8s %8s  %s\n' "lines" "words" "chars" "file" ;;
esac

total_lines=0 total_words=0 total_chars=0
for file in "$@"; do
    if [ ! -r "$file" ]; then
        echo "${0##*/}: cannot read '$file'" >&2
        continue
    fi
    read lines words chars <<< "$(count_file "$file")"
    total_lines=$((total_lines + lines))
    total_words=$((total_words + words))
    total_chars=$((total_chars + chars))

    case "$mode" in
        lines) printf '%8d  %s\n' "$lines" "$file" ;;
        words) printf '%8d  %s\n' "$words" "$file" ;;
        chars) printf '%8d  %s\n' "$chars" "$file" ;;
        all)   printf '%8d %8d %8d  %s\n' "$lines" "$words" "$chars" "$file" ;;
    esac
done

# Only bother with a total line when more than one file was processed.
if [ "$#" -gt 1 ]; then
    case "$mode" in
        lines) printf '%8d  %s\n' "$total_lines" "total" ;;
        words) printf '%8d  %s\n' "$total_words" "total" ;;
        chars) printf '%8d  %s\n' "$total_chars" "total" ;;
        all)   printf '%8d %8d %8d  %s\n' "$total_lines" "$total_words" "$total_chars" "total" ;;
    esac
fi
