/**
 * LSP Benchmark Results Viewer
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
 * Initialize the dashboard
 */
async function init() {
    try {
        await loadBenchmarkData();
        updateTimestamp();
        createLatencyChart();
        createSuccessChart();
        createPackageComparisonChart();
        populateResultsTable();
        setupFilters();
        setupDateSelector();
    } catch (error) {
        console.error('Failed to initialize dashboard:', error);
        showError('Failed to load benchmark data. Please try again later.');
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
    
    // Set default value to current data's date
    if (benchmarkData?.date) {
        dateInput.value = benchmarkData.date;
    }
    
    // Load specific date
    loadBtn.addEventListener('click', async () => {
        const date = dateInput.value;
        if (date) {
            await switchToDate(date);
        }
    });
    
    // Load latest
    latestBtn.addEventListener('click', async () => {
        await switchToDate(null);
        if (benchmarkData?.date) {
            dateInput.value = benchmarkData.date;
        }
    });
    
    // Also allow Enter key to load
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
        // Load specific date
        paths = [
            `./results/benchmark_${date}.json`,
            `../lsp/benchmark/results/benchmark_${date}.json`
        ];
    } else {
        // Load latest
        paths = [
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
                return benchmarkData;
            }
        } catch (e) {
            console.warn(`Failed to load from ${path}:`, e);
        }
    }
    
    if (date) {
        // If specific date failed, show error
        throw new Error(`No benchmark data found for ${date}`);
    }
    
    // Use demo data if no file found
    console.log('Using demo data');
    benchmarkData = getDemoData();
    return benchmarkData;
}

/**
 * Load available benchmark dates from the results directory
 */
async function loadAvailableDates() {
    const dates = [];
    
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
        } catch (e) {
            // File doesn't exist, continue
        }
    }
    
    return dates;
}

/**
 * Switch to a different date's benchmark data
 */
async function switchToDate(date) {
    try {
        await loadBenchmarkData(date);
        updateTimestamp();
        
        // Destroy existing charts
        Object.values(charts).forEach(chart => chart?.destroy());
        charts = {};
        
        // Recreate charts and table
        createLatencyChart();
        createSuccessChart();
        createPackageComparisonChart();
        populateResultsTable();
    } catch (error) {
        console.error('Failed to load data for date:', date, error);
        showError(`No benchmark data available for ${date}`);
    }
}

/**
 * Demo data for development/testing
 */
function getDemoData() {
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
                success_rate: 80.0
            },
            pyrefly: {
                packages_tested: 5,
                total_runs: 25,
                total_valid: 18,
                avg_latency_ms: 98.2,
                success_rate: 72.0
            },
            ty: {
                packages_tested: 5,
                total_runs: 25,
                total_valid: 22,
                avg_latency_ms: 52.8,
                success_rate: 88.0
            },
            zuban: {
                packages_tested: 5,
                total_runs: 25,
                total_valid: 21,
                avg_latency_ms: 75.3,
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
                    pyright: { ok: true, valid_pct: 80, found_pct: 100, latency_ms: { mean: 125, p50: 120, p95: 180 } },
                    pyrefly: { ok: true, valid_pct: 70, found_pct: 90, latency_ms: { mean: 85, p50: 80, p95: 140 } },
                    ty: { ok: true, valid_pct: 90, found_pct: 100, latency_ms: { mean: 45, p50: 42, p95: 65 } },
                    zuban: { ok: true, valid_pct: 85, found_pct: 95, latency_ms: { mean: 65, p50: 60, p95: 95 } }
                }
            },
            {
                package_name: 'flask',
                github_url: 'https://github.com/pallets/flask',
                ranking: 2,
                error: null,
                metrics: {
                    pyright: { ok: true, valid_pct: 85, found_pct: 95, latency_ms: { mean: 155, p50: 150, p95: 220 } },
                    pyrefly: { ok: true, valid_pct: 75, found_pct: 85, latency_ms: { mean: 105, p50: 100, p95: 160 } },
                    ty: { ok: true, valid_pct: 88, found_pct: 98, latency_ms: { mean: 58, p50: 55, p95: 85 } },
                    zuban: { ok: true, valid_pct: 82, found_pct: 92, latency_ms: { mean: 78, p50: 72, p95: 115 } }
                }
            },
            {
                package_name: 'django',
                github_url: 'https://github.com/django/django',
                ranking: 3,
                error: null,
                metrics: {
                    pyright: { ok: true, valid_pct: 75, found_pct: 90, latency_ms: { mean: 280, p50: 260, p95: 420 } },
                    pyrefly: { ok: true, valid_pct: 68, found_pct: 82, latency_ms: { mean: 185, p50: 170, p95: 290 } },
                    ty: { ok: true, valid_pct: 82, found_pct: 95, latency_ms: { mean: 95, p50: 88, p95: 145 } },
                    zuban: { ok: true, valid_pct: 78, found_pct: 88, latency_ms: { mean: 120, p50: 110, p95: 185 } }
                }
            },
            {
                package_name: 'fastapi',
                github_url: 'https://github.com/fastapi/fastapi',
                ranking: 4,
                error: null,
                metrics: {
                    pyright: { ok: true, valid_pct: 90, found_pct: 100, latency_ms: { mean: 135, p50: 130, p95: 195 } },
                    pyrefly: { ok: true, valid_pct: 78, found_pct: 92, latency_ms: { mean: 92, p50: 88, p95: 145 } },
                    ty: { ok: true, valid_pct: 92, found_pct: 100, latency_ms: { mean: 48, p50: 45, p95: 72 } },
                    zuban: { ok: true, valid_pct: 88, found_pct: 96, latency_ms: { mean: 68, p50: 62, p95: 100 } }
                }
            },
            {
                package_name: 'pydantic',
                github_url: 'https://github.com/pydantic/pydantic',
                ranking: 5,
                error: null,
                metrics: {
                    pyright: { ok: true, valid_pct: 72, found_pct: 88, latency_ms: { mean: 168, p50: 160, p95: 250 } },
                    pyrefly: { ok: true, valid_pct: 65, found_pct: 80, latency_ms: { mean: 115, p50: 108, p95: 175 } },
                    ty: { ok: true, valid_pct: 85, found_pct: 95, latency_ms: { mean: 62, p50: 58, p95: 95 } },
                    zuban: { ok: true, valid_pct: 80, found_pct: 90, latency_ms: { mean: 82, p50: 75, p95: 125 } }
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
function showError(message) {
    clearError(); // Clear any existing errors first
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
    errorDiv.textContent = message;
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
}

/**
 * Update overview statistics cards
 */
function updateOverviewStats() {
    const agg = benchmarkData.aggregate || {};
    const checkers = benchmarkData.type_checkers || [];
    
    // Package count
    document.getElementById('packageCount').textContent = benchmarkData.package_count || 0;
    
    // Checker count
    document.getElementById('checkerCount').textContent = checkers.length;
    
    // Find fastest (lowest avg latency)
    let fastest = null;
    let lowestLatency = Infinity;
    for (const checker of checkers) {
        const latency = agg[checker]?.avg_latency_ms;
        if (latency && latency < lowestLatency) {
            lowestLatency = latency;
            fastest = checker;
        }
    }
    document.getElementById('fastestChecker').textContent = fastest ? 
        `${CHECKER_NAMES[fastest] || fastest}` : '-';
    
    // Find most accurate (highest success rate)
    let mostAccurate = null;
    let highestRate = 0;
    for (const checker of checkers) {
        const rate = agg[checker]?.success_rate;
        if (rate && rate > highestRate) {
            highestRate = rate;
            mostAccurate = checker;
        }
    }
    document.getElementById('mostAccurate').textContent = mostAccurate ?
        `${CHECKER_NAMES[mostAccurate] || mostAccurate}` : '-';
}

/**
 * Create latency comparison chart
 */
function createLatencyChart() {
    const ctx = document.getElementById('latencyChart')?.getContext('2d');
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
                        label: (ctx) => `${ctx.raw.toFixed(1)} ms`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: '#30363d' },
                    ticks: { 
                        color: '#8b949e',
                        callback: (value) => `${value} ms`
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
function createSuccessChart() {
    const ctx = document.getElementById('successChart')?.getContext('2d');
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
                        label: (ctx) => `${ctx.raw.toFixed(1)}%`
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
                        callback: (value) => `${value}%`
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
function createPackageComparisonChart() {
    const ctx = document.getElementById('packageComparisonChart')?.getContext('2d');
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
                        label: (ctx) => `${ctx.dataset.label}: ${ctx.raw.toFixed(1)} ms`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: '#30363d' },
                    ticks: { 
                        color: '#8b949e',
                        callback: (value) => `${value} ms`
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

/**
 * Populate the results table
 */
function populateResultsTable(filterText = '', sortBy = 'ranking') {
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
            case 'latency':
                const aLat = getMinLatency(a, checkers);
                const bLat = getMinLatency(b, checkers);
                return aLat - bLat;
            case 'success':
                const aSuccess = getMaxSuccess(a, checkers);
                const bSuccess = getMaxSuccess(b, checkers);
                return bSuccess - aSuccess;
            default: // ranking
                return (a.ranking || 999) - (b.ranking || 999);
        }
    });
    
    // Build rows
    const rows = [];
    
    for (const result of results) {
        for (const checker of checkers) {
            const metrics = result.metrics?.[checker];
            const hasError = result.error || !metrics?.ok;
            
            rows.push({
                package: result.package_name,
                github_url: result.github_url,
                checker: checker,
                avgLatency: metrics?.latency_ms?.mean,
                p50Latency: metrics?.latency_ms?.p50,
                p95Latency: metrics?.latency_ms?.p95,
                validPct: metrics?.valid_pct,
                foundPct: metrics?.found_pct,
                hasError: hasError,
                error: result.error || metrics?.error
            });
        }
    }
    
    // Render
    if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="loading-row">No results found</td></tr>`;
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
                <td>${formatPercent(row.validPct)}</td>
                <td>${formatPercent(row.foundPct)}</td>
            </tr>
        `;
    }).join('');
}

/**
 * Format latency value
 */
function formatLatency(value) {
    if (value == null) return '-';
    return `${value.toFixed(1)} ms`;
}

/**
 * Format percentage value
 */
function formatPercent(value) {
    if (value == null) return '-';
    return `${value.toFixed(1)}%`;
}

/**
 * Get minimum latency across checkers for a result
 */
function getMinLatency(result, checkers) {
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
function getMaxSuccess(result, checkers) {
    let max = 0;
    for (const checker of checkers) {
        const rate = result.metrics?.[checker]?.valid_pct;
        if (rate && rate > max) max = rate;
    }
    return max;
}

/**
 * Setup filter controls
 */
function setupFilters() {
    const searchInput = document.getElementById('packageSearch');
    const sortSelect = document.getElementById('sortBy');
    
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const sortBy = sortSelect?.value || 'ranking';
            populateResultsTable(e.target.value, sortBy);
        });
    }
    
    if (sortSelect) {
        sortSelect.addEventListener('change', (e) => {
            const filterText = searchInput?.value || '';
            populateResultsTable(filterText, e.target.value);
        });
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', init);
