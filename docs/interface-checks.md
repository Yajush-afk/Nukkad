# Interface checks

The regular CI suite runs Python interface contracts and dependency-free Node
checks for navigation and decorative motion. `tests/browser-smoke.cjs` additionally
exercises real Chromium: desktop/mobile layouts, keyboard navigation, Back/Forward,
scroll restoration, unsaved fields, direct URLs, reduced motion and unavailable WebGL.

Use a new empty data directory for the primary browser server. These checks expect
an unconfigured neighbourhood and must not run against the personal server.

```sh
NUKKAD_DATA_DIR="$(mktemp -d /tmp/nukkad-interface-data.XXXXXX)" uv run nukkad serve --port 8003
```

In another terminal, install browser tooling outside the project:

```sh
npm install --prefix /tmp/nukkad-browser-check playwright@1.64.0 --no-audit --no-fund
/tmp/nukkad-browser-check/node_modules/.bin/playwright install chromium
NODE_PATH=/tmp/nukkad-browser-check/node_modules NUKKAD_BROWSER_URL=http://localhost:8003 node tests/browser-smoke.cjs
```

Optionally set `NUKKAD_MAP_BROWSER_URL` to a second server using an isolated copy
of saved map data. This enables real-map disclosure, zoom and pan checks without
saving any changes. `NUKKAD_BROWSER_OUTPUT` chooses the ignored screenshot directory.
No app runtime dependency on Playwright is introduced.

## Working-page feedback, suggestions and place editing

Automated tests cover queued/persistent feedback, paused timers, truthful clipboard success/failure, offline suggestion indexing, alias identity, provider limits/failures, obsolete queries and selection revision guards. Isolated browser checks verified mobile notifications preserve scroll, keyboard suggestion selection works while online results fail, and selecting a location does not activate it.

Custom-place editing now sits immediately below map details. A map entrance adjustment retains name/type/observation and clears public confirmation. Returning from Home retains the unsaved draft. Synthetic browser checks exercise duplicate submission and a delayed save while another place is selected. No coordinate controls are exposed; coordinates remain internal. Outside-area creation is rejected before graph loading. Reports preserve correction history and canonical identity.
