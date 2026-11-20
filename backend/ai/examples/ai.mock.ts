// Sample requests and responses for the AI helper endpoints, generated from the running service.
// The urgency criteria and routing table used here are FAKE EXAMPLES, not clinical values.
// Everything is simulated.
import type {
  ApiErrorBody, DecisionRequest, DocumentReadContent, DocumentReadRequest, HelperResponse,
  MessageDraftContent, MessageDraftRequest, ReferralTargetContent, ReferralTargetRequest,
  SubmitResponse, SummaryContent, SummaryRequest, Suggestion, UrgencyContent, UrgencyRequest,
} from "./ai.types";

export const documentReadRequest: DocumentReadRequest =
{
  "caseId": "SIM-0001",
  "documentId": "doc-1",
  "documentText": "SIMULATED DOCUMENT. NOT A REAL PATIENT.\n\nPatient ref: SIM-0001\nFacility: Facility A\nDate: 2026-11-02\nTest: PCV - HAEM\nResult: 22\nOrdering clinician: STAFF-014\nSpecialty needed: Haematology\n\nNote: please arrange follow-up.\n"
};

export const documentReadResponse: HelperResponse<DocumentReadContent> =
{
  "status": "suggested",
  "message": "Case details read from the document. Please check each one.",
  "suggestion": {
    "id": "sug_0001",
    "caseId": "SIM-0001",
    "helper": "document_read",
    "content": {
      "fields": {
        "patientRef": "SIM-0001",
        "facility": "Facility A",
        "resultDate": "2026-11-02",
        "testName": "PCV - HAEM",
        "resultValue": "22",
        "orderingClinician": "STAFF-014",
        "specialtyNeeded": "Haematology"
      }
    },
    "sources": [
      {
        "kind": "document",
        "ref": "doc-1",
        "quote": "Patient ref: SIM-0001"
      },
      {
        "kind": "document",
        "ref": "doc-1",
        "quote": "Facility: Facility A"
      },
      {
        "kind": "document",
        "ref": "doc-1",
        "quote": "Date: 2026-11-02"
      },
      {
        "kind": "document",
        "ref": "doc-1",
        "quote": "Test: PCV - HAEM"
      },
      {
        "kind": "document",
        "ref": "doc-1",
        "quote": "Result: 22"
      },
      {
        "kind": "document",
        "ref": "doc-1",
        "quote": "Ordering clinician: STAFF-014"
      },
      {
        "kind": "document",
        "ref": "doc-1",
        "quote": "Specialty needed: Haematology"
      }
    ],
    "completeness": "complete",
    "provider": "rules",
    "notices": [],
    "status": "pending",
    "requestedBy": "STAFF-021",
    "createdAt": "2026-11-10T09:00:00+00:00",
    "decidedBy": null,
    "decidedRole": null,
    "decidedAt": null,
    "decisionNote": null,
    "editedContent": null,
    "simulated": true
  },
  "manualInstruction": null
};

export const messageDraftRequest: MessageDraftRequest =
{
  "caseId": "SIM-0001",
  "language": "en",
  "urgency": "routine",
  "nextStep": "book a confirmatory test",
  "contact": "Facility A clinic, 000-000-0000"
};

export const messageDraftResponse: HelperResponse<MessageDraftContent> =
{
  "status": "suggested",
  "message": "A draft message is ready. A coordinator must approve it before it is sent.",
  "suggestion": {
    "id": "sug_0002",
    "caseId": "SIM-0001",
    "helper": "message_draft",
    "content": {
      "language": "en",
      "text": "Hello,\n\nA screening result from your recent visit needs a follow-up step.\nNext step: book a confirmatory test.\n\nPlease follow the next step above. If you are worried, contact us using the details below.\n\nPlease reply to confirm you received this message. If anything is unclear, tell us and a member of the care team will explain it.\n\nContact: Facility A clinic, 000-000-0000\n\nThis is a simulated message for a demonstration. No real patient is involved.",
      "requestedLanguage": "en",
      "needsTranslationReview": false
    },
    "sources": [
      {
        "kind": "input",
        "ref": "next_step",
        "quote": null
      },
      {
        "kind": "input",
        "ref": "urgency",
        "quote": null
      }
    ],
    "completeness": "complete",
    "provider": "rules",
    "notices": [],
    "status": "pending",
    "requestedBy": "STAFF-021",
    "createdAt": "2026-11-10T09:00:00+00:00",
    "decidedBy": null,
    "decidedRole": null,
    "decidedAt": null,
    "decisionNote": null,
    "editedContent": null,
    "simulated": true
  },
  "manualInstruction": null
};

export const messageDraftOtherLanguageResponse: HelperResponse<MessageDraftContent> =
{
  "status": "suggested",
  "message": "A draft message is ready. A coordinator must approve it before it is sent.",
  "suggestion": {
    "id": "sug_0003",
    "caseId": "SIM-0001",
    "helper": "message_draft",
    "content": {
      "language": "en",
      "text": "Hello,\n\nA screening result from your recent visit needs a follow-up step.\nNext step: visit the clinic.\n\nYour care team has marked this as urgent. Please contact us as soon as you can using the details below.\n\nPlease reply to confirm you received this message. If anything is unclear, tell us and a member of the care team will explain it.\n\nContact: Facility A clinic, 000-000-0000\n\nThis is a simulated message for a demonstration. No real patient is involved.",
      "requestedLanguage": "yo",
      "needsTranslationReview": true
    },
    "sources": [
      {
        "kind": "input",
        "ref": "next_step",
        "quote": null
      },
      {
        "kind": "input",
        "ref": "urgency",
        "quote": null
      }
    ],
    "completeness": "complete",
    "provider": "rules",
    "notices": [
      "Only English is available from the simple template. A reviewed translation is needed before sending."
    ],
    "status": "pending",
    "requestedBy": "STAFF-021",
    "createdAt": "2026-11-10T09:00:00+00:00",
    "decidedBy": null,
    "decidedRole": null,
    "decidedAt": null,
    "decisionNote": null,
    "editedContent": null,
    "simulated": true
  },
  "manualInstruction": null
};

export const urgencyRequest: UrgencyRequest =
{
  "caseId": "SIM-0001",
  "results": [
    {
      "test": "PCV - HAEM",
      "value": 22,
      "unit": "%"
    }
  ]
};

export const urgencyResponse: HelperResponse<UrgencyContent> =
{
  "status": "suggested",
  "message": "An urgency suggestion is ready. A clinician must set the urgency.",
  "suggestion": {
    "id": "sug_0004",
    "caseId": "SIM-0001",
    "helper": "urgency",
    "content": {
      "suggestedUrgency": "urgent",
      "reason": "Suggested: urgent. PCV-1 (PCV - HAEM = 22.0): About haemoglobin 7 g/dL or lower: severe anaemia needing same-day review and a transfusion decision",
      "matchedRules": [
        {
          "ruleId": "PCV-1",
          "test": "PCV - HAEM",
          "value": 22.0,
          "suggestion": "urgent",
          "reason": "About haemoglobin 7 g/dL or lower: severe anaemia needing same-day review and a transfusion decision",
          "specialty": "General medicine (same day), then Haematology",
          "lookFor": "Chest pain, breathlessness, fainting, bleeding, black stools, pregnancy, a child"
        }
      ],
      "notEvaluated": [],
      "specialties": [
        "General medicine (same day), then Haematology"
      ],
      "lookFor": [
        "Chest pain, breathlessness, fainting, bleeding, black stools, pregnancy, a child"
      ],
      "confidential": false
    },
    "sources": [
      {
        "kind": "config",
        "ref": "PCV-1",
        "quote": null
      },
      {
        "kind": "input",
        "ref": "result:PCV - HAEM",
        "quote": null
      }
    ],
    "completeness": "complete",
    "provider": "rules",
    "notices": [
      "These thresholds are DRAFT MOCK values. The lab's own range and flags win. A clinician decides."
    ],
    "status": "pending",
    "requestedBy": "STAFF-014",
    "createdAt": "2026-11-10T09:00:00+00:00",
    "decidedBy": null,
    "decidedRole": null,
    "decidedAt": null,
    "decisionNote": null,
    "editedContent": null,
    "simulated": true
  },
  "manualInstruction": null
};

export const summaryRequest: SummaryRequest =
{
  "caseId": "SIM-0001",
  "events": [
    {
      "eventId": "E1",
      "timestamp": "2026-11-02T09:00:00Z",
      "type": "result_received",
      "actorStaffId": null,
      "text": "Result arrived from Example Facility One (simulated)."
    },
    {
      "eventId": "E2",
      "timestamp": "2026-11-02T10:30:00Z",
      "type": "marked_actionable",
      "actorStaffId": "STAFF-014",
      "text": "Marked actionable, urgency routine."
    },
    {
      "eventId": "E3",
      "timestamp": "2026-11-03T08:15:00Z",
      "type": "patient_notified",
      "actorStaffId": "STAFF-021",
      "text": "Message approved and sent."
    }
  ]
};

export const summaryResponse: HelperResponse<SummaryContent> =
{
  "status": "suggested",
  "message": "A case summary is ready. Each line links to its source event.",
  "suggestion": {
    "id": "sug_0005",
    "caseId": "SIM-0001",
    "helper": "summary",
    "content": {
      "bullets": [
        {
          "text": "2026-11-02 result received: Result arrived from Example Facility One (simulated).",
          "sources": [
            "E1"
          ]
        },
        {
          "text": "2026-11-02 marked actionable (staff STAFF-014): Marked actionable, urgency routine.",
          "sources": [
            "E2"
          ]
        },
        {
          "text": "2026-11-03 patient notified (staff STAFF-021): Message approved and sent.",
          "sources": [
            "E3"
          ]
        }
      ]
    },
    "sources": [
      {
        "kind": "event",
        "ref": "E1",
        "quote": null
      },
      {
        "kind": "event",
        "ref": "E2",
        "quote": null
      },
      {
        "kind": "event",
        "ref": "E3",
        "quote": null
      }
    ],
    "completeness": "complete",
    "provider": "rules",
    "notices": [],
    "status": "pending",
    "requestedBy": "STAFF-014",
    "createdAt": "2026-11-10T09:00:00+00:00",
    "decidedBy": null,
    "decidedRole": null,
    "decidedAt": null,
    "decisionNote": null,
    "editedContent": null,
    "simulated": true
  },
  "manualInstruction": null
};

export const referralTargetRequest: ReferralTargetRequest =
{
  "caseId": "SIM-0001",
  "specialtyNeeded": "Haematology"
};

export const referralTargetResponse: HelperResponse<ReferralTargetContent> =
{
  "status": "suggested",
  "message": "Referral options are ready. The referring clinician chooses.",
  "suggestion": {
    "id": "sug_0006",
    "caseId": "SIM-0001",
    "helper": "referral_target",
    "content": {
      "options": [
        {
          "specialty": "Haematology",
          "service": "Haematology clinic and day unit",
          "primary": {
            "facilityCode": "Facility C",
            "text": "Facility C (mock public hospital): haematology clinic"
          },
          "backup": {
            "facilityCode": "Facility D",
            "text": "Facility D (mock specialist centre): haematology clinic"
          },
          "urgentRecipient": "Facility C haematology on-call pool",
          "urgentRole": "On-call haematology consultant or clinic lead",
          "timeToAcceptUrgent": "2 hours"
        }
      ],
      "reason": "Listed in the routing table (mock facilities). The time to accept is a placeholder."
    },
    "sources": [
      {
        "kind": "config",
        "ref": "routing_row_1",
        "quote": null
      }
    ],
    "completeness": "complete",
    "provider": "rules",
    "notices": [
      "Facility names are MOCK labels for the demo."
    ],
    "status": "pending",
    "requestedBy": "STAFF-014",
    "createdAt": "2026-11-10T09:00:00+00:00",
    "decidedBy": null,
    "decidedRole": null,
    "decidedAt": null,
    "decisionNote": null,
    "editedContent": null,
    "simulated": true
  },
  "manualInstruction": null
};

export const noSuggestionResponse: HelperResponse =
{
  "status": "no_suggestion",
  "message": "No case details could be read from this document. Please enter them by hand.",
  "suggestion": null,
  "manualInstruction": "Enter the case details by hand from the document."
};

export const unavailableResponse: HelperResponse =
{
  "status": "unavailable",
  "message": "No case details could be read from this document. Please enter them by hand.",
  "suggestion": null,
  "manualInstruction": "Enter the case details by hand from the document."
};

export const approveRequest: DecisionRequest =
{
  "decision": "approve",
  "note": "Agreed"
};

export const approveResponse: Suggestion<UrgencyContent> =
{
  "id": "sug_0004",
  "caseId": "SIM-0001",
  "helper": "urgency",
  "content": {
    "suggestedUrgency": "urgent",
    "reason": "Suggested: urgent. PCV-1 (PCV - HAEM = 22.0): About haemoglobin 7 g/dL or lower: severe anaemia needing same-day review and a transfusion decision",
    "matchedRules": [
      {
        "ruleId": "PCV-1",
        "test": "PCV - HAEM",
        "value": 22.0,
        "suggestion": "urgent",
        "reason": "About haemoglobin 7 g/dL or lower: severe anaemia needing same-day review and a transfusion decision",
        "specialty": "General medicine (same day), then Haematology",
        "lookFor": "Chest pain, breathlessness, fainting, bleeding, black stools, pregnancy, a child"
      }
    ],
    "notEvaluated": [],
    "specialties": [
      "General medicine (same day), then Haematology"
    ],
    "lookFor": [
      "Chest pain, breathlessness, fainting, bleeding, black stools, pregnancy, a child"
    ],
    "confidential": false
  },
  "sources": [
    {
      "kind": "config",
      "ref": "PCV-1",
      "quote": null
    },
    {
      "kind": "input",
      "ref": "result:PCV - HAEM",
      "quote": null
    }
  ],
  "completeness": "complete",
  "provider": "rules",
  "notices": [
    "These thresholds are DRAFT MOCK values. The lab's own range and flags win. A clinician decides."
  ],
  "status": "accepted",
  "requestedBy": "STAFF-014",
  "createdAt": "2026-11-10T09:00:00+00:00",
  "decidedBy": "STAFF-014",
  "decidedRole": "referring_clinician",
  "decidedAt": "2026-11-10T09:00:00+00:00",
  "decisionNote": "Agreed",
  "editedContent": null,
  "simulated": true
};

export const editRequest: DecisionRequest =
{
  "decision": "edit",
  "editedContent": {
    "language": "en",
    "text": "Hello, please book your follow-up test at Facility A clinic.",
    "requestedLanguage": "en",
    "needsTranslationReview": false
  },
  "note": "Shortened"
};

export const editResponse: Suggestion<MessageDraftContent> =
{
  "id": "sug_0002",
  "caseId": "SIM-0001",
  "helper": "message_draft",
  "content": {
    "language": "en",
    "text": "Hello,\n\nA screening result from your recent visit needs a follow-up step.\nNext step: book a confirmatory test.\n\nPlease follow the next step above. If you are worried, contact us using the details below.\n\nPlease reply to confirm you received this message. If anything is unclear, tell us and a member of the care team will explain it.\n\nContact: Facility A clinic, 000-000-0000\n\nThis is a simulated message for a demonstration. No real patient is involved.",
    "requestedLanguage": "en",
    "needsTranslationReview": false
  },
  "sources": [
    {
      "kind": "input",
      "ref": "next_step",
      "quote": null
    },
    {
      "kind": "input",
      "ref": "urgency",
      "quote": null
    }
  ],
  "completeness": "complete",
  "provider": "rules",
  "notices": [],
  "status": "edited",
  "requestedBy": "STAFF-021",
  "createdAt": "2026-11-10T09:00:00+00:00",
  "decidedBy": "STAFF-021",
  "decidedRole": "coordinator",
  "decidedAt": "2026-11-10T09:00:00+00:00",
  "decisionNote": "Shortened",
  "editedContent": {
    "language": "en",
    "text": "Hello, please book your follow-up test at Facility A clinic.",
    "requestedLanguage": "en",
    "needsTranslationReview": false
  },
  "simulated": true
};

export const wrongRoleError: ApiErrorBody =
{
  "success": false,
  "error": {
    "code": "ROLE_CANNOT_DECIDE",
    "message": "Your role cannot approve this kind of suggestion.",
    "details": {
      "allowedRoles": [
        "coordinator"
      ]
    }
  }
};

export const listResponse: Suggestion[] =
[
  {
    "id": "sug_0001",
    "caseId": "SIM-0001",
    "helper": "document_read",
    "content": {
      "fields": {
        "patientRef": "SIM-0001",
        "facility": "Facility A",
        "resultDate": "2026-11-02",
        "testName": "PCV - HAEM",
        "resultValue": "22",
        "orderingClinician": "STAFF-014",
        "specialtyNeeded": "Haematology"
      }
    },
    "sources": [
      {
        "kind": "document",
        "ref": "doc-1",
        "quote": "Patient ref: SIM-0001"
      },
      {
        "kind": "document",
        "ref": "doc-1",
        "quote": "Facility: Facility A"
      },
      {
        "kind": "document",
        "ref": "doc-1",
        "quote": "Date: 2026-11-02"
      },
      {
        "kind": "document",
        "ref": "doc-1",
        "quote": "Test: PCV - HAEM"
      },
      {
        "kind": "document",
        "ref": "doc-1",
        "quote": "Result: 22"
      },
      {
        "kind": "document",
        "ref": "doc-1",
        "quote": "Ordering clinician: STAFF-014"
      },
      {
        "kind": "document",
        "ref": "doc-1",
        "quote": "Specialty needed: Haematology"
      }
    ],
    "completeness": "complete",
    "provider": "rules",
    "notices": [],
    "status": "pending",
    "requestedBy": "STAFF-021",
    "createdAt": "2026-11-10T09:00:00+00:00",
    "decidedBy": null,
    "decidedRole": null,
    "decidedAt": null,
    "decisionNote": null,
    "editedContent": null,
    "simulated": true
  },
  {
    "id": "sug_0003",
    "caseId": "SIM-0001",
    "helper": "message_draft",
    "content": {
      "language": "en",
      "text": "Hello,\n\nA screening result from your recent visit needs a follow-up step.\nNext step: visit the clinic.\n\nYour care team has marked this as urgent. Please contact us as soon as you can using the details below.\n\nPlease reply to confirm you received this message. If anything is unclear, tell us and a member of the care team will explain it.\n\nContact: Facility A clinic, 000-000-0000\n\nThis is a simulated message for a demonstration. No real patient is involved.",
      "requestedLanguage": "yo",
      "needsTranslationReview": true
    },
    "sources": [
      {
        "kind": "input",
        "ref": "next_step",
        "quote": null
      },
      {
        "kind": "input",
        "ref": "urgency",
        "quote": null
      }
    ],
    "completeness": "complete",
    "provider": "rules",
    "notices": [
      "Only English is available from the simple template. A reviewed translation is needed before sending."
    ],
    "status": "pending",
    "requestedBy": "STAFF-021",
    "createdAt": "2026-11-10T09:00:00+00:00",
    "decidedBy": null,
    "decidedRole": null,
    "decidedAt": null,
    "decisionNote": null,
    "editedContent": null,
    "simulated": true
  },
  {
    "id": "sug_0005",
    "caseId": "SIM-0001",
    "helper": "summary",
    "content": {
      "bullets": [
        {
          "text": "2026-11-02 result received: Result arrived from Example Facility One (simulated).",
          "sources": [
            "E1"
          ]
        },
        {
          "text": "2026-11-02 marked actionable (staff STAFF-014): Marked actionable, urgency routine.",
          "sources": [
            "E2"
          ]
        },
        {
          "text": "2026-11-03 patient notified (staff STAFF-021): Message approved and sent.",
          "sources": [
            "E3"
          ]
        }
      ]
    },
    "sources": [
      {
        "kind": "event",
        "ref": "E1",
        "quote": null
      },
      {
        "kind": "event",
        "ref": "E2",
        "quote": null
      },
      {
        "kind": "event",
        "ref": "E3",
        "quote": null
      }
    ],
    "completeness": "complete",
    "provider": "rules",
    "notices": [],
    "status": "pending",
    "requestedBy": "STAFF-014",
    "createdAt": "2026-11-10T09:00:00+00:00",
    "decidedBy": null,
    "decidedRole": null,
    "decidedAt": null,
    "decisionNote": null,
    "editedContent": null,
    "simulated": true
  },
  {
    "id": "sug_0006",
    "caseId": "SIM-0001",
    "helper": "referral_target",
    "content": {
      "options": [
        {
          "specialty": "Haematology",
          "service": "Haematology clinic and day unit",
          "primary": {
            "facilityCode": "Facility C",
            "text": "Facility C (mock public hospital): haematology clinic"
          },
          "backup": {
            "facilityCode": "Facility D",
            "text": "Facility D (mock specialist centre): haematology clinic"
          },
          "urgentRecipient": "Facility C haematology on-call pool",
          "urgentRole": "On-call haematology consultant or clinic lead",
          "timeToAcceptUrgent": "2 hours"
        }
      ],
      "reason": "Listed in the routing table (mock facilities). The time to accept is a placeholder."
    },
    "sources": [
      {
        "kind": "config",
        "ref": "routing_row_1",
        "quote": null
      }
    ],
    "completeness": "complete",
    "provider": "rules",
    "notices": [
      "Facility names are MOCK labels for the demo."
    ],
    "status": "pending",
    "requestedBy": "STAFF-014",
    "createdAt": "2026-11-10T09:00:00+00:00",
    "decidedBy": null,
    "decidedRole": null,
    "decidedAt": null,
    "decisionNote": null,
    "editedContent": null,
    "simulated": true
  }
];

export const submitUrgencyResponse: SubmitResponse =
{
  "status": "submitted",
  "message": "The suggestion was sent to the backend. A staff member must approve it there.",
  "backendSuggestion": {
    "id": "01b97145-7d30-4530-b868-41ada22e3039",
    "kind": "URGENCY",
    "status": "PENDING",
    "caseId": "4d67a5a8-38c6-43d5-90fe-856f02c1e4da",
    "payload": {
      "priority": "NORMAL",
      "actionability": "ACTIONABLE",
      "rationale": "Suggested: routine. PCV-3 (PCV - HAEM = 34.0): Mild anaemia. Not urgent on its own Clinician to check: Pregnancy (route to antenatal care), recent bleeding, poor diet. Suggested specialty: Primary care; Obstetrics if pregnant."
    },
    "model": "rules",
    "requiresStaffApproval": true
  },
  "preview": null,
  "notices": [
    "These thresholds are DRAFT MOCK values. The lab's own range and flags win. A clinician decides."
  ],
  "manualInstruction": null
};
