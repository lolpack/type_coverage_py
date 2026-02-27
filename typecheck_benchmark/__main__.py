"""Allow running as `python -m typecheck_benchmark`."""

from typecheck_benchmark.daily_runner import main
import sys

sys.exit(main())
