# TransMiTracker — AI Contribution Policy

TransMiTracker is developed with AI assistance under human supervision.

## Commit attribution

- Keep the human developer as the Git commit author.
- When Codex materially contributes to a commit, include `Assisted-by: OpenAI Codex` in the commit message.
- Only include `Reviewed-with: ChatGPT (OpenAI)` when ChatGPT actually reviewed the relevant implementation.
- Do not invent GitHub identities or email addresses for AI systems.
- Never attribute contributions to tools that did not participate.

## Development standards

- Preserve existing tests and architectural contracts.
- Run the project's verification suite before declaring a phase complete.
- Document limitations and distinguish synthetic tests from real operational validation.
- Do not commit credentials, personal profiles, local databases or other sensitive information.
- Require explicit human approval before starting the next implementation phase.