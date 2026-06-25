import React, { useEffect, useRef, useState } from 'react';

// Square pan-and-zoom avatar cropper. State is the image-space point under the viewport
// centre (+ zoom), so zooming stays centred and the crop never leaves the image. Exports a
// fixed OUTPUT×OUTPUT JPEG, so the stored size is bounded regardless of the source file.
const V = 256; // viewport square (display px)
const OUTPUT = 256; // exported square (px)

interface Props {
  file: File;
  onCancel: () => void;
  onDone: (dataUri: string) => void;
}

export const AvatarCropper: React.FC<Props> = ({ file, onCancel, onDone }) => {
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const [zoom, setZoom] = useState(1);
  const [center, setCenter] = useState({ x: 0, y: 0 }); // natural-image coords under viewport centre
  const drag = useRef<{ px: number; py: number; cx: number; cy: number } | null>(null);

  useEffect(() => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      setImg(image);
      setZoom(1);
      setCenter({ x: image.naturalWidth / 2, y: image.naturalHeight / 2 });
    };
    image.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const baseScale = img ? V / Math.min(img.naturalWidth, img.naturalHeight) : 1;
  const scale = baseScale * zoom;

  const clampCenter = (c: { x: number; y: number }) => {
    if (!img) return c;
    const half = V / 2 / scale; // half the visible source square, in natural px
    const fit = (v: number, max: number) => (max <= 2 * half ? max / 2 : Math.min(max - half, Math.max(half, v)));
    return { x: fit(c.x, img.naturalWidth), y: fit(c.y, img.naturalHeight) };
  };

  // Visible area changes with zoom — re-clamp so the crop stays inside the image.
  useEffect(() => {
    setCenter((c) => clampCenter(c));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoom, img]);

  const cc = clampCenter(center);
  const dispW = img ? img.naturalWidth * scale : 0;
  const dispH = img ? img.naturalHeight * scale : 0;
  const left = V / 2 - cc.x * scale;
  const top = V / 2 - cc.y * scale;

  const onPointerDown = (e: React.PointerEvent) => {
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
    drag.current = { px: e.clientX, py: e.clientY, cx: cc.x, cy: cc.y };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    setCenter(clampCenter({
      x: drag.current.cx - (e.clientX - drag.current.px) / scale,
      y: drag.current.cy - (e.clientY - drag.current.py) / scale,
    }));
  };
  const endDrag = () => { drag.current = null; };

  const confirm = () => {
    if (!img) return;
    const half = V / 2 / scale;
    const canvas = document.createElement('canvas');
    canvas.width = OUTPUT;
    canvas.height = OUTPUT;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.drawImage(img, cc.x - half, cc.y - half, half * 2, half * 2, 0, 0, OUTPUT, OUTPUT);
    onDone(canvas.toDataURL('image/jpeg', 0.85));
  };

  return (
    <div className="p-5 space-y-4">
      <div
        className="relative mx-auto overflow-hidden rounded-full bg-muted touch-none cursor-grab active:cursor-grabbing"
        style={{ width: V, height: V }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
      >
        {img && (
          <img
            src={img.src}
            alt=""
            draggable={false}
            className="absolute max-w-none select-none"
            style={{ left, top, width: dispW, height: dispH }}
          />
        )}
      </div>
      <label className="block">
        <span className="block text-xs text-muted-foreground mb-1.5">縮放</span>
        <input type="range" min={1} max={3} step={0.01} value={zoom} onChange={(e) => setZoom(Number(e.target.value))} className="w-full accent-accent-info" />
      </label>
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="px-4 py-2 rounded-full text-sm font-medium text-foreground hover:bg-muted transition-colors">取消</button>
        <button type="button" onClick={confirm} className="px-4 py-2 rounded-full text-sm font-medium bg-foreground text-background hover:opacity-90 transition-opacity">套用</button>
      </div>
    </div>
  );
};
