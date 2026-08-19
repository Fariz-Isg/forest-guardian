import * as THREE from 'three';

const FLAME_ORANGE = 0xE8622C;
const EMBER_RUST = 0xA8481F;

function waitForEl(id, cb) {
  const el = document.getElementById(id);
  if (el && el.clientHeight > 0) cb(el);
  else requestAnimationFrame(() => waitForEl(id, cb));
}
waitForEl('canopy-earth-stage', (el) => {
  if (el.dataset.mounted) return;
  el.dataset.mounted = '1';
  initEarthHero(el);
});

function initEarthHero(container) {
  const cfg = {
    idleSpeed: parseFloat(container.dataset.idleSpeed) || 0.06,
    scrollStrength: parseFloat(container.dataset.scrollStrength) || 2.2,
    satelliteSpeed: parseFloat(container.dataset.satelliteSpeed) || 0.35,
    ringTilt: parseFloat(container.dataset.ringTilt) || 23,
    offsetX: parseFloat(container.dataset.offsetX) || 0
  };

  const size = () => ({
    w: container.clientWidth || window.innerWidth,
    h: container.clientHeight || window.innerHeight
  });
  let { w, h } = size();

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 100);
  camera.position.set(0, 0.15, 4.2);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(w, h);
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.65;
  renderer.domElement.style.display = 'block';
  renderer.domElement.style.width = '100%';
  renderer.domElement.style.height = '100%';
  renderer.domElement.style.pointerEvents = 'none';
  container.appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0x8899aa, 2.1));
  const sun = new THREE.DirectionalLight(0xfff0dd, 1.7);
  sun.position.set(5, 2.4, 3.5);
  scene.add(sun);
  const fill = new THREE.DirectionalLight(0x5a6a86, 1.1);
  fill.position.set(-4, -1.5, -3);
  scene.add(fill);
  // stays fixed relative to the camera (not a child of masterGroup) so
  // whichever hemisphere is facing the viewer is always lit, even as the
  // earth spins under scroll/idle rotation
  const camLight = new THREE.DirectionalLight(0xfff4e6, 1.3);
  camLight.position.set(0, 0.3, 1);
  scene.add(camLight);

  const masterGroup = new THREE.Group();
  masterGroup.position.x = cfg.offsetX;
  scene.add(masterGroup);

  const earthGroup = new THREE.Group();
  masterGroup.add(earthGroup);

  const earthGeo = new THREE.SphereGeometry(1, 64, 64);
  const earthMat = new THREE.MeshStandardMaterial({ color: 0x223344, roughness: 0.85, metalness: 0.05 });
  const earthMesh = new THREE.Mesh(earthGeo, earthMat);
  earthMesh.name = 'earth';
  earthGroup.add(earthMesh);

  // threejs.org serves this with CORS headers; unpkg's copy of the same
  // asset 404s on the CORS preflight, so it isn't worth trying first.
  const loader = new THREE.TextureLoader();
  const TEXTURE_URL = 'https://threejs.org/examples/textures/planets/earth_atmos_2048.jpg';
  loader.setCrossOrigin('anonymous');
  loader.load(TEXTURE_URL, applyTex, undefined, (e) => console.error('Earth texture load failed', e));
  function applyTex(tex) {
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 4;
    earthMat.map = tex;
    earthMat.color.set(0xffffff);
    earthMat.needsUpdate = true;
  }

  const atmoGeo = new THREE.SphereGeometry(1.045, 64, 64);
  const atmoMat = new THREE.ShaderMaterial({
    uniforms: { glowColor: { value: new THREE.Color(0x6fb3ff) } },
    vertexShader: `
      varying vec3 vNormal;
      void main() {
        vNormal = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      varying vec3 vNormal;
      uniform vec3 glowColor;
      void main() {
        float intensity = pow(0.68 - dot(vNormal, vec3(0.0, 0.0, 1.0)), 3.2);
        gl_FragColor = vec4(glowColor, clamp(intensity, 0.0, 1.0));
      }
    `,
    side: THREE.BackSide,
    blending: THREE.AdditiveBlending,
    transparent: true,
    depthWrite: false
  });
  const atmoMesh = new THREE.Mesh(atmoGeo, atmoMat);
  earthGroup.add(atmoMesh);

  const orbitGroup = new THREE.Group();
  orbitGroup.rotation.x = THREE.MathUtils.degToRad(cfg.ringTilt);
  orbitGroup.rotation.z = THREE.MathUtils.degToRad(6);
  masterGroup.add(orbitGroup);

  const ringRadius = 1.7;
  const ringGeo = new THREE.TorusGeometry(ringRadius, 0.007, 8, 160);
  const ringMat = new THREE.MeshStandardMaterial({ color: FLAME_ORANGE, emissive: FLAME_ORANGE, emissiveIntensity: 0.35, roughness: 0.4, metalness: 0.3 });
  const ringMesh = new THREE.Mesh(ringGeo, ringMat);
  ringMesh.rotation.x = Math.PI / 2;
  orbitGroup.add(ringMesh);

  const satelliteGroup = new THREE.Group();
  orbitGroup.add(satelliteGroup);

  const SAT_SCALE = 2.6;
  const busHalf = 0.025 * SAT_SCALE;
  const busMat = new THREE.MeshStandardMaterial({ color: 0xc9cdd1, roughness: 0.4, metalness: 0.7 });
  const busTrimMat = new THREE.MeshStandardMaterial({ color: 0x7d828a, roughness: 0.5, metalness: 0.8 });
  const bus = new THREE.Mesh(new THREE.BoxGeometry(busHalf * 2, 0.045 * SAT_SCALE, 0.075 * SAT_SCALE), busMat);
  bus.name = 'satellite-bus';
  satelliteGroup.add(bus);
  const baseTrim = new THREE.Mesh(new THREE.CylinderGeometry(busHalf * 0.55, busHalf * 0.55, 0.02 * SAT_SCALE, 10), busTrimMat);
  baseTrim.rotation.x = Math.PI / 2;
  baseTrim.position.z = -0.075 * SAT_SCALE * 0.5 - 0.01 * SAT_SCALE;
  satelliteGroup.add(baseTrim);

  const panelHalf = 0.0475 * SAT_SCALE;
  const panelDepth = 0.038 * SAT_SCALE;
  const panelMat = new THREE.MeshStandardMaterial({ color: EMBER_RUST, roughness: 0.55, metalness: 0.25 });
  const cellLineMat = new THREE.MeshStandardMaterial({ color: 0x3a1c0c, roughness: 0.7, metalness: 0.1 });
  const strutMat = new THREE.MeshStandardMaterial({ color: 0x8a8f96, roughness: 0.4, metalness: 0.8 });

  function buildPanel(sign) {
    const group = new THREE.Group();
    const panelGeo = new THREE.BoxGeometry(panelHalf * 2, 0.006 * SAT_SCALE, panelDepth);
    const panel = new THREE.Mesh(panelGeo, panelMat);
    group.add(panel);
    const divisions = 5;
    for (let i = 1; i < divisions; i++) {
      const lineX = -panelHalf + (panelHalf * 2 * i) / divisions;
      const line = new THREE.Mesh(new THREE.BoxGeometry(0.003 * SAT_SCALE, 0.007 * SAT_SCALE, panelDepth * 0.98), cellLineMat);
      line.position.x = lineX;
      group.add(line);
    }
    const midLine = new THREE.Mesh(new THREE.BoxGeometry(panelHalf * 2 * 0.98, 0.007 * SAT_SCALE, 0.003 * SAT_SCALE), cellLineMat);
    group.add(midLine);
    const strut = new THREE.Mesh(new THREE.CylinderGeometry(0.006 * SAT_SCALE, 0.006 * SAT_SCALE, panelHalf * 0.5, 8), strutMat);
    strut.rotation.z = Math.PI / 2;
    strut.position.x = sign * (busHalf + panelHalf * 0.25 - panelHalf);
    group.add(strut);
    group.position.x = sign * (busHalf + panelHalf);
    return group;
  }
  const panelL = buildPanel(-1);
  panelL.name = 'solar-panel-left';
  satelliteGroup.add(panelL);
  const panelR = buildPanel(1);
  panelR.name = 'solar-panel-right';
  satelliteGroup.add(panelR);

  const antennaMat = new THREE.MeshStandardMaterial({ color: 0xe8e8e8, roughness: 0.35, metalness: 0.65 });
  const antenna = new THREE.Mesh(new THREE.CylinderGeometry(0.003 * SAT_SCALE, 0.003 * SAT_SCALE, 0.03 * SAT_SCALE, 6), antennaMat);
  antenna.position.y = 0.045 * SAT_SCALE * 0.5 + 0.015 * SAT_SCALE;
  satelliteGroup.add(antenna);
  const dish = new THREE.Mesh(new THREE.SphereGeometry(0.018 * SAT_SCALE, 12, 8, 0, Math.PI * 2, 0, Math.PI / 2), antennaMat);
  dish.rotation.x = Math.PI;
  dish.position.y = antenna.position.y + 0.015 * SAT_SCALE;
  satelliteGroup.add(dish);

  let idleRot = 0, scrollTarget = 0, scrollCurrent = 0, orbitAngle = Math.PI * 0.3;

  // progress spans the whole document, so the Earth keeps rotating as the
  // reader moves through every section, not just the hero
  function onScroll() {
    const doc = document.documentElement;
    const travel = Math.max(doc.scrollHeight - window.innerHeight, 1);
    const progress = Math.min(Math.max(window.scrollY / travel, 0), 1);
    scrollTarget = progress * Math.PI * cfg.scrollStrength;
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  function onResize() {
    const s = size();
    w = s.w; h = s.h;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
    onScroll();
  }
  window.addEventListener('resize', onResize);
  if (window.ResizeObserver) new ResizeObserver(onResize).observe(container);

  const clock = new THREE.Clock();
  function animate() {
    requestAnimationFrame(animate);
    const delta = Math.min(clock.getDelta(), 0.05);
    idleRot += delta * cfg.idleSpeed;
    scrollCurrent += (scrollTarget - scrollCurrent) * Math.min(delta * 3.2, 1);
    masterGroup.rotation.y = idleRot + scrollCurrent;

    orbitAngle += delta * cfg.satelliteSpeed;
    satelliteGroup.position.set(ringRadius * Math.cos(orbitAngle), 0, ringRadius * Math.sin(orbitAngle));
    satelliteGroup.rotation.y = -orbitAngle + Math.PI / 2;

    renderer.render(scene, camera);
  }
  animate();
}
