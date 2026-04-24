import { useCallback, useEffect, useRef, useState } from "react";

// Wraps the Fullscreen API around a container ref. ``isFullscreen`` tracks
// document state (not local state) so the UI stays in sync when the user
// exits via Escape, the OS, or devtools -- things that bypass our toggle.
export function useFullscreen<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const onChange = () => setIsFullscreen(document.fullscreenElement === ref.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const toggle = useCallback(() => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else if (ref.current) {
      ref.current.requestFullscreen();
    }
  }, []);

  return { ref, isFullscreen, toggle };
}
