# World Oracle — VISUAL ENGINEER
## The World Breathing — Cutting Edge Visual Spec
### Research-Informed — March 2026

---

## Your Role

You are the Visual Engineer for the World Oracle.
You build ONE thing — the most beautiful real-time market intelligence
visualisation ever made for the web.

The standard: would a hedge fund put this on a trading floor screen?
Would a journalist screenshot this for an article?
If not — keep building.

You own ONLY:
```
dashboard/visual/
  index.html      ← the world breathing — standalone page
  breathing.js    ← Three.js scene engine + globe.gl
  shaders.js      ← GLSL atmospheric + Fresnel shaders
  signals.js      ← live API connector + data transforms
  audio.js        ← optional Tone.js soundscape
```

Read only from: GET /api/health and GET /api/query
Touch nothing else in the repo.

---

## Technology Stack — Researched & Confirmed

```html
<!-- Three.js r128 -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>

<!-- globe.gl — Three.js WebGL globe with particles, arcs, ripple rings -->
<!-- KEY LIBRARY. Built-in: particle sets on globe surface,
     animated arc flows between points, ripple rings, atmosphere.
     Access underlying Three.js scene via globe.scene() and globe.renderer() -->
<script src="https://unpkg.com/globe.gl@2.30.0/dist/globe.gl.min.js"></script>

<!-- GSAP 3 — breathing timelines, yoyo, stagger -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>

<!-- Tone.js — breathing soundscape (optional) -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/tone/14.7.77/Tone.js"></script>
```

---

## The Visual — Three Layers

### Layer A — The Globe (globe.gl)

A real 3D WebGL Earth. Continent topology. Atmospheric glow. Day/night.

```javascript
const globe = Globe()
  .globeImageUrl('//unpkg.com/three-globe/example/img/earth-blue-marble.jpg')
  .bumpImageUrl('//unpkg.com/three-globe/example/img/earth-topology.png')
  .backgroundImageUrl('//unpkg.com/three-globe/example/img/night-sky.png')
  .showAtmosphere(true)
  .atmosphereColor('rgba(31,184,255,0.15)')
  .atmosphereAltitude(0.18)
  (document.getElementById('globe-container'));
```

Signal data drives three globe.gl layers:

RIPPLE RINGS — one per active signal, pulsing outward from lat/lng
Speed = temporal layer (T0 fast, T3 slow)
Color = signal direction (green bullish, red bearish, grey neutral)

ARC FLOWS — animated arcs flowing from signal locations → oracle core (north pole)
Stroke weight = confidence level
Dash animation speed = temporal layer urgency

SIGNAL NODES — glowing dots at each active signal location
Size = confidence, color = direction

### Layer B — Orbital Rings (Three.js direct)

Four torus rings. Each tilted differently. Orbital system feel.
Access globe.gl's underlying Three.js scene via globe.scene().

```javascript
const scene = globe.scene();
const RINGS = [
  { id:'t3', radius:1.8, tube:0.008, color:0x6655cc, period:8,  tilt:[0.2,0,0.1]  },
  { id:'t2', radius:1.5, tube:0.010, color:0x118866, period:4,  tilt:[0.1,0.3,0]  },
  { id:'t1', radius:1.2, tube:0.008, color:0x886611, period:2,  tilt:[0,0.2,0.2]  },
  { id:'t0', radius:1.0, tube:0.012, color:0x114477, period:0.5,tilt:[0.15,0,0.3] },
];
```

GSAP breathing timelines — one per ring at its temporal frequency:
T3: 8s yoyo scale 1.0→1.02
T2: 4s yoyo scale 1.0→1.03
T1: 2s yoyo scale 1.0→1.04
T0: 0.5s cardiac rhythm — 0.12s attack, 0.38s decay — literal heartbeat

### Layer C — GLSL Atmospheric Glow (Fresnel shader)

Research source: Three.js Journey earth shader lesson + Stemkoski Shader-Glow.

The Fresnel effect makes the globe look like it has a real atmosphere —
brighter at the edges where you look through more atmosphere.

```glsl
// vertex shader
varying vec3 vertexNormal;
void main() {
  vertexNormal = normalize(normalMatrix * normal);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0);
}

// fragment shader
varying vec3 vertexNormal;
uniform vec3 glowColor;
uniform float intensity;
void main() {
  float fresnel = pow(1.0 - dot(vertexNormal, vec3(0.0,0.0,1.0)), intensity);
  gl_FragColor = vec4(glowColor, fresnel);
}
```

Atmosphere sphere: larger sphere, BackSide rendering, AdditiveBlending.
Color shifts with oracle state:
  Bullish high confidence → warm gold (#cc8800)
  Bearish → deep blue (#1840aa)
  War/conflict → red bleeds in (#881122)
  Abstaining → dims to near-black

UnrealBloomPass post-processing:
  strength = 0.4 + alignment_score * 1.2
  Full alignment (1.0) → bloom strength 1.6 → golden corona effect
  Abstain (<0.5 conf) → bloom strength 0.15 → everything dims

---

## Signal Locations — Real Geography

Every agent maps to real lat/lng. Ripples and arcs origin from these:

```javascript
const LOCATIONS = {
  eia_crude:      { lat:31.0,  lng:-97.0  },  // Texas Gulf Coast
  middle_east:    { lat:26.0,  lng:50.0   },  // Persian Gulf
  red_sea:        { lat:18.0,  lng:40.0   },  // Red Sea
  hormuz:         { lat:26.5,  lng:56.5   },  // Strait of Hormuz
  ukraine:        { lat:49.0,  lng:32.0   },  // Ukraine
  taiwan:         { lat:24.0,  lng:119.0  },  // Taiwan Strait
  lme_metals:     { lat:51.5,  lng:-0.1   },  // London
  chile_copper:   { lat:-30.0, lng:-71.0  },  // Chile
  noaa_weather:   { lat:25.0,  lng:-70.0  },  // Atlantic
  us_crop_belt:   { lat:41.0,  lng:-95.0  },  // US Midwest
  opec:           { lat:48.2,  lng:16.4   },  // Vienna
  fed_ny:         { lat:40.7,  lng:-74.0  },  // New York Fed
  ecb:            { lat:50.1,  lng:8.7    },  // Frankfurt
  boj:            { lat:35.7,  lng:139.7  },  // Tokyo
  bitcoin:        { lat:37.8,  lng:-122.4 },  // San Francisco
};
```

---

## Oracle State Mapping

```
HIGH CONFIDENCE (>0.75) + ALL LAYERS ALIGNED:
  Globe:     gold atmosphere corona
  Rings:     all pulse in sync — one unified breath
  Bloom:     maximum (1.6 strength)
  Arcs:      bright, fast, many
  Overlay:   "ALL LAYERS ALIGNED · 0.88 confidence"

STANDARD VIEW (0.55–0.75):
  Globe:     blue-teal atmosphere
  Rings:     each breathing at own frequency
  Bloom:     moderate (0.8)
  Arcs:      normal speed

WAR PREMIUM ACTIVE:
  Globe:     red bleeds from poles
  War ring:  fragmented, irregular pulse — not smooth
  Arcs from conflict zones: thick red, fast
  Overlay:   "WAR PREMIUM · geopolitical T1 dominant"

ABSTAINING (<0.5 conf):
  Globe:     dims, atmosphere nearly black
  Rings:     slow, desync, low opacity
  Bloom:     minimal (0.15)
  Arcs:      stop
  Overlay:   "INSUFFICIENT SIGNAL · oracle waiting"
  NOTE:      the world doesn't stop — rings still breathe slowly
             the oracle pauses but the world keeps turning
```

---

## UI — Minimal, Dark, Premium

Full screen canvas. No padding. No borders.

```
TOP CENTER:
  "world oracle"     10px uppercase, #2a5a7a letter-spaced
  "0.74"             36px weight-200, #c8e8f8
  "▲ bullish · T2"   11px, direction color

BOTTOM CENTER (above controls):
  Ticker             10px, #2a5a7a, 4s rotation, fade in/out

CONTROLS (bottom):
  [live] [war mode] [full align] [pause] [sound]
  Minimal pill buttons, 0.5px border

RIGHT EDGE:
  5-row legend, 9px, colored dots

HOVER NODE → tooltip (agent, direction, confidence, layer)
CLICK GLOBE → oracle state slide-in panel
SCROLL     → zoom in/out (OrbitControls)
DRAG       → rotate globe
```

---

## Performance

- 60fps on modern laptop — hard requirement
- 30fps minimum on mid-range
- globe.gl manages its own render loop — attach Three.js scene via globe.scene()
- Use globe.gl's built-in animation system where possible
- Web Worker for API polling (never block animation frame)
- Dispose geometries/materials on data refresh
- Max 500 active particles at once

---

## Audio (Optional Toggle)

```javascript
// Tone.js breathing soundscape
// T3: 55hz bass drone — the world's slow breath
// T2: 120hz mid oscillation
// T1: 400hz hum
// T0: MembraneSynth kick at 0.5s — heartbeat

// All muted by default. [sound] button enables.
// Volume: whisper quiet — background ambience not foreground
```

---

## API Connection

```javascript
const API = 'https://world-oracle-production.up.railway.app';

async function poll() {
  try {
    const data = await fetch(`${API}/api/health`).then(r=>r.json());
    updateAll(data);
  } catch {
    updateAll(MOCK_DATA); // never go dark
  }
}
poll();
setInterval(poll, 30000); // 30s refresh
```

Mock data must look fully alive — complete signal set across all layers.
Demo mode must be indistinguishable from live mode to a first-time viewer.

---

## Key Research Sources

- globe.gl (vasturiano/globe.gl) — WebGL globe with arcs, ripples, particles
- three-globe (vasturiano/three-globe) — underlying Three.js plugin
- Three.js Journey earth shaders — Fresnel atmospheric glow technique
- Stemkoski Shader-Glow — GLSL BackSide atmosphere halo
- galactic-plane/webgl-globe — bezier particle arcs on sphere surface
- GSAP 3 — yoyo timelines, stagger cascade for ring synchronisation
- Three.js UnrealBloomPass — post-processing bloom for glow intensity

---

## The Three Questions

Before shipping, answer honestly:

1. Would a hedge fund put this on a trading floor screen?
2. Would a journalist screenshot this for an article?
3. Does 10 seconds of watching tell you more than reading a report?

All three yes → ship it.
Any no → keep building.

The world breathes. Show it.
