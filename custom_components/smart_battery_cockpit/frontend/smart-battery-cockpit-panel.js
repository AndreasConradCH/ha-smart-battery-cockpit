/**
 * Smart Battery Cockpit - Native Home Assistant Custom Panel Web Component
 * Communicates natively via hass.callWS() (zero hardcoded tokens or URLs).
 */

class SmartBatteryCockpitPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._data = null;
    this._activeTab = "devices";
    this._search = "";
    this._roomFilter = "";
    this._typeFilter = "";
    this._initialized = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._initialized = true;
      this._renderShell();
      this._loadData();
    }
  }

  _pctColor(pct) {
    if (pct === null || pct === undefined) return "#64748b";
    if (pct <= 15) return "#ef4444";
    if (pct <= 30) return "#f59e0b";
    return "#22c55e";
  }

  _showToast(msg, bg = "#0284c7") {
    const t = this.shadowRoot.getElementById("toast");
    if (!t) return;
    t.textContent = msg;
    t.style.background = bg;
    t.style.display = "block";
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      t.style.display = "none";
    }, 3200);
  }

  async _loadData() {
    if (!this._hass) return;
    try {
      this._data = await this._hass.callWS({ type: "smart_battery_cockpit/get_data" });
      this._updateUI();
    } catch (err) {
      console.error("Smart Battery Cockpit load error:", err);
      this._showToast("Error loading battery data: " + (err.message || err), "#dc2626");
    }
  }

  async _triggerRoundtrip() {
    if (!this._hass) return;
    try {
      this._showToast("🔄 Running round-trip across all sensors...");
      this._data = await this._hass.callWS({ type: "smart_battery_cockpit/roundtrip" });
      this._updateUI();
      this._showToast("✅ Round-trip completed & SQLite DB updated!", "#16a34a");
    } catch (err) {
      this._showToast("Round-trip error: " + (err.message || err), "#dc2626");
    }
  }

  async _confirmSwap(entityId, friendlyName, oldPct, newPct) {
    if (!this._hass) return;
    try {
      this._showToast(`Saving battery swap for ${friendlyName}...`);
      this._data = await this._hass.callWS({
        type: "smart_battery_cockpit/confirm_swap",
        entity_id: entityId,
        old_pct: oldPct ?? 10,
        new_pct: newPct ?? 100,
      });
      this._updateUI();
      this._showToast(`✅ Battery swap saved for ${friendlyName}!`, "#16a34a");
    } catch (err) {
      this._showToast("Error: " + (err.message || err), "#dc2626");
    }
  }

  async _dismissSwap(entityId, friendlyName) {
    if (!this._hass) return;
    try {
      this._data = await this._hass.callWS({
        type: "smart_battery_cockpit/dismiss_swap",
        entity_id: entityId,
      });
      this._updateUI();
      this._showToast(`Dismissed false alarm for ${friendlyName}.`, "#64748b");
    } catch (err) {
      this._showToast("Error: " + (err.message || err), "#dc2626");
    }
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100vh;
          background: #0f172a;
          color: #f8fafc;
          font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
          padding: 20px;
          box-sizing: border-box;
        }
        * { box-sizing: border-box; }
        .container { max-width: 1400px; margin: 0 auto; }
        header {
          display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 16px;
          padding: 20px 24px;
          background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
          border: 1px solid #334155; border-radius: 16px; margin-bottom: 20px;
        }
        header h1 { margin: 0; font-size: 1.45rem; }
        .sub { color: #94a3b8; font-size: 0.88rem; margin-top: 4px; }
        .btn {
          display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px;
          border-radius: 10px; border: 1px solid #334155; background: #1e293b; color: #f8fafc;
          font-weight: 600; font-size: 0.86rem; cursor: pointer;
        }
        .btn:hover { background: #263449; border-color: #38bdf8; }
        .btn-primary { background: #0284c7; border-color: #38bdf8; }
        .btn-success { background: #16a34a; border-color: #22c55e; }
        .btn-danger { background: #dc2626; border-color: #ef4444; }
        .btn-sm { padding: 5px 10px; font-size: 0.78rem; border-radius: 8px; }
        .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin-bottom: 18px; }
        .kpi-card { background: #1e293b; border: 1px solid #334155; border-radius: 14px; padding: 16px 20px; }
        .kpi-label { color: #94a3b8; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; }
        .kpi-val { font-size: 1.85rem; font-weight: 700; margin-top: 4px; }
        .kpi-sub { font-size: 0.8rem; color: #94a3b8; margin-top: 4px; }
        .banner { background: rgba(245,158,11,0.12); border: 1px solid #f59e0b; border-radius: 14px; padding: 16px 20px; margin-bottom: 18px; display: none; }
        .banner-red { background: rgba(239,68,68,0.12); border-color: #ef4444; }
        .banner h3 { margin: 0 0 10px 0; font-size: 1rem; }
        .pending-item { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; padding: 10px 14px; background: rgba(15,23,42,0.6); border-radius: 10px; margin-top: 8px; }
        .toolbar { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 16px; }
        .tabs { display: flex; gap: 8px; flex-wrap: wrap; }
        .tab { padding: 8px 16px; border-radius: 10px; background: #1e293b; border: 1px solid #334155; color: #94a3b8; cursor: pointer; font-weight: 600; font-size: 0.88rem; }
        .tab.active { background: #38bdf8; color: #0f172a; border-color: #38bdf8; }
        .filters { display: flex; gap: 10px; flex-wrap: wrap; }
        input, select { background: #1e293b; border: 1px solid #334155; color: #f8fafc; padding: 8px 12px; border-radius: 10px; font-size: 0.86rem; }
        .table-wrap { background: #1e293b; border: 1px solid #334155; border-radius: 16px; overflow-x: auto; margin-bottom: 24px; }
        table { width: 100%; border-collapse: collapse; text-align: left; }
        th, td { padding: 12px 14px; border-bottom: 1px solid #334155; font-size: 0.88rem; }
        th { background: rgba(15,23,42,0.5); color: #94a3b8; font-weight: 600; font-size: 0.78rem; text-transform: uppercase; }
        tr:hover td { background: rgba(255,255,255,0.02); }
        .badge { display: inline-block; padding: 3px 9px; border-radius: 999px; font-size: 0.76rem; font-weight: 600; background: rgba(56,189,248,0.15); color: #38bdf8; }
        .badge-room { background: rgba(168,85,247,0.15); color: #c084fc; }
        .pct-bar-wrap { display: flex; align-items: center; gap: 10px; min-width: 125px; }
        .pct-bar { flex: 1; height: 8px; background: #0f172a; border-radius: 999px; overflow: hidden; }
        .pct-fill { height: 100%; border-radius: 999px; }
        .spark-clickable { cursor: pointer; padding: 4px 8px; border-radius: 8px; display: inline-flex; align-items: center; gap: 6px; }
        .spark-clickable:hover { background: rgba(56,189,248,0.16); }
        .spark { display: inline-flex; align-items: flex-end; gap: 2px; height: 22px; }
        .spark-bar { width: 5px; border-radius: 2px 2px 0 0; opacity: 0.88; }
        .type-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 14px; }
        .type-card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 14px 16px; display: flex; justify-content: space-between; align-items: center; }
        .modal-backdrop { position: fixed; inset: 0; background: rgba(2,6,23,0.78); backdrop-filter: blur(5px); display: none; align-items: center; justify-content: center; padding: 20px; z-index: 1000; }
        .modal-backdrop.open { display: flex; }
        .modal-box { background: #1e293b; border: 1px solid #334155; border-radius: 18px; width: 100%; max-width: 860px; padding: 24px; box-shadow: 0 25px 60px rgba(0,0,0,0.6); }
        .modal-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 16px; }
        .modal-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 18px; }
        .modal-kpi { background: #0f172a; border: 1px solid #334155; border-radius: 10px; padding: 10px 14px; }
        .modal-kpi .lbl { font-size: 0.74rem; color: #94a3b8; text-transform: uppercase; }
        .modal-kpi .val { font-size: 1.2rem; font-weight: 700; margin-top: 2px; }
        .chart-wrap { background: #0f172a; border: 1px solid #334155; border-radius: 14px; padding: 14px; position: relative; }
        .chart-tooltip { position: absolute; pointer-events: none; background: rgba(15,23,42,0.96); border: 1px solid #38bdf8; border-radius: 10px; padding: 8px 12px; font-size: 0.82rem; display: none; z-index: 20; white-space: nowrap; }
        .chart-legend { display: flex; gap: 18px; flex-wrap: wrap; font-size: 0.8rem; color: #94a3b8; margin-top: 10px; }
        .legend-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
        .toast { position: fixed; bottom: 24px; right: 24px; background: #0284c7; color: #fff; padding: 12px 20px; border-radius: 12px; font-weight: 600; display: none; z-index: 1200; }
      </style>

      <div class="container">
        <header>
          <div>
            <h1>🔋 Smart Battery Cockpit & Lifecycle DB</h1>
            <div class="sub" id="lastUpdated">Loading SQLite database snapshot...</div>
          </div>
          <div style="display:flex;gap:10px;flex-wrap:wrap;">
            <button class="btn btn-primary" id="btnRoundtrip">🔄 Run Round-Trip Now</button>
            <button class="btn" id="btnRefresh">↻ Refresh</button>
          </div>
        </header>

        <div class="kpi-grid">
          <div class="kpi-card"><div class="kpi-label">Tracked Devices</div><div class="kpi-val" id="kpiTotal">-</div><div class="kpi-sub">SQLite Long-Term DB</div></div>
          <div class="kpi-card"><div class="kpi-label">Low Batteries (≤ 20%)</div><div class="kpi-val" id="kpiLow" style="color:#f59e0b">-</div><div class="kpi-sub">Replace soon</div></div>
          <div class="kpi-card"><div class="kpi-label">Pending Confirmations</div><div class="kpi-val" id="kpiPending" style="color:#38bdf8">-</div><div class="kpi-sub">Rapid jump detected</div></div>
          <div class="kpi-card"><div class="kpi-label">Drain Anomalies</div><div class="kpi-val" id="kpiAnomaly" style="color:#ef4444">-</div><div class="kpi-sub">High daily drain</div></div>
        </div>

        <div id="pendingBanner" class="banner"><h3>❓ Battery Swap Detected – Please Confirm:</h3><div id="pendingList"></div></div>
        <div id="anomalyBanner" class="banner banner-red"><h3>🚨 Abnormally High Battery Drain Detected:</h3><div id="anomalyList"></div></div>

        <div class="toolbar">
          <div class="tabs">
            <div class="tab active" data-tab="devices">📊 All Devices (<span id="tabCountDevices">0</span>)</div>
            <div class="tab" data-tab="history">📓 Swap Logbook (<span id="tabCountHistory">0</span>)</div>
            <div class="tab" data-tab="inventory">🧰 Battery Inventory</div>
          </div>
          <div class="filters" id="deviceFilters">
            <input type="text" id="searchInput" placeholder="🔍 Search device or room..." />
            <select id="roomFilter"><option value="">All Rooms</option></select>
            <select id="typeFilter"><option value="">All Battery Types</option></select>
          </div>
        </div>

        <div id="viewDevices" class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Device</th><th>Room</th><th>Type</th><th>Charge</th><th>Voltage</th>
                <th>Trend (Ø 7d / 24h)</th><th>History (📈 Click)</th><th>Last Swap / Runtime</th><th>Action</th>
              </tr>
            </thead>
            <tbody id="devicesBody"></tbody>
          </table>
        </div>

        <div id="viewHistory" class="table-wrap" style="display:none;">
          <table>
            <thead><tr><th>Date</th><th>Device</th><th>Type</th><th>Jump (Old → New)</th><th>Previous Cycle</th><th>Notes</th></tr></thead>
            <tbody id="historyBody"></tbody>
          </table>
        </div>

        <div id="viewInventory" style="display:none;"><div class="type-grid" id="inventoryGrid"></div></div>
      </div>

      <div class="modal-backdrop" id="chartModal">
        <div class="modal-box">
          <div class="modal-header">
            <div><h2 id="modalTitle" style="margin:0;font-size:1.3rem;">📈 Battery History</h2><div id="modalSub" class="sub"></div></div>
            <button class="btn btn-sm" id="btnCloseModal">✕ Close</button>
          </div>
          <div class="modal-kpis" id="modalKpis"></div>
          <div class="chart-wrap" id="chartWrap">
            <div class="chart-tooltip" id="chartTooltip"></div>
            <svg id="lineChartSvg" viewBox="0 0 780 300" style="width:100%;height:auto;display:block;"></svg>
          </div>
          <div class="chart-legend" id="chartLegend"></div>
        </div>
      </div>

      <div class="toast" id="toast"></div>
    `;

    const sr = this.shadowRoot;
    sr.getElementById("btnRoundtrip").addEventListener("click", () => this._triggerRoundtrip());
    sr.getElementById("btnRefresh").addEventListener("click", () => this._loadData());
    sr.getElementById("btnCloseModal").addEventListener("click", () => sr.getElementById("chartModal").classList.remove("open"));
    sr.getElementById("chartModal").addEventListener("click", (e) => {
      if (e.target.id === "chartModal") sr.getElementById("chartModal").classList.remove("open");
    });
    sr.getElementById("searchInput").addEventListener("input", (e) => {
      this._search = e.target.value.toLowerCase();
      this._renderDevices();
    });
    sr.getElementById("roomFilter").addEventListener("change", (e) => {
      this._roomFilter = e.target.value;
      this._renderDevices();
    });
    sr.getElementById("typeFilter").addEventListener("change", (e) => {
      this._typeFilter = e.target.value;
      this._renderDevices();
    });
    sr.querySelectorAll(".tab").forEach((t) => {
      t.addEventListener("click", () => {
        sr.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
        t.classList.add("active");
        this._activeTab = t.dataset.tab;
        sr.getElementById("viewDevices").style.display = this._activeTab === "devices" ? "block" : "none";
        sr.getElementById("deviceFilters").style.display = this._activeTab === "devices" ? "flex" : "none";
        sr.getElementById("viewHistory").style.display = this._activeTab === "history" ? "block" : "none";
        sr.getElementById("viewInventory").style.display = this._activeTab === "inventory" ? "block" : "none";
      });
    });
  }

  _updateUI() {
    const d = this._data;
    if (!d) return;
    const sr = this.shadowRoot;

    sr.getElementById("lastUpdated").textContent = `Last Round-Trip Snapshot: ${d.generated_at} · SQLite DB`;
    sr.getElementById("kpiTotal").textContent = d.total_devices;
    sr.getElementById("kpiLow").textContent = d.low_battery_count;
    sr.getElementById("kpiPending").textContent = d.pending_confirmations_count;
    sr.getElementById("kpiAnomaly").textContent = d.anomaly_count;
    sr.getElementById("tabCountDevices").textContent = d.total_devices;
    sr.getElementById("tabCountHistory").textContent = d.swap_history.length;

    const rf = sr.getElementById("roomFilter");
    if (rf.options.length <= 1) {
      [...new Set(d.devices.map((x) => x.room).filter(Boolean))].sort().forEach((r) => rf.add(new Option(r, r)));
    }
    const tf = sr.getElementById("typeFilter");
    if (tf.options.length <= 1) {
      [...new Set(d.devices.map((x) => x.battery_type).filter(Boolean))].sort().forEach((t) => tf.add(new Option(t, t)));
    }

    // Pending banner
    const pb = sr.getElementById("pendingBanner");
    const pl = sr.getElementById("pendingList");
    if (d.pending_confirmations && d.pending_confirmations.length > 0) {
      pb.style.display = "block";
      pl.innerHTML = d.pending_confirmations
        .map(
          (p) => `
          <div class="pending-item">
            <div><strong>${p.friendly_name}</strong> (${p.room}, <span class="badge">${p.battery_type}</span>) jumped from
              <strong style="color:#ef4444">${Math.round(p.pending_swap_from || 0)}%</strong> to
              <strong style="color:#22c55e">${Math.round(p.pending_swap_to || 100)}%</strong>. Did you replace the battery?</div>
            <div style="display:flex;gap:8px;">
              <button class="btn btn-sm btn-success" data-confirm="${p.entity_id}">✅ Yes, replaced</button>
              <button class="btn btn-sm btn-danger" data-dismiss="${p.entity_id}">❌ No, false alarm</button>
            </div>
          </div>`
        )
        .join("");
      pl.querySelectorAll("[data-confirm]").forEach((btn) => {
        const p = d.pending_confirmations.find((x) => x.entity_id === btn.dataset.confirm);
        btn.addEventListener("click", () => this._confirmSwap(p.entity_id, p.friendly_name, p.pending_swap_from, p.pending_swap_to));
      });
      pl.querySelectorAll("[data-dismiss]").forEach((btn) => {
        const p = d.pending_confirmations.find((x) => x.entity_id === btn.dataset.dismiss);
        btn.addEventListener("click", () => this._dismissSwap(p.entity_id, p.friendly_name));
      });
    } else {
      pb.style.display = "none";
    }

    // Anomaly banner
    const ab = sr.getElementById("anomalyBanner");
    if (d.anomalies && d.anomalies.length > 0) {
      ab.style.display = "block";
      sr.getElementById("anomalyList").innerHTML = d.anomalies
        .map(
          (a) =>
            `<div class="pending-item"><div>⚠️ <strong>${a.friendly_name}</strong> (${a.room}): Ø <strong style="color:#ef4444">${(a.avg_7d_drain || 0).toFixed(1)} %/day</strong> (24h: ${(a.delta_24h || 0).toFixed(1)} %, now ${Math.round(a.last_level || 0)} %)</div></div>`
        )
        .join("");
    } else {
      ab.style.display = "none";
    }

    // History table
    sr.getElementById("historyBody").innerHTML = d.swap_history
      .map(
        (s) => `
        <tr>
          <td><strong>${(s.swapped_at || "").replace("T", " ").substring(0, 16)}</strong></td>
          <td>${s.friendly_name}<div style="font-size:0.74rem;color:#94a3b8"><code>${s.entity_id}</code></div></td>
          <td><span class="badge">${s.battery_type || "-"}</span></td>
          <td><span style="color:#ef4444">${Math.round(s.old_level_pct || 0)}%</span> → <strong style="color:#22c55e">${Math.round(s.new_level_pct || 100)}%</strong></td>
          <td>${s.cycle_days ? `<strong>${s.cycle_days} days</strong>` : `<span style="color:#94a3b8">Initial</span>`}</td>
          <td>${s.notes || ""}</td>
        </tr>`
      )
      .join("");

    // Inventory
    sr.getElementById("inventoryGrid").innerHTML = Object.entries(d.battery_type_summary || {})
      .map(
        ([bt, info]) => `
        <div class="type-card">
          <div><div style="font-weight:700">${bt}</div><div style="font-size:0.8rem;color:#94a3b8">${info.total} devices</div></div>
          <div style="text-align:right"><div style="font-size:1.3rem;font-weight:700;color:${info.low > 0 ? "#f59e0b" : "#22c55e"}">${info.low}</div><div style="font-size:0.74rem;color:#94a3b8">≤ 20%</div></div>
        </div>`
      )
      .join("");

    this._renderDevices();
  }

  _renderDevices() {
    if (!this._data) return;
    const sr = this.shadowRoot;
    const tbody = sr.getElementById("devicesBody");
    const filtered = this._data.devices.filter((d) => {
      if (this._roomFilter && d.room !== this._roomFilter) return false;
      if (this._typeFilter && d.battery_type !== this._typeFilter) return false;
      if (this._search && !`${d.friendly_name} ${d.entity_id} ${d.room} ${d.model}`.toLowerCase().includes(this._search)) return false;
      return true;
    });

    tbody.innerHTML = filtered
      .map((d) => {
        const pct = d.last_level;
        const c = this._pctColor(pct);
        const pctText = pct !== null && pct !== undefined ? `${Math.round(pct)} %` : "Offline";
        const voltText = d.last_voltage_mv ? `${(d.last_voltage_mv / 1000).toFixed(2)} V (${Math.round(d.last_voltage_mv)} mV)` : "-";
        const avg7 = d.avg_7d_drain || 0;
        const d24 = d.delta_24h || 0;
        const avgColor = avg7 <= -3 ? "#ef4444" : avg7 < 0 ? "#f59e0b" : avg7 > 0 ? "#22c55e" : "#94a3b8";
        const avgHtml = `<span style="color:${avgColor};font-weight:600">Ø ${avg7 > 0 ? "+" : ""}${avg7.toFixed(1)} %/d</span>`;
        const subTrend = `<div style="font-size:0.74rem;color:#94a3b8">24h: ${d24 > 0 ? "+" : ""}${d24.toFixed(1)}%${d.est_days_left != null ? ` · ~${d.est_days_left}d left` : ""}</div>`;

        const bars = (d.history || [])
          .slice(-14)
          .map((h) => {
            const hPx = h.battery_pct != null ? Math.max(6, Math.round((h.battery_pct / 100) * 22)) : 4;
            return `<span class="spark-bar" style="height:${hPx}px;background:${this._pctColor(h.battery_pct)}" title="${h.date}: ${h.battery_pct}%"></span>`;
          })
          .join("");

        let swapHtml = `<span style="color:#94a3b8">No swap logged</span>`;
        if (d.last_replaced_at) {
          const dt = d.last_replaced_at.substring(0, 10).split("-").reverse().join(".");
          swapHtml = `<div><strong>${dt}</strong></div><div style="font-size:0.76rem;color:#22c55e">${d.days_since_swap ?? 0}d active</div>`;
        }

        const actionHtml =
          d.days_since_swap === 0
            ? `<span style="color:#22c55e;font-size:0.8rem;font-weight:600;">✅ Logged</span>`
            : `<button class="btn btn-sm" data-swap="${d.entity_id}">🔋 Swap now</button>`;

        return `
          <tr>
            <td style="cursor:pointer" data-chart="${d.entity_id}">
              <div style="font-weight:600">${d.friendly_name}</div>
              <div style="font-size:0.74rem;color:#94a3b8">${d.manufacturer || ""} ${d.model || ""} · <code>${d.entity_id}</code></div>
            </td>
            <td><span class="badge badge-room">${d.room || "Home"}</span></td>
            <td><span class="badge">${d.battery_type || "-"}</span></td>
            <td><div class="pct-bar-wrap"><div class="pct-bar"><div class="pct-fill" style="width:${Math.max(0, Math.min(100, pct || 0))}%;background:${c}"></div></div><strong style="color:${c};min-width:44px;text-align:right">${pctText}</strong></div></td>
            <td>${voltText}</td>
            <td>${avgHtml}${subTrend}</td>
            <td><div class="spark-clickable" data-chart="${d.entity_id}"><div class="spark">${bars}</div><span>📈</span></div></td>
            <td>${swapHtml}</td>
            <td>${actionHtml}</td>
          </tr>`;
      })
      .join("");

    tbody.querySelectorAll("[data-chart]").forEach((el) => {
      el.addEventListener("click", () => this._openChartModal(el.dataset.chart));
    });
    tbody.querySelectorAll("[data-swap]").forEach((btn) => {
      const dev = this._data.devices.find((x) => x.entity_id === btn.dataset.swap);
      btn.addEventListener("click", () => this._confirmSwap(dev.entity_id, dev.friendly_name, dev.last_level ?? 10, 100));
    });
  }

  _openChartModal(entityId) {
    const sr = this.shadowRoot;
    const d = this._data.devices.find((x) => x.entity_id === entityId);
    if (!d) return;

    sr.getElementById("modalTitle").textContent = `📈 ${d.friendly_name}`;
    sr.getElementById("modalSub").textContent = `${d.room || "Home"} · ${d.manufacturer || ""} ${d.model || ""} · ${d.battery_type || "-"} · ${d.entity_id}`;
    const avg7 = d.avg_7d_drain || 0;
    sr.getElementById("modalKpis").innerHTML = `
      <div class="modal-kpi"><div class="lbl">Current</div><div class="val" style="color:${this._pctColor(d.last_level)}">${d.last_level != null ? Math.round(d.last_level) + " %" : "Offline"}</div></div>
      <div class="modal-kpi"><div class="lbl">Voltage</div><div class="val" style="color:#fbbf24">${d.last_voltage_mv ? (d.last_voltage_mv / 1000).toFixed(2) + " V" : "n/a"}</div></div>
      <div class="modal-kpi"><div class="lbl">Ø 7d Trend</div><div class="val" style="color:${avg7 <= -3 ? "#ef4444" : avg7 < 0 ? "#f59e0b" : "#22c55e"}">${avg7 > 0 ? "+" : ""}${avg7.toFixed(2)} %/d</div></div>
      <div class="modal-kpi"><div class="lbl">Est. Remaining</div><div class="val" style="color:#38bdf8">${d.est_days_left != null ? "~" + d.est_days_left + " days" : "Stable"}</div></div>
    `;

    const hist = (d.history || []).filter((h) => h.battery_pct != null);
    const svg = sr.getElementById("lineChartSvg");
    const tooltip = sr.getElementById("chartTooltip");
    tooltip.style.display = "none";

    if (hist.length === 0) {
      svg.innerHTML = `<text x="390" y="150" fill="#94a3b8" text-anchor="middle" font-size="15">No history recorded yet.</text>`;
      sr.getElementById("chartModal").classList.add("open");
      return;
    }

    const W = 780, H = 300, padL = 48, padR = 56, padT = 20, padB = 42;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const xFor = (i) => (hist.length === 1 ? padL + plotW / 2 : padL + (i / (hist.length - 1)) * plotW);
    const yForPct = (p) => padT + plotH - (Math.max(0, Math.min(100, p)) / 100) * plotH;

    const vPts = hist.map((h, i) => ({ i, v: h.voltage_mv })).filter((p) => p.v != null);
    let vMin = 2400, vMax = 3300;
    if (vPts.length > 0) {
      vMin = Math.floor((Math.min(...vPts.map((p) => p.v)) - 80) / 50) * 50;
      vMax = Math.ceil((Math.max(...vPts.map((p) => p.v)) + 80) / 50) * 50;
      if (vMax <= vMin) vMax = vMin + 200;
    }
    const yForV = (v) => padT + plotH - ((v - vMin) / (vMax - vMin)) * plotH;

    let grid = "";
    [0, 25, 50, 75, 100].forEach((val) => {
      const y = yForPct(val);
      grid += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#1e293b" stroke-width="1"/>`;
      grid += `<text x="${padL - 8}" y="${y + 4}" fill="#94a3b8" font-size="11" text-anchor="end">${val}%</text>`;
    });
    if (vPts.length > 0) {
      [vMin, Math.round((vMin + vMax) / 2), vMax].forEach((val) => {
        grid += `<text x="${W - padR + 8}" y="${yForV(val) + 4}" fill="#fbbf24" font-size="10">${(val / 1000).toFixed(2)}V</text>`;
      });
    }

    let xAxis = "";
    const step = Math.max(1, Math.ceil(hist.length / 8));
    hist.forEach((h, i) => {
      if (i % step === 0 || i === hist.length - 1) {
        xAxis += `<text x="${xFor(i)}" y="${H - 14}" fill="#94a3b8" font-size="11" text-anchor="middle">${h.date.substring(5).split("-").reverse().join(".")}</text>`;
      }
    });

    const devSwaps = (this._data.swap_history || []).filter((s) => s.entity_id === entityId).map((s) => s.swapped_at.substring(0, 10));
    let swapLines = "";
    hist.forEach((h, i) => {
      if (devSwaps.includes(h.date)) {
        const x = xFor(i);
        swapLines += `<line x1="${x}" y1="${padT}" x2="${x}" y2="${padT + plotH}" stroke="#22c55e" stroke-width="2" stroke-dasharray="5,4"/>`;
        swapLines += `<text x="${x + 4}" y="${padT + 14}" fill="#22c55e" font-size="10" font-weight="bold">🔋 Swap</text>`;
      }
    });

    const pts = hist.map((h, i) => `${xFor(i).toFixed(1)},${yForPct(h.battery_pct).toFixed(1)}`);
    const linePath = `M ${pts.join(" L ")}`;
    const areaPath = `${linePath} L ${xFor(hist.length - 1).toFixed(1)},${(padT + plotH).toFixed(1)} L ${xFor(0).toFixed(1)},${(padT + plotH).toFixed(1)} Z`;
    const voltPath = vPts.length >= 2 ? `<path d="M ${vPts.map((p) => `${xFor(p.i).toFixed(1)},${yForV(p.v).toFixed(1)}`).join(" L ")}" fill="none" stroke="#fbbf24" stroke-width="2" stroke-dasharray="6,4"/>` : "";

    const dots = hist
      .map((h, i) => {
        const cx = xFor(i).toFixed(1), cy = yForPct(h.battery_pct).toFixed(1);
        return `<circle cx="${cx}" cy="${cy}" r="4.5" fill="${this._pctColor(h.battery_pct)}" stroke="#0f172a" stroke-width="2"/><circle cx="${cx}" cy="${cy}" r="14" fill="transparent" style="cursor:pointer" data-idx="${i}" class="hit"/>`;
      })
      .join("");

    svg.innerHTML = `
      <defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#38bdf8" stop-opacity="0.38"/><stop offset="100%" stop-color="#38bdf8" stop-opacity="0.02"/></linearGradient></defs>
      ${grid}${xAxis}${swapLines}
      <path d="${areaPath}" fill="url(#bg)"/>
      <path d="${linePath}" fill="none" stroke="#38bdf8" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>
      ${voltPath}${dots}
    `;

    const wrap = sr.getElementById("chartWrap");
    svg.querySelectorAll(".hit").forEach((el) => {
      el.addEventListener("mouseenter", (ev) => {
        const h = hist[parseInt(ev.target.dataset.idx, 10)];
        const vStr = h.voltage_mv ? `<br/>⚡ Voltage: <strong>${(h.voltage_mv / 1000).toFixed(3)} V</strong>` : "";
        tooltip.innerHTML = `<strong>📅 ${h.date.split("-").reverse().join(".")}</strong><br/>🔋 Level: <strong style="color:${this._pctColor(h.battery_pct)}">${Math.round(h.battery_pct)} %</strong>${vStr}`;
        tooltip.style.display = "block";
        const r = wrap.getBoundingClientRect(), cr = ev.target.getBoundingClientRect();
        tooltip.style.left = `${Math.max(8, Math.min(r.width - 180, cr.left - r.left + 14))}px`;
        tooltip.style.top = `${Math.max(8, cr.top - r.top - 10)}px`;
      });
      el.addEventListener("mouseleave", () => (tooltip.style.display = "none"));
    });

    sr.getElementById("chartLegend").innerHTML = `
      <span><span class="legend-dot" style="background:#38bdf8"></span>Charge (%)</span>
      ${vPts.length >= 2 ? '<span><span class="legend-dot" style="background:#fbbf24"></span>Voltage (V)</span>' : ""}
      ${devSwaps.length > 0 ? '<span><span class="legend-dot" style="background:#22c55e"></span>Confirmed Battery Swap</span>' : ""}
      <span style="margin-left:auto">${hist.length} days stored in SQLite</span>
    `;
    sr.getElementById("chartModal").classList.add("open");
  }
}

customElements.define("smart-battery-cockpit-panel", SmartBatteryCockpitPanel);
