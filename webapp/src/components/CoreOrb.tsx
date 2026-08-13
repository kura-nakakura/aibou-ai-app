"use client";

/**
 * CoreOrb — THE FORGE OS centerpiece, a real-time 3D core on a 2D canvas.
 *
 * The look: a segmented chrome shell wrapped around a blinding white-blue
 * singularity, crossed by wide gyroscope rings that pass in front of and
 * behind the sphere. Light escapes through the gaps between the armour
 * plates, and an anamorphic lens flare streaks out of the centre.
 *
 * Everything is drawn per-frame with real 3D projection — no image assets, no
 * WebGL, no dependencies:
 *   1. bloom            — wide pale-blue haze
 *   2. dust (back)      — sparse cyan motes behind the core
 *   3. rings (back)     — ribbon segments whose depth is behind the sphere
 *   4. shell            — inner glow disc, then front-facing armour plates
 *   5. flare            — hot centre + horizontal/vertical streaks (additive)
 *   6. rings (front)    — ribbon segments in front of the sphere
 *   7. dust (front) + halo pings
 *
 * Ring ribbons are depth-sorted per segment, which is what lets a single ring
 * wrap the sphere instead of always sitting on top of it.
 *
 * The `state` prop tunes spin / glow / pulse so the core feels alive while
 * listening / speaking / thinking. Pointer movement leans the whole assembly.
 * Honors prefers-reduced-motion (single static frame) and pauses when hidden.
 */

import { useEffect, useRef } from "react";

export type CoreState = "idle" | "listening" | "speaking" | "thinking";

export interface CoreOrbProps {
  /** Diameter in px (layout size — the canvas paints beyond it for the rings). */
  size?: number;
  /** Current assistant state — tunes glow + animation. */
  state?: CoreState;
  className?: string;
}

interface Tune {
  /** Shell yaw speed (rad/s). */
  spin: number;
  /** Pale-blue bloom alpha. */
  glow: number;
  /** Cyan accent alpha (focus/active). */
  cyan: number;
  /** Core pulse frequency (Hz) and amplitude (fraction of radius). */
  pulseHz: number;
  pulseAmp: number;
  /** Ring spin multiplier — >1 spins faster (more energy). */
  orbit: number;
  /** Halo ping period (s). */
  ping: number;
  /** Lens-flare length multiplier. */
  flare: number;
}

const TUNES: Record<CoreState, Tune> = {
  idle: { spin: 0.14, glow: 0.30, cyan: 0.10, pulseHz: 0.22, pulseAmp: 0.014, orbit: 1.0, ping: 4.5, flare: 1.0 },
  listening: { spin: 0.30, glow: 0.44, cyan: 0.50, pulseHz: 0.60, pulseAmp: 0.030, orbit: 2.0, ping: 1.8, flare: 1.3 },
  speaking: { spin: 0.46, glow: 0.52, cyan: 0.40, pulseHz: 1.10, pulseAmp: 0.045, orbit: 2.6, ping: 1.2, flare: 1.5 },
  thinking: { spin: 0.24, glow: 0.46, cyan: 0.28, pulseHz: 0.42, pulseAmp: 0.024, orbit: 1.4, ping: 2.6, flare: 1.15 },
};

/**
 * Gyroscope rings. Each is a flat annulus (rIn..rOut, as a fraction of `size`)
 * tilted by rx then rotated by rz, so they cross at different angles like the
 * gimbals of a gyroscope. `period` is seconds per revolution (sign = spin
 * direction); `ticks` adds radial notches for the instrument feel.
 */
const RINGS = [
  { rz: 0.26, rx: 1.16, rIn: 0.385, rOut: 0.478, alpha: 1.0, period: 9 },
  { rz: -0.62, rx: 1.34, rIn: 0.452, rOut: 0.516, alpha: 0.82, period: -13 },
  { rz: 1.05, rx: 0.98, rIn: 0.530, rOut: 0.549, alpha: 0.40, period: 19 },
] as const;

/**
 * Armour petals — plates ringing the light with the FRONT LEFT OPEN, like an
 * iris. Their axis points at the viewer and they roll around it, so the
 * aperture stays facing us while the shell keeps turning. (A lat/long grid
 * covering the whole sphere just reads as a beach ball; this reads as a shell
 * cracked open around a singularity.)
 *
 * theta = angle off the view axis (0 = straight at the viewer),
 * phi    = position around the ring.
 */
const PETALS = 7;
const PETAL_GAP = 0.085;     // radians of phi trimmed each side → seams
const THETA_IN = 0.60;       // ~34°: inner edge = aperture radius
const THETA_OUT = 1.52;      // ~87°: outer edge reaches the silhouette
const DUST = 90;
const PERSPECTIVE = 4.0;
/** Light direction (upper-left, towards the viewer) for plate shading. */
const LX = -0.42, LY = -0.56, LZ = 0.72;

export default function CoreOrb({ size = 140, state = "idle", className = "" }: CoreOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef<CoreState>(state);
  stateRef.current = state;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduce = typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // The stage is larger than the layout box so ring ribbons and the flare
    // aren't clipped. Perspective can push near points out to ~1.33×.
    const stage = Math.ceil(size * 1.5);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = stage * dpr;
    canvas.height = stage * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const cx = stage / 2;
    const cy = stage / 2;
    const shellR = size * 0.285;      // armour sphere radius
    const dustR = size * 0.60;        // dust cloud radius

    // Sparse motes suspended around the core (fibonacci sphere, jittered out).
    const golden = Math.PI * (3 - Math.sqrt(5));
    const dust = Array.from({ length: DUST }, (_, i) => {
      const y = 1 - (i / (DUST - 1)) * 2;
      const r = Math.sqrt(Math.max(0, 1 - y * y));
      const th = golden * i;
      // Deterministic pseudo-random radius so the cloud isn't a hollow shell.
      const jitter = 0.55 + ((Math.sin(i * 12.9898) * 43758.5453) % 1 + 1) % 1 * 0.45;
      return { x: Math.cos(th) * r, y, z: Math.sin(th) * r, k: jitter, tw: (i % 9) / 9 };
    });

    // Pre-compute each plate's border in unit-sphere space (border is walked
    // once per frame and projected, so build it here rather than per frame).
    /** Unit-sphere point from (theta off the view axis, phi around it). */
    const on = (th: number, ph: number) => ({
      x: Math.sin(th) * Math.cos(ph),
      y: Math.sin(th) * Math.sin(ph),
      z: Math.cos(th),
    });
    // Petal borders, plus the mid-points of the inner and outer edges so each
    // plate can be lit from the aperture side (the light is inside the shell).
    const plates = Array.from({ length: PETALS }, (_, k) => {
      const ph0 = (k / PETALS) * Math.PI * 2 + PETAL_GAP;
      const ph1 = ((k + 1) / PETALS) * Math.PI * 2 - PETAL_GAP;
      const N = 6;
      const pts: { x: number; y: number; z: number }[] = [];
      for (let i = 0; i <= N; i++) pts.push(on(THETA_IN, ph0 + ((ph1 - ph0) * i) / N));
      for (let i = 1; i <= N; i++) pts.push(on(THETA_IN + ((THETA_OUT - THETA_IN) * i) / N, ph1));
      for (let i = 1; i <= N; i++) pts.push(on(THETA_OUT, ph1 - ((ph1 - ph0) * i) / N));
      for (let i = 1; i < N; i++) pts.push(on(THETA_OUT - ((THETA_OUT - THETA_IN) * i) / N, ph0));
      const phMid = (ph0 + ph1) / 2;
      return {
        pts,
        inner: on(THETA_IN, phMid),
        outer: on(THETA_OUT, phMid),
        normal: on((THETA_IN + THETA_OUT) / 2, phMid),
      };
    });

    // Smoothly-lerped live tune + pointer parallax.
    const live: Tune = { ...TUNES[stateRef.current] };
    let px = 0, py = 0;        // parallax target (-1..1)
    let lpx = 0, lpy = 0;      // lerped parallax
    const onPointer = (e: PointerEvent) => {
      px = (e.clientX / window.innerWidth) * 2 - 1;
      py = (e.clientY / window.innerHeight) * 2 - 1;
    };
    window.addEventListener("pointermove", onPointer, { passive: true });

    let raf = 0;
    let last = performance.now();
    let t = 0;

    const draw = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;
      t += dt;

      const target = TUNES[stateRef.current] ?? TUNES.idle;
      (Object.keys(target) as (keyof Tune)[]).forEach((k) => {
        live[k] += (target[k] - live[k]) * Math.min(1, dt * 4);
      });
      lpx += (px - lpx) * Math.min(1, dt * 3);
      lpy += (py - lpy) * Math.min(1, dt * 3);

      // The world turns slowly (rings + dust lean with the pointer), while the
      // petals roll around the view axis so the aperture keeps facing us.
      const yaw = t * live.spin * 0.5 + lpx * 0.45;
      const pitch = Math.sin(t * 0.3) * 0.09 + lpy * 0.28;
      const roll = t * live.spin * 2.2;
      const cosY = Math.cos(yaw), sinY = Math.sin(yaw);
      const cosP = Math.cos(pitch), sinP = Math.sin(pitch);
      const cosR = Math.cos(roll), sinR = Math.sin(roll);
      const pulse = 1 + live.pulseAmp * Math.sin(t * live.pulseHz * Math.PI * 2);

      ctx.clearRect(0, 0, stage, stage);

      /** World rotation (yaw then pitch) + perspective projection. */
      const project = (x0: number, y0: number, z0: number, radius: number) => {
        const x1 = x0 * cosY + z0 * sinY;
        const z1 = -x0 * sinY + z0 * cosY;
        const y2 = y0 * cosP - z1 * sinP;
        const z2 = y0 * sinP + z1 * cosP;
        const s = PERSPECTIVE / (PERSPECTIVE - z2);
        return { sx: cx + x1 * radius * s, sy: cy + y2 * radius * s, z: z2, s };
      };
      /** Roll around the view axis — applied to petals before world rotation. */
      const rollPt = (p: { x: number; y: number; z: number }) => ({
        x: p.x * cosR - p.y * sinR,
        y: p.x * sinR + p.y * cosR,
        z: p.z,
      });
      /** Rotate a direction (no projection) — for plate normals. */
      const rotate = (x0: number, y0: number, z0: number) => {
        const x1 = x0 * cosY + z0 * sinY;
        const z1 = -x0 * sinY + z0 * cosY;
        return { x: x1, y: y0 * cosP - z1 * sinP, z: y0 * sinP + z1 * cosP };
      };

      /* 1 — bloom */
      const bloom = ctx.createRadialGradient(cx, cy, shellR * 0.2, cx, cy, size * 0.72);
      bloom.addColorStop(0, `rgba(170,215,255,${(live.glow * 0.5).toFixed(3)})`);
      bloom.addColorStop(0.5, `rgba(120,180,255,${(live.glow * 0.14).toFixed(3)})`);
      bloom.addColorStop(1, "rgba(120,180,255,0)");
      ctx.fillStyle = bloom;
      ctx.fillRect(0, 0, stage, stage);

      /* 2 — dust (behind) */
      const drawDust = (front: boolean) => {
        for (const d of dust) {
          const q = project(d.x, d.y, d.z, dustR * d.k);
          if (front ? q.z < 0 : q.z >= 0) continue;
          const tw = 0.45 + 0.55 * Math.sin(t * 2.2 + d.tw * Math.PI * 2);
          const a = (front ? 0.30 + q.z * 0.45 : 0.10 + (q.z + 1) * 0.16) * tw;
          ctx.fillStyle = d.tw > 0.5
            ? `rgba(120,235,255,${(a * (0.4 + live.cyan)).toFixed(3)})`
            : `rgba(225,240,255,${(a * 0.7).toFixed(3)})`;
          ctx.beginPath();
          ctx.arc(q.sx, q.sy, Math.max(0.4, size * 0.0055 * q.s), 0, Math.PI * 2);
          ctx.fill();
        }
      };
      drawDust(false);

      /* 3/6 — ring ribbons, split by depth so they wrap the sphere.
         Each segment is a quad between the inner and outer rim. */
      const SEG = 56;
      const ringSegments = (behind: boolean) => {
        for (const ring of RINGS) {
          const cosRZ = Math.cos(ring.rz), sinRZ = Math.sin(ring.rz);
          const cosRX = Math.cos(ring.rx), sinRX = Math.sin(ring.rx);
          const spin = (t * live.orbit * Math.PI * 2) / ring.period;
          /** Point on the ring plane at angle a and radius fraction rf. */
          const at = (a: number, rf: number) => {
            const lx = Math.cos(a + spin), ly = Math.sin(a + spin);
            const y1 = ly * cosRX, z1 = ly * sinRX;
            const gx = lx * cosRZ - y1 * sinRZ;
            const gy = lx * sinRZ + y1 * cosRZ;
            return project(gx, gy, z1, size * rf);
          };
          const rMid = (ring.rIn + ring.rOut) / 2;
          let aIn = at(0, ring.rIn), aOut = at(0, ring.rOut), aMid = at(0, rMid);
          for (let i = 1; i <= SEG; i++) {
            const ang = (i / SEG) * Math.PI * 2;
            const bIn = at(ang, ring.rIn);
            const bOut = at(ang, ring.rOut);
            const bMid = at(ang, rMid);
            const depth = (aIn.z + bIn.z) / 2;
            if (behind === depth >= 0) { aIn = bIn; aOut = bOut; aMid = bMid; continue; }
            // Chrome band: bright where it faces the light, dim edge-on/behind.
            const lit = 0.24 + ((depth + 1) / 2) * 0.76;
            const a = ring.alpha * lit * (behind ? 0.34 : 1);
            ctx.beginPath();
            ctx.moveTo(aIn.sx, aIn.sy);
            ctx.lineTo(aOut.sx, aOut.sy);
            ctx.lineTo(bOut.sx, bOut.sy);
            ctx.lineTo(bIn.sx, bIn.sy);
            ctx.closePath();
            // Mid tone for the band face; the highlight line below sells the metal.
            const base = Math.round(152 + lit * 92);
            ctx.fillStyle = `rgba(${base},${base + 14},${Math.min(255, base + 40)},${(a * 0.85).toFixed(3)})`;
            ctx.fill();
            // Specular line down the middle of the band (brushed chrome).
            ctx.beginPath();
            ctx.moveTo(aMid.sx, aMid.sy);
            ctx.lineTo(bMid.sx, bMid.sy);
            ctx.strokeStyle = `rgba(255,255,255,${(a * 0.85).toFixed(3)})`;
            ctx.lineWidth = Math.max(0.8, size * 0.007);
            ctx.stroke();
            // Cyan energy line along the outer rim.
            ctx.beginPath();
            ctx.moveTo(aOut.sx, aOut.sy);
            ctx.lineTo(bOut.sx, bOut.sy);
            ctx.strokeStyle = `rgba(120,240,255,${(a * (0.40 + live.cyan * 0.5)).toFixed(3)})`;
            ctx.lineWidth = Math.max(0.6, size * 0.004);
            ctx.stroke();
            aIn = bIn;
            aOut = bOut;
            aMid = bMid;
          }
        }
      };
      ringSegments(true);

      /* 4 — shell: interior glow, then the armour plates over it */
      const R = shellR * pulse;
      const inner = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.02);
      inner.addColorStop(0, "rgba(255,255,255,1)");
      inner.addColorStop(0.28, "rgba(226,246,255,0.96)");
      inner.addColorStop(0.6, "rgba(120,205,255,0.72)");
      inner.addColorStop(0.85, "rgba(38,120,200,0.55)");
      inner.addColorStop(1, "rgba(10,40,90,0.35)");
      ctx.fillStyle = inner;
      ctx.beginPath();
      ctx.arc(cx, cy, R * 1.02, 0, Math.PI * 2);
      ctx.fill();

      // Aperture instrument rings — screen-facing circles inside the opening,
      // so the centre reads as a machined iris rather than a plain blob.
      const apR = R * Math.sin(THETA_IN);
      for (const [rf, dashes, alpha] of [[0.78, 18, 0.42], [1.0, 30, 0.30]] as const) {
        const rr = apR * rf;
        for (let i = 0; i < dashes; i++) {
          const a0 = (i / dashes) * Math.PI * 2 + roll * 0.5 * (rf > 0.9 ? -1 : 1);
          ctx.beginPath();
          ctx.arc(cx, cy, rr, a0, a0 + (Math.PI * 2) / dashes * 0.55);
          ctx.strokeStyle = `rgba(150,230,255,${(alpha * (0.5 + live.cyan)).toFixed(3)})`;
          ctx.lineWidth = Math.max(0.5, size * 0.004);
          ctx.stroke();
        }
      }

      // Armour petals, far→near so nearer plates overlap correctly.
      const visible = plates
        .map((pl) => ({ pl, n: rotate(rollPt(pl.normal).x, rollPt(pl.normal).y, pl.normal.z) }))
        .filter((v) => v.n.z > 0.02)
        .sort((a, b) => a.n.z - b.n.z);
      for (const { pl, n } of visible) {
        const diff = Math.max(0, n.x * LX + n.y * LY + n.z * LZ);
        const spec = Math.pow(diff, 9);
        ctx.beginPath();
        pl.pts.forEach((p, i) => {
          const r = rollPt(p);
          const q = project(r.x, r.y, r.z, R);
          if (i === 0) ctx.moveTo(q.sx, q.sy);
          else ctx.lineTo(q.sx, q.sy);
        });
        ctx.closePath();
        // Chrome lit from two sides: the key light outside, and the core's
        // glare from inside — so the edge facing the aperture is blown out.
        const ri = project(rollPt(pl.inner).x, rollPt(pl.inner).y, pl.inner.z, R);
        const ro = project(rollPt(pl.outer).x, rollPt(pl.outer).y, pl.outer.z, R);
        const hi = Math.round(Math.min(255, 205 + diff * 50 + spec * 40));
        const lo = Math.round(Math.min(255, 74 + diff * 120));
        const grad = ctx.createLinearGradient(ri.sx, ri.sy, ro.sx, ro.sy);
        grad.addColorStop(0, `rgba(255,255,255,${(0.90 + n.z * 0.10).toFixed(3)})`);
        grad.addColorStop(0.22, `rgba(${hi},${Math.min(255, hi + 4)},255,${(0.88 + n.z * 0.10).toFixed(3)})`);
        grad.addColorStop(1, `rgba(${lo},${lo + 10},${Math.min(255, lo + 34)},${(0.80 + n.z * 0.16).toFixed(3)})`);
        ctx.fillStyle = grad;
        ctx.fill();
        // Seam edge — light escaping between the plates.
        ctx.strokeStyle = `rgba(190,240,255,${(0.20 + live.cyan * 0.30).toFixed(3)})`;
        ctx.lineWidth = Math.max(0.5, size * 0.0032);
        ctx.stroke();
      }

      /* 5 — hot centre + anamorphic flare (additive) */
      ctx.globalCompositeOperation = "lighter";
      const hotR = R * 0.62;
      const hot = ctx.createRadialGradient(cx, cy, 0, cx, cy, hotR);
      hot.addColorStop(0, "rgba(255,255,255,1)");
      hot.addColorStop(0.22, "rgba(236,250,255,0.85)");
      hot.addColorStop(0.55, "rgba(140,220,255,0.35)");
      hot.addColorStop(1, "rgba(90,190,255,0)");
      ctx.fillStyle = hot;
      ctx.beginPath();
      ctx.arc(cx, cy, hotR, 0, Math.PI * 2);
      ctx.fill();

      // Horizontal streak (long) + vertical (short) = the classic lens cross.
      const streak = (halfW: number, halfH: number, alpha: number) => {
        const g = ctx.createLinearGradient(cx - halfW, cy, cx + halfW, cy);
        g.addColorStop(0, "rgba(150,220,255,0)");
        g.addColorStop(0.5, `rgba(235,250,255,${alpha.toFixed(3)})`);
        g.addColorStop(1, "rgba(150,220,255,0)");
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.ellipse(cx, cy, halfW, halfH, 0, 0, Math.PI * 2);
        ctx.fill();
      };
      const fl = live.flare * (0.94 + 0.06 * Math.sin(t * 3.1));
      // ステージ内で必ずフェードし切る長さに抑える（端で切れると棒に見える）
      const maxHalf = stage * 0.48;
      streak(Math.min(size * 0.62 * fl, maxHalf), Math.max(0.7, size * 0.005), 0.90);
      streak(Math.min(size * 0.28 * fl, maxHalf), Math.max(0.5, size * 0.009), 0.14);
      // Vertical streak: same helper rotated a quarter turn.
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(Math.PI / 2);
      ctx.translate(-cx, -cy);
      streak(size * 0.26 * fl, Math.max(0.6, size * 0.005), 0.45);
      ctx.restore();
      ctx.globalCompositeOperation = "source-over";

      /* 6 — rings in front */
      ringSegments(false);

      /* 7 — dust in front + halo pings */
      drawDust(true);
      const pingPhase = (t % live.ping) / live.ping;
      ctx.beginPath();
      ctx.arc(cx, cy, size * (0.50 + pingPhase * 0.12), 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(150,205,255,${(0.12 * (1 - pingPhase)).toFixed(3)})`;
      ctx.lineWidth = 1;
      ctx.stroke();
      if (live.cyan > 0.12) {
        const p2 = ((t + live.ping / 2) % live.ping) / live.ping;
        ctx.beginPath();
        ctx.arc(cx, cy, size * (0.52 + p2 * 0.14), 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(0,243,255,${(live.cyan * 0.30 * (1 - p2)).toFixed(3)})`;
        ctx.stroke();
      }
    };

    if (reduce) {
      draw(last + 16);
      return () => window.removeEventListener("pointermove", onPointer);
    }

    const loop = (now: number) => {
      draw(now);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);

    const onVis = () => {
      cancelAnimationFrame(raf);
      if (!document.hidden) {
        last = performance.now();
        raf = requestAnimationFrame(loop);
      }
    };
    document.addEventListener("visibilitychange", onVis);

    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("pointermove", onPointer);
    };
  }, [size]);

  const stagePx = Math.ceil(size * 1.5);
  return (
    <div
      className={`relative grid place-items-center ${className}`}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`THE FORGE OS core — ${state}`}
    >
      <canvas
        ref={canvasRef}
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
        style={{ width: stagePx, height: stagePx }}
      />
    </div>
  );
}
