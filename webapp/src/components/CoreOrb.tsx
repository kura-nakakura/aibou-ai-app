"use client";

/**
 * CoreOrb — THE FORGE OS centerpiece, a real-time 3D core on a 2D canvas.
 *
 * A fibonacci-sphere particle shell orbits a glowing pale-blue core, wrapped in
 * wide chrome gyroscope rings that pass in front of and behind the sphere, with
 * an anamorphic flare streaking out of the blown-out centre.
 *
 * Draw order (all real 3D projection — no images, no WebGL, no deps):
 *   1. bloom          — wide pale-blue haze
 *   2. shell (back)   — the half of the particle shell behind the body
 *   3. rings (back)   — ribbon segments whose depth is behind the sphere
 *   4. body           — the core sphere: white centre → deep navy rim
 *   5. shell (front)  — the bright half of the particle shell
 *   6. flare          — hot centre + horizontal/vertical streaks (additive)
 *   7. rings (front)  — ribbon segments in front of the sphere
 *   8. halo ping      — a soft expanding ring that marks the current state
 *
 * Two details are deliberate, learned from versions that looked wrong:
 *   · Ring ribbons are depth-sorted PER SEGMENT, which is what lets one ring
 *     wrap the sphere instead of always sitting on top of it. Adjacent segments
 *     overlap slightly and are filled opaquely, because abutting antialiased
 *     edges leave hairline seams that read as hatching along the band.
 *   · The shell is particles, not solid armour plates. Plates big enough to
 *     read as armour deform the silhouette as they cross it, which makes the
 *     rotation look like flapping rather than turning.
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
  /** Sphere yaw speed (rad/s). */
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
  idle: { spin: 0.16, glow: 0.30, cyan: 0.06, pulseHz: 0.22, pulseAmp: 0.014, orbit: 1.0, ping: 4.5, flare: 1.0 },
  listening: { spin: 0.34, glow: 0.42, cyan: 0.38, pulseHz: 0.60, pulseAmp: 0.030, orbit: 1.9, ping: 1.8, flare: 1.25 },
  speaking: { spin: 0.52, glow: 0.50, cyan: 0.30, pulseHz: 1.10, pulseAmp: 0.045, orbit: 2.4, ping: 1.2, flare: 1.4 },
  thinking: { spin: 0.28, glow: 0.45, cyan: 0.20, pulseHz: 0.42, pulseAmp: 0.024, orbit: 1.4, ping: 2.6, flare: 1.1 },
};

/**
 * Gyroscope rings: flat annuli (rIn..rOut as a fraction of `size`) tilted by rx
 * then rotated by rz, so they cross at different angles like gimbals. `period`
 * is seconds per revolution (sign = direction). Tilts stay clear of edge-on —
 * a near-edge-on ring projects to a straight line and reads as a stray streak.
 */
const RINGS = [
  { rz: 0.22, rx: 1.10, rIn: 0.392, rOut: 0.462, alpha: 1.0, period: 16, soft: false },
  { rz: -0.56, rx: 1.22, rIn: 0.444, rOut: 0.498, alpha: 0.78, period: -24, soft: false },
  { rz: 0.58, rx: 1.30, rIn: 0.498, rOut: 0.546, alpha: 0.40, period: 34, soft: true },
] as const;

const PARTICLES = 460;
const PERSPECTIVE = 3.6;
const SEG = 60;              // ring segments (also the depth-sort granularity)

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
    // aren't clipped at the edges.
    const stage = Math.ceil(size * 1.5);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = stage * dpr;
    canvas.height = stage * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const cx = stage / 2;
    const cy = stage / 2;
    const R = size * 0.325;    // particle-shell radius (just above the body)
    const coreR = size * 0.31;

    // Fibonacci sphere — evenly distributed particle shell.
    const pts: { x: number; y: number; z: number; tw: number }[] = [];
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < PARTICLES; i++) {
      const y = 1 - (i / (PARTICLES - 1)) * 2;
      const r = Math.sqrt(Math.max(0, 1 - y * y));
      const th = golden * i;
      pts.push({ x: Math.cos(th) * r, y, z: Math.sin(th) * r, tw: (i % 7) / 7 });
    }

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

      const yaw = t * live.spin * 2 + lpx * 0.45;
      const pitch = Math.sin(t * 0.35) * 0.10 + lpy * 0.30;
      const cosY = Math.cos(yaw), sinY = Math.sin(yaw);
      const cosP = Math.cos(pitch), sinP = Math.sin(pitch);
      const pulse = 1 + live.pulseAmp * Math.sin(t * live.pulseHz * Math.PI * 2);

      ctx.clearRect(0, 0, stage, stage);

      /** Project a point on a sphere of the given radius; returns screen pos,
       *  depth (-1 far … +1 near) and the perspective scale. */
      const project = (x0: number, y0: number, z0: number, radius: number) => {
        const x1 = x0 * cosY + z0 * sinY;
        const z1 = -x0 * sinY + z0 * cosY;
        const y2 = y0 * cosP - z1 * sinP;
        const z2 = y0 * sinP + z1 * cosP;
        const s = PERSPECTIVE / (PERSPECTIVE - z2);
        return { sx: cx + x1 * radius * s, sy: cy + y2 * radius * s, z: z2, s };
      };

      /* 1 — bloom */
      const bloom = ctx.createRadialGradient(cx, cy, coreR * 0.3, cx, cy, size * 0.70);
      bloom.addColorStop(0, `rgba(155,205,255,${(live.glow * 0.5).toFixed(3)})`);
      bloom.addColorStop(0.55, `rgba(120,180,255,${(live.glow * 0.15).toFixed(3)})`);
      bloom.addColorStop(1, "rgba(120,180,255,0)");
      ctx.fillStyle = bloom;
      ctx.fillRect(0, 0, stage, stage);

      /* 2/5 — particle shell, split by depth around the body */
      const shell = (front: boolean) => {
        for (const p of pts) {
          const q = project(p.x, p.y, p.z, R * pulse);
          if (front ? q.z < 0 : q.z >= 0) continue;
          if (front) {
            const tw = 0.7 + 0.3 * Math.sin(t * 2.4 + p.tw * Math.PI * 2);
            const a = (0.18 + q.z * 0.52) * tw;
            ctx.fillStyle = live.cyan > 0.1 && p.tw > 0.6
              ? `rgba(120,240,255,${a.toFixed(3)})`
              : `rgba(225,240,255,${a.toFixed(3)})`;
            ctx.beginPath();
            ctx.arc(q.sx, q.sy, Math.max(0.45, size * 0.0052 * q.s), 0, Math.PI * 2);
            ctx.fill();
          } else {
            const tw = 0.75 + 0.25 * Math.sin(t * 2 + p.tw * Math.PI * 2);
            const a = (0.05 + ((q.z + 1) / 2) * 0.30) * tw;
            ctx.fillStyle = `rgba(140,185,250,${a.toFixed(3)})`;
            ctx.beginPath();
            ctx.arc(q.sx, q.sy, Math.max(0.35, size * 0.0038 * q.s), 0, Math.PI * 2);
            ctx.fill();
          }
        }
      };
      shell(false);

      /* 3/7 — ring ribbons. Each segment is a quad between the inner and outer
         rim, drawn in the pass matching its depth so the band wraps the sphere. */
      const step = (Math.PI * 2) / SEG;
      const ringSegments = (behind: boolean) => {
        for (const ring of RINGS) {
          const cosRZ = Math.cos(ring.rz), sinRZ = Math.sin(ring.rz);
          const cosRX = Math.cos(ring.rx), sinRX = Math.sin(ring.rx);
          const spin = (t * live.orbit * Math.PI * 2) / ring.period;
          const rMid = (ring.rIn + ring.rOut) / 2;
          /** Point on the ring plane at angle a and radius fraction rf. */
          const at = (a: number, rf: number) => {
            const lx = Math.cos(a + spin), ly = Math.sin(a + spin);
            const y1 = ly * cosRX, z1 = ly * sinRX;
            const gx = lx * cosRZ - y1 * sinRZ;
            const gy = lx * sinRZ + y1 * cosRZ;
            return project(gx, gy, z1, size * rf);
          };
          for (let i = 0; i < SEG; i++) {
            const a0 = i * step;
            // Overlap the next edge slightly: abutting antialiased quads leave
            // hairline seams that read as hatch marks along the band.
            const a1 = a0 + step * 1.12;
            const p0i = at(a0, ring.rIn), p0o = at(a0, ring.rOut);
            const p1i = at(a1, ring.rIn), p1o = at(a1, ring.rOut);
            const depth = (p0i.z + p1i.z) / 2;
            if (behind === depth >= 0) continue;
            const lit = 0.24 + ((depth + 1) / 2) * 0.76;
            const dim = behind ? 0.34 : 1;
            // Opaque fill, dimmed via colour: translucent quads would double up
            // where they overlap and show as bright ridges.
            const base = Math.round((150 + lit * 95) * dim * ring.alpha);
            ctx.fillStyle = `rgb(${base},${base + 12},${Math.min(255, base + 38)})`;
            ctx.beginPath();
            ctx.moveTo(p0i.sx, p0i.sy);
            ctx.lineTo(p0o.sx, p0o.sy);
            ctx.lineTo(p1o.sx, p1o.sy);
            ctx.lineTo(p1i.sx, p1i.sy);
            ctx.closePath();
            ctx.fill();
            // Specular line down the middle (brushed chrome) + cyan outer rim.
            const m0 = at(a0, rMid), m1 = at(a1, rMid);
            ctx.lineCap = "butt";
            ctx.beginPath();
            ctx.moveTo(m0.sx, m0.sy);
            ctx.lineTo(m1.sx, m1.sy);
            ctx.strokeStyle = `rgba(255,255,255,${(ring.alpha * lit * dim * (ring.soft ? 0.28 : 0.8)).toFixed(3)})`;
            ctx.lineWidth = Math.max(0.7, size * 0.005);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(p0o.sx, p0o.sy);
            ctx.lineTo(p1o.sx, p1o.sy);
            ctx.strokeStyle = `rgba(120,240,255,${(ring.alpha * lit * dim * (0.30 + live.cyan * 0.45)).toFixed(3)})`;
            ctx.lineWidth = Math.max(0.6, size * 0.0035);
            ctx.stroke();
          }
        }
      };
      ringSegments(true);

      /* 4 — core body: white centre → deep navy rim. Drawn as a plain circle,
             so the silhouette is always true whatever else is moving. */
      const bodyR = coreR * pulse;
      const body = ctx.createRadialGradient(
        cx - bodyR * 0.22, cy - bodyR * 0.32, bodyR * 0.06,
        cx, cy, bodyR,
      );
      body.addColorStop(0, "rgba(255,255,255,0.98)");
      body.addColorStop(0.20, "rgba(219,238,255,0.95)");
      body.addColorStop(0.46, "rgba(150,193,244,0.76)");
      body.addColorStop(0.70, "rgba(62,110,183,0.66)");
      body.addColorStop(0.88, "rgba(20,42,84,0.82)");
      body.addColorStop(1, "rgba(6,12,30,0.94)");
      ctx.fillStyle = body;
      ctx.beginPath();
      ctx.arc(cx, cy, bodyR, 0, Math.PI * 2);
      ctx.fill();
      // Thin silver rim so the sphere has an edge against the dark field.
      ctx.beginPath();
      ctx.arc(cx, cy, bodyR, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(200,215,235,0.30)";
      ctx.lineWidth = Math.max(0.6, size * 0.004);
      ctx.stroke();

      shell(true);

      /* 6 — hot centre + anamorphic flare (additive) */
      ctx.globalCompositeOperation = "lighter";
      const hotR = bodyR * 0.72;
      const hot = ctx.createRadialGradient(cx, cy, 0, cx, cy, hotR);
      hot.addColorStop(0, "rgba(255,255,255,0.95)");
      hot.addColorStop(0.22, "rgba(232,248,255,0.62)");
      hot.addColorStop(0.55, "rgba(140,215,255,0.22)");
      hot.addColorStop(1, "rgba(90,190,255,0)");
      ctx.fillStyle = hot;
      ctx.beginPath();
      ctx.arc(cx, cy, hotR, 0, Math.PI * 2);
      ctx.fill();

      /** Soft streak: a long thin ellipse that fades out at both ends. */
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
      const fl = live.flare * (0.95 + 0.05 * Math.sin(t * 3.1));
      // Clamp inside the stage: a streak cut off at the edge reads as a bar.
      const maxHalf = stage * 0.47;
      streak(Math.min(size * 0.56 * fl, maxHalf), Math.max(0.6, size * 0.0045), 0.85);
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(Math.PI / 2);
      ctx.translate(-cx, -cy);
      streak(Math.min(size * 0.24 * fl, maxHalf), Math.max(0.5, size * 0.004), 0.42);
      ctx.restore();
      ctx.globalCompositeOperation = "source-over";

      ringSegments(false);

      /* 8 — halo ping (state marker, deliberately faint) */
      const pingPhase = (t % live.ping) / live.ping;
      ctx.beginPath();
      ctx.arc(cx, cy, size * (0.55 + pingPhase * 0.14), 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(150,205,255,${(0.16 * (1 - pingPhase)).toFixed(3)})`;
      ctx.lineWidth = 1;
      ctx.stroke();
      if (live.cyan > 0.12) {
        const p2 = ((t + live.ping / 2) % live.ping) / live.ping;
        ctx.beginPath();
        ctx.arc(cx, cy, size * (0.57 + p2 * 0.16), 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(0,243,255,${(live.cyan * 0.35 * (1 - p2)).toFixed(3)})`;
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
