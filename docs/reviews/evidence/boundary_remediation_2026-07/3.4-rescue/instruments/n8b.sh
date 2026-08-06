declare -n cyc=cyc 2>/dev/null
A=1 B=$cyc /bin/echo x
set | grep -c "^A="
