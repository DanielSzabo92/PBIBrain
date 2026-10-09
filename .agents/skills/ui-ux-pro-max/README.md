# UI/UX Pro Max for Codex

An offline, instruction-only Codex skill for designing and reviewing accessible, implementation-ready interfaces. It is especially useful for Windows and WPF applications, while remaining applicable to cross-platform products.

## What it covers

- Information architecture, navigation, and task flows
- WPF layout, controls, resource dictionaries, and interaction patterns
- Forms, filters, data tables, dialogs, and application states
- Keyboard access, focus behavior, contrast, and screen-reader semantics
- Compact, comfortable, and touch-friendly density modes
- Light, dark, and high-contrast themes
- Semantic design tokens, typography, spacing, and motion
- Responsive and adaptive layout reviews

## Install in Codex Windows App

1. Download or clone this repository.
2. Copy the repository folder to `C:\Users\<username>\.codex\skills\ui-ux-pro-max`.
3. Reopen Codex Windows App so the skill is discovered.
4. Invoke it with `$ui-ux-pro-max`.

No packages, scripts, services, or additional data files are required.

## Example prompts

### Review a WPF screen

> Use $ui-ux-pro-max to review this WPF settings window. Improve visual hierarchy, keyboard navigation, focus states, density, and high-contrast behavior. Do not change files until I confirm.

### Design a data-heavy workspace

> Use $ui-ux-pro-max to design an adaptive operations screen with sidebar navigation, filters, a dense data table, bulk actions, and clear loading, empty, error, and permission states.

### Define a theme and token model

> Use $ui-ux-pro-max to define semantic color, typography, spacing, radius, elevation, and motion tokens for light, dark, and high-contrast WPF themes.

## Operating model

The skill works from the user request and authorized local project context. It requires explicit confirmation before file changes and does not use network services, external APIs, package installers, environment variables, secrets, or bundled search tools.

## Repository contents

- [`SKILL.md`](SKILL.md) - complete Codex instructions
- [`agents/openai.yaml`](agents/openai.yaml) - Codex UI metadata
- [`LICENSE`](LICENSE) - MIT License

## License

MIT
