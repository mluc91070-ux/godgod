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

## sphere.mp4 / sphere.webm

The homepage hero. `components/Hero.tsx` serves the WebM first and falls back
to the WebGL field if the video fails to decode at all.

Built from `TEASER.mp4` (1280×720, 15s, 9.5MB) by:

1. **Keeping the native 16:9.** An earlier version cropped to a square, which
   looked tidy and cut about five hundred pixels off each side — by the end of
   the loop the sphere and its cabling span x=30 to x=1279 of the frame, so a
   square crop removes the half of the composition that gives it scale.
   Measured, then fixed.
2. **Boomerang, opening on the close-up.** The source is an approach: it starts
   on a distant speck and ends on a full-frame sphere, so a hard loop would
   jump. Reversed-then-forward runs close → far → close, seamless at both ends
   — 0.02/255 mean difference across the seam. The order matters:
   forward-then-reversed is equally seamless but opens on the darkest frame,
   and a visitor's first impression is a black square.
3. **Re-encoding at full resolution.** 9.5MB → 989KB MP4 / 812KB WebM at
   1280×720, CRF 28, with faststart so playback begins before the download
   finishes.

To rebuild from a new source, the steps are above and `ffmpeg` is all it takes.

A rendered loop cannot represent live state, so it is marked `aria-hidden` and
the real numbers stay in the text underneath. The WebGL field is the one bound
to activity, novelty and confidence — if that binding matters more than the
render, leave the video out.
