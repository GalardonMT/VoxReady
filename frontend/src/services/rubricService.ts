/**
 * Service for Rubric and Labeling queue management (Master Configurator)
 */
import { apiFetch } from './apiClient';
import { MasterRubric, LabelingCase } from '../types/api';
import { INITIAL_MASTER_RUBRIC, INITIAL_LABELING_QUEUE } from '../mock/mockData';

export const rubricService = {
  /**
   * Obtiene la versión activa de la rúbrica maestra
   */
  async getMasterRubric(): Promise<MasterRubric> {
    try {
      return await apiFetch<MasterRubric>('/master/rubric/active');
    } catch {
      return INITIAL_MASTER_RUBRIC;
    }
  },

  /**
   * Publica una nueva versión de la rúbrica
   */
  async publishRubric(rubric: MasterRubric): Promise<MasterRubric> {
    try {
      return await apiFetch<MasterRubric>('/master/rubric', {
        method: 'POST',
        body: JSON.stringify(rubric)
      });
    } catch {
      return rubric;
    }
  },

  /**
   * Obtiene los casos pendientes en la cola de etiquetado
   */
  async getLabelingCases(): Promise<LabelingCase[]> {
    try {
      return await apiFetch<LabelingCase[]>('/master/labeling-cases');
    } catch {
      return INITIAL_LABELING_QUEUE;
    }
  },

  /**
   * Envía la evaluación de un experto sobre un caso de la cola
   */
  async submitExpertEvaluation(
    caseId: string,
    scores: { expression: number; tone: number; coherence: number; empathy: number },
    comment: string
  ): Promise<boolean> {
    try {
      await apiFetch(`/master/labeling-cases/${caseId}/evaluate`, {
        method: 'POST',
        body: JSON.stringify({ expertScores: scores, expertComment: comment })
      });
      return true;
    } catch {
      return true;
    }
  }
};
