/* netmap front-end: render the topology with Cytoscape and overlay live status. */
(function () {
  "use strict";

  var REFRESH_MS = 20000;
  var LS_POS = "netmap-pos-v2";
  var LS_THEME = "netmap-theme";

  var TYPE_COLOR = {
    internet: "#f5a623", wan: "#f5a623", fw: "#e03c3c",
    switch: "#6f8cff", lan: "#6f8cff", vlan: "#6f8cff",
    ap: "#2dd4bf", wifi: "#2dd4bf", server: "#8ea2c9", host: "#e5913a",
    vnet: "#3b9bff", vpn: "#b07cff", tunnel: "#b07cff",
    db: "#34d399", data: "#34d399", remote: "#64b5e6"
  };
  var ICON = {
    internet: "🌐", wan: "🛰", fw: "🔥", switch: "🗄", lan: "🧩",
    vlan: "🏷", ap: "📶", server: "🖥", host: "🧱", vnet: "☁", vpn: "🔒",
    tunnel: "🔒", db: "🗃", remote: "🔑"
  };
  var EDGE_COLOR = {
    wan: "#f5a623", trunk: "#6f8cff", vlan: "#6f8cff", lan: "#6f8cff",
    wifi: "#2dd4bf", vpn: "#b07cff", peer: "#3b9bff", vnet: "#3b9bff",
    data: "#34d399", remote: "#64b5e6", host: "#e5913a"
  };

  function cssVar(n) {
    return getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  }
  function statusColor(s) {
    return cssVar("--" + (s || "unknown")) || "#64748b";
  }

  var cy = null;
  var lastStatus = {};      // id -> status (to detect changes)
  var lastOk = 0;

  function loadPos() {
    try { return JSON.parse(localStorage.getItem(LS_POS)) || {}; }
    catch (e) { return {}; }
  }
  function savePos() {
    var m = {};
    cy.nodes("[!isZone]").forEach(function (n) {
      var p = n.position(); m[n.id()] = { x: Math.round(p.x), y: Math.round(p.y) };
    });
    try { localStorage.setItem(LS_POS, JSON.stringify(m)); } catch (e) {}
  }

  function buildElements(data) {
    var els = [];
    var zoneLabel = {};
    (data.zones || []).forEach(function (z) { zoneLabel[z.id] = z.label; });

    // zone parents
    var zones = {};
    data.nodes.forEach(function (n) { zones[n.zone] = true; });
    Object.keys(zones).forEach(function (z) {
      els.push({ data: { id: "Z_" + z, label: zoneLabel[z] || z, isZone: 1 } });
    });

    var saved = loadPos();
    data.nodes.forEach(function (n) {
      var icon = ICON[n.type] || "●";
      els.push({
        data: {
          id: n.id, parent: "Z_" + n.zone, label: n.label, sub: n.sub || "",
          type: n.type, status: n.status || "unknown", icon: icon,
          typeColor: TYPE_COLOR[n.type] || "#8ea2c9",
          statusColor: statusColor(n.status),
          disp: icon + "  " + n.label + (n.sub ? "\n" + n.sub : "")
        },
        position: saved[n.id] ? { x: saved[n.id].x, y: saved[n.id].y }
                              : { x: n.x, y: n.y }
      });
    });
    data.edges.forEach(function (e) {
      els.push({
        data: {
          id: e.id, source: e.source, target: e.target,
          type: e.type, label: e.label || "", status: e.status || "unknown",
          edgeColor: EDGE_COLOR[e.type] || "#6f8cff",
          dashed: (e.type === "vpn" || e.type === "peer") ? "1" : "0"
        }
      });
    });
    return els;
  }

  function stylesheet() {
    var ink = cssVar("--ink"), muted = cssVar("--muted"),
        line = cssVar("--line"), panel = cssVar("--panel");
    return [
      {
        selector: "node[?isZone]",
        style: {
          "shape": "round-rectangle", "background-opacity": 0.05,
          "background-color": "#7d9bd6", "border-width": 1.2,
          "border-color": line, "border-style": "dashed",
          "label": "data(label)", "font-family": "Space Grotesk",
          "font-size": "13px", "font-weight": 700, "color": muted,
          "text-valign": "top", "text-halign": "center",
          "text-margin-y": 6, "padding": "26px"
        }
      },
      {
        selector: "node[!isZone]",
        style: {
          "shape": "round-rectangle", "width": "label", "height": "label",
          "padding": "11px", "background-color": "data(typeColor)",
          "background-opacity": 0.17, "border-width": 3,
          "border-color": "data(statusColor)",
          "label": "data(disp)", "text-wrap": "wrap", "text-max-width": "120px",
          "text-valign": "center", "text-halign": "center",
          "font-family": "Inter", "font-size": "11px", "line-height": 1.3,
          "color": ink, "font-weight": 500,
          "overlay-opacity": 0, "transition-property": "border-color",
          "transition-duration": "0.25s"
        }
      },
      { selector: "node[!isZone]:selected",
        style: { "border-width": 4, "border-color": cssVar("--accent") } },
      {
        selector: "edge",
        style: {
          "width": 1.8, "line-color": "data(edgeColor)", "opacity": 0.8,
          "curve-style": "bezier", "control-point-step-size": 45,
          "target-arrow-shape": "none",
          "label": "data(label)", "font-family": "JetBrains Mono",
          "font-size": "9px", "color": muted,
          "text-background-color": panel, "text-background-opacity": 0.9,
          "text-background-padding": 2, "text-background-shape": "round-rectangle"
        }
      },
      { selector: 'edge[dashed = "1"]',
        style: { "line-style": "dashed" } },
      { selector: 'edge[status = "down"]',
        style: { "line-color": cssVar("--down"), "line-style": "dashed", "opacity": 0.8 } }
    ];
  }

  function decorate(data) {
    // precompute per-element colors used by the stylesheet mappers
    cy.batch(function () {
      cy.nodes("[!isZone]").forEach(function (n) {
        var t = n.data("type");
        n.data("typeColor", TYPE_COLOR[t] || "#8ea2c9");
        n.data("statusColor", statusColor(n.data("status")));
        n.data("disp", (n.data("icon") + "  " + n.data("label")) +
                       (n.data("sub") ? "\n" + n.data("sub") : ""));
      });
      cy.edges().forEach(function (e) {
        var t = e.data("type");
        e.data("edgeColor", EDGE_COLOR[t] || "#6f8cff");
        e.data("dashed", (t === "vpn" || t === "peer") ? "1" : "0");
      });
    });
  }

  function render(data) {
    cy = cytoscape({
      container: document.getElementById("cy"),
      elements: buildElements(data),
      style: stylesheet(),
      layout: { name: "preset", fit: true, padding: 60 },
      wheelSensitivity: 0.2,
      minZoom: 0.2, maxZoom: 2.5
    });
    decorate(data);
    cy.fit(undefined, 60);

    cy.on("tap", "node[!isZone]", function (ev) { openPanel(ev.target); });
    cy.on("tap", function (ev) { if (ev.target === cy) closePanel(); });
    cy.on("dragfree", "node[!isZone]", savePos);

    (data.nodes || []).forEach(function (n) { lastStatus[n.id] = n.status; });
    updateMeta(data);
  }

  function applyLive(data) {
    if (!cy) { render(data); return; }
    cy.batch(function () {
      data.nodes.forEach(function (n) {
        var ele = cy.getElementById(n.id);
        if (!ele || ele.empty()) return;
        var prev = lastStatus[n.id];
        if (prev !== n.status) {
          ele.data("status", n.status);
          ele.data("statusColor", statusColor(n.status));
          flash(ele);
        }
        lastStatus[n.id] = n.status;
      });
      data.edges.forEach(function (e) {
        var ele = cy.getElementById(e.id);
        if (ele && !ele.empty()) ele.data("status", e.status);
      });
    });
    updateMeta(data);
  }

  function flash(ele) {
    ele.stop();
    ele.animate({ style: { "border-width": 8 } }, { duration: 260 })
       .animate({ style: { "border-width": 3 } }, { duration: 700 });
  }

  /* ---- detail panel ---- */
  function openPanel(node) {
    var p = document.getElementById("panel");
    document.getElementById("pIco").textContent = node.data("icon");
    document.getElementById("pTitle").textContent = node.data("label");
    var st = node.data("status");
    var badge = document.getElementById("pStatus");
    var map = { up: "ปกติ (up)", warn: "เฝ้าระวัง", down: "ขัดข้อง (down)", unknown: "ไม่ทราบ" };
    badge.textContent = map[st] || st;
    badge.className = "panel-badge " + st;
    var body = document.getElementById("pBody");
    body.innerHTML = "";
    var rows = [["ชนิด", node.data("type")], ["รายละเอียด", node.data("sub") || "—"],
                ["โซน", (node.parent().data("label") || "—")]];
    rows.forEach(function (r) {
      var dt = document.createElement("dt"); dt.textContent = r[0];
      var dd = document.createElement("dd"); dd.textContent = r[1];
      body.appendChild(dt); body.appendChild(dd);
    });
    p.hidden = false;
  }
  function closePanel() { document.getElementById("panel").hidden = true; cy.$(":selected").unselect(); }

  function updateMeta(data) {
    var m = data.meta || {};
    var c = m.counts || {};
    document.getElementById("meta").innerHTML =
      "ที่มา: " + (m.source || "—") + "<br>" +
      "อัปเดต: " + (m.tsLocal || "—") + " (BKK)<br>" +
      "ปกติ " + (c.up || 0) + " · เฝ้าระวัง " + (c.warn || 0) +
      " · ขัดข้อง " + (c.down || 0);
    lastOk = Date.now();
    setLive(true);
  }
  function setLive(ok) {
    var el = document.getElementById("live");
    if (ok) { el.classList.remove("stale"); el.firstChild.nextSibling; }
    else { el.classList.add("stale"); }
  }

  /* ---- data fetch ---- */
  function fetchTopo(force) {
    var url = "/api/topology";
    var opts = {};
    var chain = force
      ? fetch("/api/refresh", { method: "POST" }).then(function () { return fetch(url); })
      : fetch(url, opts);
    return chain.then(function (r) { return r.json(); })
      .then(function (data) { applyLive(data); })
      .catch(function (e) { console.warn("fetch failed", e); setLive(false); });
  }

  /* ---- controls ---- */
  function initTheme() {
    try {
      var t = localStorage.getItem(LS_THEME);
      if (t) document.documentElement.setAttribute("data-theme", t);
    } catch (e) {}
  }
  document.getElementById("btnTheme").addEventListener("click", function () {
    var cur = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
    var next = cur === "light" ? "dark" : "light";
    if (next === "light") document.documentElement.setAttribute("data-theme", "light");
    else document.documentElement.removeAttribute("data-theme");
    try { localStorage.setItem(LS_THEME, next); } catch (e) {}
    if (cy) { cy.style(stylesheet()); decorate({}); }
  });
  document.getElementById("btnRefresh").addEventListener("click", function () { fetchTopo(true); });
  document.getElementById("btnFit").addEventListener("click", function () { if (cy) cy.fit(undefined, 60); });
  document.getElementById("btnReset").addEventListener("click", function () {
    try { localStorage.removeItem(LS_POS); } catch (e) {}
    location.reload();
  });
  document.getElementById("panelX").addEventListener("click", closePanel);

  /* ---- boot ---- */
  initTheme();
  fetchTopo(false).then(function () {
    setInterval(function () { fetchTopo(false); }, REFRESH_MS);
    setInterval(function () { if (Date.now() - lastOk > REFRESH_MS * 2.5) setLive(false); }, 5000);
  });
})();
