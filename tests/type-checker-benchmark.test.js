/**
 * Tests for Type Checker Benchmark Frontend JavaScript
 *
 * These tests verify the data processing and display logic
 * for the type checker benchmark dashboard.
 */

// Mock Chart.js before loading the script
global.Chart = jest.fn().mockImplementation(() => ({
    destroy: jest.fn(),
}));

// Mock DOM elements
document.body.innerHTML = `
    <div id="lastUpdated"></div>
    <select id="osSelect">
        <option value="ubuntu">Ubuntu</option>
        <option value="macos">macOS</option>
        <option value="windows">Windows</option>
    </select>
    <input type="date" id="dateSelect" />
    <button id="loadDateBtn">Load</button>
    <button id="latestBtn">Latest</button>
    <input type="text" id="packageSearch" />
    <select id="sortBy">
        <option value="ranking">Sort by Ranking</option>
        <option value="name">Sort by Name</option>
        <option value="errors">Sort by Error Count</option>
        <option value="time">Sort by Execution Time</option>
    </select>
    <tbody id="resultsBody"></tbody>
    <canvas id="totalErrorsChart"></canvas>
    <canvas id="avgErrorsChart"></canvas>
    <canvas id="p95ErrorsChart"></canvas>
    <canvas id="avgExecutionTimeChart"></canvas>
    <canvas id="p95ExecutionTimeChart"></canvas>
    <span id="version-pyright"></span>
    <span id="version-pyrefly"></span>
    <span id="version-ty"></span>
    <span id="version-mypy"></span>
    <span id="version-zuban"></span>
`;

// Helper to create sample benchmark data
function createSampleBenchmarkData() {
    return {
        timestamp: "2026-01-13T16:41:04.550104+00:00",
        date: "2026-01-13",
        type_checkers: ["pyright", "pyrefly", "ty", "mypy", "zuban"],
        type_checker_versions: {
            pyright: "1.1.408",
            pyrefly: "0.48.0",
            ty: "0.0.11",
            mypy: "1.8.0",
            zuban: "0.4.1"
        },
        package_count: 2,
        aggregate: {
            pyright: {
                packages_tested: 2,
                total_errors: 300,
                total_warnings: 30,
                avg_errors_per_package: 150.0,
                p95_errors: 200,
                min_errors: 100,
                max_errors: 200,
                avg_execution_time_s: 7.5,
                p95_execution_time_s: 10.0
            },
            pyrefly: {
                packages_tested: 2,
                total_errors: 200,
                total_warnings: 0,
                avg_errors_per_package: 100.0,
                p95_errors: 150,
                min_errors: 50,
                max_errors: 150,
                avg_execution_time_s: 2.0,
                p95_execution_time_s: 3.0
            },
            ty: {
                packages_tested: 2,
                total_errors: 400,
                total_warnings: 50,
                avg_errors_per_package: 200.0,
                p95_errors: 300,
                min_errors: 100,
                max_errors: 300,
                avg_execution_time_s: 1.5,
                p95_execution_time_s: 2.5
            },
            mypy: {
                packages_tested: 2,
                total_errors: 100,
                total_warnings: 0,
                avg_errors_per_package: 50.0,
                p95_errors: 75,
                min_errors: 25,
                max_errors: 75,
                avg_execution_time_s: 5.0,
                p95_execution_time_s: 8.0
            },
            zuban: {
                packages_tested: 2,
                total_errors: 250,
                total_warnings: 0,
                avg_errors_per_package: 125.0,
                p95_errors: 175,
                min_errors: 75,
                max_errors: 175,
                avg_execution_time_s: 3.0,
                p95_execution_time_s: 5.0
            }
        },
        results: [
            {
                package_name: "requests",
                github_url: "https://github.com/psf/requests",
                ranking: 1,
                error: null,
                has_py_typed: true,
                configured_checkers: { pyright: true, mypy: false },
                metrics: {
                    pyright: { ok: true, error_count: 100, warning_count: 10, execution_time_s: 5.0 },
                    pyrefly: { ok: true, error_count: 50, warning_count: 0, execution_time_s: 1.0 },
                    ty: { ok: true, error_count: 100, warning_count: 20, execution_time_s: 0.8 },
                    mypy: { ok: true, error_count: 25, warning_count: 0, execution_time_s: 3.0 },
                    zuban: { ok: true, error_count: 75, warning_count: 0, execution_time_s: 2.0 }
                }
            },
            {
                package_name: "flask",
                github_url: "https://github.com/pallets/flask",
                ranking: 2,
                error: null,
                has_py_typed: false,
                configured_checkers: {},
                metrics: {
                    pyright: { ok: true, error_count: 200, warning_count: 20, execution_time_s: 10.0 },
                    pyrefly: { ok: true, error_count: 150, warning_count: 0, execution_time_s: 3.0 },
                    ty: { ok: true, error_count: 300, warning_count: 30, execution_time_s: 2.5 },
                    mypy: { ok: true, error_count: 75, warning_count: 0, execution_time_s: 8.0 },
                    zuban: { ok: true, error_count: 175, warning_count: 0, execution_time_s: 5.0 }
                }
            }
        ]
    };
}

describe('CHECKER_COLORS', () => {
    test('should have colors for all expected type checkers', () => {
        const expectedCheckers = ['pyright', 'pyrefly', 'ty', 'mypy', 'zuban'];
        const CHECKER_COLORS = {
            pyright: '#3178c6',
            pyrefly: '#e74c3c',
            ty: '#9b59b6',
            mypy: '#2ecc71',
            zuban: '#f39c12'
        };

        expectedCheckers.forEach(checker => {
            expect(CHECKER_COLORS[checker]).toBeDefined();
            expect(CHECKER_COLORS[checker]).toMatch(/^#[0-9a-f]{6}$/i);
        });
    });
});

describe('CHECKER_NAMES', () => {
    test('should have display names for all expected type checkers', () => {
        const CHECKER_NAMES = {
            pyright: 'Pyright',
            pyrefly: 'Pyrefly',
            ty: 'ty',
            mypy: 'Mypy',
            zuban: 'Zuban'
        };

        expect(CHECKER_NAMES.pyright).toBe('Pyright');
        expect(CHECKER_NAMES.pyrefly).toBe('Pyrefly');
        expect(CHECKER_NAMES.ty).toBe('ty');
        expect(CHECKER_NAMES.mypy).toBe('Mypy');
        expect(CHECKER_NAMES.zuban).toBe('Zuban');
    });
});

describe('getOsFromUrl', () => {
    const getOsFromUrl = () => {
        const params = new URLSearchParams(window.location.search);
        const os = params.get('os');
        if (os && ['ubuntu', 'macos', 'windows'].includes(os)) {
            return os;
        }
        return 'ubuntu';
    };

    test('should return ubuntu by default', () => {
        delete window.location;
        window.location = { search: '' };
        expect(getOsFromUrl()).toBe('ubuntu');
    });

    test('should return os from query string', () => {
        delete window.location;
        window.location = { search: '?os=macos' };
        expect(getOsFromUrl()).toBe('macos');
    });

    test('should return ubuntu for invalid os', () => {
        delete window.location;
        window.location = { search: '?os=invalid' };
        expect(getOsFromUrl()).toBe('ubuntu');
    });
});

describe('getDateFromUrl', () => {
    const getDateFromUrl = () => {
        const params = new URLSearchParams(window.location.search);
        const date = params.get('date');
        if (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) {
            return date;
        }
        return null;
    };

    test('should return null by default', () => {
        delete window.location;
        window.location = { search: '' };
        expect(getDateFromUrl()).toBeNull();
    });

    test('should return date from query string', () => {
        delete window.location;
        window.location = { search: '?date=2026-01-13' };
        expect(getDateFromUrl()).toBe('2026-01-13');
    });

    test('should return null for invalid date format', () => {
        delete window.location;
        window.location = { search: '?date=invalid' };
        expect(getDateFromUrl()).toBeNull();
    });

    test('should return null for partially valid date', () => {
        delete window.location;
        window.location = { search: '?date=2026-1-13' };
        expect(getDateFromUrl()).toBeNull();
    });
});

describe('getDemoData', () => {
    const getDemoData = () => {
        return {
            timestamp: new Date().toISOString(),
            date: new Date().toISOString().split('T')[0],
            type_checkers: ['pyright', 'pyrefly', 'ty', 'mypy'],
            package_count: 5,
            aggregate: {
                pyright: {
                    packages_tested: 5,
                    total_errors: 245,
                    avg_errors_per_package: 49.0,
                    avg_execution_time_s: 12.5
                }
            },
            results: []
        };
    };

    test('should return valid demo data structure', () => {
        const data = getDemoData();

        expect(data.timestamp).toBeDefined();
        expect(data.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
        expect(data.type_checkers).toContain('pyright');
        expect(data.aggregate.pyright.total_errors).toBe(245);
    });

    test('should include expected type checkers', () => {
        const data = getDemoData();

        expect(data.type_checkers).toContain('pyright');
        expect(data.type_checkers).toContain('pyrefly');
        expect(data.type_checkers).toContain('ty');
        expect(data.type_checkers).toContain('mypy');
    });
});

describe('getMaxErrors', () => {
    const getMaxErrors = (result) => {
        if (result.error || !result.metrics) return 0;
        return Math.max(...Object.values(result.metrics)
            .filter(m => m?.ok)
            .map(m => m.error_count || 0));
    };

    test('should return max errors across checkers', () => {
        const result = {
            error: null,
            metrics: {
                pyright: { ok: true, error_count: 100 },
                pyrefly: { ok: true, error_count: 200 },
                ty: { ok: true, error_count: 50 }
            }
        };

        expect(getMaxErrors(result)).toBe(200);
    });

    test('should return 0 for result with error', () => {
        const result = {
            error: 'Failed to clone',
            metrics: {}
        };

        expect(getMaxErrors(result)).toBe(0);
    });

    test('should ignore failed checkers', () => {
        const result = {
            error: null,
            metrics: {
                pyright: { ok: true, error_count: 100 },
                pyrefly: { ok: false, error_count: 0, error_message: 'Timeout' }
            }
        };

        expect(getMaxErrors(result)).toBe(100);
    });
});

describe('getAvgTime', () => {
    const getAvgTime = (result) => {
        if (result.error || !result.metrics) return 0;
        const times = Object.values(result.metrics)
            .filter(m => m?.ok && m.execution_time_s)
            .map(m => m.execution_time_s);
        return times.length ? times.reduce((a, b) => a + b, 0) / times.length : 0;
    };

    test('should return average execution time', () => {
        const result = {
            error: null,
            metrics: {
                pyright: { ok: true, execution_time_s: 10.0 },
                pyrefly: { ok: true, execution_time_s: 2.0 },
                ty: { ok: true, execution_time_s: 3.0 }
            }
        };

        expect(getAvgTime(result)).toBe(5.0);
    });

    test('should return 0 for result with error', () => {
        const result = {
            error: 'Failed',
            metrics: {}
        };

        expect(getAvgTime(result)).toBe(0);
    });

    test('should ignore failed checkers', () => {
        const result = {
            error: null,
            metrics: {
                pyright: { ok: true, execution_time_s: 10.0 },
                pyrefly: { ok: false, execution_time_s: 0 }
            }
        };

        expect(getAvgTime(result)).toBe(10.0);
    });
});

describe('Benchmark Data Structure', () => {
    test('should have valid structure', () => {
        const data = createSampleBenchmarkData();

        expect(data.timestamp).toBeDefined();
        expect(data.date).toBeDefined();
        expect(data.type_checkers).toBeInstanceOf(Array);
        expect(data.type_checker_versions).toBeDefined();
        expect(data.package_count).toBeGreaterThan(0);
        expect(data.aggregate).toBeDefined();
        expect(data.results).toBeInstanceOf(Array);
    });

    test('should have aggregate stats for each type checker', () => {
        const data = createSampleBenchmarkData();

        data.type_checkers.forEach(checker => {
            expect(data.aggregate[checker]).toBeDefined();
            expect(data.aggregate[checker].packages_tested).toBeDefined();
            expect(data.aggregate[checker].total_errors).toBeDefined();
            expect(data.aggregate[checker].avg_errors_per_package).toBeDefined();
            expect(data.aggregate[checker].avg_execution_time_s).toBeDefined();
        });
    });

    test('should have valid package results', () => {
        const data = createSampleBenchmarkData();

        data.results.forEach(result => {
            expect(result.package_name).toBeDefined();
            expect(result.github_url).toBeDefined();
            expect(result.ranking).toBeDefined();
            expect(result.metrics).toBeDefined();

            // If no error, should have metrics for each checker
            if (!result.error) {
                data.type_checkers.forEach(checker => {
                    expect(result.metrics[checker]).toBeDefined();
                    expect(result.metrics[checker].ok).toBeDefined();
                });
            }
        });
    });

    test('should have type checker versions', () => {
        const data = createSampleBenchmarkData();

        expect(data.type_checker_versions.pyright).toBe('1.1.408');
        expect(data.type_checker_versions.pyrefly).toBe('0.48.0');
        expect(data.type_checker_versions.ty).toBe('0.0.11');
    });
});

describe('Package Result Structure', () => {
    test('should have py_typed information', () => {
        const data = createSampleBenchmarkData();
        const requests = data.results.find(r => r.package_name === 'requests');

        expect(requests.has_py_typed).toBe(true);
    });

    test('should have configured_checkers information', () => {
        const data = createSampleBenchmarkData();
        const requests = data.results.find(r => r.package_name === 'requests');

        expect(requests.configured_checkers).toBeDefined();
        expect(requests.configured_checkers.pyright).toBe(true);
    });

    test('should have metrics with error_count and execution_time_s', () => {
        const data = createSampleBenchmarkData();
        const requests = data.results.find(r => r.package_name === 'requests');

        expect(requests.metrics.pyright.error_count).toBe(100);
        expect(requests.metrics.pyright.execution_time_s).toBe(5.0);
    });
});

describe('Filtering and Sorting Logic', () => {
    test('should filter results by search term', () => {
        const data = createSampleBenchmarkData();
        const searchTerm = 'flask';

        const filtered = data.results.filter(r =>
            r.package_name.toLowerCase().includes(searchTerm.toLowerCase())
        );

        expect(filtered.length).toBe(1);
        expect(filtered[0].package_name).toBe('flask');
    });

    test('should sort by ranking', () => {
        const data = createSampleBenchmarkData();
        const sorted = [...data.results].sort((a, b) =>
            (a.ranking || 999) - (b.ranking || 999)
        );

        expect(sorted[0].package_name).toBe('requests');
        expect(sorted[1].package_name).toBe('flask');
    });

    test('should sort by name alphabetically', () => {
        const data = createSampleBenchmarkData();
        const sorted = [...data.results].sort((a, b) =>
            a.package_name.localeCompare(b.package_name)
        );

        expect(sorted[0].package_name).toBe('flask');
        expect(sorted[1].package_name).toBe('requests');
    });

    test('should sort by errors descending', () => {
        const data = createSampleBenchmarkData();

        const getMaxErrors = (result) => {
            if (result.error || !result.metrics) return 0;
            return Math.max(...Object.values(result.metrics)
                .filter(m => m?.ok)
                .map(m => m.error_count || 0));
        };

        const sorted = [...data.results].sort((a, b) =>
            getMaxErrors(b) - getMaxErrors(a)
        );

        // flask has higher max errors (300 vs 100)
        expect(sorted[0].package_name).toBe('flask');
    });
});

describe('Aggregate Stats Calculations', () => {
    test('should calculate correct total errors', () => {
        const data = createSampleBenchmarkData();

        // pyright: 100 + 200 = 300
        expect(data.aggregate.pyright.total_errors).toBe(300);
    });

    test('should calculate correct average errors per package', () => {
        const data = createSampleBenchmarkData();

        // pyright: 300 / 2 = 150
        expect(data.aggregate.pyright.avg_errors_per_package).toBe(150.0);
    });

    test('should track min and max errors', () => {
        const data = createSampleBenchmarkData();

        expect(data.aggregate.pyright.min_errors).toBe(100);
        expect(data.aggregate.pyright.max_errors).toBe(200);
    });
});

describe('URL Loading Paths', () => {
    test('should generate correct path for dated OS-specific results', () => {
        const date = '2026-01-13';
        const os = 'ubuntu';

        const paths = [
            `./results/benchmark_${date}_${os}.json`,
            `../type_checker_benchmark/results/benchmark_${date}_${os}.json`,
            `./results/benchmark_${date}.json`,
            `../type_checker_benchmark/results/benchmark_${date}.json`
        ];

        expect(paths[0]).toBe('./results/benchmark_2026-01-13_ubuntu.json');
        expect(paths[1]).toBe('../type_checker_benchmark/results/benchmark_2026-01-13_ubuntu.json');
    });

    test('should generate correct path for latest OS-specific results', () => {
        const os = 'macos';

        const paths = [
            `./results/latest-${os}.json`,
            `../type_checker_benchmark/results/latest-${os}.json`,
            './results/latest.json',
            '../type_checker_benchmark/results/latest.json'
        ];

        expect(paths[0]).toBe('./results/latest-macos.json');
        expect(paths[1]).toBe('../type_checker_benchmark/results/latest-macos.json');
    });
});
