"""Bash `[[ ]]` parallels of the POSIX test/[ file-operator cluster.

`[[ ]]` is a bash extension, not POSIX. These cases were extracted from
``tests/conformance/posix/test_test_file_operators_conformance.py`` (finding C1
of the 2026-07-06 tests/docs appraisal: keep bash-only syntax out of the POSIX
conformance tree). The POSIX ``test``/``[`` forms of the same behaviors stay in
that file; here we pin that the enhanced ``[[ ]]`` form agrees with bash for the
same operators.
"""


from conformance_framework import ConformanceTest


class TestEnhancedFilePerms(ConformanceTest):
    """[[ -r/-w/-x/-s ]] hold for directories and special files, like bash."""

    def test_enhanced_x_on_dir(self):
        self.assert_identical_behavior('mkdir d; [[ -x d ]]; echo $?')

    def test_enhanced_r_on_dev_null(self):
        self.assert_identical_behavior('[[ -r /dev/null ]]; echo $?')

    def test_enhanced_s_on_dir(self):
        self.assert_identical_behavior('mkdir d; [[ -s d ]]; echo $?')


class TestEnhancedNtOt(ConformanceTest):
    """[[ f1 -nt/-ot f2 ]] honor bash's existence-asymmetry rule."""

    def test_enhanced_nt_rebuild_idiom(self):
        self.assert_identical_behavior('touch src; [[ src -nt missing ]]; echo $?')

    def test_enhanced_ot_source_missing(self):
        self.assert_identical_behavior('touch b; [[ a -ot b ]]; echo $?')
