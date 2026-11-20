// This runs inside Chromium on decoded production plates. Sample the visible
// eyelid opening in its own coordinates, then project each point into hair space.
export function inspectHair(images) {
  return images.flatMap((image, index) => {
    const doc = new DOMParser().parseFromString(decodeURIComponent(image.src.split(',')[1]), 'image/svg+xml');
    const svg = document.importNode(doc.documentElement, true);
    svg.style.cssText = 'position:fixed;left:-1000px;top:0;width:400px;height:500px';
    document.body.append(svg);
    try {
      const locks = svg.querySelector('#locks');
      if (!locks) return [];
      const outlines = [...locks.querySelectorAll('path')];
      if (outlines.some(path => (path.getAttribute('d').match(/M/g) || []).length !== 1)) {
        return [{index, reason: 'overlapping locks share a compound fill'}];
      }
      const toHair = locks.parentElement.parentElement.getScreenCTM().inverse();
      const lids = [...svg.querySelectorAll('#near-orbit, #far-orbit, #near, #far')];
      if (lids.length !== 2) return [{index, reason: 'missing eyelid outlines'}];
      for (const lid of lids) {
        const aperture = lid.querySelector('path');
        const matrix = toHair.multiply(lid.parentElement.parentElement.getScreenCTM());
        const box = aperture.getBBox();
        for (let x=box.x+.5; x<box.x+box.width; x++) {
          for (let y=box.y+.5; y<box.y+box.height; y++) {
            const point = new DOMPoint(x,y);
            if (!aperture.isPointInFill(point)) continue;
            const posed = point.matrixTransform(matrix);
            if (outlines.some(path => path.isPointInFill(posed))) return [{index, reason: lid.id+' covered'}];
          }
        }
      }
      return [];
    } finally { svg.remove(); }
  });
}
