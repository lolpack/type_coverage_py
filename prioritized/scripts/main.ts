// Configuration - paths relative to prioritized folder
const JSON_BASE_PATH = 'historical_data/json/';
const CURRENT_JSON_PATH = 'package_report.json';

interface CoverageData {
    parameter_coverage?: number;
    return_type_coverage?: number;
    parameter_coverage_with_stubs?: number;
    return_type_coverage_with_stubs?: number;
}

interface TypeshedData {
    '% param'?: number;
    '% return'?: number;
    completeness_level?: string;
    stubtest_strictness?: string;
}

interface PyrightStats {
    withKnownType?: string;
    withAmbiguousType?: string;
    withUnknownType?: string;
    coverage?: number;
}

interface PackageDetails {
    DownloadRanking?: number;
    DownloadCount?: number;
    HasTypeShed?: boolean;
    HasStubsPackage?: boolean;
    HasPyTypedFile?: boolean;
    non_typeshed_stubs?: string;
    CoverageData?: CoverageData;
    TypeshedData?: TypeshedData;
    pyright_stats?: PyrightStats;
}

type PackageReport = Record<string, PackageDetails>;

// Color calculation for coverage percentages
function getColor(percentage: number): string {
    if (percentage < 0 || percentage === null || percentage === undefined) {
        return 'transparent';
    }
    let red: number, green: number;
    if (percentage < 50) {
        red = 255;
        green = Math.floor(255 * (percentage / 50));
    } else {
        red = Math.floor(255 * ((100 - percentage) / 50));
        green = 255;
    }
    return `rgb(${red},${green},55)`;
}

// Format percentage for display
function formatPercentage(value: number | string | null | undefined): string {
    if (value === null || value === undefined || value === 'N/A') {
        return 'N/A';
    }
    if (typeof value === 'number') {
        if (value < 0) return 'N/A';
        return value.toFixed(2) + '%';
    }
    return value;
}

// Create a percentage cell with color
function createPercentageCell(value: number | string | null | undefined): string {
    const formatted = formatPercentage(value);
    if (formatted === 'N/A') {
        return `<td class="coverage-cell">N/A</td>`;
    }
    const color = getColor(parseFloat(String(value)));
    return `<td class="coverage-cell" style="background-color: ${color};">${formatted}</td>`;
}

// Create a boolean cell
function createBooleanCell(value: boolean | null | undefined): string {
    if (value) {
        return `<td class="boolean-yes">Yes</td>`;
    }
    return `<td class="boolean-no">No</td>`;
}

// Format number with commas
function formatNumber(num: number | null | undefined): string {
    if (num === null || num === undefined) return 'N/A';
    return num.toLocaleString();
}

// Render the table with package data
function renderTable(data: PackageReport): void {
    const container = document.getElementById('table-container')!;

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
                    <th>Pyright Known Types</th>
                    <th>Pyright Ambiguous Types</th>
                    <th>Pyright Unknown Types</th>
                    <th>Pyright Coverage</th>
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
        const pyright = details.pyright_stats || {};

        const paramCoverage = coverage.parameter_coverage;
        const returnCoverage = coverage.return_type_coverage;
        const paramCoverageStubs = coverage.parameter_coverage_with_stubs;
        const returnCoverageStubs = coverage.return_type_coverage_with_stubs;

        const typeshedParam = typeshed['% param'];
        const typeshedReturn = typeshed['% return'];

        let nonTypeshedStubs: string = details.non_typeshed_stubs || 'N/A';
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
                <td>${pyright.withKnownType || 'N/A'}</td>
                <td>${pyright.withAmbiguousType || 'N/A'}</td>
                <td>${pyright.withUnknownType || 'N/A'}</td>
                ${createPercentageCell(pyright.coverage)}
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
async function loadAvailableDates(): Promise<void> {
    const datePicker = document.getElementById('date-picker') as HTMLSelectElement;

    try {
        // Try to load the dates manifest file
        const response = await fetch('historical_data/json/dates.json');
        if (response.ok) {
            const dates: string[] = await response.json();
            dates.forEach(date => {
                const option = document.createElement('option');
                option.value = date;
                option.textContent = date;
                datePicker.appendChild(option);
            });
        } else {
            console.log('No dates manifest found, using current data only');
        }
    } catch (error) {
        console.error('Error loading dates:', error);
    }
}

// Load package data from JSON
async function loadPackageData(date: string | null = null): Promise<void> {
    const container = document.getElementById('table-container')!;
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
        const data: PackageReport = await response.json();
        renderTable(data);
    } catch (error) {
        console.error('Error loading package data:', error);
        container.innerHTML = `<div class="loading">Error loading data: ${(error as Error).message}</div>`;
    }
}

// Initialize the page
document.addEventListener('DOMContentLoaded', async () => {
    await loadAvailableDates();
    await loadPackageData();

    // Set up date picker change handler
    document.getElementById('date-picker')!.addEventListener('change', (e) => {
        const selectedDate = (e.target as HTMLSelectElement).value;
        loadPackageData(selectedDate || null);
    });
});

export {};
