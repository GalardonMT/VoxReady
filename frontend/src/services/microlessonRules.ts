import type { Microlesson, MicrolessonInput } from '../types/api';

export function withClient(form: MicrolessonInput, clientId: string): MicrolessonInput {
  return { ...form, clientId, scenarioId: '' };
}

export function shouldShowVideo(lesson: Pick<Microlesson, 'hasVideo'>): boolean {
  return lesson.hasVideo;
}

export function practiceScenario(lesson: Pick<Microlesson, 'scenarioId'>): string {
  return lesson.scenarioId;
}
