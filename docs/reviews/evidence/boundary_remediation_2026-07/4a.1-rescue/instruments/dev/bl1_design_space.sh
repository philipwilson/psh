#!/opt/homebrew/bin/bash
# BL-1 design space: under a low RLIMIT_NOFILE, (a) what fd does bash give
# {v}>file, and (b) does bash's permanent redirect still succeed?  If bash's
# own numbering shifts under a low limit, psh parking lower cannot break a
# parity that bash itself does not maintain.
set -u
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
printf '%-8s %-22s %-22s %s\n' LIMIT "bash {v}>f => v" "bash exec3+{v} => v" "bash 3 free slots?"
for LIMIT in 24 40 50 63 64 70 256; do
  A=$( ( ulimit -n "$LIMIT"; /opt/homebrew/bin/bash --norc -c \
        "exec {v}> $TMP/a.txt; echo \$v" ) 2>&1 | tr '\n' ' ')
  B=$( ( ulimit -n "$LIMIT"; /opt/homebrew/bin/bash --norc -c \
        "exec 3> $TMP/b.txt; exec {v}> $TMP/c.txt; echo \$v" ) 2>&1 | tr '\n' ' ')
  # How many free fds >= 10 exist at that limit (what psh could park in)?
  C=$( ( ulimit -n "$LIMIT"; /Library/Frameworks/Python.framework/Versions/3.14/bin/python -c "
import fcntl,os,resource
soft,_=resource.getrlimit(resource.RLIMIT_NOFILE)
got=[]
for base in (63,10,3):
    try:
        fd=fcntl.fcntl(1,fcntl.F_DUPFD_CLOEXEC,base); got.append((base,fd)); os.close(fd)
    except OSError as e:
        got.append((base,e.errno))
print('soft=%d %s'%(soft,got))" ) 2>&1 | tr '\n' ' ')
  printf '%-8s %-22s %-22s %s\n' "$LIMIT" "$A" "$B" "$C"
done
