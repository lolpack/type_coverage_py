/**
 * Type Checker Timing Benchmark Dashboard
 * Loads and displays timing/memory benchmark data from JSON files.
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
let currentOs = 'ubuntu';

// ---------------------------------------------------------------------------
// URL helpers
// ---------------------------------------------------------------------------

function getOsFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const os = params.get('os');
    return (os && ['ubuntu', 'macos', 'windows'].includes(os)) ? os : 'ubuntu';
}

function getDateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const date = params.get('date');
    return (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) ? date : null;
}

function updateUrlWithDate(date, os) {
    const url = new URL(window.location);
    if (date) url.searchParams.set('date', date);
    else url.searchParams.delete('date');
    if (os) url.searchParams.set('os', os);
    window.history.replaceState({}, '', url);
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function loadBenchmarkData(date, os) {
    let paths;
    if (date) {
        paths = [
            `./results/benchmark_${date}_${os}.json`,
            `./results/benchmark_${date}.json`
        ];
    } else {
        paths = [
            `./results/latest-${os}.json`,
            './results/latest.json'
        ];
    }

    for (const path of paths) {
        try {
            const response = await fetch(path);
            if (response.ok) {
                benchmarkData = await response.json();
                console.log('Loaded data from:', path);
                return benchmarkData;
            }
        } catch (e) {
            console.warn(`Failed to load ${path}:`, e);
        }
    }

    if (date) throw new Error(`No data for ${date} on ${os}`);

    console.log('Using demo data');
    benchmarkData = getDemoData();
    return benchmarkData;
}

function getDemoData() {
    return {
        timestamp: new Date().toISOString(),
        date: new Date().toISOString().split('T')[0],
        type_checkers: ['pyright', 'pyrefly', 'ty', 'mypy', 'zuban'],
        type_checker_versions: { pyright: '1.1.408', pyrefly: '0.54.0', ty: '0.0.19', mypy: '1.19.1', zuban: '0.6.1' },
        package_count: 5,
        aggregate: {
            pyright:  { packages_tested: 5, packages_failed: 0, avg_execution_time_s: 12.5, p90_execution_time_s: 22.0, p95_execution_time_s: 25.0, max_execution_time_s: 30.0, total_execution_time_s: 62.5, avg_peak_memory_mb: 350, p90_peak_memory_mb: 480, p95_peak_memory_mb: 500, max_peak_memory_mb: 550 },
            pyrefly:  { packages_tested: 5, packages_failed: 0, avg_execution_time_s: 3.2, p90_execution_time_s: 5.5, p95_execution_time_s: 6.0, max_execution_time_s: 8.0, total_execution_time_s: 16.0, avg_peak_memory_mb: 280, p90_peak_memory_mb: 380, p95_peak_memory_mb: 400, max_peak_memory_mb: 420 },
            ty:       { packages_tested: 5, packages_failed: 0, avg_execution_time_s: 2.1, p90_execution_time_s: 3.5, p95_execution_time_s: 4.0, max_execution_time_s: 5.0, total_execution_time_s: 10.5, avg_peak_memory_mb: 200, p90_peak_memory_mb: 280, p95_peak_memory_mb: 300, max_peak_memory_mb: 320 },
            mypy:     { packages_tested: 5, packages_failed: 0, avg_execution_time_s: 15.0, p90_execution_time_s: 28.0, p95_execution_time_s: 30.0, max_execution_time_s: 35.0, total_execution_time_s: 75.0, avg_peak_memory_mb: 400, p90_peak_memory_mb: 560, p95_peak_memory_mb: 600, max_peak_memory_mb: 650 },
            zuban:    { packages_tested: 5, packages_failed: 0, avg_execution_time_s: 8.0, p90_execution_time_s: 14.0, p95_execution_time_s: 15.0, max_execution_time_s: 18.0, total_execution_time_s: 40.0, avg_peak_memory_mb: 320, p90_peak_memory_mb: 430, p95_peak_memory_mb: 450, max_peak_memory_mb: 480 }
        },
        results: [
            { package_name: 'requests', github_url: 'https://github.com/psf/requests', error: null, metrics: { pyright: { ok: true, execution_time_s: 8.5, peak_memory_mb: 280 }, pyrefly: { ok: true, execution_time_s: 2.1, peak_memory_mb: 200 }, ty: { ok: true, execution_time_s: 1.5, peak_memory_mb: 150 }, mypy: { ok: true, execution_time_s: 10.0, peak_memory_mb: 300 }, zuban: { ok: true, execution_time_s: 5.0, peak_memory_mb: 250 } } },
            { package_name: 'flask', github_url: 'https://github.com/pallets/flask', error: null, metrics: { pyright: { ok: true, execution_time_s: 10.2, peak_memory_mb: 320 }, pyrefly: { ok: true, execution_time_s: 2.8, peak_memory_mb: 240 }, ty: { ok: true, execution_time_s: 1.8, peak_memory_mb: 180 }, mypy: { ok: true, execution_time_s: 12.0, peak_memory_mb: 350 }, zuban: { ok: true, execution_time_s: 6.5, peak_memory_mb: 280 } } },
            { package_name: 'django', github_url: 'https://github.com/django/django', error: null, metrics: { pyright: { ok: true, execution_time_s: 30.0, peak_memory_mb: 550 }, pyrefly: { ok: true, execution_time_s: 8.0, peak_memory_mb: 420 }, ty: { ok: true, execution_time_s: 5.0, peak_memory_mb: 320 }, mypy: { ok: true, execution_time_s: 35.0, peak_memory_mb: 650 }, zuban: { ok: true, execution_time_s: 18.0, peak_memory_mb: 480 } } },
            { package_name: 'fastapi', github_url: 'https://github.com/fastapi/fastapi', error: null, metrics: { pyright: { ok: true, execution_time_s: 6.0, peak_memory_mb: 250 }, pyrefly: { ok: true, execution_time_s: 1.5, peak_memory_mb: 180 }, ty: { ok: true, execution_time_s: 1.2, peak_memory_mb: 140 }, mypy: { ok: true, execution_time_s: 8.0, peak_memory_mb: 280 }, zuban: { ok: true, execution_time_s: 4.0, peak_memory_mb: 220 } } },
            { package_name: 'pydantic', github_url: 'https://github.com/pydantic/pydantic', error: null, metrics: { pyright: { ok: true, execution_time_s: 7.8, peak_memory_mb: 300 }, pyrefly: { ok: true, execution_time_s: 1.6, peak_memory_mb: 190 }, ty: { ok: true, execution_time_s: 1.0, peak_memory_mb: 130 }, mypy: { ok: true, execution_time_s: 10.0, peak_memory_mb: 350 }, zuban: { ok: true, execution_time_s: 6.5, peak_memory_mb: 270 } } }
        ]
    };
}

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------

async function init() {
    try {
        currentOs = getOsFromUrl();
        const osSelect = document.getElementById('osSelect');
        if (osSelect) osSelect.value = currentOs;

        const urlDate = getDateFromUrl();
        await loadBenchmarkData(urlDate, currentOs);
        renderAll();
        setupFilters();
        setupDateSelector();
    } catch (error) {
        console.error('Failed to init:', error);
        showError('Failed to load benchmark data. Please try again later.');
    }
}

function renderAll() {
    updateTimestamp();
    populateSummary();
    populateFailureTable();
    createAvgTimeChart();
    createAvgMemoryChart();
    createP90TimeChart();
    createP95TimeChart();
    createSlowestPackagesChart();
    createHighestMemoryChart();
    populateResultsTable();
}

// ---------------------------------------------------------------------------
// Date/OS selector
// ---------------------------------------------------------------------------

function setupDateSelector() {
    const dateInput = document.getElementById('dateSelect');
    const loadBtn = document.getElementById('loadDateBtn');
    const latestBtn = document.getElementById('latestBtn');
    const osSelect = document.getElementById('osSelect');

    if (!dateInput || !loadBtn || !latestBtn) return;

    if (benchmarkData?.date) dateInput.value = benchmarkData.date;

    loadBtn.addEventListener('click', async () => {
        if (dateInput.value) await switchToDate(dateInput.value, currentOs);
    });
    latestBtn.addEventListener('click', async () => {
        await switchToDate(null, currentOs);
        if (benchmarkData?.date) dateInput.value = benchmarkData.date;
    });
    dateInput.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter' && dateInput.value) await switchToDate(dateInput.value, currentOs);
    });
    if (osSelect) {
        osSelect.addEventListener('change', async () => {
            currentOs = osSelect.value;
            await switchToDate(dateInput.value || null, currentOs);
        });
    }
}

async function switchToDate(date, os) {
    try {
        await loadBenchmarkData(date, os);
        clearError();
        updateUrlWithDate(benchmarkData?.date || date, os);

        const dateInput = document.getElementById('dateSelect');
        if (dateInput && benchmarkData?.date) dateInput.value = benchmarkData.date;

        Object.values(charts).forEach(c => c?.destroy());
        charts = {};

        renderAll();
    } catch (error) {
        console.error('Failed to load:', error);
        showError(`No data available for ${date || 'latest'} on ${os}.`, {
            text: 'Load latest Ubuntu results',
            onClick: () => switchToDate(null, 'ubuntu')
        });
    }
}

// ---------------------------------------------------------------------------
// Error / timestamp display
// ---------------------------------------------------------------------------

function clearError() {
    document.querySelectorAll('.error-message').forEach(el => el.remove());
}

function showError(message, action) {
    clearError();
    const main = document.querySelector('main');
    const div = document.createElement('div');
    div.className = 'error-message';
    div.style.cssText = 'background:rgba(248,81,73,0.1);border:1px solid #f85149;color:#f85149;padding:16px 24px;border-radius:8px;margin:24px 0;text-align:center;';
    const span = document.createElement('span');
    span.textContent = message;
    div.appendChild(span);
    if (action) {
        const link = document.createElement('a');
        link.textContent = action.text;
        link.href = '#';
        link.style.cssText = 'color:#58a6ff;margin-left:8px;text-decoration:underline;cursor:pointer;';
        link.addEventListener('click', (e) => { e.preventDefault(); action.onClick(); });
        div.appendChild(link);
    }
    main.insertBefore(div, main.firstChild);
}

function updateTimestamp() {
    const el = document.getElementById('lastUpdated');
    if (benchmarkData?.timestamp) {
        const d = new Date(benchmarkData.timestamp);
        el.textContent = `Last updated: ${d.toLocaleDateString()} at ${d.toLocaleTimeString()}`;
    } else {
        el.textContent = 'Demo data';
    }
    const versions = benchmarkData?.type_checker_versions || {};
    for (const [checker, version] of Object.entries(versions)) {
        const vEl = document.getElementById(`version-${checker}`);
        if (vEl && version && version !== 'unknown' && version !== 'not installed') {
            vEl.textContent = `v${version}`;
        }
    }
}

// ---------------------------------------------------------------------------
// Summary + failure table
// ---------------------------------------------------------------------------

function populateSummary() {
    const results = benchmarkData.results || [];
    const checkers = benchmarkData.type_checkers || [];

    const testedPackages = results.filter(r => !r.error).length;
    document.getElementById('summaryPackages').textContent = testedPackages;
    document.getElementById('summaryCheckers').textContent = checkers.length;
}

function populateFailureTable() {
    const results = benchmarkData.results || [];
    const checkers = benchmarkData.type_checkers || [];
    const failureDiv = document.getElementById('failureSummary');
    const tbody = document.getElementById('failureBody');
    if (!failureDiv || !tbody) return;

    const failures = [];

    // Package-level errors (e.g. clone failed)
    for (const result of results) {
        if (result.error) {
            failures.push({
                package: result.package_name,
                checker: 'All',
                reason: result.error
            });
            continue;
        }
        // Per-checker failures
        for (const checker of checkers) {
            const m = result.metrics?.[checker];
            if (m && !m.ok) {
                failures.push({
                    package: result.package_name,
                    checker: CHECKER_NAMES[checker] || checker,
                    reason: m.error_message || 'Failed'
                });
            }
        }
    }

    if (failures.length === 0) {
        failureDiv.style.display = 'none';
        return;
    }

    failureDiv.style.display = 'block';
    tbody.innerHTML = failures.map(f => `
        <tr>
            <td class="package-name">${f.package}</td>
            <td>${f.checker === 'All' ? '<span class="status-badge error">All</span>' : `<span class="checker-badge ${f.checker.toLowerCase()}">${f.checker}</span>`}</td>
            <td><span class="status-badge error">${f.reason}</span></td>
        </tr>
    `).join('');
}

// ---------------------------------------------------------------------------
// Chart helpers
// ---------------------------------------------------------------------------

function barChart(canvasId, labels, data, colors, unit, chartKey) {
    const ctx = document.getElementById(canvasId)?.getContext('2d');
    if (!ctx) return;
    charts[chartKey] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{ data, backgroundColor: colors, borderRadius: 6, borderWidth: 0 }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: (ctx) => `${ctx.raw.toFixed(1)} ${unit}` } }
            },
            scales: {
                y: { beginAtZero: true, grid: { color: '#30363d' }, ticks: { color: '#8b949e', callback: (v) => `${v} ${unit}` } },
                x: { grid: { display: false }, ticks: { color: '#c9d1d9' } }
            }
        }
    });
}

function groupedBarChart(canvasId, packageNames, checkers, getValueFn, unit, chartKey) {
    const ctx = document.getElementById(canvasId)?.getContext('2d');
    if (!ctx) return;
    const datasets = checkers.map(checker => ({
        label: CHECKER_NAMES[checker] || checker,
        data: packageNames.map((_, i) => getValueFn(i, checker)),
        backgroundColor: CHECKER_COLORS[checker] || '#888',
        borderRadius: 4,
        borderWidth: 0
    }));
    charts[chartKey] = new Chart(ctx, {
        type: 'bar',
        data: { labels: packageNames, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            indexAxis: 'y',
            plugins: {
                legend: { position: 'top', labels: { color: '#c9d1d9', usePointStyle: true, padding: 20 } },
                tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.raw.toFixed(1)} ${unit}` } }
            },
            scales: {
                x: { beginAtZero: true, grid: { color: '#30363d' }, ticks: { color: '#8b949e', callback: (v) => `${v} ${unit}` }, title: { display: true, text: unit, color: '#8b949e' } },
                y: { grid: { display: false }, ticks: { color: '#c9d1d9' } }
            }
        }
    });
}

// ---------------------------------------------------------------------------
// Chart creators
// ---------------------------------------------------------------------------

function createAvgTimeChart() {
    const agg = benchmarkData.aggregate || {};
    const checkers = benchmarkData.type_checkers || [];
    barChart('avgTimeChart',
        checkers.map(c => CHECKER_NAMES[c] || c),
        checkers.map(c => agg[c]?.avg_execution_time_s || 0),
        checkers.map(c => CHECKER_COLORS[c] || '#888'),
        's', 'avgTime');
}

function createAvgMemoryChart() {
    const agg = benchmarkData.aggregate || {};
    const checkers = benchmarkData.type_checkers || [];
    barChart('avgMemoryChart',
        checkers.map(c => CHECKER_NAMES[c] || c),
        checkers.map(c => agg[c]?.avg_peak_memory_mb || 0),
        checkers.map(c => CHECKER_COLORS[c] || '#888'),
        'MB', 'avgMemory');
}

function createP90TimeChart() {
    const agg = benchmarkData.aggregate || {};
    const checkers = benchmarkData.type_checkers || [];
    barChart('p90TimeChart',
        checkers.map(c => CHECKER_NAMES[c] || c),
        checkers.map(c => agg[c]?.p90_execution_time_s || 0),
        checkers.map(c => CHECKER_COLORS[c] || '#888'),
        's', 'p90Time');
}

function createP95TimeChart() {
    const agg = benchmarkData.aggregate || {};
    const checkers = benchmarkData.type_checkers || [];
    barChart('p95TimeChart',
        checkers.map(c => CHECKER_NAMES[c] || c),
        checkers.map(c => agg[c]?.p95_execution_time_s || 0),
        checkers.map(c => CHECKER_COLORS[c] || '#888'),
        's', 'p95Time');
}

function createSlowestPackagesChart() {
    const results = (benchmarkData.results || []).filter(r => !r.error);
    const checkers = benchmarkData.type_checkers || [];

    // Compute average time per package across all checkers, sort descending, take top 10
    const withAvg = results.map(r => {
        let sum = 0, count = 0;
        for (const c of checkers) {
            const t = r.metrics?.[c]?.execution_time_s;
            if (t != null && r.metrics?.[c]?.ok) { sum += t; count++; }
        }
        return { result: r, avg: count > 0 ? sum / count : 0 };
    });
    withAvg.sort((a, b) => b.avg - a.avg);
    const top10 = withAvg.slice(0, 10);

    const names = top10.map(x => x.result.package_name);
    groupedBarChart('slowestPackagesChart', names, checkers,
        (i, checker) => {
            const m = top10[i].result.metrics?.[checker];
            return (m?.ok ? m.execution_time_s : 0) || 0;
        },
        's', 'slowestPackages');
}

function createHighestMemoryChart() {
    const results = (benchmarkData.results || []).filter(r => !r.error);
    const checkers = benchmarkData.type_checkers || [];

    const withAvg = results.map(r => {
        let sum = 0, count = 0;
        for (const c of checkers) {
            const m = r.metrics?.[c]?.peak_memory_mb;
            if (m != null && m > 0 && r.metrics?.[c]?.ok) { sum += m; count++; }
        }
        return { result: r, avg: count > 0 ? sum / count : 0 };
    });
    withAvg.sort((a, b) => b.avg - a.avg);
    const top10 = withAvg.slice(0, 10);

    const names = top10.map(x => x.result.package_name);
    groupedBarChart('highestMemoryChart', names, checkers,
        (i, checker) => {
            const m = top10[i].result.metrics?.[checker];
            return (m?.ok ? m.peak_memory_mb : 0) || 0;
        },
        'MB', 'highestMemory');
}

// ---------------------------------------------------------------------------
// Results table
// ---------------------------------------------------------------------------

function populateResultsTable(filterText, sortBy) {
    filterText = filterText || '';
    sortBy = sortBy || 'name';

    const tbody = document.getElementById('resultsBody');
    if (!tbody) return;

    let results = benchmarkData.results || [];
    const checkers = benchmarkData.type_checkers || [];

    if (filterText) {
        const f = filterText.toLowerCase();
        results = results.filter(r => r.package_name.toLowerCase().includes(f));
    }

    results = [...results].sort((a, b) => {
        switch (sortBy) {
            case 'time': return getMinTime(a, checkers) - getMinTime(b, checkers);
            case 'memory': return getMinMemory(a, checkers) - getMinMemory(b, checkers);
            default: return a.package_name.localeCompare(b.package_name);
        }
    });

    const rows = [];
    for (const result of results) {
        for (const checker of checkers) {
            const m = result.metrics?.[checker];
            rows.push({
                package: result.package_name,
                github_url: result.github_url,
                checker,
                time: m?.execution_time_s,
                memory: m?.peak_memory_mb,
                ok: m?.ok,
                error: result.error || m?.error_message
            });
        }
    }

    if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="loading-row">No results found</td></tr>';
        return;
    }

    tbody.innerHTML = rows.map((row, idx) => {
        const isFirst = idx === 0 || rows[idx - 1].package !== row.package;
        const pkgCell = isFirst
            ? `<td class="package-name" rowspan="${checkers.length}"><a href="${row.github_url}" target="_blank">${row.package}</a></td>`
            : '';
        const statusBadge = row.ok
            ? '<span class="status-badge success">OK</span>'
            : `<span class="status-badge error">${row.error || 'Failed'}</span>`;
        return `<tr>
            ${pkgCell}
            <td><span class="checker-badge ${row.checker}">${CHECKER_NAMES[row.checker] || row.checker}</span></td>
            <td class="mono">${row.time != null ? row.time.toFixed(1) + ' s' : '-'}</td>
            <td class="mono">${row.memory != null && row.memory > 0 ? row.memory.toFixed(0) + ' MB' : '-'}</td>
            <td>${statusBadge}</td>
        </tr>`;
    }).join('');
}

function getMinTime(result, checkers) {
    let min = Infinity;
    for (const c of checkers) {
        const t = result.metrics?.[c]?.execution_time_s;
        if (t != null && t < min) min = t;
    }
    return min === Infinity ? 9999 : min;
}

function getMinMemory(result, checkers) {
    let min = Infinity;
    for (const c of checkers) {
        const m = result.metrics?.[c]?.peak_memory_mb;
        if (m != null && m > 0 && m < min) min = m;
    }
    return min === Infinity ? 9999 : min;
}

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------

function setupFilters() {
    const searchInput = document.getElementById('packageSearch');
    const sortSelect = document.getElementById('sortBy');
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            populateResultsTable(searchInput.value, sortSelect?.value);
        });
    }
    if (sortSelect) {
        sortSelect.addEventListener('change', () => {
            populateResultsTable(searchInput?.value, sortSelect.value);
        });
    }
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', init);
