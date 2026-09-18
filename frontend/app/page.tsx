"use client";

import { ArrowRight, Scale, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef } from "react";
import { ConvergenceLogo } from "@/components/brand";
import { setPendingUploadFile } from "@/lib/pendingUpload";

export default function Home() {
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);

  function handleFileChosen(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setPendingUploadFile(file);
    router.push("/review");
  }

  return (
    <main className="flex min-h-screen flex-col bg-[#111216] text-[#f7f7f5]">
      <header className="flex items-center gap-4 px-6 py-6 lg:px-10">
        <ConvergenceLogo />
        <div className="hidden h-8 w-px bg-[#2c2d33] sm:block" />
        <div className="hidden sm:block">
          <div className="font-display text-xl font-bold tracking-[-0.03em] text-white">
            LexiSA
          </div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-[#8b8d94]">
            Contract intelligence
          </div>
        </div>
      </header>

      <section className="flex flex-1 flex-col items-center justify-center px-6 py-16 text-center">
        <span className="mb-5 inline-flex items-center rounded-full border border-[#2c2d33] bg-[#17181c] px-3 py-1 text-[10px] font-bold uppercase tracking-[0.2em] text-[#ff2b36]">
          Convergence3
        </span>
        <h1 className="max-w-2xl font-display text-4xl font-bold tracking-[-0.04em] text-white sm:text-5xl">
          Welcome to LexiSA
        </h1>
        <p className="mt-4 max-w-xl text-base leading-7 text-[#b4b6bd] sm:text-lg">
          Plain-language contract intelligence for South African SMMEs, grounded in the CPA,
          POPIA, BCEA and AFSA arbitration standards.
        </p>
        <p className="mt-8 text-sm font-semibold uppercase tracking-[0.16em] text-[#6d7480]">
          What do you want to do?
        </p>

        <div className="mt-6 grid w-full max-w-3xl gap-5 sm:grid-cols-2">
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.docx"
            onChange={handleFileChosen}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            className="group flex flex-col items-start rounded-2xl border border-[#2c2d33] bg-[#17181c] p-7 text-left transition-colors hover:border-[#e30613] hover:bg-[#1c1416]"
          >
            <span className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-[#e30613]/15 text-[#ff2b36]">
              <Upload size={22} />
            </span>
            <h2 className="font-display text-xl font-bold tracking-[-0.02em] text-white">
              Upload a legal document
            </h2>
            <p className="mt-2 text-sm leading-6 text-[#9ea1a8]">
              Choose a PDF or Word contract from your computer for an instant risk review, with
              clause-by-clause redlines and a downloadable redlined PDF.
            </p>
            <span className="mt-5 inline-flex items-center gap-1.5 text-sm font-bold text-[#ff2b36]">
              Choose a file
              <ArrowRight size={15} className="transition-transform group-hover:translate-x-1" />
            </span>
          </button>

          <Link
            href="/ask"
            className="group flex flex-col items-start rounded-2xl border border-[#2c2d33] bg-[#17181c] p-7 text-left transition-colors hover:border-[#3d6fc9] hover:bg-[#131a24]"
          >
            <span className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-[#0b469d]/20 text-[#6d91c6]">
              <Scale size={22} />
            </span>
            <h2 className="font-display text-xl font-bold tracking-[-0.02em] text-white">
              Query the South African Law
            </h2>
            <p className="mt-2 text-sm leading-6 text-[#9ea1a8]">
              Ask a plain-language legal question and get an answer grounded in South African
              legislation, with citations.
            </p>
            <span className="mt-5 inline-flex items-center gap-1.5 text-sm font-bold text-[#6d91c6]">
              Ask a question
              <ArrowRight size={15} className="transition-transform group-hover:translate-x-1" />
            </span>
          </Link>
        </div>
      </section>

      <footer className="px-6 pb-8 text-center text-[11px] text-[#5c5e66]">
        General information, not legal advice. Built by Convergence3.
      </footer>
    </main>
  );
}
