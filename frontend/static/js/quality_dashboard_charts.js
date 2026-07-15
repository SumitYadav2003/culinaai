/* =========================================================
   CULINAAI ADMIN QUALITY DASHBOARD CHARTS
   Website-theme graph colours:
   dark brown, orange, gold, green, cream.
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    if (typeof Chart === "undefined") {
        console.error("Chart.js is not loaded.");
        return;
    }

    const scoreDistributionData = readChartData("scoreDistributionData");
    const riskLevelData = readChartData("riskLevelData");
    const validationHealthData = readChartData("validationHealthData");
    const recipeTrendData = readChartData("recipeTrendData");
    const topCuisineData = readChartData("topCuisineData");
    const topMealTypeData = readChartData("topMealTypeData");

    const chartTheme = {
        text: "#1f1a17",
        muted: "#7c6d62",
        grid: "rgba(31, 26, 23, 0.10)",
        tooltipBg: "#1f1a17",

        dark: "#1f1a17",
        darkSoft: "#3b302a",
        orange: "#f97316",
        orangeDark: "#c2410c",
        orangeSoft: "rgba(249, 115, 22, 0.18)",
        gold: "#facc15",
        goldSoft: "#f7d774",
        green: "#16a34a",
        greenSoft: "#86efac",
        cream: "#fff7ed",
        amber: "#d97706",
        red: "#dc2626",
        slate: "#64748b"
    };

    Chart.defaults.font.family = "'Segoe UI', system-ui, -apple-system, BlinkMacSystemFont, sans-serif";
    Chart.defaults.color = chartTheme.text;
    Chart.defaults.animation = false;

    function readChartData(scriptId) {
        const script = document.getElementById(scriptId);

        if (!script) {
            return {
                labels: [],
                values: []
            };
        }

        try {
            let parsed = JSON.parse(script.textContent);

            if (typeof parsed === "string") {
                parsed = JSON.parse(parsed);
            }

            return parsed;
        } catch (error) {
            console.error("Could not parse chart data:", scriptId, error);
            return {
                labels: [],
                values: []
            };
        }
    }

    function hasChartData(chartData) {
        return chartData.values && chartData.values.some(function (value) {
            return Number(value) > 0;
        });
    }

    function renderEmptyChart(canvasId, message) {
        const canvas = document.getElementById(canvasId);

        if (!canvas) {
            return;
        }

        const wrapper = canvas.closest(".quality-chart-canvas-wrap");

        if (wrapper) {
            wrapper.innerHTML = `
                <div class="quality-empty-chart quality-empty-chart-professional">
                    <i class="bi bi-bar-chart-line"></i>
                    <strong>No data available yet</strong>
                    <p>${message}</p>
                </div>
            `;
        }
    }

    function professionalTooltip() {
        return {
            backgroundColor: chartTheme.tooltipBg,
            titleColor: "#ffffff",
            bodyColor: "#f8fafc",
            borderColor: "rgba(250, 204, 21, 0.25)",
            borderWidth: 1,
            padding: 12,
            cornerRadius: 8,
            displayColors: true
        };
    }

    function baseScaleOptions(indexAxis) {
        return {
            x: {
                grid: {
                    display: indexAxis === "y",
                    color: chartTheme.grid,
                    drawBorder: false
                },
                border: {
                    display: false
                },
                ticks: {
                    color: chartTheme.muted,
                    font: {
                        size: 11,
                        weight: "650"
                    },
                    maxRotation: indexAxis === "y" ? 0 : 35,
                    minRotation: 0
                }
            },
            y: {
                beginAtZero: true,
                grid: {
                    display: indexAxis !== "y",
                    color: chartTheme.grid,
                    drawBorder: false
                },
                border: {
                    display: false
                },
                ticks: {
                    precision: 0,
                    color: chartTheme.muted,
                    font: {
                        size: 11,
                        weight: "650"
                    }
                }
            }
        };
    }

    function createScoreVerticalBarChart() {
        const canvas = document.getElementById("scoreDistributionChart");

        if (!canvas) {
            return;
        }

        if (!hasChartData(scoreDistributionData)) {
            renderEmptyChart(
                "scoreDistributionChart",
                "More validation records are needed before this chart becomes useful."
            );
            return;
        }

        new Chart(canvas, {
            type: "bar",
            data: {
                labels: scoreDistributionData.labels,
                datasets: [
                    {
                        label: "Recipes",
                        data: scoreDistributionData.values,
                        backgroundColor: [
                            chartTheme.green,
                            chartTheme.gold,
                            chartTheme.orange,
                            chartTheme.red
                        ],
                        borderColor: [
                            chartTheme.green,
                            chartTheme.gold,
                            chartTheme.orange,
                            chartTheme.red
                        ],
                        borderWidth: 1,
                        borderRadius: 4,
                        borderSkipped: false,
                        barThickness: 38,
                        maxBarThickness: 42
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: professionalTooltip()
                },
                scales: baseScaleOptions("x")
            }
        });
    }

    function createRiskDoughnutChart() {
        const canvas = document.getElementById("riskLevelChart");

        if (!canvas) {
            return;
        }

        if (!hasChartData(riskLevelData)) {
            renderEmptyChart(
                "riskLevelChart",
                "Risk information will appear once recipes contain validation evidence."
            );
            return;
        }

        new Chart(canvas, {
            type: "doughnut",
            data: {
                labels: riskLevelData.labels,
                datasets: [
                    {
                        label: "Recipes",
                        data: riskLevelData.values,
                        backgroundColor: [
                            chartTheme.green,
                            chartTheme.gold,
                            chartTheme.orange,
                            chartTheme.darkSoft
                        ],
                        borderColor: "#ffffff",
                        borderWidth: 3,
                        hoverOffset: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "70%",
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: {
                            usePointStyle: true,
                            pointStyle: "circle",
                            boxWidth: 7,
                            boxHeight: 7,
                            color: chartTheme.muted,
                            padding: 14,
                            font: {
                                size: 11,
                                weight: "650"
                            }
                        }
                    },
                    tooltip: professionalTooltip()
                }
            }
        });
    }

    function createGenerationLineChart() {
        const canvas = document.getElementById("recipeTrendChart");

        if (!canvas) {
            return;
        }

        if (!hasChartData(recipeTrendData)) {
            renderEmptyChart(
                "recipeTrendChart",
                "AI recipe generation activity will appear here after more usage."
            );
            return;
        }

        new Chart(canvas, {
            type: "line",
            data: {
                labels: recipeTrendData.labels,
                datasets: [
                    {
                        label: "AI recipes",
                        data: recipeTrendData.values,
                        borderColor: chartTheme.orange,
                        backgroundColor: chartTheme.orangeSoft,
                        pointBackgroundColor: chartTheme.orange,
                        pointBorderColor: "#ffffff",
                        pointBorderWidth: 2,
                        pointRadius: 4,
                        pointHoverRadius: 5,
                        borderWidth: 2.6,
                        tension: 0.25,
                        fill: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: professionalTooltip()
                },
                scales: baseScaleOptions("x")
            }
        });
    }

    function createValidationHorizontalBarChart() {
        const canvas = document.getElementById("validationHealthChart");

        if (!canvas) {
            return;
        }

        if (!hasChartData(validationHealthData)) {
            renderEmptyChart(
                "validationHealthChart",
                "Validation process data will appear once recipes are checked."
            );
            return;
        }

        new Chart(canvas, {
            type: "bar",
            data: {
                labels: validationHealthData.labels,
                datasets: [
                    {
                        label: "Records",
                        data: validationHealthData.values,
                        backgroundColor: chartTheme.orange,
                        borderColor: chartTheme.orangeDark,
                        borderWidth: 1,
                        borderRadius: 4,
                        borderSkipped: false,
                        barThickness: 18,
                        maxBarThickness: 24
                    }
                ]
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: professionalTooltip()
                },
                scales: baseScaleOptions("y")
            }
        });
    }

    function createTopCuisinePieChart() {
        const canvas = document.getElementById("topCuisineChart");

        if (!canvas) {
            return;
        }

        if (!hasChartData(topCuisineData)) {
            renderEmptyChart(
                "topCuisineChart",
                "Cuisine analytics will appear after more AI recipes are saved."
            );
            return;
        }

        new Chart(canvas, {
            type: "pie",
            data: {
                labels: topCuisineData.labels,
                datasets: [
                    {
                        label: "Recipes",
                        data: topCuisineData.values,
                        backgroundColor: [
                            chartTheme.orange,
                            chartTheme.gold,
                            chartTheme.green,
                            chartTheme.darkSoft,
                            chartTheme.amber,
                            chartTheme.greenSoft
                        ],
                        borderColor: "#ffffff",
                        borderWidth: 3,
                        hoverOffset: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: {
                            usePointStyle: true,
                            pointStyle: "rect",
                            boxWidth: 18,
                            boxHeight: 8,
                            color: chartTheme.muted,
                            padding: 12,
                            font: {
                                size: 11,
                                weight: "650"
                            }
                        }
                    },
                    tooltip: professionalTooltip()
                }
            }
        });
    }

    function createTopMealTypeCompactBarChart() {
        const canvas = document.getElementById("topMealTypeChart");

        if (!canvas) {
            return;
        }

        if (!hasChartData(topMealTypeData)) {
            renderEmptyChart(
                "topMealTypeChart",
                "Meal type analytics will appear after more AI recipes are saved."
            );
            return;
        }

        new Chart(canvas, {
            type: "bar",
            data: {
                labels: topMealTypeData.labels,
                datasets: [
                    {
                        label: "Recipes",
                        data: topMealTypeData.values,
                        backgroundColor: chartTheme.gold,
                        borderColor: chartTheme.orange,
                        borderWidth: 1.2,
                        borderRadius: 4,
                        borderSkipped: false,
                        barThickness: 34,
                        maxBarThickness: 38
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: professionalTooltip()
                },
                scales: baseScaleOptions("x")
            }
        });
    }

    createScoreVerticalBarChart();
    createRiskDoughnutChart();
    createGenerationLineChart();
    createValidationHorizontalBarChart();
    createTopCuisinePieChart();
    createTopMealTypeCompactBarChart();
});