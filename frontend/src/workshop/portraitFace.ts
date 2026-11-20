// Local coordinates share the hairline and collar landmarks of the wardrobe.
// The mandibular angle and chin shelf are independent of the cheekbone.
import type { Layers } from './proceduralPortrait';
import type { BodyFrame } from './portraitAnatomy';

type Face = NonNullable<Layers['visage']>;
type Structure = {
  cheek: number;
  jaw: number;
  chin: number;
  depth: number;
  angle: number;
  eyeSpacing: number;
  arch: number;
  nose: number;
  mouth: number;
};
const forms: Partial<Record<Face, Structure>> = {
  oval: {
    cheek: 66,
    jaw: 52,
    chin: 20,
    depth: 281,
    angle: 247,
    eyeSpacing: 29,
    arch: 6,
    nose: 10,
    mouth: 18,
  },
  narrow: {
    cheek: 59,
    jaw: 44,
    chin: 16,
    depth: 282,
    angle: 243,
    eyeSpacing: 25,
    arch: 8,
    nose: 8,
    mouth: 16,
  },
  angular: {
    cheek: 71,
    jaw: 51,
    chin: 20,
    depth: 281,
    angle: 249,
    eyeSpacing: 30,
    arch: 5,
    nose: 10,
    mouth: 19,
  },
  broad: {
    cheek: 70,
    jaw: 60,
    chin: 26,
    depth: 277,
    angle: 253,
    eyeSpacing: 31,
    arch: 3,
    nose: 13,
    mouth: 21,
  },
  long: {
    cheek: 61,
    jaw: 50,
    chin: 22,
    depth: 291,
    angle: 257,
    eyeSpacing: 26,
    arch: 5,
    nose: 9,
    mouth: 17,
  },
  round: {
    cheek: 72,
    jaw: 58,
    chin: 21,
    depth: 268,
    angle: 239,
    eyeSpacing: 30,
    arch: 9,
    nose: 9,
    mouth: 17,
  },
  soft: {
    cheek: 68,
    jaw: 55,
    chin: 24,
    depth: 275,
    angle: 244,
    eyeSpacing: 28,
    arch: 8,
    nose: 11,
    mouth: 20,
  },
};
const mix = (a: number, b: number, t: number) => a + (b - a) * t;
const n = (v: number) => Math.round(v * 100) / 100;

export function portraitFace(
  form: Face,
  age: string,
  frame: BodyFrame,
  skin: readonly string[],
  hair: readonly string[],
  iris: string,
) {
  const f = forms[form] || forms.oval!,
    baby = age === 'infant',
    child = age === 'child',
    teen = age === 'adolescent';
  const growth = baby ? 0.84 : child ? 0.63 : teen ? 0.23 : 0,
    old = age === 'elderly',
    mature = age === 'mature_adult';
  const frameWidth = frame === 'male' ? 3 : frame === 'female' ? -1.5 : 0;
  const cheek = n(mix(f.cheek, 69, growth)),
    jaw = n(mix(f.jaw + frameWidth, 50, growth) + (old ? 2 : 0));
  const chin = n(mix(f.chin + frameWidth * 0.6, 19, growth)),
    bottom = n(mix(f.depth, 252, growth) + (old ? 1 : 0));
  const angle = n(mix(f.angle, 235, growth) + (old ? 4 : 0));
  const zygoma = form === 'angular' ? 198 : form === 'round' ? 214 : 205;
  // A broad horizontal tangent rounds the floor of the chin. The body of the
  // mandible runs from the angle to either side of it, not to a centre vertex.
  const outline = `M200 103 C238 103 263 127 263 165
 C263 183 ${200 + cheek} ${zygoma - 13} ${200 + cheek} ${zygoma}
 C${200 + cheek} ${zygoma + 15} ${202 + jaw} ${angle - 7} ${200 + jaw} ${angle}
 C${197 + jaw} ${angle + 10} ${chin + 210} ${bottom - 7} ${200 + chin} ${bottom - 3}
 C${200 + chin * 0.48} ${bottom + 1} ${200 - chin * 0.48} ${bottom + 1} ${200 - chin} ${bottom - 3}
 C${190 - chin} ${bottom - 7} ${203 - jaw} ${angle + 10} ${200 - jaw} ${angle}
 C${198 - jaw} ${angle - 7} ${200 - cheek} ${zygoma + 15} ${200 - cheek} ${zygoma}
 C${200 - cheek} ${zygoma - 13} 137 183 137 165 C137 127 162 103 200 103Z`;
  const eyeY = n(mix(194 + (f.depth - 278) * 0.14, 201, growth) + (old ? 1 : 0));
  const noseY = n(mix(eyeY + 34 + (f.depth - 278) * 0.17, 220, growth) + (old ? 2 : 0));
  const mouthY = n(noseY + (bottom - noseY) * 0.38);
  const neckWidth = n(mix(20 + frameWidth, 16, growth));
  const neckPath = `M${200 - neckWidth} 255h${2 * neckWidth} C${200 + neckWidth} 291 ${199 + neckWidth} 308 230 319 Q239 331 268 341L266 372H134L132 341Q161 331 170 319C${201 - neckWidth} 308 ${200 - neckWidth} 291 ${200 - neckWidth} 255Z`;
  const scale = baby ? 1.22 : child ? 1.1 : teen ? 1.035 : 1;
  const vertical = n((baby ? 318 : child ? 309 : teen ? 301 : 298) - bottom * scale);
  const headTransform = `translate(${n(200 - 200 * scale)} ${vertical}) scale(${scale})`;
  const ink = '#483934',
    shadow = skin[2];
  const stroke = (d: string, color: string, width: number, opacity = 1) =>
    `<path d="${d}" fill="none" stroke="${color}" stroke-width="${width}" opacity="${opacity}" stroke-linecap="round" stroke-linejoin="round"/>`;
  const fill = (d: string, color: string, opacity = 1) =>
    `<path d="${d}" fill="${color}" opacity="${opacity}"/>`;
  const ears = [-1, 1]
    .map(
      (side) =>
        `<g transform="translate(${200 + side * (cheek - 3)} ${eyeY - 6}) scale(${side} 1)">${fill('M-4 4Q1-4 8 0C17 5 11 21 7 29Q4 34-3 30Z', skin[1])}${stroke('M3 8q8-6 5 4l-4 8', ink, 1.5, 0.35)}</g>`,
    )
    .join('');
  const eyeHalf = n(mix(15, 15.3, growth)),
    opening = n(mix(old ? 4.1 : 5.3, 7, growth)),
    spacing = n(mix(f.eyeSpacing, 28, growth));
  const browLift = n(mix(f.arch, 3, growth)),
    browWeight = n(mix(frame === 'male' ? 5 : 3.8, 2.4, growth));
  const eyes = [-1, 1]
    .map((side) => {
      const upper = `M${-eyeHalf} 1 Q-4 ${-opening * 1.85} ${eyeHalf * 0.52} ${-opening * 0.8} Q${eyeHalf * 0.86} ${-opening * 0.5} ${eyeHalf} -1`;
      const aperture = upper + ` Q4 ${opening * 1.75} ${-eyeHalf} 1Z`,
        clip = 'lid' + (side === 1 ? 'R' : 'L');
      return `<g transform="translate(${n(200 + side * spacing)} ${eyeY}) scale(${side} 1)"><defs><clipPath id="${clip}"><path d="${aperture}"/></clipPath></defs>
   ${fill(aperture, '#eee4d4')}<g clip-path="url(#${clip})"><circle r="${opening + 1.1}" fill="${iris}"/><circle r="${opening * 0.51}" fill="#302d29"/><circle cx="${-side * 1.5}" cy="-2" r="1.1" fill="#fff5e6"/></g>
   ${stroke(upper, ink, 1.8, 0.82)}${stroke(`M${-eyeHalf * 0.9} -4Q0 ${-opening * 2.5} ${eyeHalf * 0.95} -5`, shadow, 1.1, 0.54)}
   ${fill(`M-15 -12 Q-8 ${-14 - browLift} 3 ${-14 - browLift} Q10 ${-14 - browLift} 16 -12 Q8 ${-15 - browLift + 1} 2 ${-15 - browLift + browWeight} Q-7 -14 -14 ${-13 + browWeight}Z`, hair[1], 0.89)}
   ${old || mature ? stroke(`M-9 7Q2 ${old ? 15 : 11} 12 7m2 -3 6 2`, ink, 1.15, old ? 0.3 : 0.17) : ''}</g>`;
    })
    .join('');
  const noseHalf = n(mix(f.nose, 7, growth)),
    lip = n(mix(f.mouth, 13, growth));
  const nose =
    fill(
      `M201 ${eyeY + 6}C201 ${noseY - 15} ${202 - noseHalf} ${noseY - 6} ${201 - noseHalf} ${noseY - 3} Q196 ${noseY + 2} 202 ${noseY + 1} Q207 ${noseY} 205 ${noseY - 4}Q200 ${noseY - 2} 201 ${eyeY + 6}Z`,
      shadow,
      0.42,
    ) +
    stroke(
      `M${199 - noseHalf} ${noseY - 1}q1 3 4 2 Q199 ${noseY + 5} 203 ${noseY + 2}Q${204 + noseHalf * 0.5} ${noseY - 1} ${200 + noseHalf} ${noseY}`,
      ink,
      baby ? 1.05 : 1.35,
      0.53,
    );
  const lips =
    fill(
      `M${200 - lip} ${mouthY}Q191 ${mouthY - 2} 196 ${mouthY - 3}Q199 ${mouthY - 4} 201 ${mouthY - 2.5}Q205 ${mouthY - 4} 210 ${mouthY - 2}L${200 + lip} ${mouthY}Q203 ${mouthY + (baby ? 9 : old ? 5 : 8)} ${200 - lip} ${mouthY}Z`,
      '#a35f56',
      0.74,
    ) +
    stroke(
      `M${200 - lip} ${mouthY}Q194 ${mouthY + 0.5} 200 ${mouthY + 1}Q206 ${mouthY + 1} ${200 + lip} ${mouthY}`,
      ink,
      1,
      0.69,
    );
  const planes = fill(
    `M${200 + cheek - 3} ${zygoma - 24} Q${200 + cheek + 6} ${angle} ${200 + chin} ${bottom}L197 ${bottom}Q${200 + jaw - 7} ${angle + 7} ${200 + jaw - 3} ${angle - 3}Q${200 + cheek - 18} ${zygoma + 7} ${200 + cheek - 3} ${zygoma - 24}Z`,
    shadow,
    0.19,
  );
  const ageLines =
    old || mature
      ? stroke(
          `M${200 - noseHalf - 4} ${noseY + 2}q-6 5 -7 11m${2 * noseHalf + 24} -11q5 4 7 11`,
          ink,
          1.3,
          old ? 0.28 : 0.13,
        )
      : '';
  const forehead = old ? stroke(`M179 ${eyeY - 36}q19-5 39-1m-34 6q16-3 29-1`, ink, 1.2, 0.2) : '';
  const face =
    fill(outline, 'url(#skin)') +
    `<g clip-path="url(#face-plane)">${planes}${eyes}${nose}${lips}${ageLines}${forehead}</g><defs><clipPath id="face-plane"><path d="${outline}"/></clipPath></defs>`;
  return { outline, face, ears, headTransform, neckPath, beardOffset: n(mouthY - 258) };
}
