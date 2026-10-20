import type { ClientStatus } from '../types/api';

export function validateClient(name: string, status: string): string | null {
  const normalizedName = name.trim();
  if (!normalizedName) return 'Ingresa el nombre de la empresa.';
  if (normalizedName.length > 150) return 'El nombre no puede superar los 150 caracteres.';
  if (status !== 'active' && status !== 'suspended') return 'Selecciona un estado válido.';
  return null;
}

export function normalizeClient(name: string, status: ClientStatus, spokespersonIds: string[] = []) {
  return { name: name.trim(), status, spokespersonIds: [...new Set(spokespersonIds)] };
}
