import { Loader2, AlertCircle, Inbox } from "lucide-react";

export function LoadingState({ label = "Loading..." }) {
  return (
    <div className="flex items-center justify-center gap-2 text-text-secondary text-sm py-16">
      <Loader2 className="w-4 h-4 animate-spin" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({ message = "Something went wrong loading this data." }) {
  return (
    <div className="flex flex-col items-center gap-2 text-signal-red text-sm py-16">
      <AlertCircle className="w-5 h-5" />
      <span>{message}</span>
    </div>
  );
}

export function EmptyState({ title = "No data yet", message = "Once data is ingested, results will appear here." }) {
  return (
    <div className="flex flex-col items-center gap-2 text-text-tertiary text-sm py-16">
      <Inbox className="w-6 h-6" />
      <span className="text-text-secondary">{title}</span>
      <span className="text-xs text-center max-w-xs">{message}</span>
    </div>
  );
}

export function PageHeader({ title, description, children }) {
  return (
    <div className="flex items-start justify-between px-8 pt-7 pb-5 border-b border-border-subtle bg-bg-base sticky top-0 z-10">
      <div>
        <h1 className="text-lg font-semibold text-text-primary">{title}</h1>
        {description && <p className="text-xs text-text-secondary mt-0.5 max-w-2xl">{description}</p>}
      </div>
      {children && <div className="flex items-center gap-2 flex-shrink-0">{children}</div>}
    </div>
  );
}
