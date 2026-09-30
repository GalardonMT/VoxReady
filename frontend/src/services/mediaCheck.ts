export type DeviceKind = 'camera' | 'microphone';

export function mediaErrorMessage(cause: unknown, device: DeviceKind): string {
  const name = cause && typeof cause === 'object' && 'name' in cause && typeof cause.name === 'string'
    ? cause.name : '';
  const label = device === 'camera' ? 'cámara' : 'micrófono';
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
    return `Se rechazó el permiso de ${label}. Habilítalo en el navegador y vuelve a comprobar.`;
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return `No se encontró ${label} disponible. Conecta o habilita el dispositivo en Windows y vuelve a comprobar.`;
  }
  return `No se pudo iniciar ${label}. Revisa su conexión, controlador y si otra aplicación lo está usando.`;
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
