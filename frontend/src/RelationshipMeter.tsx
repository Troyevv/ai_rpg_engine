import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";

/** Native meter semantics with a separate, compositor-only presentation.
 * The existing scale is linear from -100 (left) to 100 (right), NOT abs(value).
 * Entry and value transitions live on separate layers so a refresh cannot
 * restart the cascade or leave an old animation targeting stale data.
 */
export function RelationshipMeter({
  value,
  label,
  index,
  active,
}: {
  value: number;
  label: string;
  index: number;
  active: boolean;
}) {
  const track = useRef<HTMLSpanElement>(null);
  const [entered, setEntered] = useState(false);
  const [visible, setVisible] = useState(false);

  useLayoutEffect(() => {
    setEntered(false);
    setVisible(false);
    const node = track.current;
    if (!active || !node) return;
    let disposed = false;
    let intersecting = false;
    const update = () => {
      if (disposed) return;
      const shown = intersecting && document.visibilityState !== "hidden";
      setVisible(shown);
      if (shown) setEntered(true);
    };
    const observer = new IntersectionObserver(([entry]) => {
      intersecting = entry.isIntersecting;
      update();
    });
    observer.observe(node);
    document.addEventListener("visibilitychange", update);
    return () => {
      disposed = true;
      observer.disconnect();
      document.removeEventListener("visibilitychange", update);
    };
  }, [active]);

  const fraction = (Math.max(-100, Math.min(100, value)) + 100) / 200;
  return (
    <>
      <meter
        className="relationship-meter-semantic"
        min={-100}
        max={100}
        value={value}
        aria-label={`${label}: ${value}; от −100 до 100`}
      />
      <span
        ref={track}
        className="relationship-meter"
        aria-hidden="true"
        data-entered={active && entered}
        data-visible={active && visible}
        style={{ "--relationship-meter-delay": `${index * 90}ms` } as CSSProperties}
      >
        <span className="relationship-meter-reveal">
          <span
            className="relationship-meter-fill"
            style={{ transform: `scaleX(${fraction})` }}
          />
        </span>
        <span className="relationship-meter-zero" />
      </span>
    </>
  );
}
