"use client";

export function PrintButton({ label }: { label: string }) {
  return <button onClick={() => window.print()}>{label}</button>;
}
