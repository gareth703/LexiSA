export function ConvergenceLogo({ compact = false }: { compact?: boolean }) {
  return <div className={compact ? "flex items-center" : "flex items-center gap-2.5"} aria-label="Convergence3">
    <svg className={compact ? "h-8 w-9" : "h-9 w-10"} viewBox="0 0 80 76" role="img" aria-hidden="true">
      <path d="M40 2 76 68H57L40 37 23 68H4L40 2Z" fill="#e30613" />
      <path d="M40 22 57 53H40L31.5 68H23L40 22Z" fill="#ff2b36" opacity=".78" />
      <path d="m40 37 17 31H40L31.5 53 40 37Z" fill="#b90812" opacity=".9" />
    </svg>
    {!compact && <span className="font-brand text-[24px] font-semibold tracking-[-0.08em] text-white">C<span className="text-[#e30613]">3</span></span>}
  </div>;
}
