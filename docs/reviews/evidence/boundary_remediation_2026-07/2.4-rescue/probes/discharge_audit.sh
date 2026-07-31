cd /Users/pwilson/src/psh-r2-4
row() { printf '| %-28s | %-6s | %s\n' "$1" "$2" "$3"; }
chk() { # name, path, pattern
  if grep -q "$3" "$2" 2>/dev/null; then row "$1" "PASS" "$2 :: /$3/"; else row "$1" "**FAIL**" "$2 :: /$3/ NOT FOUND"; fi
}
echo "| item | status | instrument (path :: pattern that must match)"
chk "R5-C1 O3 docstring fixed"  tests/conformance/bash/test_syntax_template_timing_conformance.py "RECORD CORRECTION (round 4 . 5)"
chk "R5-C1 non-fork domain"     tests/conformance/bash/test_syntax_template_timing_conformance.py "in the NON-FORK case"
chk "R5-C2 posix-fork pin"      tests/conformance/bash/test_syntax_template_timing_conformance.py "def test_posix_option_times_fork_matrix"
chk "R5-C3 record preserved"     tests/conformance/bash/test_syntax_template_timing_conformance.py "base-identical / not mine"
chk "R5-D guard file"           tests/unit/tooling/test_substitution_abort_guards.py "def test_only_one_raise_site_for_the_abort"
chk "R5-D catcher guard"        tests/unit/tooling/test_substitution_abort_guards.py "def test_only_the_sanctioned_non_fork_catchers_exist"
chk "R5-D rederive guard"       tests/unit/tooling/test_substitution_abort_guards.py "def test_status_mapping_is_not_re_derived_at_frames"
chk "R5-D offenders run"        tests/unit/tooling/test_substitution_abort_guards.py "def test_guard2_bites_on_a_synthetic_second_catcher"
chk "R5-E errexit_suppr arm"    tests/unit/executor/test_child_policy.py "def test_substitution_syntax_abort_errexit_suppressed_arm"
chk "R5-F1 -i -c pin"           tests/conformance/bash/test_syntax_template_timing_conformance.py "def test_interactive_dash_c_channel_disposition"
