export type PortalRole = 'guard' | 'atm_admin' | 'govt_official' | 'super_admin';

export type PortalUser = {
  id: string;
  employeeId: string;
  email: string;
  displayName: string;
  mobile: string;
  role: PortalRole;
  address: string;
  pinCode: string;
  assignedAtms: string[];
  dutyTiming: string;
  emergencyContact: string;
  verificationStatus: 'pending' | 'verified' | 'suspended';
  aadhaarVerified: boolean;
  aadhaarMasked: string;
  status: 'active' | 'disabled';
  createdAt: string;
};

export type PortalAlertTimelineItem = {
  at: string;
  tier: string;
  note: string;
};

export type PortalAlert = {
  id: string;
  atmId: string;
  cameraId: string;
  incidentKind: string;
  priorRuleCode: string;
  severity: string;
  summary: string;
  subjectCode: string;
  snapshotUrl: string;
  snapshotSha256: string;
  currentPriority: number;
  status: 'active_p1' | 'escalated_p2' | 'escalated_p3' | 'acknowledged' | 'resolved';
  sirenActive: boolean;
  assignedGuardId: string;
  assignedGuardName: string;
  assignedAdminName: string;
  assignedGovtName: string;
  backupGovtName: string;
  escalateAfterAt: string;
  acknowledgedBy: string;
  resolvedBy: string;
  timeline: PortalAlertTimelineItem[];
  createdAt: string;
  updatedAt: string;
};

export type RuleObservation = {
  id: string;
  cameraId: string;
  atmId: string;
  ruleCode: string;
  subjectCode: string;
  detail: string;
  status: string;
  observedAt: string;
};

export type SecurityRule = {
  id: string;
  code: string;
  name: string;
  stage: 'observe' | 'escalate';
  enabled: boolean;
  requirePriorRule: string;
  description: string;
  updatedAt: string;
};

export type AtmAssignment = {
  atmId: string;
  atmName: string;
  location: string;
  guardUserId: string;
  guardName: string;
  adminUserId: string;
  adminName: string;
  govtUserId: string;
  govtName: string;
  backupGovtUserId: string;
  backupGovtName: string;
  p1SlaSeconds: number;
  p2SlaSeconds: number;
  updatedAt: string;
};

let portalCsrf = '';
export const setPortalCsrf = (token: string) => { portalCsrf = token; };

async function secRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.method && !['GET', 'HEAD'].includes(init.method.toUpperCase()) && portalCsrf) {
    headers.set('X-Portal-CSRF', portalCsrf);
  }
  const res = await fetch(path.startsWith('/sec-api') ? path : `/sec-api${path}`, {
    ...init,
    headers,
    credentials: 'same-origin',
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    if (res.status === 401 && !path.startsWith('/auth/')) {
      window.dispatchEvent(new Event('drishti-portal:session-expired'));
    }
    throw new Error(payload.detail || `Security Portal request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export const portalApi = {
  health: () => secRequest<{ status: string; service: string; usersCount: number; activeAlerts: number; observations: number }>('/health'),
  me: async () => {
    const r = await secRequest<{ authenticated?: boolean; user: PortalUser | null; csrfToken: string }>('/auth/me');
    if (r.csrfToken) setPortalCsrf(r.csrfToken);
    return r;
  },
  login: async (identifier: string, password: string) => {
    const r = await secRequest<{ user: PortalUser; csrfToken: string }>('/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ identifier, password }),
    });
    setPortalCsrf(r.csrfToken);
    return r;
  },
  requestOtp: (identifier: string) => secRequest<{ challengeId: string; maskedMobile: string; demoOtpHint: string; notice: string }>('/auth/otp/request', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ identifier }),
  }),
  verifyOtp: async (challenge_id: string, otp: string) => {
    const r = await secRequest<{ user: PortalUser; csrfToken: string }>('/auth/otp/verify', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ challenge_id, otp }),
    });
    setPortalCsrf(r.csrfToken);
    return r;
  },
  logout: async () => {
    await secRequest('/auth/logout', { method: 'POST' });
    setPortalCsrf('');
  },
  guards: () => secRequest<PortalUser[]>('/guards'),
  createGuard: (payload: {
    employee_id: string; email: string; display_name: string; mobile: string; role: PortalRole; password: string;
    address: string; pin_code: string; assigned_atms: string[]; duty_timing: string; emergency_contact: string;
  }) => secRequest<PortalUser>('/guards', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  updateGuard: (id: string, payload: Record<string, unknown>) =>
    secRequest<PortalUser>(`/guards/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  requestAadhaarOtp: (userId: string, aadhaar_input: string) =>
    secRequest<{ challengeId: string; aadhaarMasked: string; demoOtpHint: string; notice: string }>(`/guards/${userId}/aadhaar-otp/request`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ aadhaar_input }),
    }),
  verifyAadhaarOtp: (userId: string, challenge_id: string, otp: string) =>
    secRequest<PortalUser>(`/guards/${userId}/aadhaar-otp/verify`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ challenge_id, otp }),
    }),
  assignments: () => secRequest<AtmAssignment[]>('/assignments'),
  updateAssignment: (atmId: string, payload: Record<string, unknown>) =>
    secRequest<AtmAssignment>(`/assignments/${atmId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  rules: () => secRequest<SecurityRule[]>('/rules'),
  toggleRule: (id: string, enabled: boolean) =>
    secRequest<SecurityRule>(`/rules/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }) }),
  alerts: () => secRequest<{ alerts: PortalAlert[]; observations: RuleObservation[] }>('/alerts'),
  simulateBreach: (atm_id = 'ATM-01', with_prior_helmet = true) =>
    secRequest<{ action: string; alertId?: string; priority?: number; siren?: boolean }>('/alerts/simulate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ atm_id, with_prior_helmet }),
    }),
  acknowledgeAlert: (id: string) => secRequest(`/alerts/${id}/acknowledge`, { method: 'POST' }),
  escalateAlert: (id: string) => secRequest(`/alerts/${id}/escalate`, { method: 'POST' }),
  resolveAlert: (id: string) => secRequest(`/alerts/${id}/resolve`, { method: 'POST' }),
};

