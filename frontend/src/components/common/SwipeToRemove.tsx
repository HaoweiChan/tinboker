import { useRef, useState } from 'react';
import { Trash2 } from 'lucide-react';

const THRESHOLD = 0.35; // fraction of the row width that commits a removal
const SLOP = 10; // px of movement before a gesture is judged horizontal or vertical
const LEAVE_MS = 180;

/**
 * Swipe a row left to remove it. Vertical movement is left to the page scroll, a drag
 * never also follows the link underneath, and Delete / Backspace on a focused row
 * removes it too (keyboard users can't swipe). Undo is the caller's job — this only
 * reports the removal.
 */
export const SwipeToRemove: React.FC<{
  onRemove: () => void;
  className?: string;
  children: React.ReactNode;
}> = ({ onRemove, className = '', children }) => {
  const rowRef = useRef<HTMLDivElement>(null);
  const start = useRef<{ x: number; y: number; id: number } | null>(null);
  const dragged = useRef(false);
  const [dx, setDxState] = useState(0);
  // The release handler needs the offset of the LAST move, which a fast flick can end
  // before React has re-rendered it into state.
  const dxRef = useRef(0);
  const setDx = (v: number) => {
    dxRef.current = v;
    setDxState(v);
  };
  const [active, setActive] = useState(false);

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    start.current = { x: e.clientX, y: e.clientY, id: e.pointerId };
    dragged.current = false;
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const s = start.current;
    if (!s || s.id !== e.pointerId) return;
    const mx = e.clientX - s.x;
    const my = e.clientY - s.y;
    if (!dragged.current) {
      if (Math.abs(my) > SLOP && Math.abs(my) >= Math.abs(mx)) {
        start.current = null; // a scroll, not a swipe
        return;
      }
      if (mx > -SLOP) return;
      dragged.current = true;
      setActive(true);
      rowRef.current?.setPointerCapture(e.pointerId);
    }
    setDx(Math.min(0, mx));
  };

  const onPointerEnd = () => {
    start.current = null;
    setActive(false);
    const width = rowRef.current?.offsetWidth ?? 1;
    if (dragged.current && -dxRef.current > width * THRESHOLD) {
      setDx(-width);
      window.setTimeout(onRemove, LEAVE_MS);
    } else {
      setDx(0);
    }
  };

  const onClickCapture = (e: React.MouseEvent) => {
    if (!dragged.current) return;
    e.preventDefault();
    e.stopPropagation();
    dragged.current = false;
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== 'Delete' && e.key !== 'Backspace') return;
    e.preventDefault();
    onRemove();
  };

  return (
    <div className={`relative overflow-hidden ${className}`} onKeyDown={onKeyDown}>
      <div
        aria-hidden
        className="absolute inset-0 flex items-center justify-end gap-1.5 px-5 bg-sentiment-bear text-white text-sm font-medium"
        style={{ opacity: Math.min(1, -dx / 80) }}
      >
        <Trash2 size={16} />
        移除
      </div>
      <div
        ref={rowRef}
        className="relative select-none bg-card"
        style={{
          transform: `translateX(${dx}px)`,
          transition: active ? 'none' : `transform ${LEAVE_MS}ms ease-out`,
          touchAction: 'pan-y',
        }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerEnd}
        onPointerCancel={onPointerEnd}
        onClickCapture={onClickCapture}
      >
        {children}
      </div>
    </div>
  );
};
