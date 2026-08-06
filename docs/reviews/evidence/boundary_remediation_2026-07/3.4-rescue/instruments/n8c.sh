declare -n a=b
declare -n b=a
A=1 B=$a /bin/echo x
set | grep -c "^A="
