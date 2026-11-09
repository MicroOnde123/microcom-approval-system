# November 2026 manual build assets

Version 3.0 is finalized as synchronized English/French text-based guides. No genuine application screenshots are available in this checkout. Only the Microcom logo is embedded; no mock interfaces, pending image panels or planned pointer pages appear in the manuals.

## Build and validate

From the repository root, using the existing virtual environment:

```powershell
.\venv\Scripts\python.exe -B docs/update_november_manuals.py
.\venv\Scripts\python.exe -B docs/manual-assets/validate_guides.py docs/manual-assets/november-2026-review
```

The updater reads the current Git revision and reuses `build_guides.py` as its bilingual content and portrait-layout base. The November overlay updates the procedures, removes visual placeholders, and performs two layout passes for chapter contents references. Do not run the legacy base builder directly for publication: its standalone entry point predates the finalized overlay. The older `docs/build_user_manuals.py` requires a different capture manifest and missing PNG files; it is not the active build path.

Candidates are written to `november-2026-review/`. Validate them before replacing the documentation-root PDFs and Markdown. Copy the candidate capture manifest to this directory and the candidate screenshot checklist to `docs/`, then run:

```powershell
.\venv\Scripts\python.exe -B docs/manual-assets/validate_guides.py
```

Required assets: `build_guides.py`, `microcom-logo.png`, `capture-manifest.json`, `validate_guides.py`, and `docs/update_november_manuals.py`. `document-checks.json` records the structural checks. See `docs/user-manual-validation.md` for code trace and runtime limitations.

`docs/manual-screenshot-checklist.md` and the manifest are a separate, nonblocking illustration backlog. Existing local candidate directories, previous-edition backups and pending SVGs are retained locally but are not required build inputs or proposed commit contents.

Validation checks parsing, Unicode, pagination, chapter contents references, links and text baselines. ReportLab layout checks do not replace a paper-printer check or full visual review. Documentation builds do not import Django, contact the network or access databases. No browser dependencies are required.
