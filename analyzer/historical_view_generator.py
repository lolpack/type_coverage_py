import os
import json
from datetime import datetime
from typing import Dict, List, Any
from jinja2 import Template

def collect_historical_data(data_dir: str) -> Dict[str, List[Dict[str, Any]]]:
    historical_data: Dict[str, List[Dict[str, Any]]] = {}
    for filename in sorted(os.listdir(data_dir)):
        if filename.endswith(".json"):
            # Adjust the logic to extract the date
            date_str = filename.replace("package_report-", "").replace(".json", "")
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                print(f"Skipping file with invalid date format: {filename}")
                continue
            with open(os.path.join(data_dir, filename), "r") as f:
                data: Dict[str, Any] = json.load(f)
                for package, details in data.items():
                    if package not in historical_data:
                        historical_data[package] = []
                    formatted_date = date.strftime("%Y-%m-%d")
                    record: dict[str, Any] = {"date": formatted_date}
                    record.update({k: v for k, v in details.items() if k != 'pyright_stats'})
                    pyright_stats = details.get('pyright_stats', {})
                    record['pyright_coverage'] = pyright_stats.get('coverage') or 0.0
                    historical_data[package].append(record)
    print(f"Collected data for {len(historical_data)} packages.")
    return historical_data


def generate_html(historical_data: Dict[str, List[Dict[str, Any]]], html_output: str) -> None:
    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Type Coverage Visualization</title>
        <link rel="icon" href="https://raw.githubusercontent.com/jdecked/twemoji/master/assets/svg/2705.svg" type="image/svg+xml">
        <script src="chart.min.js"></script>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f9f9f9;
            }
            h1 {
                text-align: center;
                color: #333;
            }
            .table-container {
                margin: 20px auto;
                max-width: 800px;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 20px;
            }
            th, td {
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }
            th {
                background-color: #f2f2f2;
                font-weight: bold;
            }
            .chart-container {
                position: relative;
                width: 100%;
                max-width: 800px;
                margin: 20px auto;
            }
        </style>
    </head>
    <body>
        <h1>Type Coverage Historical Trends</h1>
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>Package</th>
                        <th>Rank</th>
                        <th>Graph</th>
                    </tr>
                </thead>
                <tbody>
                    {% for package, records in historical_data.items() %}
                    <tr>
                        <td>{{ package }}</td>
                        <td>{{ records[-1]['DownloadRanking'] }}</td>
                        <td>
                            <div class="chart-container" id="chart-container-{{ package }}">
                                <canvas id="chart-{{ package }}"></canvas>
                            </div>
                            <script>
                                (function() {
                                    const ctx = document.getElementById('chart-{{ package }}').getContext('2d');
                                    new Chart(ctx, {
                                        type: 'line',
                                        data: {
                                            labels: {{ records | map(attribute='date') | list | safe }},
                                            datasets: [
                                                {
                                                    label: 'Download Ranking',
                                                    data: {{ records | map(attribute='DownloadRanking') | list | safe }},
                                                    borderColor: 'rgb(255, 99, 132)',
                                                    yAxisID: 'y2',
                                                    tension: 0.1
                                                },
                                                {
                                                    label: 'Param Coverage with Stubs',
                                                    data: {{ records | map(attribute='CoverageData.parameter_coverage_with_stubs') | list | safe }},
                                                    borderColor: 'rgb(54, 162, 235)',
                                                    yAxisID: 'y1',
                                                    tension: 0.1
                                                },
                                                {
                                                    label: 'Return Coverage with Stubs',
                                                    data: {{ records | map(attribute='CoverageData.return_type_coverage_with_stubs') | list | safe }},
                                                    borderColor: 'rgb(75, 192, 192)',
                                                    yAxisID: 'y1',
                                                    tension: 0.1
                                                },
                                                {
                                                    label: 'Parameter Coverage',
                                                    data: {{ records | map(attribute='CoverageData.parameter_coverage') | list | safe }},
                                                    borderColor: 'rgb(153, 102, 255)',
                                                    yAxisID: 'y1',
                                                    tension: 0.1
                                                },
                                                {
                                                    label: 'Return Coverage',
                                                    data: {{ records | map(attribute='CoverageData.return_type_coverage') | list | safe }},
                                                    borderColor: 'rgb(255, 159, 64)',
                                                    yAxisID: 'y1',
                                                    tension: 0.1
                                                },
                                                {
                                                    label: 'Pyright Coverage',
                                                    data: {{ records | map(attribute='pyright_coverage') | list | safe }},
                                                    borderColor: 'rgb(255, 159, 64)',
                                                    yAxisID: 'y1',
                                                    tension: 0.1
                                                }
                                            ]
                                        },
                                        options: {
                                            responsive: true,
                                            maintainAspectRatio: false,
                                            plugins: {
                                                legend: {
                                                    display: true,
                                                    position: 'top'
                                                }
                                            },
                                            scales: {
                                                y1: {
                                                    type: 'linear',
                                                    position: 'left',
                                                    title: {
                                                        display: true,
                                                        text: 'Coverage Percent'
                                                    },
                                                    ticks: {
                                                        callback: function(value) {
                                                            return value + '%';
                                                        }
                                                    }
                                                },
                                                y2: {
                                                    type: 'linear',
                                                    position: 'right',
                                                    title: {
                                                        display: true,
                                                        text: 'Download Rank'
                                                    },
                                                    reverse: true
                                                },
                                                x: {
                                                    title: {
                                                        display: true,
                                                        text: 'Date'
                                                    }
                                                }
                                            }
                                        }
                                    });
                                })();
                            </script>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    template = Template(html_template)
    html_content = template.render(historical_data=historical_data)

    with open(html_output, "w") as f:
        f.write(html_content)

    print("HTML generated successfully.")

def generate_historical_graphs(historical_data_dir: str, html_output: str) -> None:
    historical_data = collect_historical_data(historical_data_dir)
    generate_html(historical_data, html_output)
