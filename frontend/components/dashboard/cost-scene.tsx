"use client";

import { Component, useMemo, useRef, useState, type ReactNode } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Bounds, Html, RoundedBox } from "@react-three/drei";
import { MathUtils, type Group, type Mesh, type MeshStandardMaterial } from "three";
import { cn, moneyCompact } from "@/lib/utils";

export type SceneItem = { name: string; value: number; color: string; share: number };

type Props = { items: SceneItem[]; dark: boolean; active: boolean; reduced: boolean };

const SPACING = 0.95;
const BAR = 0.58;
const MAX_HEIGHT = 2.6;
const MIN_HEIGHT = 0.18;
const SLAB_DEPTH = 1.5;
const SLAB_HEIGHT = 0.14;

function Bar({
  item,
  index,
  x,
  height,
  hovered,
  dimmed,
  onHover,
  reduced,
}: {
  item: SceneItem;
  index: number;
  x: number;
  height: number;
  hovered: boolean;
  dimmed: boolean;
  onHover: (name: string | null) => void;
  reduced: boolean;
}) {
  const mesh = useRef<Mesh>(null);
  const start = useRef<number | null>(null);

  useFrame((state, dt) => {
    const m = mesh.current;
    if (!m) return;
    if (start.current === null) start.current = state.clock.elapsedTime;
    const elapsed = state.clock.elapsedTime - start.current;
    // Staggered rise from the slab, then hold.
    const target = reduced || elapsed > 0.15 + index * 0.07 ? 1 : 0.001;
    m.scale.y = reduced ? 1 : MathUtils.damp(m.scale.y, target, 6, dt);
    m.position.y = (height * m.scale.y) / 2;
    const mat = m.material as MeshStandardMaterial;
    mat.opacity = MathUtils.damp(mat.opacity, dimmed ? 0.28 : 1, 10, dt);
    mat.emissiveIntensity = MathUtils.damp(mat.emissiveIntensity, hovered ? 0.22 : 0, 10, dt);
  });

  return (
    <group position={[x, 0, 0]}>
      <RoundedBox
        ref={mesh}
        args={[BAR, height, BAR]}
        radius={0.05}
        smoothness={3}
        scale={[1, reduced ? 1 : 0.001, 1]}
        position={[0, reduced ? height / 2 : 0, 0]}
        onPointerOver={(e) => {
          e.stopPropagation();
          onHover(item.name);
        }}
        onPointerOut={() => onHover(null)}
      >
        <meshStandardMaterial color={item.color} emissive={item.color} emissiveIntensity={0} roughness={0.55} metalness={0} transparent />
      </RoundedBox>

      {/* Value above the bar */}
      <Html position={[0, height + 0.2, 0]} center zIndexRange={[10, 0]} style={{ pointerEvents: "none" }}>
        <span
          className={cn(
            "tnum whitespace-nowrap text-[11px] font-semibold transition-opacity duration-200",
            "text-foreground",
            dimmed && "opacity-30",
          )}
        >
          {moneyCompact(item.value)}
        </span>
      </Html>

      {/* Service name on the front edge of the slab */}
      <Html position={[0, -SLAB_HEIGHT, SLAB_DEPTH / 2 + 0.05]} center zIndexRange={[10, 0]} style={{ pointerEvents: "none" }}>
        <span
          className={cn(
            "mt-3 block whitespace-nowrap text-[10.5px] font-medium transition-opacity duration-200",
            "text-muted-foreground",
            dimmed && "opacity-30",
          )}
        >
          {item.name}
        </span>
      </Html>
    </group>
  );
}

function Scene({ items, dark, reduced }: Omit<Props, "active">) {
  const [hovered, setHovered] = useState<string | null>(null);
  const max = useMemo(() => Math.max(...items.map((i) => i.value), 1), [items]);
  const width = items.length * SPACING;
  const sway = useRef<Group>(null);

  // A barely-there sway so the scene reads as 3D without spinning.
  useFrame((state) => {
    if (!sway.current || reduced) return;
    sway.current.rotation.y = Math.sin(state.clock.elapsedTime * 0.35) * 0.06;
  });

  return (
    <>
      <ambientLight intensity={dark ? 0.6 : 0.95} />
      <directionalLight position={[4, 8, 6]} intensity={dark ? 1.5 : 1.25} />
      <directionalLight position={[-6, 3, -2]} intensity={dark ? 0.35 : 0.25} />

      <group ref={sway}>
        <Bounds fit clip observe margin={1.08} maxDuration={0}>
          {/* Invisible box spanning the final extents so fitting accounts for fully grown bars */}
          <mesh visible={false} position={[0, (MAX_HEIGHT + 0.4) / 2 - SLAB_HEIGHT, 0.1]}>
            <boxGeometry args={[width + 0.3, MAX_HEIGHT + 0.4 + SLAB_HEIGHT, SLAB_DEPTH + 0.2]} />
          </mesh>

          <RoundedBox args={[width + 0.3, SLAB_HEIGHT, SLAB_DEPTH]} radius={0.05} smoothness={3} position={[0, -SLAB_HEIGHT / 2, 0]}>
            <meshStandardMaterial color={dark ? "#1b2130" : "#ffffff"} roughness={0.85} />
          </RoundedBox>

          {items.map((item, i) => (
            <Bar
              key={item.name}
              item={item}
              index={i}
              x={(i - (items.length - 1) / 2) * SPACING}
              height={MIN_HEIGHT + (item.value / max) * (MAX_HEIGHT - MIN_HEIGHT)}
              hovered={hovered === item.name}
              dimmed={hovered !== null && hovered !== item.name}
              onHover={setHovered}
              reduced={reduced}
            />
          ))}
        </Bounds>
      </group>
    </>
  );
}

/** If WebGL is unavailable, fail quietly; the same data is shown in the breakdown list. */
class SceneBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed) {
      return (
        <div className="flex h-full items-center justify-center text-[12px] text-muted-foreground">
          3D preview unavailable on this device.
        </div>
      );
    }
    return this.props.children;
  }
}

export default function CostScene({ items, dark, active, reduced }: Props) {
  return (
    <SceneBoundary>
      <Canvas
        orthographic
        // Render only while the panel is on screen.
        frameloop={active ? "always" : "never"}
        dpr={[1, 1.5]}
        camera={{ position: [5, 4.2, 8], zoom: 60, near: 0.1, far: 100 }}
        gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
      >
        <Scene items={items} dark={dark} reduced={reduced} />
      </Canvas>
    </SceneBoundary>
  );
}
