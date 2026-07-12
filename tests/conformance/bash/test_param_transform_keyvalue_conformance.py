"""Conformance tests for the ${var@K} / ${var@k} transforms (bash).

Pins the L4 fix (reappraisal #7):

  ${arr[@]@K}  -> ONE string: key "value" key "value" ... (values quoted
                 like the @A declare form: double-quoted, $/"/\\/` escaped)
  ${arr[@]@k}  -> SEPARATE fields: key, value, key, value, ... (unquoted)
  ${scalar@K}  -> the @Q-quoted value (single-element behaves like @Q)
  ${arr[i]@K}  -> the @Q-quoted element value

Associative-array cases use a SINGLE key, because bash iterates assoc
arrays in hash order while psh preserves insertion order — multi-key
listings would diverge on ordering, not on the transform itself.
All expectations verified against bash 5.2.
"""


from conformance_framework import ConformanceTest


class TestKeyValueTransformUpper(ConformanceTest):
    """${arr[@]@K}: a single key/value listing string with quoted values."""

    def test_indexed_array_whole(self):
        self.assert_identical_behavior(
            r"""a=(1 2 3); echo "${a[@]@K}" """)

    def test_indexed_array_word_values(self):
        self.assert_identical_behavior(
            r"""a=(zero one two); echo "${a[@]@K}" """)

    def test_value_with_space_is_quoted(self):
        self.assert_identical_behavior(
            r"""a=("a b" c); printf '<%s>' "${a[@]@K}"; echo""")

    def test_value_with_special_chars(self):
        self.assert_identical_behavior(
            r"""a=("x\$y" 'a"b'); echo "${a[@]@K}" """)

    def test_assoc_single_key(self):
        self.assert_identical_behavior(
            r"""declare -A m=([x]="a b"); echo "${m[@]@K}" """)

    def test_scalar(self):
        self.assert_identical_behavior(r"""v=hi; echo "${v@K}" """)

    def test_scalar_with_quote(self):
        self.assert_identical_behavior(r"""v="it's"; echo "${v@K}" """)

    def test_single_element(self):
        self.assert_identical_behavior(
            r"""a=(1 2 3); echo "${a[1]@K}" """)

    def test_unset_is_empty(self):
        self.assert_identical_behavior(
            r"""unset u; echo "[${u@K}]" """)


class TestKeyValueTransformLower(ConformanceTest):
    """${arr[@]@k}: key/value pairs as SEPARATE fields (unquoted)."""

    def test_indexed_array_whole(self):
        self.assert_identical_behavior(
            r"""a=(1 2 3); echo "${a[@]@k}" """)

    def test_fields_are_split(self):
        self.assert_identical_behavior(
            r"""a=("a b" c); for x in "${a[@]@k}"; do echo "<$x>"; done""")

    def test_unquoted_splits_too(self):
        self.assert_identical_behavior(
            r"""a=(1 2 3); echo ${a[@]@k}""")

    def test_assoc_single_key(self):
        self.assert_identical_behavior(
            r"""declare -A m=([x]="a b"); for x in "${m[@]@k}"; do echo "<$x>"; done""")

    def test_scalar_behaves_like_at_q(self):
        self.assert_identical_behavior(r"""v=hi; echo "${v@k}" """)
