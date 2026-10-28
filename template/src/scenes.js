// 《X的年轮》frozen template: scene data loader.
// Every city-specific value comes from <city>/city.json + <city>/nodes.json (see ../../SKILL.md).
// This file only fills in defaults: node durations and camera presets are derived from the node
// coordinates when the node table does not pin them.
//
// cam: target lon/lat, dist (km from target), pitch (deg above horizon), yaw (deg, 0 = looking north),
//      orbit (deg of yaw drift over the hold), push (dist multiplier reached at end of hold)

const QS = new URLSearchParams(location.search);
export const FPS = parseInt(QS.get('fps') || '30');          // 30 final; drafts may use 15
export const BASE = QS.get('city') || '/city';

const getJSON = async u => { const r = await fetch(u); if (!r.ok) throw new Error(`${u}: HTTP ${r.status}`); return r.json(); };
export const CITY = await getJSON(`${BASE}/city.json`);
const RAW = (await getJSON(`${BASE}/nodes.json`)).nodes;
if (!RAW || RAW.length < 1) throw new Error('nodes.json: no nodes');

const C0 = CITY.center;
const KX = 111.32 * Math.cos(C0.lat * Math.PI / 180), KZ = 110.95;
const km = (a, b) => Math.hypot((b.lon - a.lon) * KX, (b.lat - a.lat) * KZ);
const bearing = (a, b) => (Math.atan2((b.lon - a.lon) * KX, (b.lat - a.lat) * KZ) * 180 / Math.PI + 360) % 360;
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const r1 = x => Math.round(x * 10) / 10;

// ---------------------------------------------------------------- overview framing
const cen = { lon: RAW.reduce((s, n) => s + n.lon, 0) / RAW.length, lat: RAW.reduce((s, n) => s + n.lat, 0) / RAW.length };
const spread = Math.max(8, ...RAW.map(n => km(cen, n)));          // km, radius of the node cloud

const ci = CITY.intro || {};
const cam1 = ci.cam1 || { lon: r1(cen.lon * 100) / 100, lat: r1(cen.lat * 100) / 100, dist: Math.round(clamp(spread * 1.6, 45, 90)), pitch: 24, yaw: 200 };
// opening shot: start high and further back along the view direction, drift in
const back = (cam1.dist * 0.75) / 111;
const cam0 = ci.cam0 || {
  lon: cam1.lon - Math.sin(cam1.yaw * Math.PI / 180) * back / Math.cos(C0.lat * Math.PI / 180),
  lat: cam1.lat - Math.cos(cam1.yaw * Math.PI / 180) * back,
  dist: Math.round(cam1.dist * 1.7), pitch: 16, yaw: cam1.yaw - 8,
};
export const INTRO = { dur: ci.dur ?? 9, title: CITY.title, sub: CITY.subtitle, cam0, cam1 };

const co = CITY.outro || {};
export const OUTRO = {
  dur: co.dur ?? 10, question: co.question,
  cam: co.cam || { lon: cen.lon, lat: cen.lat, dist: Math.round(clamp(spread * 2.2, 70, 130)), pitch: 52, yaw: 345 },
};

// ---------------------------------------------------------------- node defaults
// time: 120–180 s overall; long node tables get shorter holds, two-image nodes a little longer
const autoDur = clamp((150 - INTRO.dur - OUTRO.dur) / RAW.length, 9.5, 12);
const PITCH = [34, 30, 38, 32, 40, 28];

export const NODES = [];
RAW.forEach((n, i) => {
  const prev = i ? NODES[i - 1] : null;
  const others = RAW.filter(m => km(m, n) > 0.3);
  const nn = others.length ? Math.min(...others.map(m => km(m, n))) : 10;
  let yaw;
  if (!prev) yaw = (bearing(INTRO.cam1, n) + 360) % 360;
  else if (km(prev, n) > 1) yaw = bearing(prev, n) + (i % 2 ? 25 : -25);    // look along the flight
  else yaw = prev.cam.yaw + 110;                                          // same place: swing round
  const auto = {
    dist: r1(clamp(nn * 0.9, 6.5, 16)),
    pitch: PITCH[i % PITCH.length],
    yaw: Math.round((yaw + 360) % 360),
    orbit: i % 2 ? -15 : 15,
    push: 0.82,
  };
  if (n.scope === 'region') { auto.dist = Math.round(clamp(spread * 1.5, 40, 80)); auto.pitch = 48; auto.orbit = 8; auto.push = 0.9; }
  const imgs = (n.images || []).length;
  // no archival image → text card (place name, or the year when the name is long)
  const card = n.card || (imgs ? undefined : {
    big: [...n.place].length <= 4 ? n.place : String(n.year).replace(/年.*$/, '').slice(0, 5),
    lines: [n.title],
  });
  NODES.push({ ...n, ...(card ? { card } : {}), images: imgs ? n.images : undefined, dur: n.dur ?? r1(autoDur + (imgs > 1 ? 0.5 : 0)), cam: { ...auto, ...(n.cam || {}) } });
});

export const TOTAL = INTRO.dur + NODES.reduce((s, n) => s + n.dur, 0) + OUTRO.dur;
