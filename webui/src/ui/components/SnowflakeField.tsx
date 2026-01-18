import React from "react";

type Particle = {
  x: number;
  y: number;
  tx: number;
  ty: number;
  size: number;
  alpha: number;
  hue: "white" | "blue";
  driftPhase: number;
  driftSpeed: number;
  fallSpeed: number;
  followLag: number;
};

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return true;
  return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
}

function isTouchDevice(): boolean {
  if (typeof window === "undefined") return false;
  return "ontouchstart" in window || (navigator.maxTouchPoints || 0) > 0;
}

function clamp(v: number, a: number, b: number): number {
  return Math.max(a, Math.min(b, v));
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function expSmoothing(dtMs: number, timeConstantMs: number): number {
  const dt = Math.max(0, dtMs);
  const tc = Math.max(1, timeConstantMs);
  return 1 - Math.exp(-dt / tc);
}

function drawSnowflake(ctx: CanvasRenderingContext2D, x: number, y: number, r: number) {
  // 6-branch symmetric snowflake: draw one branch, rotate 60° * 6.
  ctx.save();
  ctx.translate(x, y);
  ctx.lineWidth = Math.max(0.6, r * 0.18);
  for (let i = 0; i < 6; i++) {
    ctx.save();
    ctx.rotate((Math.PI / 3) * i);
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(0, -r);
    ctx.moveTo(0, -r * 0.52);
    ctx.lineTo(r * 0.22, -r * 0.66);
    ctx.moveTo(0, -r * 0.52);
    ctx.lineTo(-r * 0.22, -r * 0.66);
    ctx.moveTo(0, -r * 0.78);
    ctx.lineTo(r * 0.18, -r * 0.9);
    ctx.moveTo(0, -r * 0.78);
    ctx.lineTo(-r * 0.18, -r * 0.9);
    ctx.stroke();
    ctx.restore();
  }
  ctx.restore();
}

export function SnowflakeField() {
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  const rafRef = React.useRef<number | null>(null);
  const particlesRef = React.useRef<Particle[]>([]);
  const cursorRef = React.useRef<{ x: number; y: number; vx: number; vy: number }>({ x: 0, y: 0, vx: 0, vy: 0 });
  const followRef = React.useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const lastRef = React.useRef<{ t: number; cx: number; cy: number }>({ t: performance.now(), cx: 0, cy: 0 });

  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    if (prefersReducedMotion()) return;
    if (isTouchDevice()) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = 0;
    let height = 0;
    let dpr = 1;

    const resize = () => {
      // Keep DPR capped to avoid overdraw on high-density screens.
      const rect = canvas.getBoundingClientRect();
      width = Math.max(1, Math.floor(rect.width));
      height = Math.max(1, Math.floor(rect.height));
      dpr = clamp(window.devicePixelRatio || 1, 1, 2);
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const init = () => {
      // Create 50–100 particles, randomly distributed in the viewport.
      const n = clamp(Math.floor(50 + Math.random() * 50), 50, 100);
      const ps: Particle[] = [];
      for (let i = 0; i < n; i++) {
        ps.push({
          x: Math.random() * width,
          y: Math.random() * height,
          tx: Math.random() * width,
          ty: Math.random() * height,
          size: 2 + Math.random() * 6,
          alpha: 0.28 + Math.random() * 0.32,
          hue: Math.random() < 0.6 ? "white" : "blue",
          driftPhase: Math.random() * Math.PI * 2,
          driftSpeed: 0.6 + Math.random() * 1.1,
          fallSpeed: 4 + Math.random() * 16,
          followLag: 0.45 + Math.random() * 1.05
        });
      }
      particlesRef.current = ps;
      const cx = width * 0.5;
      const cy = height * 0.38;
      cursorRef.current = { x: cx, y: cy, vx: 0, vy: 0 };
      followRef.current = { x: cx, y: cy };
      lastRef.current = { t: performance.now(), cx, cy };
    };

    resize();
    init();

    const onMove = (e: MouseEvent) => {
      // Mouse speed feeds into the swarm spacing and follow latency.
      const x = e.clientX;
      const y = e.clientY;
      const now = performance.now();
      const dt = Math.max(8, now - lastRef.current.t);
      const vx = (x - lastRef.current.cx) / dt;
      const vy = (y - lastRef.current.cy) / dt;
      cursorRef.current = { x, y, vx, vy };
      lastRef.current = { t: now, cx: x, cy: y };
    };

    window.addEventListener("mousemove", onMove, { passive: true });

    const loop = () => {
      // Single rAF loop: update follow target, drift/fall, and draw.
      const now = performance.now();
      const dt = now - lastRef.current.t;
      lastRef.current.t = now;

      const cursor = cursorRef.current;
      const follow = followRef.current;
      const speed = Math.hypot(cursor.vx, cursor.vy);
      const tau = lerp(1500, 500, clamp(speed * 22, 0, 1));
      const kFollow = expSmoothing(dt, tau);

      follow.x = lerp(follow.x, cursor.x, kFollow);
      follow.y = lerp(follow.y, cursor.y, kFollow);

      ctx.clearRect(0, 0, width, height);

      // Ambient light around the mouse-follow point.
      const light = ctx.createRadialGradient(follow.x, follow.y, 0, follow.x, follow.y, Math.min(520, Math.max(260, speed * 220)));
      light.addColorStop(0, "rgba(135, 206, 235, 0.16)");
      light.addColorStop(0.55, "rgba(255, 182, 193, 0.08)");
      light.addColorStop(1, "rgba(255, 255, 255, 0)");
      ctx.fillStyle = light;
      ctx.fillRect(0, 0, width, height);

      const radius = 26 + clamp(speed * 380, 0, 220);
      const ps = particlesRef.current;
      for (let i = 0; i < ps.length; i++) {
        const p = ps[i];
        p.driftPhase += (dt / 1000) * p.driftSpeed;
        const driftX = Math.sin(p.driftPhase) * 10;
        const driftY = Math.cos(p.driftPhase * 0.8) * 6;

        const ring = ((i / ps.length) * Math.PI * 2 + p.driftPhase * 0.12) % (Math.PI * 2);
        const ox = Math.cos(ring) * radius * (0.5 + (i % 7) * 0.08);
        const oy = Math.sin(ring) * radius * (0.45 + (i % 5) * 0.1);

        p.tx = follow.x + ox + driftX;
        p.ty = follow.y + oy + driftY;

        // Each particle eases to its target over 0.5–1.5s (per-particle lag).
        const k = expSmoothing(dt, p.followLag * 1000);
        p.x = lerp(p.x, p.tx, k);
        p.y = lerp(p.y, p.ty, k);

        // Slow falling motion + recycling to avoid unbounded memory growth.
        p.y += (p.fallSpeed * dt) / 1000;
        if (p.y > height + 12) {
          p.y = -12;
          p.x = Math.random() * width;
        }

        ctx.save();
        ctx.globalAlpha = p.alpha;
        ctx.strokeStyle = p.hue === "white" ? "rgba(255,255,255,0.9)" : "rgba(135,206,235,0.95)";
        ctx.shadowColor = p.hue === "white" ? "rgba(255,255,255,0.35)" : "rgba(135,206,235,0.35)";
        ctx.shadowBlur = 8;
        drawSnowflake(ctx, p.x, p.y, p.size);
        ctx.restore();
      }

      rafRef.current = window.requestAnimationFrame(loop);
    };

    rafRef.current = window.requestAnimationFrame(loop);

    const ro = new ResizeObserver(() => {
      resize();
      init();
    });
    ro.observe(canvas);

    return () => {
      window.removeEventListener("mousemove", onMove);
      ro.disconnect();
      if (rafRef.current) window.cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      particlesRef.current = [];
    };
  }, []);

  return <canvas ref={canvasRef} className="pointer-events-none fixed inset-0 z-0" />;
}
