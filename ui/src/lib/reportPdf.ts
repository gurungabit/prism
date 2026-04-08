import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";

import type { PRISMReport } from "./schemas";

type PdfColor = [number, number, number];

const COLORS = {
  ink: [33, 37, 41],
  muted: [99, 104, 119],
  border: [219, 223, 233],
  accent: [45, 138, 126],
  accentSoft: [231, 245, 243],
  success: [28, 126, 96],
  warning: [198, 129, 22],
  danger: [192, 68, 91],
  slate: [244, 246, 248],
  white: [255, 255, 255],
} satisfies Record<string, PdfColor>;

const PAGE = {
  width: 210,
  height: 297,
  marginX: 16,
  marginTop: 18,
  marginBottom: 18,
};

const BODY_WIDTH = PAGE.width - PAGE.marginX * 2;
const CONTENT_X = PAGE.marginX;

function getTextBlockMetrics(
  doc: jsPDF,
  text: string,
  width: number,
  fontSize: number,
): {
  lines: string[];
  lineHeight: number;
  height: number;
} {
  const lines = doc.splitTextToSize(text, width) as string[];
  const scaleFactor = doc.internal.scaleFactor || 1;
  const lineHeight = doc.getLineHeightFactor() * fontSize / scaleFactor;
  return {
    lines,
    lineHeight,
    height: lines.length * lineHeight + lineHeight * 0.2,
  };
}

function confidencePercent(value: number): string {
  const normalized = value > 1 ? value : value * 100;
  return `${Math.round(normalized)}%`;
}

function stripMarkdown(value: string): string {
  return value
    .replace(/```[\s\S]*?```/g, "")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/_([^_]+)_/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function formatDate(value?: string): string {
  if (!value) return new Date().toLocaleDateString();
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function slugify(value: string): string {
  const normalized = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 50);
  return normalized || "analysis-report";
}

function ensureSpace(doc: jsPDF, y: number, needed: number): number {
  if (y + needed <= PAGE.height - PAGE.marginBottom) return y;
  doc.addPage();
  addPageChrome(doc);
  return PAGE.marginTop + 10;
}

function setDrawColor(doc: jsPDF, color: PdfColor): void {
  doc.setDrawColor(color[0], color[1], color[2]);
}

function setFillColor(doc: jsPDF, color: PdfColor): void {
  doc.setFillColor(color[0], color[1], color[2]);
}

function setTextColor(doc: jsPDF, color: PdfColor): void {
  doc.setTextColor(color[0], color[1], color[2]);
}

function addPageChrome(doc: jsPDF): void {
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();

  setDrawColor(doc, COLORS.border);
  doc.setLineWidth(0.3);
  doc.line(PAGE.marginX, PAGE.marginTop - 6, pageWidth - PAGE.marginX, PAGE.marginTop - 6);
  doc.line(PAGE.marginX, pageHeight - PAGE.marginBottom + 2, pageWidth - PAGE.marginX, pageHeight - PAGE.marginBottom + 2);

  doc.setFont("helvetica", "bold");
  doc.setFontSize(8);
  setTextColor(doc, COLORS.muted);
  doc.text("PRISM", PAGE.marginX, PAGE.marginTop - 9);
}

function addPageNumbers(doc: jsPDF): void {
  const totalPages = doc.getNumberOfPages();
  for (let page = 1; page <= totalPages; page += 1) {
    doc.setPage(page);
    const pageWidth = doc.internal.pageSize.getWidth();
    const pageHeight = doc.internal.pageSize.getHeight();
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    setTextColor(doc, COLORS.muted);
    doc.text(`Page ${page} of ${totalPages}`, pageWidth - PAGE.marginX, pageHeight - 8, {
      align: "right",
    });
  }
}

function pickHeadlineFontSize(title: string): number {
  const length = title.trim().length;
  if (length > 240) return 11.5;
  if (length > 190) return 12.5;
  if (length > 140) return 13.5;
  if (length > 90) return 14.5;
  return 15.5;
}

function addSectionTitle(doc: jsPDF, y: number, title: string, eyebrow?: string): number {
  // Reserve enough for title + separator + at least a few lines of content
  // so headers never sit stranded at the bottom of a page
  const minReserve = eyebrow ? 40 : 35;
  y = ensureSpace(doc, y, minReserve);

  if (eyebrow) {
    doc.setFont("helvetica", "bold");
    doc.setFontSize(8);
    setTextColor(doc, COLORS.accent);
    doc.text(eyebrow.toUpperCase(), PAGE.marginX, y);
    y += 5;
  }

  doc.setFont("helvetica", "bold");
  doc.setFontSize(13.5);
  setTextColor(doc, COLORS.ink);
  doc.text(title, PAGE.marginX, y);
  y += 3;

  setDrawColor(doc, COLORS.border);
  doc.setLineWidth(0.35);
  doc.line(PAGE.marginX, y + 1, PAGE.marginX + BODY_WIDTH, y + 1);

  return y + 6;
}

function addParagraph(doc: jsPDF, y: number, text: string, width = BODY_WIDTH, options?: { muted?: boolean; fontSize?: number }): number {
  const content = stripMarkdown(text);
  if (!content) return y;

  const fontSize = options?.fontSize ?? 10.5;
  doc.setFont("helvetica", "normal");
  doc.setFontSize(fontSize);
  setTextColor(doc, options?.muted ? COLORS.muted : COLORS.ink);

  const metrics = getTextBlockMetrics(doc, content, width, fontSize);
  const advance = metrics.height + 3;
  y = ensureSpace(doc, y, advance);
  doc.text(metrics.lines, PAGE.marginX, y, { baseline: "top" });
  return y + advance;
}

function addLabeledParagraph(doc: jsPDF, y: number, label: string, text: string): number {
  const content = stripMarkdown(text);
  if (!content) return y;

  y = ensureSpace(doc, y, 14);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(8);
  setTextColor(doc, COLORS.muted);
  doc.text(label.toUpperCase(), PAGE.marginX, y);
  y += 4.5;

  return addParagraph(doc, y, content);
}

function addBulletList(doc: jsPDF, y: number, items: string[], accent: PdfColor = COLORS.accent): number {
  const cleanItems = items.map(stripMarkdown).filter(Boolean);
  if (cleanItems.length === 0) return y;

  cleanItems.forEach((item) => {
    const fontSize = 10.5;
    const metrics = getTextBlockMetrics(doc, item, BODY_WIDTH - 6, fontSize);
    const itemHeight = Math.max(metrics.height, 5);
    const advance = itemHeight + 2.5;
    y = ensureSpace(doc, y, advance);
    setFillColor(doc, accent);
    doc.circle(PAGE.marginX + 1.5, y + 2, 0.8, "F");
    doc.setFont("helvetica", "normal");
    doc.setFontSize(fontSize);
    setTextColor(doc, COLORS.ink);
    doc.text(metrics.lines, PAGE.marginX + 5, y, { baseline: "top" });
    y += advance;
  });

  return y + 2;
}

function addStatCards(doc: jsPDF, y: number, report: PRISMReport): number {
  const supportingTeams =
    report.team_routing?.supporting_teams.map((team) => team.name).filter(Boolean) ?? [];
  const affectedServices =
    report.affected_services.map((service) => service.name).filter(Boolean) ?? [];
  const blockingDependencies =
    report.dependencies.blocking
      .slice(0, 2)
      .map((edge) => `${edge.from_service} -> ${edge.to_service}`) ?? [];

  const items = [
    {
      label: "Recommended Owner",
      value: report.team_routing?.primary_team.name || "Unclear",
    },
    {
      label: "Supporting Teams",
      value: supportingTeams.length > 0 ? supportingTeams.join(", ") : "None identified",
    },
    {
      label: "Services In Scope",
      value: affectedServices.length > 0 ? affectedServices.join(", ") : "None identified",
    },
    {
      label: "Overall Risk",
      value: report.risk_assessment?.overall_risk || "unknown",
    },
    {
      label: "Estimated Effort",
      value: report.effort_estimate
        ? `${report.effort_estimate.total_days_min}-${report.effort_estimate.total_days_max} days`
        : "unknown",
    },
    {
      label: "Evidence Base",
      value: `${report.coverage_report.documents_cited} cited from ${report.coverage_report.documents_retrieved} retrieved documents`,
    },
  ];

  if (blockingDependencies.length > 0) {
    items.push({
      label: "Primary Blockers",
      value: blockingDependencies.join("; "),
    });
  }

  const labelWidth = 40;
  const valueWidth = BODY_WIDTH - labelWidth;
  const valueFontSize = 9.8;
  const labelFontSize = 7.5;
  const rowPadY = 2.8;

  y = addSectionTitle(doc, y, "Overview");

  items.forEach((item, index) => {
    doc.setFont("helvetica", "normal");
    doc.setFontSize(valueFontSize);
    const metrics = getTextBlockMetrics(doc, item.value, valueWidth, valueFontSize);
    const contentHeight = Math.max(4, metrics.height);
    const rowHeight = contentHeight + rowPadY * 2;
    y = ensureSpace(doc, y, rowHeight + 1);

    // Alternate row background
    if (index % 2 === 0) {
      setFillColor(doc, COLORS.slate);
      doc.rect(CONTENT_X, y, BODY_WIDTH, rowHeight, "F");
    }

    // Label — vertically centered in the row
    const labelY = y + rowPadY + contentHeight / 2;
    doc.setFont("helvetica", "bold");
    doc.setFontSize(labelFontSize);
    setTextColor(doc, COLORS.muted);
    doc.text(item.label.toUpperCase(), CONTENT_X + 2, labelY, { baseline: "middle" });

    // Value — vertically centered in the row
    doc.setFont("helvetica", "normal");
    doc.setFontSize(valueFontSize);
    setTextColor(doc, COLORS.ink);
    if (metrics.lines.length <= 1) {
      doc.text(metrics.lines[0] ?? "", CONTENT_X + labelWidth, labelY, { baseline: "middle" });
    } else {
      doc.text(metrics.lines, CONTENT_X + labelWidth, y + rowPadY, { baseline: "top" });
    }

    y += rowHeight;
  });

  return y + 2;
}

function addHeaderBlock(doc: jsPDF, report: PRISMReport): number {
  const y = PAGE.marginTop + 3;
  const title = report.analysis_input?.requirement || report.requirement;
  const headlineFontSize = pickHeadlineFontSize(title);

  doc.setFont("helvetica", "bold");
  doc.setFontSize(headlineFontSize);
  const titleMetrics = getTextBlockMetrics(doc, title, BODY_WIDTH, headlineFontSize);
  const titleLines = titleMetrics.lines;
  const titleHeight = titleMetrics.height;
  const metaY = y + 5 + titleHeight + 2;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(8);
  setTextColor(doc, COLORS.accent);
  doc.text("PRISM ANALYSIS BRIEF", CONTENT_X, y);

  doc.setFont("helvetica", "bold");
  doc.setFontSize(headlineFontSize);
  setTextColor(doc, COLORS.ink);
  doc.text(titleLines, CONTENT_X, y + 5, {
    baseline: "top",
    maxWidth: BODY_WIDTH,
  });

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  setTextColor(doc, COLORS.muted);
  doc.text(`Generated ${formatDate(report.created_at)}`, CONTENT_X, metaY);
  doc.text(`Run ${report.analysis_id}`, CONTENT_X + BODY_WIDTH, metaY, {
    align: "right",
  });

  setDrawColor(doc, COLORS.border);
  doc.setLineWidth(0.4);
  doc.line(CONTENT_X, metaY + 3.5, CONTENT_X + BODY_WIDTH, metaY + 3.5);

  return metaY + 10;
}

function addSummaryBand(doc: jsPDF, y: number, report: PRISMReport): number {
  y = addSectionTitle(doc, y, "Executive Summary");
  return addParagraph(doc, y, report.executive_summary || report.requirement, BODY_WIDTH);
}

function addMiniTable(
  doc: jsPDF,
  y: number,
  title: string,
  rows: string[][],
  head: string[],
  options?: {
    columnStyles?: Record<number, { cellWidth?: number }>;
    theme?: "grid" | "striped" | "plain";
    leadText?: string;
  },
): number {
  if (rows.length === 0) return y;

  const leadTextReserve = options?.leadText ? 12 : 0;
  y = ensureSpace(doc, y, 40 + leadTextReserve);
  y = addSectionTitle(doc, y, title);
  if (options?.leadText) {
    y = addParagraph(doc, y, options.leadText, BODY_WIDTH, { muted: true });
  }

  autoTable(doc, {
    startY: y,
    head: [head],
    body: rows,
    theme: options?.theme ?? "striped",
    pageBreak: "auto",
    rowPageBreak: "avoid",
    margin: { left: PAGE.marginX, right: PAGE.marginX },
    styles: {
      font: "helvetica",
      fontSize: 9,
      cellPadding: 2.2,
      lineColor: COLORS.border,
      textColor: COLORS.ink,
      valign: "top",
    },
    headStyles: {
      fillColor: COLORS.accentSoft,
      textColor: COLORS.accent,
      fontStyle: "bold",
      lineColor: COLORS.border,
    },
    alternateRowStyles: {
      fillColor: COLORS.slate,
    },
    columnStyles: options?.columnStyles,
    didDrawPage: () => {
      addPageChrome(doc);
    },
  });

  return ((doc as jsPDF & { lastAutoTable?: { finalY?: number } }).lastAutoTable?.finalY ?? y) + 6;
}

export async function downloadAnalysisReportPdf(report: PRISMReport): Promise<void> {
  const doc = new jsPDF({
    format: "a4",
    unit: "mm",
    compress: true,
  });
  const title = report.analysis_input?.requirement || report.requirement;

  doc.setProperties({
    title: `${title} - PRISM Analysis Brief`,
    subject: "Cross-team requirement analysis",
    author: "PRISM",
    creator: "PRISM",
    keywords: "analysis, product owner, architecture, requirements",
  });

  addPageChrome(doc);

  const SECTION_GAP = 6;

  let y = addHeaderBlock(doc, report);
  y = addStatCards(doc, y, report);
  y += SECTION_GAP;
  y = addSummaryBand(doc, y, report);

  if (report.analysis_input?.business_goal) {
    y += SECTION_GAP;
    y = addSectionTitle(doc, y, "Business Goal");
    y = addParagraph(doc, y, report.analysis_input.business_goal);
  }

  if (
    report.analysis_input?.context ||
    report.analysis_input?.constraints ||
    report.analysis_input?.known_teams ||
    report.analysis_input?.known_services ||
    report.analysis_input?.questions_to_answer
  ) {
    y += SECTION_GAP;
    y = addSectionTitle(doc, y, "Input Context");
    y = addLabeledParagraph(doc, y, "Context", report.analysis_input?.context || "");
    y = addLabeledParagraph(doc, y, "Constraints", report.analysis_input?.constraints || "");
    y = addLabeledParagraph(doc, y, "Known Teams", report.analysis_input?.known_teams || "");
    y = addLabeledParagraph(doc, y, "Known Services", report.analysis_input?.known_services || "");
    y = addLabeledParagraph(doc, y, "Questions To Answer", report.analysis_input?.questions_to_answer || "");
  }

  if (report.recommendations.length > 0) {
    y += SECTION_GAP;
    y = addSectionTitle(doc, y, "Recommendations");
    y = addBulletList(doc, y, report.recommendations, COLORS.accent);
  }

  if (report.caveats.length > 0 || report.data_quality_summary) {
    y += SECTION_GAP;
    y = addSectionTitle(doc, y, "Caveats And Data Quality");
    if (report.data_quality_summary) {
      y = addParagraph(doc, y, report.data_quality_summary, BODY_WIDTH, { muted: true });
    }
    if (report.caveats.length > 0) {
      y = addBulletList(doc, y, report.caveats, COLORS.warning);
    }
  }

  if (report.team_routing) {
    y += SECTION_GAP;
    y = addMiniTable(
      doc,
      y,
      "Team Routing",
      [
        [
          report.team_routing.primary_team.name,
          "primary",
          confidencePercent(report.team_routing.primary_team.confidence),
          stripMarkdown(report.team_routing.primary_team.justification || "-"),
        ],
        ...report.team_routing.supporting_teams.map((team) => [
          team.name,
          team.role || "supporting",
          confidencePercent(team.confidence),
          stripMarkdown(team.justification || "-"),
        ]),
      ],
      ["Team", "Role", "Confidence", "Why"],
      {
        leadText: report.team_routing_narrative,
        columnStyles: {
          0: { cellWidth: 34 },
          1: { cellWidth: 24 },
          2: { cellWidth: 26 },
        },
      },
    );
  }

  if (report.impact_matrix.length > 0) {
    y += SECTION_GAP;
    y = addMiniTable(
      doc,
      y,
      "Cross-Team Impact Matrix",
      report.impact_matrix.map((row) => [
        row.team,
        row.service,
        row.role || "-",
        row.confidence,
        stripMarkdown(row.why_involved || "-"),
        stripMarkdown(row.blocker || "-"),
      ]),
      ["Team", "Service", "Role", "Confidence", "Why Involved", "Blocker"],
      {
        columnStyles: {
          0: { cellWidth: 28 },
          1: { cellWidth: 28 },
          2: { cellWidth: 20 },
          3: { cellWidth: 22 },
        },
      },
    );
  }

  const dependencyRows = [
    ...(report.dependencies.blocking || []).map((edge) => ["blocking", edge.from_service, edge.to_service, stripMarkdown(edge.reason || "-")]),
    ...(report.dependencies.impacted || []).map((edge) => ["non-blocking", edge.from_service, edge.to_service, stripMarkdown(edge.reason || "-")]),
    ...(report.dependencies.informational || []).map((edge) => ["context", edge.from_service, edge.to_service, stripMarkdown(edge.reason || "-")]),
  ];
  if (dependencyRows.length > 0) {
    y += SECTION_GAP;
    y = addMiniTable(
      doc,
      y,
      "Dependencies",
      dependencyRows,
      ["Type", "From", "To", "Reason"],
      {
        leadText: report.dependency_narrative,
        columnStyles: {
          0: { cellWidth: 22 },
          1: { cellWidth: 34 },
          2: { cellWidth: 34 },
        },
      },
    );
  }

  if (report.risk_assessment?.risks.length) {
    y += SECTION_GAP;
    y = addMiniTable(
      doc,
      y,
      "Risks",
      report.risk_assessment.risks.map((risk) => [
        risk.level,
        risk.category.replace(/_/g, " "),
        stripMarkdown(risk.description),
        stripMarkdown(risk.mitigation || "-"),
      ]),
      ["Level", "Category", "Description", "Mitigation"],
      {
        leadText: report.risk_narrative,
        columnStyles: {
          0: { cellWidth: 18 },
          1: { cellWidth: 30 },
        },
      },
    );
  }

  if (report.effort_estimate?.breakdown.length) {
    y += SECTION_GAP;
    y = addMiniTable(
      doc,
      y,
      "Effort Breakdown",
      report.effort_estimate.breakdown.map((item) => [
        item.task,
        item.team,
        `${item.days_min}-${item.days_max} days`,
      ]),
      ["Task", "Team", "Estimate"],
      {
        leadText: report.effort_narrative,
        columnStyles: {
          1: { cellWidth: 34 },
          2: { cellWidth: 28 },
        },
      },
    );
  }

  if (report.verification_report.verified_claims.length > 0) {
    y += SECTION_GAP;
    y = addMiniTable(
      doc,
      y,
      "Verified Claims",
      report.verification_report.verified_claims.slice(0, 8).map((claim) => [
        stripMarkdown(claim.claim),
        claim.confidence,
        claim.supporting_doc,
      ]),
      ["Claim", "Confidence", "Supporting Doc"],
      {
        columnStyles: {
          1: { cellWidth: 24 },
        },
      },
    );
  }

  const verificationItems = [
    ...report.verification_report.unsupported_claims.map((item) => `Unsupported: ${item}`),
    ...report.coverage_report.critical_gaps.map((item) => `Critical gap: ${item}`),
    ...report.coverage_report.stale_sources.slice(0, 8).map((item) => `Stale source: ${item}`),
  ];
  if (verificationItems.length > 0) {
    y += SECTION_GAP;
    y = addSectionTitle(doc, y, "Verification And Gaps");
    y = addBulletList(doc, y, verificationItems, COLORS.warning);
  }

  if (report.all_sources.length > 0) {
    y += SECTION_GAP;
    y = addMiniTable(
      doc,
      y,
      "Sources",
      report.all_sources.slice(0, 18).map((source) => [
        source.platform,
        source.path,
        source.last_modified || "-",
        source.is_stale ? "stale" : "current",
      ]),
      ["Platform", "Source", "Updated", "Status"],
      {
        columnStyles: {
          0: { cellWidth: 22 },
          2: { cellWidth: 24 },
          3: { cellWidth: 18 },
        },
      },
    );
  }

  addPageNumbers(doc);

  const fileName = `${slugify(title)}-prism-report.pdf`;
  doc.save(fileName);
}
