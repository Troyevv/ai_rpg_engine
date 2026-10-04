/** Purely decorative SVG geometry stays outside every layout and hit target. */
const motifs:Record<string,string>={
 cyberpunk:'M8 50 V8 H50 M12 58 V12 H58 M80 8 H116 V44 M8 80 V112 H40 M65 22 H110 M96 30 H110 M22 66 H46 V92 H72 M20 36 H44',
 industrial:'M8 8 H112 V112 H8 Z M14 14 H106 V106 H14 Z M24 8 V112 M8 40 H112 M82 8 V112 M0 56 H112 V72 H0 M34 92 L46 80 M50 92 L62 80 M66 92 L78 80',
 medieval:'M20 16 H100 V62 Q98 92 60 112 Q22 92 20 62 Z M60 26 V90 M35 50 H85 M12 8 H108 M12 8 V40 M108 8 V40',
 arcane:'M60 8 A52 52 0 1 1 59 8 M60 20 A40 40 0 1 0 61 20 M60 26 L90 80 H30 Z M24 24 L96 96 M96 24 L24 96 M60 0 V15 M60 105 V120 M0 60 H15 M105 60 H120',
 parchment:'M20 8 H92 L108 24 V108 H20 Z M92 8 V24 H108 M30 38 H92 M30 46 H92 M30 54 H80 M34 84 A18 18 0 1 0 70 84 A18 18 0 1 0 34 84 M44 102 L40 118 L52 110 L64 118 L60 102',
 gothic:'M12 112 V60 Q12 26 60 6 Q108 26 108 60 V112 M24 112 V62 Q24 36 60 18 Q96 36 96 62 V112 M60 18 V112 M12 84 H108 M40 50 Q60 30 80 50 Q60 70 40 50',
 urban:'M4 20 H32 L60 48 V114 M8 90 H100 V16 M8 50 H30 L80 100 H114 M32 16 V24 M56 48 H64 M96 38 H104 M96 70 H104 M78 96 V104',
 street:'M5 30 L104 6 L116 90 L18 114 Z M6 12 L42 2 L48 18 L12 28 Z M76 102 L110 90 L116 108 L82 118 Z M24 70 L44 36 L62 80 L84 26 M24 90 L100 68',
 noir:'M10 20 H108 V108 H10 Z M20 34 H96 M20 44 H80 M20 54 H88 M64 76 L98 68 L104 88 L70 96 Z M0 0 L120 30 M0 10 L120 40 M0 20 L120 50',
 terminal:'M10 10 H110 V104 H10 Z M16 16 H104 V98 H16 Z M28 32 L42 44 L28 56 M50 56 H70 M24 80 H96 M32 114 H88',
 space:'M10 40 L40 10 H110 V80 L80 110 H10 Z M60 24 V96 M24 60 H96 M34 60 A26 26 0 1 1 86 60 A26 26 0 1 1 34 60 M4 20 H24 M4 28 H20 M92 100 H116 M100 108 H116',
 'post-apocalypse':'M8 18 L108 10 L112 106 L14 112 Z M6 42 L116 36 M36 8 L42 116 M26 34 L28 48 M40 32 L42 46 M54 32 L56 46 M60 98 V70 A22 22 0 0 1 104 70 V98 Z M82 90 L92 64',
 biotech:'M20 14 C104 2 0 114 96 106 M96 14 C12 2 116 114 20 106 M30 22 H86 M36 40 H80 M38 60 H78 M36 80 H80 M30 98 H86 M10 48 Q22 32 32 48 Q22 64 10 48 M88 72 Q100 56 112 72 Q100 88 88 72',
 occult:'M60 8 A52 52 0 1 1 59 8 M60 12 L90 102 L14 46 H108 L30 102 Z M8 8 L24 24 M96 96 L112 112 M8 112 L24 96 M96 24 L112 8',
 retro:'M10 12 Q10 4 20 4 H100 Q110 4 110 14 V106 Q110 116 100 116 H20 Q10 116 10 106 Z M24 20 H96 V72 H24 Z M26 94 A10 10 0 1 0 46 94 A10 10 0 1 0 26 94 M66 88 H96 M66 96 H96 M66 104 H96',
};
// Artwork is data, not a separate copy of the game for every theme.
const inscriptions:Record<string,[string,string]>={
 cyberpunk:['NIGHT / LINK','SECTOR 07 · RX / TX'], medieval:['',''], noir:['CASE FILE / 014','PRIVATE · ARCHIVE'],
 arcane:['✧  IX · IV · VII  ✧',''], gothic:['',''], terminal:['> STORY_BUFFER','[ ONLINE ]'],
 space:['FLIGHT LOG / 07','ORB 024 · NAV / SYS'], industrial:['FIELD RECORD','MK IV / SERVICE'],
 'post-apocalypse':['SALVAGED / 07','REPAIRED · KEEP DRY'], parchment:['EX LIBRIS',''],
 street:['AFTER HOURS','VOL. 01'], urban:['DISTRICT / 07','NORTH → CENTRAL'], biotech:['CELL / 09','MEMBRANE · SYNC'],
 occult:['FIG. VII','SIGILLUM / NOCTIS'], retro:['STEREO / CHRONICLE','FM 88 · 108'],
};
const flourishes:Record<string,string>={
 medieval:'M0 50H160L180 35L200 50L180 65L160 50 M440 50H640 M460 35L440 50L460 65 M70 27L78 22L130 66L126 71Z M113 70L132 49 M121 65L140 81 M134 85L144 75',
 arcane:'M10 50H180 M460 50H630 M140 50l15 -15l15 15l-15 15Z M470 50l15 -15l15 15l-15 15Z',
 gothic:'M10 80V40Q45 0 80 40V80 M90 80V40Q125 0 160 40V80 M480 80V40Q515 0 550 40V80 M560 80V40Q595 0 630 40V80',
 noir:'M15 72H190 M450 72H620 M475 66h65v6h-65Z M490 57c-25 -18 25 -15 0 -37 M550 75q25 18 50 0',
 terminal:'M12 20h12 M12 20v60h12 M628 20h-12 M628 20v60h-12 M45 65l12 -12l-12 -12 M70 65h50',
 space:'M5 50H140L165 25H205 M435 75H475L500 50H635 M65 40v20 M95 35v30 M545 35v30 M575 40v20',
 industrial:'M0 22H180V78H0 M460 22H640V78H460 M20 30l30 40 M50 30l30 40 M80 30l30 40 M110 30l30 40',
 'post-apocalypse':'M0 30L205 38 M435 62L640 70 M45 24v16 M65 25v17 M85 26v17 M515 58v17 M535 59v17 M555 60v17',
 parchment:'M5 50Q80 10 155 50T230 50 M410 50Q460 10 535 50T635 50 M155 50q-20 -35 -45 -15q0 20 45 15 M485 50q20 35 45 15q0 -20 -45 -15',
 street:'M15 75L180 20 M30 85L195 30 M460 20l140 60 M480 20l125 45',
 urban:'M0 65H100L140 25H205 M435 25H485L525 65H640 M40 58v14 M75 58v14 M565 58v14 M600 58v14',
 biotech:'M0 50C70 -20 130 120 210 50 M0 60C70 -10 130 130 210 60 M430 50C510 -20 570 120 640 50 M430 60C510 -10 570 130 640 60',
 occult:'M15 50H190 M450 50H625 M60 20l35 60l35 -60Z M510 80l35 -60l35 60Z',
 retro:'M10 75V25Q80 -5 150 25V75 M30 55L75 20 M490 75V25Q560 -5 630 25V75 M555 55L600 20 M165 30h35v40h-35Z M440 30h35v40h-35Z',
 cyberpunk:'M0 15H180L200 35 M0 80H150L170 60 M440 35L460 15H640 M470 60L490 80H640 M20 30H100 M540 65H620',
};
/** This reserved header slot never overlaps narrative text or controls. */
export function SkinHeader({pack}:{pack:string}) {
 if(pack==='none')return null;
 const [left,right]=inscriptions[pack]||['',''];
 return <div className={`skin-header-art art-${pack}`} aria-hidden="true">
  <svg viewBox="0 0 640 100" preserveAspectRatio="xMidYMid meet">
   <path className="art-flourish" d={flourishes[pack]}/>
   <g className="art-emblem" transform="translate(274 4) scale(.76)"><path d={motifs[pack]}/></g>
   <text x="12" y="96">{left}</text><text x="628" y="96" textAnchor="end">{right}</text>
  </svg>
 </div>;
}
/** Ambient marks stay inside narrow screen gutters, never across the reading surface. */
export function ThemeDecorationLayer({pack}:{pack:string}) {
 if(pack==='none')return null;
 return <div className={`theme-decoration decoration-${pack}`} aria-hidden="true">
  <span className="decoration-edge edge-left"/><span className="decoration-edge edge-right"/>
 </div>;
}
