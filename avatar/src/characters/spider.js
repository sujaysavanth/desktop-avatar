// Character definition: a masked wall-crawler.
//
// Original artwork built from primitives in the archetype — red suit, blue limbs,
// big white lenses, webbing on the mask — not traced from any published design.
// If you want a more polished look, this whole file is the swappable unit: keep
// `size`/`joints`/`poses`/`capabilities` and replace `svg`.
//
// The interesting part isn't the art, it's `capabilities`. Declaring "climb" and
// "hang" is what unlocks the wall and ceiling surfaces in behavior.js — he leaves
// the floor at a screen edge instead of turning around, and he has no `sit` or
// `sleep` because a wall-crawler doesn't nap on your taskbar.

window.CHARACTERS = window.CHARACTERS || {};

const _RED = "#cf2b2b";
const _RED_DARK = "#8f1d1d";
const _BLUE = "#2340a8";
const _BLUE_DARK = "#1a3080";
const _INK = "#141422";

window.CHARACTERS.spider = {
  id: "spider",
  label: "wall-crawler",

  size: { w: 120, h: 172 },
  viewBox: "0 0 120 172",

  capabilities: ["climb", "hang"],

  joints: {
    legL: [52, 116],
    legR: [68, 116],
    armL: [44, 74],
    armR: [76, 74],
    head: [60, 66],
  },

  // No eyes/mouth channels — the mask is rigid. The driver detects the missing
  // elements and substitutes a head-bob for talking.
  rest: {
    legL: 0,
    legR: 0,
    armL: 6,
    armR: -6,
    headTilt: 0,
    bobY: 0,
    lean: 0,
  },

  poses: {
    idle: {},
    walk: {},
    // Splayed wide and low — reads as gripping rather than standing.
    climb: { armL: 34, armR: -34, legL: 20, legR: -20, headTilt: 0, bobY: 4 },
    // Rotation to the ceiling is behavior.js's job. In his own frame this is
    // "feet planted, arms dangling toward my head", which after the 180° flip
    // reads as hanging with his arms falling downward on screen.
    hang: { legL: 9, legR: -9, armL: 168, armR: -168, headTilt: 0, bobY: 2 },
    drag: { legL: -16, legR: 12, armL: 152, armR: -152, headTilt: 5 },
    fall: { legL: -30, legR: 24, armL: 118, armR: -118, headTilt: -4 },
    happy: { armL: 148, armR: -148, legL: -6, legR: 6 },
  },

  cycles: {
    walk: { stride: 24, arm: 22, bob: 3, head: 1.5, rate: 26 },
    // Bigger reach, slower cadence, and a deliberate body rise per grab.
    climb: { stride: 40, arm: 52, bob: 4, head: 3, rate: 20 },
  },

  svg: `
    <g id="flip">
      <g id="bob">
        <g id="legL" transform="translate(52,116)">
          <rect x="-5" y="-2" width="10" height="50" rx="5" fill="${_BLUE_DARK}" />
          <path d="M-5 44 Q-5 54 4 54 Q9 54 9 47 L9 44 Z" fill="${_RED_DARK}" />
        </g>
        <g id="legR" transform="translate(68,116)">
          <rect x="-5" y="-2" width="10" height="50" rx="5" fill="${_BLUE}" />
          <path d="M-5 44 Q-5 54 4 54 Q9 54 9 47 L9 44 Z" fill="${_RED}" />
        </g>

        <g id="armL" transform="translate(44,74)">
          <rect x="-4.5" y="-4" width="9" height="40" rx="4.5" fill="${_BLUE_DARK}" />
          <circle cx="0" cy="39" r="5.5" fill="${_RED_DARK}" />
        </g>

        <g id="torso">
          <!-- Chest, red, with webbing. The top runs up to y=60 — well under the
               head, which draws after it and hides the join. Stopping at the
               neck instead leaves a visible gap that reads as a detached head
               the moment he rotates onto a wall. -->
          <path d="M44 60 Q42 92 43 104 L77 104 Q78 92 76 60 Z" fill="${_RED}" />
          <g stroke="${_RED_DARK}" stroke-width="0.9" fill="none" opacity="0.85">
            <path d="M60 64 L60 104" />
            <path d="M45 68 L75 100" />
            <path d="M75 68 L45 100" />
            <path d="M46 82 Q60 88 74 82" />
            <path d="M45 93 Q60 99 75 93" />
          </g>
          <!-- spider emblem -->
          <g fill="${_INK}">
            <ellipse cx="60" cy="84" rx="3" ry="5" />
            <g stroke="${_INK}" stroke-width="1.3" fill="none" stroke-linecap="round">
              <path d="M57 81 Q50 78 47 82" />
              <path d="M57 84 Q49 84 46 87" />
              <path d="M57 87 Q50 90 48 94" />
              <path d="M63 81 Q70 78 73 82" />
              <path d="M63 84 Q71 84 74 87" />
              <path d="M63 87 Q70 90 72 94" />
            </g>
          </g>
          <!-- pelvis, blue -->
          <path d="M43 104 L77 104 Q76 116 74 121 L46 121 Q44 116 43 104 Z" fill="${_BLUE}" />
          <!-- belt -->
          <rect x="43" y="103" width="34" height="3.5" fill="${_INK}" opacity="0.5" />
        </g>

        <g id="armR" transform="translate(76,74)">
          <rect x="-4.5" y="-4" width="9" height="40" rx="4.5" fill="${_BLUE}" />
          <circle cx="0" cy="39" r="5.5" fill="${_RED}" />
        </g>

        <!-- head: origin is the neck, so the mask is drawn at negative y -->
        <g id="head" transform="translate(60,66)">
          <ellipse cx="0" cy="-26" rx="23" ry="26" fill="${_RED}" />
          <!-- webbing on the mask: radial spokes + concentric arcs -->
          <g stroke="${_RED_DARK}" stroke-width="0.85" fill="none" opacity="0.9">
            <path d="M0 -52 L0 -2" />
            <path d="M-21 -38 L21 -14" />
            <path d="M21 -38 L-21 -14" />
            <path d="M-23 -26 L23 -26" />
            <path d="M-19 -43 Q0 -36 19 -43" />
            <path d="M-22 -33 Q0 -26 22 -33" />
            <path d="M-22 -20 Q0 -13 22 -20" />
            <path d="M-16 -9 Q0 -3 16 -9" />
          </g>
          <!-- lenses -->
          <g stroke="${_INK}" stroke-width="1.7">
            <ellipse cx="-10" cy="-29" rx="9.5" ry="6.8" transform="rotate(-17 -10 -29)" fill="#ffffff" />
            <ellipse cx="10" cy="-29" rx="9.5" ry="6.8" transform="rotate(17 10 -29)" fill="#ffffff" />
          </g>
          <g fill="#e8ecf5" opacity="0.65">
            <ellipse cx="-12" cy="-31" rx="3.2" ry="2" transform="rotate(-17 -12 -31)" />
            <ellipse cx="8" cy="-31" rx="3.2" ry="2" transform="rotate(17 8 -31)" />
          </g>
        </g>
      </g>
    </g>
  `,
};
