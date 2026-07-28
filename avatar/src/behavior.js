// The brain stem. Deterministic state machine + physics, ~60fps, no LLM in the
// loop — design principle #2: the LLM decides *what*, code executes *how*.
//
// The world is no longer just a floor. A character is attached to a SURFACE, and
// which surfaces it may use comes from its declared capabilities:
//
//   ┌──────────── ceiling ────────────┐   walk / hang     (needs "hang")
//   │ w                             w │
//   │ a        ▲ climb              a │   climb           (needs "climb")
//   │ l        │                    l │
//   │ l                             l │
//   └───────────── floor ─────────────┘   walk / sit / sleep
//
// Position is tracked as an ANCHOR — the midpoint of the character's feet — not
// as the element's top-left corner. That's what lets the same walk logic drive a
// wall-crawl: the anchor slides along whichever surface it's stuck to, and
// `placement()` converts anchor + surface into the element transform. Deriving
// the corner from the anchor is easy; the reverse is not, once rotation is
// involved.
//
// A character with neither "climb" nor "hang" (the chibi) simply never leaves the
// floor — it turns around at a screen edge where the spider would start climbing.

const Behavior = (() => {
  const WALK_SPEED = 46; // px/s along floor or ceiling
  const CLIMB_SPEED = 34; // px/s up or down a wall
  const GRAVITY = 1500; // px/s²

  // Chance of letting go when reaching the end of a wall or ceiling run, rather
  // than transferring to the next surface. Keeps it from looking like it's on
  // rails.
  const DROP_CHANCE = 0.18;

  // Released within this many px of a climbable surface? Stick to it instead of
  // falling. Makes throwing the spider at a wall behave the way you'd expect.
  const STICK_RANGE = 46;

  let W = 120;
  let H = 164;
  let caps = new Set();

  let world = null;
  let ax = 200; // anchor: feet midpoint, window-local
  let ay = 0;
  let surface = "floor"; // floor | ceiling | wall-left | wall-right | air
  let vy = 0; // screen-space fall velocity
  let dir = 1; // along-surface direction: +1 = right (floor/ceiling) or down (walls)
  let targetAlong = null;

  let state = "idle";
  let stateTime = 0;
  let dwell = 2;

  let intent = null;
  let focusedApp = null;
  let grabbed = false;
  let placed = false;

  const listeners = {};

  function on(evt, fn) {
    (listeners[evt] ||= []).push(fn);
  }
  function emit(evt, ...args) {
    for (const fn of listeners[evt] || []) fn(...args);
  }

  // -------------------------------------------------------------------- init --

  function init({ size, capabilities }) {
    W = size.w;
    H = size.h;
    caps = new Set(capabilities || []);
  }

  const can = (c) => caps.has(c);

  // ---------------------------------------------------------------- geometry --

  // Work area (taskbar-excluded) of the display under a given window-local x,
  // in window-local coords.
  function areaAt(px) {
    if (!world) return { x1: 0, y1: 0, x2: 800, y2: 600 };
    const sx = px + world.origin.x;
    const d =
      world.displays.find(
        (s) => sx >= s.bounds.x && sx < s.bounds.x + s.bounds.width
      ) || world.displays[0];
    if (!d) return { x1: 0, y1: 0, x2: world.size.width, y2: world.size.height };
    return {
      x1: d.workArea.x - world.origin.x,
      y1: d.workArea.y - world.origin.y,
      x2: d.workArea.x + d.workArea.width - world.origin.x,
      y2: d.workArea.y + d.workArea.height - world.origin.y,
    };
  }

  const area = () => areaAt(ax);

  function setWorld(layout) {
    world = layout;
    if (!placed) {
      // Drop in on the floor, right of centre.
      const a = areaAt(world.size.width * 0.72);
      ax = Math.min(a.x2 - W / 2, world.size.width * 0.72);
      ay = a.y2;
      surface = "floor";
      targetAlong = ax;
      placed = true;
    } else if (surface === "floor") {
      ay = area().y2; // taskbar may have moved
    }
  }

  /**
   * Anchor + surface -> element transform.
   *
   * Rotations are chosen so the character's own "down" points into the surface:
   * +90° puts its feet to the screen-left (left wall), -90° to the screen-right,
   * 180° upward (ceiling). Because rotation happens about the element's centre,
   * the offsets below place the *rotated* footprint against the surface.
   */
  function placement() {
    switch (surface) {
      case "ceiling":
        return { x: ax - W / 2, y: ay, rot: 180 };
      case "wall-left":
        return { x: ax + H / 2 - W / 2, y: ay - H / 2, rot: 90 };
      case "wall-right":
        return { x: ax - H / 2 - W / 2, y: ay - H / 2, rot: -90 };
      default: // floor, air
        return { x: ax - W / 2, y: ay - H, rot: 0 };
    }
  }

  // Axis-aligned screen box the character actually occupies. On a wall its long
  // axis is horizontal, so width and height swap — the renderer needs this for
  // hover detection or you couldn't click a climbing character.
  function hitbox() {
    const p = placement();
    if (surface === "wall-left" || surface === "wall-right") {
      return { x: p.x + W / 2 - H / 2, y: p.y + H / 2 - W / 2, w: H, h: W };
    }
    return { x: p.x, y: p.y, w: W, h: H };
  }

  const isWall = (s = surface) => s === "wall-left" || s === "wall-right";

  // Position along the current surface, and its legal range. Both surfaces use
  // the character's WIDTH as the along-extent (on a wall, width runs vertically).
  const alongGet = () => (isWall() ? ay : ax);
  function alongSet(v) {
    if (isWall()) ay = v;
    else ax = v;
  }
  function alongBounds() {
    const a = area();
    return isWall() ? [a.y1 + W / 2, a.y2 - W / 2] : [a.x1 + W / 2, a.x2 - W / 2];
  }

  // Pin the anchor to the surface it's attached to.
  function reseat() {
    const a = area();
    if (surface === "floor") ay = a.y2;
    else if (surface === "ceiling") ay = a.y1;
    else if (surface === "wall-left") ax = a.x1;
    else if (surface === "wall-right") ax = a.x2;
  }

  // A 180° or ±90° rotation mirrors the local frame, so the sprite has to be
  // flipped to keep it facing the way it's travelling.
  function facingFor(d) {
    if (surface === "ceiling" || surface === "wall-right") return -d;
    return d;
  }

  const movingState = () => (isWall() ? "climb" : "walk");
  const restingState = () => (surface === "ceiling" ? "hang" : "idle");
  const speedFor = (s) => (s === "climb" ? CLIMB_SPEED : WALK_SPEED);

  // ----------------------------------------------------------- surface moves --

  function attach(next, direction) {
    surface = next;
    reseat();
    dir = direction;
    Character.setFacing(facingFor(dir));
  }

  /** Reached the end of the current surface. Transfer, turn around, or drop. */
  function atBoundary(atLowEnd) {
    // Falling off is always an option once you're off the floor.
    if (surface !== "floor" && Math.random() < DROP_CHANCE) return letGo();

    if (surface === "floor") {
      const wall = atLowEnd ? "wall-left" : "wall-right";
      if (can("climb")) {
        attach(wall, -1); // -1 along a wall = upward
        return enter("climb");
      }
      dir = -dir; // no wall skills: turn around
      Character.setFacing(facingFor(dir));
      return enter("idle");
    }

    if (isWall()) {
      if (atLowEnd) {
        // Top of the wall.
        if (can("hang")) {
          attach("ceiling", surface === "wall-left" ? 1 : -1);
          return enter(Math.random() < 0.5 ? "walk" : "hang");
        }
        dir = 1; // head back down
        Character.setFacing(facingFor(dir));
        return enter("climb");
      }
      attach("floor", surface === "wall-left" ? 1 : -1); // back on the ground
      return enter("idle");
    }

    // Ceiling: climb down whichever wall we reached.
    const wall = atLowEnd ? "wall-left" : "wall-right";
    if (can("climb")) {
      attach(wall, 1); // +1 along a wall = downward
      return enter("climb");
    }
    return letGo();
  }

  // Head toward the middle of a wall we just landed on, so being stuck near the
  // bottom doesn't immediately dump us back onto the floor.
  function climbDirToward(a) {
    const mid = (a.y1 + a.y2) / 2;
    return ay > mid ? -1 : 1; // -1 = up, +1 = down
  }

  function letGo() {
    surface = "air";
    vy = 0;
    return enter("fall");
  }

  // -------------------------------------------------------------------- FSM --

  function enter(next) {
    state = next;
    stateTime = 0;
    Character.setPose(next);

    switch (next) {
      case "idle":
        dwell = 2 + Math.random() * 4;
        break;
      case "hang":
        dwell = 6 + Math.random() * 14;
        break;
      case "walk":
      case "climb": {
        const [lo, hi] = alongBounds();
        const here = alongGet();
        if (targetAlong === null || Math.abs(targetAlong - here) < 30) {
          targetAlong = lo + Math.random() * Math.max(1, hi - lo);
        }
        targetAlong = Math.max(lo, Math.min(hi, targetAlong));
        dir = targetAlong >= here ? 1 : -1;
        Character.setFacing(facingFor(dir));
        dwell = Infinity; // ends on arrival
        break;
      }
      case "sit":
        dwell = 5 + Math.random() * 10;
        break;
      case "sleep":
        dwell = 20 + Math.random() * 40;
        break;
      case "drag":
      case "fall":
        dwell = Infinity;
        break;
    }
    emit("state", state);
  }

  // Per-surface options, filtered by what this character can actually do.
  function optionsFor() {
    if (surface === "ceiling") return { walk: 0.5, hang: 0.5 };
    if (isWall()) return { climb: 0.72, idle: 0.28 };

    const w = { walk: 0.55, idle: 0.17 };
    if (can("sit")) w.sit = 0.2;
    if (can("sleep")) w.sleep = 0.08;

    // The focused app tilts the table a little.
    const app = (focusedApp || "").toLowerCase();
    if (app.includes("code") || app.includes("devenv") || app.includes("idea")) {
      if (w.sit) w.sit += 0.2; // you're working — settle down and watch
      w.walk -= 0.15;
    } else if (app.includes("chrome") || app.includes("msedge") || app.includes("firefox")) {
      w.walk += 0.1; // browsing — restless
    }
    return w;
  }

  function pickNext() {
    if (intent) {
      const { action, text } = intent;
      intent = null;
      if (text) emit("say", text);

      const [lo, hi] = alongBounds();
      switch (action) {
        case "approach":
          targetAlong = lo + (hi - lo) * (0.35 + Math.random() * 0.3);
          return movingState();
        case "peek": {
          const here = alongGet();
          targetAlong = here - lo < hi - here ? lo : hi;
          return movingState();
        }
        case "sleep":
          if (can("sleep") && surface === "floor") return "sleep";
          return restingState();
        case "wander":
          targetAlong = null;
          return movingState();
        case "idle":
          return restingState();
      }
    }

    const w = optionsFor();
    const total = Object.values(w).reduce((a, b) => a + Math.max(0, b), 0);
    let r = Math.random() * total;
    for (const [k, v] of Object.entries(w)) {
      r -= Math.max(0, v);
      if (r <= 0) return k;
    }
    return restingState();
  }

  // ----------------------------------------------------------------- update --

  function update(dt) {
    stateTime += dt;
    let speed = 0;

    switch (state) {
      case "walk":
      case "climb": {
        speed = speedFor(state);
        const [lo, hi] = alongBounds();
        let next = alongGet() + dir * speed * dt;

        if (next <= lo || next >= hi) {
          alongSet(Math.max(lo, Math.min(hi, next)));
          reseat();
          atBoundary(next <= lo);
          break;
        }

        alongSet(next);
        reseat(); // the floor can change height mid-stride across monitors

        if (Math.abs(alongGet() - targetAlong) < speed * dt + 1) {
          alongSet(targetAlong);
          enter(restingState());
        }
        break;
      }

      case "fall": {
        vy += GRAVITY * dt;
        ay += vy * dt;
        const floorY = areaAt(ax).y2;
        if (ay >= floorY) {
          ay = floorY;
          vy = 0;
          surface = "floor";
          enter("idle");
        }
        break;
      }

      case "drag":
        break; // position written by grabMove()

      default:
        if (stateTime >= dwell) enter(pickNext());
    }

    Character.update(dt, state, speed);
    const p = placement();
    return { x: p.x, y: p.y, rot: p.rot, state };
  }

  // ------------------------------------------------------------ interaction --

  function grab() {
    grabbed = true;
    // Preserve the on-screen position across the switch to airborne. Without
    // this, grabbing a character off a wall snaps it by half its own height as
    // the rotation drops away.
    const hb = hitbox();
    const cx = hb.x + hb.w / 2;
    const cy = hb.y + hb.h / 2;
    surface = "air";
    ax = cx;
    ay = cy + H / 2;
    vy = 0;
    enter("drag");
  }

  // Takes ELEMENT top-left coords (what the pointer maths produces) and converts
  // to the anchor. Airborne, so no rotation to undo.
  function grabMove(elemX, elemY) {
    if (!grabbed) return;
    ax = elemX + W / 2;
    ay = elemY + H;
  }

  function release() {
    if (!grabbed) return;
    grabbed = false;

    const a = area();

    // Distances from the character's own EDGES to each surface — not from the
    // anchor. The anchor is the midpoint of the feet, so a character flush
    // against a wall still has its anchor half its width away; measuring from
    // there means the stick test can never fire for anything wider than
    // 2*STICK_RANGE.
    const gapLeft = ax - W / 2 - a.x1;
    const gapRight = a.x2 - (ax + W / 2);
    const gapTop = ay - H - a.y1;

    if (can("climb") && gapLeft < STICK_RANGE && gapLeft <= gapRight) {
      attach("wall-left", climbDirToward(a));
      return enter("climb");
    }
    if (can("climb") && gapRight < STICK_RANGE) {
      attach("wall-right", climbDirToward(a));
      return enter("climb");
    }
    if (can("hang") && gapTop < STICK_RANGE) {
      attach("ceiling", Math.random() < 0.5 ? 1 : -1);
      return enter("hang");
    }

    if (ay < a.y2 - 2) return letGo();
    surface = "floor";
    reseat();
    enter("idle");
  }

  function poke() {
    if (state === "sleep" || state === "sit") enter("idle");
    Character.setPose("happy");
    Character.talk(0.6);
  }

  // -------------------------------------------------------------- external --

  // Backend nudge. Queued, applied at the next transition so it never interrupts
  // a stride mid-flight. If we're off the floor, come down first — every intent
  // is phrased in terms of the human's screen, not a wall.
  function setIntent(next) {
    intent = next;
    if (surface !== "floor" && surface !== "air") {
      letGo();
    } else if (state === "idle" || state === "sit" || state === "sleep" || state === "hang") {
      enter(pickNext());
    }
  }

  function setFocusedApp(app) {
    focusedApp = app;
  }

  return {
    init,
    setWorld,
    update,
    grab,
    grabMove,
    release,
    poke,
    setIntent,
    setFocusedApp,
    on,
    hitbox,
    get state() { return state; },
    get surface() { return surface; },
    get pos() { const p = placement(); return { x: p.x, y: p.y }; },
    get size() { return { w: W, h: H }; },
  };
})();
