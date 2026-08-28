// =============================================================================
// region TWO-APPROVAL DELETION STATE
// =============================================================================

export const DELETE_STAGE = Object.freeze({ CLOSED: "", REVIEW: "review", APPROVAL: "approval" })
export const DELETE_OUTCOME = Object.freeze({ UNLINK: "unlink", RECURSIVE: "recursive" })

export function normalizeDeletionPlan(payload = {}) {
  return Object.freeze({
    doctype: payload.doctype || "",
    roots: Object.freeze((payload.roots || []).map(normalizeNode)),
    dependencies: Object.freeze((payload.dependencies || []).map(normalizeNode)),
    blockers: Object.freeze((payload.blockers || []).map((row) => Object.freeze({ ...row }))),
    outcomes: Object.freeze({
      [DELETE_OUTCOME.UNLINK]: normalizeOutcome(payload.outcomes?.unlink),
      [DELETE_OUTCOME.RECURSIVE]: normalizeOutcome(payload.outcomes?.recursive),
    }),
    totalRecords: Number(payload.total_records || 0),
    planToken: payload.plan_token || "",
  })
}

export function deletionOutcomeAllowed(plan, outcome) {
  return Boolean(plan?.outcomes?.[outcome]?.allowed && !plan.outcomes[outcome].blockers.length)
}

export function finalDeleteRequest(doctype, names, plan, outcome) {
  if (!plan?.planToken) throw new Error("Review every deletion connection before approval.")
  if (!Object.values(DELETE_OUTCOME).includes(outcome)) throw new Error("Choose whether to unlink or recursively delete related records.")
  if (!deletionOutcomeAllowed(plan, outcome)) throw new Error("The selected deletion outcome is blocked.")
  return Object.freeze({ doctype, names: Object.freeze([...names]), planToken: plan.planToken, outcome, approved: true })
}

function normalizeNode(node) {
  return Object.freeze({ ...node, linkedBy: Object.freeze((node.linked_by || []).map((link) => Object.freeze({ ...link, fieldLabel: link.field_label || link.field }))) })
}

function normalizeOutcome(outcome = {}) {
  return Object.freeze({ allowed: Boolean(outcome.allowed), blockers: Object.freeze((outcome.blockers || []).map((row) => Object.freeze({ ...row }))), links: Object.freeze((outcome.links || []).map((row) => Object.freeze({ ...row }))) })
}

// endregion TWO-APPROVAL DELETION STATE
