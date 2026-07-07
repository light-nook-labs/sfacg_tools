import type { Plugin } from "@opencode-ai/plugin"
import { execSync } from "child_process"

export default (async ({ project }) => {
  return {
    "tool.execute.after": async (input, output) => {
      if (input.tool === "edit") {
        const filePath = input.args?.filePath as string | undefined
        if (filePath && (filePath.endsWith(".py") || filePath.endsWith("AGENTS.md") || filePath.endsWith("README.md"))) {
          try {
            const result = execSync("uv run python scripts/check_docs.py", {
              cwd: project.path,
              timeout: 30000,
              encoding: "utf-8",
            })
            output.result = (output.result || "") + "\n\n" + result
          } catch (e: any) {
            output.result = (output.result || "") + "\n\n⚠️ Doc sync check failed:\n" + (e.stdout || e.message)
          }
        }
      }
    },
  }
}) satisfies Plugin
