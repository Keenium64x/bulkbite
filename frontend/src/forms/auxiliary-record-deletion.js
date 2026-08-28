// =============================================================================
// region TWO-APPROVAL DELETION STATE
// =============================================================================

export const DELETE_STAGE = Object.freeze({ CLOSED: "", REVIEW: "review", APPROVAL: "approval" })

export function normalizeDeletionPlan(payload = {}) {
  return Object.freeze({
    doctype: payload.doctype || "",
    roots: Object.freeze((payload.roots || []).map(normalizeNode)),
    dependencies: Object.freeze((payload.dependencies || []).map(normalizeNode)),
    blockers: Object.freeze((payload.blockers || []).map((row) => Object.freeze({ ...row }))),
    totalRecords: Number(payload.total_records || 0),
    planToken: payload.plan_token || "",
  })
}

export function finalDeleteRequest(doctype, names, plan) {
  if (!plan?.planToken || plan.blockers.length) throw new Error("Review every deletion connection before approval.")
  return Object.freeze({ doctype, names: Object.freeze([...names]), planToken: plan.planToken, cascade: Boolean(plan.dependencies.length), approved: true })
}

function normalizeNode(node) {
  return Object.freeze({ ...node, linkedBy: Object.freeze((node.linked_by || []).map((link) => Object.freeze({ ...link, fieldLabel: link.field_label || link.field }))) })
}

// endregion TWO-APPROVAL DELETION STATE
