import { type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from "react";
import { cn } from "./utils";
export { cn } from "./utils";

export function Button({ className, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={cn("inline-flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50", className)} {...props} />;
}
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl border border-[#d8ded8] bg-white", className)} {...props} />;
}
export function Badge({ className, children, ...props }: HTMLAttributes<HTMLSpanElement> & { children: ReactNode }) {
  return <span className={cn("inline-flex items-center rounded-full px-2 py-1 text-[11px] font-bold uppercase tracking-[0.12em]", className)} {...props}>{children}</span>;
}
export function ScrollArea({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("overflow-auto", className)} {...props} />;
}
