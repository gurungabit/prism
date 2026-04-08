const canvg = {
  fromString(): never {
    throw new Error(
      "canvg-backed SVG conversion is disabled in PRISM. The PDF generator uses native jsPDF primitives instead.",
    );
  },
};

export default canvg;
