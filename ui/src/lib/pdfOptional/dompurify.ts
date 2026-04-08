const DOMPurify = {
  sanitize(): never {
    throw new Error(
      "DOMPurify-backed jsPDF HTML export is disabled in PRISM. The PDF generator uses native jsPDF primitives instead.",
    );
  },
};

export default DOMPurify;
