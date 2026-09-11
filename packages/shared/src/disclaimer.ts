/**
 * Mandatory disclaimer for the public chatbot (FRD §14).
 * Must be shown verbatim wherever AI-generated legal information is displayed.
 */
export const MANDATORY_DISCLAIMER =
  'This AI provides general legal information and document guidance based on ' +
  'available legal sources. It does not constitute legal advice, does not ' +
  'establish an advocate-client relationship, and should not replace advice ' +
  'from a qualified legal professional. Laws and procedures may vary by ' +
  'jurisdiction and circumstances.';

/** Shown when retrieval cannot find sufficient grounded evidence (roadmap Phase 4). */
export const INSUFFICIENT_EVIDENCE_MESSAGE =
  "I couldn't find sufficient verified information in the available legal " +
  'sources to answer this reliably.';

/** Appended to responses for HIGH/CRITICAL risk queries (FRD §13). */
export const ADVOCATE_RECOMMENDATION_MESSAGE =
  'This matter may require advice from a qualified advocate.';
