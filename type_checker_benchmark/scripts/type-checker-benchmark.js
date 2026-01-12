/**
 * Type Checker Error Benchmark Results Viewer
 * Loads and displays benchmark data from JSON files
 */

const CHECKER_COLORS = {
    pyright: '#3178c6',
    pyrefly: '#e74c3c',
    ty: '#9b59b6',
    mypy: '#2ecc71',
    zuban: '#f39c12'
};

const CHECKER_NAMES = {
    pyright: 'Pyright',
    pyrefly: 'Pyrefly',
    ty: 'ty',
    mypy: 'Mypy',
    zuban: 'Zuban'
};

let benchmarkData = null;
let charts = {};

/**
 * Get date from URL query string
 * @returns {string|null} Date string (YYYY-MM-DD) or null if not specified
 */
function getDateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const date = params.get('date');
    if (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) {
        return date;
    }
    return null;
}

/**
 * Update URL query string with date
 * @param {string|null} date - Date to set, or null to remove
 */
function updateUrlWithDate(date) {
    const url = new URL(window.location);
    if (date) {
        url.searchParams.set('date', date);
    } else {
        url.searchParams.delete('date');
    }
    window.history.replaceState({}, '', url);
}

/**
 * Initialize the dashboard
 */
async function init() {
    try {
        const urlDate = getDateFromUrl();
        await loadBenchmarkData(urlDate);
        updateTimestamp();
        createTotalErrorsChart();
        createAvgErrorsChart();
        createPackageComparisonChart();
        createExecutionTimeChart();
        populateResultsTable();
        setupFilters();
        setupDateSelector();
    } catch (error) {
        console.error('Failed to initialize dashboard:', error);
        const urlDate = getDateFromUrl();
        if (urlDate) {
            showError(`No benchmark data available for ${urlDate}.`, {
                text: 'Load latest results →',
                onClick: () => switchToDate(null)
            });
        } else {
            showError('Failed to load benchmark data. Please try again later.');
        }
    }
}

/**
 * Setup date selector event listeners
 */
function setupDateSelector() {
    const dateInput = document.getElementById('dateSelect');
    const loadBtn = document.getElementById('loadDateBtn');
    const latestBtn = document.getElementById('latestBtn');
    
    if (!dateInput || !loadBtn || !latestBtn) return;
    
    if (benchmarkData?.date) {
        dateInput.value = benchmarkData.date;
    }
    
    loadBtn.addEventListener('click', async () => {
        const date = dateInput.value;
        if (date) {
            await switchToDate(date);
        }
    });
    
    latestBtn.addEventListener('click', async () => {
        await switchToDate(null);
        if (benchmarkData?.date) {
            dateInput.value = benchmarkData.date;
        }
    });
    
    dateInput.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter') {
            const date = dateInput.value;
            if (date) {
                await switchToDate(date);
            }
        }
    });
}

/**
 * Load benchmark results from JSON file
 * @param {string|null} date - Optional date string (YYYY-MM-DD) to load historical data
 */
async function loadBenchmarkData(date = null) {
    let paths;
    
    if (date) {
        paths = [
            `./results/benchmark_${date}.json`,
            `../type_checker_benchmark/results/benchmark_${date}.json`
        ];
    } else {
        paths = [
            './results/latest.json',
            '../type_checker_benchmark/results/latest.json'
        ];
    }
    
    for (const path of paths) {
        try {
            const response = await fetch(path);
            if (response.ok) {
                benchmarkData = await response.json();
                console.log('Loaded benchmark data from:', path);
                return benchmarkData;
            }
        } catch (e) {
            console.warn(`Failed to load from ${path}:`, e);
        }
    }
    
    if (date) {
        throw new Error(`No benchmark data found for ${date}`);
    }
    
    console.log('Using demo data');
    benchmarkData = getDemoData();
    return benchmarkData;
}

/**
 * Switch to a different date's benchmark data
 */
async function switchToDate(date) {
    try {
        await loadBenchmarkData(date);
        clearError();
        updateTimestamp();
        
        const loadedDate = benchmarkData?.date || date;
        updateUrlWithDate(loadedDate);
        
        const dateInput = document.getElementById('dateSelect');
        if (dateInput && loadedDate) {
            dateInput.value = loadedDate;
        }
        
        Object.values(charts).forEach(chart => chart?.destroy());
        charts = {};
        
        createTotalErrorsChart();
        createAvgErrorsChart();
        createPackageComparisonChart();
        createExecutionTimeChart();
        populateResultsTable();
    } catch (error) {
        console.error('Failed to load data for date:', date, error);
        showError(`No benchmark data available for ${date}.`, {
            text: 'Load latest results →',
            onClick: () => switchToDate(null)
        });
    }
}

/**
 * Demo data for development/testing
 */
function getDemoData() {
    return {
        timestamp: new Date().toISOString(),
        date: new Date().toISOString().split('T')[0],
        type_checkers: ['pyright', 'pyrefly', 'ty', 'mypy'],
        package_count: 5,
        aggregate: {
            pyright: {
                packages_tested: 5,
                total_errors: 245,
                total_warnings: 120,
                avg_errors_per_package: 49.0,
                min_errors: 12,
                max_errors: 85,
                avg_execution_time_s: 12.5
            },
            pyrefly: {
                packages_tested: 5,
                total_errors: 312,
                total_warnings: 45,
                avg_errors_per_package: 62.4,
                min_errors: 18,
                max_errors: 120,
                avg_execution_time_s: 8.2
            },
            ty: {
                packages_tested: 5,
                total_errors: 180,
                total_warnings: 65,
                avg_errors_per_package: 36.0,
                min_errors: 8,
                max_errors: 70,
                avg_execution_time_s: 3.5
            },
            mypy: {
                packages_tested: 5,
                total_errors: 298,
                total_warnings: 85,
                avg_errors_per_package: 59.6,
                min_errors: 15,
                max_errors: 95,
                avg_execution_time_s: 25.8
            }
        },
        results: [
            {
                package_name: 'requests',
                github_url: 'https://github.com/psf/requests',
                ranking: 1,
                error: null,
                metrics: {
                    pyright: { ok: true, error_count: 45, warning_count: 22, execution_time_s: 8.5 },
                    pyrefly: { ok: true, error_count: 62, warning_count: 8, execution_time_s: 5.2 },
                    ty: { ok: true, error_count: 28, warning_count: 12, execution_time_s: 2.1 },
                    mypy: { ok: true, error_count: 58, warning_count: 18, execution_time_s: 18.5 }
                }
            },
            {
                package_name: 'flask',
                github_url: 'https://github.com/pallets/flask',
                ranking: 2,
                error: null,
                metrics: {
                    pyright: { ok: true, error_count: 38, warning_count: 28, execution_time_s: 10.2 },
                    pyrefly: { ok: true, error_count: 48, warning_count: 12, execution_time_s: 6.8 },
                    ty: { ok: true, error_count: 32, warning_count: 15, execution_time_s: 2.8 },
                    mypy: { ok: true, error_count: 52, warning_count: 20, execution_time_s: 22.4 }
                }
            },
            {
                package_name: 'django',
                github_url: 'https://github.com/django/django',
                ranking: 3,
                error: null,
                metrics: {
                    pyright: { ok: true, error_count: 85, warning_count: 35, execution_time_s: 18.5 },
                    pyrefly: { ok: true, error_count: 120, warning_count: 15, execution_time_s: 12.5 },
                    ty: { ok: true, error_count: 70, warning_count: 22, execution_time_s: 5.8 },
                    mypy: { ok: true, error_count: 95, warning_count: 28, execution_time_s: 38.2 }
                }
            },
            {
                package_name: 'fastapi',
                github_url: 'https://github.com/fastapi/fastapi',
                ranking: 4,
                error: null,
                metrics: {
                    pyright: { ok: true, error_count: 25, warning_count: 15, execution_time_s: 7.8 },
                    pyrefly: { ok: true, error_count: 35, warning_count: 5, execution_time_s: 4.5 },
                    ty: { ok: true, error_count: 18, warning_count: 8, execution_time_s: 1.8 },
                    mypy: { ok: true, error_count: 42, warning_count: 10, execution_time_s: 15.2 }
                }
            },
            {
                package_name: 'pydantic',
                github_url: 'https://github.com/pydantic/pydantic',
                ranking: 5,
                error: null,
                metrics: {
                    pyright: { ok: true, error_count: 52, warning_count: 20, execution_time_s: 12.5 },
                    pyrefly: { ok: true, error_count: 47, warning_count: 5, execution_time_s: 8.0 },
                    ty: { ok: true, error_count: 32, warning_count: 8, execution_time_s: 4.2 },
                    mypy: { ok: true, error_count: 51, warning_count: 9, execution_time_s: 28.5 }
                }
            }
        ]
    };
}

/**
 * Clear any error messages
 */
function clearError() {
    const errorMessages = document.querySelectorAll('.error-message');
    errorMessages.forEach(el => el.remove());
}

/**
 * Show error message to user
 */
function showError(message, action = null) {
    clearError();
    const main = document.querySelector('main');
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
        link.addEventListener('click', (e) => {
            e.preventDefault();
            action.onClick();
        });
        errorDiv.appendChild(link);
    }
    
    main.insertBefore(errorDiv, main.firstChild);
}

/**
 * Update the last updated timestamp
 */
function updateTimestamp() {
    const el = document.getElementById('lastUpdated');
    if (benchmarkData?.timestamp) {
        const date = new Date(benchmarkData.timestamp);
        el.textContent = `Last updated: ${date.toLocaleDateString()} at ${date.toLocaleTimeString()}`;
    } else {
        el.textContent = 'Demo data - no benchmark results available';
    }
    
    updateTypeCheckerVersions();
}

/**
 * Update type checker version displays
 */
function updateTypeCheckerVersions() {
    const versions = benchmarkData?.type_checker_versions || {};
    for (const [checker, version] of Object.entries(versions)) {
        const el = document.getElementById(`version-${checker}`);
        if (el && version && version !== 'unknown' && version !== 'not installed') {
            el.textContent = `v${version}`;
        }
    }
}

/**
 * Create total errors chart
 */
function createTotalErrorsChart() {
    const ctx = document.getElementById('totalErrorsChart')?.getContext('2d');
    if (!ctx) return;
    
    const agg = benchmarkData.aggregate || {};
    const checkers = benchmarkData.type_checkers || [];
    
    const labels = checkers.map(c => CHECKER_NAMES[c] || c);
    const data = checkers.map(c => agg[c]?.total_errors || 0);
    const colors = checkers.map(c => CHECKER_COLORS[c] || '#888');
    
    charts.totalErrors = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Total Errors',
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
                        label: (ctx) => `${ctx.raw.toLocaleString()} errors`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: '#30363d' },
                    ticks: { color: '#8b949e' }
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
 * Create average errors per package chart
 */
function createAvgErrorsChart() {
    const ctx = document.getElementById('avgErrorsChart')?.getContext('2d');
    if (!ctx) return;
    
    const agg = benchmarkData.aggregate || {};
    const checkers = benchmarkData.type_checkers || [];
    
    const labels = checkers.map(c => CHECKER_NAMES[c] || c);
    const data = checkers.map(c => agg[c]?.avg_errors_per_package || 0);
    const colors = checkers.map(c => CHECKER_COLORS[c] || '#888');
    
    charts.avgErrors = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Avg Errors/Package',
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
                        label: (ctx) => `${ctx.raw.toFixed(1)} errors/package`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: '#30363d' },
                    ticks: { color: '#8b949e' }
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
function createPackageComparisonChart() {
    const ctx = document.getElementById('packageComparisonChart')?.getContext('2d');
    if (!ctx) return;
    
    const results = benchmarkData.results || [];
    const checkers = benchmarkData.type_checkers || [];
    
    // Get packages with valid metrics
    const validResults = results.filter(r => !r.error && r.metrics);
    const labels = validResults.map(r => r.package_name);
    
    const datasets = checkers.map(checker => ({
        label: CHECKER_NAMES[checker] || checker,
        data: validResults.map(r => r.metrics[checker]?.error_count || 0),
        backgroundColor: CHECKER_COLORS[checker] || '#888',
        borderRadius: 4
    }));
    
    charts.packageComparison = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: '#c9d1d9' }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: '#30363d' },
                    ticks: { color: '#8b949e' },
                    title: {
                        display: true,
                        text: 'Error Count',
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

/**
 * Create execution time comparison chart
 */
function createExecutionTimeChart() {
    const ctx = document.getElementById('executionTimeChart')?.getContext('2d');
    if (!ctx) return;
    
    const agg = benchmarkData.aggregate || {};
    const checkers = benchmarkData.type_checkers || [];
    
    const labels = checkers.map(c => CHECKER_NAMES[c] || c);
    const data = checkers.map(c => agg[c]?.avg_execution_time_s || 0);
    const colors = checkers.map(c => CHECKER_COLORS[c] || '#888');
    
    charts.executionTime = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Avg Execution Time (s)',
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
                        label: (ctx) => `${ctx.raw.toFixed(1)}s`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: '#30363d' },
                    ticks: { color: '#8b949e' },
                    title: {
                        display: true,
                        text: 'Seconds',
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

/**
 * Populate the results table
 */
function populateResultsTable() {
    const tbody = document.getElementById('resultsBody');
    if (!tbody) return;
    
    const results = benchmarkData.results || [];
    const checkers = benchmarkData.type_checkers || [];
    
    tbody.innerHTML = '';
    
    for (const result of results) {
        for (let i = 0; i < checkers.length; i++) {
            const checker = checkers[i];
            const metrics = result.metrics?.[checker];
            
            const row = document.createElement('tr');
            
            // Package name (only on first row for each package)
            const packageCell = document.createElement('td');
            if (i === 0) {
                packageCell.rowSpan = checkers.length;
                packageCell.className = 'package-name';
                if (result.github_url) {
                    const link = document.createElement('a');
                    link.href = result.github_url;
                    link.target = '_blank';
                    link.textContent = result.package_name;
                    packageCell.appendChild(link);
                } else {
                    packageCell.textContent = result.package_name;
                }
                row.appendChild(packageCell);
            }
            
            // Type checker badge
            const checkerCell = document.createElement('td');
            const badge = document.createElement('span');
            badge.className = `checker-badge ${checker}`;
            badge.textContent = CHECKER_NAMES[checker] || checker;
            checkerCell.appendChild(badge);
            row.appendChild(checkerCell);
            
            // Error count
            const errorCell = document.createElement('td');
            errorCell.className = 'error-count';
            if (result.error) {
                errorCell.textContent = '-';
            } else if (metrics?.ok) {
                errorCell.textContent = (metrics.error_count || 0).toLocaleString();
            } else {
                errorCell.textContent = metrics?.error_message || 'Failed';
            }
            row.appendChild(errorCell);
            
            // Warning count
            const warningCell = document.createElement('td');
            if (result.error || !metrics?.ok) {
                warningCell.textContent = '-';
            } else {
                warningCell.textContent = (metrics.warning_count || 0).toLocaleString();
            }
            row.appendChild(warningCell);
            
            // Execution time
            const timeCell = document.createElement('td');
            if (result.error || !metrics?.ok) {
                timeCell.textContent = '-';
            } else {
                const time = metrics.execution_time_s;
                timeCell.textContent = time ? `${time.toFixed(1)}s` : '-';
            }
            row.appendChild(timeCell);
            
            // Status badge
            const statusCell = document.createElement('td');
            const statusBadge = document.createElement('span');
            if (result.error) {
                statusBadge.className = 'status-badge error';
                statusBadge.textContent = 'Skipped';
            } else if (metrics?.ok) {
                statusBadge.className = 'status-badge success';
                statusBadge.textContent = 'OK';
            } else {
                statusBadge.className = 'status-badge error';
                statusBadge.textContent = 'Failed';
            }
            statusCell.appendChild(statusBadge);
            row.appendChild(statusCell);
            
            tbody.appendChild(row);
        }
    }
}

/**
 * Setup filter and search functionality
 */
function setupFilters() {
    const searchInput = document.getElementById('packageSearch');
    const sortSelect = document.getElementById('sortBy');
    
    if (searchInput) {
        searchInput.addEventListener('input', applyFilters);
    }
    
    if (sortSelect) {
        sortSelect.addEventListener('change', applyFilters);
    }
}

/**
 * Apply filters and sorting to the results
 */
function applyFilters() {
    const searchInput = document.getElementById('packageSearch');
    const sortSelect = document.getElementById('sortBy');
    
    const searchTerm = searchInput?.value.toLowerCase() || '';
    const sortBy = sortSelect?.value || 'ranking';
    
    let results = [...(benchmarkData.results || [])];
    
    // Filter by search term
    if (searchTerm) {
        results = results.filter(r => 
            r.package_name.toLowerCase().includes(searchTerm)
        );
    }
    
    // Sort results
    results.sort((a, b) => {
        switch (sortBy) {
            case 'name':
                return a.package_name.localeCompare(b.package_name);
            case 'errors':
                const aErrors = getMaxErrors(a);
                const bErrors = getMaxErrors(b);
                return bErrors - aErrors;
            case 'time':
                const aTime = getAvgTime(a);
                const bTime = getAvgTime(b);
                return bTime - aTime;
            case 'ranking':
            default:
                return (a.ranking || 999) - (b.ranking || 999);
        }
    });
    
    // Update the table with filtered/sorted results
    const tempData = { ...benchmarkData, results };
    const originalData = benchmarkData;
    benchmarkData = tempData;
    populateResultsTable();
    benchmarkData = originalData;
}

/**
 * Get max errors across all checkers for a result
 */
function getMaxErrors(result) {
    if (result.error || !result.metrics) return 0;
    return Math.max(...Object.values(result.metrics)
        .filter(m => m?.ok)
        .map(m => m.error_count || 0));
}

/**
 * Get average execution time across all checkers
 */
function getAvgTime(result) {
    if (result.error || !result.metrics) return 0;
    const times = Object.values(result.metrics)
        .filter(m => m?.ok && m.execution_time_s)
        .map(m => m.execution_time_s);
    return times.length ? times.reduce((a, b) => a + b, 0) / times.length : 0;
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', init);
