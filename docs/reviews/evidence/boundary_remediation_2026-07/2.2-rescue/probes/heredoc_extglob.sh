shopt -s extglob
cat <<EOF
$(echo @(a|b))
EOF
