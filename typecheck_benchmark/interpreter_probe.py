"""Audit interpreter queries using the real benchmark commands (macOS/Linux).

Run with ``python -m typecheck_benchmark.interpreter_probe --output /tmp/probe.json``.
The temporary package interpreter logs its arguments and optionally sleeps before
executing Python. Comparing zero-delay and delayed runs demonstrates whether
interpreter queries contribute to the benchmark's wall-clock measurement. These
instrumented timings are diagnostic evidence, not publishable benchmark results.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import statistics
import sys
import tempfile
import venv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from typecheck_benchmark import daily_runner as runner


def instrument_interpreter(environment: Path) -> Path:
    """Wrap every Python alias in a disposable venv, preserving its layout."""
    venv.EnvBuilder(with_pip=False).create(environment)
    bin_dir = environment / "bin"
    real_python = bin_dir / "probe-python"
    real_python.symlink_to(Path(sys.executable).resolve())
    aliases = list(bin_dir.glob("python*"))
    for alias in aliases:
        alias.unlink()
    python = bin_dir / "python"
    python.write_text(
        "#!/bin/sh\n"
        "printf '\\036' >> \"$INTERPRETER_PROBE_LOG\"\n"
        "printf '%s\\0' \"$@\" >> \"$INTERPRETER_PROBE_LOG\"\n"
        'if [ "$INTERPRETER_PROBE_DELAY" != "0" ]; then\n'
        '  sleep "$INTERPRETER_PROBE_DELAY"\n'
        "fi\n"
        f"exec {shlex.quote(str(real_python))} \"$@\"\n",
        encoding="utf-8",
    )
    python.chmod(0o755)
    for alias in aliases:
        if alias != python:
            alias.symlink_to("python")
    return python


def probe(output: Path, runs: int, delay: float) -> dict[str, Any]:
    """Record real commands, query arguments, exit codes, and paired timings."""
    report: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "versions": runner.get_type_checker_versions(),
        "runs_per_condition": runs,
        "injected_delay_s_per_query": delay,
        "results": {},
    }
    with tempfile.TemporaryDirectory(prefix="interpreter-probe-") as temporary:
        root = Path(temporary)
        project = root / "project"
        project.mkdir()
        source = project / "example.py"
        source.write_text(
            "import sys\nfrom probe_dependency import value\n"
            "platform_name: str = sys.platform\nresult: str = value\n",
            encoding="utf-8",
        )
        environment = root / "environment"
        instrument_interpreter(environment)
        site_packages = next((environment / "lib").glob("python*/site-packages"))
        # A clean check also proves the selected environment was discovered.
        dependency = site_packages / "probe_dependency"
        dependency.mkdir()
        (dependency / "__init__.py").write_text('value: str = "probe"\n', encoding="utf-8")
        (dependency / "py.typed").touch()
        log = root / "queries.log"
        real_run = runner.run_process_with_timeout

        for checker in runner.DEFAULT_TYPE_CHECKERS:
            conditions = [("baseline", 0), ("delayed", delay)]
            if checker == "pyrefly":
                conditions.append(("skip_query_delayed", delay))
            samples: dict[str, list[dict[str, Any]]] = {name: [] for name, _ in conditions}
            # Alternate conditions; discard one warmup pair per checker.
            for iteration in range(runs + 1):
                for condition, seconds in conditions:
                    log.write_bytes(b"")
                    record: dict[str, Any] = {}

                    def measured_run(cmd: list[str], **kwargs: Any) -> runner.ProcessResult:
                        if condition == "skip_query_delayed":
                            # Negative control: preserve the environment explicitly
                            # while disabling only Pyrefly's automatic query.
                            cmd = cmd.copy()
                            index = cmd.index("--python-interpreter-path")
                            del cmd[index:index + 2]
                            cmd.extend([
                                "--skip-interpreter-query",
                                "--python-version", f"{sys.version_info.major}.{sys.version_info.minor}",
                                "--python-platform", sys.platform,
                                "--site-packages-path", str(site_packages),
                            ])
                        result = real_run(cmd, **kwargs)
                        record.update(command=cmd, process=result)
                        return result

                    with (
                        patch.dict(os.environ, {
                            "INTERPRETER_PROBE_LOG": str(log),
                            "INTERPRETER_PROBE_DELAY": str(seconds),
                        }),
                        patch.object(runner, "run_process_with_timeout", measured_run),
                    ):
                        metrics = runner.run_checker(
                            checker, project, [source], timeout=60, venv=environment,
                        )
                    record["queries"] = [
                        entry.rstrip(b"\0").decode().split("\0")
                        for entry in log.read_bytes().split(b"\x1e") if entry
                    ]
                    record["metrics"] = metrics
                    # A clean fixture must actually finish without diagnostics.
                    if not metrics["ok"] or record["process"]["returncode"] != 0:
                        raise RuntimeError(f"{checker} did not check the fixture cleanly: {record}")
                    if iteration:
                        samples[condition].append(record)

            medians = {
                condition: statistics.median(
                    sample["metrics"]["execution_time_s"] for sample in values
                )
                for condition, values in samples.items()
            }
            result = {
                "median_time_s": medians,
                "median_added_time_s": round(medians["delayed"] - medians["baseline"], 3),
                "query_counts": {
                    condition: [len(sample["queries"]) for sample in values]
                    for condition, values in samples.items()
                },
                "samples": samples,
            }
            report["results"][checker] = result
            print(f"{checker}: {result['query_counts']}; added {result['median_added_time_s']}s", flush=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--delay", type=float, default=0.1)
    args = parser.parse_args()
    if sys.platform == "win32":
        parser.error("The instrumented interpreter uses a POSIX shell; run on macOS or Linux.")
    if args.runs < 1 or args.delay <= 0:
        parser.error("--runs and --delay must be positive")
    probe(args.output, args.runs, args.delay)


if __name__ == "__main__":
    main()
