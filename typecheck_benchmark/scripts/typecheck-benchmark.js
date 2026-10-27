/**
 * Type Checker Timing Benchmark Dashboard
 * Loads and displays timing/memory benchmark data from JSON files.
 */
// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
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
    const url = new URL(window.location.href);
    if (date)
        url.searchParams.set('date', date);
    else
        url.searchParams.delete('date');
    if (os)
        url.searchParams.set('os', os);
    window.history.replaceState({}, '', url.toString());
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
    }
    else {
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
        }
        catch (e) {
            console.warn(`Failed to load ${path}:`, e);
        }
    }
    if (date)
        throw new Error(`No data for ${date} on ${os}`);
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
        runs_per_package: 5,
        warmup_runs: 1,
        aggregate: {
            pyright: { packages_tested: 5, packages_failed: 0, avg_execution_time_s: 12.5, p90_execution_time_s: 22.0, p95_execution_time_s: 25.0, max_execution_time_s: 30.0, total_execution_time_s: 62.5, avg_peak_memory_mb: 350, p90_peak_memory_mb: 480, p95_peak_memory_mb: 500, max_peak_memory_mb: 550 },
            pyrefly: { packages_tested: 5, packages_failed: 0, avg_execution_time_s: 3.2, p90_execution_time_s: 5.5, p95_execution_time_s: 6.0, max_execution_time_s: 8.0, total_execution_time_s: 16.0, avg_peak_memory_mb: 280, p90_peak_memory_mb: 380, p95_peak_memory_mb: 400, max_peak_memory_mb: 420 },
            ty: { packages_tested: 5, packages_failed: 0, avg_execution_time_s: 2.1, p90_execution_time_s: 3.5, p95_execution_time_s: 4.0, max_execution_time_s: 5.0, total_execution_time_s: 10.5, avg_peak_memory_mb: 200, p90_peak_memory_mb: 280, p95_peak_memory_mb: 300, max_peak_memory_mb: 320 },
            mypy: { packages_tested: 5, packages_failed: 0, avg_execution_time_s: 15.0, p90_execution_time_s: 28.0, p95_execution_time_s: 30.0, max_execution_time_s: 35.0, total_execution_time_s: 75.0, avg_peak_memory_mb: 400, p90_peak_memory_mb: 560, p95_peak_memory_mb: 600, max_peak_memory_mb: 650 },
            zuban: { packages_tested: 5, packages_failed: 0, avg_execution_time_s: 8.0, p90_execution_time_s: 14.0, p95_execution_time_s: 15.0, max_execution_time_s: 18.0, total_execution_time_s: 40.0, avg_peak_memory_mb: 320, p90_peak_memory_mb: 430, p95_peak_memory_mb: 450, max_peak_memory_mb: 480 }
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
        if (osSelect)
            osSelect.value = currentOs;
        const urlDate = getDateFromUrl();
        await loadBenchmarkData(urlDate, currentOs);
        renderAll();
        setupFilters();
        setupDateSelector();
    }
    catch (error) {
        console.error('Failed to init:', error);
        showError('Failed to load benchmark data. Please try again later.');
    }
}
function renderAll() {
    updateTimestamp();
    renderStats();
    renderSpeed();
    renderMemory();
    renderFailures();
    const search = document.getElementById('packageSearch');
    const sort = document.getElementById('sortBy');
    populateResultsTable(search?.value || '', sort?.value || 'name');
}
// ---------------------------------------------------------------------------
// Date/OS selector
// ---------------------------------------------------------------------------
function updateDiscontinuedBanner(os) {
    const banner = document.getElementById('discontinuedBanner');
    if (banner)
        banner.style.display = (os === 'macos' || os === 'windows') ? 'block' : 'none';
}
function setupDateSelector() {
    const dateInput = document.getElementById('dateSelect');
    const loadBtn = document.getElementById('loadDateBtn');
    const latestBtn = document.getElementById('latestBtn');
    const osSelect = document.getElementById('osSelect');
    if (!dateInput || !loadBtn || !latestBtn)
        return;
    if (benchmarkData?.date)
        dateInput.value = benchmarkData.date;
    loadBtn.addEventListener('click', async () => {
        if (dateInput.value)
            await switchToDate(dateInput.value, currentOs);
    });
    latestBtn.addEventListener('click', async () => {
        await switchToDate(null, currentOs);
        if (benchmarkData?.date)
            dateInput.value = benchmarkData.date;
    });
    dateInput.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter' && dateInput.value)
            await switchToDate(dateInput.value, currentOs);
    });
    if (osSelect) {
        osSelect.addEventListener('change', async () => {
            currentOs = osSelect.value;
            updateDiscontinuedBanner(currentOs);
            await switchToDate(dateInput.value || null, currentOs);
        });
    }
    updateDiscontinuedBanner(currentOs);
}
async function switchToDate(date, os) {
    try {
        await loadBenchmarkData(date, os);
        clearError();
        updateUrlWithDate(benchmarkData?.date || date || null, os);
        const dateInput = document.getElementById('dateSelect');
        if (dateInput && benchmarkData?.date)
            dateInput.value = benchmarkData.date;
        renderAll();
    }
    catch (error) {
        console.error('Failed to load:', error);
        showError(`No data available for ${date || 'latest'} on ${os}.`, {
            text: 'Load latest Ubuntu results',
            onClick: () => { switchToDate(null, 'ubuntu'); }
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
    if (!main)
        return;
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
    if (!el)
        return;
    if (benchmarkData?.timestamp) {
        const d = new Date(benchmarkData.timestamp);
        const runs = benchmarkData.runs_per_package;
        const warmup = benchmarkData.warmup_runs;
        const runsStr = runs && runs > 1 ? ` | ${runs} runs per package` : '';
        const warmupStr = warmup && warmup > 0 ? ` (${warmup} warmup)` : '';
        el.textContent = `Last updated: ${d.toLocaleDateString()} at ${d.toLocaleTimeString()}${runsStr}${warmupStr}`;
    }
    else {
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
let currentMetric = 'geomean';
function geometricMean(values) {
    if (values.length === 0)
        return 0;
    // Guard against zero times from very fast runs before taking logs
    return Math.exp(values.reduce((s, v) => s + Math.log(Math.max(v, 0.001)), 0) / values.length);
}
function median(values) {
    if (values.length === 0)
        return 0;
    const v = [...values].sort((a, b) => a - b);
    const mid = Math.floor(v.length / 2);
    return v.length % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2;
}
function finishedByAll() {
    if (!benchmarkData)
        return [];
    const checkers = benchmarkData.type_checkers || [];
    return (benchmarkData.results || []).filter(r => checkers.every(c => r.metrics?.[c]?.ok && r.metrics[c].execution_time_s != null));
}
function summarize() {
    if (!benchmarkData)
        return [];
    const checkers = benchmarkData.type_checkers || [];
    const common = finishedByAll();
    return checkers.map(checker => {
        const times = common.map(r => r.metrics[checker].execution_time_s);
        const mems = common.map(r => r.metrics[checker].peak_memory_mb || 0);
        const failures = (benchmarkData.results || [])
            .filter(r => !r.metrics?.[checker]?.ok)
            .map(r => ({ pkg: r.package_name, reason: r.metrics?.[checker]?.error_message || r.error || 'Failed' }));
        return {
            checker,
            geomean: geometricMean(times),
            median: median(times),
            mean: times.length ? times.reduce((s, v) => s + v, 0) / times.length : 0,
            total: times.reduce((s, v) => s + v, 0),
            memGeomean: mems.length && mems.every(m => m > 0) ? geometricMean(mems) : null,
            failures,
        };
    });
}
function formatTime(t) {
    if (t < 10)
        return `${t.toFixed(3)} s`;
    if (t < 100)
        return `${t.toFixed(2)} s`;
    return `${t.toFixed(1)} s`;
}
function withinNoise(a, b) {
    return Math.abs(a - b) <= Math.max(0.010, 0.05 * Math.min(a, b));
}
function shortReason(reason) {
    if (/OOM/i.test(reason))
        return 'Out of memory';
    if (/Timeout/i.test(reason))
        return 'Timeout (>5 min)';
    if (/Not installed/i.test(reason))
        return 'Not installed';
    return 'Crashed';
}
function escapeHtml(s) {
    return s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}
function checkerLabel(checker) {
    return `<span class="checker-swatch" style="background:${CHECKER_COLORS[checker] || '#888'}"></span>${CHECKER_NAMES[checker] || checker}`;
}
function renderStats() {
    const grid = document.getElementById('statGrid');
    if (!grid || !benchmarkData)
        return;
    const summaries = summarize();
    const failed = summaries.reduce((n, s) => n + s.failures.length, 0);
    const stats = [
        [benchmarkData.results?.length || 0, 'Packages tested'],
        [finishedByAll().length, 'Finished by every checker (summarized below)'],
        [(benchmarkData.type_checkers || []).length, 'Type checkers'],
        [failed, "Runs that didn't finish"],
    ];
    grid.innerHTML = stats.map(([v, l]) => `<div class="stat-card"><div class="stat-value">${v}</div><div class="stat-label">${l}</div></div>`).join('');
}
function renderBars(containerId, rows, trailing) {
    const el = document.getElementById(containerId);
    if (!el)
        return;
    const sorted = [...rows].sort((a, b) => a.value - b.value);
    const max = Math.max(...sorted.map(r => r.value), 0) || 1;
    const best = sorted[0]?.value || 0;
    el.innerHTML = sorted.map(r => {
        const pct = (r.value / max) * 78;
        const rel = r.value === best ? 'lowest' : `${(r.value / best).toFixed(1)}&times; the lowest`;
        return `<div class="bar-name">${checkerLabel(r.checker)}</div>
            <div class="bar-track" title="${escapeHtml(CHECKER_NAMES[r.checker] || r.checker)}: ${r.label} (${rel.replace('&times;', 'x')})">
                <div class="bar-fill" style="width:${pct}%;background:${CHECKER_COLORS[r.checker] || '#888'}"></div>
                <span class="bar-value" style="left:calc(${pct}% + 8px)">${r.label}</span>
            </div>
            ${trailing(r.checker)}`;
    }).join('');
}
const METRIC_DESCRIPTIONS = {
    geomean: 'Geometric mean of the time per package. Every package counts equally whether it takes 0.1 s or 100 s, so one huge package can\'t dominate.',
    median: 'Median time per package: half the packages are faster than this.',
    mean: 'Ordinary average time per package.',
    total: 'Total time to check all of these packages back to back.',
};
function renderSpeed() {
    if (!benchmarkData)
        return;
    const summaries = summarize();
    const byChecker = new Map(summaries.map(s => [s.checker, s]));
    document.querySelectorAll('.metric-tabs button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.metric === currentMetric)));
    const desc = document.getElementById('speedDescription');
    if (desc)
        desc.textContent = `${METRIC_DESCRIPTIONS[currentMetric]} Lower is better. Computed over the ${finishedByAll().length} packages every checker finished.`;
    renderBars('speedBars', summaries.map(s => ({ checker: s.checker, value: s[currentMetric], label: formatTime(s[currentMetric]) })), checker => {
        const f = byChecker.get(checker)?.failures || [];
        if (!f.length)
            return `<span class="bar-trailing">Finished all ${benchmarkData.results.length}</span>`;
        const list = f.map(x => `${x.pkg}: ${shortReason(x.reason)}`).join('\n');
        return `<span class="bar-trailing"><span class="fail-chip" tabindex="0" title="${escapeHtml(list)}"><span class="fail-icon" aria-hidden="true">&#9888;</span>${f.length} didn't finish</span></span>`;
    });
    const note = document.getElementById('speedNote');
    if (!note)
        return;
    if (currentMetric === 'mean' || currentMetric === 'total') {
        note.classList.add('warn');
        note.textContent = `The ${currentMetric === 'mean' ? 'average' : 'total'} is dominated by the largest packages. Use it if you mostly care about very large codebases.`;
    }
    else {
        note.classList.remove('warn');
        note.textContent = 'Packages a checker didn\'t finish are listed beside it and left out for every checker, so all are compared on the same packages.';
    }
}
function renderMemory() {
    const summaries = summarize();
    const el = document.getElementById('memoryBars');
    if (!el)
        return;
    if (summaries.some(s => s.memGeomean == null)) {
        el.innerHTML = '<p class="summary-note">Peak memory wasn\'t recorded for this run.</p>';
        return;
    }
    renderBars('memoryBars', summaries.map(s => ({ checker: s.checker, value: s.memGeomean, label: `${Math.round(s.memGeomean)} MB` })), () => '<span></span>');
}
function renderFailures() {
    const tbody = document.getElementById('failureBody');
    if (!tbody)
        return;
    const rows = summarize().flatMap(s => s.failures.map(f => `<tr><td>${checkerLabel(s.checker)}</td><td>${escapeHtml(f.pkg)}</td><td class="fail-text" title="${escapeHtml(f.reason)}">&#9888; ${shortReason(f.reason)}</td></tr>`));
    tbody.innerHTML = rows.join('') || '<tr><td colspan="3">Every checker finished every package.</td></tr>';
}
// ---------------------------------------------------------------------------
// Per-package table
// ---------------------------------------------------------------------------
function okTimes(r, checkers) {
    return checkers.map(c => r.metrics?.[c]).filter(m => m?.ok && m.execution_time_s != null)
        .map(m => m.execution_time_s);
}
function populateResultsTable(filterText, sortBy) {
    if (!benchmarkData)
        return;
    const head = document.getElementById('resultsHead');
    const tbody = document.getElementById('resultsBody');
    if (!head || !tbody)
        return;
    const checkers = benchmarkData.type_checkers || [];
    const f = (filterText || '').toLowerCase();
    let results = (benchmarkData.results || []).filter(r => r.package_name.toLowerCase().includes(f));
    const slowest = (r) => Math.max(0, ...okTimes(r, checkers));
    const spread = (r) => {
        const t = okTimes(r, checkers);
        return t.length ? Math.max(...t) / Math.max(Math.min(...t), 0.001) : 0;
    };
    results = [...results].sort((a, b) => {
        if (sortBy === 'slowest')
            return slowest(b) - slowest(a);
        if (sortBy === 'spread')
            return spread(b) - spread(a);
        return a.package_name.toLowerCase().localeCompare(b.package_name.toLowerCase());
    });
    head.innerHTML = `<tr><th>Package</th>${checkers.map(c => `<th>${checkerLabel(c)}</th>`).join('')}</tr>`;
    tbody.innerHTML = results.map(r => {
        const times = okTimes(r, checkers);
        const best = times.length ? Math.min(...times) : 0;
        const cells = checkers.map(c => {
            const m = r.metrics?.[c];
            if (!m?.ok || m.execution_time_s == null) {
                const reason = m?.error_message || r.error || 'Failed';
                return `<td class="fail-text" title="${escapeHtml(reason)}">&#9888; ${shortReason(reason)}</td>`;
            }
            const t = m.execution_time_s;
            const mem = m.peak_memory_mb ? `, ${Math.round(m.peak_memory_mb)} MB` : '';
            if (withinNoise(t, best))
                return `<td class="best" title="${formatTime(t)}${mem}">${formatTime(t)}</td>`;
            return `<td title="${formatTime(t)}${mem}">${formatTime(t)}<span class="times-slower">${(t / best).toFixed(1)}&times;</span></td>`;
        }).join('');
        return `<tr><td>${escapeHtml(r.package_name)}</td>${cells}</tr>`;
    }).join('') || `<tr><td colspan="${checkers.length + 1}" class="loading-row">No packages match.</td></tr>`;
}
function setupFilters() {
    const searchInput = document.getElementById('packageSearch');
    const sortSelect = document.getElementById('sortBy');
    const refresh = () => populateResultsTable(searchInput?.value || '', sortSelect?.value || 'name');
    searchInput?.addEventListener('input', refresh);
    sortSelect?.addEventListener('change', refresh);
    document.querySelectorAll('.metric-tabs button').forEach(b => b.addEventListener('click', () => {
        currentMetric = b.dataset.metric || 'geomean';
        renderSpeed();
    }));
}
document.addEventListener('DOMContentLoaded', init);
export {};
