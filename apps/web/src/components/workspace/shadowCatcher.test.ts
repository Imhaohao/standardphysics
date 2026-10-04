import { BufferAttribute, BufferGeometry, FrontSide, Mesh, MeshBasicMaterial, Raycaster, ShaderLib, ShadowMaterial, Vector3, type Intersection } from "three";
import { describe, expect, it } from "vitest";
import { SHADOW } from "./palette";
import { catchShadowsOn, shadeByFacing, shadowCatcherMaterial } from "./shadowCatcher";

function floor(): Mesh {
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(new Float32Array([-1, 0, 1, 1, 0, 1, 0, 0, -1]), 3));
  return new Mesh(geometry, new MeshBasicMaterial());
}

describe("the shadow catcher's shader", () => {
  const shader = { vertexShader: ShaderLib.shadow.vertexShader, fragmentShader: ShaderLib.shadow.fragmentShader };
  shadeByFacing(shader);

  it("replaces three's own shading line, so a three upgrade that renames it fails here instead of silently", () => {
    expect(shader.fragmentShader).not.toContain("gl_FragColor = vec4( color, opacity * ( 1.0 - getShadowMask() ) );");
    expect(shader.fragmentShader).toContain("directionalLights[ 0 ].direction");
  });

  it("filters the soft edge with sixteen looks of its own, keeping three's lookup for the boxes", () => {
    expect(shader.fragmentShader).toContain("#include <shadowmask_pars_fragment>");
    expect(shader.fragmentShader).toContain("#define CATCHER_LOOKS 16");
    expect(shader.fragmentShader).toContain("( 1.0 - catcherShadowMask() )");
  });

  it("hands each fragment its position from the camera, to work out the triangle's own normal", () => {
    expect(shader.vertexShader).toContain("vCatcherViewPosition = - mvPosition.xyz;");
    expect(shader.fragmentShader).toContain("varying vec3 vCatcherViewPosition;");
    expect(shader.fragmentShader).toContain("dFdx( vCatcherViewPosition )");
  });
});

describe("the shadow catcher's material", () => {
  const material = shadowCatcherMaterial(5);

  it("is see-through, darkening a fully shaded floor by the palette's share", () => {
    expect(material).toBeInstanceOf(ShadowMaterial);
    expect(material.transparent).toBe(true);
    expect(material.opacity).toBe(SHADOW.darkening);
  });

  it("is pulled toward the camera instead of fighting the surface under it, and writes no depth of its own", () => {
    expect(material.polygonOffset).toBe(true);
    expect(material.polygonOffsetFactor).toBe(-5);
    expect(material.polygonOffsetUnits).toBe(-5);
    expect(material.depthWrite).toBe(false);
    expect(material.side).toBe(FrontSide);
  });

  it("compiles to its own program rather than reusing a plain ShadowMaterial's", () => {
    expect(material.customProgramCacheKey()).not.toBe(new ShadowMaterial().customProgramCacheKey());
  });
});

describe("laying a catcher over a surface", () => {
  const surface = floor();
  const catcher = catchShadowsOn(surface, shadowCatcherMaterial());

  it("draws the surface's own triangles again and rides along with it", () => {
    expect(catcher.parent).toBe(surface);
    expect(catcher.geometry).toBe(surface.geometry);
  });

  it("only catches: it throws no shadow of its own and cannot be picked", () => {
    expect(catcher.receiveShadow).toBe(true);
    expect(catcher.castShadow).toBe(false);
    const hits: Intersection[] = [];
    catcher.raycast(new Raycaster(new Vector3(0, 1, 0), new Vector3(0, -1, 0)), hits);
    expect(hits).toHaveLength(0);
  });

  it("starts hidden until something casts", () => {
    expect(catcher.visible).toBe(false);
  });
});
