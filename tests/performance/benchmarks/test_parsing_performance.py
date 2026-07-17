"""
Performance benchmarks for PSH parsing speed.

Tests parsing performance with various sizes and complexities of input
to ensure PSH maintains reasonable performance.

Tier classification (campaign E1b audit, 2026-07-17): the two timing classes
below are CPU-time MICROBENCHMARKS (millisecond thresholds) — they carry
``benchmark`` + ``serial`` markers, are excluded from every standard-gate
phase, and run via ``python run_tests.py --benchmarks``.
``TestLargeInputRobustness`` (formerly misleadingly named ``TestMemoryUsage``
while measuring no memory) contains deterministic no-timing invariants and
runs in the standard gate.

Measurement discipline (v0.313.0): wall-clock timing flakes under load
(e.g. xdist worker contention), so these benchmarks measure
``time.process_time()`` — CPU time consumed by this process only, immune
to preemption — and take the min over the sampled iterations to discard
cache-cold or GC-interrupted runs. Algorithmic regressions (e.g. O(N^2)
blowup) show identically in CPU time.
"""

import time

import pytest

from psh.lexer import tokenize
from psh.parser import Parser


@pytest.mark.benchmark
@pytest.mark.serial
class TestParsingPerformance:
    """Benchmark parsing performance."""

    def measure_parse_time(self, script: str, iterations: int = 100) -> float:
        """Measure min-of-iterations CPU time to parse a script."""
        times = []

        for _ in range(iterations):
            start = time.process_time()
            parser = Parser(tokenize(script))
            parser.parse()
            end = time.process_time()
            times.append(end - start)

        return min(times)

    def test_simple_command_performance(self):
        """Test parsing performance of simple commands."""
        # Single command
        single_time = self.measure_parse_time("echo hello world")
        assert single_time < 0.001  # Should parse in under 1ms

        # 100 simple commands
        script_100 = "\n".join(f"echo line{i}" for i in range(100))
        time_100 = self.measure_parse_time(script_100, iterations=10)
        assert time_100 < 0.01  # Should parse in under 10ms

        # 1000 simple commands
        script_1000 = "\n".join(f"echo line{i}" for i in range(1000))
        time_1000 = self.measure_parse_time(script_1000, iterations=10)
        assert time_1000 < 0.1  # Should parse in under 100ms

        # Verify linear scaling
        ratio = time_1000 / time_100
        assert 8 < ratio < 12  # Should scale roughly linearly

    def test_complex_structure_performance(self):
        """Test parsing performance of complex structures."""
        # Nested if statements
        nested_if = """
if true; then
    if true; then
        if true; then
            if true; then
                echo "deeply nested"
            fi
        fi
    fi
fi
"""
        nested_time = self.measure_parse_time(nested_if * 10)
        assert nested_time < 0.01  # Should handle nesting efficiently

        # Complex pipeline
        pipeline = "echo start | grep a | sed s/a/b/ | awk '{print}' | sort | uniq | tail -n 10"
        pipeline_time = self.measure_parse_time(pipeline * 10)
        assert pipeline_time < 0.01

        # Large case statement
        case_stmt = """
case $x in
""" + "\n".join(f'    pattern{i}) echo "match{i}" ;;' for i in range(50)) + """
    *) echo "default" ;;
esac
"""
        case_time = self.measure_parse_time(case_stmt)
        assert case_time < 0.01

    def test_string_parsing_performance(self):
        """Test performance of parsing strings with escapes."""
        # Long string with escapes
        escaped = '"' + ("hello\\nworld\\t" * 100) + '"'
        escaped_time = self.measure_parse_time(f"echo {escaped}")
        assert escaped_time < 0.005

        # Many quoted strings
        many_quotes = " ".join(f'"string{i}"' for i in range(100))
        quotes_time = self.measure_parse_time(f"echo {many_quotes}")
        assert quotes_time < 0.01

    def test_expansion_parsing_performance(self):
        """Test performance of parsing various expansions."""
        # Variable expansions
        var_expansion = " ".join(f"${{var{i}:-default}}" for i in range(50))
        var_time = self.measure_parse_time(f"echo {var_expansion}")
        assert var_time < 0.01

        # Command substitutions
        cmd_sub = " ".join(f"$(echo {i})" for i in range(20))
        sub_time = self.measure_parse_time(f"echo {cmd_sub}")
        assert sub_time < 0.01

        # Arithmetic expansions
        arith = " ".join(f"$((i + {i}))" for i in range(50))
        arith_time = self.measure_parse_time(f"echo {arith}")
        assert arith_time < 0.01

    def test_real_script_performance(self):
        """Test parsing performance on realistic scripts."""
        # Typical shell script
        real_script = '''
#!/bin/bash
# Process some files

SOURCE_DIR="${1:-/tmp/source}"
DEST_DIR="${2:-/tmp/dest}"

if [ ! -d "$SOURCE_DIR" ]; then
    echo "Source directory does not exist"
    exit 1
fi

mkdir -p "$DEST_DIR"

for file in "$SOURCE_DIR"/*.txt; do
    if [ -f "$file" ]; then
        basename=$(basename "$file")
        echo "Processing $basename..."

        # Process the file
        grep -v "^#" "$file" | \
            sed 's/[[:space:]]*$//' | \
            awk '{if (NF > 0) print}' > "$DEST_DIR/$basename"

        if [ $? -eq 0 ]; then
            echo "Successfully processed $basename"
        else
            echo "Failed to process $basename" >&2
        fi
    fi
done

echo "Processing complete"
'''
        script_time = self.measure_parse_time(real_script, iterations=50)
        assert script_time < 0.005  # Should parse quickly

    @pytest.mark.xfail(reason="PSH parser doesn't handle deeply nested parentheses")
    def test_pathological_cases(self):
        """Test performance on pathological inputs."""
        # Deeply nested parentheses
        deep_parens = "echo " + "(" * 50 + "value" + ")" * 50
        parens_time = self.measure_parse_time(deep_parens)
        assert parens_time < 0.01  # Should handle deep nesting

        # Very long single line
        long_line = " ".join([f"command{i}" for i in range(100)] + ["|"] * 99)
        long_time = self.measure_parse_time(long_line)
        assert long_time < 0.02  # Should handle long lines

        # Many here-documents
        heredocs = "\n".join(f"""
cat << EOF{i}
This is heredoc {i}
With multiple lines
EOF{i}
""" for i in range(20))
        heredoc_time = self.measure_parse_time(heredocs)
        assert heredoc_time < 0.02


@pytest.mark.benchmark
@pytest.mark.serial
class TestTokenizationPerformance:
    """Benchmark tokenization performance."""

    def measure_tokenize_time(self, script: str, iterations: int = 100) -> float:
        """Measure min-of-iterations CPU time to tokenize a script."""
        times = []

        for _ in range(iterations):
            start = time.process_time()
            list(tokenize(script))  # Force evaluation of generator
            end = time.process_time()
            times.append(end - start)

        return min(times)

    def test_tokenization_scaling(self):
        """Test how tokenization scales with input size."""
        sizes = [100, 1000, 10000]
        times = []

        for size in sizes:
            script = " ".join(f"word{i}" for i in range(size))
            avg_time = self.measure_tokenize_time(script, iterations=10)
            times.append(avg_time)

            # Verify reasonable absolute performance
            if size == 100:
                assert avg_time < 0.002  # Allow up to 2ms for tokenization
            elif size == 1000:
                assert avg_time < 0.02  # Allow up to 20ms for 1000 tokens
            elif size == 10000:
                assert avg_time < 0.2  # Allow up to 200ms for 10000 tokens

        # Verify linear scaling
        ratio1 = times[1] / times[0]  # 1000 vs 100
        ratio2 = times[2] / times[1]  # 10000 vs 1000

        assert 8 < ratio1 < 12  # Should be roughly 10x
        assert 8 < ratio2 < 12  # Should be roughly 10x


class TestLargeInputRobustness:
    """Deterministic large-input robustness invariants (no timing, no memory
    measurement — the class was named ``TestMemoryUsage`` for years while
    measuring nothing of the kind; renamed honestly in campaign E1b). These
    are ordinary standard-gate tests: they assert the parser completes on
    large and deeply nested input without raising."""

    def test_large_script_parses(self):
        """A 10,000-command script parses to a complete AST."""
        large_script = "\n".join(
            f"echo 'Line {i} with some text to make it realistic'"
            for i in range(10000)
        )
        parser = Parser(tokenize(large_script))
        ast = parser.parse()
        assert ast is not None

    def test_deeply_nested_structure_parses(self):
        """100-deep nested `if` parses without hitting recursion limits."""
        depth = 100
        nested = "if true; then\n" * depth
        nested += "echo deep\n"
        nested += "fi\n" * depth
        parser = Parser(tokenize(nested))
        ast = parser.parse()
        assert ast is not None
