declare -A a; a["]"]=V; echo "${a["]"]:-d}"; echo "${a[absent]:-d}"
