/** Which backend transition request is in flight. UX only: the backend enforces state. */
export type ActionMutation = 'approve' | 'reject' | 'execute' | 'approve_execute'
