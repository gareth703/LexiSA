"use client";

import { ArrowLeft, Gavel, Loader2, Scale, Send } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { cn } from "@/components/ui";
import { sendLegalQuestion, type LegalSource } from "@/lib/api";

type Message = {
  role: "user" | "assistant";
  text: string;
  sa_statute_citation?: string;
  legal_sources?: LegalSource[];
};

const DEFAULT_SUGGESTIONS = [
  "Is my business POPIA compliant?",
  "What warranty does the CPA require?",
  "How does AFSA arbitration work?",
];

export default function AskPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "Ask a plain-language question about South African law — POPIA, the CPA, the BCEA, AFSA arbitration, or B-BBEE compliance.",
    },
  ]);
  const [suggestions, setSuggestions] = useState<string[]>(DEFAULT_SUGGESTIONS);
  const [question, setQuestion] = useState("");
  const [isTyping, setIsTyping] = useState(false);

  async function ask(query = question) {
    if (!query.trim() || isTyping) return;
    setQuestion("");
    setMessages((current) => [...current, { role: "user", text: query }]);
    setIsTyping(true);
    try {
      const data = await sendLegalQuestion(query);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: data.answer,
          sa_statute_citation: data.sa_statute_citation,
          legal_sources: data.legal_sources,
        },
      ]);
      if (data.suggested_followups.length) setSuggestions(data.suggested_followups);
    } catch {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: "The legal assistant is offline. Check that the FastAPI backend is running, then try again.",
        },
      ]);
    }
    setIsTyping(false);
  }

  return (
    <main className="flex min-h-screen flex-col bg-[#111216] text-[#f7f7f5]">
      <header className="flex items-center gap-4 border-b border-[#22232a] px-6 py-5 lg:px-10">
        <Link
          href="/"
          className="flex items-center gap-2 text-sm font-semibold text-[#9ea1a8] transition-colors hover:text-white"
        >
          <ArrowLeft size={16} /> Home
        </Link>
        <div className="h-6 w-px bg-[#2c2d33]" />
        <div className="flex items-center gap-2">
          <Scale size={18} className="text-[#6d91c6]" />
          <span className="font-display text-lg font-bold tracking-[-0.02em] text-white">
            Query the South African Law
          </span>
        </div>
      </header>

      <section className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-5 py-8">
        <div className="flex-1 space-y-4 overflow-y-auto pb-4">
          {messages.map((message, index) => (
            <div
              key={index}
              className={cn(
                "max-w-[88%] rounded-xl p-3.5 text-sm leading-6",
                message.role === "user"
                  ? "ml-auto bg-[#0b469d] text-white"
                  : "bg-[#17181c] text-[#d4d6db]",
              )}
            >
              <div>{message.text}</div>
              {message.sa_statute_citation && (
                <span className="mt-2 mr-1 inline-flex items-center gap-1 rounded-full border border-[#2c2d33] bg-[#111216] px-2 py-1 text-[10px] font-bold text-[#6d91c6]">
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
                      className="mt-2 mr-1 inline-flex items-center gap-1 rounded-full border border-[#2c2d33] bg-[#111216] px-2 py-1 text-[10px] font-bold text-[#6d91c6]"
                    >
                      <Gavel size={11} /> Laws.Africa: {source.title}
                    </a>
                  ),
              )}
            </div>
          ))}
          {isTyping && (
            <div className="max-w-[88%] rounded-xl bg-[#17181c] p-3.5 text-sm text-[#d4d6db]">
              <span className="inline-flex items-center gap-1">
                <Loader2 size={14} className="animate-spin" /> Checking South African legislation...
              </span>
            </div>
          )}
        </div>

        <div className="mb-3 flex flex-wrap gap-2">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              onClick={() => ask(suggestion)}
              className="rounded-full border border-[#2c2d33] bg-[#17181c] px-2.5 py-1.5 text-left text-[11px] font-semibold text-[#9ea1a8] hover:border-[#6d91c6] hover:text-[#6d91c6]"
            >
              {suggestion}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 rounded-xl border border-[#2c2d33] bg-[#17181c] p-2">
          <input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && ask()}
            placeholder="Ask about South African law..."
            disabled={isTyping}
            className="min-w-0 flex-1 bg-transparent px-2 text-sm text-white outline-none placeholder:text-[#6d7480] disabled:opacity-60"
          />
          <button
            onClick={() => ask()}
            disabled={isTyping}
            aria-label="Send question"
            className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#0b469d] text-white transition-colors hover:bg-[#0d54ba] disabled:opacity-60"
          >
            {isTyping ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
      </section>

      <footer className="px-6 pb-6 text-center text-[11px] text-[#5c5e66]">
        General information, not legal advice.
      </footer>
    </main>
  );
}
