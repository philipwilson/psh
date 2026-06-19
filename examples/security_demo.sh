#!/usr/bin/env psh
#
# security_demo.sh — DELIBERATELY INSECURE. Do not copy these patterns.
#
# This script exists only as input for PSH's static-analysis tools. Every
# construct below is a known anti-pattern that the analyzers should flag:
#
#   psh --security examples/security_demo.sh   # injection / unsafe eval
#   psh --lint     examples/security_demo.sh   # style & robustness
#
# Compare the reports against the comments to see what each tool catches.

# 1. eval on caller-controlled input — the canonical code-injection hole.
#    If $1 is "; rm -rf ~", this runs it.
run_user_expression() {
    eval "result = $1"
    echo "$result"
}

# 2. Unquoted variable used as a command argument. A value containing
#    spaces or globs is re-split and re-globbed at the call site.
remove_path() {
    rm -rf $1
}

# 3. Command substitution spliced unquoted into another command — output
#    with whitespace becomes multiple arguments.
backup_files() {
    cp $(find . -name '*.conf') /backup
}

# 4. Parsing `ls` output, which breaks on spaces and special characters.
for f in $(ls); do
    echo "found: $f"
done

# 5. A predictable, world-readable temp file in a shared directory — a
#    classic symlink/race vulnerability.
echo "secret data" > /tmp/app_scratch.txt

# 6. Building a SQL-ish string by hand from unsanitized input.
user="$1"
query="SELECT * FROM users WHERE name = '$user'"
echo "$query"
