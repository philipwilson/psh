unset A
A=1 B=$((A=9)) C=$((1/0)) /bin/echo x
set | grep -q "^A=" && echo LEAK || echo CLEAN
