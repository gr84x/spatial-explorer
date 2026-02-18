// webgl_points.js — WebGL2 instanced point renderer (ES module)

// Renders circles via instanced quads (two triangles per instance) with a disc fragment shader.
// Intended for 10K–100K points with minimal CPU work per frame.

function _compileShader(gl, type, src){
  const sh = gl.createShader(type);
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if(!gl.getShaderParameter(sh, gl.COMPILE_STATUS)){
    const msg = gl.getShaderInfoLog(sh) || 'Shader compile failed';
    gl.deleteShader(sh);
    throw new Error(msg + '\n' + src);
  }
  return sh;
}

function _linkProgram(gl, vsSrc, fsSrc){
  const vs = _compileShader(gl, gl.VERTEX_SHADER, vsSrc);
  const fs = _compileShader(gl, gl.FRAGMENT_SHADER, fsSrc);
  const p = gl.createProgram();
  gl.attachShader(p, vs);
  gl.attachShader(p, fs);
  gl.linkProgram(p);
  gl.deleteShader(vs);
  gl.deleteShader(fs);
  if(!gl.getProgramParameter(p, gl.LINK_STATUS)){
    const msg = gl.getProgramInfoLog(p) || 'Program link failed';
    gl.deleteProgram(p);
    throw new Error(msg);
  }
  return p;
}

const VS = `#version 300 es
precision highp float;

layout(location=0) in vec2 aQuad;          // [-1,+1] quad corners (two triangles)
layout(location=1) in vec2 aWorld;         // per-instance world xy
layout(location=2) in vec4 aColor;         // per-instance RGBA (0..1)
layout(location=3) in float aRadiusPx;     // per-instance radius in pixels
layout(location=4) in float aVisible;      // 0 or 1
layout(location=5) in float aGate;         // 0 or 1 (gate ring)

uniform vec2 uCanvasPx;    // (width,height) in CSS px
uniform float uScale;
uniform vec2 uTranslate;

out vec2 vUV;
out vec4 vColor;
out float vGate;

void main(){
  vUV = aQuad;
  vColor = aColor;
  vGate = aGate;

  if(aVisible < 0.5){
    gl_Position = vec4(2.0, 2.0, 0.0, 1.0);
    return;
  }

  vec2 centerPx = aWorld * uScale + uTranslate;
  vec2 posPx = centerPx + aQuad * aRadiusPx;

  vec2 ndc = (posPx / uCanvasPx) * 2.0 - 1.0;
  ndc.y = -ndc.y;
  gl_Position = vec4(ndc, 0.0, 1.0);
}`;

const FS_FILL = `#version 300 es
precision highp float;

in vec2 vUV;
in vec4 vColor;
out vec4 outColor;

void main(){
  float r2 = dot(vUV, vUV);
  if(r2 > 1.0) discard;
  outColor = vColor;
}`;

const FS_RING = `#version 300 es
precision highp float;

in vec2 vUV;
in vec4 vColor;
out vec4 outColor;

uniform float uRingInner; // 0..1
uniform float uRingOuter; // 0..1

void main(){
  float r = sqrt(dot(vUV, vUV));
  if(r > uRingOuter || r < uRingInner) discard;
  outColor = vColor;
}`;

const FS_GATE_RING = `#version 300 es
precision highp float;

in vec2 vUV;
in float vGate;
out vec4 outColor;

uniform float uRingInner;
uniform float uRingOuter;
uniform vec4 uGateColor;

void main(){
  if(vGate < 0.5) discard;
  float r = sqrt(dot(vUV, vUV));
  if(r > uRingOuter || r < uRingInner) discard;
  outColor = uGateColor;
}`;

export function createWebGLPointsRenderer({canvas}){
  const gl = canvas.getContext('webgl2', {
    alpha: true,
    antialias: true,
    premultipliedAlpha: true,
    preserveDrawingBuffer: false,
  });
  if(!gl) return null;

  const progFill = _linkProgram(gl, VS, FS_FILL);
  const progRing = _linkProgram(gl, VS, FS_RING);
  const progGate = _linkProgram(gl, VS, FS_GATE_RING);

  const uFill = {
    canvasPx: gl.getUniformLocation(progFill, 'uCanvasPx'),
    scale: gl.getUniformLocation(progFill, 'uScale'),
    translate: gl.getUniformLocation(progFill, 'uTranslate'),
  };
  const uRing = {
    canvasPx: gl.getUniformLocation(progRing, 'uCanvasPx'),
    scale: gl.getUniformLocation(progRing, 'uScale'),
    translate: gl.getUniformLocation(progRing, 'uTranslate'),
    inner: gl.getUniformLocation(progRing, 'uRingInner'),
    outer: gl.getUniformLocation(progRing, 'uRingOuter'),
  };
  const uGate = {
    canvasPx: gl.getUniformLocation(progGate, 'uCanvasPx'),
    scale: gl.getUniformLocation(progGate, 'uScale'),
    translate: gl.getUniformLocation(progGate, 'uTranslate'),
    inner: gl.getUniformLocation(progGate, 'uRingInner'),
    outer: gl.getUniformLocation(progGate, 'uRingOuter'),
    color: gl.getUniformLocation(progGate, 'uGateColor'),
  };

  // Geometry: 2 triangles covering [-1,1]^2
  const quad = new Float32Array([
    -1,-1,  +1,-1,  +1,+1,
    -1,-1,  +1,+1,  -1,+1,
  ]);

  const quadBuf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
  gl.bufferData(gl.ARRAY_BUFFER, quad, gl.STATIC_DRAW);

  const worldBuf = gl.createBuffer();
  const colorFillBuf = gl.createBuffer();
  const colorRingBuf = gl.createBuffer();
  const radiusBuf = gl.createBuffer();
  const visibleBuf = gl.createBuffer();
  const gateBuf = gl.createBuffer();

  function _bindInstanceAttrib(buf, loc, size, type, normalized){
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, size, type, normalized, 0, 0);
    gl.vertexAttribDivisor(loc, 1);
  }

  function _bindCommonAttribs({colorBuf}){
    // aQuad (per-vertex)
    gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.vertexAttribDivisor(0, 0);

    // per-instance attribs
    _bindInstanceAttrib(worldBuf, 1, 2, gl.FLOAT, false);
    _bindInstanceAttrib(colorBuf, 2, 4, gl.UNSIGNED_BYTE, true);
    _bindInstanceAttrib(radiusBuf, 3, 1, gl.FLOAT, false);
    _bindInstanceAttrib(visibleBuf, 4, 1, gl.UNSIGNED_BYTE, true);
    _bindInstanceAttrib(gateBuf, 5, 1, gl.UNSIGNED_BYTE, true);
  }

  const vaoFill = gl.createVertexArray();
  gl.bindVertexArray(vaoFill);
  _bindCommonAttribs({colorBuf: colorFillBuf});

  const vaoRing = gl.createVertexArray();
  gl.bindVertexArray(vaoRing);
  _bindCommonAttribs({colorBuf: colorRingBuf});

  gl.bindVertexArray(null);

  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

  let _n = 0;

  function uploadStatic({worldXY}){
    _n = Math.floor(worldXY.length / 2);
    gl.bindBuffer(gl.ARRAY_BUFFER, worldBuf);
    gl.bufferData(gl.ARRAY_BUFFER, worldXY, gl.STATIC_DRAW);
  }

  function uploadDynamic({fillColorsRgba, ringColorsRgba=null, radiiPx, visibleMask, gateMask}){
    gl.bindBuffer(gl.ARRAY_BUFFER, colorFillBuf);
    gl.bufferData(gl.ARRAY_BUFFER, fillColorsRgba, gl.DYNAMIC_DRAW);

    if(ringColorsRgba){
      gl.bindBuffer(gl.ARRAY_BUFFER, colorRingBuf);
      gl.bufferData(gl.ARRAY_BUFFER, ringColorsRgba, gl.DYNAMIC_DRAW);
    }

    gl.bindBuffer(gl.ARRAY_BUFFER, radiusBuf);
    gl.bufferData(gl.ARRAY_BUFFER, radiiPx, gl.DYNAMIC_DRAW);

    gl.bindBuffer(gl.ARRAY_BUFFER, visibleBuf);
    gl.bufferData(gl.ARRAY_BUFFER, visibleMask, gl.DYNAMIC_DRAW);

    gl.bindBuffer(gl.ARRAY_BUFFER, gateBuf);
    gl.bufferData(gl.ARRAY_BUFFER, gateMask, gl.DYNAMIC_DRAW);
  }

  function resizeViewport(){
    gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight);
  }

  function _setCommonUniforms(prog, u, {canvasCssWidth, canvasCssHeight, scale, tx, ty}){
    gl.useProgram(prog);
    gl.uniform2f(u.canvasPx, canvasCssWidth, canvasCssHeight);
    gl.uniform1f(u.scale, scale);
    gl.uniform2f(u.translate, tx, ty);
  }

  function render({canvasCssWidth, canvasCssHeight, scale, tx, ty, drawTypeOutlines, drawGateRings}){
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.clearColor(0,0,0,0);
    gl.clear(gl.COLOR_BUFFER_BIT);

    // Fill pass
    gl.bindVertexArray(vaoFill);
    _setCommonUniforms(progFill, uFill, {canvasCssWidth, canvasCssHeight, scale, tx, ty});
    gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, _n);

    if(drawTypeOutlines){
      gl.bindVertexArray(vaoRing);
      _setCommonUniforms(progRing, uRing, {canvasCssWidth, canvasCssHeight, scale, tx, ty});
      gl.uniform1f(uRing.inner, 0.78);
      gl.uniform1f(uRing.outer, 0.98);
      gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, _n);
    }

    if(drawGateRings){
      gl.bindVertexArray(vaoFill);
      _setCommonUniforms(progGate, uGate, {canvasCssWidth, canvasCssHeight, scale, tx, ty});
      gl.uniform1f(uGate.inner, 0.70);
      gl.uniform1f(uGate.outer, 0.98);
      gl.uniform4f(uGate.color, 0.98, 0.80, 0.08, 0.92); // amber
      gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, _n);
    }

    gl.bindVertexArray(null);
  }

  function destroy(){
    try{
      gl.deleteProgram(progFill);
      gl.deleteProgram(progRing);
      gl.deleteProgram(progGate);
      gl.deleteBuffer(quadBuf);
      gl.deleteBuffer(worldBuf);
      gl.deleteBuffer(colorFillBuf);
      gl.deleteBuffer(colorRingBuf);
      gl.deleteBuffer(radiusBuf);
      gl.deleteBuffer(visibleBuf);
      gl.deleteBuffer(gateBuf);
      gl.deleteVertexArray(vaoFill);
      gl.deleteVertexArray(vaoRing);
    } catch {}
  }

  return {
    gl,
    uploadStatic,
    uploadDynamic,
    resizeViewport,
    render,
    destroy,
  };
}
