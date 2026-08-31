Vendored from npm `three@0.185.1` (MIT).

- `build/three.module.min.js` — ESM 入口（会再 import 同目录 `three.core.min.js`，两者必须同放）
- `build/three.core.min.js` — 核心实现
- `examples/jsm/controls/OrbitControls.js` — addon（`from 'three'`）
- `LICENSE` — MIT

Do not concatenate into application JS. Viewer loads via import map.
