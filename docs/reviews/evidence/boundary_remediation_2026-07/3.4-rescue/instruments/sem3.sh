A=1 B=$((1/0)) /bin/echo x
set | grep -c "^A="
