// Configuration
const JSON_BASE_PATH = 'historical_data/json/';
const CURRENT_JSON_PATH = 'package_report.json';
// Color calculation for coverage percentages
function getColor(percentage) {
    if (percentage < 0 || percentage === null || percentage === undefined) {
        return 'transparent';
    }
    let red, green;
    if (percentage < 50) {
        red = 255;
        green = Math.floor(255 * (percentage / 50));
    }
    else {
        red = Math.floor(255 * ((100 - percentage) / 50));
        green = 255;
    }
    return `rgb(${red},${green},55)`;
}
// Format percentage for display
function formatPercentage(value) {
    if (value === null || value === undefined || value === 'N/A') {
        return 'N/A';
    }
    if (typeof value === 'number') {
        if (value < 0)
            return 'N/A';
        return value.toFixed(2) + '%';
    }
    return value;
}
// Create a percentage cell with color
function createPercentageCell(value) {
    const formatted = formatPercentage(value);
    if (formatted === 'N/A') {
        return `<td class="coverage-cell">N/A</td>`;
    }
    const color = getColor(parseFloat(String(value)));
    return `<td class="coverage-cell" style="background-color: ${color};">${formatted}</td>`;
}
// Create a boolean cell
function createBooleanCell(value) {
    if (value) {
        return `<td class="boolean-yes">Yes</td>`;
    }
    return `<td class="boolean-no">No</td>`;
}
// Format number with commas
function formatNumber(num) {
    if (num === null || num === undefined)
        return 'N/A';
    return num.toLocaleString();
}
// Render the table with package data
function renderTable(data) {
    const container = document.getElementById('table-container');
    let html = `
        <table>
            <thead>
                <tr>
                    <th>Ranking</th>
                    <th>Package Name</th>
                    <th>Download Count</th>
                    <th>Has Typeshed</th>
                    <th>Has Stubs Package</th>
                    <th>Has py.typed File</th>
                    <th>Non-Typeshed Stubs</th>
                    <th>Parameter Type Coverage</th>
                    <th>Return Type Coverage</th>
                    <th>Parameter Coverage w/ Typeshed</th>
                    <th>Return Type Coverage w/ Typeshed</th>
                    <th>Typeshed-stats Parameter Type Coverage</th>
                    <th>Typeshed-stats Return Type Coverage</th>
                    <th>Typeshed-stats Completeness Level</th>
                    <th>Typeshed-stats Stubtest Strictness</th>
                </tr>
            </thead>
            <tbody>
    `;
    for (const [packageName, details] of Object.entries(data)) {
        const coverage = details.CoverageData || {};
        const typeshed = details.TypeshedData || {};
        const paramCoverage = coverage.parameter_coverage;
        const returnCoverage = coverage.return_type_coverage;
        const paramCoverageStubs = coverage.parameter_coverage_with_stubs;
        const returnCoverageStubs = coverage.return_type_coverage_with_stubs;
        const typeshedParam = typeshed['% param'];
        const typeshedReturn = typeshed['% return'];
        let nonTypeshedStubs = details.non_typeshed_stubs || 'N/A';
        if (nonTypeshedStubs !== 'N/A') {
            nonTypeshedStubs = `<a href="${nonTypeshedStubs}" target="_blank" class="package-link">${packageName}-stubs</a>`;
        }
        html += `
            <tr>
                <td>${details.DownloadRanking || 'N/A'}</td>
                <td>${packageName}</td>
                <td>${formatNumber(details.DownloadCount)}</td>
                ${createBooleanCell(details.HasTypeShed)}
                ${createBooleanCell(details.HasStubsPackage)}
                ${createBooleanCell(details.HasPyTypedFile)}
                <td>${nonTypeshedStubs}</td>
                ${createPercentageCell(paramCoverage)}
                ${createPercentageCell(returnCoverage)}
                ${createPercentageCell(paramCoverageStubs)}
                ${createPercentageCell(returnCoverageStubs)}
                ${createPercentageCell(typeshedParam)}
                ${createPercentageCell(typeshedReturn)}
                <td>${typeshed.completeness_level || 'N/A'}</td>
                <td>${typeshed.stubtest_strictness || 'N/A'}</td>
            </tr>
        `;
    }
    html += `
            </tbody>
        </table>
    `;
    container.innerHTML = html;
}
// Load available dates for the date picker
async function loadAvailableDates() {
    const datePicker = document.getElementById('date-picker');
    try {
        // Try to load the dates manifest file
        const response = await fetch('historical_data/json/dates.json');
        if (response.ok) {
            const dates = await response.json();
            dates.forEach(date => {
                const option = document.createElement('option');
                option.value = date;
                option.textContent = date;
                datePicker.appendChild(option);
            });
        }
        else {
            // Fallback: try to load a known recent date range
            const today = new Date();
            const dates = [];
            for (let i = 0; i < 365; i++) {
                const date = new Date(today);
                date.setDate(date.getDate() - i);
                const dateStr = date.toISOString().split('T')[0];
                dates.push(dateStr);
            }
            // Just add some placeholder dates - in production the manifest should exist
            console.log('No dates manifest found, using current data only');
        }
    }
    catch (error) {
        console.error('Error loading dates:', error);
    }
}
// Load package data from JSON
async function loadPackageData(date = null) {
    const container = document.getElementById('table-container');
    container.innerHTML = '<div class="loading">Loading package data...</div>';
    let jsonPath = CURRENT_JSON_PATH;
    if (date) {
        jsonPath = `${JSON_BASE_PATH}package_report-${date}.json`;
    }
    try {
        const response = await fetch(jsonPath);
        if (!response.ok) {
            throw new Error(`Failed to load data: ${response.status}`);
        }
        const data = await response.json();
        renderTable(data);
    }
    catch (error) {
        console.error('Error loading package data:', error);
        container.innerHTML = `<div class="loading">Error loading data: ${error.message}</div>`;
    }
}
// Initialize the page
document.addEventListener('DOMContentLoaded', async () => {
    await loadAvailableDates();
    await loadPackageData();
    // Set up date picker change handler
    document.getElementById('date-picker').addEventListener('change', (e) => {
        const selectedDate = e.target.value;
        loadPackageData(selectedDate || null);
    });
});
export {};
