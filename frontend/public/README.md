# Brand assets

Generated from the charter mark, not hand-drawn twice. The geometry lives in
`components/Mark.tsx`; `scripts/build_brand.py` renders the raster versions from
the same numbers, so the tab icon and the in-page logo cannot drift apart.

| File | Where it is used |
| --- | --- |
| `icon.svg` | modern browsers, any size, sharp |
| `favicon.ico` | 16, 24, 32, 48 — the small two use a simplified mark |
| `apple-icon.png` | iOS home screen, 180×180, opaque |
| `og.png` | link previews on X and elsewhere, 1200×630 |

**Below 24px the mark drops its horizontal segments.** The full mark is an
ellipse plus six lines; at 16 pixels those land on the same three rows and turn
to mush — checked by rendering it, not assumed. A mark nobody can read in a
browser tab is not more faithful for having kept every stroke.

## sphere.mp4

Drop a video here and the homepage plays it instead of the WebGL field. No code
change and no flag: `components/Hero.tsx` probes for the file and falls back
when it is absent.

- **Square**, 1:1. It renders at 520×520 and is object-contained.
- **Loop seamlessly** — it plays muted on repeat forever.
- **Keep it small.** Every visitor downloads it; over ~3MB, cut the duration or
  the bitrate rather than the resolution.
- Black background, `#050506`, so it sits on the page without an edge.

A rendered loop cannot represent live state, so it is marked `aria-hidden` and
the real numbers stay in the text underneath. The WebGL field is the one bound
to activity, novelty and confidence — if that binding matters more than the
render, leave the video out.
