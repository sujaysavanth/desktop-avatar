// Character definition: the original chibi placeholder, now data instead of
// hardcoded markup. See character.js for the contract every definition honors.
//
// She has no `climb` or `hang` capability, so behavior.js keeps her on the floor
// — she'll turn around at a screen edge where the spider would start climbing.

window.CHARACTERS = window.CHARACTERS || {};

window.CHARACTERS.chibi = {
  id: "chibi",
  label: "placeholder girl",

  size: { w: 120, h: 164 },
  viewBox: "0 0 120 164",

  // What behavior.js is allowed to ask of her. "walk" is assumed for everyone.
  capabilities: ["sit", "sleep"],

  // Joint name -> [x, y] in viewBox coords. Must match a group id in `svg`.
  joints: {
    legL: [52, 114],
    legR: [68, 114],
    armL: [45, 78],
    armR: [75, 78],
    head: [60, 72],
  },

  // Neutral pose. Every numeric key here becomes an interpolated channel; every
  // string key is a discrete flag the driver snaps.
  rest: {
    legL: 0,
    legR: 0,
    armL: 4,
    armR: -4,
    headTilt: 0,
    bobY: 0,
    lean: 0,
    eyes: "open", // open | shut | happy
    mouth: "smile", // smile | talk | flat | o
  },

  poses: {
    idle: {},
    walk: {},
    sit: { legL: 78, legR: 84, armL: 12, armR: -10, bobY: 30 },
    sleep: { legL: 80, legR: 86, armL: 18, armR: -16, headTilt: -14, bobY: 32, eyes: "shut", mouth: "flat" },
    drag: { legL: -14, legR: 10, armL: 150, armR: -150, headTilt: 6, mouth: "o" },
    fall: { legL: -26, legR: 22, armL: 130, armR: -130, mouth: "o" },
    happy: { armL: 140, armR: -140, eyes: "happy" },
  },

  // Walk-cycle shape. The driver drives the maths; these are the amplitudes.
  cycles: {
    walk: { stride: 26, arm: 20, bob: 2.5, head: 2, rate: 26 },
  },

  mouths: {
    smile: "M -10 -16 Q 0 -9 10 -16",
    flat: "M -8 -14 Q 0 -12 8 -14",
    talk: "M -9 -16 Q 0 -6 9 -16",
    o: "M -6 -15 Q 0 -6 6 -15 Q 0 -20 -6 -15",
  },

  // Rig markup. Required ids: #flip (facing mirror) and #bob (body bob + lean),
  // plus one group per joint. #eyes-open / #eyes-shut / #mouth are optional —
  // the driver skips blinking and mouth shapes for characters without them.
  svg: `
    <g id="flip">
      <g id="bob">
        <g id="legL" transform="translate(52,114)">
          <rect x="-4.5" y="-2" width="9" height="44" rx="4.5" fill="#f2d6be" />
          <ellipse cx="0" cy="46" rx="7.5" ry="4" fill="#43436a" />
        </g>
        <g id="legR" transform="translate(68,114)">
          <rect x="-4.5" y="-2" width="9" height="44" rx="4.5" fill="#ffe0c7" />
          <ellipse cx="0" cy="46" rx="7.5" ry="4" fill="#4e4e7a" />
        </g>

        <g id="armL" transform="translate(45,78)">
          <rect x="-4" y="-4" width="8" height="36" rx="4" fill="#f2d6be" />
          <circle cx="0" cy="34" r="5" fill="#ffe0c7" />
        </g>

        <g id="torso">
          <path d="M45 82 Q42 116 38 122 L82 122 Q78 116 75 82 Z" fill="#5f51d6" />
          <rect x="45" y="70" width="30" height="26" rx="12" fill="#6c5ce7" />
          <path d="M52 72 Q60 80 68 72" stroke="#4b3fb0" stroke-width="2" fill="none" />
        </g>

        <g id="armR" transform="translate(75,78)">
          <rect x="-4" y="-4" width="8" height="36" rx="4" fill="#ffe0c7" />
          <circle cx="0" cy="34" r="5" fill="#ffe0c7" />
        </g>

        <g id="head" transform="translate(60,72)">
          <path d="M-30 -26 Q-35 -67 0 -71 Q35 -67 30 -26 L30 -4 Q0 -17 -30 -4 Z" fill="#6c5ce7" />
          <ellipse cx="0" cy="-32" rx="27" ry="29" fill="#ffe0c7" />
          <path d="M-27 -37 Q-21 -66 0 -68 Q21 -66 27 -37 Q16 -51 5 -47 Q0 -60 -5 -49 Q-16 -51 -27 -37 Z" fill="#7d6cf0" />
          <ellipse cx="-19" cy="-21" rx="6.5" ry="3.2" fill="#ffb3ba" opacity="0.7" />
          <ellipse cx="19" cy="-21" rx="6.5" ry="3.2" fill="#ffb3ba" opacity="0.7" />
          <g id="eyes-open">
            <ellipse cx="-11" cy="-30" rx="5" ry="7" fill="#2d2d44" />
            <ellipse cx="11" cy="-30" rx="5" ry="7" fill="#2d2d44" />
            <circle cx="-9.5" cy="-32.5" r="1.9" fill="#fff" />
            <circle cx="12.5" cy="-32.5" r="1.9" fill="#fff" />
          </g>
          <g id="eyes-shut" style="display: none">
            <path d="M-16 -30 Q-11 -26 -6 -30" stroke="#2d2d44" stroke-width="2" fill="none" stroke-linecap="round" />
            <path d="M6 -30 Q11 -26 16 -30" stroke="#2d2d44" stroke-width="2" fill="none" stroke-linecap="round" />
          </g>
          <path id="mouth" d="M -10 -16 Q 0 -9 10 -16" stroke="#c0607a" stroke-width="2.2" fill="none" stroke-linecap="round" />
        </g>
      </g>
    </g>
  `,
};
