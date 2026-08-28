import assert from "node:assert/strict"
import test from "node:test"

import { DELETE_STAGE, finalDeleteRequest, normalizeDeletionPlan } from "../src/forms/auxiliary-record-deletion.js"

test("normalizes every selected record, dependency, linking field, and blocker", () => {
  const plan = normalizeDeletionPlan({
    roots: [{ doctype: "BulkBite Supplier", name: "SUP-1", linked_by: [] }],
    dependencies: [{ doctype: "BulkBite Supplier Offer", name: "OFFER-1", linked_by: [{ doctype: "BulkBite Supplier Offer", field: "supplier", field_label: "Supplier" }] }],
    blockers: [],
    total_records: 2,
    plan_token: "fresh",
  })
  assert.equal(DELETE_STAGE.REVIEW, "review")
  assert.equal(plan.totalRecords, 2)
  assert.equal(plan.dependencies[0].linkedBy[0].fieldLabel, "Supplier")
  assert.deepEqual(finalDeleteRequest("BulkBite Supplier", ["SUP-1"], plan), {
    doctype: "BulkBite Supplier",
    names: ["SUP-1"],
    planToken: "fresh",
    cascade: true,
    approved: true,
  })
})

test("refuses a final request while blockers remain", () => {
  const plan = normalizeDeletionPlan({ blockers: [{ doctype: "BulkBite Receipt Intake", name: "REC-1", reason: "Operational history" }], plan_token: "fresh" })
  assert.throws(() => finalDeleteRequest("BulkBite Supplier", ["SUP-1"], plan), /Review every deletion connection/)
})
