/* 视频 v3 用的三维库打包入口：three@0.186.1（MIT）＋ postprocessing@6.39.5（Zlib），只取用到的部分，
 * 打成一个普通 <script> 能读的文件（双击打开的本地页不能用 ES 模块）。挂到 window.THREE 和 window.POSTPROCESSING。 */
import {
  WebGLRenderer, Scene, PerspectiveCamera, Color, Vector2, Vector3, Vector4, Matrix4, Quaternion, Euler, MathUtils,
  Group, Object3D, Mesh, Points, LineSegments, Line, InstancedMesh, Sprite, Fog, FogExp2,
  BufferGeometry, BufferAttribute, Float32BufferAttribute, InstancedBufferAttribute, PlaneGeometry, BoxGeometry,
  CylinderGeometry, SphereGeometry, RingGeometry, CircleGeometry, TubeGeometry, ShapeGeometry, ExtrudeGeometry,
  TorusGeometry, Shape, Path, CatmullRomCurve3, QuadraticBezierCurve3, CubicBezierCurve3, LineCurve3, CurvePath,
  EdgesGeometry, ShaderMaterial, RawShaderMaterial, MeshBasicMaterial, MeshStandardMaterial, MeshPhysicalMaterial,
  PointsMaterial, LineBasicMaterial, LineDashedMaterial, SpriteMaterial, CanvasTexture, Texture, DataTexture,
  AmbientLight, HemisphereLight, DirectionalLight, PointLight, SpotLight, PMREMGenerator, Raycaster, Box3, Sphere,
  AdditiveBlending, NormalBlending, MultiplyBlending, CustomBlending, DoubleSide, FrontSide, BackSide,
  SRGBColorSpace, LinearSRGBColorSpace, NoToneMapping, ACESFilmicToneMapping, AgXToneMapping, HalfFloatType,
  UnsignedByteType, FloatType, LinearFilter, NearestFilter, LinearMipmapLinearFilter, RepeatWrapping,
  ClampToEdgeWrapping, RGBAFormat, RedFormat, UniformsUtils, UniformsLib, ShaderChunk, Clock, Layers,
  WebGLRenderTarget, DepthTexture, OrthographicCamera, Frustum, Uniform, Matrix3, Plane, Ray, Spherical
} from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import {
  EffectComposer, RenderPass, EffectPass, BloomEffect, DepthOfFieldEffect, VignetteEffect, ToneMappingEffect,
  ToneMappingMode, KernelSize, BlendFunction, Effect, EffectAttribute, SMAAEffect, SMAAPreset,
  ChromaticAberrationEffect, NoiseEffect, HueSaturationEffect, BrightnessContrastEffect, Resolution
} from 'postprocessing';

window.THREE = {
  WebGLRenderer, Scene, PerspectiveCamera, Color, Vector2, Vector3, Vector4, Matrix4, Quaternion, Euler, MathUtils,
  Group, Object3D, Mesh, Points, LineSegments, Line, InstancedMesh, Sprite, Fog, FogExp2,
  BufferGeometry, BufferAttribute, Float32BufferAttribute, InstancedBufferAttribute, PlaneGeometry, BoxGeometry,
  CylinderGeometry, SphereGeometry, RingGeometry, CircleGeometry, TubeGeometry, ShapeGeometry, ExtrudeGeometry,
  TorusGeometry, Shape, Path, CatmullRomCurve3, QuadraticBezierCurve3, CubicBezierCurve3, LineCurve3, CurvePath,
  EdgesGeometry, ShaderMaterial, RawShaderMaterial, MeshBasicMaterial, MeshStandardMaterial, MeshPhysicalMaterial,
  PointsMaterial, LineBasicMaterial, LineDashedMaterial, SpriteMaterial, CanvasTexture, Texture, DataTexture,
  AmbientLight, HemisphereLight, DirectionalLight, PointLight, SpotLight, PMREMGenerator, Raycaster, Box3, Sphere,
  AdditiveBlending, NormalBlending, MultiplyBlending, CustomBlending, DoubleSide, FrontSide, BackSide,
  SRGBColorSpace, LinearSRGBColorSpace, NoToneMapping, ACESFilmicToneMapping, AgXToneMapping, HalfFloatType,
  UnsignedByteType, FloatType, LinearFilter, NearestFilter, LinearMipmapLinearFilter, RepeatWrapping,
  ClampToEdgeWrapping, RGBAFormat, RedFormat, UniformsUtils, UniformsLib, ShaderChunk, Clock, Layers,
  WebGLRenderTarget, DepthTexture, OrthographicCamera, Frustum, Uniform, Matrix3, Plane, Ray, Spherical,
  RoundedBoxGeometry, RoomEnvironment, REVISION: '186.1'
};
window.POSTPROCESSING = {
  EffectComposer, RenderPass, EffectPass, BloomEffect, DepthOfFieldEffect, VignetteEffect, ToneMappingEffect,
  ToneMappingMode, KernelSize, BlendFunction, Effect, EffectAttribute, SMAAEffect, SMAAPreset,
  ChromaticAberrationEffect, NoiseEffect, HueSaturationEffect, BrightnessContrastEffect, Resolution, VERSION: '6.39.5'
};
