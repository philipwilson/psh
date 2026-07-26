declare -A a; a[<(x)]=1; for k in "${!a[@]}"; do echo "key=<$k>"; done
