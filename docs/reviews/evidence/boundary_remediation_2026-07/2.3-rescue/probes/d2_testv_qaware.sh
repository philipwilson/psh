declare -A a; a["]"]=1; test -v 'a["]"]'; echo rc=$?
