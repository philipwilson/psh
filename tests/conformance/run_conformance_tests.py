#!/usr/bin/env python3
"""
Conformance test runner and tracking system.

Runs comprehensive conformance tests and generates detailed reports
on PSH's POSIX compliance and bash compatibility.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from conformance_framework import ConformanceResult


class ConformanceTestRunner:
    """Main conformance test runner."""

    def __init__(self, output_dir: str = "conformance_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.results = []
        self.start_time = None
        self.end_time = None

    def run_posix_tests(self):
        """Run POSIX compliance tests."""
        print("Running POSIX compliance tests...")

        try:
            # Import and run POSIX tests
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'posix'))
            from test_posix_compliance import (
                TestPOSIXArithmeticExpansion,
                TestPOSIXCommandSubstitution,
                TestPOSIXCompoundCommands,
                TestPOSIXLists,
                TestPOSIXParameterExpansion,
                TestPOSIXPathnameExpansion,
                TestPOSIXPipelines,
                TestPOSIXQuoteRemoval,
                TestPOSIXShellFunctions,
                TestPOSIXShellParameters,
                TestPOSIXSimpleCommands,
                TestPOSIXTildeExpansion,
            )

            posix_test_classes = [
                TestPOSIXParameterExpansion,
                TestPOSIXCommandSubstitution,
                TestPOSIXArithmeticExpansion,
                TestPOSIXTildeExpansion,
                TestPOSIXPathnameExpansion,
                TestPOSIXQuoteRemoval,
                TestPOSIXSimpleCommands,
                TestPOSIXPipelines,
                TestPOSIXLists,
                TestPOSIXCompoundCommands,
                TestPOSIXShellFunctions,
                TestPOSIXShellParameters
            ]

            posix_results = self._run_test_classes(posix_test_classes, "POSIX")
            return posix_results

        except ImportError as e:
            print(f"Could not import POSIX tests: {e}")
            return []

    def run_bash_tests(self):
        """Run bash compatibility tests."""
        print("Running bash compatibility tests...")

        try:
            # Import and run bash tests
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bash'))
            from test_bash_compatibility import (
                TestBashAliases,
                TestBashArithmeticExpansion,
                TestBashArrays,
                TestBashBraceExpansion,
                TestBashBuiltins,
                TestBashCommandSubstitution,
                TestBashConditionals,
                TestBashFunctions,
                TestBashGlobbing,
                TestBashHistory,
                TestBashJobControl,
                TestBashMiscellaneous,
                TestBashOptions,
                TestBashParameterExpansion,
                TestBashRedirection,
                TestDocumentedDifferences,
            )
            from test_edge_cases import (
                TestEdgeArithmetic,
                TestEdgeBraceExpansion,
                TestEdgeGlobbing,
                TestEdgeParameterExpansion,
                TestEdgePrintf,
                TestEdgeQuotingWordSplitting,
                TestEdgeRegex,
                TestEdgeTraps,
            )

            bash_test_classes = [
                TestBashBuiltins,
                TestBashConditionals,
                TestBashArrays,
                TestBashParameterExpansion,
                TestBashCommandSubstitution,
                TestBashBraceExpansion,
                TestBashArithmeticExpansion,
                TestBashGlobbing,
                TestBashJobControl,
                TestBashHistory,
                TestBashOptions,
                TestBashRedirection,
                TestBashFunctions,
                TestBashAliases,
                TestBashMiscellaneous,
                TestDocumentedDifferences,
                TestEdgeQuotingWordSplitting,
                TestEdgeArithmetic,
                TestEdgeParameterExpansion,
                TestEdgeGlobbing,
                TestEdgeBraceExpansion,
                TestEdgePrintf,
                TestEdgeRegex,
                TestEdgeTraps,
            ]

            bash_results = self._run_test_classes(bash_test_classes, "Bash")
            return bash_results

        except ImportError as e:
            print(f"Could not import bash tests: {e}")
            return []

    def _run_test_classes(self, test_classes, category):
        """Run a list of test classes and collect results."""
        category_results = []

        for test_class in test_classes:
            print(f"  Running {test_class.__name__}...")
            test_instance = test_class()

            # Get all test methods
            test_methods = [method for method in dir(test_instance)
                          if method.startswith('test_') and callable(getattr(test_instance, method))]

            for method_name in test_methods:
                try:
                    method = getattr(test_instance, method_name)
                    is_xfail = self._is_xfail_test(method)
                    method()
                    if is_xfail:
                        print(f"    ↷ {method_name} (xfail passed)")
                    else:
                        print(f"    ✓ {method_name}")
                except Exception as e:
                    if self._is_xfail_test(getattr(test_instance, method_name)):
                        print(f"    ↷ {method_name} (xfail): {e}")
                        continue

                    print(f"    ✗ {method_name}: {e}")
                    # Create error result
                    from conformance_framework import CommandResult, ComparisonResult
                    error_result = ComparisonResult(
                        command=f"{test_class.__name__}.{method_name}",
                        psh_result=CommandResult("", str(e), 1, 0.0, "psh", "test_error"),
                        bash_result=CommandResult("", "", 0, 0.0, "bash", "test_error"),
                        conformance=ConformanceResult.TEST_ERROR,
                        notes=f"Test execution error: {e}"
                    )
                    test_instance.results.append(error_result)

            # Add category to results
            for result in test_instance.results:
                result.category = category

            category_results.extend(test_instance.results)

        return category_results

    @staticmethod
    def _is_xfail_test(method) -> bool:
        """Return True when a test function has a pytest xfail marker."""
        func = getattr(method, '__func__', method)
        marks = getattr(func, 'pytestmark', [])
        return any(getattr(mark, 'name', None) == 'xfail' for mark in marks)

    def run_all_tests(self):
        """Run all conformance tests."""
        self.start_time = time.time()
        print("Starting comprehensive conformance test suite...")
        print("=" * 60)

        # Run POSIX tests
        posix_results = self.run_posix_tests()
        print(f"POSIX tests completed: {len(posix_results)} results")

        # Run bash tests
        bash_results = self.run_bash_tests()
        print(f"Bash tests completed: {len(bash_results)} results")

        # Combine results
        self.results = posix_results + bash_results
        self.end_time = time.time()

        print("=" * 60)
        print(f"All conformance tests completed: {len(self.results)} total results")
        print(f"Execution time: {self.end_time - self.start_time:.2f} seconds")

        return self.results

    def generate_summary_report(self):
        """Generate summary report of all conformance tests."""
        if not self.results:
            return {"error": "No test results available"}

        # Categorize results
        summary = {
            "total_tests": len(self.results),
            "execution_time": self.end_time - self.start_time if self.end_time and self.start_time else 0,
            "timestamp": datetime.now().isoformat(),
            "by_conformance": {},
            "by_category": {},
            "posix_compliance": {},
            "bash_compatibility": {},
            "areas_of_concern": []
        }

        # Count by conformance result
        for result_type in ConformanceResult:
            summary["by_conformance"][result_type.value] = sum(
                1 for r in self.results if r.conformance == result_type
            )

        # Count by category (POSIX vs Bash)
        for category in ["POSIX", "Bash"]:
            category_results = [r for r in self.results if getattr(r, 'category', None) == category]
            summary["by_category"][category] = {
                "total": len(category_results),
                "identical": sum(1 for r in category_results if r.conformance == ConformanceResult.IDENTICAL),
                "documented_differences": sum(1 for r in category_results if r.conformance == ConformanceResult.DOCUMENTED_DIFFERENCE),
                "psh_extensions": sum(1 for r in category_results if r.conformance == ConformanceResult.PSH_EXTENSION),
                "bash_specific": sum(1 for r in category_results if r.conformance == ConformanceResult.BASH_SPECIFIC),
                "psh_bugs": sum(1 for r in category_results if r.conformance == ConformanceResult.PSH_BUG),
                "test_errors": sum(1 for r in category_results if r.conformance == ConformanceResult.TEST_ERROR)
            }

        # Calculate compliance scores
        posix_results = [r for r in self.results if getattr(r, 'category', None) == "POSIX"]
        if posix_results:
            posix_compliant = sum(1 for r in posix_results
                                if r.conformance in [ConformanceResult.IDENTICAL, ConformanceResult.DOCUMENTED_DIFFERENCE])
            summary["posix_compliance"] = {
                "total_tests": len(posix_results),
                "compliant_tests": posix_compliant,
                "compliance_percentage": (posix_compliant / len(posix_results)) * 100
            }

        bash_results = [r for r in self.results if getattr(r, 'category', None) == "Bash"]
        if bash_results:
            bash_compatible = sum(1 for r in bash_results
                                if r.conformance in [ConformanceResult.IDENTICAL, ConformanceResult.DOCUMENTED_DIFFERENCE, ConformanceResult.BASH_SPECIFIC])
            summary["bash_compatibility"] = {
                "total_tests": len(bash_results),
                "compatible_tests": bash_compatible,
                "compatibility_percentage": (bash_compatible / len(bash_results)) * 100
            }

        # Identify areas of concern
        bug_results = [r for r in self.results if r.conformance == ConformanceResult.PSH_BUG]
        error_results = [r for r in self.results if r.conformance == ConformanceResult.TEST_ERROR]

        if bug_results:
            summary["areas_of_concern"].append({
                "type": "potential_bugs",
                "count": len(bug_results),
                "commands": [r.command for r in bug_results[:10]]  # First 10
            })

        if error_results:
            summary["areas_of_concern"].append({
                "type": "test_errors",
                "count": len(error_results),
                "commands": [r.command for r in error_results[:10]]  # First 10
            })

        return summary

    def generate_detailed_report(self):
        """Generate detailed report with all test results."""
        detailed = {
            "summary": self.generate_summary_report(),
            "detailed_results": []
        }

        for result in self.results:
            detailed_result = {
                "command": result.command,
                "category": getattr(result, 'category', 'unknown'),
                "conformance": result.conformance.value,
                "difference_id": result.difference_id,
                "notes": result.notes,
                "psh_result": {
                    "stdout": result.psh_result.stdout,
                    "stderr": result.psh_result.stderr,
                    "exit_code": result.psh_result.exit_code,
                    "execution_time": result.psh_result.execution_time
                },
                "bash_result": {
                    "stdout": result.bash_result.stdout,
                    "stderr": result.bash_result.stderr,
                    "exit_code": result.bash_result.exit_code,
                    "execution_time": result.bash_result.execution_time
                }
            }
            detailed["detailed_results"].append(detailed_result)

        return detailed

    def save_reports(self):
        """Save all reports to files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save summary report
        summary_file = self.output_dir / f"conformance_summary_{timestamp}.json"
        with open(summary_file, 'w') as f:
            json.dump(self.generate_summary_report(), f, indent=2)
        print(f"Summary report saved to: {summary_file}")

        # Save detailed report
        detailed_file = self.output_dir / f"conformance_detailed_{timestamp}.json"
        with open(detailed_file, 'w') as f:
            json.dump(self.generate_detailed_report(), f, indent=2)
        print(f"Detailed report saved to: {detailed_file}")

        # Save latest symlinks
        latest_summary = self.output_dir / "latest_summary.json"
        latest_detailed = self.output_dir / "latest_detailed.json"

        if latest_summary.exists():
            latest_summary.unlink()
        if latest_detailed.exists():
            latest_detailed.unlink()

        latest_summary.symlink_to(summary_file.name)
        latest_detailed.symlink_to(detailed_file.name)

        return summary_file, detailed_file

    def print_summary(self):
        """Print summary to console."""
        summary = self.generate_summary_report()

        print("\n" + "=" * 80)
        print("CONFORMANCE TEST SUMMARY")
        print("=" * 80)

        print(f"Total Tests: {summary['total_tests']}")
        print(f"Execution Time: {summary['execution_time']:.2f} seconds")
        print(f"Timestamp: {summary['timestamp']}")

        print("\nOverall Results:")
        for result_type, count in summary['by_conformance'].items():
            if count > 0:
                percentage = (count / summary['total_tests']) * 100
                print(f"  {result_type.replace('_', ' ').title()}: {count} ({percentage:.1f}%)")

        if 'posix_compliance' in summary and summary['posix_compliance']:
            posix = summary['posix_compliance']
            print(f"\nPOSIX Compliance: {posix['compliance_percentage']:.1f}% ({posix['compliant_tests']}/{posix['total_tests']})")

        if 'bash_compatibility' in summary and summary['bash_compatibility']:
            bash = summary['bash_compatibility']
            print(f"Bash Compatibility: {bash['compatibility_percentage']:.1f}% ({bash['compatible_tests']}/{bash['total_tests']})")

        if summary['areas_of_concern']:
            print("\nAreas of Concern:")
            for concern in summary['areas_of_concern']:
                print(f"  {concern['type'].replace('_', ' ').title()}: {concern['count']} issues")
                if concern['commands']:
                    print(f"    Examples: {', '.join(concern['commands'][:3])}...")

        print("=" * 80)


def main():
    """Main entry point for conformance test runner."""
    parser = argparse.ArgumentParser(description="Run PSH conformance tests")
    parser.add_argument("--output-dir", default="conformance_results",
                       help="Directory to save results (default: conformance_results)")
    parser.add_argument("--posix-only", action="store_true",
                       help="Run only POSIX compliance tests")
    parser.add_argument("--bash-only", action="store_true",
                       help="Run only bash compatibility tests")
    parser.add_argument("--summary-only", action="store_true",
                       help="Print summary only (don't save detailed results)")

    args = parser.parse_args()

    runner = ConformanceTestRunner(args.output_dir)

    try:
        if args.posix_only:
            runner.results = runner.run_posix_tests()
        elif args.bash_only:
            runner.results = runner.run_bash_tests()
        else:
            runner.run_all_tests()

        # Print summary
        runner.print_summary()

        # Save reports unless summary-only
        if not args.summary_only:
            runner.save_reports()

    except KeyboardInterrupt:
        print("\nConformance tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error running conformance tests: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
