// =============================================================================
// region TWO-APPROVAL DELETION STATE
// =============================================================================

export const DELETE_STAGE = Object.freeze({ CLOSED: "", REVIEW: "review", APPROVAL: "approval" })
export const DELETE_OUTCOME = Object.freeze({ UNLINK: "unlink", DELETE: "delete", RECURSIVE: "delete" })

export function normalizeDeletionPlan(payload = {}) {
  return Object.freeze({
    doctype: payload.doctype || "",
    roots: Object.freeze((payload.roots || []).map(normalizeNode)),
    dependencies: Object.freeze((payload.dependencies || []).map(normalizeNode)),
    blockers: Object.freeze((payload.blockers || []).map((row) => Object.freeze({ ...row }))),
    relatedTypes: Object.freeze((payload.related_types || payload.relatedTypes || []).map(normalizeRelatedType)),
    resolution: normalizeResolution(payload.resolution),
    totalRecords: Number(payload.total_records || 0),
    planToken: payload.plan_token || "",
  })
}

export function deletionOutcomeAllowed(plan, outcome) {
  return Boolean(Object.values(DELETE_OUTCOME).includes(outcome) && plan?.resolution?.allowed && !plan.resolution.blockers.length)
}

export function finalDeleteRequest(doctype, names, plan, outcome, outcomesByDoctype = {}) {
  if (!plan?.planToken) throw new Error("Review every deletion connection before approval.")
  if (!Object.values(DELETE_OUTCOME).includes(outcome)) throw new Error("Choose Delete or Unlink as the default related-record action.")
  if (!deletionOutcomeAllowed(plan, outcome)) throw new Error("The selected deletion outcome is blocked.")
  return Object.freeze({ doctype, names: Object.freeze([...names]), planToken: plan.planToken, outcome, outcomesByDoctype: Object.freeze({ ...outcomesByDoctype }), approved: true })
}

export function relatedTypeChoices(plan) {
  return plan?.relatedTypes || []
}

function normalizeNode(node) {
  return Object.freeze({ ...node, linkedBy: Object.freeze((node.linked_by || []).map((link) => Object.freeze({ ...link, fieldLabel: link.field_label || link.field }))) })
}

function normalizeOutcome(outcome = {}) {
  return Object.freeze({ allowed: Boolean(outcome.allowed), blockers: Object.freeze((outcome.blockers || []).map((row) => Object.freeze({ ...row }))), links: Object.freeze((outcome.links || []).map((row) => Object.freeze({ ...row }))) })
}

function normalizeRelatedType(row = {}) {
  return Object.freeze({
    doctype: row.doctype || "",
    recordCount: Number(row.record_count ?? row.recordCount ?? 0),
    linkCount: Number(row.link_count ?? row.linkCount ?? 0),
    historyCount: Number(row.history_count ?? row.historyCount ?? 0),
    managed: Boolean(row.managed),
    configurable: Boolean(row.configurable ?? row.managed),
  })
}

function normalizeResolution(resolution = {}) {
  return Object.freeze({
    allowed: Boolean(resolution.allowed),
    blockers: Object.freeze((resolution.blockers || []).map((row) => Object.freeze({ ...row }))),
    defaultOutcome: resolution.default_outcome || resolution.defaultOutcome || "",
    outcomesByDoctype: Object.freeze({ ...(resolution.outcomes_by_doctype || resolution.outcomesByDoctype || {}) }),
    deleteCount: Number(resolution.delete_count ?? resolution.deleteCount ?? 0),
    unlinkCount: Number(resolution.unlink_count ?? resolution.unlinkCount ?? 0),
    archiveCount: Number(resolution.archive_count ?? resolution.archiveCount ?? 0),
    preserveCount: Number(resolution.preserve_count ?? resolution.preserveCount ?? 0),
    archived: Object.freeze((resolution.archived || []).map((row) => Object.freeze({ ...row }))),
    preserved: Object.freeze((resolution.preserved || []).map((row) => Object.freeze({ ...row }))),
  })
}

// endregion TWO-APPROVAL DELETION STATE
