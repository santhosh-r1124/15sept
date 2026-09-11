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

/** Returned in place of a generated answer when the classifier flags is_out_of_scope. */
export const OUT_OF_SCOPE_MESSAGE =
  'I can only help with general Indian legal information, document guidance, ' +
  'and connecting you with an advocate. Could you rephrase your question as a ' +
  'legal question, or tell me what legal topic you need help with?';
