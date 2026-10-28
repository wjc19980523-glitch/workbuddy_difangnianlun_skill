import * as THREE from 'three';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { INTRO, NODES, OUTRO, CITY, BASE, TOTAL, FPS } from './scenes.js';

const W = 1080, H = 1920;
// render quality knobs (query string, set by render.mjs from NL_SCALE / NL_SAMPLES): defaults = final quality
const QS = new URLSearchParams(location.search);
const RS = parseFloat(QS.get('scale') || '1');          // WebGL resolution scale (0.5 → 540x960 drawing buffer)
const MSAA = parseInt(QS.get('samples') ?? '4');
const LON0 = CITY.center.lon, LAT0 = CITY.center.lat;
const KX = 111.32 * Math.cos(LAT0 * Math.PI / 180), KZ = 110.95;
const EX = CITY.map?.exaggeration ?? 2.6;   // vertical exaggeration
const SUN = new THREE.Vector3(-0.62, 0.30, 0.72).normalize();   // low sun in the south-west

const wx = lon => (lon - LON0) * KX;
const wz = lat => -(lat - LAT0) * KZ;
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const smooth = x => { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); };
const smoother = x => { x = clamp(x, 0, 1); return x * x * x * (x * (x * 6 - 15) + 10); };
const ease = x => 0.5 - 0.5 * Math.cos(Math.PI * clamp(x, 0, 1));
const lerp = (a, b, t) => a + (b - a) * t;
const ramp = (t, a, b) => smooth((t - a) / (b - a));   // 0→1 between a and b
const win = (t, a, b, c, d) => ramp(t, a, b) * (1 - ramp(t, c, d)); // fade in a→b, out c→d

async function loadJSON(u) { return (await fetch(u)).json(); }
async function loadF32(u) { return new Float32Array(await (await fetch(u)).arrayBuffer()); }
function loadTex(u) {
  return new Promise(res => new THREE.TextureLoader().load(u, t => {
    t.colorSpace = THREE.NoColorSpace; t.anisotropy = 8; t.generateMipmaps = true;
    t.minFilter = THREE.LinearMipmapLinearFilter; res(t);
  }));
}

const lat2my = lat => Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360));
const my2lat = my => (2 * Math.atan(Math.exp(my)) - Math.PI / 2) * 180 / Math.PI;

// ---------------------------------------------------------------- renderer
const canvas = document.getElementById('gl');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(RS);
renderer.setSize(W, H, false);
renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
renderer.toneMapping = THREE.NoToneMapping;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(38, W / H, 0.05, 4000);

const rt = new THREE.WebGLRenderTarget(W * RS, H * RS, { type: THREE.HalfFloatType, samples: MSAA });
// resolve target for MSAA (depth must come from a non-multisampled target)
const rtDepth = new THREE.WebGLRenderTarget(W * RS, H * RS, { type: THREE.HalfFloatType });
rtDepth.depthTexture = new THREE.DepthTexture(W * RS, H * RS);
rtDepth.depthTexture.type = THREE.UnsignedIntType;

// ---------------------------------------------------------------- shared GLSL
const NOISE = `
float hash(vec2 p){ p = fract(p*vec2(123.34, 456.21)); p += dot(p, p+45.32); return fract(p.x*p.y); }
float vnoise(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.-2.*f);
  return mix(mix(hash(i),hash(i+vec2(1,0)),f.x), mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x), f.y); }
float fbm(vec2 p){ float s=0., a=.5; for(int i=0;i<5;i++){ s+=a*vnoise(p); p=p*2.03+vec2(1.7,9.2); a*=.5; } return s; }
`;

const ATMOS = {
  sunColor: new THREE.Color(1.55, 1.18, 0.82),
  ambSky: new THREE.Color(0.36, 0.44, 0.55),
  ambGround: new THREE.Color(0.20, 0.17, 0.13),
  fog: new THREE.Color(0.47, 0.50, 0.53),
  fogSun: new THREE.Color(1.05, 0.80, 0.55),
};

function terrainMaterial(map, water, isWide) {
  return new THREE.ShaderMaterial({
    uniforms: {
      map: { value: map }, water: { value: water }, hasWater: { value: water ? 1 : 0 }, isWide: { value: isWide ? 1 : 0 },
      sunDir: { value: SUN }, sunColor: { value: ATMOS.sunColor }, ambSky: { value: ATMOS.ambSky }, ambGround: { value: ATMOS.ambGround },
      fogColor: { value: ATMOS.fog }, fogSun: { value: ATMOS.fogSun }, fogDensity: { value: 0.012 }, time: { value: 0 },
      dim: { value: 1 },
    },
    vertexShader: `
      varying vec2 vUv; varying vec3 vW; varying vec3 vN;
      void main(){ vUv = uv; vec4 w = modelMatrix*vec4(position,1.); vW = w.xyz; vN = normalize(mat3(modelMatrix)*normal);
        gl_Position = projectionMatrix*viewMatrix*w; }`,
    fragmentShader: `
      uniform sampler2D map, water; uniform float hasWater, isWide, fogDensity, time, dim;
      uniform vec3 sunDir, sunColor, ambSky, ambGround, fogColor, fogSun;
      varying vec2 vUv; varying vec3 vW; varying vec3 vN;
      ${NOISE}
      void main(){
        vec3 alb = texture2D(map, vUv).rgb;
        alb = pow(alb, vec3(2.2));
        float l = dot(alb, vec3(.2126,.7152,.0722));
        alb = mix(vec3(l), alb, 1.12);                // a touch more colour
        alb = pow(alb, vec3(1.08)) * 1.05;           // and contrast
        vec3 n = normalize(vN);
        float w = hasWater > .5 ? texture2D(water, vUv).r : 0.;
        if (isWide > .5) {
          // far ring: approximate water from colour (teal)
          w = smoothstep(.0, .06, (alb.g - alb.r)) * smoothstep(.02,.08, alb.b - alb.r*0.8) * 0.0;
        }
        vec3 V = normalize(cameraPosition - vW);
        // relief shading: exaggerate slope light so hills read at altitude
        float diff = max(dot(n, sunDir), 0.);
        float hemi = n.y*.5+.5;
        vec3 col = alb * (sunColor * diff * 1.05 + mix(ambGround, ambSky, hemi) * 0.62);
        // water
        if (w > 0.01) {
          vec2 p = vW.xz*1.6;
          float e = .05;
          float h0 = fbm(p + time*.15), hx = fbm(p+vec2(e,0.) + time*.15), hz = fbm(p+vec2(0.,e) + time*.15);
          vec3 wn = normalize(vec3((h0-hx)*.9, 1., (h0-hz)*.9));
          vec3 Hh = normalize(V + sunDir);
          float spec = pow(max(dot(wn, Hh), 0.), 160.) * 5.5 + pow(max(dot(wn, Hh), 0.), 18.) * .22;
          float fr = .03 + .97*pow(1. - max(dot(V, wn), 0.), 5.);
          vec3 sky = mix(vec3(.42,.5,.58), fogSun*.9, pow(max(dot(reflect(-V, wn), sunDir),0.), 4.));
          vec3 wc = alb*.62*(ambSky*.9 + sunColor*.25) + sky*fr*.75 + sunColor*spec;
          col = mix(col, wc, w);
        }
        col *= dim;
        // atmosphere: distance + height fog, warmer towards the sun
        float d = length(cameraPosition - vW);
        float f = 1. - exp(-pow(d*fogDensity, 1.35));
        f *= mix(1., .55, clamp(vW.y*.35, 0., 1.));
        vec3 vd = normalize(vW - cameraPosition);
        vec3 fc = mix(fogColor, fogSun, pow(max(dot(vd, sunDir), 0.), 5.));
        if (isWide > .5) {
          vec2 e2 = min(vUv, 1.-vUv);
          f = max(f, 1. - smoothstep(0., .12, min(e2.x, e2.y)));
        }
        gl_FragColor = vec4(mix(col, fc, clamp(f, 0., 1.)), 1.);
      }`,
  });
}

function buildTerrain(meta, heights, n, mat, yOff) {
  const pos = new Float32Array(n * n * 3), uv = new Float32Array(n * n * 2);
  const my1 = lat2my(meta.lat1), my0 = lat2my(meta.lat0);
  for (let j = 0; j < n; j++) {
    const lat = my2lat(lerp(my1, my0, j / (n - 1)));
    for (let i = 0; i < n; i++) {
      const lon = lerp(meta.lon0, meta.lon1, i / (n - 1));
      const k = j * n + i;
      pos[k * 3] = wx(lon); pos[k * 3 + 1] = heights[k] / 1000 * EX + yOff; pos[k * 3 + 2] = wz(lat);
      uv[k * 2] = i / (n - 1); uv[k * 2 + 1] = 1 - j / (n - 1);
    }
  }
  const idx = new Uint32Array((n - 1) * (n - 1) * 6);
  let p = 0;
  for (let j = 0; j < n - 1; j++) for (let i = 0; i < n - 1; i++) {
    const a = j * n + i, b = a + 1, c = a + n, d = c + 1;
    idx[p++] = a; idx[p++] = c; idx[p++] = b; idx[p++] = b; idx[p++] = c; idx[p++] = d;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  g.setIndex(new THREE.BufferAttribute(idx, 1));
  g.computeVertexNormals();
  return new THREE.Mesh(g, mat);
}

// height lookup on the core grid (world units)
let CORE = null;
function heightAt(lon, lat) {
  const { meta, h, n } = CORE;
  const fi = (lon - meta.lon0) / (meta.lon1 - meta.lon0) * (n - 1);
  const fj = (lat2my(meta.lat1) - lat2my(lat)) / (lat2my(meta.lat1) - lat2my(meta.lat0)) * (n - 1);
  const i = clamp(Math.floor(fi), 0, n - 2), j = clamp(Math.floor(fj), 0, n - 2);
  const u = clamp(fi - i, 0, 1), v = clamp(fj - j, 0, 1);
  const a = lerp(h[j * n + i], h[j * n + i + 1], u), b = lerp(h[(j + 1) * n + i], h[(j + 1) * n + i + 1], u);
  return lerp(a, b, v) / 1000 * EX;
}

// ---------------------------------------------------------------- sky, mist
function buildSky() {
  const m = new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false,
    uniforms: { sunDir: { value: SUN }, fog: { value: ATMOS.fog }, fogSun: { value: ATMOS.fogSun } },
    vertexShader: `varying vec3 vD; void main(){ vD = normalize(position); vec4 p = projectionMatrix*modelViewMatrix*vec4(position,1.); gl_Position = p.xyww; }`,
    fragmentShader: `uniform vec3 sunDir, fog, fogSun; varying vec3 vD;
      void main(){ vec3 d = normalize(vD); float h = clamp(d.y, -0.1, 1.);
        vec3 zen = vec3(.16,.22,.31);
        vec3 col = mix(fog*1.05, zen, pow(max(h,0.), .55));
        float s = max(dot(d, sunDir), 0.);
        col = mix(col, fogSun*1.25, pow(s, 6.)*.75*(1.-max(h,0.)*.6));
        col += vec3(1.9,1.5,1.05) * pow(s, 900.) * 6. + vec3(1.2,.85,.55)*pow(s, 60.)*.5;
        gl_FragColor = vec4(col, 1.); }`,
  });
  const s = new THREE.Mesh(new THREE.SphereGeometry(3000, 48, 24), m);
  s.frustumCulled = false; s.renderOrder = -10;
  return s;
}

function buildMist() {
  const group = new THREE.Group();
  const levels = [0.18, 0.55, 1.15, 2.2];
  levels.forEach((y, k) => {
    const m = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false,
      uniforms: { time: { value: 0 }, k: { value: k }, sunDir: { value: SUN }, amt: { value: 1 }, fog: { value: ATMOS.fog }, fogSun: { value: ATMOS.fogSun } },
      vertexShader: `varying vec3 vW; void main(){ vec4 w = modelMatrix*vec4(position,1.); vW = w.xyz; gl_Position = projectionMatrix*viewMatrix*w; }`,
      fragmentShader: `uniform float time, k, amt; uniform vec3 sunDir, fog, fogSun; varying vec3 vW; ${NOISE}
        void main(){
          vec2 p = vW.xz*(.055 + k*.018) + vec2(time*.012*(1.+k*.4), time*.006);
          float n = fbm(p); n = smoothstep(.42, .9, n);
          float d = length(cameraPosition - vW);
          float a = n * (.30 - k*.05) * smoothstep(.6, 6., d) * (1. - smoothstep(140., 260., d)) * amt;
          vec3 vd = normalize(vW - cameraPosition);
          vec3 c = mix(fog*1.12, fogSun*1.15, pow(max(dot(vd, sunDir),0.), 3.));
          gl_FragColor = vec4(c, a); }`,
    });
    const p = new THREE.Mesh(new THREE.PlaneGeometry(420, 420, 1, 1), m);
    p.rotation.x = -Math.PI / 2; p.position.set(0, y, 0); p.renderOrder = 5 + k;
    group.add(p);
  });
  return group;
}

// ---------------------------------------------------------------- markers ("年轮")
function ringMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    uniforms: { t: { value: 0 }, live: { value: 0 }, vis: { value: 0 } },
    vertexShader: `varying vec2 vUv; void main(){ vUv = uv*2.-1.; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.); }`,
    fragmentShader: `uniform float t, live, vis; varying vec2 vUv;
      void main(){ float r = length(vUv);
        // concentric growth rings: a few fine circles, newest one expanding outward
        float rings = 0.;
        for (int i=0;i<5;i++){ float ri = .16 + float(i)*.16; rings += smoothstep(.012,.0,abs(r-ri))*(1.-float(i)*.16); }
        float wave = fract(t*.32); float wr = wave*1.0;
        float pulse = smoothstep(.03,.0,abs(r-wr))*(1.-wave);
        float core = smoothstep(.07,.0,r)*1.6 + smoothstep(.22,.0,r)*.25;
        float a = (rings*.55*live + pulse*1.3*live + core) * (1.-smoothstep(.9,1.,r));
        vec3 c = mix(vec3(1.0,.72,.38), vec3(1.0,.9,.7), core*.5);
        gl_FragColor = vec4(c*a*vis, 1.); }`,
  });
}
function beamMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    uniforms: { vis: { value: 0 } },
    vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.); }`,
    fragmentShader: `uniform float vis; varying vec2 vUv;
      void main(){ float a = pow(1.-vUv.y, 3.0) * .32 * vis; gl_FragColor = vec4(vec3(1.,.78,.48)*a, 1.); }`,
  });
}

const markers = [];   // one per node location (deduplicated)
function markerFor(lon, lat) {
  let m = markers.find(m => Math.abs(m.lon - lon) < 1e-4 && Math.abs(m.lat - lat) < 1e-4);
  if (m) return m;
  const ring = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), ringMaterial());
  ring.rotation.x = -Math.PI / 2; ring.renderOrder = 20;
  const beam = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 1, 24, 1, true), beamMaterial());
  beam.renderOrder = 21;
  const y = heightAt(lon, lat);
  ring.position.set(wx(lon), y + 0.04, wz(lat));
  beam.position.set(wx(lon), y, wz(lat));
  scene.add(ring, beam);
  m = { lon, lat, ring, beam, y, seen: -1 };
  markers.push(m);
  return m;
}

// ---------------------------------------------------------------- path between nodes
let pathLines = [];
function buildPaths() {
  for (let i = 1; i < NODES.length; i++) {
    const a = NODES[i - 1], b = NODES[i];
    const ax = wx(a.lon), az = wz(a.lat), bx = wx(b.lon), bz = wz(b.lat);
    const d = Math.hypot(bx - ax, bz - az);
    if (d < 0.5) { pathLines.push(null); continue; }
    const ya = heightAt(a.lon, a.lat), yb = heightAt(b.lon, b.lat);
    const pts = [], N = 80;
    for (let k = 0; k <= N; k++) {
      const u = k / N;
      pts.push(lerp(ax, bx, u), lerp(ya, yb, u) + Math.sin(Math.PI * u) * d * 0.22 + 0.05, lerp(az, bz, u));
    }
    const g = new LineGeometry(); g.setPositions(pts);
    const m = new LineMaterial({ color: 0xffc98a, linewidth: 2.2 * RS, transparent: true, opacity: 0.0, depthWrite: false, blending: THREE.AdditiveBlending, resolution: new THREE.Vector2(W * RS, H * RS) });
    const l = new Line2(g, m); l.computeLineDistances(); l.renderOrder = 22; l.frustumCulled = false;
    l.userData.N = N; scene.add(l);
    pathLines.push(l);
  }
}

let river = null;
async function buildRiver() {
  try {
    if (!CITY.river) return;
    const d = await loadJSON(`${BASE}/${CITY.river}`);
    const group = [];
    for (const line of d.lines) {
      const pts = [];
      for (const [lon, lat] of line) pts.push(wx(lon), heightAt(lon, lat) + 0.03, wz(lat));
      if (pts.length < 6) continue;
      const g = new LineGeometry(); g.setPositions(pts);
      const m = new LineMaterial({ color: 0x9fd8ff, linewidth: 3 * RS, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, resolution: new THREE.Vector2(W * RS, H * RS) });
      const l = new Line2(g, m); l.renderOrder = 23; l.frustumCulled = false; scene.add(l); group.push(l);
    }
    river = group;
  } catch (e) { river = null; }
}

// ---------------------------------------------------------------- post
const post = new THREE.ShaderMaterial({
  uniforms: {
    tColor: { value: null }, tDepth: { value: null }, res: { value: new THREE.Vector2(W * RS, H * RS) },
    near: { value: camera.near }, far: { value: camera.far }, focusDist: { value: 10 }, focusRange: { value: 6 },
    maxBlur: { value: 9 }, bgBlur: { value: 0 }, time: { value: 0 }, exposure: { value: 1 }, fade: { value: 1 },
    sunUV: { value: new THREE.Vector2(0, 0) }, sunVis: { value: 0 },
  },
  vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0., 1.); }`,
  fragmentShader: `
    uniform sampler2D tColor, tDepth; uniform vec2 res, sunUV; uniform float near, far, focusDist, focusRange, maxBlur, bgBlur, time, exposure, fade, sunVis;
    varying vec2 vUv;
    float lin(vec2 uv){ float z = texture2D(tDepth, uv).x*2.-1.; return 2.*near*far/(far+near - z*(far-near)); }
    float hash(vec2 p){ p = fract(p*vec2(443.897, 441.423)); p += dot(p, p.yx+19.19); return fract((p.x+p.y)*p.x); }
    vec3 aces(vec3 x){ return clamp((x*(2.51*x+.03))/(x*(2.43*x+.59)+.14), 0., 1.); }
    void main(){
      float d = lin(vUv);
      float coc = clamp(abs(d - focusDist) / focusRange, 0., 1.);
      coc = coc*coc;
      // tilt-shift-ish: soften the far top of frame a little more
      coc = max(coc, smoothstep(.62, 1., vUv.y)*.35);
      coc = max(coc, bgBlur);
      float r = coc * maxBlur;
      vec3 acc = vec3(0.); float ws = 0.;
      for (int i=0;i<20;i++){
        float fi = float(i);
        float rr = sqrt((fi+.5)/20.) * r;
        float a = fi*2.39996 + hash(vUv*res)*0.6;
        vec2 o = vec2(cos(a), sin(a))*rr/res;
        vec3 c = texture2D(tColor, vUv + o).rgb;
        float w = 1. + dot(c, vec3(.3,.5,.2))*1.5;
        acc += c*w; ws += w;
      }
      vec3 col = acc/ws;
      // volumetric light shafts from the sun position (screen space)
      if (sunVis > .001) {
        vec2 dir = (sunUV - vUv); float L = length(dir);
        vec2 st = dir / 30. ;
        vec2 p = vUv + st*hash(vUv*res+time);
        float il = 1., sum = 0.;
        for (int i=0;i<30;i++){
          vec3 c = texture2D(tColor, p).rgb;
          float b = max(dot(c, vec3(.33)) - .95, 0.);
          sum += b*il; il *= .95; p += st;
        }
        col += vec3(1.,.74,.45) * sum * .085 * sunVis * smoothstep(1.6, .1, L);
      }
      col *= exposure;
      col = aces(col);
      col = pow(col, vec3(1./2.2));
      float l = dot(col, vec3(.2126,.7152,.0722));
      col = mix(vec3(l), col, .82);                                     // restrained saturation
      col += vec3(-.018, .004, .03)*(1.-l)*(1.-l) + vec3(.045, .018, -.03)*l*l; // teal shadows, warm highlights
      col = mix(col, col*col*(3.-2.*col), .22);                         // gentle S-curve
      col = col*.955 + vec3(.022,.024,.028);                            // lifted blacks
      vec2 q = (vUv-.5)*vec2(1.0, 1.0);
      float v = smoothstep(.95, .28, length(q*vec2(1.25, 0.95)));
      col *= mix(.48, 1., v);
      col += (hash(vUv*res + fract(time*7.13)*100.) - .5) * .038;   // grain
      gl_FragColor = vec4(col*fade, 1.);
    }`,
  depthWrite: false, depthTest: false,
});
const postScene = new THREE.Scene();
const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), post);
quad.frustumCulled = false; postScene.add(quad);
const postCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

// ---------------------------------------------------------------- timeline
const segs = [];
{
  let t = 0;
  segs.push({ kind: 'intro', t0: t, t1: t + INTRO.dur }); t += INTRO.dur;
  NODES.forEach((n, i) => { segs.push({ kind: 'node', i, t0: t, t1: t + n.dur }); t += n.dur; });
  segs.push({ kind: 'outro', t0: t, t1: t + OUTRO.dur });
}
const nodeStart = i => segs[i + 1].t0;

function nodeHold(i, tau) {
  const n = NODES[i], c = n.cam, u = tau / n.dur;
  return {
    lon: c.lon ?? n.lon, lat: c.lat ?? n.lat,
    dist: c.dist * lerp(1, c.push, ease(u)),
    pitch: c.pitch + 3 * (ease(u) - 0.5),
    yaw: c.yaw + c.orbit * (u - 0.5),
  };
}
function introCam(tau) {
  const u = ease(tau / INTRO.dur), a = INTRO.cam0, b = INTRO.cam1;
  return { lon: lerp(a.lon, b.lon, u), lat: lerp(a.lat, b.lat, u), dist: Math.exp(lerp(Math.log(a.dist), Math.log(b.dist), u)), pitch: lerp(a.pitch, b.pitch, u), yaw: lerp(a.yaw, b.yaw, u) };
}
function outroHold(tau) {
  const c = OUTRO.cam, u = tau / OUTRO.dur;
  return { lon: c.lon, lat: c.lat, dist: c.dist * lerp(1, 1.06, u), pitch: c.pitch, yaw: c.yaw + 8 * (u - 0.5) };
}
function blend(a, b, w, bump) {
  let dy = ((b.yaw - a.yaw + 540) % 360) - 180;
  return {
    lon: lerp(a.lon, b.lon, w), lat: lerp(a.lat, b.lat, w),
    dist: Math.exp(lerp(Math.log(a.dist), Math.log(b.dist), w)) * (1 + bump * Math.sin(Math.PI * w)),
    pitch: lerp(a.pitch, b.pitch, w) + 16 * Math.min(1, bump) * Math.sin(Math.PI * w),
    yaw: a.yaw + dy * w,
  };
}
const FLY = 3.0;
function camAt(t) {
  const s = segs.find(s => t >= s.t0 && t < s.t1) || segs[segs.length - 1];
  const tau = t - s.t0;
  if (s.kind === 'intro') return introCam(tau);
  let prev, cur, fly = FLY;
  if (s.kind === 'node') {
    cur = nodeHold(s.i, tau);
    prev = s.i === 0 ? introCam(INTRO.dur) : nodeHold(s.i - 1, NODES[s.i - 1].dur);
  } else {
    cur = outroHold(tau); fly = 4.2;
    prev = nodeHold(NODES.length - 1, NODES[NODES.length - 1].dur);
  }
  if (tau >= fly) return cur;
  const sep = Math.hypot(wx(cur.lon) - wx(prev.lon), wz(cur.lat) - wz(prev.lat));
  const bump = clamp(sep / (prev.dist + cur.dist) * 0.9, 0, 1.4);
  // the hold motion starts at tau=0 so velocity is continuous when the flight ends
  return blend(prev, cur, smoother(tau / fly), bump);
}

function applyCam(c) {
  const tx = wx(c.lon), tz = wz(c.lat), ty = heightAt(c.lon, c.lat);
  const p = c.pitch * Math.PI / 180, y = c.yaw * Math.PI / 180;
  const off = new THREE.Vector3(-Math.sin(y) * Math.cos(p), Math.sin(p), Math.cos(y) * Math.cos(p)).multiplyScalar(c.dist);
  camera.position.set(tx + off.x, ty + off.y, tz + off.z);
  // keep the camera above the ground
  const gy = heightAt(c.lon + off.x / KX, c.lat - off.z / KZ) + 0.25;
  if (camera.position.y < gy) camera.position.y = gy;
  // aim slightly above the target so the marker sits a bit below centre
  camera.lookAt(tx, ty + c.dist * 0.02, tz);
  camera.updateMatrixWorld();
  return new THREE.Vector3(tx, ty, tz);
}

// ---------------------------------------------------------------- DOM overlay
const $ = id => document.getElementById(id);
const el = { cnt: $('cnt'), placeTop: $('placeTop'), year: $('year'), era: $('era'), head: $('head'), foot: $('foot'), title: $('title'),
  rule: $('title-rule'), body: $('body'), src: $('src'), card: $('card'), labels: $('labels'), intro: $('intro'), outro: $('outro'), black: $('black') };
const CN = ['', '壹', '贰', '叁', '肆', '伍', '陆', '柒', '捌', '玖', '拾', '拾壹', '拾贰', '拾叁', '拾肆', '拾伍'];

const imgs = {};
function preloadImages() {
  const ids = new Set();
  NODES.forEach(n => (n.images || []).forEach(im => ids.add(im.id)));
  return Promise.all([...ids].map(id => new Promise(res => {
    const im = new Image(); im.onload = () => { imgs[id] = im; res(); }; im.onerror = () => res(); im.src = `${BASE}/assets/img/${id}.jpg`;
  })));
}

function fitBox(im, maxW, maxH) {
  const r = Math.min(maxW / im.naturalWidth, maxH / im.naturalHeight);
  return [Math.round(im.naturalWidth * r), Math.round(im.naturalHeight * r)];
}

let builtFor = -1;
function buildNodeDom(i) {
  if (builtFor === i) return;
  builtFor = i;
  const n = NODES[i];
  el.cnt.textContent = `${String(i + 1).padStart(2, '0')} / ${NODES.length}`;
  el.placeTop.textContent = n.place;
  el.year.textContent = n.year; el.era.textContent = n.era;
  el.title.textContent = n.title;
  el.body.innerHTML = n.body.map(l => `<div>${l}</div>`).join('');
  el.src.textContent = '出处｜' + n.src;
  el.card.innerHTML = '';
  if (n.images) {
    n.images.forEach((spec, k) => {
      const im = imgs[spec.id];
      const box = document.createElement('div');
      box.className = 'cardimg'; box.style.cssText = 'position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;';
      if (im) {
        const [w, h] = fitBox(im, 840, 600);
        box.innerHTML = `<div class="imgwrap"><div class="clip" style="width:${w}px;height:${h}px"><img src="${im.src}" style="width:${w}px;height:${h}px"><div class="tone"></div></div></div>
          <div class="cap">${spec.caption}</div><div class="credit">${spec.credit}</div>`;
      }
      el.card.appendChild(box);
    });
  } else if (n.card) {
    const box = document.createElement('div');
    box.className = 'cardimg'; box.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;';
    box.innerHTML = `<div class="tcard"><div class="big">${n.card.big}</div><div class="seal"></div>${n.card.lines.map(l => `<div class="ln">${l}</div>`).join('')}</div>`;
    el.card.appendChild(box);
  }
  // map labels
  el.labels.innerHTML = '';
  const mk = (cls, name, sub) => { const d = document.createElement('div'); d.className = 'lab ' + cls; d.innerHTML = `<div class="name">${name}</div>${sub ? `<div class="sub">${sub}</div>` : ''}${cls === 'main' || cls === 'county' ? '<div class="stem"></div>' : ''}`; el.labels.appendChild(d); return d; };
  labelEls = [{ d: mk('main', n.place, n.where), lon: n.lon, lat: n.lat, kind: 'main' }];
  if (n.highlights) n.highlights.forEach(c => labelEls.push({ d: mk('county', c.name, ''), lon: c.lon, lat: c.lat, kind: 'county' }));
}
let labelEls = [];
const ambient = CITY.ambient || [];
let ambientEls = null;

const tmpV = new THREE.Vector3();
function project(x, y, z) {
  tmpV.set(x, y, z).project(camera);
  return { x: (tmpV.x * 0.5 + 0.5) * W, y: (-tmpV.y * 0.5 + 0.5) * H, ok: tmpV.z < 1 && tmpV.z > -1 };
}

function setOpacity(e, o, dy = 0) { e.style.opacity = o.toFixed(3); e.style.transform = dy ? `translateY(${dy.toFixed(1)}px)` : ''; }

// ---------------------------------------------------------------- frame
let mats = [];
let mist;
function renderAt(t) {
  const s = segs.find(s => t >= s.t0 && t < s.t1) || segs[segs.length - 1];
  const tau = t - s.t0;
  const c = camAt(t);
  const target = applyCam(c);

  mats.forEach(m => { if (m.uniforms.time) m.uniforms.time.value = t; });
  mist.children.forEach(p => { p.material.uniforms.time.value = t; });

  // markers: visited ones keep a faint ring; the active one glows with a beam
  const activeIdx = s.kind === 'node' ? s.i : -1;
  markers.forEach(m => { m.ring.material.uniforms.vis.value = 0; m.beam.material.uniforms.vis.value = 0; m.ring.material.uniforms.live.value = 0; });
  NODES.forEach((n, i) => {
    const m = markerFor(n.lon, n.lat);
    const st = nodeStart(i);
    if (t < st + 1.2) return;
    const isActive = i === activeIdx || (activeIdx > i && NODES[activeIdx].lon === n.lon && NODES[activeIdx].lat === n.lat);
    const age = t - st - 1.2;
    const scale = isActive ? c.dist * 0.16 : Math.max(0.9, c.dist * 0.035);
    m.ring.scale.set(scale, scale, 1);
    const u = m.ring.material.uniforms;
    if (isActive) {
      u.vis.value = Math.max(u.vis.value, smooth(age / 1.0) * (s.kind === 'node' ? 1 - ramp(tau, NODES[activeIdx].dur - 0.6, NODES[activeIdx].dur + 0.4) * 0.6 : 1));
      u.live.value = 1; u.t.value = age;
      m.beam.material.uniforms.vis.value = smooth(age / 1.2);
      const bh = c.dist * 0.17;
      m.beam.scale.set(c.dist * 0.0022, bh, c.dist * 0.0022);
      m.beam.position.y = m.y + bh / 2;
    } else {
      u.vis.value = Math.max(u.vis.value, s.kind === 'outro' ? 0.55 + 0.45 * ramp(tau, 1, 3) : 0.42);
      u.live.value = Math.max(u.live.value, s.kind === 'outro' ? ramp(tau, 2, 4) : 0); u.t.value = age;
    }
  });
  // golden path: draws during each flight, then stays dim
  pathLines.forEach((l, k) => {
    if (!l) return;
    const i = k + 1, st = nodeStart(i);
    const p = clamp((t - st) / (FLY * 0.95), 0, 1);
    l.geometry.instanceCount = Math.max(1, Math.floor(p * l.userData.N));
    const live = i === activeIdx ? 1 : 0;
    l.material.opacity = t < st ? 0 : (live ? 0.85 : (s.kind === 'outro' ? 0.25 + 0.5 * ramp(tau, 1.5, 4) : 0.22));
    l.material.linewidth = (live ? 2.4 : 1.6) * RS;
  });
  if (river) {
    const rn = NODES[activeIdx];
    const v = rn && rn.river ? ramp(tau, 1.6, 3.6) * (1 - ramp(tau, rn.dur - 1, rn.dur)) : 0;
    river.forEach(l => { l.material.opacity = v * 0.75; });
  }

  // atmosphere thins out as the camera climbs so wide shots stay readable
  terrainMats.forEach(m => { m.uniforms.fogDensity.value = 0.42 / (c.dist + 22); });
  const mistAmt = clamp(1.25 - c.dist / 90, 0.12, 1);
  mist.children.forEach(p => { p.material.uniforms.amt.value = mistAmt; });

  // depth of field focus on the target
  post.uniforms.focusDist.value = camera.position.distanceTo(target);
  post.uniforms.focusRange.value = Math.max(2.5, c.dist * 0.75);
  post.uniforms.maxBlur.value = 10 * RS;
  post.uniforms.time.value = t;

  // sun on screen → light shafts
  const sp = SUN.clone().multiplyScalar(2000).add(camera.position).project(camera);
  post.uniforms.sunUV.value.set(sp.x * 0.5 + 0.5, sp.y * 0.5 + 0.5);
  const inFront = sp.z < 1;
  const edge = Math.max(Math.abs(sp.x), Math.abs(sp.y));
  post.uniforms.sunVis.value = inFront ? clamp(1.8 - edge, 0, 1) : 0;

  // ---------------- overlay
  let headO = 0, footO = 0, cardO = 0, bg = 0, introO = 0, outroO = 0, labO = 0, black = 0;
  el.intro.style.opacity = 0; el.outro.style.opacity = 0;
  if (s.kind === 'intro') {
    if (!ambientEls) { ambientEls = ambient.map(a => { const d = document.createElement('div'); d.className = 'lab ambient'; d.innerHTML = `<div class="name">${a.name}</div>`; document.getElementById('labels').appendChild(d); return { d, ...a }; }); }
    el.intro.querySelector('.t').textContent = INTRO.title;
    el.intro.querySelector('.s').textContent = INTRO.sub;
    introO = win(tau, 1.2, 3.0, 7.0, 8.6);
    el.intro.style.opacity = introO.toFixed(3);
    el.intro.querySelector('.t').style.letterSpacing = (0.3 + 0.08 * (1 - ease(tau / INTRO.dur))).toFixed(3) + 'em';
    el.intro.querySelector('.r').style.width = (520 * ramp(tau, 2.2, 4.4)).toFixed(0) + 'px';
    el.intro.querySelector('.s').style.opacity = ramp(tau, 3.0, 4.6).toFixed(3);
    black = 1 - ramp(tau, 0, 1.6);
  } else if (s.kind === 'node') {
    const n = NODES[s.i];
    if (ambientEls) { ambientEls.forEach(a => a.d.remove()); ambientEls = null; }
    buildNodeDom(s.i);
    const D = n.dur;
    headO = win(tau, 1.0, 2.0, D - 0.9, D - 0.2);
    footO = win(tau, 1.6, 2.4, D - 0.9, D - 0.2);
    el.title.style.opacity = ramp(tau, 1.7, 2.6);
    el.title.style.transform = `translateY(${(1 - ease((tau - 1.7) / 1.2)) * 18}px)`;
    el.rule.style.width = (360 * ease((tau - 2.0) / 1.4)).toFixed(0) + 'px';
    [...el.body.children].forEach((d, k) => { const a = 2.4 + k * 0.42; d.style.opacity = ramp(tau, a, a + 0.8); d.style.transform = `translateY(${(1 - ease((tau - a) / 1.0)) * 14}px)`; });
    el.src.style.opacity = ramp(tau, 3.6, 4.4) * 0.95;
    labO = win(tau, 1.6, 2.4, 3.6, 4.2) + win(tau, D - 2.3, D - 1.8, D - 0.9, D - 0.4);
    // card
    const c0 = 3.9, c1 = D - 2.0;
    cardO = win(tau, c0, c0 + 0.9, c1 - 0.6, c1 + 0.2);
    bg = cardO;
    const boxes = [...el.card.children];
    boxes.forEach((b, k) => {
      let o = 1;
      if (boxes.length > 1) { const mid = (c0 + c1) / 2; o = k === 0 ? 1 - ramp(tau, mid - 0.4, mid + 0.4) : ramp(tau, mid - 0.4, mid + 0.4); }
      b.style.opacity = o.toFixed(3);
      const img = b.querySelector('img');
      if (img) img.style.transform = `scale(${(1.0 + 0.07 * ease((tau - c0) / (c1 - c0 + 1))).toFixed(4)})`;
    });
    el.card.style.transform = `translateY(${((1 - ease((tau - c0) / 1.2)) * 40).toFixed(1)}px) scale(${(1.02 - 0.02 * ease((tau - c0) / 1.6)).toFixed(4)})`;
  } else {
    if (ambientEls) { ambientEls.forEach(a => a.d.remove()); ambientEls = null; }
    el.labels.innerHTML = ''; labelEls = []; builtFor = -1;
    el.outro.querySelector('.q').textContent = OUTRO.question;
    outroO = ramp(tau, 3.0, 4.6) * (1 - ramp(tau, OUTRO.dur - 1.6, OUTRO.dur - 0.5));
    el.outro.style.opacity = outroO.toFixed(3);
    el.outro.querySelector('.r').style.width = (420 * ramp(tau, 3.6, 5.6)).toFixed(0) + 'px';
    black = ramp(tau, OUTRO.dur - 1.4, OUTRO.dur - 0.15);
    bg = 0.15 * ramp(tau, 3, 5);
  }
  setOpacity(el.head, headO);
  setOpacity(el.foot, footO);
  el.card.parentElement.style.opacity = cardO.toFixed(3);
  el.black.style.opacity = black.toFixed(3);
  post.uniforms.bgBlur.value = bg * 0.55;
  terrainMats.forEach(m => { m.uniforms.dim.value = 1 - bg * 0.28; });

  // labels follow the 3D anchor
  labelEls.forEach(L => {
    const y = heightAt(L.lon, L.lat);
    const p = project(wx(L.lon), y, wz(L.lat));
    let o = L.kind === 'main' ? labO : (NODES[s.i]?.highlights ? win(tau, 3.0, 3.8, NODES[s.i].dur - 1.2, NODES[s.i].dur - 0.4) * (1 - cardO) : 0);
    if (!p.ok) o = 0;
    L.d.style.left = p.x.toFixed(1) + 'px'; L.d.style.top = (p.y - 6).toFixed(1) + 'px'; L.d.style.opacity = o.toFixed(3);
  });
  if (ambientEls) ambientEls.forEach(a => {
    const p = project(wx(a.lon), 0.3, wz(a.lat));
    a.d.style.left = p.x.toFixed(1) + 'px'; a.d.style.top = p.y.toFixed(1) + 'px';
    a.d.style.opacity = (p.ok ? win(tau, 5.2, 6.4, 7.6, 8.6) * 0.9 : 0).toFixed(3);
  });
  // highlight rings (e.g. sub-districts) for nodes that list them
  countyMarks.forEach(m => {
    const n = NODES[activeIdx];
    const v = n && m.node === activeIdx ? win(tau, 2.6, 3.6, n.dur - 1.0, n.dur) : 0;
    m.ring.material.uniforms.vis.value = v; m.ring.material.uniforms.live.value = v; m.ring.material.uniforms.t.value = tau;
    const sc = c.dist * 0.07; m.ring.scale.set(sc, sc, 1);
  });

  // ---------------- draw
  renderer.setRenderTarget(rt);
  renderer.clear();
  renderer.render(scene, camera);
  // copy depth via a second pass of depth-only render into rtDepth (MSAA targets cannot be sampled for depth)
  renderer.setRenderTarget(rtDepth);
  renderer.clear();
  scene.overrideMaterial = depthOnly;
  camera.layers.set(1);
  renderer.render(scene, camera);
  camera.layers.set(0);
  scene.overrideMaterial = null;
  post.uniforms.tColor.value = rt.texture;
  post.uniforms.tDepth.value = rtDepth.depthTexture;
  renderer.setRenderTarget(null);
  renderer.render(postScene, postCam);
}
const depthOnly = new THREE.MeshBasicMaterial({ colorWrite: false });
let terrainMats = [];
const countyMarks = [];

// ---------------------------------------------------------------- boot
async function boot() {
  const M = `${BASE}/assets/map`;
  const grid = await loadJSON(`${M}/grid.json`);
  const [coreH, wideH, satHi, satLo, water] = await Promise.all([
    loadF32(`${M}/core_h.bin`), loadF32(`${M}/wide_h.bin`),
    loadTex(`${M}/sat_hi_4k.jpg`), loadTex(`${M}/sat_lo_2k.jpg`), loadTex(`${M}/water.png`),
  ]);
  document.title = CITY.title;
  document.getElementById('mapcredit').textContent = CITY.mapCredit || '';
  CORE = { meta: grid.core, h: coreH, n: grid.core.n };
  const mCore = terrainMaterial(satHi, water, false), mWide = terrainMaterial(satLo, null, true);
  terrainMats = [mCore, mWide];
  const tCore = buildTerrain(grid.core, coreH, grid.core.n, mCore, 0);
  const tWide = buildTerrain(grid.wide, wideH, grid.wide.n, mWide, -0.12);
  tCore.layers.enable(1); tWide.layers.enable(1);
  scene.add(tCore, tWide);
  scene.add(buildSky());
  mist = buildMist(); scene.add(mist);
  mats = [mCore, mWide];
  NODES.forEach(n => markerFor(n.lon, n.lat));
  NODES.forEach((nd, ni) => (nd.highlights || []).forEach(cn => {
    const ring = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), ringMaterial());
    ring.rotation.x = -Math.PI / 2; ring.renderOrder = 20;
    ring.position.set(wx(cn.lon), heightAt(cn.lon, cn.lat) + 0.04, wz(cn.lat));
    scene.add(ring); countyMarks.push({ ring, node: ni });
  }));
  buildPaths();
  await buildRiver();
  await preloadImages();
  await document.fonts.ready;
  window.renderAt = renderAt;
  window.TOTAL = TOTAL; window.FPS = FPS;
  window.segments = segs.map(s => ({ kind: s.kind, i: s.i, t0: s.t0, t1: s.t1 }));
  window.ready = true;
}
boot().catch(e => { window.bootError = String(e && e.stack || e); console.error(e); });
