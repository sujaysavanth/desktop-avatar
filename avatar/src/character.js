// The rig driver. Loads a character definition from window.CHARACTERS and turns
// pose requests into SVG transforms.
//
// The contract with behavior.js has not changed: `setPose(name)`, `setFacing()`,
// `talk()`, `update(dt, state, speed)`. Everything character-specific — size,
// joints, poses, walk amplitudes, whether it even HAS a mouth — now comes from
// the definition, which is what makes a second character a data file instead of
// a fork of this one.
//
// Angles are degrees. 0 = limb hanging along the body's own "down". Positive
// swings toward +x in the character's local frame.

const Character = (() => {
  let def = null;
  let el = {};
  let has = { eyes: false, mouth: false };

  let cur = {};
  let target = {};
  let numKeys = [];
  let flagKeys = [];

  let facing = 1; // 1 = right, -1 = left (in the character's local frame)
  let phase = 0;
  let blinkTimer = 1.5;
  let blinkHold = 0;
  let talkTimer = 0;

  // ------------------------------------------------------------------ load --

  function load(id) {
    const registry = window.CHARACTERS || {};
    def = registry[id];
    if (!def) {
      const known = Object.keys(registry).join(", ") || "none loaded";
      throw new Error(`unknown character "${id}" (have: ${known})`);
    }

    const svg = document.getElementById("char");
    svg.setAttribute("viewBox", def.viewBox);
    svg.style.width = `${def.size.w}px`;
    svg.style.height = `${def.size.h}px`;
    svg.innerHTML = def.svg;

    el = {
      flip: document.getElementById("flip"),
      bob: document.getElementById("bob"),
      eyesOpen: document.getElementById("eyes-open"),
      eyesShut: document.getElementById("eyes-shut"),
      mouth: document.getElementById("mouth"),
    };
    for (const joint of Object.keys(def.joints)) {
      el[joint] = document.getElementById(joint);
      if (!el[joint]) console.warn(`[character] ${id}: no element for joint "${joint}"`);
    }

    // Optional features. A rigid mask has neither, and that must not be an error.
    has.eyes = Boolean(el.eyesOpen && el.eyesShut);
    has.mouth = Boolean(el.mouth && def.mouths);

    numKeys = Object.keys(def.rest).filter((k) => typeof def.rest[k] === "number");
    flagKeys = Object.keys(def.rest).filter((k) => typeof def.rest[k] === "string");

    cur = { ...def.rest };
    target = { ...def.rest };
    phase = 0;

    console.log(`[character] loaded "${id}" (${def.size.w}x${def.size.h})`);
    return def;
  }

  // ------------------------------------------------------------------ poses --

  function setPose(name) {
    if (!def) return;
    // Unknown pose falls back to rest rather than throwing — a character that
    // lacks `sit` should stand, not crash.
    const pose = def.poses[name] || def.poses.idle || {};
    target = { ...def.rest, ...pose };
  }

  function setFacing(dir) {
    if (dir !== 0) facing = dir > 0 ? 1 : -1;
  }

  function talk(seconds = 2) {
    talkTimer = Math.max(talkTimer, seconds);
  }

  const lerp = (a, b, t) => a + (b - a) * t;

  // ----------------------------------------------------------------- update --

  /**
   * @param dt     seconds since last frame
   * @param state  behavior state name (drives which cycle, if any, is layered on)
   * @param speed  movement speed along the current surface, px/s
   */
  function update(dt, state, speed = 0) {
    if (!def) return;

    // Frame-rate independent easing toward the target pose.
    const t = 1 - Math.exp(-12 * dt);
    for (const k of numKeys) cur[k] = lerp(cur[k], target[k], t);

    const cycle = def.cycles && def.cycles[state];

    if (cycle && speed > 1) {
      // Procedural locomotion, layered over the eased pose. Same maths for
      // walking and climbing — only the amplitudes differ, per definition.
      phase += dt * (speed / cycle.rate);
      const s = Math.sin(phase * Math.PI * 2);
      const c = Math.cos(phase * Math.PI * 2);
      cur.legL = s * cycle.stride;
      cur.legR = -s * cycle.stride;
      cur.armL = -s * cycle.arm + (def.rest.armL || 0);
      cur.armR = s * cycle.arm + (def.rest.armR || 0);
      cur.bobY = Math.abs(c) * -cycle.bob;
      cur.headTilt = s * cycle.head;
    } else if (state === "idle") {
      phase += dt * 0.35;
      cur.bobY += Math.sin(phase * Math.PI * 2) * 0.8; // breathing
    } else {
      phase += dt * 0.25;
      if (state === "sleep") cur.bobY += Math.sin(phase * Math.PI * 2) * 1.6;
      if (state === "hang") cur.headTilt += Math.sin(phase * Math.PI * 2) * 3; // idle sway
    }

    // --- discrete flags ---
    const flags = {};
    for (const k of flagKeys) flags[k] = target[k];

    // --- blinking (only if this character has eyes; sleep holds them shut) ---
    if (has.eyes && flags.eyes === "open") {
      blinkTimer -= dt;
      if (blinkHold > 0) {
        blinkHold -= dt;
        flags.eyes = "shut";
      } else if (blinkTimer <= 0) {
        blinkHold = 0.09;
        blinkTimer = 2 + Math.random() * 4;
      }
    }

    // --- talking ---
    if (talkTimer > 0) {
      talkTimer -= dt;
      if (has.mouth) {
        flags.mouth = Math.sin(performance.now() / 70) > 0 ? "talk" : "flat";
      } else {
        // No mouth to move, so the whole head nods instead. Without this a
        // masked character would deliver a whole paragraph stone still.
        cur.headTilt += Math.sin(performance.now() / 90) * 2.5;
        cur.bobY += Math.sin(performance.now() / 110) * 0.7;
      }
    }

    draw(flags);
  }

  function draw(flags) {
    el.flip.setAttribute(
      "transform",
      facing === 1 ? "" : `translate(${def.size.w},0) scale(-1,1)`
    );

    const pivotY = def.size.h * 0.7; // lean/roll about the hips, not the middle
    el.bob.setAttribute(
      "transform",
      `translate(0,${cur.bobY.toFixed(2)}) rotate(${cur.lean.toFixed(2)} ${def.size.w / 2} ${pivotY})`
    );

    for (const [joint, [jx, jy]] of Object.entries(def.joints)) {
      const node = el[joint];
      if (!node) continue;
      const angle = joint === "head" ? cur.headTilt : cur[joint];
      node.setAttribute("transform", `translate(${jx},${jy}) rotate(${(angle || 0).toFixed(2)})`);
    }

    if (has.eyes) {
      const shut = flags.eyes === "shut";
      el.eyesOpen.style.display = shut ? "none" : "";
      el.eyesShut.style.display = shut ? "" : "none";
      el.eyesOpen.classList.toggle("happy", flags.eyes === "happy");
    }

    if (has.mouth) {
      el.mouth.setAttribute("d", def.mouths[flags.mouth] || def.mouths.smile);
    }
  }

  return {
    load,
    setPose,
    setFacing,
    talk,
    update,
    get facing() { return facing; },
    get size() { return def ? def.size : { w: 120, h: 164 }; },
    get capabilities() { return def ? def.capabilities || [] : []; },
    get id() { return def ? def.id : null; },
  };
})();
