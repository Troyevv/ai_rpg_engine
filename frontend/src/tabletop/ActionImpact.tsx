import { useEffect, useState } from "react";
import { api } from "../api";
import { BuildImpactPreview, type BuildPreview } from "./BuildImpactPreview";
import type { Catalog, Command } from "./types";
export function ActionImpact({
  gameId,
  command,
}: {
  gameId: string;
  command: Command;
}) {
  const [data, setData] = useState<{
    before: BuildPreview;
    after: BuildPreview;
    catalog: Pick<Catalog, "features">;
  } | null>(null);
  const [error, setError] = useState("");
  const encoded = JSON.stringify(command);
  useEffect(() => {
    let active = true;
    setData(null);
    setError("");
    void api<{
      before: BuildPreview;
      after: BuildPreview;
      catalog: Pick<Catalog, "features">;
    }>(`/tabletop/games/${gameId}/impact`, { command: JSON.parse(encoded) })
      .then((d) => {
        if (active) setData(d);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [gameId, encoded]);
  return error ? (
    <p role="status">{error}</p>
  ) : data ? (
    <BuildImpactPreview {...data} />
  ) : (
    <p role="status">Расчёт изменений…</p>
  );
}
