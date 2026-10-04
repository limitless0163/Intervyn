import { runAvatars } from "./commands/avatars";
import { runInit } from "./commands/init";
import { runSkills } from "./commands/skills";
import { runTraces } from "./commands/traces";

const [, , command, ...args] = process.argv;

function printHelp(): void {
  console.log(`intervyn — Intervyn CLI

Usage:
  intervyn init             Guided setup: pick a run mode, enter provider
                                 keys, and write the .env files
  intervyn init --no-input  Non-interactive: copy .env.example → .env
                                 (for CI / scripted setups; --yes is an alias)
  intervyn init --force     Re-sync the local-dev copies from the root .env
                                 (non-interactive)
  intervyn skills lint      Validate skill packs in backend/skills/ (frontmatter
                                 schema + conventions) before opening a PR
  intervyn avatars pull     Fetch published avatar packs (SHA-256 verified
                                 against frontend/cli/avatars.manifest.json)
  intervyn avatars verify   Pre-flight local avatar files before submitting
                                 a pack (technical contract + hashes)
  intervyn traces [list]    Show recent agent runs (prep/score/live) from
                                 the local trace store (.intervyn/traces)
  intervyn traces show <id> Replay one run: nested spans, LLM calls, errors

\`init\` writes three files:
  .env                 → read by docker compose (the full stack)
  backend/.env      → read by the Python agent in local dev (pnpm dev)
  frontend/.env.local  → read by the Next.js app in local dev (pnpm dev)

In a terminal, \`init\` runs an interactive wizard: choose a run mode (live voice
/ prep-only / offline demo), then enter only the keys that mode needs (existing
values are offered as defaults, so re-running to update a key is safe). With no
TTY it falls back to copying .env.example so you can fill in keys by hand.`);
}

async function main(): Promise<void> {
  switch (command) {
    case "init":
      await runInit(args);
      break;
    case "skills":
      await runSkills(args);
      break;
    case "avatars":
      await runAvatars(args);
      break;
    case "traces":
      await runTraces(args);
      break;
    case undefined:
    case "help":
    case "--help":
    case "-h":
      printHelp();
      break;
    default:
      console.error(`Unknown command: ${command}\n`);
      printHelp();
      process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
