import { useEffect, useState } from "react";

// Tiny hook that wires Cmd+K / Ctrl+K to a boolean ``open`` flag for a
// command-palette modal. Suppresses the shortcut when the user is in
// a text input / textarea / contenteditable so typing "K" doesn't
// hijack into the palette mid-edit. Bound globally so any chat route
// (and later, any palette consumer) can open it.
export function useCommandPalette() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const isShortcut = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k";
      if (!isShortcut) return;
      // Don't hijack the shortcut if the user is editing text in
      // another input -- they may have a different binding in mind
      // (browsers' default Cmd+K is the address bar). We only steal
      // it from "neutral" focus.
      const active = document.activeElement;
      const inEditable =
        active instanceof HTMLInputElement ||
        active instanceof HTMLTextAreaElement ||
        (active instanceof HTMLElement && active.isContentEditable);
      if (inEditable) return;
      e.preventDefault();
      setOpen((v) => !v);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return { open, setOpen };
}
