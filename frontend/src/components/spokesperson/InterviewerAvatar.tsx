import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

interface InterviewerAvatarProps {
  questionText: string;
  questionIndex: number;
  isPaused: boolean;
  onSpeechEnd?: () => void;
  className?: string;
  style?: React.CSSProperties;
}

export const InterviewerAvatar: React.FC<InterviewerAvatarProps> = ({
  questionText,
  questionIndex,
  isPaused,
  onSpeechEnd,
  className,
  style
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isMuted, setIsMuted] = useState(false);

  const onSpeechEndRef = useRef(onSpeechEnd);
  onSpeechEndRef.current = onSpeechEnd;

  // Referencias para el loop de animación
  const isSpeakingRef = useRef(false);
  isSpeakingRef.current = isSpeaking;

  const isPausedRef = useRef(isPaused);
  isPausedRef.current = isPaused;

  // Refs de three.js
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const animFrameIdRef = useRef<number | null>(null);

  // Huesos y meshes con morph targets
  const morphMeshesRef = useRef<{ mesh: THREE.Mesh; mouthIndex: number; smileIndex: number }[]>([]);
  const eyeMeshesRef = useRef<THREE.Object3D[]>([]);
  const bonesRef = useRef<{
    spine1?: THREE.Bone;
    spine2?: THREE.Bone;
    neck?: THREE.Bone;
    head?: THREE.Bone;
    leftShoulder?: THREE.Bone;
    rightShoulder?: THREE.Bone;
    initialRotations: Map<THREE.Object3D, THREE.Euler>;
    initialPositions: Map<THREE.Object3D, THREE.Vector3>;
  }>({
    initialRotations: new Map(),
    initialPositions: new Map()
  });

  // Sintetizador de voz
  const speakQuestion = useCallback((text: string) => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;

    window.speechSynthesis.cancel();
    if (isPausedRef.current || !text) {
      setIsSpeaking(false);
      return;
    }

    // Limpiar texto para una locución fluida
    const cleanText = text.replace(/["“”«»]/g, '').trim();
    if (!cleanText) return;

    const utterance = new SpeechSynthesisUtterance(cleanText);

    // Buscar una voz natural en español
    const voices = window.speechSynthesis.getVoices();
    const spanishVoice =
      voices.find(v => v.lang.startsWith('es') && (v.name.includes('Male') || v.name.includes('Hombre') || v.name.includes('Alvaro') || v.name.includes('Raul') || v.name.includes('Pablo') || v.name.includes('Jorge'))) ||
      voices.find(v => v.lang.startsWith('es') && !v.name.includes('Google') && !v.name.includes('Natural')) ||
      voices.find(v => v.lang.startsWith('es')) ||
      null;

    if (spanishVoice) {
      utterance.voice = spanishVoice;
    }
    utterance.lang = spanishVoice?.lang || 'es-ES';
    utterance.rate = 0.98;
    utterance.pitch = 0.95;

    utterance.onstart = () => {
      setIsSpeaking(true);
    };

    utterance.onend = () => {
      setIsSpeaking(false);
      onSpeechEndRef.current?.();
    };

    utterance.onerror = (e) => {
      // Ignorar cancelaciones intencionales
      if (e.error !== 'canceled' && e.error !== 'interrupted') {
        console.warn('SpeechSynthesis error:', e.error);
      }
      setIsSpeaking(false);
    };

    try {
      window.speechSynthesis.speak(utterance);
    } catch (err) {
      console.warn('Error al ejecutar speak:', err);
      setIsSpeaking(false);
    }
  }, []);

  // Leer la pregunta cada vez que cambia questionIndex o questionText
  useEffect(() => {
    if (isLoading || isMuted || isPaused) return;

    // Pequeño retardo de cortesía de 350ms para que la transición sea fluida
    const timer = setTimeout(() => {
      speakQuestion(questionText);
    }, 350);

    return () => {
      clearTimeout(timer);
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
      setIsSpeaking(false);
    };
  }, [questionIndex, questionText, isLoading, isMuted, isPaused, speakQuestion]);

  // Si se pausa la sesión, detener de inmediato la locución
  useEffect(() => {
    if (isPaused) {
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
      setIsSpeaking(false);
    }
  }, [isPaused]);

  // Inicialización de la escena Three.js
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const width = container.clientWidth || 320;
    const height = container.clientHeight || 280;

    // Escena
    const scene = new THREE.Scene();
    sceneRef.current = scene;

    // Cámara con ángulo cerrado (32 deg) para encuadre tipo televisión sin deformación
    const camera = new THREE.PerspectiveCamera(32, width / height, 0.1, 50);
    // Posición inicial estándar para busto de Ready Player Me
    camera.position.set(0, 1.58, 0.88);
    camera.lookAt(0, 1.55, 0);

    // Renderer
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance'
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.innerHTML = '';
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Iluminación de estudio profesional
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.3);
    scene.add(ambientLight);

    // Luz principal (Key Light)
    const keyLight = new THREE.DirectionalLight(0xfff5ea, 2.2);
    keyLight.position.set(0.9, 2.2, 1.8);
    scene.add(keyLight);

    // Luz de relleno (Fill Light)
    const fillLight = new THREE.DirectionalLight(0xbfdbfe, 1.1);
    fillLight.position.set(-1.4, 1.5, 1.2);
    scene.add(fillLight);

    // Luz trasera / contra (Rim / Hair Light)
    const rimLight = new THREE.DirectionalLight(0x60a5fa, 0.9);
    rimLight.position.set(0, 2.0, -1.8);
    scene.add(rimLight);

    // Cargar modelo GLB
    const loader = new GLTFLoader();
    let isCancelled = false;

    loader.load(
      '/models/Human.glb',
      (gltf) => {
        if (isCancelled) return;

        const model = gltf.scene;
        scene.add(model);

        // Buscar huesos de respiración y postura
        const bonesData = bonesRef.current;
        bonesData.initialRotations.clear();
        bonesData.initialPositions.clear();

        model.traverse((child) => {
          if (child instanceof THREE.Bone) {
            const name = child.name;
            if (name === 'Spine1') bonesData.spine1 = child;
            if (name === 'Spine2') bonesData.spine2 = child;
            if (name === 'Neck') bonesData.neck = child;
            if (name === 'Head') bonesData.head = child;
            if (name === 'LeftShoulder') bonesData.leftShoulder = child;
            if (name === 'RightShoulder') bonesData.rightShoulder = child;

            bonesData.initialRotations.set(child, child.rotation.clone());
            bonesData.initialPositions.set(child, child.position.clone());
          }

          // Buscar meshes con morph targets para labios y parpadeo
          if (child instanceof THREE.Mesh) {
            if (child.morphTargetDictionary && child.morphTargetInfluences) {
              const mouthIndex = child.morphTargetDictionary['mouthOpen'];
              const smileIndex = child.morphTargetDictionary['mouthSmile'];
              if (mouthIndex !== undefined) {
                morphMeshesRef.current.push({
                  mesh: child,
                  mouthIndex,
                  smileIndex: smileIndex !== undefined ? smileIndex : -1
                });
                // Sonrisa sutil y profesional fija
                if (smileIndex !== undefined) {
                  child.morphTargetInfluences[smileIndex] = 0.12;
                }
              }
            }

            // Ojos para parpadeo
            if (child.name === 'EyeLeft' || child.name === 'EyeRight') {
              eyeMeshesRef.current.push(child);
            }
          }
        });

        // Calcular encuadre exacto con BoundingBox de la cabeza
        const box = new THREE.Box3().setFromObject(model);
        const headNode = model.getObjectByName('Head');
        let targetY = 1.55;
        if (headNode) {
          const headWorldPos = new THREE.Vector3();
          headNode.getWorldPosition(headWorldPos);
          targetY = headWorldPos.y - 0.05;
        } else if (!box.isEmpty()) {
          targetY = box.max.y - 0.22;
        }

        camera.position.set(0, targetY + 0.04, 0.85);
        camera.lookAt(0, targetY, 0);

        setIsLoading(false);
      },
      undefined,
      (error) => {
        if (isCancelled) return;
        console.error('Error al cargar /models/Human.glb:', error);
        setLoadError('No se pudo cargar el modelo 3D.');
        setIsLoading(false);
      }
    );

    // Variables de parpadeo procedural
    let nextBlinkTime = 2.0;
    let blinkDuration = 0.14;
    let blinkStartTime = 0;
    let isBlinking = false;
    let currentMouthOpen = 0;

    const clock = new THREE.Clock();

    // Loop de animación a 60fps
    const animate = () => {
      animFrameIdRef.current = requestAnimationFrame(animate);

      const delta = clock.getDelta();
      const elapsed = clock.getElapsedTime();

      // 1. ANIMACIÓN DE RESPIRACIÓN (Idle breathing)
      // Ritmo de respiración suave: ~16 respiraciones/minuto (frecuencia = 1.7)
      const breath = Math.sin(elapsed * 1.7);
      const spine1 = bonesRef.current.spine1;
      const spine2 = bonesRef.current.spine2;
      const head = bonesRef.current.head;
      const leftShoulder = bonesRef.current.leftShoulder;
      const rightShoulder = bonesRef.current.rightShoulder;
      const initialRots = bonesRef.current.initialRotations;
      const initialPos = bonesRef.current.initialPositions;

      if (spine1 && initialRots.has(spine1)) {
        const base = initialRots.get(spine1)!;
        spine1.rotation.x = base.x + breath * 0.016;
      }
      if (spine2 && initialRots.has(spine2)) {
        const base = initialRots.get(spine2)!;
        spine2.rotation.x = base.x + breath * 0.012;
      }

      // Elevación de hombros sutil con la inhalación
      if (leftShoulder && initialPos.has(leftShoulder)) {
        const base = initialPos.get(leftShoulder)!;
        leftShoulder.position.y = base.y + (breath + 1) * 0.0018;
      }
      if (rightShoulder && initialPos.has(rightShoulder)) {
        const base = initialPos.get(rightShoulder)!;
        rightShoulder.position.y = base.y + (breath + 1) * 0.0018;
      }

      // Micro-movimientos de cabeza orgánicos (para que no parezca inmóvil)
      if (head && initialRots.has(head)) {
        const base = initialRots.get(head)!;
        const subtleNod = isSpeakingRef.current ? Math.sin(elapsed * 8) * 0.018 : 0;
        head.rotation.x = base.x + Math.sin(elapsed * 0.8) * 0.006 + subtleNod;
        head.rotation.y = base.y + Math.cos(elapsed * 0.5) * 0.008;
      }

      // 2. PARPADEO (Blink)
      if (!isBlinking && elapsed >= nextBlinkTime) {
        isBlinking = true;
        blinkStartTime = elapsed;
        // Próximo parpadeo en 2.8 a 5.2 segundos de forma aleatoria
        nextBlinkTime = elapsed + 2.8 + Math.random() * 2.4;
      }

      if (isBlinking) {
        const blinkProgress = (elapsed - blinkStartTime) / blinkDuration;
        if (blinkProgress >= 1.0) {
          isBlinking = false;
          // Restaurar escala normal de ojos
          eyeMeshesRef.current.forEach((eye) => {
            eye.scale.y = 1.0;
          });
        } else {
          // Escala triangular en Y: de 1 a 0.05 y vuelve a 1
          const scaleY =
            blinkProgress < 0.5
              ? THREE.MathUtils.lerp(1.0, 0.05, blinkProgress * 2)
              : THREE.MathUtils.lerp(0.05, 1.0, (blinkProgress - 0.5) * 2);

          eyeMeshesRef.current.forEach((eye) => {
            eye.scale.y = scaleY;
          });
        }
      }

      // 3. MOVIMIENTO DE LABIOS (Lip Sync)
      // "La única vez que tiene que mover los labios es cuando aparece una pregunta en pantalla... este debería leerla."
      if (isSpeakingRef.current && !isPausedRef.current) {
        // Modular apertura de boca con armónicos rápidos para simular fonemas
        const freq1 = Math.sin(elapsed * 16);
        const freq2 = Math.cos(elapsed * 9);
        const freq3 = Math.sin(elapsed * 24);
        const rawMouth = Math.max(0, (freq1 * 0.45 + freq2 * 0.35 + freq3 * 0.2 + 0.25));
        const targetOpen = Math.min(0.65, rawMouth);
        currentMouthOpen = THREE.MathUtils.lerp(currentMouthOpen, targetOpen, 0.3);
      } else {
        // Cerrar boca suavemente
        currentMouthOpen = THREE.MathUtils.lerp(currentMouthOpen, 0, 0.25);
      }

      // Aplicar influencia de mouthOpen a las mallas correspondientes
      morphMeshesRef.current.forEach(({ mesh, mouthIndex }) => {
        if (mesh.morphTargetInfluences) {
          mesh.morphTargetInfluences[mouthIndex] = currentMouthOpen;
        }
      });

      renderer.render(scene, camera);
    };

    animate();

    // Manejo de redimensionado responsivo
    const handleResize = () => {
      if (!container || !rendererRef.current) return;
      const newW = container.clientWidth;
      const newH = container.clientHeight;
      if (newW > 0 && newH > 0) {
        camera.aspect = newW / newH;
        camera.updateProjectionMatrix();
        rendererRef.current.setSize(newW, newH);
      }
    };

    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(container);

    // Limpieza
    return () => {
      isCancelled = true;
      resizeObserver.disconnect();
      if (animFrameIdRef.current !== null) {
        cancelAnimationFrame(animFrameIdRef.current);
      }
      if (rendererRef.current) {
        rendererRef.current.dispose();
        if (rendererRef.current.domElement.parentElement) {
          rendererRef.current.domElement.parentElement.removeChild(rendererRef.current.domElement);
        }
      }
      morphMeshesRef.current = [];
      eyeMeshesRef.current = [];
    };
  }, []);

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: '280px',
        overflow: 'hidden',
        borderRadius: '8px',
        background: 'linear-gradient(180deg, #111827 0%, #080c14 100%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        ...style
      }}
      className={className}
    >
      {/* Canvas 3D */}
      <div
        ref={containerRef}
        style={{
          width: '100%',
          height: '100%',
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none'
        }}
      />

      {/* Spinner de carga inicial */}
      {isLoading && (
        <div
          style={{
            position: 'absolute',
            zIndex: 10,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '10px'
          }}
        >
          <div
            style={{
              width: '36px',
              height: '36px',
              border: '3px solid rgba(96, 165, 250, 0.2)',
              borderTopColor: '#38bdf8',
              borderRadius: '50%',
              animation: 'spin 1s linear infinite'
            }}
          />
          <span style={{ fontSize: '12px', color: '#94a3b8', fontWeight: 500 }}>
            Cargando entrevistador 3D...
          </span>
        </div>
      )}

      {/* Error fallback */}
      {loadError && (
        <div style={{ position: 'absolute', zIndex: 10, textAlign: 'center', padding: '16px' }}>
          <div style={{ fontSize: '32px', marginBottom: '8px' }}>👔</div>
          <div style={{ fontSize: '12px', color: '#f87171' }}>{loadError}</div>
        </div>
      )}

      {/* Badge Superior Izquierdo: Entrevistador IA */}
      <div
        style={{
          position: 'absolute',
          top: '12px',
          left: '12px',
          zIndex: 10,
          background: 'rgba(15, 23, 42, 0.75)',
          backdropFilter: 'blur(6px)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          color: '#f1f5f9',
          padding: '4px 10px',
          borderRadius: '999px',
          fontSize: '11.5px',
          fontWeight: 600,
          display: 'flex',
          alignItems: 'center',
          gap: '6px'
        }}
      >
        <span>🤖 Entrevistador IA</span>
      </div>

      {/* Badge Inferior Izquierdo: Estado actual (En pausa / Hablando / En espera) */}
      <div
        style={{
          position: 'absolute',
          bottom: '12px',
          left: '12px',
          zIndex: 10,
          background: 'rgba(15, 23, 42, 0.8)',
          backdropFilter: 'blur(6px)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          color: '#e2e8f0',
          padding: '4px 10px',
          borderRadius: '999px',
          fontSize: '11px',
          fontWeight: 500,
          display: 'flex',
          alignItems: 'center',
          gap: '6px'
        }}
      >
        {isPaused ? (
          <>
            <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: '#f59e0b' }} />
            <span>⏸ En pausa</span>
          </>
        ) : isSpeaking ? (
          <>
            <span
              style={{
                width: '7px',
                height: '7px',
                borderRadius: '50%',
                background: '#38bdf8',
                boxShadow: '0 0 8px #38bdf8'
              }}
            />
            <span>🗣️ Formulando pregunta...</span>
          </>
        ) : (
          <>
            <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: '#10b981' }} />
            <span>En escucha</span>
          </>
        )}
      </div>

      {/* Botón flotante inferior derecho: Repetir pregunta / Silenciar */}
      <div
        style={{
          position: 'absolute',
          bottom: '10px',
          right: '12px',
          zIndex: 10,
          display: 'flex',
          gap: '6px'
        }}
      >
        <button
          type="button"
          onClick={() => speakQuestion(questionText)}
          disabled={isPaused || isSpeaking}
          title="Escuchar la pregunta de nuevo"
          style={{
            background: 'rgba(15, 23, 42, 0.75)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            color: isSpeaking ? '#38bdf8' : '#cbd5e1',
            borderRadius: '6px',
            padding: '4px 8px',
            fontSize: '11px',
            cursor: isPaused || isSpeaking ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            transition: 'all 0.2s ease',
            opacity: isPaused ? 0.5 : 1
          }}
        >
          <span>🔊</span>
          <span>Repetir</span>
        </button>

        <button
          type="button"
          onClick={() => {
            if (!isMuted) {
              if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
                window.speechSynthesis.cancel();
              }
              setIsSpeaking(false);
            }
            setIsMuted((prev) => !prev);
          }}
          title={isMuted ? 'Activar voz del entrevistador' : 'Silenciar voz del entrevistador'}
          style={{
            background: 'rgba(15, 23, 42, 0.75)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            color: isMuted ? '#f87171' : '#94a3b8',
            borderRadius: '6px',
            padding: '4px 8px',
            fontSize: '11px',
            cursor: 'pointer',
            transition: 'all 0.2s ease'
          }}
        >
          {isMuted ? '🔇' : '🔉'}
        </button>
      </div>
    </div>
  );
};
