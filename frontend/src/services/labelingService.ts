import { apiFetch } from './apiClient';
import { prepareLabelingCases } from './labelingModel';
import type {
  LabelingCase,
  LabelingCaseDetail,
  LabelingCaseListResponse,
  LabelingCaseStatus,
  LabelingLease,
  LabelingReview,
  LabelingReviewListResponse,
  LabelingReviewRequest,
  LabelingRecordingTicket,
  LabelingQualitySummary,
} from '../types/api';

const base = '/api/master/labeling-cases';

export interface LabelingQueuePage {
  items: LabelingCase[];
  total: number;
}

export const labelingService = {
  async list(status: LabelingCaseStatus, signal?: AbortSignal): Promise<LabelingQueuePage> {
    const response = await apiFetch<LabelingCaseListResponse>(
      `${base}?status=${status}&limit=10`,
      { signal },
    );
    return { items: prepareLabelingCases(response, status), total: response.total };
  },

  async listQueues(signal?: AbortSignal): Promise<{
    pending: LabelingQueuePage;
    reviewed: LabelingQueuePage;
  }> {
    const [pending, reviewed] = await Promise.all([
      this.list('pending', signal),
      this.list('reviewed', signal),
    ]);
    return { pending, reviewed };
  },

  getDetail(caseId: string, signal?: AbortSignal): Promise<LabelingCaseDetail> {
    return apiFetch<LabelingCaseDetail>(`${base}/${encodeURIComponent(caseId)}`, { signal });
  },

  acquireLease(caseId: string): Promise<LabelingLease> {
    return apiFetch<LabelingLease>(`${base}/${encodeURIComponent(caseId)}/lease`, {
      method: 'POST',
      body: JSON.stringify({ leaseToken: null, leaseGeneration: null }),
    });
  },

  renewLease(caseId: string, lease: LabelingLease): Promise<LabelingLease> {
    return apiFetch<LabelingLease>(`${base}/${encodeURIComponent(caseId)}/lease`, {
      method: 'POST',
      body: JSON.stringify({
        leaseToken: lease.leaseToken,
        leaseGeneration: lease.leaseGeneration,
      }),
    });
  },

  releaseLease(caseId: string, lease: LabelingLease): Promise<void> {
    return apiFetch<void>(`${base}/${encodeURIComponent(caseId)}/lease`, {
      method: 'DELETE',
      body: JSON.stringify({
        leaseToken: lease.leaseToken,
        leaseGeneration: lease.leaseGeneration,
      }),
    });
  },

  submitReview(caseId: string, request: LabelingReviewRequest): Promise<LabelingReview> {
    return apiFetch<LabelingReview>(`${base}/${encodeURIComponent(caseId)}/reviews`, {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  async listReviews(caseId: string, signal?: AbortSignal): Promise<LabelingReview[]> {
    const response = await apiFetch<LabelingReviewListResponse>(
      `${base}/${encodeURIComponent(caseId)}/reviews`,
      { signal },
    );
    return response.items;
  },

  getRecordingTicket(caseId: string, signal?: AbortSignal): Promise<LabelingRecordingTicket> {
    return apiFetch<LabelingRecordingTicket>(
      `${base}/${encodeURIComponent(caseId)}/recording-url`,
      { signal, cache: 'no-store' },
    );
  },

  getQualitySummary(period: { from: string | null; to: string | null }, signal?: AbortSignal): Promise<LabelingQualitySummary> {
    const query = new URLSearchParams({ currentReviewsOnly: 'true' });
    if (period.from) query.set('from', period.from);
    if (period.to) query.set('to', period.to);
    return apiFetch<LabelingQualitySummary>(
      `/api/master/quality-reviews/summary?${query.toString()}`,
      { signal, cache: 'no-store' },
    );
  },
};
