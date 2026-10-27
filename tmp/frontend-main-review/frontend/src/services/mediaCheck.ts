export type DeviceKind = 'camera' | 'microphone';

export function mediaErrorMessage(cause: unknown, device: DeviceKind, blockedByPolicy = false): string {
  const name = cause && typeof cause === 'object' && 'name' in cause && typeof cause.name === 'string'
    ? cause.name : '';
  const label = device === 'camera' ? 'cámara' : 'micrófono';
  if (blockedByPolicy) {
    return `Esta página no tiene permitido usar ${label}. Abre la aplicación directamente o habilita ${label} en los permisos del sitio que la contiene.`;
  }
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
    return `El navegador bloqueó el acceso a ${label}. En los permisos de este sitio, cambia ${label} a Permitir y vuelve a comprobar. Si no apareció una solicitud, puede que el permiso ya estuviera bloqueado.`;
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return `No se encontró ${label} disponible. Conecta o habilita el dispositivo en Windows y vuelve a comprobar.`;
  }
  if (name === 'NotReadableError' || name === 'TrackStartError') {
    return `No se pudo usar ${label}. Cierra otras aplicaciones que lo estén usando y vuelve a comprobar.`;
  }
  if (name === 'SecurityError') {
    return `El navegador impide usar ${label} en esta página. Revisa los permisos y la configuración de seguridad del sitio.`;
  }
  return `No se pudo iniciar ${label}. Revisa su conexión, controlador y si otra aplicación lo está usando.`;
}

export function mediaApiError(isSecureContext: boolean, hasGetUserMedia: boolean): string | null {
  if (!isSecureContext) {
    return 'El navegador solo puede solicitar cámara y micrófono en HTTPS o localhost. Abre esta aplicación desde una de esas direcciones.';
  }
  if (!hasGetUserMedia) {
    return 'Este navegador no ofrece acceso a cámara y micrófono. Revisa sus permisos o prueba con una versión actualizada.';
  }
  return null;
}

export function blockedByMediaPolicy(device: DeviceKind, policy: { allowsFeature: (feature: string) => boolean } | undefined): boolean {
  return policy?.allowsFeature(device === 'camera' ? 'camera' : 'microphone') === false;
}

export function trackAvailable(track: MediaStreamTrack): boolean {
  return track.readyState === 'live' && track.enabled && !track.muted;
}

export function stopMediaStream(stream: MediaStream | null): void {
  stream?.getTracks().forEach((track) => track.stop());
}

export interface DeviceCheckResult {
  audio: MediaStream | null;
  video: MediaStream | null;
  audioError: unknown;
  videoError: unknown;
}

export async function requestAudioAndVideo(
  devices: Pick<MediaDevices, 'getUserMedia'>,
  isCurrent: () => boolean,
): Promise<DeviceCheckResult | null> {
  let audio: MediaStream | null = null;
  let video: MediaStream | null = null;
  let audioError: unknown = null;
  let videoError: unknown = null;

  try {
    audio = await devices.getUserMedia({ audio: true, video: false });
  } catch (error) {
    audioError = error;
  }
  if (!isCurrent()) {
    stopMediaStream(audio);
    return null;
  }

  try {
    video = await devices.getUserMedia({ audio: false, video: true });
  } catch (error) {
    videoError = error;
  }
  if (!isCurrent()) {
    stopMediaStream(audio);
    stopMediaStream(video);
    return null;
  }

  return { audio, video, audioError, videoError };
}
