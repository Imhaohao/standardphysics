import { FrontSide, Mesh, ShadowMaterial, type WebGLProgramParametersWithUniforms } from "three";
import { SHADOW } from "./palette";

const VIEW_POSITION = "varying vec3 vCatcherViewPosition;";
const STOCK_SHADE = "gl_FragColor = vec4( color, opacity * ( 1.0 - getShadowMask() ) );";
const SHADOW_MASK = "#include <shadowmask_pars_fragment>";

/**
 * How much of the light reaches this fragment, averaged over sixteen looks
 * across the soft edge instead of three's five.
 *
 * Ceiling light throws soft shadows, so the edge is wide, and five looks
 * spread across a wide edge left it grainy. The looks are the same Vogel disk
 * three uses, turned per pixel by the same noise, so the grain that is left is
 * finer than the photograph's own. Without a filtered shadow map it falls back
 * to three's own lookup.
 */
const SOFT_SHADOW_MASK = /* glsl */ `
#if defined( USE_SHADOWMAP ) && NUM_DIR_LIGHT_SHADOWS > 0 && defined( SHADOWMAP_TYPE_PCF )
	#define CATCHER_LOOKS 16
	float catcherShadowMask() {
		DirectionalLightShadow light = directionalLightShadows[ 0 ];
		vec4 coord = vDirectionalShadowCoord[ 0 ];
		coord.xyz /= coord.w;
		coord.z += light.shadowBias;
		bool inFrustum = coord.x >= 0.0 && coord.x <= 1.0 && coord.y >= 0.0 && coord.y <= 1.0 && coord.z <= 1.0;
		if ( ! inFrustum ) return 1.0;
		vec2 radius = light.shadowRadius / light.shadowMapSize;
		float phi = interleavedGradientNoise( gl_FragCoord.xy ) * PI2;
		float lit = 0.0;
		for ( int i = 0; i < CATCHER_LOOKS; i ++ ) {
			lit += texture( directionalShadowMap[ 0 ], vec3( coord.xy + vogelDiskSample( i, CATCHER_LOOKS, phi ) * radius, coord.z ) );
		}
		return mix( 1.0, lit / float( CATCHER_LOOKS ), light.shadowIntensity );
	}
#else
	float catcherShadowMask() { return getShadowMask(); }
#endif`;

/**
 * Shade in proportion to how squarely the surface faces the light.
 *
 * A floor square to the light loses `opacity` of its brightness in shadow. A
 * wall stands nearly edge-on to a light that is almost overhead, so it takes
 * little of that light to begin with, and a shadow drawn across it at the
 * floor's strength read as paint. The share lost follows direct light over
 * direct plus ambient, with the ambient fixed by what a floor loses. The scan
 * carries no normals, so each triangle's own is worked out from its slope on
 * screen.
 */
const SHADE_BY_FACING = /* glsl */ `
	vec3 catcherNormal = normalize( cross( dFdx( vCatcherViewPosition ), dFdy( vCatcherViewPosition ) ) );
	float facing = 0.0;
	#if NUM_DIR_LIGHTS > 0
		facing = saturate( dot( catcherNormal, directionalLights[ 0 ].direction ) );
	#endif
	float direct = facing * opacity / ( 1.0 - opacity );
	gl_FragColor = vec4( color, direct / ( direct + 1.0 ) * ( 1.0 - catcherShadowMask() ) );`;

export function shadeByFacing(shader: Pick<WebGLProgramParametersWithUniforms, "vertexShader" | "fragmentShader">) {
  shader.vertexShader = shader.vertexShader
    .replace("#include <common>", `#include <common>\n${VIEW_POSITION}`)
    .replace("#include <project_vertex>", "#include <project_vertex>\n\tvCatcherViewPosition = - mvPosition.xyz;");
  shader.fragmentShader = shader.fragmentShader
    .replace("#include <common>", `#include <common>\n${VIEW_POSITION}`)
    .replace(SHADOW_MASK, `${SHADOW_MASK}\n${SOFT_SHADOW_MASK}`)
    .replace(STOCK_SHADE, SHADE_BY_FACING);
}

/**
 * The see-through layer that is dark only where a shadow falls. `pull` draws it
 * that many depth steps toward the camera, so it never fights the surface it
 * lies on; it must outpull whatever that surface is already pulled by.
 */
export function shadowCatcherMaterial(pull = 1): ShadowMaterial {
  const material = new ShadowMaterial({
    color: SHADOW.color,
    opacity: SHADOW.darkening,
    depthWrite: false,
    side: FrontSide,
    polygonOffset: true,
    polygonOffsetFactor: -pull,
    polygonOffsetUnits: -pull,
  });
  material.onBeforeCompile = shadeByFacing;
  material.customProgramCacheKey = () => "shadow-catcher-by-facing";
  return material;
}

/**
 * Lays a shadow catcher over a painted surface: the surface's own triangles
 * again, drawn after it, see-through except where a moved piece shades them.
 * It shares the geometry and rides along as a child, and it starts hidden,
 * since it is a second pass over the surface that only pays once something
 * casts.
 */
export function catchShadowsOn(surface: Mesh, material: ShadowMaterial): Mesh {
  const catcher = new Mesh(surface.geometry, material);
  catcher.receiveShadow = true;
  catcher.raycast = () => null;
  catcher.visible = false;
  surface.add(catcher);
  return catcher;
}
