/**
 * LSP Benchmark Results Viewer
 * Loads and displays benchmark data from JSON files
 */

// Chart.js is loaded via <script> tag
declare const Chart: any;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface LatencyMs {
    mean?: number;
    p50?: number;
    p95?: number;
}

interface CheckerMetrics {
    ok?: boolean;
    ok_pct?: number;
    valid_pct?: number;
    latency_ms?: LatencyMs;
    error?: string;
}

interface AggregateEntry {
    packages_tested: number;
    total_runs: number;
    total_valid: number;
    avg_latency_ms: number;
    ok_rate: number;
    success_rate: number;
}

interface BenchmarkResult {
    package_name: string;
    github_url: string;
    ranking?: number;
    error: string | null;
    metrics: Record<string, CheckerMetrics>;
}

interface BenchmarkData {
    timestamp: string;
    date: string;
    type_checkers: string[];
    type_checker_versions?: Record<string, string>;
    package_count: number;
    runs_per_package?: number;
    aggregate: Record<string, AggregateEntry>;
    results: BenchmarkResult[];
}

interface ErrorAction {
    text: string;
    onClick: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CHECKER_COLORS: Record<string, string> = {
    pyright: '#3178c6',
    pyrefly: '#e74c3c',
    ty: '#9b59b6',
    mypy: '#2ecc71',
    zuban: '#f39c12'
};

const CHECKER_NAMES: Record<string, string> = {
    pyright: 'Pyright',
    pyrefly: 'Pyrefly',
    ty: 'ty',
    mypy: 'Mypy',
    zuban: 'Zuban'
};

let benchmarkData: BenchmarkData | null = null;
let charts: Record<string, any> = {};
let currentOs = 'ubuntu';

// ---------------------------------------------------------------------------
// URL helpers
// ---------------------------------------------------------------------------

/**
 * Get OS from URL query string
 */
function getOsFromUrl(): string {
    const params = new URLSearchParams(window.location.search);
    const os = params.get('os');
    if (os && ['ubuntu', 'macos', 'windows'].includes(os)) {
        return os;
    }
    return 'ubuntu';
}

/**
 * Get date from URL query string
 */
function getDateFromUrl(): string | null {
    const params = new URLSearchParams(window.location.search);
    const date = params.get('date');
    // Validate date format (YYYY-MM-DD)
    if (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) {
        return date;
    }
    return null;
}

/**
 * Update URL query string with date and OS
 */
function updateUrlWithDate(date: string | null, os: string | null = null): void {
    const url = new URL(window.location.href);
    if (date) {
        url.searchParams.set('date', date);
    } else {
        url.searchParams.delete('date');
    }
    if (os) {
        url.searchParams.set('os', os);
    }
    window.history.replaceState({}, '', url.toString());
}

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------

/**
 * Initialize the dashboard
 */
async function init(): Promise<void> {
    try {
        // Check for OS and date in URL query string
        currentOs = getOsFromUrl();
        const osSelect = document.getElementById('osSelect') as HTMLSelectElement | null;
        if (osSelect) {
            osSelect.value = currentOs;
        }

        const urlDate = getDateFromUrl();
        await loadBenchmarkData(urlDate, currentOs);
        updateTimestamp();
        createLatencyChart();
        createOkChart();
        createSuccessChart();
        createPackageComparisonChart();
        populateResultsTable();
        setupFilters();
        setupDateSelector();
    } catch (error) {
        console.error('Failed to initialize dashboard:', error);
        const urlDate = getDateFromUrl();
        if (urlDate) {
            showError(`No benchmark data available for ${urlDate} on ${currentOs}.`, {
                text: 'Load latest Ubuntu results →',
                onClick: () => { switchToDate(null, 'ubuntu'); }
            });
        } else {
            showError('Failed to load benchmark data. Please try again later.');
        }
    }
}

// ---------------------------------------------------------------------------
// Date/OS selector
// ---------------------------------------------------------------------------

/**
 * Setup date selector event listeners
 */
function setupDateSelector(): void {
    const dateInput = document.getElementById('dateSelect') as HTMLInputElement | null;
    const loadBtn = document.getElementById('loadDateBtn');
    const latestBtn = document.getElementById('latestBtn');
    const osSelect = document.getElementById('osSelect') as HTMLSelectElement | null;

    if (!dateInput || !loadBtn || !latestBtn) return;

    // Set default value to current data's date
    if (benchmarkData?.date) {
        dateInput.value = benchmarkData.date;
    }

    // Load specific date
    loadBtn.addEventListener('click', async () => {
        const date = dateInput.value;
        if (date) {
            await switchToDate(date, currentOs);
        }
    });

    // Load latest
    latestBtn.addEventListener('click', async () => {
        await switchToDate(null, currentOs);
        if (benchmarkData?.date) {
            dateInput.value = benchmarkData.date;
        }
    });

    // Also allow Enter key to load
    dateInput.addEventListener('keypress', async (e: KeyboardEvent) => {
        if (e.key === 'Enter') {
            const date = dateInput.value;
            if (date) {
                await switchToDate(date, currentOs);
            }
        }
    });

    // OS selector change handler
    if (osSelect) {
        osSelect.addEventListener('change', async () => {
            currentOs = osSelect.value;
            const date = dateInput.value || null;
            await switchToDate(date, currentOs);
        });
    }
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

/**
 * Load benchmark results from JSON file
 */
async function loadBenchmarkData(date: string | null = null, os: string = 'ubuntu'): Promise<BenchmarkData> {
    let paths: string[];

    if (date) {
        paths = [
            `./results/benchmark_${date}_${os}.json`,
            `../lsp/benchmark/results/benchmark_${date}_${os}.json`,
            // Fallback to non-OS-specific files for backwards compatibility
            `./results/benchmark_${date}.json`,
            `../lsp/benchmark/results/benchmark_${date}.json`
        ];
    } else {
        paths = [
            `./results/latest-${os}.json`,
            `../lsp/benchmark/results/latest-${os}.json`,
            // Fallback to non-OS-specific files for backwards compatibility
            './results/latest.json',
            '../lsp/benchmark/results/latest.json',
            './data/benchmark-latest.json'
        ];
    }

    for (const path of paths) {
        try {
            const response = await fetch(path);
            if (response.ok) {
                benchmarkData = await response.json();
                console.log('Loaded benchmark data from:', path);
                return benchmarkData!;
            }
        } catch (e) {
            console.warn(`Failed to load from ${path}:`, e);
        }
    }

    if (date) {
        throw new Error(`No benchmark data found for ${date} on ${os}`);
    }

    // Use demo data if no file found
    console.log('Using demo data');
    benchmarkData = getDemoData();
    return benchmarkData;
}

/**
 * Load available benchmark dates from the results directory
 */
async function loadAvailableDates(): Promise<string[]> {
    const dates: string[] = [];

    // Try to load the manifest or scan for files
    // For now, we'll try common recent dates
    const today = new Date();
    for (let i = 0; i < 30; i++) {
        const date = new Date(today);
        date.setDate(date.getDate() - i);
        const dateStr = date.toISOString().split('T')[0];

        try {
            const response = await fetch(`./results/benchmark_${dateStr}.json`, { method: 'HEAD' });
            if (response.ok) {
                dates.push(dateStr);
            }
        } catch (_e) {
            // File doesn't exist, continue
        }
    }

    return dates;
}

/**
 * Switch to a different date's benchmark data
 */
async function switchToDate(date: string | null, os: string = 'ubuntu'): Promise<void> {
    try {
        await loadBenchmarkData(date, os);
        clearError();
        updateTimestamp();

        const loadedDate = benchmarkData?.date || date;
        updateUrlWithDate(loadedDate ?? null, os);

        // Update date input to reflect loaded date
        const dateInput = document.getElementById('dateSelect') as HTMLInputElement | null;
        if (dateInput && loadedDate) {
            dateInput.value = loadedDate;
        }

        // Destroy existing charts
        Object.values(charts).forEach((chart: any) => chart?.destroy());
        charts = {};

        // Recreate charts and table
        createLatencyChart();
        createOkChart();
        createSuccessChart();
        createPackageComparisonChart();
        populateResultsTable();
    } catch (error) {
        console.error('Failed to load data for date:', date, 'os:', os, error);
        showError(`No benchmark data available for ${date || 'latest'} on ${os}.`, {
            text: 'Load latest Ubuntu results →',
            onClick: () => { switchToDate(null, 'ubuntu'); }
        });
    }
}

// ---------------------------------------------------------------------------
// Demo data
// ---------------------------------------------------------------------------

/**
 * Demo data for development/testing
 */
function getDemoData(): BenchmarkData {
    return {
        timestamp: new Date().toISOString(),
        date: new Date().toISOString().split('T')[0],
        type_checkers: ['pyright', 'pyrefly', 'ty', 'zuban'],
        package_count: 5,
        runs_per_package: 5,
        aggregate: {
            pyright: {
                packages_tested: 5,
                total_runs: 25,
                total_valid: 20,
                avg_latency_ms: 145.5,
                ok_rate: 92.0,
                success_rate: 80.0
            },
            pyrefly: {
                packages_tested: 5,
                total_runs: 25,
                total_valid: 18,
                avg_latency_ms: 98.2,
                ok_rate: 88.0,
                success_rate: 72.0
            },
            ty: {
                packages_tested: 5,
                total_runs: 25,
                total_valid: 22,
                avg_latency_ms: 52.8,
                ok_rate: 96.0,
                success_rate: 88.0
            },
            zuban: {
                packages_tested: 5,
                total_runs: 25,
                total_valid: 21,
                avg_latency_ms: 75.3,
                ok_rate: 94.0,
                success_rate: 84.0
            }
        },
        results: [
            {
                package_name: 'requests',
                github_url: 'https://github.com/psf/requests',
                ranking: 1,
                error: null,
                metrics: {
                    pyright: { ok: true, valid_pct: 80, latency_ms: { mean: 125, p50: 120, p95: 180 } },
                    pyrefly: { ok: true, valid_pct: 70, latency_ms: { mean: 85, p50: 80, p95: 140 } },
                    ty: { ok: true, valid_pct: 90, latency_ms: { mean: 45, p50: 42, p95: 65 } },
                    zuban: { ok: true, valid_pct: 85, latency_ms: { mean: 65, p50: 60, p95: 95 } }
                }
            },
            {
                package_name: 'flask',
                github_url: 'https://github.com/pallets/flask',
                ranking: 2,
                error: null,
                metrics: {
                    pyright: { ok: true, valid_pct: 85, latency_ms: { mean: 155, p50: 150, p95: 220 } },
                    pyrefly: { ok: true, valid_pct: 75, latency_ms: { mean: 105, p50: 100, p95: 160 } },
                    ty: { ok: true, valid_pct: 88, latency_ms: { mean: 58, p50: 55, p95: 85 } },
                    zuban: { ok: true, valid_pct: 82, latency_ms: { mean: 78, p50: 72, p95: 115 } }
                }
            },
            {
                package_name: 'django',
                github_url: 'https://github.com/django/django',
                ranking: 3,
                error: null,
                metrics: {
                    pyright: { ok: true, valid_pct: 75, latency_ms: { mean: 280, p50: 260, p95: 420 } },
                    pyrefly: { ok: true, valid_pct: 68, latency_ms: { mean: 185, p50: 170, p95: 290 } },
                    ty: { ok: true, valid_pct: 82, latency_ms: { mean: 95, p50: 88, p95: 145 } },
                    zuban: { ok: true, valid_pct: 78, latency_ms: { mean: 120, p50: 110, p95: 185 } }
                }
            },
            {
                package_name: 'fastapi',
                github_url: 'https://github.com/fastapi/fastapi',
                ranking: 4,
                error: null,
                metrics: {
                    pyright: { ok: true, valid_pct: 90, latency_ms: { mean: 135, p50: 130, p95: 195 } },
                    pyrefly: { ok: true, valid_pct: 78, latency_ms: { mean: 92, p50: 88, p95: 145 } },
                    ty: { ok: true, valid_pct: 92, latency_ms: { mean: 48, p50: 45, p95: 72 } },
                    zuban: { ok: true, valid_pct: 88, latency_ms: { mean: 68, p50: 62, p95: 100 } }
                }
            },
            {
                package_name: 'pydantic',
                github_url: 'https://github.com/pydantic/pydantic',
                ranking: 5,
                error: null,
                metrics: {
                    pyright: { ok: true, valid_pct: 72, latency_ms: { mean: 168, p50: 160, p95: 250 } },
                    pyrefly: { ok: true, valid_pct: 65, latency_ms: { mean: 115, p50: 108, p95: 175 } },
                    ty: { ok: true, valid_pct: 85, latency_ms: { mean: 62, p50: 58, p95: 95 } },
                    zuban: { ok: true, valid_pct: 80, latency_ms: { mean: 82, p50: 75, p95: 125 } }
                }
            }
        ]
    };
}

// ---------------------------------------------------------------------------
// Error display
// ---------------------------------------------------------------------------

/**
 * Clear any error messages
 */
function clearError(): void {
    const errorMessages = document.querySelectorAll('.error-message');
    errorMessages.forEach(el => el.remove());
}

/**
 * Show error message to user with optional action link
 */
function showError(message: string, action: ErrorAction | null = null): void {
    clearError(); // Clear any existing errors first
    const main = document.querySelector('main');
    if (!main) return;
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message';
    errorDiv.style.cssText = `
        background: rgba(248, 81, 73, 0.1);
        border: 1px solid #f85149;
        color: #f85149;
        padding: 16px 24px;
        border-radius: 8px;
        margin: 24px 0;
        text-align: center;
    `;

    const messageSpan = document.createElement('span');
    messageSpan.textContent = message;
    errorDiv.appendChild(messageSpan);

    if (action) {
        const link = document.createElement('a');
        link.textContent = action.text;
        link.href = '#';
        link.style.cssText = `
            color: #58a6ff;
            margin-left: 8px;
            text-decoration: underline;
            cursor: pointer;
        `;
        link.addEventListener('click', (e: Event) => {
            e.preventDefault();
            action.onClick();
        });
        errorDiv.appendChild(link);
    }

    main.insertBefore(errorDiv, main.firstChild);
}

// ---------------------------------------------------------------------------
// Timestamp / versions
// ---------------------------------------------------------------------------

/**
 * Update the last updated timestamp
 */
function updateTimestamp(): void {
    const el = document.getElementById('lastUpdated');
    if (!el) return;
    if (benchmarkData?.timestamp) {
        const date = new Date(benchmarkData.timestamp);
        el.textContent = `Last updated: ${date.toLocaleDateString()} at ${date.toLocaleTimeString()}`;
    } else {
        el.textContent = 'Demo data - no benchmark results available';
    }

    // Update type checker versions in legend
    updateTypeCheckerVersions();
}

/**
 * Update type checker version displays in the legend
 */
function updateTypeCheckerVersions(): void {
    const versions = benchmarkData?.type_checker_versions || {};
    for (const [checker, version] of Object.entries(versions)) {
        const el = document.getElementById(`version-${checker}`);
        if (el && version && version !== 'unknown' && version !== 'not installed') {
            el.textContent = `v${version}`;
        }
    }
}

/**
 * Update overview statistics cards
 */
function updateOverviewStats(): void {
    if (!benchmarkData) return;
    const agg = benchmarkData.aggregate || {};
    const checkers = benchmarkData.type_checkers || [];

    // Package count
    const packageCountEl = document.getElementById('packageCount');
    if (packageCountEl) packageCountEl.textContent = String(benchmarkData.package_count || 0);

    // Checker count
    const checkerCountEl = document.getElementById('checkerCount');
    if (checkerCountEl) checkerCountEl.textContent = String(checkers.length);

    // Find fastest (lowest avg latency)
    let fastest: string | null = null;
    let lowestLatency = Infinity;
    for (const checker of checkers) {
        const latency = agg[checker]?.avg_latency_ms;
        if (latency && latency < lowestLatency) {
            lowestLatency = latency;
            fastest = checker;
        }
    }
    const fastestEl = document.getElementById('fastestChecker');
    if (fastestEl) fastestEl.textContent = fastest ? (CHECKER_NAMES[fastest] || fastest) : '-';

    // Find most accurate (highest success rate)
    let mostAccurate: string | null = null;
    let highestRate = 0;
    for (const checker of checkers) {
        const rate = agg[checker]?.success_rate;
        if (rate && rate > highestRate) {
            highestRate = rate;
            mostAccurate = checker;
        }
    }
    const mostAccurateEl = document.getElementById('mostAccurate');
    if (mostAccurateEl) mostAccurateEl.textContent = mostAccurate ? (CHECKER_NAMES[mostAccurate] || mostAccurate) : '-';
}

// ---------------------------------------------------------------------------
// Charts
// ---------------------------------------------------------------------------

/**
 * Create latency comparison chart
 */
function createLatencyChart(): void {
    if (!benchmarkData) return;
    const canvas = document.getElementById('latencyChart') as HTMLCanvasElement | null;
    const ctx = canvas?.getContext('2d');
    if (!ctx) return;

    const agg = benchmarkData.aggregate || {};
    const checkers = benchmarkData.type_checkers || [];

    const labels = checkers.map(c => CHECKER_NAMES[c] || c);
    const data = checkers.map(c => agg[c]?.avg_latency_ms || 0);
    const colors = checkers.map(c => CHECKER_COLORS[c] || '#888');

    charts.latency = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Average Latency (ms)',
                data: data,
                backgroundColor: colors,
                borderRadius: 6,
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (tooltipCtx: any) => `${tooltipCtx.raw.toFixed(1)} ms`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: '#30363d' },
                    ticks: {
                        color: '#8b949e',
                        callback: (value: any) => `${value} ms`
                    }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#c9d1d9' }
                }
            }
        }
    });
}

/**
 * Create success rate chart
 */
function createSuccessChart(): void {
    if (!benchmarkData) return;
    const canvas = document.getElementById('successChart') as HTMLCanvasElement | null;
    const ctx = canvas?.getContext('2d');
    if (!ctx) return;

    const agg = benchmarkData.aggregate || {};
    const checkers = benchmarkData.type_checkers || [];

    const labels = checkers.map(c => CHECKER_NAMES[c] || c);
    const data = checkers.map(c => agg[c]?.success_rate || 0);
    const colors = checkers.map(c => CHECKER_COLORS[c] || '#888');

    charts.success = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Success Rate (%)',
                data: data,
                backgroundColor: colors,
                borderRadius: 6,
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (tooltipCtx: any) => `${tooltipCtx.raw.toFixed(1)}%`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    grid: { color: '#30363d' },
                    ticks: {
                        color: '#8b949e',
                        callback: (value: any) => `${value}%`
                    }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#c9d1d9' }
                }
            }
        }
    });
}

/**
 * Create OK rate chart
 */
function createOkChart(): void {
    if (!benchmarkData) return;
    const canvas = document.getElementById('okChart') as HTMLCanvasElement | null;
    const ctx = canvas?.getContext('2d');
    if (!ctx) return;

    const agg = benchmarkData.aggregate || {};
    const checkers = benchmarkData.type_checkers || [];

    const labels = checkers.map(c => CHECKER_NAMES[c] || c);
    const data = checkers.map(c => agg[c]?.ok_rate || 0);
    const colors = checkers.map(c => CHECKER_COLORS[c] || '#888');

    charts.ok = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'OK Rate (%)',
                data: data,
                backgroundColor: colors,
                borderRadius: 6,
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (tooltipCtx: any) => `${tooltipCtx.raw.toFixed(1)}%`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    grid: { color: '#30363d' },
                    ticks: {
                        color: '#8b949e',
                        callback: (value: any) => `${value}%`
                    }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#c9d1d9' }
                }
            }
        }
    });
}

/**
 * Create package comparison chart
 */
function createPackageComparisonChart(): void {
    if (!benchmarkData) return;
    const canvas = document.getElementById('packageComparisonChart') as HTMLCanvasElement | null;
    const ctx = canvas?.getContext('2d');
    if (!ctx) return;

    const results = (benchmarkData.results || []).filter(r => !r.error).slice(0, 10);
    const checkers = benchmarkData.type_checkers || [];

    const labels = results.map(r => r.package_name);

    const datasets = checkers.map(checker => ({
        label: CHECKER_NAMES[checker] || checker,
        data: results.map(r => {
            const metrics = r.metrics?.[checker];
            return metrics?.latency_ms?.p95 || 0;
        }),
        backgroundColor: CHECKER_COLORS[checker] || '#888',
        borderRadius: 4,
        borderWidth: 0
    }));

    charts.packageComparison = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                title: {
                    display: true,
                    text: 'Latency by Package (p95)',
                    color: '#c9d1d9',
                    font: { size: 16 }
                },
                legend: {
                    position: 'top',
                    labels: {
                        color: '#c9d1d9',
                        usePointStyle: true,
                        padding: 20
                    }
                },
                tooltip: {
                    callbacks: {
                        label: (tooltipCtx: any) => `${tooltipCtx.dataset.label}: ${tooltipCtx.raw.toFixed(1)} ms`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: '#30363d' },
                    ticks: {
                        color: '#8b949e',
                        callback: (value: any) => `${value} ms`
                    },
                    title: {
                        display: true,
                        text: 'Latency (ms)',
                        color: '#8b949e'
                    }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#c9d1d9' }
                }
            }
        }
    });
}

// ---------------------------------------------------------------------------
// Results table
// ---------------------------------------------------------------------------

interface TableRow {
    package: string;
    github_url: string;
    checker: string;
    avgLatency?: number;
    p50Latency?: number;
    p95Latency?: number;
    okPct?: number;
    validPct?: number;
    hasError: boolean;
    error: string | null | undefined;
}

/**
 * Populate the results table
 */
function populateResultsTable(filterText: string = '', sortBy: string = 'ranking'): void {
    if (!benchmarkData) return;
    const tbody = document.getElementById('resultsBody');
    if (!tbody) return;

    let results = benchmarkData.results || [];
    const checkers = benchmarkData.type_checkers || [];

    // Filter
    if (filterText) {
        const filter = filterText.toLowerCase();
        results = results.filter(r =>
            r.package_name.toLowerCase().includes(filter)
        );
    }

    // Sort
    results = [...results].sort((a, b) => {
        switch (sortBy) {
            case 'name':
                return a.package_name.localeCompare(b.package_name);
            case 'latency': {
                const aLat = getMinLatency(a, checkers);
                const bLat = getMinLatency(b, checkers);
                return aLat - bLat;
            }
            case 'success': {
                const aSuccess = getMaxSuccess(a, checkers);
                const bSuccess = getMaxSuccess(b, checkers);
                return bSuccess - aSuccess;
            }
            default: // ranking
                return (a.ranking || 999) - (b.ranking || 999);
        }
    });

    // Build rows
    const rows: TableRow[] = [];

    for (const result of results) {
        for (const checker of checkers) {
            const metrics = result.metrics?.[checker];
            const hasError = !!(result.error || !metrics?.ok);

            rows.push({
                package: result.package_name,
                github_url: result.github_url,
                checker: checker,
                avgLatency: metrics?.latency_ms?.mean,
                p50Latency: metrics?.latency_ms?.p50,
                p95Latency: metrics?.latency_ms?.p95,
                okPct: metrics?.ok_pct,
                validPct: metrics?.valid_pct,
                hasError: hasError,
                error: result.error || metrics?.error
            });
        }
    }

    // Render
    if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="loading-row">No results found</td></tr>`;
        return;
    }

    tbody.innerHTML = rows.map((row, idx) => {
        const isFirstInGroup = idx === 0 || rows[idx - 1].package !== row.package;
        const packageCell = isFirstInGroup
            ? `<td class="package-name" rowspan="${checkers.length}">
                 <a href="${row.github_url}" target="_blank">${row.package}</a>
               </td>`
            : '';

        return `
            <tr>
                ${packageCell}
                <td><span class="checker-badge ${row.checker}">${CHECKER_NAMES[row.checker] || row.checker}</span></td>
                <td class="latency">${formatLatency(row.avgLatency)}</td>
                <td class="latency">${formatLatency(row.p50Latency)}</td>
                <td class="latency">${formatLatency(row.p95Latency)}</td>
                <td>${formatPercent(row.okPct)}</td>
                <td>${formatPercent(row.validPct)}</td>
            </tr>
        `;
    }).join('');
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

/**
 * Format latency value
 */
function formatLatency(value: number | undefined): string {
    if (value == null) return '-';
    return `${value.toFixed(1)} ms`;
}

/**
 * Format percentage value
 */
function formatPercent(value: number | undefined): string {
    if (value == null) return '-';
    return `${value.toFixed(1)}%`;
}

/**
 * Get minimum latency across checkers for a result
 */
function getMinLatency(result: BenchmarkResult, checkers: string[]): number {
    let min = Infinity;
    for (const checker of checkers) {
        const lat = result.metrics?.[checker]?.latency_ms?.mean;
        if (lat && lat < min) min = lat;
    }
    return min === Infinity ? 0 : min;
}

/**
 * Get maximum success rate across checkers for a result
 */
function getMaxSuccess(result: BenchmarkResult, checkers: string[]): number {
    let max = 0;
    for (const checker of checkers) {
        const rate = result.metrics?.[checker]?.valid_pct;
        if (rate && rate > max) max = rate;
    }
    return max;
}

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------

/**
 * Setup filter controls
 */
function setupFilters(): void {
    const searchInput = document.getElementById('packageSearch') as HTMLInputElement | null;
    const sortSelect = document.getElementById('sortBy') as HTMLSelectElement | null;

    if (searchInput) {
        searchInput.addEventListener('input', () => {
            const sortByVal = sortSelect?.value || 'ranking';
            populateResultsTable(searchInput.value, sortByVal);
        });
    }

    if (sortSelect) {
        sortSelect.addEventListener('change', () => {
            const filterTextVal = searchInput?.value || '';
            populateResultsTable(filterTextVal, sortSelect.value);
        });
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', init);

export {};
