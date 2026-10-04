# COMMIT_INSTRUCTIONS.md

Commit the current code changes to Git.

Requirements:
- Review `git status` and `git diff` before committing.
- Commit only relevant changes; do not include secrets, credentials, temporary files, or unrelated files.
- Split unrelated changes into separate commits when appropriate.
- Use standard English Conventional Commits format:
  `<type>(<scope>): <description>`
- Use lowercase types such as `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `style`, or `build`.
- Keep the subject concise, specific, and written in imperative style.
- Add a short commit body only when necessary to explain important changes.
- Run relevant tests or checks before committing when available.
- Do not add unnecessary signatures, AI attribution, or `Co-authored-by` lines.
- Complete the commit directly without asking for confirmation unless there is a blocking issue.