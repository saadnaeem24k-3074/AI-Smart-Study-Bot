"""
Slide capture for Google Meet presentations (v2).

What it does, every few seconds, on the largest <video> on the page (the
presentation tile while someone presents):

  * NEW SLIDE   – the picture changed a lot and then held still  → new screenshot.
  * REFINE      – the same slide gained content (teacher reveals bullets one by
                  one)                                           → the slide's
                  screenshot is overwritten, so you keep the COMPLETE version.
  * SNAPSHOT    – the screen never settles (a video, a whiteboard being drawn
                  on, scrolling)                                 → a keyframe
                  every `keyframe_secs` so the notes still have visuals.

The picture is reduced to a 64x36 grayscale signature inside the browser, so no
image library is needed.
"""

import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from core.logger import setup_logger

logger = setup_logger("Slides")

SIG_JS = """() => {
  const vids = [...document.querySelectorAll('video')]
      .filter(v => v.videoWidth > 0 && v.readyState >= 2);
  if (!vids.length) return null;
  let best = null, area = 0;
  for (const v of vids) {
    const r = v.getBoundingClientRect(), a = r.width * r.height;
    if (a > area) { area = a; best = v; }
  }
  if (!best || area < 120 * 120) return null;
  window.__slideVideo = best;
  const W = 64, H = 36;
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(best, 0, 0, W, H);
  const d = ctx.getImageData(0, 0, W, H).data;
  const sig = [];
  for (let i = 0; i < d.length; i += 4)
    sig.push((d[i] * 0.299 + d[i + 1] * 0.587 + d[i + 2] * 0.114) | 0);
  const txt = (document.body.innerText || '').toLowerCase();
  const presenting = /presentation|presenting|\u067e\u0631\u06cc\u0632\u0646\u0679\u06cc\u0634\u0646/.test(txt);
  const r = best.getBoundingClientRect();
  const big = (area / (window.innerWidth * window.innerHeight)) > 0.30;
  return { sig, presenting, big, w: best.videoWidth, h: best.videoHeight,
           x: r.x, y: r.y, rw: r.width, rh: r.height };
}"""


def _stats(a: List[int], b: List[int]) -> Tuple[float, float]:
    """(mean absolute difference 0-255, fraction of pixels that changed a lot)."""
    n = max(1, min(len(a), len(b)))
    total = changed = 0
    for x, y in zip(a, b):
        d = abs(x - y)
        total += d
        if d > 40:
            changed += 1
    return total / n, changed / n


class SlideCapture:
    STABLE_MEAN, STABLE_FRAC = 3.0, 0.05      # frame-to-frame: "picture has settled"
    NEW_MEAN, NEW_FRAC = 6.0, 0.22            # vs saved slide: "this is a different slide"
    REFINE_MEAN, REFINE_FRAC = 0.6, 0.004     # vs saved slide: "same slide, more content"
    REFINE_EVERY = 6.0                        # seconds between overwrites of the same slide
    MAX_SLIDES = 150

    def __init__(self, slides_dir: Path, mode: str, interval: float,
                 on_slide: Callable[[str, str], int], keyframe_secs: float = 30.0):
        self.dir = slides_dir
        self.mode = mode                        # auto | always | off
        self.interval = max(2.0, float(interval))
        self.keyframe_secs = float(keyframe_secs or 0)
        self.on_slide = on_slide                # (relative file, kind) -> slide number
        self._last_tick = 0.0
        self._prev_sig: Optional[List[int]] = None
        self._saved_sig: Optional[List[int]] = None
        self._saved_sigs = {}
        self._cur_rel: Optional[str] = None
        self._cur_kind = "slide"
        self._last_refresh = 0.0
        self._unstable_since: Optional[float] = None
        self._warned = False
        self.count = 0

    async def tick(self, page) -> bool:
        """Call often; does real work at most once per `interval`. True if a NEW entry was saved."""
        if self.mode == "off" or self.count >= self.MAX_SLIDES:
            return False
        now = time.time()
        if now - self._last_tick < self.interval:
            return False
        self._last_tick = now
        try:
            info = await page.evaluate(SIG_JS)
        except Exception as e:
            if not self._warned:
                logger.warning(f"Slide check failed (will keep trying quietly): {e}")
                self._warned = True
            return False
        if not info or not info.get("sig"):
            self._reset_motion()
            return False
        if self.mode == "auto" and not (info["presenting"] and info["big"]):
            self._reset_motion()
            return False

        sig = info["sig"]
        prev, self._prev_sig = self._prev_sig, sig
        if prev is None:
            return False                                    # first sighting
        mean, frac = _stats(sig, prev)

        # ── still moving ─────────────────────────────────
        if mean > self.STABLE_MEAN or frac > self.STABLE_FRAC:
            if self._unstable_since is None:
                self._unstable_since = now
            if self.keyframe_secs and now - self._unstable_since >= self.keyframe_secs:
                self._unstable_since = now                  # video / whiteboard → periodic snapshot
                return await self._save(page, info, "moment", sig)
            return False

        # ── settled ──────────────────────────────────────
        self._unstable_since = None
        if self._saved_sig is None:
            return await self._save(page, info, "slide", sig)
        smean, sfrac = _stats(sig, self._saved_sig)
        if smean >= self.NEW_MEAN or sfrac >= self.NEW_FRAC:
            return await self._save(page, info, "slide", sig)
        if (self._cur_kind == "slide" and (smean >= self.REFINE_MEAN or sfrac >= self.REFINE_FRAC)
                and now - self._last_refresh >= self.REFINE_EVERY):
            await self._shoot(page, info, self.dir.parent / self._cur_rel)   # keep the fuller version
            self._saved_sig = sig
            self._saved_sigs[self.count] = sig
            self._last_refresh = now
            logger.info(f"Slide {self.count} updated (more content revealed)")
        return False

    def _reset_motion(self):
        self._prev_sig = None
        self._unstable_since = None

    async def _save(self, page, info, kind: str, sig: List[int]) -> bool:
        if any(self._same_image(sig, saved) for saved in self._saved_sigs.values()):
            logger.debug("Skipped a screenshot matching an earlier slide or snapshot")
            return False
        n = self.count + 1
        rel = f"slides/slide_{n:03d}.jpg"
        if not await self._shoot(page, info, self.dir.parent / rel):
            return False
        self._saved_sig, self._cur_rel, self._cur_kind = sig, rel, kind
        self._saved_sigs[n] = sig
        self._last_refresh = time.time()
        self.count = n
        self.on_slide(rel, kind)
        logger.info(f"{'Snapshot' if kind == 'moment' else 'Slide'} {n} captured ({info['w']}x{info['h']})")
        return True

    @classmethod
    def _same_image(cls, a: List[int], b: List[int]) -> bool:
        mean, frac = _stats(a, b)
        return mean < cls.NEW_MEAN and frac < cls.NEW_FRAC

    async def _shoot(self, page, info, path: Path) -> bool:
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            handle = await page.evaluate_handle("() => window.__slideVideo")
            el = handle.as_element()
            if el is None:
                raise RuntimeError("no video element")
            await el.screenshot(path=str(path), type="jpeg", quality=82)
            return True
        except Exception:
            try:
                await page.screenshot(
                    path=str(path), type="jpeg", quality=82,
                    clip={"x": max(0, info["x"]), "y": max(0, info["y"]),
                          "width": max(10, info["rw"]), "height": max(10, info["rh"])})
                return True
            except Exception as e:
                logger.warning(f"Could not capture slide: {e}")
                return False
