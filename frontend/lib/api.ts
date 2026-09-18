/** LexiSA FastAPI client: contract analysis, RAG chat, redlines, and PDF export. */

export type RiskLevel = "RED" | "AMBER" | "GREEN";

export type Clause = {
  number: string;
  heading: string;
  text: string;
  category: string;
};

export type Risk = {
  id: string;
  clause_number: string;
  category: string;
  risk_level: RiskLevel;
  original_text: string;
  issue: string;
  sa_law_citation: string;
  suggested_redline: string;
};

export type Contract = {
  contract_id: string;
  filename: string;
  text: string;
  clauses: Clause[];
  analysis: {
    summary: { red: number; amber: number; green: number; overall_score: string };
    risks: Risk[];
  };
};

export type LegalSource = { title: string; url: string; text: string };

export type RagChatResponse = {
  answer: string;
  cited_clause_numbers: string[];
  sa_statute_citation: string;
  suggested_followups: string[];
  legal_sources: LegalSource[];
};

export type RedlineStatus = "ACCEPTED" | "REJECTED" | "PENDING";

export type RedlineRecord = {
  id: string;
  contract_id: string;
  clause_number: string;
  original_text: string;
  redlined_text: string;
  status: RedlineStatus;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function requestJson<T>(path: string, init?: RequestInit, action = "Request"): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    throw new Error(`${action} failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function jsonBody(payload: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  };
}

export function fetchDemoContract(): Promise<Contract> {
  return requestJson<Contract>("/api/v1/demo-contract", undefined, "Load demo contract");
}

export function fetchContract(contractId: string): Promise<Contract> {
  return requestJson<Contract>(`/api/v1/contracts/${contractId}`, undefined, "Load contract");
}

export function uploadAndAnalyzeContract(file: File): Promise<Contract> {
  const body = new FormData();
  body.append("file", file);
  return requestJson<Contract>("/api/v1/upload-contract", { method: "POST", body }, "Upload contract");
}

export function sendChatMessage(contractId: string, query: string): Promise<RagChatResponse> {
  return requestJson<RagChatResponse>(
    `/api/v1/contracts/${contractId}/chat`,
    jsonBody({ query }),
    "Send chat message",
  );
}

export function acceptRedline(contractId: string, clauseNumber: string): Promise<RedlineRecord> {
  return requestJson<RedlineRecord>(
    "/api/v1/redlines/accept",
    jsonBody({ contract_id: contractId, clause_number: clauseNumber }),
    "Accept redline",
  );
}

export function submitCustomRedline(contractId: string, clauseNumber: string, customText: string): Promise<RedlineRecord> {
  return requestJson<RedlineRecord>(
    "/api/v1/redlines/custom",
    jsonBody({ contract_id: contractId, clause_number: clauseNumber, custom_text: customText }),
    "Submit custom redline",
  );
}

export async function downloadRedlinedPDF(contractId: string, filename = "lexisa-redlined-contract.pdf"): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/contracts/${contractId}/export-pdf`);
  if (!response.ok) {
    throw new Error(`Export PDF failed with status ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
