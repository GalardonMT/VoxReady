import type {
  ClientScenarioDetail,
  ClientScenarioListOptions,
  ClientScenarioPage,
} from './clientScenarioModel';

type ApiRequest = <T>(endpoint: string, options?: RequestInit) => Promise<T>;

export function createClientScenarioService(apiRequest: ApiRequest) {
  const base = '/api/client/scenarios';

  return {
    list(options: ClientScenarioListOptions = {}): Promise<ClientScenarioPage> {
      const query = new URLSearchParams({
        page: String(options.page ?? 1),
        pageSize: String(options.pageSize ?? 20),
      });
      return apiRequest<ClientScenarioPage>(`${base}?${query}`, { cache: 'no-store' });
    },
    get(scenarioId: string): Promise<ClientScenarioDetail> {
      return apiRequest<ClientScenarioDetail>(
        `${base}/${encodeURIComponent(scenarioId)}`,
        { cache: 'no-store' },
      );
    },
  };
}
