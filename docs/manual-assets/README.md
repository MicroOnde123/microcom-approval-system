# User manual evidence

These are authentic screenshots from the existing Django application served over loopback, backed by the verified disposable local PostgreSQL cluster, using sanitized training data. They are not mocked template previews or AI-generated interfaces.

- `en/raw/`, `fr/raw/`: unmodified browser captures.
- `en/annotated/`, `fr/annotated/`: external numbered pointers and existing-state highlights; selected field views are cropped for legibility.
- `capture-manifest.json`: source revision, relative route, actual page title, target geometry, figure numbers, crops and raw SHA-256 values. No passwords, session cookies or confirmation tokens.
- `build-results.json`: PDF filenames, page counts and SHA-256 values.
- `qa-results.json`: documentation verification results, when built.

Private browser profiles/session metadata are **not** in this directory or Git. Screenshots use a training administrator and cannot establish operational roles' authorization. Missing workflows are tracked in `../manual-screenshot-checklist.md`.

Build the manuals offline from existing captures with `venv\Scripts\python.exe docs\build_user_manuals.py`. It uses the installed ReportLab, Pillow and pypdf packages and the existing Microcom logo. It performs no database or network access. It must not be treated as a screenshot-capture command or a substitute for release approval.
