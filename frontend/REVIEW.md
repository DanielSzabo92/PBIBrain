# Frontend review

## Current design

The main path is Search → Inspector → scoped Graph. Each request is model- and report-aware, and the graph shows server truncation plainly instead of silently replacing it with a client-side subset.

Configuration only writes project name and source inputs in normal use. Database and identity-map locations are visible for diagnosis but read-only because the server loads them at startup.

## Later work

- Add documentation export after the canonical object/evidence contract is stable.
- Add graph layout persistence only if users need saved investigation views.
