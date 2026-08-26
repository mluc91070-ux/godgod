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

## sphere.mp4 / sphere.webm

The homepage hero. `components/Hero.tsx` serves the WebM first and falls back
to the WebGL field if the video fails to decode at all.

Built from `TEASER.mp4` (1280×720, 15s, 9.5MB) by:

1. **Cropping to square.** The sphere is centred, so a 720×720 centre crop
   loses nothing, and the hero slot is 1:1.
2. **Boomerang, opening on the close-up.** The source is an approach: it starts
   on a distant speck and ends on a full-frame sphere, so a hard loop would
   jump. Reversed-then-forward runs close → far → close, which is seamless at
   both ends — measured at 0.02/255 mean difference across the seam. The order
   matters: forward-then-reversed is equally seamless but opens on the darkest
   frame, and a visitor's first impression is a black square.
3. **Re-encoding.** 9.5MB → 505KB MP4 / 420KB WebM at 640×640, CRF 30. Every
   visitor downloads this; the original was nineteen times heavier for a
   picture nobody can tell apart at this size.

To rebuild from a new source, the steps are above and `ffmpeg` is all it takes.

A rendered loop cannot represent live state, so it is marked `aria-hidden` and
the real numbers stay in the text underneath. The WebGL field is the one bound
to activity, novelty and confidence — if that binding matters more than the
render, leave the video out.
