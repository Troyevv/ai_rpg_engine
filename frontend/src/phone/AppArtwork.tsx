// Registry extensions can still supply any icon component.
export function appArtwork(symbol: string) {
  return function Artwork({ size }: { size?: number }) {
    return (
      <svg className="smart-artwork" viewBox="0 0 64 64" width={size} height={size} aria-hidden="true" focusable="false">
        <use href={import.meta.env.BASE_URL + 'icons/phone-apps.svg#' + symbol} />
      </svg>
    );
  };
}
