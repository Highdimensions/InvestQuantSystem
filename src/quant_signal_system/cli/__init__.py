"""Command-line entry points for backtest runs."""

from quant_signal_system.cli._common import (
    build_artifact_set,
    exit_with,
    parse_args,
    resolve_output_dir,
)
from quant_signal_system.cli.compare_runs import cli as compare_runs_cli
from quant_signal_system.cli.run_backtest import cli as run_backtest_cli
from quant_signal_system.cli.validate_backtest import cli as validate_backtest_cli

__all__ = [
    "build_artifact_set",
    "compare_runs_cli",
    "exit_with",
    "parse_args",
    "resolve_output_dir",
    "run_backtest_cli",
    "validate_backtest_cli",
]