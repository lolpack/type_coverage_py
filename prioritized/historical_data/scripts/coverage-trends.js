// Configuration - paths relative to prioritized/historical_data folder
const JSON_BASE_PATH = 'json/';
// Chart colors - improved for better visibility, Pyright is primary here
const COLORS = {
    ranking: 'rgb(255, 99, 132)',
    paramStubs: 'rgb(59, 130, 246)', // Blue
    returnStubs: 'rgb(16, 185, 129)', // Green
    param: 'rgb(139, 92, 246)', // Purple
    return: 'rgb(249, 115, 22)', // Orange
    pyright: 'rgb(236, 72, 153)' // Pink - primary metric for prioritized
};
let historicalData = {};
let charts = {};
// Collect historical data from all JSON files
async function loadHistoricalData() {
    const container = document.getElementById('charts-container');
    try {
        // First, try to load the dates manifest
        const datesResponse = await fetch(`${JSON_BASE_PATH}dates.json`);
        let dates = [];
        if (datesResponse.ok) {
            dates = await datesResponse.json();
        }
        else {
            // Fallback: generate date range
            const today = new Date();
            for (let i = 365; i >= 0; i--) {
                const date = new Date(today);
                date.setDate(date.getDate() - i);
                dates.push(date.toISOString().split('T')[0]);
            }
        }
        // Load all available JSON files
        const loadPromises = dates.map(async (date) => {
            try {
                const response = await fetch(`${JSON_BASE_PATH}package_report-${date}.json`);
                if (response.ok) {
                    const data = await response.json();
                    return { date, data };
                }
            }
            catch (e) {
                // File doesn't exist, skip
            }
            return null;
        });
        const results = await Promise.all(loadPromises);
        const validResults = results.filter((r) => r !== null);
        if (validResults.length === 0) {
            container.innerHTML = '<div class="no-data">No historical data found.</div>';
            return;
        }
        // Organize data by package
        historicalData = {};
        for (const { date, data } of validResults) {
            for (const [packageName, details] of Object.entries(data)) {
                if (!historicalData[packageName]) {
                    historicalData[packageName] = [];
                }
                historicalData[packageName].push({
                    date,
                    ranking: details.DownloadRanking,
                    paramCoverage: details.CoverageData?.parameter_coverage ?? 0,
                    returnCoverage: details.CoverageData?.return_type_coverage ?? 0,
                    paramCoverageStubs: details.CoverageData?.parameter_coverage_with_stubs ?? 0,
                    returnCoverageStubs: details.CoverageData?.return_type_coverage_with_stubs ?? 0,
                    pyrightCoverage: details.pyright_stats?.coverage ?? 0
                });
            }
        }
        // Sort each package's data by date
        for (const packageName of Object.keys(historicalData)) {
            historicalData[packageName].sort((a, b) => a.date.localeCompare(b.date));
        }
        renderCharts();
    }
    catch (error) {
        console.error('Error loading historical data:', error);
        container.innerHTML = `<div class="loading">Error loading data: ${error.message}</div>`;
    }
}
// Get the current rank for sorting
function getCurrentRank(packageName) {
    const data = historicalData[packageName];
    if (!data || data.length === 0)
        return Infinity;
    return data[data.length - 1].ranking || Infinity;
}
// Render charts for all packages
function renderCharts() {
    const container = document.getElementById('charts-container');
    const filter = document.getElementById('package-filter').value.toLowerCase();
    const limit = document.getElementById('limit-select').value;
    const metric = document.getElementById('metric-select').value;
    // Destroy existing charts
    Object.values(charts).forEach((chart) => chart.destroy());
    charts = {};
    // Filter and sort packages
    let packages = Object.keys(historicalData)
        .filter(name => name.toLowerCase().includes(filter))
        .sort((a, b) => getCurrentRank(a) - getCurrentRank(b));
    if (limit !== 'all') {
        packages = packages.slice(0, parseInt(limit));
    }
    if (packages.length === 0) {
        container.innerHTML = '<div class="no-data">No packages match your filter.</div>';
        return;
    }
    container.innerHTML = '';
    for (const packageName of packages) {
        const data = historicalData[packageName];
        const currentRank = getCurrentRank(packageName);
        const latestData = data[data.length - 1];
        // Get the current value for the selected metric
        const metricValues = {
            'param_stubs': latestData.paramCoverageStubs,
            'return_stubs': latestData.returnCoverageStubs,
            'param': latestData.paramCoverage,
            'return': latestData.returnCoverage,
            'pyright': latestData.pyrightCoverage
        };
        const currentValue = metricValues[metric] || 0;
        const coverageClass = currentValue >= 80 ? 'coverage-high' : currentValue >= 50 ? 'coverage-medium' : 'coverage-low';
        // Create card
        const card = document.createElement('div');
        card.className = 'package-card';
        card.innerHTML = `
            <div class="package-header">
                <div class="package-info">
                    <span class="package-name">${packageName}</span>
                    <span class="package-rank">Download Rank #${currentRank}</span>
                </div>
                <span class="coverage-badge ${coverageClass}">${currentValue.toFixed(1)}%</span>
            </div>
            <div class="chart-container">
                <canvas id="chart-${packageName.replace(/[^a-zA-Z0-9]/g, '-')}"></canvas>
            </div>
        `;
        container.appendChild(card);
        // Create chart
        const ctx = card.querySelector('canvas').getContext('2d');
        const chartData = createChartData(data, metric);
        charts[packageName] = new Chart(ctx, {
            type: 'line',
            data: chartData,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            usePointStyle: true,
                            padding: 15
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                let label = context.dataset.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                if (context.parsed.y !== null) {
                                    if (context.dataset.yAxisID === 'y2') {
                                        label += context.parsed.y;
                                    }
                                    else {
                                        label += context.parsed.y.toFixed(2) + '%';
                                    }
                                }
                                return label;
                            }
                        }
                    }
                },
                scales: {
                    y1: {
                        type: 'linear',
                        position: 'left',
                        min: 0,
                        max: 100,
                        title: {
                            display: true,
                            text: 'Coverage %'
                        },
                        ticks: {
                            callback: (value) => value + '%'
                        }
                    },
                    y2: {
                        type: 'linear',
                        position: 'right',
                        reverse: true,
                        title: {
                            display: true,
                            text: 'Rank'
                        },
                        grid: {
                            drawOnChartArea: false
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Date'
                        },
                        ticks: {
                            maxTicksLimit: 12,
                            maxRotation: 45,
                            minRotation: 45
                        }
                    }
                }
            }
        });
    }
}
// Create chart data configuration
function createChartData(data, primaryMetric) {
    const labels = data.map(d => d.date);
    // Helper to determine if this metric is primary (shown with emphasis)
    const isPrimary = (metric) => metric === primaryMetric;
    const datasets = [
        {
            label: 'Download Ranking',
            data: data.map(d => d.ranking),
            borderColor: COLORS.ranking,
            backgroundColor: COLORS.ranking + '20',
            yAxisID: 'y2',
            tension: 0.1,
            hidden: true,
            pointRadius: 2,
            borderWidth: 1,
            fill: false
        },
        {
            label: 'Pyright Coverage',
            data: data.map(d => d.pyrightCoverage),
            borderColor: COLORS.pyright,
            backgroundColor: 'rgba(200, 200, 200, 0.2)',
            yAxisID: 'y1',
            tension: 0.3,
            hidden: !isPrimary('pyright'),
            pointRadius: isPrimary('pyright') ? 3 : 2,
            borderWidth: isPrimary('pyright') ? 3 : 1.5,
            fill: isPrimary('pyright')
        },
        {
            label: 'Param Coverage (with Stubs)',
            data: data.map(d => d.paramCoverageStubs),
            borderColor: COLORS.paramStubs,
            backgroundColor: 'rgba(200, 200, 200, 0.2)',
            yAxisID: 'y1',
            tension: 0.3,
            hidden: !isPrimary('param_stubs'),
            pointRadius: isPrimary('param_stubs') ? 3 : 2,
            borderWidth: isPrimary('param_stubs') ? 3 : 1.5,
            fill: isPrimary('param_stubs')
        },
        {
            label: 'Return Coverage (with Stubs)',
            data: data.map(d => d.returnCoverageStubs),
            borderColor: COLORS.returnStubs,
            backgroundColor: 'rgba(200, 200, 200, 0.2)',
            yAxisID: 'y1',
            tension: 0.3,
            hidden: !isPrimary('return_stubs'),
            pointRadius: isPrimary('return_stubs') ? 3 : 2,
            borderWidth: isPrimary('return_stubs') ? 3 : 1.5,
            fill: isPrimary('return_stubs')
        },
        {
            label: 'Parameter Coverage',
            data: data.map(d => d.paramCoverage),
            borderColor: COLORS.param,
            backgroundColor: 'rgba(200, 200, 200, 0.2)',
            yAxisID: 'y1',
            tension: 0.3,
            hidden: !isPrimary('param'),
            pointRadius: isPrimary('param') ? 3 : 2,
            borderWidth: isPrimary('param') ? 3 : 1.5,
            fill: isPrimary('param')
        },
        {
            label: 'Return Coverage',
            data: data.map(d => d.returnCoverage),
            borderColor: COLORS.return,
            backgroundColor: 'rgba(200, 200, 200, 0.2)',
            yAxisID: 'y1',
            tension: 0.3,
            hidden: !isPrimary('return'),
            pointRadius: isPrimary('return') ? 3 : 2,
            borderWidth: isPrimary('return') ? 3 : 1.5,
            fill: isPrimary('return')
        }
    ];
    return { labels, datasets };
}
// Debounce helper
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadHistoricalData();
    // Set up filter handlers
    document.getElementById('package-filter').addEventListener('input', debounce(renderCharts, 300));
    document.getElementById('limit-select').addEventListener('change', renderCharts);
    document.getElementById('metric-select').addEventListener('change', renderCharts);
});
export {};
