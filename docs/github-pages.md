# Publishing with GitHub Pages

Publishing this `docs/` folder is straightforward.

## Option A: Simple branch publishing (fastest)

1. Push docs to your repository (for example on `main` or `develop`).
2. In GitHub repo settings, open **Pages**.
3. Set source to:
   - Branch: your chosen branch
   - Folder: `/docs`
4. Save and wait for deployment.

This is easiest and requires no static-site tooling.

## Option B: MkDocs-based site (better navigation/search)

Use this if you want polished navigation and search.

High-level steps:

1. Add `mkdocs.yml`.
2. Install MkDocs (and optional theme).
3. Configure a GitHub Actions workflow to build/deploy to Pages.

This is still manageable but adds maintenance overhead.

## Difficulty estimate

- Basic Pages from `/docs`: easy.
- MkDocs + CI deployment: moderate.
- Custom theme/plugins/private auth requirements: higher complexity.

## Recommended path

Start with Option A now, then move to MkDocs once content stabilizes.
