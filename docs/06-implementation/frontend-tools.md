---
id: IMPL-FRONTEND-TOOLS-001
kind: implementation_note
status: accepted
---

# Frontend tools and skills

The project-local Codex skills live under `.agents/skills/`. They support future
frontend work against the references in `references/`; this change does not
implement that frontend work.

| Source | Commit | Installed resource | License / constraint |
| --- | --- | --- | --- |
| [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | `8cf362b6fea7b6e6a5f38db5a737faccd6d30bdc5` | `.agents/skills/impeccable` | Apache-2.0; local scripts are not executed during install |
| [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | `14ddef5c05e52d7c253b8f0129de7bcd1045ae5b` | `.agents/skills/{design,design-system,ui-styling,...}` | MIT; search/generation scripts require review before execution |
| [emilkowalski/skills](https://github.com/emilkowalski/skills) | `da80201b64de7d608a6dc5f723797ce6c65b692b` | `.agents/skills/{emil-design-eng,review-animations,...}` | MIT; guidance-only skill files |
| [juliangarnier/anime](https://github.com/juliangarnier/anime) | `2c9cf8ea00329f6768c7d7902252ed977d75ce42` | `animejs@4.5.0` | MIT; installed through npm |
| [animate-css/animate.css](https://github.com/animate-css/animate.css) | `3f8ab233dbbd9d2fe577528d2296382954be3d1a` | `animate.css@4.1.1` | Package metadata declares Hippocratic-2.1; installed through npm |
| [abi/screenshot-to-code](https://github.com/abi/screenshot-to-code) | `d026163f586dfa8c5c10d28c36edd59a9d3b0e88` | `tools/screenshot-to-code` | Isolated optional tool; requires provider keys and separate runtime |

The screenshot-to-code repository's remote installer was excluded because it
pipes a network script into Python and installs a separate application stack.
No API keys, generated output, or provider integrations were added to HiTrendy.
