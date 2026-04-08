export default function html2canvas(): never {
  throw new Error(
    "html2canvas-backed jsPDF export is disabled in PRISM. The PDF generator uses native jsPDF primitives instead.",
  );
}
