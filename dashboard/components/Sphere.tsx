"use client";
// La sfera di particelle (WebGL, three.js): ogni titolo della watchlist è una particella grande,
// colorata dal verdetto del riflesso e pulsante in base alla confidenza. Il pulviscolo intorno
// prende il colore del regime di mercato. Rotazione lenta; ferma se il sistema chiede movimento ridotto.
import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { Verdict } from "@/lib/live";
import { REGIME_COLOR, VERDICT_COLOR } from "@/lib/fmt";

const VERT = `
attribute float size; attribute float phase; attribute float conf; attribute vec3 color;
uniform float time; uniform float dpr; varying vec3 vColor; varying float vFade;
void main() {
  vColor = color;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  float pulse = 1.0 + conf * 0.45 * sin(time * (1.5 + conf * 2.5) + phase);
  gl_PointSize = size * pulse * dpr * (3.3 / -mv.z);   // size in pixel CSS alla distanza della camera
  vFade = smoothstep(-4.2, -2.2, mv.z);   // le particelle sul retro della sfera sono più tenui
  gl_Position = projectionMatrix * mv;
}`;
const FRAG = `
varying vec3 vColor; varying float vFade;
void main() {
  vec2 c = gl_PointCoord - 0.5; float d = length(c);
  if (d > 0.5) discard;
  float a = smoothstep(0.5, 0.0, d);
  gl_FragColor = vec4(vColor, a * (0.25 + 0.75 * vFade));
}`;

function fib(i: number, n: number, r: number) {
  const y = 1 - (i / (n - 1)) * 2, rad = Math.sqrt(1 - y * y), th = Math.PI * (3 - Math.sqrt(5)) * i;
  return new THREE.Vector3(Math.cos(th) * rad * r, y * r, Math.sin(th) * rad * r);
}

export function Sphere({ verdicts, regime, pulse }: { verdicts: Verdict[]; regime?: string; pulse: boolean }) {
  const host = useRef<HTMLDivElement>(null);
  const labels = useRef<HTMLDivElement>(null);
  const api = useRef<{ update: (v: Verdict[], regime?: string) => void; flash: () => void } | null>(null);

  useEffect(() => {
    const el = host.current!;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    camera.position.set(0, 0, 3.3);
    const group = new THREE.Group();
    scene.add(group);
    const uniforms = { time: { value: 0 }, dpr: { value: renderer.getPixelRatio() } };
    const mat = new THREE.ShaderMaterial({
      vertexShader: VERT, fragmentShader: FRAG, uniforms, transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending,
    });

    // pulviscolo: 1600 particelle sulla superficie e dentro il volume
    const N = 1600;
    const dust = new THREE.BufferGeometry();
    const dp = new Float32Array(N * 3), dc = new Float32Array(N * 3), ds = new Float32Array(N), dph = new Float32Array(N), dcf = new Float32Array(N);
    for (let i = 0; i < N; i++) {
      const v = fib(i, N, 0.55 + Math.random() * 0.45);
      dp.set([v.x, v.y, v.z], i * 3);
      ds[i] = 2.2 + Math.random() * 3.5;
      dph[i] = Math.random() * 6.28;
      dcf[i] = Math.random() * 0.3;
    }
    dust.setAttribute("position", new THREE.BufferAttribute(dp, 3));
    dust.setAttribute("color", new THREE.BufferAttribute(dc, 3));
    dust.setAttribute("size", new THREE.BufferAttribute(ds, 1));
    dust.setAttribute("phase", new THREE.BufferAttribute(dph, 1));
    dust.setAttribute("conf", new THREE.BufferAttribute(dcf, 1));
    group.add(new THREE.Points(dust, mat));

    // titoli: particelle grandi + raggi verso il centro
    const syms = new THREE.BufferGeometry();
    const symPoints = new THREE.Points(syms, mat);
    group.add(symPoints);
    const rays = new THREE.LineSegments(new THREE.BufferGeometry(),
      new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.35, blending: THREE.AdditiveBlending }));
    group.add(rays);
    const core = new THREE.Mesh(new THREE.SphereGeometry(0.09, 24, 24),
      new THREE.MeshBasicMaterial({ color: "#3DD6FF", transparent: true, opacity: 0.9 }));
    group.add(core);
    let symPos: THREE.Vector3[] = [];
    let symNames: string[] = [];
    let flashUntil = 0;

    const update = (vs: Verdict[], reg?: string) => {
      const rc = new THREE.Color(REGIME_COLOR[reg ?? ""] ?? "#3DD6FF");
      for (let i = 0; i < N; i++) {
        const k = 0.35 + Math.random() * 0.45;
        dc.set([rc.r * k, rc.g * k, rc.b * k], i * 3);
      }
      dust.attributes.color.needsUpdate = true;
      const n = vs.length;
      const p = new Float32Array(n * 3), c = new Float32Array(n * 3), s = new Float32Array(n), ph = new Float32Array(n), cf = new Float32Array(n);
      const rp = new Float32Array(n * 6), rcol = new Float32Array(n * 6);
      symPos = [];
      vs.forEach((v, i) => {
        const pos = fib(i, Math.max(n, 2), 1.02);
        symPos.push(pos);
        const col = new THREE.Color(VERDICT_COLOR[v.verdict] ?? "#6B7A90");
        p.set([pos.x, pos.y, pos.z], i * 3);
        c.set([col.r, col.g, col.b], i * 3);
        s[i] = 7 + (v.confidence / 100) * 12;
        ph[i] = i * 1.7;
        cf[i] = v.confidence / 100;
        rp.set([0, 0, 0, pos.x, pos.y, pos.z], i * 6);
        rcol.set([0.1, 0.5, 0.7, col.r, col.g, col.b], i * 6);
      });
      symNames = vs.map((v) => v.symbol);
      syms.setAttribute("position", new THREE.BufferAttribute(p, 3));
      syms.setAttribute("color", new THREE.BufferAttribute(c, 3));
      syms.setAttribute("size", new THREE.BufferAttribute(s, 1));
      syms.setAttribute("phase", new THREE.BufferAttribute(ph, 1));
      syms.setAttribute("conf", new THREE.BufferAttribute(cf, 1));
      rays.geometry.setAttribute("position", new THREE.BufferAttribute(rp, 3));
      rays.geometry.setAttribute("color", new THREE.BufferAttribute(rcol, 3));
      if (labels.current) {
        labels.current.innerHTML = vs.map((v) =>
          `<span style="color:${VERDICT_COLOR[v.verdict] ?? "#6B7A90"}">${v.symbol}</span>`).join("");
      }
    };
    api.current = { update, flash: () => { flashUntil = performance.now() + 1200; } };

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight;
      renderer.setSize(w, h, false);
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";
      camera.aspect = w / Math.max(h, 1);
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();

    let raf = 0;
    const v3 = new THREE.Vector3();
    const frame = (now: number) => {
      uniforms.time.value = now / 1000;
      if (!still) {
        group.rotation.y += 0.0016;
        group.rotation.x = Math.sin(now / 9000) * 0.18;
      }
      const f = Math.max(0, (flashUntil - now) / 1200);
      core.scale.setScalar(1 + f * 2.5 + 0.08 * Math.sin(now / 500));
      (core.material as THREE.MeshBasicMaterial).color.set(f > 0 ? "#3DFF8F" : "#3DD6FF");
      renderer.render(scene, camera);
      // etichette HTML dei titoli, proiettate sullo schermo
      const spans = labels.current?.children;
      if (spans) {
        for (let i = 0; i < symPos.length && i < spans.length; i++) {
          v3.copy(symPos[i]).applyMatrix4(group.matrixWorld);
          const front = v3.z > -0.2;
          v3.project(camera);
          const sp = spans[i] as HTMLElement;
          sp.style.transform = `translate(${(v3.x * 0.5 + 0.5) * el.clientWidth + 8}px, ${(-v3.y * 0.5 + 0.5) * el.clientHeight - 6}px)`;
          sp.style.opacity = front ? "1" : "0.18";
        }
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.dispose();
      mat.dispose();
      dust.dispose();
      syms.dispose();
      el.removeChild(renderer.domElement);
      void symNames;
    };
  }, []);

  useEffect(() => { api.current?.update(verdicts, regime); }, [verdicts, regime]);
  useEffect(() => { if (pulse) api.current?.flash(); }, [pulse]);

  return (
    <div className="relative h-full w-full">
      <div ref={host} className="absolute inset-0" aria-hidden />
      <div ref={labels} className="pointer-events-none absolute inset-0 text-[10px] font-bold tracking-[0.08em] [&>span]:absolute [&>span]:left-0 [&>span]:top-0 [&>span]:[text-shadow:0_0_6px_currentColor]" aria-hidden />
    </div>
  );
}
