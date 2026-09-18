"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronDown,
  Copy,
  FileText,
  Gavel,
  Loader2,
  MessageCircle,
  Paperclip,
  Send,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { ConvergenceLogo } from "@/components/brand";
import { Badge, Button, Card, ScrollArea, cn } from "@/components/ui";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import {
  acceptRedline,
  downloadRedlinedPDF,
  fetchDemoContract,
  sendChatMessage,
  uploadAndAnalyzeContract,
  type Clause,
  type Contract,
  type LegalSource,
  type Risk,
  type RiskLevel,
} from "@/lib/api";
import { takePendingUploadFile } from "@/lib/pendingUpload";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

type ChatMessage = {
  role: "user" | "assistant";
  text: string;
  citations?: string[];
  sa_statute_citation?: string;
  legal_sources?: LegalSource[];
};

const demo: Contract = {
  contract_id: "",
  filename: "Master Services Agreement — demo",
  text: "",
  clauses: [
    {
      number: "1",
      heading: "Services",
      category: "Services",
      text: "1. Services\nThe Supplier will provide software implementation, support and advisory services described in each Statement of Work.",
    },
    {
      number: "2.1",
      heading: "Warranty",
      category: "Warranty",
      text: "2.1 The Supplier warrants that the Services will materially conform to the Statement of Work for a period of 30 days from delivery.",
    },
    {
      number: "3.1",
      heading: "Client Data",
      category: "Data Protection",
      text: "3.1 The Supplier may process personal information supplied by the Client in connection with the Services. The Supplier will use reasonable security measures and may appoint service providers to assist with processing.",
    },
    {
      number: "4.1",
      heading: "Indemnity",
      category: "Indemnity",
      text: "4.1 The Supplier indemnifies, defends and holds harmless the Client and its affiliates from and against any and all claims, losses, damages, costs and expenses arising out of or relating to the Services, without limitation.",
    },
    {
      number: "5.1",
      heading: "Intellectual Property",
      category: "IP",
      text: "5.1 All background intellectual property used in providing the Services shall transfer to the Client upon creation, without additional compensation to the Supplier.",
    },
    {
      number: "6.1",
      heading: "Termination",
      category: "Termination",
      text: "6.1 Either party may terminate this Agreement on 30 days' written notice.",
    },
    {
      number: "7.1",
      heading: "Governing Law and Disputes",
      category: "Dispute Resolution",
      text: "7.1 This Agreement is governed by the laws of England and Wales. The courts of England and Wales shall have exclusive jurisdiction.",
    },
  ],
  analysis: {
    summary: { red: 3, amber: 2, green: 2, overall_score: "Needs attention" },
    risks: [],
  },
};
demo.analysis.risks = [
  {
    id: "risk-1",
    clause_number: "2.1",
    category: "Warranty",
    risk_level: "RED",
    original_text: demo.clauses[1].text,
    issue:
      "The warranty is shorter than the six-month implied warranty period.",
    sa_law_citation: "Consumer Protection Act 68 of 2008, section 56",
    suggested_redline:
      "The Supplier warrants the Services for at least six months from delivery, subject to fair and reasonable exclusions permitted by the CPA.",
  },
  {
    id: "risk-2",
    clause_number: "4.1",
    category: "Indemnity",
    risk_level: "RED",
    original_text: demo.clauses[3].text,
    issue:
      "This creates an unlimited indemnity for the Supplier and does not allocate liability proportionately.",
    sa_law_citation:
      "Common-law proportionality; Constitution section 34 access to justice",
    suggested_redline:
      "The Supplier's aggregate liability will be capped at fees paid in the preceding 12 months, with uncapped liability limited to fraud, wilful misconduct and confidentiality breaches.",
  },
  {
    id: "risk-3",
    clause_number: "5.1",
    category: "IP",
    risk_level: "RED",
    original_text: demo.clauses[4].text,
    issue:
      "Background IP transfers without compensation, potentially giving away pre-existing SMME assets.",
    sa_law_citation: "Copyright Act 98 of 1978; contractual IP principles",
    suggested_redline:
      "Each party retains its background IP. The Supplier grants the Client a non-exclusive licence to use Supplier background IP only as needed to receive the Services.",
  },
  {
    id: "risk-4",
    clause_number: "3.1",
    category: "Data Protection",
    risk_level: "AMBER",
    original_text: demo.clauses[2].text,
    issue:
      "Personal information may be processed without the required operator terms, instructions and security commitments.",
    sa_law_citation: "POPIA 4 of 2013, section 21",
    suggested_redline:
      "The parties will enter into an Operator data processing addendum covering documented instructions, confidentiality, security safeguards, sub-processors and breach notification.",
  },
  {
    id: "risk-5",
    clause_number: "7.1",
    category: "Dispute Resolution",
    risk_level: "AMBER",
    original_text: demo.clauses[6].text,
    issue:
      "Overseas courts increase cost and enforcement friction for a South African SMME.",
    sa_law_citation: "International Arbitration Act 15 of 2017; AFSA Rules",
    suggested_redline:
      "South African law applies and disputes will be referred to mediation, then AFSA arbitration seated in Johannesburg, in English.",
  },
];

const riskOrder: Record<RiskLevel, number> = { RED: 0, AMBER: 1, GREEN: 2 };
const DEFAULT_SUGGESTIONS = [
  "Is this POPIA compliant?",
  "What is the notice period for termination?",
  "Are there hidden liabilities?",
];

type Phase = "idle" | "processing" | "ready";
type RiskFilter = "ALL" | RiskLevel;

// The backend analyzes a contract in one synchronous call with no incremental
// progress signal, so this is a staged, simulated progress indicator (not a
// literal readout of backend internals) that advances while the request is
// in flight and completes on the real response.
const PROCESSING_STAGES: Array<{ pct: number; label: string }> = [
  { pct: 12, label: "Uploading document..." },
  { pct: 35, label: "Extracting clauses..." },
  { pct: 60, label: "Matching South African statutory rules..." },
  { pct: 85, label: "Drafting redline suggestions..." },
];

export default function Home() {
  const [contract, setContract] = useState<Contract>(demo);
  const [activeTab, setActiveTab] = useState<"risks" | "chat">("risks");
  const [selectedClause, setSelectedClause] = useState<string | null>(null);
  const [accepted, setAccepted] = useState<string[]>([]);
  const [dismissed, setDismissed] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [chat, setChat] = useState<ChatMessage[]>([
    {
      role: "assistant",
      text: "I have reviewed the agreement. Ask me about a clause, a South African legal benchmark, or a practical negotiation move.",
      citations: ["LexiSA review"],
    },
  ]);
  const [suggestions, setSuggestions] = useState<string[]>(DEFAULT_SUGGESTIONS);
  const [isTyping, setIsTyping] = useState(false);
  const [question, setQuestion] = useState("");
  const [exporting, setExporting] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [documentUrl, setDocumentUrl] = useState<string | null>(null);
  const [documentIsPdf, setDocumentIsPdf] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState(0);
  const [progressLabel, setProgressLabel] = useState("");
  const [showCompleteBanner, setShowCompleteBanner] = useState(false);
  const [activeFilter, setActiveFilter] = useState<RiskFilter>("ALL");
  const fileInput = useRef<HTMLInputElement>(null);
  const clauseRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const cancelledRef = useRef(false);
  const initializedRef = useRef(false);
  const visibleRisks = useMemo(
    () =>
      contract.analysis.risks
        .filter((risk) => !dismissed.includes(risk.id))
        .filter((risk) => activeFilter === "ALL" || risk.risk_level === activeFilter)
        .sort((a, b) => riskOrder[a.risk_level] - riskOrder[b.risk_level]),
    [contract.analysis.risks, dismissed, activeFilter],
  );
  const acceptedClauseNumbers = useMemo(
    () =>
      contract.analysis.risks
        .filter((risk) => accepted.includes(risk.id))
        .map((risk) => risk.clause_number),
    [contract.analysis.risks, accepted],
  );
  // Live counts of actual issues raised, not the backend's static summary —
  // otherwise dismissing a risk (or filtering) leaves the badges stale, and
  // "Low" previously reused the "clauses with no risk at all" count instead
  // of counting actual GREEN-severity issues (of which there currently are
  // none in the SA rules matrix), which didn't match what clicking the
  // filter actually showed.
  const liveCounts = useMemo(() => {
    const active = contract.analysis.risks.filter((risk) => !dismissed.includes(risk.id));
    return {
      red: active.filter((risk) => risk.risk_level === "RED").length,
      amber: active.filter((risk) => risk.risk_level === "AMBER").length,
      green: active.filter((risk) => risk.risk_level === "GREEN").length,
    };
  }, [contract.analysis.risks, dismissed]);

  useEffect(() => {
    // React 18 Strict Mode (Next.js dev default) mounts, cleans up, and
    // re-mounts this effect once to surface cleanup bugs. Without this guard
    // that second invocation would find takePendingUploadFile() already
    // consumed and fall through to loading the demo contract, overwriting
    // the real upload once it resolves. cancelledRef is reset on every
    // invocation (including the synthetic one) so it still correctly blocks
    // state updates after a genuine unmount.
    cancelledRef.current = false;
    if (!initializedRef.current) {
      initializedRef.current = true;
      const pendingFile = takePendingUploadFile();
      if (pendingFile) {
        processFile(pendingFile);
      } else {
        fetchDemoContract()
          .then(setContract)
          .catch(() => undefined);
      }
    }
    return () => {
      cancelledRef.current = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    return () => {
      if (documentUrl) URL.revokeObjectURL(documentUrl);
    };
  }, [documentUrl]);

  function jumpToClause(number: string) {
    setSelectedClause(number);
    clauseRefs.current[number]?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  }
  function processFile(file: File) {
    setPhase("processing");
    setProgress(0);
    setProgressLabel(PROCESSING_STAGES[0].label);
    setShowCompleteBanner(false);
    setUploadError("");
    setDocumentUrl(URL.createObjectURL(file));
    setDocumentIsPdf(file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"));

    let stageIndex = 0;
    const timer = setInterval(() => {
      if (stageIndex >= PROCESSING_STAGES.length) return;
      setProgress(PROCESSING_STAGES[stageIndex].pct);
      setProgressLabel(PROCESSING_STAGES[stageIndex].label);
      stageIndex += 1;
    }, 650);

    uploadAndAnalyzeContract(file)
      .then((uploadedContract) => {
        clearInterval(timer);
        if (cancelledRef.current) return;
        setProgress(100);
        setProgressLabel("Review complete");
        setContract(uploadedContract);
        setAccepted([]);
        setDismissed([]);
        setSelectedClause(null);
        setSuggestions(DEFAULT_SUGGESTIONS);
        setActiveTab("risks");
        setActiveFilter("ALL");
        setPhase("ready");
        setShowCompleteBanner(true);
        window.setTimeout(() => {
          if (!cancelledRef.current) setShowCompleteBanner(false);
        }, 6000);
      })
      .catch(() => {
        clearInterval(timer);
        if (cancelledRef.current) return;
        setPhase("ready");
        setUploadError("Upload failed. Check that the FastAPI backend is running, then try again.");
      });
  }
  function handleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    processFile(file);
  }
  async function ask(query = question) {
    if (!query.trim() || !contract.contract_id) return;
    setQuestion("");
    setChat((messages) => [...messages, { role: "user", text: query }]);
    setIsTyping(true);
    try {
      const data = await sendChatMessage(contract.contract_id, query);
      setChat((messages) => [
        ...messages,
        {
          role: "assistant",
          text: data.answer,
          citations: data.cited_clause_numbers,
          sa_statute_citation: data.sa_statute_citation,
          legal_sources: data.legal_sources,
        },
      ]);
      if (data.suggested_followups.length) setSuggestions(data.suggested_followups);
    } catch {
      setChat((messages) => [
        ...messages,
        {
          role: "assistant",
          text: "The local assistant is offline. Review the highlighted clauses for the current risk picture.",
        },
      ]);
    }
    setIsTyping(false);
  }
  async function handleAcceptRedline(risk: Risk) {
    if (!contract.contract_id || accepted.includes(risk.id)) return;
    try {
      const redline = await acceptRedline(contract.contract_id, risk.clause_number);
      setContract((current) => ({
        ...current,
        clauses: current.clauses.map((clause) =>
          clause.number === risk.clause_number ? { ...clause, text: redline.redlined_text } : clause,
        ),
      }));
      setAccepted((items) => [...items, risk.id]);
    } catch {
      setUploadError("Could not save the redline. Check that the FastAPI backend is running.");
    }
  }
  async function handleExportPdf() {
    if (!contract.contract_id || exporting) return;
    setExporting(true);
    try {
      const safeName = contract.filename.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
      await downloadRedlinedPDF(contract.contract_id, `${safeName}-redlined.pdf`);
    } catch {
      setUploadError("Could not export the redlined PDF. Check that the FastAPI backend is running.");
    }
    setExporting(false);
  }
  const counts = liveCounts;

  return (
    <main className="lexisa-app min-h-screen bg-[#f7f7f5]">
      <header className="flex min-h-[76px] flex-wrap items-center justify-between gap-4 border-b border-[#d4d5d7] bg-[#17181c] px-5 py-4 lg:px-8">
        <div className="flex items-center gap-4">
          <Link href="/" aria-label="Back to home">
            <ConvergenceLogo />
          </Link>
          <div className="hidden h-8 w-px bg-[#d4d5d7] sm:block" />
          <div>
            <div className="font-display text-xl font-bold tracking-[-0.03em] text-[#202126]">
              LexiSA
            </div>
            <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-[#6b6d73]">
              Contract intelligence
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.docx"
            onChange={handleUpload}
            className="hidden"
          />
          <Button
            onClick={() => fileInput.current?.click()}
            disabled={phase === "processing"}
            className="bg-[#11262a] text-white hover:bg-[#25464b] disabled:opacity-60"
          >
            {phase === "processing" ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Upload size={16} />
            )}{" "}
            Upload document
          </Button>
          {uploadError && (
            <span
              role="alert"
              className="hidden text-xs font-semibold text-[#ff6970] sm:inline"
            >
              {uploadError}
            </span>
          )}
          <Button
            onClick={handleExportPdf}
            disabled={!contract.contract_id || exporting}
            className="hidden border border-[#ccd6d1] bg-white text-[#11262a] hover:bg-[#edf2ed] disabled:opacity-50 md:inline-flex"
          >
            {exporting ? <Loader2 size={16} className="animate-spin" /> : <ArrowUpRight size={16} />} Export redlined PDF
          </Button>
          <Button className="hidden bg-[#f3a62f] text-[#11262a] hover:bg-[#e8a02e] lg:inline-flex">
            <Gavel size={16} /> Request attorney review
          </Button>
        </div>
      </header>
      {phase === "processing" && (
        <div className="flex items-center gap-2 border-b border-[#0d3a86] bg-[#0b469d] px-5 py-2.5 text-sm font-semibold text-white lg:px-8">
          <Loader2 size={15} className="animate-spin" /> Processing {contract.filename || "your document"}
          <span className="opacity-80">— {progressLabel}</span>
        </div>
      )}
      {showCompleteBanner && (
        <div className="flex items-center gap-2 border-b border-[#1f5f4e] bg-[#22785f] px-5 py-2.5 text-sm font-semibold text-white lg:px-8">
          <CheckCircle2 size={15} /> Review complete
          <span className="opacity-90">
            — {counts.red + counts.amber} item{counts.red + counts.amber === 1 ? "" : "s"} need your attention.
          </span>
        </div>
      )}
      <section className="flex flex-wrap items-center justify-between gap-3 border-b border-[#d8ded8] bg-[#eef2ec] px-5 py-3 lg:px-8">
        <div className="flex items-center gap-2 text-xs text-[#62716d]">
          <FileText size={15} />
          <span className="max-w-[260px] truncate font-semibold text-[#11262a]">
            {contract.filename}
          </span>
          <span>•</span>
          <span>Reviewed just now</span>
        </div>
        <div className="flex items-center gap-2">
          <Metric
            color="bg-[#ec6855]"
            label="High"
            value={counts.red}
            active={activeFilter === "RED"}
            onClick={() => setActiveFilter((current) => (current === "RED" ? "ALL" : "RED"))}
          />
          <Metric
            color="bg-[#e6b94f]"
            label="Medium"
            value={counts.amber}
            active={activeFilter === "AMBER"}
            onClick={() => setActiveFilter((current) => (current === "AMBER" ? "ALL" : "AMBER"))}
          />
          <Metric
            color="bg-[#a4d5c8]"
            label="Low"
            value={counts.green}
            active={activeFilter === "GREEN"}
            onClick={() => setActiveFilter((current) => (current === "GREEN" ? "ALL" : "GREEN"))}
          />
        </div>
      </section>
      <div className="grid min-h-[calc(100vh-129px)] lg:grid-cols-[minmax(0,1.05fr)_minmax(440px,0.95fr)]">
        <section className="border-r border-[#d8ded8] bg-[#eeeae1] p-5 lg:p-8">
          <div className="mx-auto max-w-3xl">
            <div className="mb-6 flex items-end justify-between">
              <div>
                <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.2em] text-[#ad7657]">
                  Document viewer
                </p>
                <h1 className="font-display text-2xl font-bold tracking-[-0.04em]">
                  {contract.filename.replace(" — demo", "")}
                </h1>
              </div>
              <Badge className="border border-[#cbd5cf] bg-[#f8f6ef] text-[#6b7773]">
                {contract.clauses.length} sections
              </Badge>
            </div>
            <ScrollArea className="document-scroll max-h-[calc(100vh-245px)] pr-3">
              {documentUrl && documentIsPdf ? (
                <PdfDocumentViewer
                  url={documentUrl}
                  risks={contract.analysis.risks}
                  selectedClause={selectedClause}
                  acceptedClauseNumbers={acceptedClauseNumbers}
                />
              ) : (
                <div className="space-y-1 rounded-xl border border-[#ddd8ce] bg-[#f8f6ef] p-6 shadow-[0_12px_30px_rgba(17,38,42,0.04)]">
                  {contract.clauses.map((clause) => {
                    const risk = contract.analysis.risks.find(
                      (item) => item.clause_number === clause.number,
                    );
                    const isAccepted = risk && accepted.includes(risk.id);
                    return (
                      <div
                        key={clause.number}
                        ref={(element) => {
                          clauseRefs.current[clause.number] = element;
                        }}
                        className={cn(
                          "relative scroll-mt-10 border-b border-[#e5e0d7] py-5 transition-colors last:border-0",
                          selectedClause === clause.number &&
                            "rounded-lg bg-[#fff5d9] px-3",
                          isAccepted && "opacity-60",
                        )}
                      >
                        <div className="mb-2 flex items-center gap-2">
                          <span className="font-display text-sm font-bold text-[#ad7657]">
                            {clause.number}
                          </span>
                          <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#8c9993]">
                            {clause.category}
                          </span>
                          {risk && (
                            <span
                              className={cn(
                                "ml-auto h-2 w-2 rounded-full",
                                risk.risk_level === "RED"
                                  ? "bg-[#ec6855]"
                                  : "bg-[#e6b94f]",
                              )}
                            />
                          )}
                        </div>
                        <p
                          className={cn(
                            "whitespace-pre-line text-sm leading-7 text-[#334b4b]",
                            risk?.risk_level === "RED" &&
                              "border-l-2 border-[#ec6855] pl-3",
                            risk?.risk_level === "AMBER" &&
                              "border-l-2 border-[#e6b94f] pl-3",
                          )}
                        >
                          {clause.text}
                        </p>
                        {isAccepted && (
                          <span className="mt-3 inline-flex items-center gap-1 text-xs font-bold text-[#3d786d]">
                            <Check size={14} /> Redline accepted
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </ScrollArea>
          </div>
        </section>
        <section className="bg-[#fbfaf7] p-5 lg:p-8">
          <div className="flex h-full min-h-[620px] flex-col">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.2em] text-[#ad7657]">
                  Workbench
                </p>
                <h2 className="font-display text-2xl font-bold tracking-[-0.04em]">
                  What needs your eye?
                </h2>
              </div>
              <Badge className="bg-[#eef2ec] text-[#54726a]">
                <Sparkles size={12} className="mr-1" /> Gemini ready
              </Badge>
            </div>
            {phase === "processing" ? (
              <ProcessingPane progress={progress} label={progressLabel} />
            ) : (
            <>
            <div className="mb-5 flex border-b border-[#d8ded8]">
              <button
                onClick={() => setActiveTab("risks")}
                className={cn(
                  "border-b-2 px-1 pb-3 text-sm font-bold",
                  activeTab === "risks"
                    ? "border-[#ad7657] text-[#11262a]"
                    : "border-transparent text-[#84908b]",
                )}
              >
                Risk analysis matrix{" "}
                <span className="ml-1 text-xs text-[#ad7657]">
                  {visibleRisks.length}
                </span>
              </button>
              <button
                onClick={() => setActiveTab("chat")}
                className={cn(
                  "ml-6 border-b-2 px-1 pb-3 text-sm font-bold",
                  activeTab === "chat"
                    ? "border-[#ad7657] text-[#11262a]"
                    : "border-transparent text-[#84908b]",
                )}
              >
                <MessageCircle size={15} className="mr-1 inline" /> AI legal
                assistant
              </button>
            </div>
            {activeTab === "risks" ? (
              <ScrollArea className="chat-scroll flex-1 pr-1">
                {visibleRisks.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-[#d8ded8] p-6 text-center text-sm text-[#84908b]">
                    {activeFilter === "ALL"
                      ? "No concerns to show — everything is either resolved or dismissed."
                      : `No ${activeFilter === "RED" ? "high" : activeFilter === "AMBER" ? "medium" : "low"}-risk items match the current filter.`}
                  </div>
                ) : (
                  <div className="space-y-3">
                    {visibleRisks.map((risk, index) => (
                      <RiskCard
                        key={risk.id}
                        risk={risk}
                        index={index}
                        expanded={expanded === risk.id}
                        accepted={accepted.includes(risk.id)}
                        onExpand={() =>
                          setExpanded(expanded === risk.id ? null : risk.id)
                        }
                        onJump={() => jumpToClause(risk.clause_number)}
                        onAccept={() => handleAcceptRedline(risk)}
                        onDismiss={() =>
                          setDismissed((items) => [...items, risk.id])
                        }
                      />
                    ))}
                  </div>
                )}
              </ScrollArea>
            ) : (
              <ChatView
                messages={chat}
                question={question}
                setQuestion={setQuestion}
                onAsk={ask}
                onJump={jumpToClause}
                suggestions={suggestions}
                isTyping={isTyping}
              />
            )}
            </>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

function PdfDocumentViewer({
  url,
  risks,
  selectedClause,
  acceptedClauseNumbers,
}: {
  url: string;
  risks: Risk[];
  selectedClause: string | null;
  acceptedClauseNumbers: string[];
}) {
  const [pageCount, setPageCount] = useState(0);
  const viewerRef = useRef<HTMLDivElement>(null);

  function highlightTextLayer() {
    const spans = Array.from(
      viewerRef.current?.querySelectorAll<HTMLSpanElement>(
        ".react-pdf__Page__textContent span",
      ) ?? [],
    );
    const normalize = (value: string) =>
      value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
    const spanRanges: Array<{ span: HTMLSpanElement; start: number; end: number }> = [];
    let documentText = "";
    spans.forEach((span) => {
      const text = normalize(span.textContent ?? "");
      const start = documentText.length;
      documentText += `${documentText ? " " : ""}${text}`;
      spanRanges.push({ span, start, end: documentText.length });
      span.classList.remove("pdf-risk-red", "pdf-risk-amber", "pdf-risk-accepted", "pdf-risk-selected");
    });
    risks.forEach((risk) => {
      const clauseText = normalize(risk.original_text);
      const matchStart = documentText.indexOf(clauseText);
      if (matchStart < 0) return;
      const matchEnd = matchStart + clauseText.length;
      const isAccepted = acceptedClauseNumbers.includes(risk.clause_number);
      const highlightClass = isAccepted
        ? "pdf-risk-accepted"
        : risk.risk_level === "RED"
          ? "pdf-risk-red"
          : "pdf-risk-amber";
      spanRanges.forEach(({ span, start, end }) => {
        if (end <= matchStart || start >= matchEnd) return;
        span.classList.add(highlightClass);
        if (risk.clause_number === selectedClause) {
          span.classList.add("pdf-risk-selected");
        }
      });
    });
  }

  useEffect(() => {
    highlightTextLayer();
  }, [selectedClause, risks, acceptedClauseNumbers]);

  // Scrolls the highlighted clause into view whenever the selection changes
  // (a risk card's "Clause X.X" link, or a chat citation). Runs as a separate
  // effect so accepting a redline or the highlight pass re-running doesn't
  // also cause an unwanted scroll jump.
  useEffect(() => {
    if (!selectedClause) return;
    const target = viewerRef.current?.querySelector(".pdf-risk-selected");
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedClause]);

  return (
    <div
      ref={viewerRef}
      className="document-scroll max-h-[calc(100vh-245px)] space-y-5 overflow-auto rounded-xl border border-[#ddd8ce] bg-[#202126] p-4 shadow-[0_12px_30px_rgba(0,0,0,0.25)]"
    >
      <Document
        file={url}
        onLoadSuccess={({ numPages }) => setPageCount(numPages)}
        loading={<div className="p-8 text-sm text-white">Loading PDF...</div>}
        error={<div className="p-8 text-sm text-[#ff6970]">Unable to render this PDF.</div>}
      >
        {Array.from({ length: pageCount }, (_, index) => (
          <Page
            key={`pdf-page-${index + 1}`}
            pageNumber={index + 1}
            width={Math.min(760, typeof window === "undefined" ? 760 : window.innerWidth * 0.46)}
            renderTextLayer
            renderAnnotationLayer
            onRenderTextLayerSuccess={highlightTextLayer}
          />
        ))}
      </Document>
    </div>
  );
}

function ProcessingPane({ progress, label }: { progress: number; label: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed border-[#d8ded8] bg-[#f8f6ef] p-10 text-center">
      <Loader2 size={28} className="mb-4 animate-spin text-[#ad7657]" />
      <p className="font-display text-lg font-bold tracking-[-0.02em] text-[#11262a]">
        Reviewing your document
      </p>
      <p className="mt-1 text-sm text-[#7c8984]">{label}</p>
      <div className="mt-5 h-2 w-full max-w-xs overflow-hidden rounded-full bg-[#e5e0d7]">
        <div
          className="h-full rounded-full bg-[#ad7657] transition-[width] duration-500 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>
      <p className="mt-2 text-xs font-semibold text-[#9aa39e]">{progress}%</p>
    </div>
  );
}
function Metric({
  color,
  label,
  value,
  active,
  onClick,
}: {
  color: string;
  label: string;
  value: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-bold transition-colors",
        active
          ? "border-[#ad7657] bg-[#ad7657] text-[#1f140d]"
          : "border-[#d6ded8] bg-[#fbfaf7] text-[#11262a] hover:border-[#ad7657]",
      )}
    >
      <span className={cn("h-2 w-2 rounded-full", active ? "bg-[#1f140d]" : color)} />
      {value}
      <span className={cn("hidden sm:inline font-medium", active ? "text-[#1f140d]/80" : "text-[#7c8984]")}>
        {label}
      </span>
    </button>
  );
}
function RiskCard({
  risk,
  index,
  expanded,
  accepted,
  onExpand,
  onJump,
  onAccept,
  onDismiss,
}: {
  risk: Risk;
  index: number;
  expanded: boolean;
  accepted: boolean;
  onExpand: () => void;
  onJump: () => void;
  onAccept: () => void;
  onDismiss: () => void;
}) {
  const red = risk.risk_level === "RED";
  return (
    <Card
      className={cn(
        "animate-rise overflow-hidden border-l-4",
        red ? "border-l-[#ec6855]" : "border-l-[#e6b94f]",
        `delay-${Math.min(index + 1, 3)}`,
        accepted && "opacity-60",
      )}
    >
      <div className="p-4">
        <div className="mb-3 flex items-center gap-2">
          <Badge
            className={
              red
                ? "bg-[#fbe3de] text-[#b34135]"
                : "bg-[#fff3cf] text-[#92701c]"
            }
          >
            {red ? "High risk" : "Medium"}
          </Badge>
          <button
            onClick={onJump}
            className="text-xs font-bold text-[#62716d] underline decoration-[#d5ddd7] underline-offset-2"
          >
            Clause {risk.clause_number}
          </button>
          <button
            onClick={onDismiss}
            aria-label="Dismiss risk"
            className="ml-auto text-[#98a49f] hover:text-[#11262a]"
          >
            <X size={16} />
          </button>
        </div>
        <div className="mb-1 flex items-center justify-between">
          <h3 className="font-display font-bold">{risk.category}</h3>
          {accepted && (
            <span className="flex items-center gap-1 text-xs font-bold text-[#3d786d]">
              <Check size={14} /> Accepted
            </span>
          )}
        </div>
        <p className="text-sm leading-6 text-[#53635e]">{risk.issue}</p>
        <button
          onClick={onExpand}
          className="mt-3 flex w-full items-center justify-between border-t border-[#edf0eb] pt-3 text-xs font-bold text-[#ad7657]"
        >
          <span>SA: {risk.sa_law_citation}</span>
          <ChevronDown
            size={15}
            className={cn("transition-transform", expanded && "rotate-180")}
          />
        </button>
        {expanded && (
          <div className="mt-3 rounded-lg bg-[#f5f6f1] p-3 text-sm leading-6 text-[#38504d]">
            <p>{risk.suggested_redline}</p>
            <div className="mt-3 flex gap-2">
              <Button
                onClick={onAccept}
                disabled={accepted}
                className="bg-[#11262a] px-2.5 py-1.5 text-xs text-white hover:bg-[#25464b] disabled:opacity-60"
              >
                <Check size={14} />{" "}
                {accepted ? "Accepted" : "Accept redline"}
              </Button>
              <Button
                onClick={() =>
                  navigator.clipboard?.writeText(risk.suggested_redline)
                }
                className="border border-[#ccd6d1] bg-white px-2.5 py-1.5 text-xs hover:bg-[#edf2ed]"
              >
                <Copy size={14} /> Copy wording
              </Button>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
function ChatView({
  messages,
  question,
  setQuestion,
  onAsk,
  onJump,
  suggestions,
  isTyping,
}: {
  messages: ChatMessage[];
  question: string;
  setQuestion: (value: string) => void;
  onAsk: (query?: string) => void;
  onJump: (clause: string) => void;
  suggestions: string[];
  isTyping: boolean;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ScrollArea className="chat-scroll mb-4 flex-1 pr-2">
        <div className="space-y-4">
          {messages.map((message, index) => (
            <div
              key={index}
              className={cn(
                "max-w-[92%] rounded-xl p-3 text-sm leading-6",
                message.role === "user"
                  ? "ml-auto bg-[#11262a] text-white"
                  : "bg-[#eef2ec] text-[#38504d]",
              )}
            >
              <div>{message.text}</div>
              {message.citations?.map((citation) => (
                <button
                  key={citation}
                  onClick={() => onJump(citation.replace(/[^0-9.]/g, ""))}
                  className="mt-2 mr-1 inline-flex items-center gap-1 rounded-full border border-[#cbd8d0] bg-white px-2 py-1 text-[10px] font-bold text-[#55736b]"
                >
                  <FileText size={11} /> Clause {citation}
                </button>
              ))}
              {message.sa_statute_citation && (
                <span className="mt-2 mr-1 inline-flex items-center gap-1 rounded-full border border-[#cbd8d0] bg-white px-2 py-1 text-[10px] font-bold text-[#55736b]">
                  <Gavel size={11} /> {message.sa_statute_citation}
                </span>
              )}
              {message.legal_sources?.map(
                (source) =>
                  source.url && (
                    <a
                      key={source.url}
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2 mr-1 inline-flex items-center gap-1 rounded-full border border-[#cbd8d0] bg-white px-2 py-1 text-[10px] font-bold text-[#55736b]"
                    >
                      <Gavel size={11} /> Laws.Africa: {source.title}
                    </a>
                  ),
              )}
            </div>
          ))}
          {isTyping && (
            <div className="max-w-[92%] rounded-xl bg-[#eef2ec] p-3 text-sm text-[#38504d]">
              <span className="inline-flex items-center gap-1">
                <Loader2 size={14} className="animate-spin" /> LexiSA is thinking...
              </span>
            </div>
          )}
        </div>
      </ScrollArea>
      <div className="mb-3 flex flex-wrap gap-2">
        {suggestions.map((suggestion) => (
          <button
            key={suggestion}
            onClick={() => onAsk(suggestion)}
            className="rounded-full border border-[#ccd6d1] bg-white px-2.5 py-1.5 text-left text-[11px] font-semibold text-[#62716d] hover:border-[#ad7657] hover:text-[#ad7657]"
          >
            {suggestion}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2 rounded-xl border border-[#ccd6d1] bg-white p-2">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && onAsk()}
          placeholder="Ask about this agreement..."
          disabled={isTyping}
          className="min-w-0 flex-1 bg-transparent px-2 text-sm outline-none placeholder:text-[#a1aba6] disabled:opacity-60"
        />
        <Button
          onClick={() => onAsk()}
          disabled={isTyping}
          aria-label="Send question"
          className="h-9 w-9 rounded-lg bg-[#f3a62f] p-0 text-[#11262a] hover:bg-[#e8a02e] disabled:opacity-60"
        >
          {isTyping ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
        </Button>
      </div>
    </div>
  );
}
