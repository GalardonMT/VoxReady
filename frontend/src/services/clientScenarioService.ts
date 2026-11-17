import { apiFetch } from './apiClient';
import { createClientScenarioService } from './clientScenarioServiceCore';

export * from './clientScenarioModel';

export const clientScenarioService = createClientScenarioService(apiFetch);
