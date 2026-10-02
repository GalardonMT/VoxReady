import assert from 'node:assert/strict';
import test from 'node:test';
import { blockedByMediaPolicy, mediaApiError, mediaErrorMessage, requestAudioAndVideo, stopMediaStream, trackAvailable } from '../src/services/mediaCheck.ts';

test('un permiso rechazado y un dispositivo ausente producen errores distintos', () => {
  assert.match(mediaErrorMessage(Object.assign(new Error('denied'), { name: 'NotAllowedError' }), 'microphone'), /acceso a micrófono/);
  assert.match(mediaErrorMessage(Object.assign(new Error('missing'), { name: 'NotFoundError' }), 'camera'), /cámara disponible/);
});

test('explica por qué no aparece la solicitud de permisos', () => {
  assert.match(mediaApiError(false, false), /HTTPS o localhost/);
  assert.match(mediaApiError(true, false), /no ofrece acceso/);
  assert.equal(mediaApiError(true, true), null);
  assert.match(mediaErrorMessage({ name: 'NotAllowedError' }, 'camera'), /no apareció una solicitud/);
});

test('detecta una política que bloquea un dispositivo sin culpar al usuario', () => {
  const policy = { allowsFeature: (feature) => feature !== 'camera' };
  assert.equal(blockedByMediaPolicy('camera', policy), true);
  assert.equal(blockedByMediaPolicy('microphone', policy), false);
  assert.equal(blockedByMediaPolicy('camera', undefined), false);
  assert.match(mediaErrorMessage({ name: 'NotAllowedError' }, 'camera', true), /Esta página no tiene permitido usar cámara/);
});

test('una pista deja de estar disponible al terminar, mutearse o deshabilitarse', () => {
  const track = { readyState: 'live', enabled: true, muted: false };
  assert.equal(trackAvailable(track), true);
  track.muted = true;
  assert.equal(trackAvailable(track), false);
  track.muted = false;
  track.enabled = false;
  assert.equal(trackAvailable(track), false);
  track.enabled = true;
  track.readyState = 'ended';
  assert.equal(trackAvailable(track), false);
});

test('al salir se detienen todas las pistas', () => {
  let stopped = 0;
  stopMediaStream({ getTracks: () => [{ stop: () => stopped++ }, { stop: () => stopped++ }] });
  assert.equal(stopped, 2);
});

test('la falta de cámara no impide pedir permiso de micrófono', async () => {
  const calls = [];
  const audio = { getTracks: () => [{ stop() {} }] };
  const devices = { getUserMedia: async (constraints) => {
    calls.push(constraints);
    if (constraints.video) throw Object.assign(new Error('missing'), { name: 'NotFoundError' });
    return audio;
  } };
  const result = await requestAudioAndVideo(devices, () => true);
  assert.deepEqual(calls, [{ audio: true, video: false }, { audio: false, video: true }]);
  assert.equal(result.audio, audio);
  assert.equal(result.video, null);
  assert.equal(result.videoError.name, 'NotFoundError');
});

test('rechazar el micrófono todavía permite comprobar la cámara', async () => {
  const calls = [];
  const video = { getTracks: () => [{ stop() {} }] };
  const devices = { getUserMedia: async (constraints) => {
    calls.push(constraints);
    if (constraints.audio) throw Object.assign(new Error('denied'), { name: 'NotAllowedError' });
    return video;
  } };
  const result = await requestAudioAndVideo(devices, () => true);
  assert.deepEqual(calls, [{ audio: true, video: false }, { audio: false, video: true }]);
  assert.equal(result.audio, null);
  assert.equal(result.video, video);
  assert.equal(result.audioError.name, 'NotAllowedError');
});

test('si se cancela durante el permiso se liberan las pistas recibidas', async () => {
  let stopped = 0;
  let current = true;
  const devices = { getUserMedia: async () => {
    current = false;
    return { getTracks: () => [{ stop: () => stopped++ }] };
  } };
  const result = await requestAudioAndVideo(devices, () => current);
  assert.equal(result, null);
  assert.equal(stopped, 1);
});
