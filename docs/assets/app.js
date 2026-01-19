/* docs/assets/app.js
 *
 * - Charge les JSON générés par les scripts Python (snapshot + correlations + metadata)
 * - Rend :
 *   1) tableaux temps réel
 *   2) carte Leaflet (voiture + vélo)
 *   3) heatmap Plotly + classement + filtres
 *   4) sélection de fenêtre temporelle (7/14/21/30) via correlations_<days>.json
 */

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fmtNumber(x) {
  if (x === null || x === undefined) return "—";
  if (Number.isFinite(x)) return String(x);
  return String(x);
}

function fmtKm(x) {
  if (x === null || x === undefined) return "—";
  return `${Number(x).toFixed(2)}`;
}

function fmtDateTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("fr-FR");
  } catch {
    return String(iso);
  }
}

async function fetchJson(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Erreur fetch ${path} : ${res.status}`);
  }
  return await res.json();
}

/* =========================
 *  TABLEAUX TEMPS REEL
 * ========================= */
function renderRealtimeTables(snapshot) {
  const carsBody = $("carsTable");
  const bikesBody = $("bikesTable");
  if (!carsBody || !bikesBody) return;

  const cars = Array.isArray(snapshot.cars) ? snapshot.cars : [];
  const bikes = Array.isArray(snapshot.bikes) ? snapshot.bikes : [];

  function rowHtml(name, free, total) {
    return `<tr>
      <td>${escapeHtml(name)}</td>
      <td class="num">${fmtNumber(free)}</td>
      <td class="num">${fmtNumber(total)}</td>
    </tr>`;
  }

  carsBody.innerHTML = cars.map((p) => rowHtml(p.name, p.free, p.total)).join("");
  bikesBody.innerHTML = bikes.map((s) => rowHtml(s.name, s.free, s.total)).join("");

  // Recherche
  const searchCars = $("searchCars");
  const searchBikes = $("searchBikes");

  function applyFilter(inputEl, list, targetBody) {
    const q = (inputEl.value || "").trim().toLowerCase();
    const filtered = q
      ? list.filter((x) => String(x.name || "").toLowerCase().includes(q))
      : list;
    targetBody.innerHTML = filtered.map((x) => rowHtml(x.name, x.free, x.total)).join("");
  }

  if (searchCars) {
    searchCars.addEventListener("input", () => applyFilter(searchCars, cars, carsBody));
  }
  if (searchBikes) {
    searchBikes.addEventListener("input", () => applyFilter(searchBikes, bikes, bikesBody));
  }
}

/* =========================
 *  CARTE (Leaflet)
 * ========================= */
let _map = null;
let _carsLayer = null;
let _bikesLayer = null;

function renderMap(snapshot) {
  const mapEl = $("map");
  if (!mapEl) return;
  if (!window.L) return;

  // Evite de recréer si on rerender l'analyse
  if (_map) return;

  _map = L.map("map").setView([43.6108, 3.8767], 13);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(_map);

  _carsLayer = L.layerGroup().addTo(_map);
  _bikesLayer = L.layerGroup().addTo(_map);

  const showCars = $("showCars");
  const showBikes = $("showBikes");

  function refreshVisibility() {
    if (!_map) return;
    if (showCars?.checked) _map.addLayer(_carsLayer);
    else _map.removeLayer(_carsLayer);

    if (showBikes?.checked) _map.addLayer(_bikesLayer);
    else _map.removeLayer(_bikesLayer);
  }

  showCars?.addEventListener("change", refreshVisibility);
  showBikes?.addEventListener("change", refreshVisibility);

  const cars = Array.isArray(snapshot.cars) ? snapshot.cars : [];
  const bikes = Array.isArray(snapshot.bikes) ? snapshot.bikes : [];

  cars.forEach((p) => {
    if (p.lat == null || p.lon == null) return;
    const popup = `<b>${escapeHtml(p.name)}</b><br/>Libres: ${fmtNumber(p.free)} / ${fmtNumber(p.total)}`;
    L.marker([p.lat, p.lon]).bindPopup(popup).addTo(_carsLayer);
  });

  bikes.forEach((s) => {
    if (s.lat == null || s.lon == null) return;
    const popup = `<b>${escapeHtml(s.name)}</b><br/>Places libres: ${fmtNumber(s.free)} / ${fmtNumber(s.total)}`;
    L.circleMarker([s.lat, s.lon], { radius: 7 }).bindPopup(popup).addTo(_bikesLayer);
  });

  refreshVisibility();
}

/* =========================
 *  CORRELATIONS / HEATMAP
 * ========================= */

function getFilters() {
  const maxDistance = Number($("maxDistance")?.value ?? 2);
  const minAbsCorr = Number($("minAbsCorr")?.value ?? 0.25);
  const onlyNegative = Boolean($("onlyNegative")?.checked ?? true);
  return { maxDistance, minAbsCorr, onlyNegative };
}

function updateFilterLabels() {
  const maxDistance = $("maxDistance");
  const minAbsCorr = $("minAbsCorr");
  if ($("maxDistanceValue") && maxDistance) $("maxDistanceValue").textContent = `${maxDistance.value} km`;
  if ($("minAbsCorrValue") && minAbsCorr) $("minAbsCorrValue").textContent = `${minAbsCorr.value}`;
}

function applyFiltersToPairs(pairs, filters) {
  return pairs.filter((p) => {
    const r = Number(p.r);
    const absR = Number(p.abs_r ?? Math.abs(r));
    const dist = p.distance_km == null ? null : Number(p.distance_km);

    if (filters.onlyNegative && !(r < 0)) return false;
    if (absR < filters.minAbsCorr) return false;
    if (dist != null && dist > filters.maxDistance) return false;

    return true;
  });
}

function renderPairsTable(pairs, filters) {
  const body = $("pairsTable");
  if (!body) return;

  const filtered = applyFiltersToPairs(pairs, filters).slice(0, 200);

  body.innerHTML = filtered
    .map((p) => {
      return `<tr>
        <td>${escapeHtml(p.car)}</td>
        <td>${escapeHtml(p.bike)}</td>
        <td class="num">${fmtNumber(p.r)}</td>
        <td class="num">${p.distance_km == null ? "—" : fmtKm(p.distance_km)}</td>
        <td class="num">${fmtNumber(p.n)}</td>
        <td class="num">${fmtNumber(p.score)}</td>
      </tr>`;
    })
    .join("");
}

function renderHeatmap(corr, filters) {
  const container = $("heatmap");
  if (!container) return;
  if (!window.Plotly) {
    container.innerHTML = "<p class='muted'>Plotly non chargé.</p>";
    return;
  }

  const cars = Array.isArray(corr.cars) ? corr.cars : [];
  const bikes = Array.isArray(corr.bikes) ? corr.bikes : [];
  const matrix = Array.isArray(corr.matrix) ? corr.matrix : [];

  // On fabrique une matrice "filtrée" en utilisant corr.pairs
  // pour vérifier distance, abs corr, négatif.
  const pairMap = new Map();
  const pairs = Array.isArray(corr.pairs) ? corr.pairs : [];
  for (const p of pairs) {
    pairMap.set(`${p.car}|||${p.bike}`, p);
  }

  const z = [];
  const text = [];

  for (let i = 0; i < cars.length; i++) {
    const row = [];
    const rowText = [];
    for (let j = 0; j < bikes.length; j++) {
      const carName = cars[i];
      const bikeName = bikes[j];
      const key = `${carName}|||${bikeName}`;
      const p = pairMap.get(key);

      if (!p) {
        row.push(null);
        rowText.push("");
        continue;
      }

      const r = Number(p.r);
      const absR = Number(p.abs_r ?? Math.abs(r));
      const dist = p.distance_km == null ? null : Number(p.distance_km);

      // filtres
      if (filters.onlyNegative && !(r < 0)) {
        row.push(null);
        rowText.push("");
        continue;
      }
      if (absR < filters.minAbsCorr) {
        row.push(null);
        rowText.push("");
        continue;
      }
      if (dist != null && dist > filters.maxDistance) {
        row.push(null);
        rowText.push("");
        continue;
      }

      row.push(r);
      rowText.push(`r=${r}\nkm=${dist == null ? "?" : dist}\npoints=${p.n}`);
    }
    z.push(row);
    text.push(rowText);
  }

  const data = [
    {
      z,
      x: bikes,
      y: cars,
      type: "heatmap",
      hoverinfo: "text",
      text,
    },
  ];

  const layout = {
    margin: { l: 160, r: 20, t: 20, b: 160 },
    xaxis: { automargin: true },
    yaxis: { automargin: true },
  };

  Plotly.newPlot(container, data, layout, { displayModeBar: false, responsive: true });
}

function wireFilterEvents(onChange) {
  const ids = ["maxDistance", "minAbsCorr", "onlyNegative"];
  ids.forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("input", () => {
      updateFilterLabels();
      onChange();
    });
    el.addEventListener("change", () => {
      updateFilterLabels();
      onChange();
    });
  });
}

/* =========================
 *  FENETRE TEMPORELLE (7/14/21/30)
 * ========================= */
async function loadCorrelations(days) {
  const d = Number(days);
  const path = `./data/correlations_${d}.json`;
  return await fetchJson(path);
}

/* =========================
 *  INIT
 * ========================= */
async function init() {
  updateFilterLabels();

  // Snapshot temps réel (toujours le même fichier)
  const snapshot = await fetchJson("./data/latest_snapshot.json");
  renderRealtimeTables(snapshot);
  renderMap(snapshot);

  // Infos en haut
  $("lastUpdate").textContent = fmtDateTime(snapshot.generated_at);

  const windowSelect = $("windowSelect");
  const selectedDays = windowSelect ? Number(windowSelect.value) : 21;

  let corr = null;

  async function rerenderAnalysis() {
    const filters = getFilters();
    if (!corr) return;

    $("analysisInfo").textContent = `${corr.lookback_days ?? selectedDays} jours (min points: ${corr.min_common_points ?? "—"})`;

    const pairs = Array.isArray(corr.pairs) ? corr.pairs : [];
    renderHeatmap(corr, filters);
    renderPairsTable(pairs, filters);
  }

  // Chargement initial
  try {
    corr = await loadCorrelations(selectedDays);
  } catch (e) {
    console.error(e);
    $("analysisInfo").textContent =
      "Corrélations indisponibles (génère correlations_7/14/21/30.json côté workflow).";
    return;
  }

  wireFilterEvents(rerenderAnalysis);

  if (windowSelect) {
    windowSelect.addEventListener("change", async () => {
      const days = Number(windowSelect.value);
      try {
        corr = await loadCorrelations(days);
        rerenderAnalysis();
      } catch (e) {
        console.error(e);
        alert("Impossible de charger les corrélations pour cette fenêtre. Vérifie les fichiers correlations_<days>.json.");
      }
    });
  }

  rerenderAnalysis();
}

document.addEventListener("DOMContentLoaded", () => {
  init().catch((e) => {
    console.error(e);
    const el = $("analysisInfo");
    if (el) el.textContent = "Erreur de chargement (voir console).";
  });
});
