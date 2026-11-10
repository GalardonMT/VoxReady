/**
 * Service for Rubric and Labeling queue management (Master Configurator)
 */
import { apiFetch, isAccessError } from './apiClient';
import { MasterRubric } from '../types/api';
import { INITIAL_MASTER_RUBRIC } from '../mock/mockData';

export const rubricService = {
  /**
   * Obtiene la versión activa de la rúbrica maestra
   */
  async getMasterRubric(): Promise<MasterRubric> {
    try {
      return await apiFetch<MasterRubric>('/master/rubric/active');
    } catch (error) { if (isAccessError(error)) throw error;
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
    } catch (error) {
      throw error;
    }
  }
};
