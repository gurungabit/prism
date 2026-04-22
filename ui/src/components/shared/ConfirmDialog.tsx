import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

import { Button } from "./Button";
import { Modal } from "./Modal";

export interface ConfirmOptions {
  title: string;
  message?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** "danger" styles the confirm button in red for destructive actions. */
  variant?: "default" | "danger";
}

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn | null>(null);

/**
 * Returns a promise-based confirm() replacement for ``window.confirm``.
 *
 *     const confirm = useConfirm();
 *     if (!(await confirm({ title: "Delete X?", variant: "danger" }))) return;
 */
export function useConfirm(): ConfirmFn {
  const ctx = useContext(ConfirmContext);
  if (!ctx) {
    throw new Error("useConfirm must be used within <ConfirmProvider>");
  }
  return ctx;
}

interface State {
  open: boolean;
  options: ConfirmOptions;
}

const DEFAULT_STATE: State = {
  open: false,
  options: { title: "" },
};

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(DEFAULT_STATE);
  // Resolver is captured when confirm() is called and invoked on user choice.
  // A ref avoids re-rendering the whole tree when we swap resolvers between
  // calls.
  const resolverRef = useRef<((result: boolean) => void) | null>(null);

  const confirm = useCallback<ConfirmFn>(
    (options) =>
      new Promise<boolean>((resolve) => {
        // If another confirm was still open (user spammed a button), resolve
        // the previous one as "cancel" so its caller unblocks cleanly.
        resolverRef.current?.(false);
        resolverRef.current = resolve;
        setState({ open: true, options });
      }),
    [],
  );

  const finish = useCallback((result: boolean) => {
    resolverRef.current?.(result);
    resolverRef.current = null;
    setState((s) => ({ ...s, open: false }));
  }, []);

  const { options } = state;
  const isDanger = options.variant === "danger";

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Modal open={state.open} onClose={() => finish(false)} title={options.title} width="max-w-md">
        <div className="space-y-4">
          <div className="flex gap-3">
            {isDanger && (
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-rose-100 dark:bg-rose-950/50 flex items-center justify-center">
                <AlertTriangle className="w-4 h-4 text-rose-600 dark:text-rose-400" />
              </div>
            )}
            {options.message && (
              <div className="text-[13px] text-zinc-600 dark:text-zinc-400 leading-relaxed">
                {options.message}
              </div>
            )}
          </div>
          <div className="flex justify-end gap-2 pt-2 border-t border-zinc-200/60 dark:border-zinc-700/30">
            <Button variant="ghost" size="sm" onClick={() => finish(false)}>
              {options.cancelLabel ?? "Cancel"}
            </Button>
            <Button
              variant={isDanger ? "danger" : "primary"}
              size="sm"
              onClick={() => finish(true)}
              autoFocus
            >
              {options.confirmLabel ?? "Confirm"}
            </Button>
          </div>
        </div>
      </Modal>
    </ConfirmContext.Provider>
  );
}
