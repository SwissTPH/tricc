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

## Option B: Zensical-based site (better navigation/search)

Use this if you want polished navigation and search. The project uses
[Zensical](https://zensical.org/) (the successor to Material for MkDocs, built
by the same team) to generate a static site from the existing `mkdocs.yml`.

High-level steps:

1. Ensure `mkdocs.yml` is present (Zensical reads it directly).
2. Install Zensical: `pip install zensical`.
3. Configure a GitHub Actions workflow to build/deploy to Pages.

## Difficulty estimate

- Basic Pages from `/docs`: easy.
- Zensical + CI deployment: moderate.
- Custom theme/plugins/private auth requirements: higher complexity.

## Recommended path

Start with Option A now, then move to Zensical once content stabilizes.
