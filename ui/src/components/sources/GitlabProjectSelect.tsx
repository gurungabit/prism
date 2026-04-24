import { searchGitlabProjects, type GitLabProject } from "../../lib/api";
import { GitlabEntitySelect } from "./GitlabEntitySelect";

interface Props {
  value: string;
  onChange: (path: string) => void;
  label?: string;
  placeholder?: string;
}

// Project-picker variant of ``GitlabEntitySelect``. The search endpoint
// falls back to the server-wide service-account token on the backend, so
// the component doesn't collect per-source credentials.
export function GitlabProjectSelect({
  value,
  onChange,
  label = "Project path",
  placeholder = "Search projects…",
}: Props) {
  return (
    <GitlabEntitySelect<GitLabProject>
      value={value}
      onChange={onChange}
      label={label}
      placeholder={placeholder}
      fetcher={async ({ q, page, per_page }) => {
        const data = await searchGitlabProjects({ q, page, per_page });
        return { items: data.projects, has_more: data.has_more };
      }}
      getPath={(p) => p.path_with_namespace}
      getLabel={(p) => p.name}
      getId={(p) => p.id}
    />
  );
}
