import { getAuxiliaryCatalogue, getAuxiliaryRecord, getAuxiliaryRecordWorkspace, saveAuxiliaryRecord, planAuxiliaryRecordDeletion, deleteAuxiliaryRecords } from "@/resources/api"

// =============================================================================
// region ALL SETUP PAGE DEFINITION
// =============================================================================

const recordModules = import.meta.glob("./records/*.definition.js", { eager: true })
const records = Object.freeze(Object.fromEntries(Object.values(recordModules).map((module) => module.default).filter((definition) => definition?.doctype).map((definition) => [definition.doctype, definition])))

export const auxiliaryRecordSystem = Object.freeze({
  page: Object.freeze({ preserveExistingLayout: true, pageSize: 25 }),
  deletion: Object.freeze({ enabled: true, approvals: 2, defaultOutcome: "delete", relatedTypeOverrides: true, preserveProtectedHistory: true }),
  records,
  resources: Object.freeze({
    catalogue: getAuxiliaryCatalogue,
    list: getAuxiliaryRecordWorkspace,
    load: getAuxiliaryRecord,
    save: saveAuxiliaryRecord,
    planDelete: planAuxiliaryRecordDeletion,
    deleteMany: deleteAuxiliaryRecords,
  }),
})

export function recordDefinition(doctype) {
  return records[doctype] || Object.freeze({ doctype, list: Object.freeze({}) })
}

// endregion ALL SETUP PAGE DEFINITION
