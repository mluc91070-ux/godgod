# Brand assets

**Caching.** Files here are served by Next with `max-age=0, must-revalidate` by
default, because their names carry no content hash — for the 830KB hero video
that meant a blocking round trip on every visit. `next.config.mjs` gives the
video and poster a day of freshness with a week of stale-while-revalidate, and
the icons a week with a month. Replacing a file reaches everyone within that
window without renaming it.

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

## sphere.mp4 / sphere.webm — removed

The homepage hero was a 15-second video loop of a sphere. It is gone, and the
three files with it: `sphere.mp4` (989KB), `sphere.webm` (812KB) and
`sphere-poster.jpg`.

It looked better than the live field did. It was still the wrong thing on this
site. A fixed loop cannot represent state, so it was `aria-hidden` and every
claim had to be carried by the numbers underneath — and it animated identically
whether the system had run four cycles that hour or had been dead since
Tuesday. On a page whose argument is that every visual parameter is bound to a
real value, that is the one thing it could not be.

`components/LiveField.tsx` renders `FieldSphere` instead: 24,000 points, with
rotation bound to activity, surface to novelty, core radius to confidence,
colour to the state machine, and a front crossing the shell for every row the
system writes.
