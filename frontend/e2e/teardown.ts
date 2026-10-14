import { execFileSync } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
export default function teardown() {
  const root = path.resolve(process.cwd(), "..");
  const python =
    process.platform === "win32"
      ? path.join(root, "backend/.venv/Scripts/python.exe")
      : path.join(root, "backend/.venv/bin/python");
  execFileSync(python, ["e2e_fixture.py", "cleanup"], {
    cwd: path.join(root, "backend"),
    stdio: "pipe",
  });
  // Keep test evidence in JSON; do not leave newly generated Markdown files.
  function clean(directory: string) {
    if (!fs.existsSync(directory)) return;
    for (const item of fs.readdirSync(directory, { withFileTypes: true })) {
      const file = path.join(directory, item.name);
      if (item.isDirectory()) clean(file);
      else if (item.name === "error-context.md") fs.unlinkSync(file);
    }
  }
  clean(path.join(root, "frontend/test-results"));
}
