"use client";

export function TypingIndicator() {
  return (
    <div className="flex items-start">
      <div className="max-w-[85%] rounded-xl bg-[#f5f5f7] px-3 py-3">
        <div className="flex items-center gap-1">
          <span className="text-sm text-[#1d1d1f]">Coach is thinking</span>
          <span className="inline-flex gap-0.5">
            <span
              className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#6e6e73]"
              style={{ animationDelay: "0ms" }}
            />
            <span
              className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#6e6e73]"
              style={{ animationDelay: "150ms" }}
            />
            <span
              className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#6e6e73]"
              style={{ animationDelay: "300ms" }}
            />
          </span>
        </div>
      </div>
    </div>
  );
}
