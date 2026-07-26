shopt -s extglob
a=($(echo @(a|b)))
echo "${a[@]}"
