import type { MicrolessonAssignment, SpokespersonMicrolesson } from '../types/api';

/** The master API returns assignment cycles in newest-first order. */
export function latestAssignmentIds(assignments: Pick<MicrolessonAssignment, 'id' | 'userId'>[]): Set<string> {
  const users = new Set<string>();
  const latest = new Set<string>();
  for (const assignment of assignments) {
    if (users.has(assignment.userId)) continue;
    users.add(assignment.userId);
    latest.add(assignment.id);
  }
  return latest;
}

export function groupMicrolessons(items: SpokespersonMicrolesson[], history: SpokespersonMicrolesson[]) {
  const currentAssignmentIds = new Set(items.map(item => item.assignmentId));
  const historyByAssignmentId = new Map(history.map(item => [item.assignmentId, item]));
  return {
    assigned: items.filter(item => item.assignmentStatus === 'assigned'),
    inProgress: items.filter(item => item.assignmentStatus === 'in_progress'),
    completed: [
      ...items.filter(item => item.assignmentStatus === 'completed').map(item => ({ ...historyByAssignmentId.get(item.assignmentId), ...item })),
      ...history.filter(item => item.assignmentStatus === 'completed' && item.status !== 'archived' && !currentAssignmentIds.has(item.assignmentId)),
    ],
    catalog: items.filter(item => item.assignmentStatus === null || item.assignmentStatus === 'revoked'),
    archived: history.filter(item => item.assignmentStatus === 'revoked' || item.status === 'archived'),
  };
}

export function chooseLesson(items: SpokespersonMicrolesson[], reference: string): SpokespersonMicrolesson | null {
  return items.find(item => item.id === reference && item.canOpen) ?? null;
}
