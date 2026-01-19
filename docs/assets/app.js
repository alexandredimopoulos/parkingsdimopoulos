/* global Plotly */

const SNAPSHOT_URL = "./data/latest_snapshot.json";
const CORR_URL = "./data/correlations.json";

function qs(sel) {
  return document.querySelector(sel);
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fmt(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  if (typeof n === "number") return n.toLocaleString("fr-FR");
  return String(n);
}

function fmtFloat(n, digits = 3) {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  return Number(n).toFixed(digits);
}

function normalizeKey(s) {
  // Simplissime : minuscule + suppression accents (via NFD)
  return String(s)
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

async function waitForPlotly() {
  for (let i = 0; i < 100; i += 1) {
    if (window.Plotly) return;
    await new Promise((r) => setTimeout(r, 50));
  }
  throw new Error("Plotly non chargé");
}

function renderAvailabilityTable(tbodyEl, items) {
  const rows = items
    .map((it) => {
      return `
        <tr>
          <td>${escapeHtml(it.name)}</td>
          <td class="num">${fmt(it.free)}</td>
          <td class="num">${fmt(it.total)}</td>
        </tr>`;
    })
    .join("");
  tbodyEl.innerHTML = rows;
}

function filterItemsBySearch(items, searchValue) {
  const q = normalizeKey(searchValue);
  if (!q) return items;
  return items.filter((it) => normalizeKey(it.name).includes(q));
}

function buildFilteredMatrix(cars, bikes, pairs, maxDistanceKm, minAbsCorr, onlyNegative) {
  // dict (car|bike) -> r
  const pairMap = new Map();
  for (const p of pairs) {
    const distOk = (p.distance_km === null || p.distance_km === undefined)
      ? true
      : (p.distance_km <= maxDistanceKm);

    const corrOk = Math.abs(p.r) >= minAbsCorr;
    const signOk = !onlyNegative || Number(p.r) < 0;

    if (distOk && corrOk && signOk) {
      pairMap.set(`${p.car}|||${p.bike}`, p.r);
    }
  }

  const z = [];
  for (const car of cars) {
    const row = [];
    for (const bike of bikes) {
      const r = pairMap.get(`${car}|||${bike}`);
      row.push(r === undefined ? null : r);
    }
    z.push(row);
  }
  return z;
}

function renderHeatmap({ cars, bikes, pairs, maxDistanceKm, minAbsCorr, onlyNegative }) {
  const z = buildFilteredMatrix(cars, bikes, pairs, maxDistanceKm, minAbsCorr, onlyNegative);

  const data = [
    {
      type: "heatmap",
      x: bikes,
      y: cars,
      z,
      zmin: -1,
      zmax: 1,
      hovertemplate:
        "<b>%{y}</b> ↔ <b>%{x}</b><br>corr=%{z:.3f}<extra></extra>",
    },
  ];

  const layout = {
    margin: { l: 130, r: 10, t: 20, b: 120 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    xaxis: {
      tickangle: -45,
      automargin: true,
    },
    yaxis: {
      automargin: true,
      autorange: "reversed",
    },
    height: Math.max(420, cars.length * 18 + 160),
  };

  const config = { displayModeBar: false, responsive: true };

  Plotly.newPlot("heatmap", data, layout, config);
}

function renderPairsRanking(tbodyEl, pairs, maxDistanceKm, minAbsCorr, onlyNegative) {
  const filtered = pairs.filter((p) => {
    const distOk = (p.distance_km === null || p.distance_km === undefined)
      ? true
      : (p.distance_km <= maxDistanceKm);
    const corrOk = Math.abs(p.r) >= minAbsCorr;
    const signOk = !onlyNegative || Number(p.r) < 0;
    return distOk && corrOk && signOk;
  });

  const top = filtered.slice(0, 80);

  tbodyEl.innerHTML = top
    .map((p) => {
      const corr = Number(p.r);
      const cls = corr < 0 ? "neg" : "pos";
      return `
        <tr>
          <td>${escapeHtml(p.car)}</td>
          <td>${escapeHtml(p.bike)}</td>
          <td class="num ${cls}">${fmtFloat(corr, 3)}</td>
          <td class="num">${p.distance_km === null ? "–" : fmtFloat(p.distance_km, 3)}</td>
          <td class="num">${fmt(p.n)}</td>
          <td class="num">${fmtFloat(p.score, 4)}</td>
        </tr>`;
    })
    .join("");
}

function fillSelect(selectEl, options) {
  selectEl.innerHTML = options
    .map((opt) => `<option value="${escapeHtml(opt)}">${escapeHtml(opt)}</option>`)
    .join("");
}

function renderLocalLinks(tbodyEl, links, direction) {
  // direction: "car" => affiche stations vélo ; "bike" => affiche parkings voiture
  tbodyEl.innerHTML = links
    .map((p) => {
      const corr = Number(p.r);
      const cls = corr < 0 ? "neg" : "pos";
      const leftName = direction === "car" ? p.bike : p.car;
      return `
        <tr>
          <td>${escapeHtml(leftName)}</td>
          <td class="num ${cls}">${fmtFloat(corr, 3)}</td>
          <td class="num">${p.distance_km === null ? "–" : fmtFloat(p.distance_km, 3)}</td>
          <td class="num">${fmt(p.n)}</td>
          <td class="num">${fmtFloat(p.score, 4)}</td>
        </tr>`;
    })
    .join("");
}

function setPill(id, text) {
  const el = qs(id);
  if (el) el.textContent = text;
}

async function loadAll() {
  await waitForPlotly();

  let snapshot = null;
  let corr = null;

  try {
    const r = await fetch(SNAPSHOT_URL, { cache: "no-store" });
    snapshot = await r.json();
  } catch (e) {
    console.error(e);
  }

  try {
    const r = await fetch(CORR_URL, { cache: "no-store" });
    corr = await r.json();
  } catch (e) {
    console.error(e);
  }

  if (snapshot) {
    qs("#lastUpdate").textContent = snapshot.generated_at || "–";
    qs("#sources").textContent = snapshot.sources
      ? `Sources: voitures=${snapshot.sources.cars} ; vélos=${snapshot.sources.bikes}`
      : "Sources: –";

    const carsTbody = qs("#carsTable");
    const bikesTbody = qs("#bikesTable");

    const cars = snapshot.cars || [];
    const bikes = snapshot.bikes || [];

    renderAvailabilityTable(carsTbody, cars);
    renderAvailabilityTable(bikesTbody, bikes);

    qs("#searchCars").addEventListener("input", (ev) => {
      renderAvailabilityTable(carsTbody, filterItemsBySearch(cars, ev.target.value));
    });

    qs("#searchBikes").addEventListener("input", (ev) => {
      renderAvailabilityTable(bikesTbody, filterItemsBySearch(bikes, ev.target.value));
    });
  } else {
    qs("#lastUpdate").textContent = "(snapshot indisponible)";
  }

  if (corr) {
    const analysisInfo = qs("#analysisInfo");
    analysisInfo.textContent = `Fenêtre: ${corr.lookback_days} jours · min points: ${corr.min_common_points} · paires: ${corr.counts?.pairs_computed ?? "?"}`;

    const cars = corr.cars || [];
    const bikes = corr.bikes || [];
    const pairs = corr.pairs || [];

    // Valeurs par défaut depuis le JSON (si présent)
    const defaultMaxD = corr.default_filters?.max_distance_km ?? 2.0;
    const defaultMinAbs = corr.default_filters?.min_abs_correlation ?? 0.25;

    const maxDistanceInput = qs("#maxDistance");
    const minAbsCorrInput = qs("#minAbsCorr");
    const onlyNegativeInput = qs("#onlyNegative");

    // Classements locaux
    const byCar = corr.by_car || {};
    const byBike = corr.by_bike || {};
    const carSelect = qs("#carSelect");
    const bikeSelect = qs("#bikeSelect");
    const carLinksTbody = qs("#carLinks");
    const bikeLinksTbody = qs("#bikeLinks");

    if (carSelect) fillSelect(carSelect, cars);
    if (bikeSelect) fillSelect(bikeSelect, bikes);

    maxDistanceInput.value = String(defaultMaxD);
    minAbsCorrInput.value = String(defaultMinAbs);

    const updateViz = () => {
      const maxD = Number(maxDistanceInput.value);
      const minAbs = Number(minAbsCorrInput.value);
      const onlyNegative = onlyNegativeInput ? Boolean(onlyNegativeInput.checked) : false;

      setPill("#maxDistanceValue", `${maxD.toFixed(1)} km`);
      setPill("#minAbsCorrValue", `${minAbs.toFixed(2)}`);

      renderHeatmap({ cars, bikes, pairs, maxDistanceKm: maxD, minAbsCorr: minAbs, onlyNegative });
      renderPairsRanking(qs("#pairsTable"), pairs, maxD, minAbs, onlyNegative);

      // Mise à jour des tableaux "local" en gardant les mêmes filtres
      if (carSelect && carLinksTbody) {
        const selectedCar = carSelect.value || cars[0];
        const links = (byCar[selectedCar] || []).filter((p) => {
          const distOk = (p.distance_km === null || p.distance_km === undefined)
            ? true
            : (p.distance_km <= maxD);
          const corrOk = Math.abs(p.r) >= minAbs;
          const signOk = !onlyNegative || Number(p.r) < 0;
          return distOk && corrOk && signOk;
        });
        renderLocalLinks(carLinksTbody, links, "car");
      }

      if (bikeSelect && bikeLinksTbody) {
        const selectedBike = bikeSelect.value || bikes[0];
        const links = (byBike[selectedBike] || []).filter((p) => {
          const distOk = (p.distance_km === null || p.distance_km === undefined)
            ? true
            : (p.distance_km <= maxD);
          const corrOk = Math.abs(p.r) >= minAbs;
          const signOk = !onlyNegative || Number(p.r) < 0;
          return distOk && corrOk && signOk;
        });
        renderLocalLinks(bikeLinksTbody, links, "bike");
      }
    };

    maxDistanceInput.addEventListener("input", updateViz);
    minAbsCorrInput.addEventListener("input", updateViz);
    if (onlyNegativeInput) onlyNegativeInput.addEventListener("change", updateViz);

    if (carSelect) carSelect.addEventListener("change", updateViz);
    if (bikeSelect) bikeSelect.addEventListener("change", updateViz);

    updateViz();
  } else {
    qs("#analysisInfo").textContent = "(corrélations indisponibles)";
  }
}

loadAll();
