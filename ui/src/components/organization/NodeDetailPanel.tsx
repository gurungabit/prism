import { useEffect } from "react";
import { Link } from "@tanstack/react-router";
import {
  ArrowRight,
  Boxes,
  Building2,
  ExternalLink,
  Users,
  X,
} from "lucide-react";

import { Badge } from "../shared/Badge";
import { Button } from "../shared/Button";
import type { OrganizationGraphResponse } from "../../lib/api";

export type SelectedNode =
  | { kind: "org"; id: string }
  | { kind: "team"; id: string }
  | { kind: "service"; id: string };

interface Props {
  selected: SelectedNode | null;
  data: OrganizationGraphResponse;
  onClose: () => void;
}

export function NodeDetailPanel({ selected, data, onClose }: Props) {
  // Esc closes the panel. Mirrors the Modal's UX so keyboard users get a
  // consistent dismiss key across the app.
  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selected, onClose]);

  const open = selected !== null;

  return (
    <>
      {/* Backdrop -- soft dimmer so the graph stays visible but de-emphasized */}
      <div
        onClick={onClose}
        className={`
          fixed inset-0 z-40 bg-black/20 backdrop-blur-[1px]
          transition-opacity duration-150
          ${open ? "opacity-100" : "opacity-0 pointer-events-none"}
        `}
        aria-hidden="true"
      />

      {/* Drawer */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Node details"
        className={`
          fixed top-0 right-0 z-50 h-full w-[400px] max-w-[90vw]
          border-l border-zinc-200 dark:border-zinc-700/40
          bg-white dark:bg-[#1a1a1c]
          shadow-xl
          transition-transform duration-200 ease-out
          ${open ? "translate-x-0" : "translate-x-full"}
        `}
      >
        {selected && <DetailContent selected={selected} data={data} onClose={onClose} />}
      </aside>
    </>
  );
}

function DetailContent({ selected, data, onClose }: Props & { selected: SelectedNode }) {
  if (selected.kind === "org") {
    const org = data.orgs.find((o) => o.id === selected.id);
    if (!org) return <NotFound onClose={onClose} label="organization" />;

    const teamsForOrg = data.teams.filter((t) => t.org_id === org.id);
    const serviceCount = data.services.filter((s) =>
      teamsForOrg.some((t) => t.id === s.team_id),
    ).length;

    return (
      <DetailLayout
        icon={<Building2 className="w-4 h-4 text-[var(--color-accent)] dark:text-[var(--color-accent-dark)]" />}
        kindLabel="Organization"
        title={org.name}
        onClose={onClose}
        detailHref={`/orgs/${org.id}`}
      >
        <Row label="Teams">{teamsForOrg.length}</Row>
        <Row label="Services">{serviceCount}</Row>
        <Row label="Created">{formatDate(org.created_at)}</Row>

        {teamsForOrg.length > 0 && (
          <Section title="Teams">
            <div className="space-y-1.5">
              {teamsForOrg.map((t) => (
                <div
                  key={t.id}
                  className="flex items-center gap-2 text-[12px] text-zinc-600 dark:text-zinc-400"
                >
                  <Users className="w-3 h-3" />
                  <span className="truncate">{t.name}</span>
                </div>
              ))}
            </div>
          </Section>
        )}
      </DetailLayout>
    );
  }

  if (selected.kind === "team") {
    const team = data.teams.find((t) => t.id === selected.id);
    if (!team) return <NotFound onClose={onClose} label="team" />;

    const servicesForTeam = data.services.filter((s) => s.team_id === team.id);

    return (
      <DetailLayout
        icon={<Users className="w-4 h-4 text-zinc-500 dark:text-zinc-400" />}
        kindLabel="Team"
        title={team.name}
        onClose={onClose}
        detailHref={`/teams/${team.id}`}
      >
        {team.description && <Row label="Description">{team.description}</Row>}
        <Row label="Services">{servicesForTeam.length}</Row>
        <Row label="Created">{formatDate(team.created_at)}</Row>

        {servicesForTeam.length > 0 && (
          <Section title="Services">
            <div className="space-y-1.5">
              {servicesForTeam.map((s) => (
                <div
                  key={s.id}
                  className="flex items-center gap-2 text-[12px] text-zinc-600 dark:text-zinc-400"
                >
                  <Boxes className="w-3 h-3" />
                  <span className="truncate">{s.name}</span>
                </div>
              ))}
            </div>
          </Section>
        )}
      </DetailLayout>
    );
  }

  // service
  const svc = data.services.find((s) => s.id === selected.id);
  if (!svc) return <NotFound onClose={onClose} label="service" />;

  const team = data.teams.find((t) => t.id === svc.team_id);
  const outbound = data.dependencies.filter((d) => d.from_service_id === svc.id);
  const inbound = data.dependencies.filter((d) => d.to_service_id === svc.id);

  return (
    <DetailLayout
      icon={<Boxes className="w-4 h-4 text-zinc-500 dark:text-zinc-400" />}
      kindLabel="Service"
      title={svc.name}
      onClose={onClose}
      detailHref={`/services/${svc.id}`}
    >
      {team && <Row label="Team">{team.name}</Row>}
      {svc.description && <Row label="Description">{svc.description}</Row>}
      {svc.repo_url && (
        <Row label="Repo">
          <a
            href={svc.repo_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-[var(--color-accent)] dark:text-[var(--color-accent-dark)] hover:underline truncate"
          >
            {svc.repo_url}
            <ExternalLink className="w-3 h-3 flex-shrink-0" />
          </a>
        </Row>
      )}
      <Row label="Created">{formatDate(svc.created_at)}</Row>

      {outbound.length > 0 && (
        <Section title={`Depends on (${outbound.length})`}>
          <div className="space-y-1.5">
            {outbound.map((d) => (
              <div
                key={`${d.from_service_id}-${d.to_service_id}`}
                className="flex items-center gap-2 text-[12px] text-zinc-600 dark:text-zinc-400"
              >
                <ArrowRight className="w-3 h-3" />
                <span className="truncate">{d.to_service}</span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {inbound.length > 0 && (
        <Section title={`Depended on by (${inbound.length})`}>
          <div className="space-y-1.5">
            {inbound.map((d) => (
              <div
                key={`${d.from_service_id}-${d.to_service_id}`}
                className="flex items-center gap-2 text-[12px] text-zinc-600 dark:text-zinc-400"
              >
                <Boxes className="w-3 h-3" />
                <span className="truncate">{d.from_service}</span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {outbound.length === 0 && inbound.length === 0 && (
        <Section title="Dependencies">
          <p className="text-[12px] text-zinc-400 dark:text-zinc-500">
            No declared dependencies.
          </p>
        </Section>
      )}
    </DetailLayout>
  );
}

// ── building blocks ────────────────────────────────────────────────────────

interface DetailLayoutProps {
  icon: React.ReactNode;
  kindLabel: string;
  title: string;
  onClose: () => void;
  detailHref: string;
  children: React.ReactNode;
}

function DetailLayout({ icon, kindLabel, title, onClose, detailHref, children }: DetailLayoutProps) {
  return (
    <div className="h-full flex flex-col">
      <div className="flex items-start justify-between gap-2 px-5 py-4 border-b border-zinc-200 dark:border-zinc-700/40">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            {icon}
            <Badge variant="neutral" size="sm">
              {kindLabel}
            </Badge>
          </div>
          <h2 className="text-[16px] font-semibold tracking-tight text-zinc-900 dark:text-zinc-100 mt-1.5 truncate">
            {title}
          </h2>
        </div>
        <button
          onClick={onClose}
          aria-label="Close"
          className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-700/30 transition-colors duration-150 flex-shrink-0"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">{children}</div>

      <div className="px-5 py-3 border-t border-zinc-200 dark:border-zinc-700/40">
        {/* Routing here uses the type-less variant of <Link> -- the graph
            panel only needs absolute paths, and threading param-shape
            constraints through the route tree would add zero value. */}
        <Link to={detailHref as never}>
          <Button variant="secondary" size="sm" className="w-full justify-center">
            Open full detail page
          </Button>
        </Link>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[90px_1fr] gap-3 items-start text-[12px]">
      <dt className="text-zinc-400 dark:text-zinc-500 uppercase tracking-wider text-[10px] font-medium pt-0.5">
        {label}
      </dt>
      <dd className="text-zinc-700 dark:text-zinc-300 min-w-0">{children}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="pt-3 border-t border-zinc-200/60 dark:border-zinc-700/30 space-y-2">
      <h3 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
        {title}
      </h3>
      {children}
    </div>
  );
}

function NotFound({ onClose, label }: { onClose: () => void; label: string }) {
  return (
    <div className="h-full flex flex-col items-center justify-center px-5 py-4 text-center">
      <p className="text-[13px] text-zinc-500 dark:text-zinc-400 mb-3">
        That {label} was not found.
      </p>
      <Button size="sm" onClick={onClose}>
        Close
      </Button>
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
