---
id: IMPL-FRONTEND-ASSETS-001
kind: implementation_note
status: accepted
related: [FR-002, FR-004, FR-006]
---

# Frontend asset inventory

## Integrated assets

- Brand mark: `starter/web/public/brand/hitrendy-mark.svg`.
- Home and template catalog: `starter/web/public/templates/`.
- Dashboard folder: `starter/web/public/icons/folder-violet-papirus-hitrendy.svg`.

The template images are local demo assets. The catalog still receives its
business data from the templates API; local presentation metadata supplies
tags, category labels and aspect ratios without extending the API schema. The
eight seed IDs (`tpl_*`) are mapped to local images because their historical
`/static/thumbnails/*.svg` paths are not served by the integrated web app.

## Papirus attribution

The folder icon is an adapted Papirus Dark asset. Its notice and GPL-3.0 text
are preserved in `starter/web/public/licenses/` so the distributed frontend
retains the source attribution and license text.

## Replacement path

Production template records can replace local thumbnails by returning a stable
`thumbnail_url`; unknown or failed images show an accessible local fallback.
Search, filtering and responsive proportions remain in the frontend
presentation adapter until server-side catalog search is added.
