(function () {
  const state = {
    bars: [],
    signals: [],
    evaluations: [],
    selectedSignalId: null,
    chart: null,
  };

  const $ = (id) => document.getElementById(id);

  function setDefaultTimes() {
    const now = new Date();
    const end = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 7, 0, 0));
    const start = new Date(end.getTime() - 7 * 24 * 60 * 60 * 1000);
    $("fromTime").value = toLocalInput(start);
    $("toTime").value = toLocalInput(end);
  }

  function toLocalInput(date) {
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 16);
  }

  function inputTimeToIso(id) {
    const value = $(id).value;
    if (!value) return "";
    return new Date(value).toISOString();
  }

  function queryBase() {
    const params = new URLSearchParams();
    params.set("symbol", $("symbol").value.trim());
    params.set("timeframe", $("timeframe").value);
    params.set("from_time", inputTimeToIso("fromTime"));
    params.set("to_time", inputTimeToIso("toTime"));
    params.set("data_source_version", $("dataSourceVersion").value.trim());
    params.set("as_of_version", $("asOfVersion").value.trim());
    const direction = $("direction").value;
    if (direction) params.set("direction", direction);
    selectedStrategies().forEach((version) => params.append("strategy_version", version));
    return params;
  }

  function selectedStrategies() {
    return Array.from(document.querySelectorAll("[data-strategy-version]:checked")).map(
      (item) => item.dataset.strategyVersion,
    );
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || response.statusText);
    return payload;
  }

  async function loadStrategies() {
    const payload = await fetchJson("/api/strategies");
    const list = $("strategyList");
    list.innerHTML = "";
    if (!payload.strategies.length) {
      list.innerHTML = '<div class="muted">No persisted signals</div>';
      return;
    }
    payload.strategies.forEach((strategy) => {
      const row = document.createElement("label");
      row.className = "check-row";
      row.innerHTML = `
        <span>
          <strong>${escapeHtml(strategy.strategy_version)}</strong><br />
          <span class="muted">${escapeHtml(strategy.strategy_name)} · ${strategy.sample_count}</span>
        </span>
        <input type="checkbox" checked data-strategy-version="${escapeHtml(strategy.strategy_version)}" />
      `;
      row.querySelector("input").addEventListener("change", refresh);
      list.appendChild(row);
    });
  }

  async function refresh() {
    try {
      const params = queryBase();
      const barsParams = new URLSearchParams(params);
      barsParams.delete("direction");
      barsParams.delete("strategy_version");
      const [barsPayload, signalsPayload] = await Promise.all([
        fetchJson(`/api/bars?${barsParams}`),
        fetchJson(`/api/signals?${params}`),
      ]);
      state.bars = barsPayload.bars;
      state.signals = signalsPayload.signals;
      const signalParams = new URLSearchParams();
      state.signals.forEach((signal) => signalParams.append("signal_id", signal.signal_id));
      state.evaluations = state.signals.length
        ? (await fetchJson(`/api/evaluations?${signalParams}`)).evaluations
        : [];
      renderChart();
      renderSummary();
      renderEvaluations();
    } catch (error) {
      $("summary").textContent = error.message;
      showChartStatus(`加载失败：${error.message}`);
    }
  }

  function renderChart() {
    if (!window.echarts) {
      showChartStatus("ECharts 静态资源加载失败，无法渲染图表。");
      return;
    }
    if (!state.bars.length) {
      if (state.chart) state.chart.clear();
      showChartStatus("当前查询范围没有持久化 K 线数据。请先启动 Shadow Run 或调整标的、时间窗与数据版本。");
      return;
    }
    showChartStatus("");
    if (!state.chart) {
      state.chart = echarts.init($("chart"));
      state.chart.on("click", (params) => {
        if (params.data && params.data.signal_id) {
          selectSignal(params.data.signal_id);
        }
      });
      window.addEventListener("resize", () => state.chart.resize());
    }
    const times = state.bars.map((bar) => bar.market_data_time);
    const candle = state.bars.map((bar) => [
      bar.open_price,
      bar.close_price,
      bar.low_price,
      bar.high_price,
    ]);
    const series = [
      {
        name: "K",
        type: "candlestick",
        data: candle,
        itemStyle: {
          color: "#0f9d58",
          color0: "#d93025",
          borderColor: "#0f9d58",
          borderColor0: "#d93025",
        },
      },
      ...signalSeries(times),
    ];
    state.chart.setOption(
      {
        animation: false,
        legend: { top: 8, type: "scroll" },
        tooltip: { trigger: "axis" },
        grid: { left: 56, right: 24, top: 48, bottom: 72 },
        xAxis: { type: "category", data: times, boundaryGap: true, axisLabel: { hideOverlap: true } },
        yAxis: { scale: true },
        dataZoom: [
          { type: "inside", start: 0, end: 100 },
          { type: "slider", height: 24, bottom: 22 },
        ],
        series,
      },
      true,
    );
  }

  function showChartStatus(message) {
    const status = $("chartStatus");
    status.textContent = message;
    status.hidden = !message;
  }

  function signalSeries(times) {
    const groups = new Map();
    state.signals.forEach((signal) => {
      const key = `${signal.strategy_version} ${signal.direction_label}`;
      if (!groups.has(key)) groups.set(key, []);
      const index = nearestIndex(times, signal.market_data_time);
      if (index >= 0) {
        groups.get(key).push({
          value: [index, signal.reference_price],
          signal_id: signal.signal_id,
          symbol: signal.symbol,
          strategy_version: signal.strategy_version,
          direction_label: signal.direction_label,
        });
      }
    });
    return Array.from(groups.entries()).map(([name, data]) => {
      const direction = name.endsWith("BUY") ? "BUY" : name.endsWith("SELL") ? "SELL" : "HOLD";
      return {
        name,
        type: "scatter",
        data,
        symbolSize: 11,
        itemStyle: { color: colorForDirection(direction) },
      };
    });
  }

  function nearestIndex(times, target) {
    const exact = times.indexOf(target);
    if (exact >= 0) return exact;
    const targetMs = Date.parse(target);
    let best = -1;
    let bestDistance = Infinity;
    times.forEach((time, index) => {
      const distance = Math.abs(Date.parse(time) - targetMs);
      if (distance < bestDistance) {
        best = index;
        bestDistance = distance;
      }
    });
    return best;
  }

  function colorForDirection(direction) {
    if (direction === "BUY") return "#0f9d58";
    if (direction === "SELL") return "#d93025";
    return "#6b7280";
  }

  function renderSummary() {
    const buy = state.signals.filter((item) => item.direction_label === "BUY").length;
    const sell = state.signals.filter((item) => item.direction_label === "SELL").length;
    const hold = state.signals.filter((item) => item.direction_label === "HOLD").length;
    $("summary").textContent = `${state.bars.length} bars · BUY ${buy} · SELL ${sell} · HOLD ${hold}`;
  }

  function selectSignal(signalId) {
    state.selectedSignalId = signalId;
    const signal = state.signals.find((item) => item.signal_id === signalId);
    $("signalDetail").textContent = JSON.stringify(signal || {}, null, 2);
    renderEvaluations();
  }

  function renderEvaluations() {
    const rows = state.selectedSignalId
      ? state.evaluations.filter((item) => item.signal_id === state.selectedSignalId)
      : state.evaluations;
    if (!rows.length) {
      $("evaluationTable").innerHTML = '<div class="muted">No evaluations</div>';
      return;
    }
    $("evaluationTable").innerHTML = `
      <table>
        <thead>
          <tr>
            <th>signal_id</th>
            <th>horizon</th>
            <th>status</th>
            <th>direction_return</th>
            <th>net_return</th>
            <th>MFE</th>
            <th>MAE</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row) => `
                <tr>
                  <td>${escapeHtml(row.signal_id.slice(0, 10))}</td>
                  <td>${row.horizon_seconds}</td>
                  <td>${escapeHtml(row.status)}</td>
                  <td>${formatPct(row.direction_return)}</td>
                  <td>${formatPct(row.net_return)}</td>
                  <td>${formatPct(row.mfe)}</td>
                  <td>${formatPct(row.mae)}</td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    `;
  }

  async function startShadowRun() {
    try {
      const payload = await fetchJson("/api/shadow-runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: $("symbol").value.trim(),
          timeframe: $("timeframe").value,
          from_time: inputTimeToIso("fromTime"),
          to_time: inputTimeToIso("toTime"),
          data_source_version: $("dataSourceVersion").value.trim(),
          as_of_version: $("asOfVersion").value.trim(),
        }),
      });
      renderShadowRuns([payload]);
      setTimeout(loadShadowRuns, 1000);
    } catch (error) {
      $("summary").textContent = error.message;
    }
  }

  async function loadShadowRuns() {
    const payload = await fetchJson("/api/shadow-runs");
    renderShadowRuns(payload.shadow_runs);
    if (payload.shadow_runs.some((run) => ["STARTING", "RUNNING", "STOPPING"].includes(run.status))) {
      setTimeout(loadShadowRuns, 1500);
    }
  }

  function renderShadowRuns(runs) {
    const list = $("shadowRuns");
    if (!runs.length) {
      list.innerHTML = '<div class="muted">No shadow runs</div>';
      return;
    }
    list.innerHTML = "";
    runs
      .slice()
      .reverse()
      .forEach((run) => {
        const row = document.createElement("div");
        row.className = "run-row";
        row.innerHTML = `
          <span>
            <strong>${escapeHtml(run.status)}</strong><br />
            <span class="muted">${escapeHtml(run.run_id)} · bars ${run.bars_seen} · signals ${run.signals_created}</span>
          </span>
          <button type="button" ${["COMPLETED", "FAILED", "STOPPED"].includes(run.status) ? "disabled" : ""}>停止</button>
        `;
        row.querySelector("button").addEventListener("click", async () => {
          await fetchJson(`/api/shadow-runs/${run.run_id}/stop`, { method: "POST" });
          loadShadowRuns();
        });
        list.appendChild(row);
      });
  }

  function formatPct(value) {
    return value === null || value === undefined ? "-" : `${(value * 100).toFixed(2)}%`;
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  $("refreshButton").addEventListener("click", refresh);
  $("startShadowButton").addEventListener("click", startShadowRun);
  setDefaultTimes();
  loadStrategies().then(refresh).catch((error) => {
    $("summary").textContent = error.message;
  });
  loadShadowRuns().catch(() => undefined);
})();
