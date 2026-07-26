declare -A a; a["]"]=1; a[x]=2; unset -v 'a["]"]'; echo rc=$?; declare -p a
