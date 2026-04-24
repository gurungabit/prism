import { searchGitlabGroups, type GitLabGroup } from "../../lib/api";
import { GitlabEntitySelect } from "./GitlabEntitySelect";

interface Props {
  value: string;
  onChange: (path: string) => void;
  label?: string;
  placeholder?: string;
}

// Group-picker variant of ``GitlabEntitySelect`` used by the source wizard
// when the user toggles to "Whole group" ingest mode.
export function GitlabGroupSelect({
  value,
  onChange,
  label = "Group path",
  placeholder = "Search groups…",
}: Props) {
  return (
    <GitlabEntitySelect<GitLabGroup>
      value={value}
      onChange={onChange}
      label={label}
      placeholder={placeholder}
      fetcher={async ({ q, page, per_page }) => {
        const data = await searchGitlabGroups({ q, page, per_page });
        return { items: data.groups, has_more: data.has_more };
      }}
      getPath={(g) => g.full_path}
      getLabel={(g) => g.name}
      getId={(g) => g.id}
    />
  );
}
