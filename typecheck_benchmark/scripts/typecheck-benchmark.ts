/**
 * Type Checker Timing Benchmark Dashboard
 * Loads and displays timing/memory benchmark data from JSON files.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CheckerTimingMetrics {
    ok?: boolean;
    execution_time_s?: number;
    peak_memory_mb?: number;
    error_message?: string;
}

interface TimingAggregateEntry {
    packages_tested: number;
    packages_failed?: number;
    avg_execution_time_s: number;
    p90_execution_time_s: number;
    p95_execution_time_s: number;
    max_execution_time_s: number;
    total_execution_time_s: number;
    avg_peak_memory_mb: number;
    p90_peak_memory_mb: number;
    p95_peak_memory_mb: number;
    max_peak_memory_mb: number;
}

interface TimingBenchmarkResult {
    package_name: string;
    github_url: string;
    error: string | null;
    /** Each checker in its default configuration. */
    metrics: Record<string, CheckerTimingMetrics>;
    /** Checkers run with the opposite of their default return type inference setting. */
    alternate_metrics?: Record<string, CheckerTimingMetrics>;
}

interface TimingBenchmarkData {
    timestamp: string;
    date: string;
    type_checkers: string[];
    type_checker_versions?: Record<string, string>;
    package_count: number;
    runs_per_package?: number;
    warmup_runs?: number;
    /** Whether each checker's default configuration infers return types. */
    return_type_inference_default?: Record<string, boolean>;
    aggregate: Record<string, TimingAggregateEntry>;
    results: TimingBenchmarkResult[];
}

/** Hand-written explanation of how checkers differ on one package. */
interface PackageNote {
    checkers: string[];
    text: string;
    link?: string;
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

let benchmarkData: TimingBenchmarkData | null = null;
let currentOs = 'ubuntu';
let packageNotes: Record<string, PackageNote[]> = {};

// ---------------------------------------------------------------------------
// URL helpers
// ---------------------------------------------------------------------------

function getOsFromUrl(): string {
    const params = new URLSearchParams(window.location.search);
    const os = params.get('os');
    return (os && ['ubuntu', 'macos', 'windows'].includes(os)) ? os : 'ubuntu';
}

function getInferenceViewFromUrl(): InferenceView {
    const view = new URLSearchParams(window.location.search).get('inference');
    return view === 'off' || view === 'on' ? view : 'both';
}

function getCellLayoutFromUrl(): CellLayout {
    return new URLSearchParams(window.location.search).get('cells') === 'columns' ? 'columns' : 'stacked';
}

function updateUrlParam(name: string, value: string | null): void {
    const url = new URL(window.location.href);
    if (value) url.searchParams.set(name, value);
    else url.searchParams.delete(name);
    window.history.replaceState({}, '', url.toString());
}

function getDateFromUrl(): string | null {
    const params = new URLSearchParams(window.location.search);
    const date = params.get('date');
    return (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) ? date : null;
}

function updateUrlWithDate(date: string | null, os: string | null): void {
    const url = new URL(window.location.href);
    if (date) url.searchParams.set('date', date);
    else url.searchParams.delete('date');
    if (os) url.searchParams.set('os', os);
    window.history.replaceState({}, '', url.toString());
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function loadBenchmarkData(date: string | null, os: string): Promise<TimingBenchmarkData> {
    let paths: string[];
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
                return benchmarkData!;
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

// Notes are optional: if the file is missing or malformed the table renders without them.
async function loadPackageNotes(): Promise<void> {
    try {
        const response = await fetch('./package_notes.json');
        if (!response.ok) return;
        const raw: unknown = await response.json();
        if (!raw || typeof raw !== 'object') return;
        const notes: Record<string, PackageNote[]> = {};
        for (const [pkg, list] of Object.entries(raw as Record<string, unknown>)) {
            if (!Array.isArray(list)) continue;
            const valid = list.filter((n): n is PackageNote =>
                typeof n?.text === 'string' && Array.isArray(n.checkers)
                && (n.link === undefined || (typeof n.link === 'string' && n.link.startsWith('https://'))));
            if (valid.length) notes[pkg] = valid;
        }
        packageNotes = notes;
    } catch (e) {
        console.warn('Failed to load package notes:', e);
    }
}

function getDemoData(): TimingBenchmarkData {
    return {
        timestamp: new Date().toISOString(),
        date: new Date().toISOString().split('T')[0],
        type_checkers: ['pyright', 'pyrefly', 'ty', 'mypy', 'zuban'],
        type_checker_versions: { pyright: '1.1.408', pyrefly: '0.54.0', ty: '0.0.19', mypy: '1.19.1', zuban: '0.6.1' },
        package_count: 5,
        runs_per_package: 5,
        warmup_runs: 1,
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

async function init(): Promise<void> {
    try {
        currentOs = getOsFromUrl();
        inferenceView = getInferenceViewFromUrl();
        cellLayout = getCellLayoutFromUrl();
        const osSelect = document.getElementById('osSelect') as HTMLSelectElement | null;
        if (osSelect) osSelect.value = currentOs;

        const urlDate = getDateFromUrl();
        await Promise.all([loadBenchmarkData(urlDate, currentOs), loadPackageNotes()]);
        renderAll();
        setupFilters();
        setupNotes();
        setupDateSelector();
    } catch (error) {
        console.error('Failed to init:', error);
        showError('Failed to load benchmark data. Please try again later.');
    }
}

function renderAll(): void {
    updateTimestamp();
    renderInferenceControls();
    renderStats();
    renderSpeed();
    renderMemory();
    renderFailures();
    const search = document.getElementById('packageSearch') as HTMLInputElement | null;
    const sort = document.getElementById('sortBy') as HTMLSelectElement | null;
    populateResultsTable(search?.value || '', sort?.value || 'name');
}

// ---------------------------------------------------------------------------
// Date/OS selector
// ---------------------------------------------------------------------------

function updateDiscontinuedBanner(os: string): void {
    const banner = document.getElementById('discontinuedBanner');
    if (banner) banner.style.display = (os === 'macos' || os === 'windows') ? 'block' : 'none';
}

function setupDateSelector(): void {
    const dateInput = document.getElementById('dateSelect') as HTMLInputElement | null;
    const loadBtn = document.getElementById('loadDateBtn');
    const latestBtn = document.getElementById('latestBtn');
    const osSelect = document.getElementById('osSelect') as HTMLSelectElement | null;

    if (!dateInput || !loadBtn || !latestBtn) return;

    if (benchmarkData?.date) dateInput.value = benchmarkData.date;

    loadBtn.addEventListener('click', async () => {
        if (dateInput.value) await switchToDate(dateInput.value, currentOs);
    });
    latestBtn.addEventListener('click', async () => {
        await switchToDate(null, currentOs);
        if (benchmarkData?.date) dateInput.value = benchmarkData.date;
    });
    dateInput.addEventListener('keypress', async (e: KeyboardEvent) => {
        if (e.key === 'Enter' && dateInput.value) await switchToDate(dateInput.value, currentOs);
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

async function switchToDate(date: string | null, os: string): Promise<void> {
    try {
        await loadBenchmarkData(date, os);
        clearError();
        updateUrlWithDate(benchmarkData?.date || date || null, os);

        const dateInput = document.getElementById('dateSelect') as HTMLInputElement | null;
        if (dateInput && benchmarkData?.date) dateInput.value = benchmarkData.date;

        renderAll();
    } catch (error) {
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

function clearError(): void {
    document.querySelectorAll('.error-message').forEach(el => el.remove());
}

function showError(message: string, action?: ErrorAction): void {
    clearError();
    const main = document.querySelector('main');
    if (!main) return;
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
        link.addEventListener('click', (e: Event) => { e.preventDefault(); action.onClick(); });
        div.appendChild(link);
    }
    main.insertBefore(div, main.firstChild);
}

function updateTimestamp(): void {
    const el = document.getElementById('lastUpdated');
    if (!el) return;
    if (benchmarkData?.timestamp) {
        const d = new Date(benchmarkData.timestamp);
        const runs = benchmarkData.runs_per_package;
        const warmup = benchmarkData.warmup_runs;
        const runsStr = runs && runs > 1 ? ` | ${runs} runs per package` : '';
        const warmupStr = warmup && warmup > 0 ? ` (${warmup} warmup)` : '';
        el.textContent = `Last updated: ${d.toLocaleDateString()} at ${d.toLocaleTimeString()}${runsStr}${warmupStr}`;
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
// Return type inference configurations
// ---------------------------------------------------------------------------

/** Which return type inference setting the page shows: both side by side, or one. */
type InferenceView = 'both' | 'off' | 'on';

/** How the per-package table shows both settings: two lines per cell, or two columns per checker. */
type CellLayout = 'stacked' | 'columns';

/**
 * One measured configuration of a checker. `on` is whether it infers return
 * types, or null for results recorded before the benchmark varied the setting.
 */
interface CheckerConfig {
    checker: string;
    on: boolean | null;
}

let inferenceView: InferenceView = 'both';
let cellLayout: CellLayout = 'stacked';

/** True when these results time some checkers both with and without return type inference. */
function hasInferenceVariants(): boolean {
    return !!benchmarkData?.return_type_inference_default
        && (benchmarkData.results || []).some(r => Object.keys(r.alternate_metrics || {}).length > 0);
}

function inferenceDefault(checker: string): boolean | undefined {
    return benchmarkData?.return_type_inference_default?.[checker];
}

function hasAlternate(checker: string): boolean {
    return (benchmarkData?.results || []).some(r => r.alternate_metrics?.[checker]);
}

/** Why a checker has no measurement with return type inference set to `on`, or null if it has one. */
function unsupportedReason(checker: string, on: boolean): string | null {
    const def = inferenceDefault(checker);
    if (def === on || hasAlternate(checker)) return null;
    return on ? "Doesn't infer return types" : 'No setting to turn it off';
}

/** Every configuration with measurements, in table order: per checker, off before on. */
function allConfigs(): CheckerConfig[] {
    const checkers = benchmarkData?.type_checkers || [];
    if (!hasInferenceVariants()) return checkers.map(checker => ({ checker, on: null }));
    return checkers.flatMap(checker => [false, true]
        .filter(on => unsupportedReason(checker, on) === null)
        .map(on => ({ checker, on })));
}

/** The configurations the current view shows. */
function visibleConfigs(): CheckerConfig[] {
    return allConfigs().filter(c => c.on === null || inferenceView === 'both' || c.on === (inferenceView === 'on'));
}

function configMetrics(r: TimingBenchmarkResult, c: CheckerConfig): CheckerTimingMetrics | undefined {
    if (c.on === null || c.on === inferenceDefault(c.checker)) return r.metrics?.[c.checker];
    return r.alternate_metrics?.[c.checker];
}

function configTime(r: TimingBenchmarkResult, c: CheckerConfig): number | null {
    const m = configMetrics(r, c);
    return m?.ok && m.execution_time_s != null ? m.execution_time_s : null;
}

function modeName(on: boolean): string {
    return on ? 'on' : 'off';
}

/** A small marker for the setting: hollow for off, filled for on. */
function modeGlyph(on: boolean): string {
    return `<span class="rti-glyph rti-${modeName(on)}" aria-hidden="true">${on ? '&#9679;' : '&#9675;'}</span>`;
}

function configTitle(c: CheckerConfig): string {
    const name = CHECKER_NAMES[c.checker] || c.checker;
    if (c.on === null) return name;
    const isDefault = c.on === inferenceDefault(c.checker) ? ', default' : '';
    return `${name} (return type inference ${modeName(c.on)}${isDefault})`;
}

function configLabel(c: CheckerConfig): string {
    if (c.on === null) return checkerLabel(c.checker);
    return `${checkerLabel(c.checker)}<span class="rti-tag">${modeGlyph(c.on)}${modeName(c.on)}</span>`;
}

// ---------------------------------------------------------------------------
// Summaries over the packages every configuration finished
// ---------------------------------------------------------------------------

type SpeedMetric = 'geomean' | 'median' | 'mean' | 'total';

interface ConfigSummary {
    config: CheckerConfig;
    geomean: number;
    median: number;
    mean: number;
    total: number;
    memGeomean: number | null;
    failures: { pkg: string; reason: string }[];
}

let currentMetric: SpeedMetric = 'geomean';

function geometricMean(values: number[]): number {
    if (values.length === 0) return 0;
    // Guard against zero times from very fast runs before taking logs
    return Math.exp(values.reduce((s, v) => s + Math.log(Math.max(v, 0.001)), 0) / values.length);
}

function median(values: number[]): number {
    if (values.length === 0) return 0;
    const v = [...values].sort((a, b) => a - b);
    const mid = Math.floor(v.length / 2);
    return v.length % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2;
}

// Every configuration, not just the visible ones, so switching views keeps the same packages.
function finishedByAll(): TimingBenchmarkResult[] {
    if (!benchmarkData) return [];
    const configs = allConfigs();
    return (benchmarkData.results || []).filter(r => configs.every(c => configTime(r, c) !== null));
}

function summarize(configs: CheckerConfig[]): ConfigSummary[] {
    if (!benchmarkData) return [];
    const common = finishedByAll();
    return configs.map(config => {
        const times = common.map(r => configTime(r, config) as number);
        const mems = common.map(r => configMetrics(r, config)?.peak_memory_mb || 0);
        const failures = (benchmarkData!.results || [])
            .filter(r => configTime(r, config) === null)
            .map(r => ({ pkg: r.package_name, reason: configMetrics(r, config)?.error_message || r.error || 'Failed' }));
        return {
            config,
            geomean: geometricMean(times),
            median: median(times),
            mean: times.length ? times.reduce((s, v) => s + v, 0) / times.length : 0,
            total: times.reduce((s, v) => s + v, 0),
            memGeomean: mems.length && mems.every(m => m > 0) ? geometricMean(mems) : null,
            failures,
        };
    });
}

function formatTime(t: number): string {
    if (t < 10) return `${t.toFixed(3)} s`;
    if (t < 100) return `${t.toFixed(2)} s`;
    return `${t.toFixed(1)} s`;
}

function withinNoise(a: number, b: number): boolean {
    return Math.abs(a - b) <= Math.max(0.010, 0.05 * Math.min(a, b));
}

function shortReason(reason: string): string {
    if (/OOM/i.test(reason)) return 'Out of memory';
    if (/Timeout/i.test(reason)) return 'Timeout (>5 min)';
    if (/Not installed/i.test(reason)) return 'Not installed';
    return 'Crashed';
}

function escapeHtml(s: string): string {
    return s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] as string));
}

function checkerLabel(checker: string): string {
    return `<span class="checker-swatch" style="background:${CHECKER_COLORS[checker] || '#888'}"></span>${CHECKER_NAMES[checker] || checker}`;
}

function interpreterNotePopover(checker: string): string {
    if (checker !== 'ty' && checker !== 'zuban') return '';
    const id = `interpreter-note-${checker}`;
    return `<button type="button" class="note-button" data-note="${id}" aria-controls="${id}"
            aria-expanded="false" aria-label="Interpreter query timing note for ${CHECKER_NAMES[checker]}">&#9432;</button>
        <div popover id="${id}" class="note-popover">
            <h4>Interpreter query timing</h4>
            <p>ty and Zuban discover this benchmark's environment without launching Python.
                Pyrefly, Pyright and mypy query its interpreter for details such as import paths,
                Python version or platform.</p>
            <p>Times include this overhead, which can be a substantial share of a small package's time.</p>
            <p><a href="#interpreter-query-details">Methodology and configuration details</a></p>
        </div>`;
}

function renderStats(): void {
    const grid = document.getElementById('statGrid');
    if (!grid || !benchmarkData) return;
    const failed = summarize(allConfigs()).reduce((n, s) => n + s.failures.length, 0);
    const stats: [number, string][] = [
        [benchmarkData.results?.length || 0, 'Packages tested'],
        [finishedByAll().length, hasInferenceVariants()
            ? 'Finished by every checker and setting (summarized below)'
            : 'Finished by every checker (summarized below)'],
        [(benchmarkData.type_checkers || []).length, 'Type checkers'],
        [failed, "Runs that didn't finish"],
    ];
    grid.innerHTML = stats.map(([v, l]) =>
        `<div class="stat-card"><div class="stat-value">${v}</div><div class="stat-label">${l}</div></div>`).join('');
}

// ---------------------------------------------------------------------------
// Summary bars
// ---------------------------------------------------------------------------

interface BarRow {
    config: CheckerConfig;
    value: number;
    label: string;
}

function barHtml(row: BarRow, max: number, best: number, name: string, trailing: string, nameClass = ''): string {
    const pct = (row.value / max) * 78;
    const rel = row.value === best ? 'lowest' : `${(row.value / best).toFixed(1)}&times; the lowest`;
    const mode = row.config.on === null ? '' : ` rti-bar-${modeName(row.config.on)}`;
    return `<div class="bar-name${nameClass}">${name}</div>
        <div class="bar-track" title="${escapeHtml(configTitle(row.config))}: ${row.label} (${rel.replace('&times;', 'x')})">
            <div class="bar-fill${mode}" style="width:${pct}%;--bar-color:${CHECKER_COLORS[row.config.checker] || '#888'}"></div>
            <span class="bar-value" style="left:calc(${pct}% + 8px)">${row.label}</span>
        </div>
        ${trailing}`;
}

function unsupportedBarHtml(checker: string, on: boolean, name: string, nameClass = ''): string {
    return `<div class="bar-name${nameClass}">${name}</div>
        <div class="bar-track rti-unsupported"><span class="bar-value" style="left:0">n/a</span></div>
        <span class="bar-trailing rti-unsupported">${escapeHtml(unsupportedReason(checker, on) || '')}</span>`;
}

/**
 * Bars for the visible configurations, fastest first. Each setting is compared
 * only with the same setting. In the "both" view, each checker's two settings
 * sit together, ordered by its default configuration.
 */
function renderBars(containerId: string, rows: BarRow[], trailing: (c: CheckerConfig) => string): void {
    const el = document.getElementById(containerId);
    if (!el) return;
    const max = Math.max(...rows.map(r => r.value), 0) || 1;
    const bestFor = (c: CheckerConfig) =>
        Math.min(...rows.filter(r => r.config.on === c.on).map(r => r.value));
    const note = (checker: string) => containerId === 'speedBars' ? interpreterNotePopover(checker) : '';
    el.classList.toggle('rti-paired', hasInferenceVariants() && inferenceView === 'both');

    if (!hasInferenceVariants()) {
        el.innerHTML = [...rows].sort((a, b) => a.value - b.value).map(r =>
            barHtml(r, max, bestFor(r.config), `${checkerLabel(r.config.checker)}${note(r.config.checker)}`, trailing(r.config))).join('');
        return;
    }

    const checkers = benchmarkData?.type_checkers || [];
    if (inferenceView !== 'both') {
        const on = inferenceView === 'on';
        const measured = rows.filter(r => r.config.on === on).sort((a, b) => a.value - b.value);
        const missing = checkers.filter(c => unsupportedReason(c, on) !== null);
        el.innerHTML = measured.map(r =>
            barHtml(r, max, bestFor(r.config), `${checkerLabel(r.config.checker)}${note(r.config.checker)}`, trailing(r.config))).join('')
            + missing.map(c => unsupportedBarHtml(c, on, `<span class="rti-unsupported">${checkerLabel(c)}</span>`)).join('');
        return;
    }

    const defaultValue = (checker: string) =>
        rows.find(r => r.config.checker === checker && r.config.on === inferenceDefault(checker))?.value ?? Infinity;
    el.innerHTML = [...checkers].sort((a, b) => defaultValue(a) - defaultValue(b)).map(checker =>
        [false, true].map((on, i) => {
            const row = rows.find(r => r.config.checker === checker && r.config.on === on);
            const name = `<span class="rti-bar-checker">${i === 0 ? `${checkerLabel(checker)}${note(checker)}` : ''}</span>`
                + `<span class="rti-tag${row ? '' : ' rti-unsupported'}">${modeGlyph(on)}${modeName(on)}</span>`;
            const nameClass = i === 0 ? ' rti-group-start' : '';
            return row
                ? barHtml(row, max, bestFor(row.config), name, trailing(row.config), nameClass)
                : unsupportedBarHtml(checker, on, name, nameClass);
        }).join('')).join('');
}

const METRIC_DESCRIPTIONS: Record<SpeedMetric, string> = {
    geomean: 'Geometric mean of the time per package. Every package counts equally whether it takes 0.1 s or 100 s, so one huge package can\'t dominate.',
    median: 'Median time per package: half the packages are faster than this.',
    mean: 'Ordinary average time per package.',
    total: 'Total time to check all of these packages back to back.',
};

function renderSpeed(): void {
    if (!benchmarkData) return;
    const summaries = summarize(visibleConfigs());
    document.querySelectorAll<HTMLButtonElement>('.metric-tabs button[data-metric]').forEach(b =>
        b.setAttribute('aria-pressed', String(b.dataset.metric === currentMetric)));

    const desc = document.getElementById('speedDescription');
    const which = hasInferenceVariants() ? 'checker and setting' : 'checker';
    if (desc) desc.textContent = `${METRIC_DESCRIPTIONS[currentMetric]} Lower is better. Computed over the ${finishedByAll().length} packages every ${which} finished.`;

    renderBars('speedBars',
        summaries.map(s => ({ config: s.config, value: s[currentMetric], label: formatTime(s[currentMetric]) })),
        config => {
            const f = summaries.find(s => s.config === config)?.failures || [];
            // Paired bars only call out failures, so the column isn't a wall of repeats.
            const paired = hasInferenceVariants() && inferenceView === 'both';
            if (!f.length) return `<span class="bar-trailing">${paired ? '' : `Finished all ${benchmarkData!.results.length}`}</span>`;
            const list = f.map(x => `${x.pkg}: ${shortReason(x.reason)}`).join('\n');
            return `<span class="bar-trailing"><span class="fail-chip" tabindex="0" title="${escapeHtml(list)}"><span class="fail-icon" aria-hidden="true">&#9888;</span>${f.length} didn't finish</span></span>`;
        });

    const note = document.getElementById('speedNote');
    if (!note) return;
    if (currentMetric === 'mean' || currentMetric === 'total') {
        note.classList.add('warn');
        note.textContent = `The ${currentMetric === 'mean' ? 'average' : 'total'} is dominated by the largest packages. Use it if you mostly care about very large codebases.`;
    } else {
        note.classList.remove('warn');
        note.textContent = 'Packages a checker didn\'t finish are listed beside it and left out for every checker, so all are compared on the same packages.';
    }
}

function renderMemory(): void {
    const summaries = summarize(visibleConfigs());
    const el = document.getElementById('memoryBars');
    if (!el) return;
    if (summaries.some(s => s.memGeomean == null)) {
        el.innerHTML = '<p class="summary-note">Peak memory wasn\'t recorded for this run.</p>';
        return;
    }
    renderBars('memoryBars',
        summaries.map(s => ({ config: s.config, value: s.memGeomean as number, label: `${Math.round(s.memGeomean as number)} MB` })),
        () => '<span></span>');
}

function renderFailures(): void {
    const tbody = document.getElementById('failureBody');
    if (!tbody) return;
    const rows = summarize(visibleConfigs()).flatMap(s => s.failures.map(f =>
        `<tr><td>${configLabel(s.config)}</td><td>${escapeHtml(f.pkg)}</td><td class="fail-text" title="${escapeHtml(f.reason)}">&#9888; ${shortReason(f.reason)}</td></tr>`));
    tbody.innerHTML = rows.join('') || '<tr><td colspan="3">Every checker finished every package.</td></tr>';
}

// ---------------------------------------------------------------------------
// Return type inference controls
// ---------------------------------------------------------------------------

function renderInferenceControls(): void {
    const show = hasInferenceVariants();
    document.querySelectorAll<HTMLElement>('.rti-only').forEach(el => { el.hidden = !show; });
    document.querySelectorAll<HTMLButtonElement>('.inference-tabs button').forEach(b =>
        b.setAttribute('aria-pressed', String(b.dataset.view === inferenceView)));
}

// ---------------------------------------------------------------------------
// Per-package table
// ---------------------------------------------------------------------------

function noteId(pkg: string): string {
    return `note-${pkg.replace(/[^A-Za-z0-9_-]/g, '-')}`;
}

function checkerList(checkers: string[]): string {
    const names = checkers.map(c => CHECKER_NAMES[c] || c);
    return names.length > 1 ? `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}` : names.join('');
}

// One native popover per package holds all of its notes; the button after the
// package name and the markers in affected cells all show it (see setupNotes).
function notePopover(pkg: string, notes: PackageNote[]): string {
    const body = notes.map(n => `<p>${escapeHtml(n.text)}</p>
        <p class="note-meta">Affects ${escapeHtml(checkerList(n.checkers))}.${n.link
            ? ` <a href="${escapeHtml(n.link)}" target="_blank" rel="noopener">Source</a>` : ''}</p>`).join('');
    return `<button type="button" class="note-button" data-note="${noteId(pkg)}" aria-controls="${noteId(pkg)}"
            aria-expanded="false" aria-label="Note on how checkers differ on ${escapeHtml(pkg)}">&#9432;</button>
        <div popover id="${noteId(pkg)}" class="note-popover">
            <h4>${escapeHtml(pkg)}</h4>${body}
        </div>`;
}

function noteMarker(pkg: string, checker: string): string {
    if (!packageNotes[pkg]?.some(n => n.checkers.includes(checker))) return '';
    return `<button type="button" class="note-marker" data-note="${noteId(pkg)}" aria-controls="${noteId(pkg)}"
        aria-expanded="false" aria-label="Note on how ${escapeHtml(CHECKER_NAMES[checker] || checker)} differs on ${escapeHtml(pkg)}">&#9432;</button>`;
}

const NOTE_TRIGGER = '.note-button, .note-marker';
// Long enough to move the pointer from the trigger onto the note (to reach its link).
const NOTE_HIDE_DELAY_MS = 200;
let noteHideTimer: number | undefined;
let openNoteTrigger: HTMLElement | null = null;

function showNote(trigger: HTMLElement): void {
    window.clearTimeout(noteHideTimer);
    const pop = document.getElementById(trigger.dataset.note || '');
    if (!pop) return;
    if (openNoteTrigger && openNoteTrigger !== trigger) openNoteTrigger.setAttribute('aria-expanded', 'false');
    if (!pop.matches(':popover-open')) pop.showPopover();
    openNoteTrigger = trigger;
    trigger.setAttribute('aria-expanded', 'true');
    // Place below the trigger, or above it if there is no room, kept inside the viewport.
    const t = trigger.getBoundingClientRect();
    const p = pop.getBoundingClientRect();
    const top = t.bottom + 6 + p.height <= window.innerHeight ? t.bottom + 6 : Math.max(8, t.top - 6 - p.height);
    const left = Math.min(Math.max(8, t.left), window.innerWidth - p.width - 8);
    pop.style.top = `${top}px`;
    pop.style.left = `${left}px`;
}

function hideNote(): void {
    window.clearTimeout(noteHideTimer);
    document.querySelectorAll<HTMLElement>('.note-popover:popover-open').forEach(p => p.hidePopover());
}

function scheduleHideNote(): void {
    window.clearTimeout(noteHideTimer);
    noteHideTimer = window.setTimeout(() => {
        if (inNote(document.activeElement)
            || document.querySelector('.note-button:hover, .note-marker:hover, .note-popover:hover')) return;
        hideNote();
    }, NOTE_HIDE_DELAY_MS);
}

// Within a trigger or an open note, so moving between them keeps the note up.
function inNote(el: EventTarget | null): boolean {
    return el instanceof Element && !!el.closest(`${NOTE_TRIGGER}, .note-popover`);
}

// Delegated from the document because the table re-renders on every filter change.
function setupNotes(): void {
    document.addEventListener('mouseover', e => {
        const trigger = (e.target as Element).closest<HTMLElement>(NOTE_TRIGGER);
        if (trigger) showNote(trigger);
        else if (inNote(e.target)) window.clearTimeout(noteHideTimer);
    });
    document.addEventListener('mouseout', e => {
        if (inNote(e.target) && !inNote(e.relatedTarget)) scheduleHideNote();
    });
    document.addEventListener('focusin', e => {
        const trigger = (e.target as Element).closest<HTMLElement>(NOTE_TRIGGER);
        if (trigger) showNote(trigger);
    });
    document.addEventListener('focusout', e => {
        if (inNote(e.target) && !inNote(e.relatedTarget)) scheduleHideNote();
    });
    // Touch has no hover: a tap shows the note, and tapping elsewhere dismisses it.
    document.addEventListener('click', e => {
        const trigger = (e.target as Element).closest<HTMLElement>(NOTE_TRIGGER);
        if (trigger) showNote(trigger);
    });
    document.addEventListener('toggle', e => {
        // Toggle events arrive asynchronously, so only reset if the note that closed is still the current one.
        if ((e as ToggleEvent).newState === 'closed' && openNoteTrigger
            && (e.target as Element).id === openNoteTrigger.dataset.note) {
            openNoteTrigger.setAttribute('aria-expanded', 'false');
            openNoteTrigger = null;
        }
    }, true);
    window.addEventListener('scroll', hideNote, { passive: true });
}

/** Fastest time among the visible configurations with return type inference `on`. */
function fastest(r: TimingBenchmarkResult, configs: CheckerConfig[], on: boolean | null): number {
    const times = configs.filter(c => c.on === on).map(c => configTime(r, c)).filter((t): t is number => t !== null);
    return times.length ? Math.min(...times) : 0;
}

interface TimeCell {
    cls: string;
    html: string;
}

/** One checker's time on one package with one setting, compared with the fastest checker at that setting. */
function timeCell(r: TimingBenchmarkResult, checker: string, on: boolean | null, best: number, inline: boolean): TimeCell {
    const reason = on === null ? null : unsupportedReason(checker, on);
    if (reason) return { cls: 'rti-unsupported', html: `<span title="${escapeHtml(reason)}">n/a</span>` };
    const config = { checker, on };
    const m = configMetrics(r, config);
    const t = configTime(r, config);
    if (t === null) {
        const failure = m?.error_message || r.error || 'Failed';
        return { cls: 'fail-text', html: `<span title="${escapeHtml(failure)}">&#9888; ${shortReason(failure)}</span>` };
    }
    const mem = m?.peak_memory_mb ? `, ${Math.round(m.peak_memory_mb)} MB` : '';
    const title = `${escapeHtml(configTitle(config))}: ${formatTime(t)}${mem}`;
    const time = `<span class="rti-time" title="${title}">${formatTime(t)}</span>`;
    if (withinNoise(t, best)) return { cls: 'best', html: time };
    const slower = `<span class="times-slower${inline ? ' inline' : ''}">${(t / best).toFixed(1)}&times;</span>`;
    return { cls: '', html: `${time}${slower}` };
}

function populateResultsTable(filterText?: string, sortBy?: string): void {
    if (!benchmarkData) return;
    const head = document.getElementById('resultsHead');
    const tbody = document.getElementById('resultsBody');
    if (!head || !tbody) return;
    const checkers = benchmarkData.type_checkers || [];
    const configs = visibleConfigs();
    const f = (filterText || '').toLowerCase();
    let results = (benchmarkData.results || []).filter(r => r.package_name.toLowerCase().includes(f));

    const okTimes = (r: TimingBenchmarkResult) =>
        configs.map(c => configTime(r, c)).filter((t): t is number => t !== null);
    const slowest = (r: TimingBenchmarkResult) => Math.max(0, ...okTimes(r));
    const spread = (r: TimingBenchmarkResult) => {
        const t = okTimes(r);
        return t.length ? Math.max(...t) / Math.max(Math.min(...t), 0.001) : 0;
    };
    results = [...results].sort((a, b) => {
        if (sortBy === 'slowest') return slowest(b) - slowest(a);
        if (sortBy === 'spread') return spread(b) - spread(a);
        return a.package_name.toLowerCase().localeCompare(b.package_name.toLowerCase());
    });

    const variants = hasInferenceVariants();
    const settings: (boolean | null)[] = !variants ? [null]
        : inferenceView === 'both' ? [false, true] : [inferenceView === 'on'];
    const paired = settings.length === 2;
    const columns = paired && cellLayout === 'columns';
    const table = head.closest('table');
    table?.classList.toggle('rti-stacked', paired && !columns);
    table?.classList.toggle('rti-columns', columns);

    const defaultNote = (c: string) => variants
        ? `<span class="rti-default">default: ${modeName(inferenceDefault(c) as boolean)}</span>` : '';
    const unsupportedHead = (c: string) =>
        !paired && settings[0] !== null && unsupportedReason(c, settings[0]) ? ' class="rti-unsupported"' : '';
    if (columns) {
        head.innerHTML = `<tr><th rowspan="2">Package</th>${checkers.map(c =>
            `<th colspan="2" class="rti-group">${checkerLabel(c)}${defaultNote(c)}</th>`).join('')}</tr>
            <tr>${checkers.map(() => settings.map(on =>
                `<th class="rti-subhead">${modeGlyph(on as boolean)}${modeName(on as boolean)}</th>`).join('')).join('')}</tr>`;
    } else {
        head.innerHTML = `<tr><th>Package</th>${checkers.map(c =>
            `<th${unsupportedHead(c)}>${checkerLabel(c)}${defaultNote(c)}</th>`).join('')}</tr>`;
    }

    const colCount = 1 + checkers.length * (columns ? 2 : 1);
    tbody.innerHTML = results.map(r => {
        const best = new Map(settings.map(on => [on, fastest(r, configs, on)]));
        const cells = checkers.map(c => {
            const marker = noteMarker(r.package_name, c);
            if (columns) {
                return settings.map((on, i) => {
                    const cell = timeCell(r, c, on, best.get(on) as number, false);
                    return `<td class="${cell.cls}${i === 0 ? ' rti-group' : ''}">${cell.html}${i === 0 ? marker : ''}</td>`;
                }).join('');
            }
            if (paired) {
                const lines = settings.map(on => {
                    const cell = timeCell(r, c, on, best.get(on) as number, true);
                    return `<div class="rti-line ${cell.cls}">${modeGlyph(on as boolean)}${cell.html}</div>`;
                }).join('');
                return `<td>${lines}${marker}</td>`;
            }
            const cell = timeCell(r, c, settings[0], best.get(settings[0]) as number, false);
            return `<td class="${cell.cls}">${cell.html}${marker}</td>`;
        }).join('');
        const notes = packageNotes[r.package_name];
        return `<tr><td>${escapeHtml(r.package_name)}${notes ? notePopover(r.package_name, notes) : ''}</td>${cells}</tr>`;
    }).join('') || `<tr><td colspan="${colCount}" class="loading-row">No packages match.</td></tr>`;
}

function refreshViews(): void {
    renderInferenceControls();
    renderSpeed();
    renderMemory();
    renderFailures();
    const searchInput = document.getElementById('packageSearch') as HTMLInputElement | null;
    const sortSelect = document.getElementById('sortBy') as HTMLSelectElement | null;
    populateResultsTable(searchInput?.value || '', sortSelect?.value || 'name');
}

function setupFilters(): void {
    const searchInput = document.getElementById('packageSearch') as HTMLInputElement | null;
    const sortSelect = document.getElementById('sortBy') as HTMLSelectElement | null;
    const refresh = () => populateResultsTable(searchInput?.value || '', sortSelect?.value || 'name');
    searchInput?.addEventListener('input', refresh);
    sortSelect?.addEventListener('change', refresh);
    document.querySelectorAll<HTMLButtonElement>('.metric-tabs button[data-metric]').forEach(b =>
        b.addEventListener('click', () => {
            currentMetric = (b.dataset.metric as SpeedMetric) || 'geomean';
            renderSpeed();
        }));
    document.querySelectorAll<HTMLButtonElement>('.inference-tabs button').forEach(b =>
        b.addEventListener('click', () => {
            inferenceView = (b.dataset.view as InferenceView) || 'both';
            updateUrlParam('inference', inferenceView === 'both' ? null : inferenceView);
            refreshViews();
        }));
}

document.addEventListener('DOMContentLoaded', init);

export {};
