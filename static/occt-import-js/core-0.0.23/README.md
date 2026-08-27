Vendored from npm `occt-import-js@0.0.23` (LGPL-2.1, OpenCascade WASM).

Keep these three files as siblings so the official worker can `importScripts('occt-import-js.js')`
and `locateFile` can resolve `occt-import-js.wasm`:

- `occt-import-js.js`
- `occt-import-js.wasm`
- `occt-import-js-worker.js`
- `LICENSE`

Do not minify/concatenate the glue JS into application code (LGPL dynamic load).
