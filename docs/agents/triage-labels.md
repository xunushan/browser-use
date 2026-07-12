# Triage Labels

The five canonical triage roles and their labels:

| Role | Label | Meaning |
|------|-------|---------|
| needs-triage | `needs-triage` | Maintainer needs to evaluate |
| needs-info | `needs-info` | Waiting on reporter |
| ready-for-agent | `ready-for-agent` | Fully specified, AFK-ready (an agent can pick it up with no human context) |
| ready-for-human | `ready-for-human` | Needs human implementation |
| wontfix | `wontfix` | Will not be actioned |

## Usage

When `/triage` processes an incoming issue, it moves it through this state machine by applying the appropriate label.
